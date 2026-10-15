/**
 * Moment 5 in the revision panel: the prepared revision of the sample is a real file read like any other, and "ask the
 * same question of the revision" starts a real run on the revised document with the same question and guidance, then
 * sets the two recorded answers side by side, saying who set each status. Nothing is decided here.
 */

import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { createGuidance, createRun, followRun, getRunTrustDiff, recordSupersedes, uploadDocument } from "@/lib/api";
import type { FindingView, RunView, TrustDiffView } from "@/lib/types";

const api = vi.hoisted(() => ({
  uploadDocument: vi.fn<typeof uploadDocument>(),
  recordSupersedes: vi.fn<typeof recordSupersedes>(),
  getRunTrustDiff: vi.fn<typeof getRunTrustDiff>(),
  createGuidance: vi.fn<typeof createGuidance>(),
  createRun: vi.fn<typeof createRun>(),
  followRun: vi.fn<typeof followRun>(),
}));

vi.mock("@/lib/api", () => ({
  ...api,
  errorMessage: (error: unknown) => (error instanceof Error ? error.message : String(error)),
}));

import { RevisionCheck, SAMPLE_REVISION } from "./RevisionCheck";

const DIFF = {
  sections: { identical: 122, changed: ["§5.3(a) Termination"], removed: [], added: [] },
  sectionsTotal: 123,
  sectionsSearched: 1,
  sectionsReused: 122,
  counts: { unchanged: 0, revalidated: 0, stale: 1 },
  findings: [{ findingId: "f1", ordinal: 0, topic: "Cure period", before: "supported", after: "unsupported", verdict: "stale", why: [], obligations: [] }],
} as unknown as TrustDiffView;

function finding(over: Partial<FindingView>): FindingView {
  return {
    id: "f",
    topic: "Cure period",
    status: "pass",
    statusSource: "model_hint",
    statusReason: null,
    decidedBy: "model",
    concerns: [],
    flagged: false,
    conclusion: "A party has 30 days to cure.",
    spans: [
      {
        sectionId: "s",
        start: 0,
        end: 10,
        quote: "following 30 days notice",
        verified: true,
        method: "exact",
        citedSectionLabel: "sec_29",
        sectionLabel: "§5.3(a)",
      },
    ],
    ...over,
  } as FindingView;
}

const BEFORE = {
  id: "run-1",
  question: "How long to cure?",
  guidanceText: "At least 30 days to cure.",
  hasGuidance: true,
  findings: [finding({})],
} as unknown as RunView;
const AFTER = {
  id: "run-2",
  stage: "complete",
  hasGuidance: true,
  findings: [
    finding({
      id: "g",
      status: "needs_review",
      statusSource: "computed_days",
      decidedBy: "code",
      statusReason: "the contract provides 10 calendar days; the guidance requires at least 30 calendar days",
      conclusion: "A party has 10 days to cure.",
      spans: [
        {
          sectionId: "s",
          start: 0,
          end: 10,
          quote: "following 10 days notice",
          verified: true,
          method: "exact",
          citedSectionLabel: "sec_29",
          sectionLabel: "§5.3(a)",
        },
      ],
    }),
  ],
} as unknown as RunView;

