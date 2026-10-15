/**
 * A finding the model reported as not found shows the product's sentence as the finding, and the model's own sentence
 * only collapsed and named as the model's (m10). The live smoke test of 2026-10-11 asked whether Birch could terminate
 * at once for an unpaid invoice: the model answered in substance, mostly right, and marked the point missing, and the
 * card showed only "not found" above the very clause that answers it. Whether there is such a sentence is the API's
 * call (Finding.withheld_conclusion), so the card and the memo cannot disagree; the card only renders it.
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
const SUMMARY = "The model also wrote a sentence · withheld";

function finding(over: Partial<FindingView>): FindingView {
  return {
    id: "f1",
    topic: "Immediate Termination for Nonpayment",
    status: "missing",
    statusSource: "model_hint",
    statusReason: null,
    conclusion: NOT_FOUND,
    modelConclusion: MODEL,
    withheldConclusion: MODEL,
    evidenceKind: "coverage",
    review: null,
    latestReviewId: 0,
    spans: [{ sectionId: "s3", verified: true, method: "exact", quote: QUOTE, start: 0, end: QUOTE.length, citedSectionLabel: "sec_3", matchCount: 1 }],
    relations: [], // the API always sends the list (runs.relations); empty when the contract's statements touch nothing
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
    const summary = screen.getByText(SUMMARY);
    const details = summary.closest("details") as HTMLDetailsElement;
    expect(details.open).toBe(false);
    expect(details.textContent).toContain(MODEL);
    expect(details.textContent).toContain("The model's words, not checked by code.");
    expect(details.textContent).toContain("Withheld from the finding because the model reported the point as not found in the sections it was given.");
    fireEvent.click(summary);
    expect(details.open).toBe(true);
  });

  it("says beside the passages that a pass rests on a section the model was not shown", () => {
    const unseen = "the sentence points at §9, which was not handed to the model";
    renderCard(finding({ status: "pass", statusSource: "model_hint", statusReason: unseen, codeCompared: false, unseenReason: unseen }));
    expect(screen.getByTestId("unseen-note").textContent).toContain(`Code found that ${unseen}. The answer may depend on it, and nothing checked that.`);
    expect(document.body.textContent).not.toMatch(/Code compared/);
  });

  it("control: a finding with nothing unseen carries no such note", () => {
    renderCard(finding({ status: "pass", statusSource: "model_hint", statusReason: null, codeCompared: false, unseenReason: null }));
    expect(screen.queryByTestId("unseen-note")).toBeNull();
  });

  it("shows no withheld sentence when the API sends none, whatever the status and the model's sentence", () => {
    // The card decides nothing: a different model sentence on a needs-review finding, a not-found finding whose model
    // sentence is only whitespace, and a pass all come from the API without a withheld sentence.
    for (const over of [
      { status: "needs_review", conclusion: "The fee is 5%.", modelConclusion: "The fee is 8%.", evidenceKind: "passage" },
      { status: "missing", modelConclusion: "   " },
      { status: "missing", modelConclusion: `${NOT_FOUND}\n` },
      { status: "pass", conclusion: MODEL, modelConclusion: MODEL, evidenceKind: "passage" },
    ] as Partial<FindingView>[]) {
      renderCard(finding({ ...over, withheldConclusion: null }));
      expect(screen.queryByText(SUMMARY)).toBeNull();
      cleanup();
    }
  });
});
