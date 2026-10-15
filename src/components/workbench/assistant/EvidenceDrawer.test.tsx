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
  isConflict: (error: unknown) => error instanceof Error && error.name === "ApiError" && (error as Error & { status?: number }).status === 409,
  absolute: (path: string) => `http://api.test${path}`,
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
    latestReviewId: review ? 7 : 0,
    spans: [{ sectionId: "s0", verified: true, method: "relocated:exact", quote: QUOTE, start: 4136, end: 4284, citedSectionLabel: "sec_4", matchCount: 1 }],
    relations: [], // the API always sends the list (runs.relations); empty when the contract's statements touch nothing
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

  it("names the clause a relocated passage sits in, then the reading's section, never the section alone", async () => {
    const base = finding(null);
    const placed = { ...base, spans: base.spans.map((span) => ({ ...span, clauseLabel: "§4.1 Termination Without Cause" })) } as unknown as FindingView;
    renderDrawer(placed);
    const drawer = screen.getByLabelText("Evidence");
    await within(drawer).findByText("Its hint");
    const source = within(drawer).getByTestId("layer-source");
    expect(source.textContent).toContain("Found in §4.1 Termination Without Cause, within EXHIBIT 10.102 (part 1), not in the section the model cited.");
    expect(within(source).getByRole("button", { name: "§4.1 Termination Without Cause" })).toBeTruthy();
  });

  it("keeps the relocation in the Source cell when it also names a value in none of the quotes", async () => {
    // Browser QA, 2026-10-09: the value note replaced "in another section" instead of joining it.
    const relocatedAndUnquoted = { ...finding(null), unquotedValues: ["75 days"] } as unknown as FindingView;
    renderDrawer(relocatedAndUnquoted);
    const drawer = screen.getByLabelText("Evidence");
    await within(drawer).findByText("Its hint");
    const strip = drawer.textContent ?? "";
    expect(strip).toContain("75 days in none of them");
    expect(strip).toContain("in another section");
  });

  it("says which check lowered a finding: a reference check is not a day-count conflict", async () => {
    const lowered = { ...finding(null), statusSource: "reference_check", statusReason: null } as unknown as FindingView;
    renderDrawer(lowered);
    const drawer = screen.getByLabelText("Evidence");
    const code = within(drawer).getByTestId("layer-code");
    expect(within(code).getByRole("heading", { level: 4 }).textContent).toBe("Code lowered it");
    expect(code.textContent).toContain("the conclusion names a section this document does not have");
    expect(drawer.textContent).not.toContain("day counts conflict");
    expect(drawer.textContent).toContain("names a section not in this document");
  });

  it("shows the Phase 1 finding in four layers, in order, with the machinery behind Prove it", async () => {
    renderDrawer(finding(CONFIRMED));
    const drawer = screen.getByLabelText("Evidence");

    // The four layers appear in this order and nothing technical sits between them.
    const heads = within(drawer)
      .getAllByRole("heading", { level: 4 })
      .map((h) => h.textContent);
    expect(heads).toEqual(["Model proposed", "Source", "Code found a conflict", "Human"]);
    expect(drawer.textContent).not.toContain("sec_4");

    // Model proposed: the model's hint under guidance is its view, in its own words, read from the explanation.
    const model = await within(drawer).findByTestId("layer-model");
    expect(api.getRunExplanation).toHaveBeenCalledWith("e5a20e2283e8416e");
    expect(await within(model).findByText("Within guidance (model's view)")).toBeTruthy();
    // The model's phrases are set apart as its own words, with no quotation marks that could pass them off as the contract's.
    expect(model.textContent).toContain("60 days' written notice against at least 90 days");
    const words = [...model.querySelectorAll("span")].map((s) => s.textContent);
    expect(words).toEqual(expect.arrayContaining(["60 days' written notice", "at least 90 days"]));
    expect(model.textContent).toContain("1 passage; 1 found in the document text");
    // What the model suggested and where it pointed in the guidance are the model's, and sit in its layer.
    expect(model.textContent).toContain("It suggested90 days' written notice");
    expect(model.textContent).toContain("It pointed at");

    // Source: the quote, how it verified, and where it was found in words.
    const source = within(drawer).getByTestId("layer-source");
    expect(within(source).getByText("EXHIBIT 10.102 (part 1)")).toBeTruthy();
    expect(source.textContent).toContain("Found in the document text · relocated:exact");
    // What code checked is said beside the passages: their presence in the text, not that they support the answer.
    expect(within(source).getByTestId("source-limit").textContent).toContain("Whether it supports the answer is the model");
    // And where to see that gap in a recorded answer (final release review, 2026-10-11).
    expect(within(within(source).getByTestId("source-limit")).getByRole("link").getAttribute("href")).toBe("/break");
    expect(source.textContent).toContain("Found in EXHIBIT 10.102 (part 1), not in the section the model cited.");

    // Code found a conflict: observed against required, the sentence, the final status; the guidance it was checked against.
    const code = within(drawer).getByTestId("layer-code");
    expect(within(code).getByRole("heading", { name: "Guidance" })).toBeTruthy();
    expect(code.textContent).toContain("the contract provides 60 calendar days; the guidance requires at least 90 calendar days");
    expect(within(code).getByText("Needs review")).toBeTruthy();
    // Nothing the model wrote sits under "Code found a conflict": not its phrase for what it observed, not its suggestion.
    expect(code.textContent).not.toContain("60 days' written notice");
    expect(code.textContent).not.toContain("Suggested position");
    expect(code.textContent).toContain("Code found");

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

  it("does not head a status the model gave as if code compared anything", async () => {
    const hinted = {
      ...finding(null),
      status: "pass",
      statusSource: "model_hint",
      statusReason: null,
    } as unknown as FindingView;
    renderDrawer(hinted);
    const drawer = screen.getByLabelText("Evidence");
    const heads = within(drawer)
      .getAllByRole("heading", { level: 4 })
      .map((h) => h.textContent);
    expect(heads).toEqual(["Model proposed", "Source", "Code did not decide", "Human"]);
    const code = within(drawer).getByTestId("layer-code");
    expect(code.textContent).toContain("the model's hint stands as its view");
    expect(code.textContent).not.toContain("Code found");
    expect(within(code).getByText("Within guidance (model's view)")).toBeTruthy();
    expect(within(code).getByRole("heading", { name: "Guidance given" })).toBeTruthy();
    await screen.findByText("Its hint");
  });

  it("says a pass rests on a section the model was not shown, and does not show its source as settled", async () => {
    // Release integration, 2026-10-13: policy-v8 names the unseen section in the reason; the drawer showed it only as
    // the status sentence, with the source cell in the pass colour.
    const unseen = "the sentence points at §9, which was not handed to the model";
    const hinted = {
      ...finding(null),
      status: "pass",
      statusSource: "model_hint",
      statusReason: unseen,
      codeCompared: false,
      unseenReason: unseen,
    } as unknown as FindingView;
    renderDrawer(hinted);
    const drawer = screen.getByLabelText("Evidence");
    expect(within(drawer).getByTestId("unseen-fact").textContent).toContain(`Code found that ${unseen}. The answer may depend on it`);
    expect(drawer.textContent).toContain("they point at a section the model was not shown");
    expect(within(drawer).getByTestId("layer-code").textContent).not.toContain("Code found a conflict");
    await screen.findByText("Its hint");
  });

  it("heads a pass the model proposed and code confirmed as confirmed, not decided", async () => {
    const confirmed = {
      ...finding(null),
      status: "pass",
      statusSource: "confirmed_days",
      statusReason: "the contract provides 90 calendar days; the guidance requires at least 90 calendar days",
    } as unknown as FindingView;
    renderDrawer(confirmed);
    const drawer = screen.getByLabelText("Evidence");
    const heads = within(drawer)
      .getAllByRole("heading", { level: 4 })
      .map((h) => h.textContent);
    expect(heads).toEqual(["Model proposed", "Source", "Code confirmed", "Human"]);
    const code = within(drawer).getByTestId("layer-code");
    expect(code.textContent).toContain("Confirmed by code");
    expect(code.textContent).not.toContain("Code found");
    expect(within(code).getByText("Within guidance (confirmed by code)")).toBeTruthy();
    await screen.findByText("Its hint");
  });

  it("keeps the model's own sentence in the model's layer when the product does not repeat it", async () => {
    const notFound = {
      ...finding(null),
      status: "missing",
      statusSource: "model_hint",
      statusReason: null,
      evidenceKind: "coverage",
      conclusion: "The model did not find this in the sections it was given.",
      modelConclusion: "The contract does not provide for termination for convenience.",
      withheldConclusion: "The contract does not provide for termination for convenience.",
    } as unknown as FindingView;
    renderDrawer(notFound);
    const model = within(screen.getByLabelText("Evidence")).getByTestId("layer-model");
    expect(within(model).getByTestId("model-sentence").textContent).toContain("The contract does not provide for termination for convenience.");
    await screen.findByText("Its hint");
    cleanup();
    // Where the product shows the model's conclusion as the finding, it is not said twice.
    renderDrawer({ ...finding(null), modelConclusion: finding(null).conclusion, withheldConclusion: null } as unknown as FindingView);
    expect(within(screen.getByLabelText("Evidence")).queryByTestId("model-sentence")).toBeNull();
    await screen.findByText("Its hint");
    cleanup();
    // The drawer decides nothing itself: a not-found finding the API sends without a withheld sentence (here the
    // model's was only whitespace) shows none, as the card and the memo show none (review of d2672cc).
    renderDrawer({ ...notFound, modelConclusion: "   ", withheldConclusion: null } as unknown as FindingView);
    expect(within(screen.getByLabelText("Evidence")).queryByTestId("model-sentence")).toBeNull();
    await screen.findByText("Its hint");
  });

  it("records a decision from the drawer under a remembered name and hands the review back", async () => {
    window.localStorage.setItem("workbench.reviewer", "Pavan");
    const onReviewed = vi.fn();
    api.reviewFinding.mockResolvedValue({ review: CONFIRMED, latestReviewId: 8 } as unknown as Awaited<ReturnType<typeof reviewFinding>>);
    renderDrawer(finding(null), onReviewed);
    const human = within(screen.getByLabelText("Evidence")).getByTestId("layer-human");
    expect(human.textContent).toContain("No one has decided on this finding yet.");
    fireEvent.click(within(human).getByRole("button", { name: "Confirm" }));
    await vi.waitFor(() => expect(onReviewed).toHaveBeenCalledWith("afa60a7574984690", CONFIRMED, 8));
    // The decision names the review state the drawer showed: none yet.
    expect(api.reviewFinding).toHaveBeenCalledWith("afa60a7574984690", { verdict: "confirmed", reviewer: "Pavan", note: null, basedOn: 0 });
  });

  it("asks for a name before clearing a decision when none is remembered, then records the clear under it", async () => {
    // m7 audit, 2026-10-10: with no remembered name (cleared site data, another browser) "Clear the decision" did nothing.
    window.localStorage.removeItem("workbench.reviewer");
    const onReviewed = vi.fn();
    api.reviewFinding.mockResolvedValue({ review: null, latestReviewId: 8 } as Awaited<ReturnType<typeof reviewFinding>>);
    renderDrawer(finding(CONFIRMED), onReviewed);
    const human = within(screen.getByLabelText("Evidence")).getByTestId("layer-human");
    fireEvent.click(within(human).getByRole("button", { name: "Clear the decision" }));
    expect(api.reviewFinding).not.toHaveBeenCalled();
    fireEvent.change(screen.getByLabelText("Your name, recorded with the decision"), { target: { value: "R. Reviewer" } });
    fireEvent.click(screen.getByRole("button", { name: "Clear as R. Reviewer" }));
    await vi.waitFor(() => expect(onReviewed).toHaveBeenCalledWith("afa60a7574984690", null, 8));
    expect(api.reviewFinding).toHaveBeenCalledWith("afa60a7574984690", { verdict: "cleared", reviewer: "R. Reviewer", note: null, basedOn: 7 });
  });

  it("says a decision was refused when the finding was reviewed since, and asks for the current state", async () => {
    window.localStorage.setItem("workbench.reviewer", "Pavan");
    const onReviewed = vi.fn();
    const stale = Object.assign(new Error("This finding was dismissed by B. Reviewer after you opened it."), { name: "ApiError", status: 409 });
    api.reviewFinding.mockRejectedValue(stale);
    renderDrawer(finding(CONFIRMED), onReviewed);
    const human = within(screen.getByLabelText("Evidence")).getByTestId("layer-human");
    fireEvent.click(within(human).getByRole("button", { name: "Clear the decision" }));
    await vi.waitFor(() => expect(within(human).getByRole("alert").textContent).toContain("dismissed by B. Reviewer after you opened it"));
    expect(api.reviewFinding).toHaveBeenCalledWith("afa60a7574984690", { verdict: "cleared", reviewer: "Pavan", note: null, basedOn: 7 });
    expect(onReviewed).toHaveBeenCalledWith("afa60a7574984690", undefined);
  });

  it("control: a failure that is not a conflict is shown and does not ask for the state again", async () => {
    window.localStorage.setItem("workbench.reviewer", "Pavan");
    const onReviewed = vi.fn();
    api.reviewFinding.mockRejectedValue(new Error("The workbench API is not reachable."));
    renderDrawer(finding(null), onReviewed);
    const human = within(screen.getByLabelText("Evidence")).getByTestId("layer-human");
    fireEvent.click(within(human).getByRole("button", { name: "Dismiss" }));
    await vi.waitFor(() => expect(within(human).getByRole("alert").textContent).toContain("not reachable"));
    expect(onReviewed).not.toHaveBeenCalled();
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

describe("one drawer, another finding", () => {
  afterEach(cleanup);

  it("a decision form opened for one finding is not carried to the next one opened in the same drawer", () => {
    api.getRunExplanation.mockResolvedValue(EXPLANATION_E5A20E22);
    window.localStorage.removeItem("workbench.reviewer");
    const first = finding(null);
    const second = { ...finding(null), id: `${first.id}-other`, topic: "Another finding" } as FindingView;
    const props = {
      run: RUN,
      guidanceText: null,
      sectionsById: new Map([["s0", SECTION]]),
      onJump: vi.fn(),
      onClose: vi.fn(),
      onReviewed: vi.fn(),
      closeRef: null,
      reduceMotion: true,
    };
    const view = render(<EvidenceDrawer finding={first} {...props} />);
    const human = () => within(screen.getByLabelText("Evidence")).getByTestId("layer-human");
    fireEvent.click(within(human()).getByRole("button", { name: "Dismiss" }));
    expect(within(human()).getByLabelText("Your name, recorded with the decision")).toBeTruthy();
    // The reader opens the other finding (the palette's "Inspect evidence", or another card) without closing the drawer.
    view.rerender(<EvidenceDrawer finding={second} {...props} />);
    expect(within(human()).queryByLabelText("Your name, recorded with the decision")).toBeNull();
    expect(within(human()).getByRole("button", { name: "Dismiss" })).toBeTruthy();
  });

  it("on a phone, where the contract text is hidden, offers no button that would mark a passage in it", () => {
    // The 375 px review (2026-10-15): the sheet's source link and relation ends marked text in the hidden document pane.
    const replaces = {
      kind: "replaces",
      statement: { sectionId: "s0", label: "AMENDMENT NO. 1", start: 0, end: 30, text: "clause 4.1 is deleted and replaced" },
      target: "4.1",
      replaced: { sectionId: "s0", label: "EXHIBIT 10.102 (part 1)", start: 4136, end: 4284, text: QUOTE },
      replacement: null,
      scope: null,
      effective: null,
      parts: [],
    };
    const view = { ...finding(null), relations: [{ effect: "replaced", sentence: "code's whole sentence", relation: replaces }] } as unknown as FindingView;
    const buttons = (narrow: boolean): number => {
      Object.defineProperty(window, "matchMedia", {
        configurable: true,
        writable: true,
        value: (media: string) => ({ matches: narrow, media, addEventListener: vi.fn(), removeEventListener: vi.fn() }),
      });
      renderDrawer(view);
      const count = screen.getAllByRole("button").length;
      expect(screen.getByText(/Original clause 4\.1/)).toBeTruthy(); // the passage is still shown, as text
      cleanup();
      return count;
    };
    try {
      // On a wide screen: the source link and both ends of the relation open the document; on a phone none is offered.
      expect(buttons(false) - buttons(true)).toBe(3);
    } finally {
      delete (window as { matchMedia?: unknown }).matchMedia;
    }
  });

  it("on a phone, shows the stored text around a verified quote, only where its offsets fit that text", () => {
    const at = SECTION.text.indexOf(QUOTE);
    const base = finding(null);
    const located = { ...base, spans: [{ ...base.spans[0], start: at, end: at + QUOTE.length }] } as unknown as FindingView;
    const around = (view: FindingView, narrow: boolean) => {
      Object.defineProperty(window, "matchMedia", {
        configurable: true,
        writable: true,
        value: (media: string) => ({ matches: narrow, media, addEventListener: vi.fn(), removeEventListener: vi.fn() }),
      });
      renderDrawer(view);
      const summary = screen.queryByText("Text around this quote");
      const shown = summary ? (summary.closest("details")?.querySelector("strong")?.textContent ?? "") : null;
      const labelled = !!screen.queryByText(/as Verity read it, not an image of the page/);
      cleanup();
      return { shown, labelled };
    };
    try {
      // The text at the quote's offsets is what is emphasised, and it is called text Verity read, not the page.
      expect(around(located, true)).toEqual({ shown: QUOTE, labelled: true });
      // A wide screen has the document beside it; offsets outside the stored text and an unverified quote show nothing.
      expect(around(located, false).shown).toBeNull();
      expect(around(base, true).shown).toBeNull();
      expect(around({ ...located, spans: [{ ...located.spans[0], verified: false }] } as unknown as FindingView, true).shown).toBeNull();
    } finally {
      delete (window as { matchMedia?: unknown }).matchMedia;
    }
  });
});
