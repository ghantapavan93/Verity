/**
 * The record's counts are the store's own, so the page says them before any animation does. They used to start at 0
 * and count up only once scrolled into view: until then a screen reader, a copy or a print read "0 Contracts, 0
 * Questions" beside "560 sections read" for a visitor with three contracts and a named review (m7 audit, 2026-10-10).
 */

import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import type { CitationRecord, DocumentSummary } from "@/lib/types";

import { RecordPipeline } from "./LandingStory";

afterEach(cleanup);
// jsdom has no IntersectionObserver; this one never reports anything in view, as for content not yet scrolled to.
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

const documents = [
  { sections: 512, reviewedFindings: 1 },
  { sections: 14, reviewedFindings: 0 },
  { sections: 34, reviewedFindings: 0 },
] as unknown as DocumentSummary[];
const citations = { runs: 4, spans: 7, verifiedSpans: 6, withheldFindings: 1 } as unknown as CitationRecord;

it("states every count before the reader scrolls to it, with motion allowed", () => {
  render(<RecordPipeline citations={citations} documents={documents} reduceMotion={false} />);
  const node = (label: string) => screen.getByText(label, { selector: "*" }).closest("li") ?? screen.getByText(label).parentElement!;
  expect(node("Contracts").textContent).toContain("3");
  expect(node("Questions").textContent).toContain("4");
  expect(node("Model proposed").textContent).toContain("7");
  expect(node("Code found").textContent).toContain("6");
  expect(node("Code withheld").textContent).toContain("1");
  expect(node("A person decided").textContent).toContain("1");
  expect(screen.getByText("560 sections read")).toBeTruthy();
});
