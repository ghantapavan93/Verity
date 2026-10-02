/**
 * A finding opened by its address must land on the clause, not on the top of the section the clause is in. The
 * scroll is measured from the mark, and the mark exists only once the highlight has rendered; so the scroll is
 * decided in the same commit that renders it. The case is the Phase 1 run's quote, deep in a long first section.
 */

import { cleanup, render } from "@testing-library/react";
import { useRef } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { DocumentView, SpanView } from "@/lib/types";
import { DocumentPane, type Highlight } from "../workspace/DocumentPane";
import { useHighlightScroll } from "./useHighlightScroll";

const BEFORE = "RESELLER AGREEMENT. ".repeat(40);
const QUOTE =
  "4.1 TERMINATION WITHOUT CAUSE. Either party may terminate this Agreement without cause upon sixty (60) days prior written notice to the other party.";
const DOC = {
  id: "doc1",
  coverage: null,
  name: "MTI-Reseller-Agreement.docx",
  pages: 1,
  sha256: null,
  sections: [
    { id: "s0", number: "", heading: "EXHIBIT 10.102 (part 1)", text: `${BEFORE}${QUOTE} 4.2 TERMINATION FOR BREACH.` },
    { id: "s1", number: "", heading: "EXHIBIT 10.102 (part 2)", text: "McDATA Corporation Standard Terms." },
  ],
  createdAt: "2026-09-28T00:00:00+00:00",
  reused: false,
} as unknown as DocumentView;
const SPAN = {
  sectionId: "s0",
  verified: true,
  method: "relocated:exact",
  quote: QUOTE,
  start: BEFORE.length,
  end: BEFORE.length + QUOTE.length,
} as unknown as SpanView;

/** Where layout would put things: the clause 2,876px down the pane, the second section's top at 5,400px. */
const MARK_TOP = 2876;
const SECTION_TOP = 5400;

function Harness({ highlight, reduceMotion = false }: { highlight: Highlight | null; reduceMotion?: boolean }) {
  const paneRef = useRef<HTMLDivElement>(null);
  useHighlightScroll(paneRef, highlight, reduceMotion);
  return <DocumentPane doc={DOC} isSample={false} lit={null} highlight={highlight} reduceMotion={reduceMotion} paneRef={paneRef} />;
}

/** A jump is a new highlight object, as the workbench makes one for every jump. */
const toClause = (): Highlight => ({ sectionId: "s0", span: SPAN });

/** Each scroll, with whether the mark was in the document at the moment it was decided. */
const scrolls: { top: number; behavior: string; markPresent: boolean }[] = [];

beforeEach(() => {
  scrolls.length = 0;
  HTMLElement.prototype.scrollTo = function scrollTo(options?: ScrollToOptions | number) {
    const { top = 0, behavior = "auto" } = typeof options === "object" ? options : {};
    scrolls.push({ top, behavior, markPresent: document.querySelector("mark") !== null });
  } as typeof HTMLElement.prototype.scrollTo;
  vi.spyOn(HTMLElement.prototype, "getBoundingClientRect").mockImplementation(function rect(this: HTMLElement) {
    return { top: this.tagName === "MARK" ? MARK_TOP : 0 } as DOMRect;
  });
  vi.spyOn(HTMLElement.prototype, "offsetTop", "get").mockImplementation(function offsetTop(this: HTMLElement) {
    return this.dataset.section === "s1" ? SECTION_TOP : 0;
  });
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("the document scrolls to what is highlighted", () => {
  it("lands on the clause, measured from the mark in the commit that renders it", () => {
    const { rerender } = render(<Harness highlight={null} />);
    expect(scrolls).toEqual([]);
    rerender(<Harness highlight={toClause()} />);
    expect(document.querySelector("mark")?.textContent).toBe(QUOTE);
    expect(scrolls).toEqual([{ top: MARK_TOP - 72, behavior: "smooth", markPresent: true }]);
  });

  it("lands on the clause when the document first appears with the highlight already set", () => {
    render(<Harness highlight={toClause()} />);
    expect(scrolls).toEqual([{ top: MARK_TOP - 72, behavior: "smooth", markPresent: true }]);
  });

  it("goes to the section's top when there is no passage to mark", () => {
    render(<Harness highlight={{ sectionId: "s1", span: null }} />);
    expect(scrolls).toEqual([{ top: SECTION_TOP - 72, behavior: "smooth", markPresent: false }]);
  });

  it("scrolls back when the passage already marked is jumped to again", () => {
    const { rerender } = render(<Harness highlight={toClause()} />);
    rerender(<Harness highlight={toClause()} />);
    expect(scrolls).toHaveLength(2);
    expect(scrolls[1]).toEqual(scrolls[0]);
  });

  it("does not move the reader when only the motion preference changes, and honours it on the next jump", () => {
    const highlight = toClause();
    const { rerender } = render(<Harness highlight={highlight} />);
    rerender(<Harness highlight={highlight} reduceMotion />);
    expect(scrolls).toHaveLength(1);
    rerender(<Harness highlight={toClause()} reduceMotion />);
    expect(scrolls[1].behavior).toBe("auto");
  });

  it("does nothing for a section that is not in the document, or when the highlight is cleared", () => {
    const { rerender } = render(<Harness highlight={{ sectionId: "gone", span: null }} />);
    rerender(<Harness highlight={null} />);
    expect(scrolls).toEqual([]);
  });
});
