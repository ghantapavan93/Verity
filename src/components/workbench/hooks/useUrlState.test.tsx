/**
 * The URL is the reload contract: `document`, `run` and `view` are restored once on mount and written back whenever
 * they change, so a finished run can be sent as a link. It is also the Back button's contract: a move is a history
 * entry, and popstate restores the screen the address names.
 */

import { renderHook } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { DocumentView, RunView } from "@/lib/types";
import type { Stage, View } from "../shell/constants";
import { useUrlState } from "./useUrlState";

const doc: DocumentView = {
  id: "doc1",
  coverage: null,
  name: "agreement.docx",
  pages: 9,
  sha256: null,
  sections: [],
  createdAt: "2026-09-28T00:00:00+00:00",
  reused: false,
};
const running: RunView = {
  id: "run1",
  question: "q",
  stage: "checking",
  findings: [],
  withheld: [],
  model: "qwen3:8b",
  promptVersion: "answer-v2",
  promptHash: "abc",
  latencyMs: null,
  note: null,
  error: null,
  reason: null,
  reused: false,
  shared: false,
  hasGuidance: false,
  reviewHead: "",
  guidanceText: null,
};
const finished: RunView = { ...running, stage: "complete" };

function handlers() {
  return {
    openRun: vi.fn(async () => {}),
    openDocument: vi.fn(async () => {}),
    navigate: vi.fn(),
    goHome: vi.fn(),
  };
}

function props(overrides: { view?: View; doc?: DocumentView | null; stage?: Stage; run?: RunView | null; findingId?: string | null } = {}) {
  return {
    view: "assistant" as View,
    doc: null as DocumentView | null,
    stage: "empty" as Stage,
    run: null as RunView | null,
    findingId: null as string | null,
    ...handlers(),
    ...overrides,
  };
}

function setUrl(search: string) {
  window.history.replaceState(null, "", `/${search}`);
}

