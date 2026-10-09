/**
 * The paper's blocks are memoised (a keystroke elsewhere re-rendered every block of a long contract). What is held: a
 * render with unchanged props produces the same paper, a highlight still reaches exactly its block at its offsets, and
 * moving it leaves no mark behind.
 */

import { cleanup, render } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import type { DocumentView, SpanView } from "@/lib/types";
import { DocumentPane, type Highlight } from "./DocumentPane";

afterEach(cleanup);

const doc = {
  id: "d1",
  name: "a.txt",
  pages: null,
  sections: [
    { id: "s1", number: "1", heading: "Term", text: "The term is two years from the Effective Date." },
    { id: "s2", number: "2", heading: "Notice", text: "Either party may terminate on thirty days' notice." },
  ],
} as unknown as DocumentView;

const span = (sectionId: string, start: number, end: number): SpanView =>
  ({ sectionId, start, end, quote: "", verified: true, method: "exact" }) as unknown as SpanView;

function paper(highlight: Highlight | null) {
  return <DocumentPane doc={doc} isSample={false} lit={null} highlight={highlight} reduceMotion paneRef={null} />;
}

describe("DocumentPane with memoised blocks", () => {
  it("renders the same paper again, and moves a highlight to exactly its block and offsets", () => {
    const view = render(paper(null));
    const first = view.container.innerHTML;
    view.rerender(paper(null));
    expect(view.container.innerHTML).toBe(first);

    view.rerender(paper({ sectionId: "s2", span: span("s2", 30, 42) }));
    const marks = view.container.querySelectorAll("mark");
    expect(marks.length).toBe(1);
    expect(marks[0].textContent).toBe("thirty days'");

    view.rerender(paper({ sectionId: "s1", span: span("s1", 12, 21) }));
    const moved = view.container.querySelectorAll("mark");
    expect(moved.length).toBe(1);
    expect(moved[0].textContent).toBe("two years");

    view.rerender(paper(null));
    expect(view.container.querySelectorAll("mark").length).toBe(0);
    expect(view.container.innerHTML).toBe(first);
  });
});
