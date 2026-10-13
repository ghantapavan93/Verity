/**
 * The page asks the API to wake a hosted model when a contract opens and when a question is started after a pause,
 * never for a model on the server itself, and no more than once in WAKE_EVERY_MS however often it re-renders.
 */

import { renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const wakeModel = vi.fn(() => Promise.resolve({ state: "waking" as const }));
vi.mock("@/lib/api", () => ({ wakeModel: () => wakeModel() }));

import { useModelWake, WAKE_EVERY_MS } from "./useModelWake";

beforeEach(() => {
  vi.useFakeTimers();
  vi.setSystemTime(new Date("2026-10-13T05:00:00Z"));
  wakeModel.mockClear();
});
afterEach(() => vi.useRealTimers());

type Props = { hosted: boolean; docId: string | null; typing: boolean };
const mount = (props: Props) => renderHook((p: Props) => useModelWake(p.hosted, p.docId, p.typing), { initialProps: props });

describe("waking a hosted model before the question", () => {
  it("opening a contract wakes it once, however often the page renders", () => {
    const view = mount({ hosted: true, docId: null, typing: false });
    expect(wakeModel).not.toHaveBeenCalled();
    view.rerender({ hosted: true, docId: "doc-1", typing: false });
    view.rerender({ hosted: true, docId: "doc-1", typing: false });
    view.rerender({ hosted: true, docId: "doc-1", typing: true });
    expect(wakeModel).toHaveBeenCalledTimes(1);
  });

  it("a question started after a pause wakes it again", () => {
    const view = mount({ hosted: true, docId: "doc-1", typing: false });
    vi.advanceTimersByTime(WAKE_EVERY_MS + 1000);
    view.rerender({ hosted: true, docId: "doc-1", typing: true });
    expect(wakeModel).toHaveBeenCalledTimes(2);
  });

  it("control: a model on the server itself is never woken, and nothing is asked before a contract is open", () => {
    const view = mount({ hosted: false, docId: "doc-1", typing: true });
    view.rerender({ hosted: false, docId: "doc-2", typing: false });
    mount({ hosted: true, docId: null, typing: true });
    expect(wakeModel).not.toHaveBeenCalled();
  });

  it("a refused or failed wake-up changes nothing on the page", async () => {
    wakeModel.mockImplementationOnce(() => Promise.reject(new Error("429")));
    mount({ hosted: true, docId: "doc-1", typing: false });
    await Promise.resolve();
    expect(wakeModel).toHaveBeenCalledTimes(1);
  });
});
