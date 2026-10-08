/**
 * The findings list is where most decisions are made. Each decision button names the finding it decides, so a screen
 * reader does not hear a column of identical "Confirm" buttons; and a decision made against a state that changed since
 * is refused by the API and the list reads the decision that stands.
 */

import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { listFindings, reviewFinding } from "@/lib/api";
import type { FindingRecord } from "@/lib/types";

const api = vi.hoisted(() => ({
  listFindings: vi.fn<typeof listFindings>(),
  reviewFinding: vi.fn<typeof reviewFinding>(),
}));

vi.mock("@/lib/api", () => ({
  listFindings: api.listFindings,
  reviewFinding: api.reviewFinding,
  errorMessage: (error: unknown) => (error instanceof Error ? error.message : String(error)),
  isConflict: (error: unknown) => error instanceof Error && (error as Error & { status?: number }).status === 409,
}));

import { FindingsView } from "./FindingsView";

function record(id: string, topic: string, review: FindingRecord["review"], latestReviewId: number): FindingRecord {
  return {
    id,
    runId: "run1",
    shared: false,
    documentId: "doc1",
    documentName: "agreement.pdf",
    question: "What are the termination rights?",
    topic,
    status: "needs_review",
    conclusion: "A conclusion.",
    verifiedSpans: 1,
    evidenceKind: "passage",
    review,
    latestReviewId,
    citations: ["§10"],
    hasGuidance: true,
    statusSource: "computed_days",
    createdAt: "2026-10-08T10:00:00+00:00",
  } as FindingRecord;
}

const CONFIRMED = { verdict: "confirmed", reviewer: "A. Reviewer", note: null, at: "2026-10-08T10:05:00+00:00" } as FindingRecord["review"];
const OPEN = record("f1", "Termination for convenience", null, 0);
const DECIDED = record("f2", "Governing law", CONFIRMED, 3);

beforeEach(() => {
  window.localStorage.setItem("workbench.reviewer", "B. Reviewer");
  api.listFindings.mockResolvedValue([OPEN, DECIDED]);
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("FindingsView", () => {
  it("names the finding each decision button decides", async () => {
    render(<FindingsView notice={null} onOpen={vi.fn()} />);
    expect(await screen.findByRole("button", { name: "Confirm: Termination for convenience" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Dismiss: Termination for convenience" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Undo: Governing law" })).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Confirm" })).toBeNull(); // no bare, ambiguous name
  });

  it("sends the review state the row showed, and on a refusal reads the decision that stands", async () => {
    const stale = Object.assign(new Error("This finding was confirmed by A. Reviewer after you opened it."), { status: 409 });
    api.reviewFinding.mockRejectedValue(stale);
    render(<FindingsView notice={null} onOpen={vi.fn()} />);
    fireEvent.click(await screen.findByRole("button", { name: "Dismiss: Termination for convenience" }));
    expect(await screen.findByText(/after you opened it/)).toBeTruthy();
    expect(api.reviewFinding).toHaveBeenCalledWith("f1", { verdict: "dismissed", reviewer: "B. Reviewer", note: null, basedOn: 0 });
    await vi.waitFor(() => expect(api.listFindings).toHaveBeenCalledTimes(2)); // the list is read again
  });

  it("control: a failure that is not a conflict is shown and the list is not read again", async () => {
    api.reviewFinding.mockRejectedValue(new Error("The workbench API is not reachable."));
    render(<FindingsView notice={null} onOpen={vi.fn()} />);
    fireEvent.click(await screen.findByRole("button", { name: "Undo: Governing law" }));
    expect(await screen.findByText(/not reachable/)).toBeTruthy();
    expect(api.reviewFinding).toHaveBeenCalledWith("f2", { verdict: "cleared", reviewer: "B. Reviewer", note: null, basedOn: 3 });
    expect(api.listFindings).toHaveBeenCalledTimes(1);
  });
});
