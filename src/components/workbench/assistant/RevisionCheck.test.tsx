/**
 * The revision check renders what the API says a revised document does to a run's findings, and decides nothing:
 * which findings are stale and why come from the API's answer, in the API's words.
 */

import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { getRunTrustDiff, recordSupersedes, uploadDocument } from "@/lib/api";
import type { TrustDiffView } from "@/lib/types";

const api = vi.hoisted(() => ({
  uploadDocument: vi.fn<typeof uploadDocument>(),
  recordSupersedes: vi.fn<typeof recordSupersedes>(),
  getRunTrustDiff: vi.fn<typeof getRunTrustDiff>(),
}));

vi.mock("@/lib/api", () => ({
  ...api,
  errorMessage: (error: unknown) => (error instanceof Error ? error.message : String(error)),
}));

import { RevisionCheck } from "./RevisionCheck";

const DIFF: TrustDiffView = {
  manifestId: "aaaaaaaaaaaaaaaa",
  runId: "run-1",
  fromDocumentId: "doc-1",
  toDocumentId: "doc-2",
  fromSnapshot: "s1",
  toSnapshot: "s2",
  sections: { identical: 2, changed: ["§2 Termination for Convenience"], removed: [], added: [] },
  sectionsTotal: 3,
  sectionsSearched: 1,
  sectionsReused: 2,
  counts: { unchanged: 1, revalidated: 0, stale: 1 },
  findings: [
    { findingId: "f2", ordinal: 1, topic: "Governing law", before: "supported", after: "supported", verdict: "unchanged", why: [], obligations: [] },
    {
      findingId: "f1",
      ordinal: 0,
      topic: "Termination for convenience",
      before: "supported",
      after: "unsupported",
      verdict: "stale",
      why: ["15 calendar days → 30 calendar days: the passage the finding quoted now states a different duration"],
      obligations: [],
    },
  ],
};

function choose(file: File) {
  fireEvent.change(screen.getByLabelText("Revised contract file"), { target: { files: [file] } });
}

describe("RevisionCheck", () => {
  beforeEach(() => {
    Object.values(api).forEach((mock) => mock.mockReset());
  });
  afterEach(cleanup);

  it("uploads the revision, records it as the next version, and shows what the API said", async () => {
    api.uploadDocument.mockResolvedValue({ id: "doc-2" } as Awaited<ReturnType<typeof uploadDocument>>);
    api.recordSupersedes.mockResolvedValue({} as Awaited<ReturnType<typeof recordSupersedes>>);
    api.getRunTrustDiff.mockResolvedValue(DIFF);
    render(<RevisionCheck runId="run-1" documentId="doc-1" />);
    choose(new File(["revised"], "agreement-v2.txt", { type: "text/plain" }));

    const panel = await screen.findByTestId("revision-check");
    await waitFor(() => expect(panel.textContent).toContain("1 finding is stale."));
    expect(api.recordSupersedes).toHaveBeenCalledWith("doc-2", "doc-1");
    expect(api.getRunTrustDiff).toHaveBeenCalledWith("run-1", "doc-2");
    expect(panel.textContent).toContain("0 were established again. 1 was not reached by the revision.");
    expect(panel.textContent).toContain("changed: §2 Termination for Convenience");
    expect(panel.textContent).toContain("1 of 3 sections searched again");

    const rows = within(panel)
      .getAllByRole("listitem")
      .filter((row) => row.hasAttribute("data-verdict"));
    expect(rows.map((row) => row.getAttribute("data-verdict"))).toEqual(["stale", "unchanged"]);
    expect(rows[0].textContent).toContain("15 calendar days → 30 calendar days");
    expect(rows[0].textContent).toContain("supported → unsupported");
    expect(rows[1].textContent).toContain("Its source evidence did not change.");
  });

  it("says so when the file is the document the run already read, and records nothing", async () => {
    api.uploadDocument.mockResolvedValue({ id: "doc-1" } as Awaited<ReturnType<typeof uploadDocument>>);
    render(<RevisionCheck runId="run-1" documentId="doc-1" />);
    choose(new File(["same"], "agreement.txt", { type: "text/plain" }));
    expect((await screen.findByRole("alert")).textContent).toContain("already read");
    expect(api.recordSupersedes).not.toHaveBeenCalled();
    expect(api.getRunTrustDiff).not.toHaveBeenCalled();
  });

  it("shows the API's own sentence when the check is refused", async () => {
    api.uploadDocument.mockResolvedValue({ id: "doc-2" } as Awaited<ReturnType<typeof uploadDocument>>);
    api.recordSupersedes.mockRejectedValue(new Error("This document already has a place in a line of versions."));
    render(<RevisionCheck runId="run-1" documentId="doc-1" />);
    choose(new File(["revised"], "agreement-v2.txt", { type: "text/plain" }));
    expect((await screen.findByRole("alert")).textContent).toContain("already has a place in a line of versions");
  });
});
