/**
 * The evidence drawer reads top-down in the order a stranger needs: what the model proposed, what the source says,
 * what code decided, what a person decided; the machinery sits behind "Prove it". The case is the Phase 1 run
 * (docs/DEMO-PROOF.md): the model hinted pass, cited one section and was found in another, code computed needs
 * review from 60 against 90 days, and a person confirmed it. Nothing here is decided; every row is the record's.
 */

import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { getRunExplanation, reviewFinding } from "@/lib/api";
import type { FindingView, RunView, SectionView } from "@/lib/types";

const api = vi.hoisted(() => ({
  getRunExplanation: vi.fn<typeof getRunExplanation>(),
  reviewFinding: vi.fn<typeof reviewFinding>(),
}));

vi.mock("@/lib/api", () => ({
  getRunExplanation: api.getRunExplanation,
  reviewFinding: api.reviewFinding,
  errorMessage: (error: unknown) => (error instanceof Error ? error.message : String(error)),
}));

import { EXPLANATION_E5A20E22 } from "./__fixtures__/explanation-e5a20e2283e8416e";
import { EvidenceDrawer } from "./EvidenceDrawer";

const SECTION: SectionView = {
  id: "s0",
  number: "",
  heading: "EXHIBIT 10.102 (part 1)",
  text: "…4.1 TERMINATION WITHOUT CAUSE. Either party may terminate this Agreement without cause upon sixty (60) days prior written notice to the other party.…",
} as unknown as SectionView;

const QUOTE =
  "4.1 TERMINATION WITHOUT CAUSE. Either party may terminate this Agreement without cause upon sixty (60) days prior written notice to the other party.";

function finding(review: FindingView["review"]): FindingView {
  return {
    id: "afa60a7574984690",
    topic: "Termination for convenience",
    status: "needs_review",
    statusSource: "computed_days",
    statusReason: "the contract provides 60 calendar days; the guidance requires at least 90 calendar days",
    conclusion: "Either party may terminate this agreement for convenience with 60 days' written notice.",
    observed: "60 days' written notice",
    required: "at least 90 days",
    guidanceReference: "We require at least 90 days' written notice for termination for convenience.",
    suggestedPosition: "90 days' written notice",
    evidenceKind: "passage",
    review,
    spans: [{ sectionId: "s0", verified: true, method: "relocated:exact", quote: QUOTE, start: 4136, end: 4284, citedSectionLabel: "sec_4", matchCount: 1 }],
  } as unknown as FindingView;
}

const RUN = {
  id: "e5a20e2283e8416e",
  stage: "complete",
  hasGuidance: true,
  guidanceText: "We require at least 90 days' written notice for termination for convenience. Anything shorter needs review.",
  model: "qwen3:8b",
  promptVersion: "answer-v2",
  promptHash: "9dbeb12a871ece17",
  latencyMs: 69000,
  findings: [],
} as unknown as RunView;

const CONFIRMED = { verdict: "confirmed", reviewer: "Pavan", at: "2026-09-30T17:25:00Z", note: null } as FindingView["review"];

function renderDrawer(view: FindingView, onReviewed = vi.fn()) {
  return render(
    <EvidenceDrawer
      finding={view}
      run={RUN}
      guidanceText={null}
      sectionsById={new Map([["s0", SECTION]])}
      onJump={vi.fn()}
      onClose={vi.fn()}
      onReviewed={onReviewed}
      closeRef={null}
      reduceMotion
    />,
  );
}

