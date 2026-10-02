"use client";

import { type RefObject, useLayoutEffect } from "react";
import type { Highlight } from "../workspace/DocumentPane";

/** Room left above the passage, so it is read with a line of what comes before it. */
const LEAD_PX = 72;

/**
 * Brings the highlighted passage into view in the document pane.
 *
 * The scroll goes to the passage, not the section: a quote deep in a long section (a 6,000-character part of a
 * contract read without headings) would otherwise land below the fold. The mark exists only once the highlight
 * has rendered, so the measurement runs in the layout effect of that same commit. Measuring a frame after asking
 * for the highlight raced the render: on a cold load the frame could come first, no mark was found, and the
 * reader was left at the section's top with the clause off screen. Without a span, the section's top.
 */
export function useHighlightScroll(paneRef: RefObject<HTMLElement | null>, highlight: Highlight | null, reduceMotion: boolean) {
  useLayoutEffect(() => {
    if (!highlight) return;
    const pane = paneRef.current;
    const target = pane?.querySelector<HTMLElement>(`[data-section="${highlight.sectionId}"]`);
    if (!pane || !target) return;
    const mark = highlight.span ? target.querySelector<HTMLElement>("mark") : null;
    const anchorTop = mark ? mark.getBoundingClientRect().top - pane.getBoundingClientRect().top + pane.scrollTop : target.offsetTop;
    pane.scrollTo({ top: Math.max(0, anchorTop - LEAD_PX), behavior: reduceMotion ? "auto" : "smooth" });
    // A new highlight is a new jump. A change of motion preference alone must not scroll the reader again.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [paneRef, highlight]);
}