describe("the revision panel, asked again", () => {
  beforeEach(() => {
    Object.values(api).forEach((mock) => mock.mockReset());
    // A fetched file as the component reads it: ok, and its bytes as a Blob (jsdom's Response cannot make one).
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => ({ ok: true, blob: async () => new Blob(["docx bytes"]) })),
    );
  });
  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  it("reads the prepared revision as a file, says what it changes, and asks the same question of it", async () => {
    api.uploadDocument.mockResolvedValue({ id: "doc-2" } as Awaited<ReturnType<typeof uploadDocument>>);
    api.recordSupersedes.mockResolvedValue({} as Awaited<ReturnType<typeof recordSupersedes>>);
    api.getRunTrustDiff.mockResolvedValue(DIFF);
    api.createGuidance.mockResolvedValue({ id: "g-1" } as Awaited<ReturnType<typeof createGuidance>>);
    api.createRun.mockResolvedValue(AFTER);
    render(<RevisionCheck runId="run-1" documentId="doc-1" run={BEFORE} prepared={SAMPLE_REVISION} />);

    expect(screen.getByText(/The prepared revision makes one change by Verity/)).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Use a prepared revision" }));
    await waitFor(() => expect(api.uploadDocument).toHaveBeenCalled());
    expect(api.uploadDocument.mock.calls[0][0].name).toBe(SAMPLE_REVISION.fileName);
    fireEvent.click(await screen.findByRole("button", { name: "Record as the next version" }));
    fireEvent.click(await screen.findByRole("button", { name: "Ask the same question of the revision" }));

    await screen.findByText("The same question, both versions");
    expect(api.createRun).toHaveBeenCalledWith({ documentId: "doc-2", guidanceId: "g-1", question: "How long to cure?" });
    const panel = screen.getByTestId("revision-check");
    expect(panel.textContent).toMatch(/Within guidance \(model's view\)\s*→\s*became\s*Needs review, set by code/);
    expect(panel.textContent).toContain("Code set this status: the contract provides 10 calendar days");
    expect(panel.textContent).toContain("§5.3(a) following 10 days notice");
    expect(panel.textContent).not.toContain("sec_29"); // the model's handle is never a citation
  });

  it("says which of the contract's own statements the revision changed, from the two runs' records", async () => {
    const ranking = (text: string, parts: string[]) => ({
      kind: "precedence",
      statement: { sectionId: "s2", label: "§2", start: 0, end: text.length, text },
      target: null,
      replaced: null,
      replacement: null,
      scope: null,
      effective: null,
      parts,
    });
    const before = {
      ...BEFORE,
      relations: [ranking("2.2 In a conflict: (a) Schedule 1; (b) the General Terms.", ["Schedule 1", "the General Terms"])],
    } as unknown as RunView;
    const after = {
      ...AFTER,
      relations: [ranking("2.2 In a conflict: (a) the General Terms; (b) Schedule 1.", ["the General Terms", "Schedule 1"])],
    } as unknown as RunView;
    api.uploadDocument.mockResolvedValue({ id: "doc-2" } as Awaited<ReturnType<typeof uploadDocument>>);
    api.recordSupersedes.mockResolvedValue({} as Awaited<ReturnType<typeof recordSupersedes>>);
    api.getRunTrustDiff.mockResolvedValue(DIFF);
    api.createGuidance.mockResolvedValue({ id: "g-1" } as Awaited<ReturnType<typeof createGuidance>>);
    api.createRun.mockResolvedValue(after);
    render(<RevisionCheck runId="run-1" documentId="doc-1" run={before} prepared={SAMPLE_REVISION} />);
    fireEvent.click(screen.getByRole("button", { name: "Use a prepared revision" }));
    fireEvent.click(await screen.findByRole("button", { name: "Record as the next version" }));
    fireEvent.click(await screen.findByRole("button", { name: "Ask the same question of the revision" }));
    const changed = await screen.findByTestId("statements-changed");
    expect(changed.textContent).toContain("This version: §2 ranks Schedule 1, the General Terms for a conflict.");
    expect(changed.textContent).toContain("The revision: §2 ranks the General Terms, Schedule 1 for a conflict.");
  });

  it("says nothing about statements when the two versions make the same ones", async () => {
    api.uploadDocument.mockResolvedValue({ id: "doc-2" } as Awaited<ReturnType<typeof uploadDocument>>);
    api.recordSupersedes.mockResolvedValue({} as Awaited<ReturnType<typeof recordSupersedes>>);
    api.getRunTrustDiff.mockResolvedValue(DIFF);
    api.createGuidance.mockResolvedValue({ id: "g-1" } as Awaited<ReturnType<typeof createGuidance>>);
    api.createRun.mockResolvedValue(AFTER);
    render(<RevisionCheck runId="run-1" documentId="doc-1" run={BEFORE} prepared={SAMPLE_REVISION} />);
    fireEvent.click(screen.getByRole("button", { name: "Use a prepared revision" }));
    fireEvent.click(await screen.findByRole("button", { name: "Record as the next version" }));
    fireEvent.click(await screen.findByRole("button", { name: "Ask the same question of the revision" }));
    await screen.findByText("The same question, both versions");
    expect(screen.queryByTestId("statements-changed")).toBeNull();
  });

  it("offers no prepared revision for a document of the reader's own", () => {
    render(<RevisionCheck runId="run-1" documentId="doc-1" run={BEFORE} />);
    expect(screen.queryByRole("button", { name: "Use a prepared revision" })).toBeNull();
  });
});
