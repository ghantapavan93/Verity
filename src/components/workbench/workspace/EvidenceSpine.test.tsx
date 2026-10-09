/**
 * Evidence styling belongs only to passages a finding relies on. A provision the model read for a point it reports as
 * not found is marked as read, outlined, and said to be not relied on; the passage a finding stands on is evidence.
 */

import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { DocumentView, FindingView } from "@/lib/types";
import { EvidenceSpine } from "./EvidenceSpine";

afterEach(cleanup);

const doc = {
  id: "d1",
  name: "a.txt",
  sections: [
    { id: "s1", number: "1", heading: "Term", text: "The term is two years from the Effective Date." },
    { id: "s2", number: "2", heading: "Notice", text: "Either party may terminate on thirty days' notice." },
  ],
} as unknown as DocumentView;

function finding(id: string, kind: "passage" | "coverage", sectionId: string): FindingView {
  return {
    id,
    topic: kind === "coverage" ? "Most favoured nation" : "Termination",
    status: kind === "coverage" ? "missing" : "pass",
    evidenceKind: kind,
    spans: [{ sectionId, start: 0, end: 10, quote: "x", verified: true, method: "exact" }],
  } as unknown as FindingView;
}

describe("EvidenceSpine", () => {
  it("marks a not-found finding's provisions as read, not relied on, and evidence as evidence", () => {
    render(<EvidenceSpine doc={doc} findings={[finding("f1", "passage", "s2"), finding("f2", "coverage", "s1")]} highlight={null} onJump={vi.fn()} />);
    const read = screen.getByRole("button", { name: /Most favoured nation.*read, not relied on/ });
    const evidence = screen.getByRole("button", { name: /^Termination, §2 · Notice: show in the document$/ });
    expect(read.getAttribute("data-read")).toBe("true");
    expect(evidence.getAttribute("data-read")).toBeNull();
    expect(read.className).not.toBe(evidence.className);
  });
});
