"use client";

import { useCallback, useEffect, useMemo, useReducer, useRef } from "react";
import { createRun, errorMessage, followRun } from "@/lib/api";
import { STAGE_ORDER, type RunStage, type RunView } from "@/lib/types";

type StageDetails = Partial<Record<RunStage, string>>;
const TERMINAL: readonly RunStage[] = ["complete", "unresolved", "failed"];

/**
 * Every state the follower can be in, and nothing else. There is no run without an id, no finished run
 * without its record, and no "still loading" flag beside a finished record: each of those was a race the
 * old flags could express. The stage of a run in flight comes from the API's events; the terminal stage is
 * never applied from an event, only from the record fetched after it, so findings and stage arrive together.
 */
export type FollowerState =
  | { phase: "idle"; error: string | null }
  | { phase: "starting"; question: string; hasGuidance: boolean; error: null }
  | { phase: "not_started"; question: string; hasGuidance: boolean; error: string }
  | { phase: "following"; run: RunView; stage: RunStage; details: StageDetails; error: null }
  | { phase: "loading_record"; run: RunView; stage: RunStage; details: StageDetails; error: null }
  | { phase: "finished"; run: RunView; details: StageDetails; error: string | null }
  | { phase: "disconnected"; run: RunView; stage: RunStage; details: StageDetails; error: string };

type Action =
  | { type: "start"; question: string; hasGuidance: boolean }
  | { type: "created"; run: RunView }
  | { type: "not_started"; error: string }
  | { type: "stage"; runId: string; stage: RunStage; detail?: string | null }
  | { type: "record"; run: RunView }
  | { type: "stream_error"; runId: string; error: string }
  | { type: "error"; error: string | null }
  | { type: "show"; run: RunView }
  | { type: "clear" };

const IDLE: FollowerState = { phase: "idle", error: null };

function reduce(state: FollowerState, action: Action): FollowerState {
  switch (action.type) {
    case "start":
      return { phase: "starting", question: action.question, hasGuidance: action.hasGuidance, error: null };
    case "created":
      return TERMINAL.includes(action.run.stage)
        ? { phase: "finished", run: action.run, details: {}, error: null }
        : { phase: "following", run: action.run, stage: action.run.stage, details: {}, error: null };
    case "not_started":
      return state.phase === "starting" ? { phase: "not_started", question: state.question, hasGuidance: state.hasGuidance, error: action.error } : state;
    case "stage": {
      if ((state.phase !== "following" && state.phase !== "loading_record") || state.run.id !== action.runId) return state;
      const details =
        action.detail && (STAGE_ORDER as readonly string[]).includes(action.stage) ? { ...state.details, [action.stage]: action.detail } : state.details;
      // The terminal stage is not applied from the event: the record that carries the findings is fetched next.
      if (TERMINAL.includes(action.stage)) return { phase: "loading_record", run: state.run, stage: state.stage, details, error: null };
      return { phase: "following", run: state.run, stage: action.stage, details, error: null };
    }
    case "record":
      if ((state.phase === "following" || state.phase === "loading_record" || state.phase === "disconnected") && state.run.id !== action.run.id) return state;
      return { phase: "finished", run: action.run, details: "details" in state ? state.details : {}, error: null };
    case "stream_error":
      if ((state.phase !== "following" && state.phase !== "loading_record") || state.run.id !== action.runId) return state;
      return { phase: "disconnected", run: state.run, stage: state.stage, details: state.details, error: action.error };
    case "error":
      if (action.error === null) return state.error === null ? state : ({ ...state, error: null } as FollowerState);
      if (state.phase === "idle" || state.phase === "finished") return { ...state, error: action.error };
      return state;
    case "show":
      return TERMINAL.includes(action.run.stage)
        ? { phase: "finished", run: action.run, details: {}, error: null }
        : { phase: "following", run: action.run, stage: action.run.stage, details: {}, error: null };
    case "clear":
      return IDLE;
  }
}

/**
 * The current run as the API reports it: created, followed stage by stage over SSE (with a polling
 * fallback inside the client), then replaced by the finished record. Stage details are the API's own
 * counts and timings; nothing here interprets the model's output.
 */
export function useRunFollower() {
  const [state, dispatch] = useReducer(reduce, IDLE);
  const stopFollowing = useRef<(() => void) | null>(null);

  useEffect(() => () => stopFollowing.current?.(), []);

  const stop = useCallback(() => {
    stopFollowing.current?.();
    stopFollowing.current = null;
  }, []);

  const attach = useCallback(
    (runId: string) => {
      stop();
      stopFollowing.current = followRun(
        runId,
        (stage, detail) => dispatch({ type: "stage", runId, stage, detail }),
        (finished) => dispatch({ type: "record", run: finished }),
        (message) => dispatch({ type: "stream_error", runId, error: message }),
      );
    },
    [stop],
  );

  /** True when the API accepted the question; false when it refused it (the caller keeps the text). */
  const ask = useCallback(
    async (documentId: string, guidanceId: string | null, question: string): Promise<boolean> => {
      stop();
      dispatch({ type: "start", question, hasGuidance: guidanceId !== null });
      try {
        const created = await createRun({ documentId, guidanceId, question });
        dispatch({ type: "created", run: created });
        if (!TERMINAL.includes(created.stage)) attach(created.id);
        return true;
      } catch (error) {
        dispatch({ type: "not_started", error: errorMessage(error) });
        return false;
      }
    },
    [stop, attach],
  );

  /** A run loaded from the record: shown as it is, and followed when it is still in flight. */
  const show = useCallback(
    (run: RunView | null) => {
      stop();
      if (run === null) dispatch({ type: "clear" });
      else {
        dispatch({ type: "show", run });
        if (!TERMINAL.includes(run.stage)) attach(run.id);
      }
    },
    [stop, attach],
  );

  /** Follow the run again after a dropped stream: the record is truth, so nothing is lost by reattaching. */
  const resume = useCallback(() => {
    if (state.phase === "disconnected") {
      dispatch({ type: "show", run: { ...state.run, stage: state.stage } });
      attach(state.run.id);
    }
  }, [state, attach]);

  const setRunError = useCallback((error: string | null) => dispatch({ type: "error", error }), []);

  const run = useMemo<RunView | null>(() => {
    switch (state.phase) {
      case "following":
      case "loading_record":
      case "disconnected":
        return { ...state.run, stage: state.stage };
      case "finished":
        return state.run;
      default:
        return null;
    }
  }, [state]);
  const pending = state.phase === "starting" || state.phase === "not_started" ? { question: state.question, hasGuidance: state.hasGuidance } : null;
  const stageDetails: StageDetails = "details" in state ? state.details : {};

  return { state, run, pending, runError: state.error, stageDetails, ask, show, stop, resume, setRunError };
}

export type RunController = ReturnType<typeof useRunFollower>;
