/**
 * The page asks the API to wake a hosted model only when the reader does something that leads to a question: adds a
 * contract, or starts typing a question. Opening a contract from a link, a reload or a recorded run wakes nothing, a
 * model on the server itself is never woken, and however often the page renders it asks at most once in WAKE_EVERY_MS.
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

type Props = { hosted: boolean; added: number; typing: boolean };
const mount = (props: Props) => renderHook((p: Props) => useModelWake(p.hosted, p.added, p.typing), { initialProps: props });

describe("waking a hosted model before the question", () => {
  it("adding a contract wakes it once, however often the page renders", () => {
    const view = mount({ hosted: true, added: 0, typing: false });
    expect(wakeModel).not.toHaveBeenCalled();
    view.rerender({ hosted: true, added: 1, typing: false });
    view.rerender({ hosted: true, added: 1, typing: false });
    view.rerender({ hosted: true, added: 1, typing: true });
    expect(wakeModel).toHaveBeenCalledTimes(1);
  });

  it("a contract opened from a link, a reload or a recorded run wakes nothing until the reader starts a question", () => {
    // Nothing added in this page; a contract is on screen because the address named it.
    const view = mount({ hosted: true, added: 0, typing: false });
    view.rerender({ hosted: true, added: 0, typing: false });
    expect(wakeModel).not.toHaveBeenCalled();
    view.rerender({ hosted: true, added: 0, typing: true });
    expect(wakeModel).toHaveBeenCalledTimes(1);
  });

  it("a question started after a pause wakes it again", () => {
    const view = mount({ hosted: true, added: 1, typing: false });
    vi.advanceTimersByTime(WAKE_EVERY_MS + 1000);
    view.rerender({ hosted: true, added: 1, typing: true });
    expect(wakeModel).toHaveBeenCalledTimes(2);
  });

  it("control: a model on the server itself is never woken", () => {
    const view = mount({ hosted: false, added: 1, typing: true });
    view.rerender({ hosted: false, added: 2, typing: false });
    expect(wakeModel).not.toHaveBeenCalled();
  });

  it("a refused or failed wake-up changes nothing on the page", async () => {
    wakeModel.mockImplementationOnce(() => Promise.reject(new Error("429")));
    mount({ hosted: true, added: 1, typing: false });
    await Promise.resolve();
    expect(wakeModel).toHaveBeenCalledTimes(1);
  });
});