describe("EvidenceDrawer", () => {
  beforeEach(() => {
    api.getRunExplanation.mockReset();
    api.reviewFinding.mockReset();
    api.getRunExplanation.mockResolvedValue(EXPLANATION_E5A20E22);
  });
  afterEach(cleanup);

  it("shows the Phase 1 finding in four layers, in order, with the machinery behind Prove it", async () => {
    renderDrawer(finding(CONFIRMED));
    const drawer = screen.getByLabelText("Evidence");

    // The four layers appear in this order and nothing technical sits between them.
    const heads = within(drawer)
      .getAllByRole("heading", { level: 4 })
      .map((h) => h.textContent);
    expect(heads).toEqual(["Model proposed", "Source", "Code decided", "Human"]);
    expect(drawer.textContent).not.toContain("sec_4");

    // Model proposed: the model's hint under guidance is its view, in its own words, read from the explanation.
    const model = await within(drawer).findByTestId("layer-model");
    expect(api.getRunExplanation).toHaveBeenCalledWith("e5a20e2283e8416e");
    expect(await within(model).findByText("Within guidance (model's view)")).toBeTruthy();
    expect(model.textContent).toContain("“60 days' written notice” against “at least 90 days”");
    expect(model.textContent).toContain("1 passage; 1 verified");

    // Source: the quote, how it verified, and where it was found in words.
    const source = within(drawer).getByTestId("layer-source");
    expect(within(source).getByText("EXHIBIT 10.102 (part 1)")).toBeTruthy();
    expect(source.textContent).toContain("Verified verbatim in the document text · relocated:exact");
    expect(source.textContent).toContain("Found in “EXHIBIT 10.102 (part 1)”, not in the section the model cited.");

    // Code decided: observed against required, the sentence, the final status; the guidance it was checked against.
    const code = within(drawer).getByTestId("layer-code");
    expect(within(code).getByRole("heading", { name: "Guidance" })).toBeTruthy();
    expect(code.textContent).toContain("the contract provides 60 calendar days; the guidance requires at least 90 calendar days");
    expect(within(code).getByText("Needs review")).toBeTruthy();

    // Human: the person's decision, as recorded, with the control to change it.
    const human = within(drawer).getByTestId("layer-human");
    expect(human.textContent).toContain("Confirmed");
    expect(human.textContent).toContain("by Pavan");
    expect(within(human).getByRole("button", { name: "Clear the decision" })).toBeTruthy();

    // Prove it: collapsed by default; open, it holds the run facts and the full explanation without a second read.
    expect(screen.queryByTestId("why-this-answer")).toBeNull();
    fireEvent.click(within(drawer).getByRole("button", { name: "Prove it" }));
    const proof = await screen.findByTestId("why-this-answer");
    expect(drawer.textContent).toContain("e5a20e2283e8416e");
    expect(proof.textContent).toContain("ModelProposal");
    expect(proof.textContent).toContain("sec_4");
    expect(api.getRunExplanation).toHaveBeenCalledTimes(1);
  });

  it("records a decision from the drawer under a remembered name and hands the review back", async () => {
    window.localStorage.setItem("workbench.reviewer", "Pavan");
    const onReviewed = vi.fn();
    api.reviewFinding.mockResolvedValue({ review: CONFIRMED, reviewHead: "abc" } as unknown as Awaited<ReturnType<typeof reviewFinding>>);
    renderDrawer(finding(null), onReviewed);
    const human = within(screen.getByLabelText("Evidence")).getByTestId("layer-human");
    expect(human.textContent).toContain("No one has decided on this finding yet.");
    fireEvent.click(within(human).getByRole("button", { name: "Confirm" }));
    await vi.waitFor(() => expect(onReviewed).toHaveBeenCalledWith("afa60a7574984690", CONFIRMED));
    expect(api.reviewFinding).toHaveBeenCalledWith("afa60a7574984690", { verdict: "confirmed", reviewer: "Pavan", note: null });
  });

  it("asks for a name once when none is remembered", () => {
    window.localStorage.removeItem("workbench.reviewer");
    renderDrawer(finding(null));
    const human = within(screen.getByLabelText("Evidence")).getByTestId("layer-human");
    fireEvent.click(within(human).getByRole("button", { name: "Dismiss" }));
    expect(within(human).getByLabelText("Your name, recorded with the decision")).toBeTruthy();
    expect(api.reviewFinding).not.toHaveBeenCalled();
  });
});
