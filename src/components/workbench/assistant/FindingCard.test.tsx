/**
 * A finding the model reported as not found shows the product's sentence as the finding, and the model's own sentence
 * only collapsed and named as the model's (m10). The live smoke test of 2026-10-11 asked whether Birch could terminate
 * at once for an unpaid invoice: the model answered in substance, mostly right, and marked the point missing, and the
 * card showed only "not found" above the very clause that answers it.
 */

import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { FindingView, SectionView } from "@/lib/types";

import { FindingCard } from "./FindingCard";

afterEach(cleanup);

const NOT_FOUND = "The model did not find this in the sections it was given.";
const MODEL =
  "Birch Systems cannot immediately terminate if Alder Labs hasn't paid an invoice. Provider must first give written notice of nonpayment, and if Alder Labs does not pay within 10 days, Birch Systems may then terminate.";
const QUOTE = "If Customer fails to pay an undisputed invoice when due, Provider may give Customer written notice of the nonpayment.";

function finding(over: Partial<FindingView>): FindingView {
  return {
    id: "f1",
    topic: "Immediate Termination for Nonpayment",
    status: "missing",
    statusSource: "model_hint",
    statusReason: null,
    conclusion: NOT_FOUND,
    modelConclusion: MODEL,
    evidenceKind: "coverage",
    review: null,
    latestReviewId: 0,
    spans: [{ sectionId: "s3", verified: true, method: "exact", quote: QUOTE, start: 0, end: QUOTE.length, citedSectionLabel: "sec_3", matchCount: 1 }],
    ...over,
  } as unknown as FindingView;
}

const sections = new Map<string, SectionView>([
  ["s3", { id: "s3", ordinal: 3, number: "3", heading: "Term and Termination", text: QUOTE } as unknown as SectionView],
]);

function renderCard(f: FindingView) {
  return render(<FindingCard finding={f} hasGuidance={false} sectionsById={sections} onJump={vi.fn()} onEvidence={vi.fn()} onFollowUp={vi.fn()} />);
}

describe("a finding the model reported as not found", () => {
  it("states the product's sentence as the finding and keeps the model's collapsed, named as the model's", () => {
    renderCard(finding({}));
    expect(screen.getByText(NOT_FOUND)).toBeTruthy();
    const summary = screen.getByText("The model also wrote a sentence · withheld");
    const details = summary.closest("details") as HTMLDetailsElement;
    expect(details.open).toBe(false);
    fireEvent.click(summary);
    expect(details.textContent).toContain(MODEL);
    expect(details.textContent).toContain("The model's words, not checked by code.");
    expect(details.textContent).toContain("reported the point as not found in the sections it was given");
  });

  it("shows no withheld sentence when the model's sentence is the finding's", () => {
    renderCard(finding({ status: "pass", conclusion: MODEL, modelConclusion: MODEL, evidenceKind: "passage" } as Partial<FindingView>));
    expect(screen.queryByText("The model also wrote a sentence · withheld")).toBeNull();
    expect(screen.getByText(MODEL)).toBeTruthy();
  });

  it("shows nothing extra for a not-found finding whose model sentence was the product's already", () => {
    renderCard(finding({ modelConclusion: NOT_FOUND }));
    expect(screen.queryByText("The model also wrote a sentence · withheld")).toBeNull();
  });
});
