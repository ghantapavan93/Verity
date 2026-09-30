/**
 * The URL is the reload contract: `document`, `run` and `view` are restored once on mount and
 * written back whenever they change, so a finished run can be sent as a link.
 */

import { renderHook } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { DocumentView, RunView } from "@/lib/types";
import type { Stage, View } from "../shell/constants";
import { useUrlState } from "./useUrlState";

const doc: DocumentView = { id: "doc1", name: "agreement.docx", pages: 9, sha256: null, sections: [], createdAt: "2026-09-28T00:00:00+00:00", reused: false };
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
  hasGuidance: false,
  reviewHead: "",
};
const finished: RunView = { ...running, stage: "complete" };

function handlers() {
  return {
    openRun: vi.fn(async () => {}),
    openDocument: vi.fn(async () => {}),
    navigate: vi.fn(),
  };
}

function props(overrides: { view?: View; doc?: DocumentView | null; stage?: Stage; run?: RunView | null } = {}) {
  return { view: "assistant" as View, doc: null as DocumentView | null, stage: "empty" as Stage, run: null as RunView | null, ...handlers(), ...overrides };
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

  it("writes the open document, then the finished run, then the view; and clears them when the workspace closes", () => {
    setUrl("");
    const initial = props({ doc, stage: "workspace", run: running });
    const { rerender } = renderHook((p) => useUrlState(p), { initialProps: initial });
    expect(window.location.search).toBe("?document=doc1");

    rerender({ ...initial, run: finished });
    expect(window.location.search).toBe("?document=doc1&run=run1");

    rerender({ ...initial, run: finished, view: "runs" });
    expect(window.location.search).toBe("?view=runs&document=doc1&run=run1");

    rerender({ ...initial, run: finished, view: "runs", stage: "empty" });
    expect(window.location.search).toBe("?view=runs");
  });
});