describe("useUrlState", () => {
  it("restores a run link once, with the finding a memo linked to, in the background when a view is requested too", () => {
    setUrl("?run=run1&finding=f9&view=findings");
    const initial = props();
    const { rerender } = renderHook((p) => useUrlState(p), { initialProps: initial });

    expect(initial.openRun).toHaveBeenCalledWith("run1", "f9", false);
    expect(initial.openDocument).not.toHaveBeenCalled();
    expect(initial.navigate).toHaveBeenCalledWith("findings");

    rerender({ ...initial, view: "findings" });
    expect(initial.openRun).toHaveBeenCalledTimes(1);
    expect(initial.navigate).toHaveBeenCalledTimes(1);
  });

  it("restores a document link and shows it when no view is requested", () => {
    setUrl("?document=doc1");
    const initial = props();
    renderHook((p) => useUrlState(p), { initialProps: initial });

    expect(initial.openDocument).toHaveBeenCalledWith("doc1", true);
    expect(initial.openRun).not.toHaveBeenCalled();
    expect(initial.navigate).not.toHaveBeenCalled();
  });

  it("ignores a view it does not have", () => {
    setUrl("?view=settings");
    const initial = props();
    renderHook((p) => useUrlState(p), { initialProps: initial });
    expect(initial.navigate).not.toHaveBeenCalled();
    expect(window.location.search).toBe("");
  });

  it("writes the open document and the run at once, then the view; and clears them when the workspace closes", () => {
    setUrl("");
    const initial = props({ doc, stage: "workspace", run: running });
    const { rerender } = renderHook((p) => useUrlState(p), { initialProps: initial });
    expect(window.location.search).toBe("?document=doc1&run=run1"); // the run in flight is already in the URL

    rerender({ ...initial, run: finished });
    expect(window.location.search).toBe("?document=doc1&run=run1");

    rerender({ ...initial, run: finished, view: "runs" });
    expect(window.location.search).toBe("?view=runs&document=doc1&run=run1");

    rerender({ ...initial, run: finished, view: "runs", stage: "empty" });
    expect(window.location.search).toBe("?view=runs");
  });

  it("writes the finding whose evidence is open, and only on the review surface", () => {
    setUrl("");
    const initial = props({ doc, stage: "workspace", run: finished, findingId: "f9" });
    const { rerender } = renderHook((p) => useUrlState(p), { initialProps: initial });
    expect(window.location.search).toBe("?document=doc1&run=run1&finding=f9");
    rerender({ ...initial, view: "findings" });
    expect(window.location.search).toBe("?view=findings&document=doc1&run=run1");
  });

  it("writes a move as a history entry, so Back has somewhere to go; the states one click passes through are one entry", () => {
    vi.useFakeTimers();
    try {
      setUrl("");
      const before = window.history.length;
      const initial = props();
      const { rerender } = renderHook((p) => useUrlState(p), { initialProps: initial });
      vi.advanceTimersByTime(1000); // the first render's corrections are over
      rerender({ ...initial, view: "runs" });
      expect(window.location.search).toBe("?view=runs");
      expect(window.history.length).toBe(before + 1);
      rerender({ ...initial, view: "runs", doc, stage: "workspace" }); // the same click, a moment later
      expect(window.location.search).toBe("?view=runs&document=doc1");
      expect(window.history.length).toBe(before + 1);
      vi.advanceTimersByTime(1000);
      rerender({ ...initial, view: "findings", doc, stage: "workspace" }); // a new move
      expect(window.history.length).toBe(before + 2);
    } finally {
      vi.useRealTimers();
    }
  });

  it("restores the screen the address names when the browser goes back", () => {
    setUrl("");
    const initial = props();
    renderHook((p) => useUrlState(p), { initialProps: initial });
    setUrl("?document=doc1&run=run1");
    window.dispatchEvent(new PopStateEvent("popstate"));
    expect(initial.openRun).toHaveBeenCalledWith("run1", null, true);
    setUrl("?view=findings");
    window.dispatchEvent(new PopStateEvent("popstate"));
    expect(initial.navigate).toHaveBeenCalledWith("findings");
    setUrl("");
    window.dispatchEvent(new PopStateEvent("popstate"));
    expect(initial.goHome).toHaveBeenCalledTimes(1);
  });

  it("leaves the address alone while a restore is on its way", () => {
    setUrl("?document=doc1&run=run1");
    const initial = props();
    const { rerender } = renderHook((p) => useUrlState(p), { initialProps: initial });
    rerender({ ...initial, doc, stage: "workspace" }); // the document has arrived, the run has not
    expect(window.location.search).toBe("?document=doc1&run=run1");
    rerender({ ...initial, doc, stage: "workspace", run: running });
    expect(window.location.search).toBe("?document=doc1&run=run1");
  });

  it("corrects an address that names a run under another document's id, once, in place", () => {
    // Adversarial review, 2026-10-08: ?document=A&run=<a run of B> showed B and its answer but kept document=A.
    setUrl("?document=docOther&run=run1");
    const before = window.history.length;
    const initial = props();
    const { rerender } = renderHook((p) => useUrlState(p), { initialProps: initial });
    expect(initial.openRun).toHaveBeenCalledWith("run1", null, true);
    rerender({ ...initial, doc, stage: "workspace", run: finished }); // the run arrives with its own document
    expect(window.location.search).toBe("?document=doc1&run=run1");
    expect(window.history.length).toBe(before); // replaced, not pushed
    rerender({ ...initial, doc, stage: "workspace", run: { ...finished } });
    rerender({ ...initial, doc, stage: "workspace", run: { ...finished } });
    expect(window.location.search).toBe("?document=doc1&run=run1");
    expect(window.history.length).toBe(before); // no loop, no further entries
    expect(initial.openRun).toHaveBeenCalledTimes(1);
  });

  it("control: an address whose run does not arrive is left as it was", () => {
    setUrl("?document=docOther&run=runMissing");
    const initial = props();
    const { rerender } = renderHook((p) => useUrlState(p), { initialProps: initial });
    rerender({ ...initial }); // the run failed to load: nothing is shown
    rerender({ ...initial, doc, stage: "workspace" }); // a document alone is not the run the address named
    expect(window.location.search).toBe("?document=docOther&run=runMissing");
  });
});
