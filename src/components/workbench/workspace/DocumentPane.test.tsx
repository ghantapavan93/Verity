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
  return <DocumentPane doc={doc} sample={null} lit={null} highlight={highlight} reduceMotion paneRef={null} />;
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

/**
 * The paper revealed the text before a highlight, the highlight and the text after it each on its own, so a selector at a
 * highlight's edge had no neighbour there and acted unmarked: "9\ufe0f0" read as 90 with the 9 highlighted (stress
 * test, 2026-10-30). The whole section is read for what is invisible, then split; and the file's own words (its name,
 * a heading) are shown through the same primitive as its text.
 */
describe("DocumentPane, what is invisible in the stored text", () => {
  const stored = {
    id: "d2",
    name: "lease\u202etxt.exe",
    pages: null,
    sections: [{ id: "s1", number: "1", heading: "Term\u202e of lease", text: "Notice of 9\ufe0f0 days." }],
  } as unknown as DocumentView;

  it("marks a selector at the edge of a highlight as it marks it in the unbroken text", () => {
    const at = Array.from("Notice of ").length;
    for (const [start, end] of [
      [at, at + 1], // the highlight ends on the 9: the selector opens the text after it
      [at + 1, at + 3], // the highlight starts on the selector
      [0, at + 1],
    ]) {
      const view = render(
        <DocumentPane doc={stored} sample={null} lit={null} highlight={{ sectionId: "s1", span: span("s1", start, end) }} reduceMotion paneRef={null} />,
      );
      const body = view.container.querySelector("[data-section='s1'] p")!;
      expect(body.textContent, `${start}-${end}`).not.toContain("\ufe0f");
      expect(body.textContent).toContain("U+FE0F");
      cleanup();
    }
  });

  it("names an invisible character in the file's name and in a heading", () => {
    const view = render(<DocumentPane doc={stored} sample={null} lit={null} highlight={null} reduceMotion paneRef={null} />);
    const text = view.container.textContent ?? "";
    expect(text).not.toContain("\u202e");
    expect(text).toContain("leaseU+202Etxt.exe");
    expect(text).toContain("TermU+202E of lease");
  });
});
