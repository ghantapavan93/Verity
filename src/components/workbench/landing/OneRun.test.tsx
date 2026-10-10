/**
 * The proof run's story says what that run's record says. It used to carry its own facts: a title ("The model missed a
 * 90 day floor"), fallback periods when the finding could not be read, and "Needs review." after whatever status the
 * record held (m7 audit, 2026-10-10).
 */

import { cleanup, render } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import type { FindingView, RunSummary } from "@/lib/types";

import { OneRun } from "./LandingStory";

afterEach(cleanup);
vi.stubGlobal(
  "IntersectionObserver",
  class {
    observe() {}
    unobserve() {}
    disconnect() {}
    takeRecords() {
      return [];
    }
  },
);

const proof = { id: "r1", question: "How much notice must the customer give?", hasGuidance: true } as unknown as RunSummary;
const lead = (status: string, review: FindingView["review"] = null) =>
  ({
    id: "f1",
    status,
    statusSource: status === "pass" ? "model_hint" : "computed_days",
    statusReason: "the contract provides 45 calendar days; the guidance requires at least 30 calendar days",
    observed: "45 days' notice",
    required: "at least 30 days",
    review,
  }) as unknown as FindingView;

it("tells nothing of its own when the run's finding could not be read", () => {
  const { container } = render(<OneRun proof={proof} lead={null} onOpen={vi.fn()} reduceMotion />);
  expect(container.textContent).not.toMatch(/90 day|60 days|Needs review/);
});

it("takes its title, periods and status from the record", () => {
  render(<OneRun proof={proof} lead={lead("pass")} onOpen={vi.fn()} reduceMotion />);
  const story = document.body;
  expect(story.textContent).toContain("45 days' notice");
  expect(story.textContent).toContain("at least 30 days");
  expect(story.textContent).not.toMatch(/missed a 90 day floor|Needs review\./);
});

it("says needs review only when the record does", () => {
  render(<OneRun proof={proof} lead={lead("needs_review")} onOpen={vi.fn()} reduceMotion />);
  expect(document.body.textContent).toMatch(/[Nn]eeds review/);
});
