/**
 * The run follower mirrors what the API reports and nothing else: the created run, each stage
 * event with the API's own detail, then the finished record. When the run cannot be started,
 * the failure is shown as such, with no reason invented on the client.
 */

import { act, renderHook } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { createRun, followRun } from "@/lib/api";
import type { RunView } from "@/lib/types";

const api = vi.hoisted(() => ({
  createRun: vi.fn<typeof createRun>(),
  followRun: vi.fn<typeof followRun>(),
}));

vi.mock("@/lib/api", () => ({
  createRun: api.createRun,
  followRun: api.followRun,
  errorMessage: (error: unknown) => (error instanceof Error ? error.message : String(error)),
}));

import { useRunFollower } from "./useRunFollower";

function runView(overrides: Partial<RunView> = {}): RunView {
  return {
    id: "run1",
    question: "What notice is needed to terminate for convenience?",
    stage: "reading",
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
    ...overrides,
  };
}

/** The callbacks the hook handed to followRun on its most recent call. */
function callbacks() {
  const call = api.followRun.mock.calls.at(-1);
  if (!call) throw new Error("followRun was not called");
  return { onStage: call[1], onDone: call[2], onError: call[3] };
}

describe("useRunFollower", () => {
  beforeEach(() => {
    api.createRun.mockReset();
    api.followRun.mockReset();
  });

  it("creates the run, mirrors each stage and its detail, then takes the finished record", async () => {
    const stop = vi.fn();
    api.createRun.mockResolvedValue(runView());
    api.followRun.mockReturnValue(stop);

    const { result, unmount } = renderHook(() => useRunFollower());
    await act(() => result.current.ask("doc1", null, "What notice is needed to terminate for convenience?"));

    expect(api.createRun).toHaveBeenCalledWith({ documentId: "doc1", guidanceId: null, question: "What notice is needed to terminate for convenience?" });
    expect(api.followRun).toHaveBeenCalledWith("run1", expect.any(Function), expect.any(Function), expect.any(Function));
    expect(result.current.run?.id).toBe("run1");
    expect(result.current.run?.stage).toBe("reading");

    act(() => {
      callbacks().onStage("finding_evidence", "6 candidate sections");
      callbacks().onStage("checking", "against the question");
    });
    expect(result.current.run?.stage).toBe("checking");
    expect(result.current.stageDetails).toEqual({ finding_evidence: "6 candidate sections", checking: "against the question" });

    const finished = runView({ stage: "complete", latencyMs: 32000 });
    act(() => callbacks().onDone(finished));
    expect(result.current.run).toEqual(finished);
    expect(result.current.runError).toBeNull();

    unmount();
    expect(stop).toHaveBeenCalledTimes(1);
  });

  it("shows a run that could not be started as failed, with the API's sentence and no reason of its own", async () => {
    api.createRun.mockRejectedValue(new Error("The workbench API at http://127.0.0.1:8000 is not reachable."));

    const { result } = renderHook(() => useRunFollower());
    await act(() => result.current.ask("doc1", "g1", "Is there a most favoured nation clause?"));

    expect(result.current.runError).toBe("The workbench API at http://127.0.0.1:8000 is not reachable.");
    expect(result.current.run?.stage).toBe("failed");
    expect(result.current.run?.reason).toBeNull();
    expect(api.followRun).not.toHaveBeenCalled();
  });

  it("stops following the earlier run when a new question is asked, and surfaces a stream error", async () => {
    const stopFirst = vi.fn();
    const stopSecond = vi.fn();
    api.createRun.mockResolvedValueOnce(runView({ id: "run1" })).mockResolvedValueOnce(runView({ id: "run2" }));
    api.followRun.mockReturnValueOnce(stopFirst).mockReturnValueOnce(stopSecond);

    const { result } = renderHook(() => useRunFollower());
    await act(() => result.current.ask("doc1", null, "first"));
    await act(() => result.current.ask("doc1", null, "second"));

    expect(stopFirst).toHaveBeenCalledTimes(1);
    expect(stopSecond).not.toHaveBeenCalled();
    expect(result.current.run?.id).toBe("run2");
    expect(result.current.stageDetails).toEqual({});

    act(() => callbacks().onError("The event stream closed before the run finished."));
    expect(result.current.runError).toBe("The event stream closed before the run finished.");
  });
});
