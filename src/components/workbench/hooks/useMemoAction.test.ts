/**
 * A memo belongs to the run it was written for: one that arrives after another run came on screen is kept with its run
 * id (AssistantPanel shows it only under that run), so reopening the same run still shows it; the busy state of a
 * request the screen has left does not stay on the button.
 */

import { act, renderHook } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { MemoRecord } from "@/lib/api";
import type { RunView } from "@/lib/types";

let finish: (memo: MemoRecord) => void = () => undefined;
vi.mock("@/lib/api", () => ({
  createMemo: () => new Promise<MemoRecord>((resolve) => (finish = resolve)),
  errorMessage: (error: unknown) => String(error),
}));

import { useMemoAction } from "./useMemoAction";

const RUN = { id: "runX", stage: "complete" } as RunView;
const MEMO = { id: "m1", runId: "runX", docxUrl: "/d", htmlUrl: "/h", docxSha256: "s", reviewHead: "" } as MemoRecord;

describe("a memo and the run it was written for", () => {
  it("arriving after the screen moved on, it is kept with its run id and the busy state is cleared", async () => {
    const { result } = renderHook(() => useMemoAction());
    act(() => {
      void result.current.generate(RUN);
    });
    expect(result.current.busy).toBe(true);
    act(() => result.current.reset()); // another run came on screen
    expect(result.current.busy).toBe(false);
    await act(async () => finish(MEMO));
    expect(result.current.memo?.runId).toBe("runX");
    expect(result.current.busy).toBe(false);
  });
});
