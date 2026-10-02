/**
 * "Why this answer?" renders what the API says happened and decides nothing. The case is the Phase 1 run
 * (docs/DEMO-PROOF.md): a never-seen contract, the model's hint "pass", a quote cited to one section and
 * found in another, and a status computed by code. Every row of that record must be readable on one screen.
 */

import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { getRunExplanation } from "@/lib/api";

const api = vi.hoisted(() => ({ getRunExplanation: vi.fn<typeof getRunExplanation>() }));

vi.mock("@/lib/api", () => ({
  getRunExplanation: api.getRunExplanation,
  errorMessage: (error: unknown) => (error instanceof Error ? error.message : String(error)),
}));

import { EXPLANATION_E5A20E22 } from "./__fixtures__/explanation-e5a20e2283e8416e";
import { WhyThisAnswer } from "./WhyThisAnswer";

describe("WhyThisAnswer", () => {
  beforeEach(() => {
    api.getRunExplanation.mockReset();
  });
  afterEach(cleanup);

  it("shows the Phase 1 run layer by layer, from the record", async () => {
    api.getRunExplanation.mockResolvedValue(EXPLANATION_E5A20E22);
    render(<WhyThisAnswer runId="e5a20e2283e8416e" findingId="afa60a7574984690" />);
    const panel = await screen.findByTestId("why-this-answer");
    expect(api.getRunExplanation).toHaveBeenCalledWith("e5a20e2283e8416e");
    const text = panel.textContent ?? "";

    // Reading: reader v4, persisted coverage, approximate structure.
    expect(text).toContain("MTI-Reseller-Agreement.docx");
    expect(within(panel).getByText("v4")).toBeTruthy();
    expect(text).toContain("6 sections · little structure was found, so sections are approximate");
    expect(text).toContain("every part of the file with content was read (persisted, reader v4)");

    // Retrieval: six candidates, ranked; five truncated, one whole; the characters the model never saw.
    const rows = within(panel).getAllByRole("row").slice(1);
    expect(rows).toHaveLength(6);
    expect(rows.map((r) => r.textContent?.slice(0, 1))).toEqual(["1", "2", "3", "4", "5", "6"]);
    expect(rows.filter((r) => /the rest was cut/.test(r.textContent ?? ""))).toHaveLength(5);
    expect(rows.filter((r) => /^6.*all 3,?329 characters/.test(r.textContent ?? ""))).toHaveLength(1);
    expect(text).toContain("4,375 characters across the selected sections were outside this run's model-visible context.");

    // The exact input, rebuilt and matching.
    expect(text).toContain("rebuilt from the record; it hashes to what the checking stage recorded (f5991f589759)");
    expect(text).toContain("answer-v2 · 9dbeb12a871e");

    // ModelProposal: the model's words and its hint, not the finding's status.
    expect(text).toContain("ModelProposal");
    expect(text).toContain("Hintpass");
    expect(text).toContain("60 days' written notice (the model's words)");
    expect(text).toContain("at least 90 days (the model's words)");
    expect(text).toContain("cited sec_4: 4.1 TERMINATION WITHOUT CAUSE.");

    // SourceMatch: cited sec_4, located in sec_0, exact, once, at 4136–4284, inside the slice the model saw.
    const match = within(panel).getByTestId("source-match");
    expect(match.textContent).toContain("Model citedsec_4");
    expect(match.textContent).toContain("Located insec_0 · EXHIBIT 10.102 (part 1) (not where the model said)");
    expect(match.textContent).toContain("Matchrelocated:exact");
    expect(match.textContent).toContain("Occurrences1");
    expect(match.textContent).toContain("Offsets4136 to 4284");
    expect(match.textContent).toContain("Inside model-visible contextyes");

    // Recorded PolicyEvaluation: needs review, computed by code, with the sentence that says why.
    const policy = within(panel).getByTestId("policy-evaluation");
    expect(policy.textContent).toContain("Final statusNeeds review");
    expect(policy.textContent).toContain("Sourcecomputed_days");
    expect(policy.textContent).toContain("Decided by codethe contract provides 60 calendar days; the guidance requires at least 90 calendar days");

    // Reproduce: the identities a stranger needs, and that the input matches.
    expect(text).toContain("Rune5a20e2283e8416e");
    expect(text).toContain("sha256 d510d1d71a7b · reader v4");
    expect(text).toContain("f5991f589759 · rebuilt input matches");
    expect(text).toContain("Evidence packavailable");
    expect(text).not.toMatch(/verified truth|deterministic model|reasoning/i);
  });

  it("says when the model's proposal cannot be reconstructed, and shows a failed reconstruction rather than hiding it", async () => {
    api.getRunExplanation.mockResolvedValue({
      ...EXPLANATION_E5A20E22,
      proposals: [],
      proposalsProblem: "Model proposal not reconstructable for this run.",
      reconstruction: {
        ...EXPLANATION_E5A20E22.reconstruction,
        reconstructable: false,
        problem: "prompt file answer-v2.md was rewritten since the run: abc now, def then",
        charactersOutsideContext: null,
      },
      retrieval: EXPLANATION_E5A20E22.retrieval.map((c) => ({ ...c, truncated: null, sliceStart: null, sliceEnd: null })),
      findings: EXPLANATION_E5A20E22.findings.map((f) => ({
        ...f,
        sourceMatches: f.sourceMatches.map((m) => ({ ...m, insideModelVisibleContext: null })),
      })),
    });
    render(<WhyThisAnswer runId="e5a20e2283e8416e" />);
    const panel = await screen.findByTestId("why-this-answer");
    const text = panel.textContent ?? "";
    expect(text).toContain("Model proposal not reconstructable for this run.");
    expect(text).toContain("could not be rebuilt: prompt file answer-v2.md was rewritten since the run");
    expect(text).toContain("Inside model-visible contextnot determined");
    expect(text).not.toContain("outside this run's model-visible context");
    expect(
      within(panel)
        .getAllByRole("row")
        .slice(1)
        .every((r) => /not determined/.test(r.textContent ?? "")),
    ).toBe(true);
    // The recorded status does not depend on any of that.
    expect(within(panel).getByTestId("policy-evaluation").textContent).toContain("Sourcecomputed_days");
  });

  it("reports an unreadable explanation as a sentence", async () => {
    api.getRunExplanation.mockRejectedValue(new Error("The workbench API at http://127.0.0.1:8000 is not reachable."));
    render(<WhyThisAnswer runId="e5a20e2283e8416e" />);
    expect(await screen.findByText(/The explanation could not be read: The workbench API/)).toBeTruthy();
  });
});
