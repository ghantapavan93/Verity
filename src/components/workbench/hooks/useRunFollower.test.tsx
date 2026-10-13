/**
 * The run follower mirrors what the API reports and nothing else: the created run, each stage event
 * with the API's own detail, then the finished record. It cannot represent a run without an id, a
 * finished run without its record, or a finished record beside a spinner: each was a race before.
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
    shared: false,
    hasGuidance: false,
    reviewHead: "",
    guidanceText: null,
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
    expect(result.current.state.phase).toBe("following");
    expect(result.current.run?.id).toBe("run1");
    expect(result.current.run?.stage).toBe("reading");
    expect(result.current.pending).toBeNull();

    act(() => {
      callbacks().onStage("finding_evidence", "6 candidate sections");
      callbacks().onStage("checking", "against the question");
    });
    expect(result.current.run?.stage).toBe("checking");
    expect(result.current.stageDetails).toEqual({ finding_evidence: "6 candidate sections", checking: "against the question" });

    // The terminal stage arrives as an event first; the run does not turn complete until its record is here.
    act(() => callbacks().onStage("complete"));
    expect(result.current.state.phase).toBe("loading_record");
    expect(result.current.run?.stage).toBe("checking");

    const finished = runView({ stage: "complete", latencyMs: 32000 });
    act(() => callbacks().onDone(finished));
    expect(result.current.state.phase).toBe("finished");
    expect(result.current.run).toEqual(finished);
    expect(result.current.runError).toBeNull();

    unmount();
    expect(stop).toHaveBeenCalledTimes(1);
  });

  it("shows the question as pending while the run is created, and never a run without an id", async () => {
    let resolve: (run: RunView) => void = () => {};
    api.createRun.mockReturnValue(new Promise<RunView>((r) => (resolve = r)));
    api.followRun.mockReturnValue(vi.fn());

    const { result } = renderHook(() => useRunFollower());
    let asked: Promise<boolean> = Promise.resolve(false);
    act(() => {
      asked = result.current.ask("doc1", "g1", "Is there a most favoured nation clause?");
    });
    expect(result.current.state.phase).toBe("starting");
    expect(result.current.run).toBeNull();
    expect(result.current.pending).toEqual({ question: "Is there a most favoured nation clause?", hasGuidance: true });

    await act(async () => {
      resolve(runView({ id: "run7", stage: "reading" }));
      await asked;
    });
    expect(result.current.run?.id).toBe("run7");
    expect(result.current.pending).toBeNull();
  });

  it("reports a run that could not be started with the API's sentence, keeps the question, and has no run", async () => {
    api.createRun.mockRejectedValue(new Error("The workbench API at http://127.0.0.1:8000 is not reachable."));

    const { result } = renderHook(() => useRunFollower());
    await act(() => result.current.ask("doc1", "g1", "Is there a most favoured nation clause?"));

    expect(result.current.state.phase).toBe("not_started");
    expect(result.current.runError).toBe("The workbench API at http://127.0.0.1:8000 is not reachable.");
    expect(result.current.run).toBeNull();
    expect(result.current.pending?.question).toBe("Is there a most favoured nation clause?");
    expect(api.followRun).not.toHaveBeenCalled();
  });

  it("stops following the earlier run when a new question is asked, and a dropped stream keeps the run as disconnected", async () => {
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

    act(() => callbacks().onStage("checking", "against the question"));
    act(() => callbacks().onError("The event stream closed before the run finished."));
    expect(result.current.state.phase).toBe("disconnected");
    expect(result.current.runError).toBe("The event stream closed before the run finished.");
    expect(result.current.run?.id).toBe("run2");
    expect(result.current.run?.stage).toBe("checking");

    // Resuming reattaches to the same run; the record is truth, so nothing was lost.
    api.followRun.mockReturnValueOnce(vi.fn());
    act(() => result.current.resume());
    expect(result.current.state.phase).toBe("following");
    expect(api.followRun).toHaveBeenLastCalledWith("run2", expect.any(Function), expect.any(Function), expect.any(Function));
  });

  it("follows a run in flight that was loaded from the record, and shows a finished one as it is", () => {
    api.followRun.mockReturnValue(vi.fn());
    const { result } = renderHook(() => useRunFollower());

    act(() => result.current.show(runView({ id: "run3", stage: "checking" })));
    expect(result.current.state.phase).toBe("following");
    expect(api.followRun).toHaveBeenCalledWith("run3", expect.any(Function), expect.any(Function), expect.any(Function));

    act(() => result.current.show(runView({ id: "run4", stage: "complete" })));
    expect(result.current.state.phase).toBe("finished");
    expect(api.followRun).toHaveBeenCalledTimes(1);

    act(() => result.current.show(null));
    expect(result.current.state.phase).toBe("idle");
    expect(result.current.run).toBeNull();
  });

  it("ignores events for a run it no longer follows", async () => {
    api.createRun.mockResolvedValueOnce(runView({ id: "run1" })).mockResolvedValueOnce(runView({ id: "run2" }));
    api.followRun.mockReturnValue(vi.fn());
    const { result } = renderHook(() => useRunFollower());
    await act(() => result.current.ask("doc1", null, "first"));
    const first = callbacks();
    await act(() => result.current.ask("doc1", null, "second"));
    act(() => first.onStage("verifying", "late event from run1"));
    act(() => first.onDone(runView({ id: "run1", stage: "complete" })));
    expect(result.current.run?.id).toBe("run2");
    expect(result.current.run?.stage).toBe("reading");
    expect(result.current.stageDetails).toEqual({});
  });
});

describe("records that arrive after the person moved on (m9 smoke, 2026-10-11)", () => {
  beforeEach(() => {
    api.createRun.mockReset();
    api.followRun.mockReset();
  });

  it("a refresh replaces the finished run it names", () => {
    const { result } = renderHook(() => useRunFollower());
    act(() => result.current.show(runView({ stage: "complete" })));
    act(() => result.current.refresh(runView({ stage: "complete", reviewHead: "review-3" })));
    expect(result.current.run?.reviewHead).toBe("review-3");
  });

  it("a refresh of the reviewed run, landing after the next question, neither shows it nor stops the new one", async () => {
    // The race the live smoke test reproduced: confirm a finding, close the drawer, ask at once; the record re-read
    // after the review came back last and put the reviewed run back on screen, and the new run was never followed.
    const stopNew = vi.fn();
    api.followRun.mockReturnValue(stopNew);
    api.createRun.mockResolvedValue(runView({ id: "run2", stage: "reading", question: "What law governs this agreement?" }));
    const { result } = renderHook(() => useRunFollower());
    act(() => result.current.show(runView({ id: "run1", stage: "complete" })));
    await act(() => result.current.ask("doc1", null, "What law governs this agreement?"));

    act(() => result.current.refresh(runView({ id: "run1", stage: "complete", reviewHead: "review-1" })));

    expect(result.current.state.phase).toBe("following");
    expect(result.current.run?.id).toBe("run2");
    expect(stopNew).not.toHaveBeenCalled();
    act(() => callbacks().onStage("checking", "against the question"));
    expect(result.current.run?.stage).toBe("checking");
  });

  it("a refresh of a run still in flight changes nothing: its stream owns it", () => {
    api.followRun.mockReturnValue(vi.fn());
    const { result } = renderHook(() => useRunFollower());
    act(() => result.current.show(runView({ stage: "checking" })));
    act(() => result.current.refresh(runView({ stage: "complete" })));
    expect(result.current.state.phase).toBe("following");
    expect(result.current.run?.stage).toBe("checking");
  });

  it("a claim stays the newest intent until a question is asked, a run is shown, or another claim is made", async () => {
    api.followRun.mockReturnValue(vi.fn());
    api.createRun.mockResolvedValue(runView({ id: "run2", stage: "reading" }));
    const { result } = renderHook(() => useRunFollower());

    const opening = result.current.claim();
    expect(opening()).toBe(true);
    await act(() => result.current.ask("doc1", null, "What law governs this agreement?"));
    expect(opening()).toBe(false);

    const second = result.current.claim();
    act(() => result.current.show(runView({ id: "run3", stage: "complete" })));
    expect(second()).toBe(false);

    const earlier = result.current.claim();
    const later = result.current.claim();
    expect(earlier()).toBe(false);
    expect(later()).toBe(true);
  });
});

describe("a run created after the reader moved on", () => {
  beforeEach(() => {
    api.createRun.mockReset();
    api.followRun.mockReset();
  });

  function deferredRun() {
    let resolve: (run: RunView) => void = () => undefined;
    api.createRun.mockImplementationOnce(() => new Promise<RunView>((r) => (resolve = r)));
    return (run: RunView) => resolve(run);
  }

  it("is not put over another contract or run the reader opened meanwhile", async () => {
    const answer = deferredRun();
    const { result } = renderHook(() => useRunFollower());
    let accepted: Promise<boolean> = Promise.resolve(false);
    act(() => {
      accepted = result.current.ask("docA", null, "What notice is needed?");
    });
    act(() => result.current.show(null)); // another contract opened: nothing is on screen for it
    await act(async () => answer(runView({ id: "runA", stage: "complete" })));
    expect(await accepted).toBe(true);
    expect(result.current.run).toBeNull();
  });

  it("is still shown when the reader's other action did not replace the waiting question", async () => {
    const answer = deferredRun();
    const { result } = renderHook(() => useRunFollower());
    let accepted: Promise<boolean> = Promise.resolve(false);
    act(() => {
      accepted = result.current.ask("docA", null, "What notice is needed?");
    });
    // A recorded run's open claims the screen first, then fails before showing anything.
    act(() => {
      result.current.claim();
    });
    await act(async () => answer(runView({ id: "runA", stage: "complete" })));
    expect(await accepted).toBe(true);
    expect(result.current.run?.id).toBe("runA");
  });
});

describe("the screen's owner, not its phase (re-review probes, 2026-10-13)", () => {
  beforeEach(() => {
    api.createRun.mockReset();
    api.followRun.mockReset();
  });

  it("a run arriving after the reader opened another contract and asked there (refused) is not put on that contract", async () => {
    let answerA: (run: RunView) => void = () => undefined;
    api.createRun.mockImplementationOnce(() => new Promise<RunView>((r) => (answerA = r))).mockRejectedValueOnce(new Error("Too many runs"));
    const { result } = renderHook(() => useRunFollower());
    act(() => {
      void result.current.ask("docA", null, "What notice is needed?");
    });
    act(() => result.current.show(null)); // contract B opened
    await act(async () => {
      await result.current.ask("docB", null, "Which law governs?"); // refused by the API
    });
    await act(async () => answerA(runView({ id: "runA", stage: "complete" })));
    expect(result.current.run).toBeNull();
  });

  it("an older question's run arriving while a newer question waits is not put over it", async () => {
    let answerA: (run: RunView) => void = () => undefined;
    let answerB: (run: RunView) => void = () => undefined;
    api.createRun
      .mockImplementationOnce(() => new Promise<RunView>((r) => (answerA = r)))
      .mockImplementationOnce(() => new Promise<RunView>((r) => (answerB = r)));
    api.followRun.mockReturnValue(() => undefined);
    const { result } = renderHook(() => useRunFollower());
    act(() => {
      void result.current.ask("docA", null, "What notice is needed?");
    });
    act(() => result.current.show(null)); // contract B opened
    act(() => {
      void result.current.ask("docB", null, "Which law governs?"); // still waiting for its run
    });
    await act(async () => answerA(runView({ id: "runA", stage: "complete" })));
    expect(result.current.run).toBeNull();
    await act(async () => answerB(runView({ id: "runB", stage: "complete" })));
    expect(result.current.run?.id).toBe("runB");
  });

  it("a run arriving in the same moment another contract is opened is not shown", async () => {
    let answerA: (run: RunView) => void = () => undefined;
    api.createRun.mockImplementationOnce(() => new Promise<RunView>((r) => (answerA = r)));
    const { result } = renderHook(() => useRunFollower());
    act(() => {
      void result.current.ask("docA", null, "What notice is needed?");
    });
    await act(async () => {
      result.current.show(null);
      answerA(runView({ id: "runA", stage: "complete" }));
    });
    expect(result.current.run).toBeNull();
  });

  it("an older question refused after the reader asked another, still waiting, leaves the newer one as it is", async () => {
    let refuseA: (error: Error) => void = () => undefined;
    api.createRun
      .mockImplementationOnce(() => new Promise<RunView>((_, reject) => (refuseA = reject)))
      .mockImplementationOnce(() => new Promise<RunView>(() => undefined));
    const { result } = renderHook(() => useRunFollower());
    let acceptedA: boolean | undefined;
    act(() => {
      void result.current.ask("docA", null, "What notice is needed?").then((ok) => (acceptedA = ok));
    });
    act(() => result.current.show(null)); // contract B opened
    act(() => {
      void result.current.ask("docB", null, "Which law governs?");
    });
    await act(async () => refuseA(new Error("502 Bad Gateway")));
    expect(result.current.runError).toBeNull();
    expect(result.current.pending?.question).toBe("Which law governs?");
    expect(acceptedA).toBe(true); // nothing to put back into contract B's composer
  });
});
