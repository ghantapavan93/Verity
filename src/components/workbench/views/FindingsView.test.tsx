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

import { FindingsView, forAttention } from "./FindingsView";

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
    expect(screen.getByRole("button", { name: "Clear decision: Governing law" })).toBeTruthy();
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
    fireEvent.click(await screen.findByRole("button", { name: "Clear decision: Governing law" }));
    expect(await screen.findByText(/not reachable/)).toBeTruthy();
    expect(api.reviewFinding).toHaveBeenCalledWith("f2", { verdict: "cleared", reviewer: "B. Reviewer", note: null, basedOn: 3 });
    expect(api.listFindings).toHaveBeenCalledTimes(1);
  });
});

describe("FindingsView: what needs a person comes first", () => {
  it("lists an answer code has concerns about before a plain answer, and after a needs-review finding", () => {
    const plain = { ...record("p", "Payment terms", null, 0), status: "pass", flagged: false } as FindingRecord;
    const concerned = { ...record("c", "Liability cap", null, 0), status: "pass", flagged: true } as FindingRecord;
    const review = { ...record("r", "Renewal notice", null, 0), flagged: false } as FindingRecord;
    expect(forAttention([plain, concerned, review]).map((r) => r.id)).toEqual(["r", "c", "p"]);
  });

  it("control: a decided answer with concerns still waits behind every undecided one", () => {
    const plain = { ...record("p", "Payment terms", null, 0), status: "pass", flagged: false } as FindingRecord;
    const decided = { ...record("d", "Liability cap", CONFIRMED, 1), status: "pass", flagged: true } as FindingRecord;
    expect(forAttention([decided, plain]).map((r) => r.id)).toEqual(["p", "d"]);
  });

  it("lists a finding that needs review before an answer within the same contract, whatever order the API gave", async () => {
    const answered = { ...record("f3", "Payment terms", null, 0), status: "pass", statusSource: "model_hint" } as FindingRecord;
    const flagged = record("f4", "Renewal notice", null, 0);
    api.listFindings.mockResolvedValue([answered, flagged]);
    render(<FindingsView notice={null} onOpen={vi.fn()} />);
    const first = await screen.findByText("Renewal notice");
    expect(first.compareDocumentPosition(screen.getByText("Payment terms")) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it("lists every undecided finding before a decided one, a decided needs-review finding included", async () => {
    const decided = { ...record("f5", "Renewal notice", CONFIRMED, 1) } as FindingRecord;
    const answered = { ...record("f6", "Payment terms", null, 0), status: "pass", statusSource: "model_hint" } as FindingRecord;
    const flagged = record("f7", "Liability cap", null, 0);
    api.listFindings.mockResolvedValue([decided, answered, flagged]);
    render(<FindingsView notice={null} onOpen={vi.fn()} />);
    const at = (topic: string) => screen.findByText(topic);
    const [cap, payment, renewal] = await Promise.all([at("Liability cap"), at("Payment terms"), at("Renewal notice")]);
    expect(cap.compareDocumentPosition(payment) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(payment.compareDocumentPosition(renewal) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it("keeps a row where it is once it is decided here, under the reader's hand", async () => {
    const flagged = record("f8", "Liability cap", null, 0);
    const answered = { ...record("f9", "Payment terms", null, 0), status: "pass", statusSource: "model_hint" } as FindingRecord;
    api.listFindings.mockResolvedValue([answered, flagged]);
    api.reviewFinding.mockResolvedValue({ review: CONFIRMED, latestReviewId: 1 } as Awaited<ReturnType<typeof reviewFinding>>);
    render(<FindingsView notice={null} onOpen={vi.fn()} />);
    fireEvent.click(await screen.findByRole("button", { name: "Confirm: Liability cap" }));
    await screen.findByRole("button", { name: /Clear decision/ });
    const cap = screen.getByText("Liability cap");
    expect(cap.compareDocumentPosition(screen.getByText("Payment terms")) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it("keeps a row where it is when a refused decision reads the list again", async () => {
    const flagged = record("f10", "Liability cap", null, 0);
    const answered = { ...record("f11", "Payment terms", null, 0), status: "pass", statusSource: "model_hint" } as FindingRecord;
    api.listFindings.mockResolvedValueOnce([answered, flagged]).mockResolvedValueOnce([answered, { ...flagged, review: CONFIRMED, latestReviewId: 1 }]);
    api.reviewFinding.mockRejectedValue(Object.assign(new Error("decided since"), { status: 409 }));
    render(<FindingsView notice={null} onOpen={vi.fn()} />);
    fireEvent.click(await screen.findByRole("button", { name: "Dismiss: Liability cap" }));
    await screen.findByText(/decided since/);
    await screen.findByText(/Confirmed/);
    const cap = screen.getByText("Liability cap");
    expect(cap.compareDocumentPosition(screen.getByText("Payment terms")) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it("offers the amendment challenge when there is nothing to list", async () => {
    api.listFindings.mockResolvedValue([]);
    const start = vi.fn();
    render(<FindingsView notice={null} onOpen={vi.fn()} onStart={start} />);
    fireEvent.click(await screen.findByRole("button", { name: "Try the amendment challenge" }));
    expect(start).toHaveBeenCalledOnce();
  });
});
