/**
 * A memo belongs to the run it was written for: one that arrives after another run came on screen is kept with its run
 * id (AssistantPanel shows it only under that run), so reopening the same run still shows it; the busy state of a
 * request the screen has left does not stay on the button.
 */

import { act, renderHook } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { MemoRecord } from "@/lib/api";
import type { RunView } from "@/lib/types";

const pending: ((memo: MemoRecord) => void)[] = [];
const finish = (memo: MemoRecord) => pending.shift()?.(memo);
vi.mock("@/lib/api", () => ({
  createMemo: () => new Promise<MemoRecord>((resolve) => pending.push(resolve)),
  errorMessage: (error: unknown) => String(error),
}));

import { useMemoAction } from "./useMemoAction";

const RUN = { id: "runX", stage: "complete" } as RunView;
const MEMO = { id: "m1", runId: "runX", docxUrl: "/d", htmlUrl: "/h", docxSha256: "s", reviewHead: "" } as MemoRecord;

describe("a memo and the run it was written for", () => {
  beforeEach(() => {
    pending.length = 0; // a test that fails early leaves its requests unanswered
  });

  it("arriving after the screen moved on, it is kept with its run id and the busy state is cleared", async () => {
    const { result } = renderHook(() => useMemoAction());
    act(() => {
      void result.current.generate(RUN);
    });
    expect(result.current.busy).toBe(true);
    act(() => result.current.reset()); // another run came on screen
    expect(result.current.busy).toBe(false);
    await act(async () => finish(MEMO));
    expect(result.current.memoFor("runX")?.id).toBe("m1");
    expect(result.current.busy).toBe(false);
  });

  it("an older memo answering after a newer one does not replace it", async () => {
    const { result } = renderHook(() => useMemoAction());
    const OTHER = { ...MEMO, id: "m2", runId: "runY" } as MemoRecord;
    let resolveX: (memo: MemoRecord) => void = () => undefined;
    act(() => {
      void result.current.generate(RUN);
    });
    resolveX = pending.shift() as (memo: MemoRecord) => void;
    act(() => result.current.reset()); // run Y comes on screen
    act(() => {
      void result.current.generate({ id: "runY", stage: "complete" } as RunView);
    });
    await act(async () => finish(OTHER)); // Y's memo first
    await act(async () => resolveX(MEMO)); // then X's, late
    expect(result.current.memoFor("runY")?.id).toBe("m2");
  });

  it("a memo answering after the reader went to another run and came back shows under its own run, and stays", async () => {
    const { result } = renderHook(() => useMemoAction());
    const OTHER = { ...MEMO, id: "m2", runId: "runY" } as MemoRecord;
    act(() => {
      void result.current.generate(RUN);
    });
    const resolveX = pending.shift() as (memo: MemoRecord) => void;
    act(() => result.current.reset()); // run Y on screen
    act(() => {
      void result.current.generate({ id: "runY", stage: "complete" } as RunView);
    });
    act(() => result.current.reset()); // back to run X
    await act(async () => resolveX(MEMO));
    expect(result.current.memoFor("runX")?.id).toBe("m1");
    await act(async () => finish(OTHER)); // Y's answers last
    expect(result.current.memoFor("runX")?.id).toBe("m1");
  });

  it("two requests for one run: the earlier finishing first leaves the later one writing", async () => {
    const { result } = renderHook(() => useMemoAction());
    act(() => {
      void result.current.generate(RUN);
    });
    const resolveFirst = pending.shift() as (memo: MemoRecord) => void;
    act(() => {
      void result.current.generate(RUN); // the palette's command does not wait for the button
    });
    await act(async () => resolveFirst({ ...MEMO, id: "m-early" }));
    expect(result.current.busy).toBe(true);
    await act(async () => finish(MEMO));
    expect(result.current.memoFor("runX")?.id).toBe("m1");
    expect(result.current.busy).toBe(false);
  });

  it("within one run, an earlier request's memo answering last does not replace the later one's", async () => {
    const { result } = renderHook(() => useMemoAction());
    act(() => {
      void result.current.generate(RUN);
    });
    const resolveFirst = pending.shift() as (memo: MemoRecord) => void;
    act(() => {
      void result.current.generate(RUN);
    });
    await act(async () => finish(MEMO)); // the later one first
    await act(async () => resolveFirst({ ...MEMO, id: "m-early" }));
    expect(result.current.memoFor("runX")?.id).toBe("m1");
  });
});
