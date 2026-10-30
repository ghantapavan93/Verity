"use client";

import { useCallback, useEffect, useMemo, useReducer, useRef, useState } from "react";
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
  | { phase: "starting"; documentId: string; question: string; hasGuidance: boolean; error: null }
  | { phase: "not_started"; documentId: string; question: string; hasGuidance: boolean; error: string }
  | { phase: "following"; documentId: string | null; run: RunView; stage: RunStage; details: StageDetails; error: null }
  | { phase: "loading_record"; documentId: string | null; run: RunView; stage: RunStage; details: StageDetails; error: null }
  | { phase: "finished"; documentId: string | null; run: RunView; details: StageDetails; error: string | null }
  | { phase: "disconnected"; documentId: string | null; run: RunView; stage: RunStage; details: StageDetails; error: string };

type Action =
  | { type: "start"; documentId: string; question: string; hasGuidance: boolean }
  | { type: "created"; documentId: string; run: RunView }
  | { type: "not_started"; error: string }
  | { type: "stage"; runId: string; stage: RunStage; detail?: string | null }
  | { type: "record"; run: RunView }
  | { type: "stream_error"; runId: string; error: string }
  | { type: "error"; error: string | null }
  | { type: "show"; documentId: string | null; run: RunView }
  | { type: "refresh"; run: RunView }
  | { type: "clear" };

const IDLE: FollowerState = { phase: "idle", error: null };
const NO_DETAILS: StageDetails = {};

/** A run put on screen: followed while in flight, else finished as it is. */
function shown(run: RunView, documentId: string | null): FollowerState {
  return TERMINAL.includes(run.stage)
    ? { phase: "finished", documentId, run, details: {}, error: null }
    : { phase: "following", documentId, run, stage: run.stage, details: {}, error: null };
}

function reduce(state: FollowerState, action: Action): FollowerState {
  switch (action.type) {
    case "start":
      return { phase: "starting", documentId: action.documentId, question: action.question, hasGuidance: action.hasGuidance, error: null };
    case "created":
      return shown(action.run, action.documentId);
    case "not_started":
      return state.phase === "starting"
        ? { phase: "not_started", documentId: state.documentId, question: state.question, hasGuidance: state.hasGuidance, error: action.error }
        : state;
    case "stage": {
      if ((state.phase !== "following" && state.phase !== "loading_record") || state.run.id !== action.runId) return state;
      const order = STAGE_ORDER as readonly string[];
      const details =
        action.detail && order.includes(action.stage) && state.details[action.stage] !== action.detail
          ? { ...state.details, [action.stage]: action.detail }
          : state.details;
      // The terminal stage is not applied from the event: the record that carries the findings is fetched next.
      if (TERMINAL.includes(action.stage))
        return { phase: "loading_record", documentId: state.documentId, run: state.run, stage: state.stage, details, error: null };
      // A run's stages only move forward, and a poll repeats every stage the run has passed: an earlier stage keeps the
      // current one, and an event that changes nothing keeps the state itself, so a poll of an unchanged run renders nothing.
      const stage = order.indexOf(action.stage) < order.indexOf(state.stage) ? state.stage : action.stage;
      if (state.phase === "following" && stage === state.stage && details === state.details) return state;
      return { phase: "following", documentId: state.documentId, run: state.run, stage, details, error: null };
    }
    case "record":
      // The record of the run being followed, and only that. A record taken in any other phase was one read after its
      // run's terminal event and landing after the reader moved on: it replaced another finished run, turned a question
      // still being created into the old run, and came back after the screen was cleared (stress test, 2026-10-30).
      if ((state.phase !== "following" && state.phase !== "loading_record" && state.phase !== "disconnected") || state.run.id !== action.run.id) return state;
      return { phase: "finished", documentId: state.documentId, run: action.run, details: state.details, error: null };
    case "stream_error":
      if ((state.phase !== "following" && state.phase !== "loading_record") || state.run.id !== action.runId) return state;
      return { phase: "disconnected", documentId: state.documentId, run: state.run, stage: state.stage, details: state.details, error: action.error };
    case "error":
      if (action.error === null) return state.error === null ? state : ({ ...state, error: null } as FollowerState);
      if (state.phase === "idle" || state.phase === "finished") return { ...state, error: action.error };
      return state;
    case "show":
      return shown(action.run, action.documentId);
    case "refresh":
      // A newer copy of the finished run on screen, and only that: a refresh of any other run, or of one still in
      // flight, is a record from before the person moved on (m9 smoke, 2026-10-11) and changes nothing.
      return state.phase === "finished" && state.run.id === action.run.id ? { ...state, run: action.run } : state;
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
  // Who owns the screen: changed, synchronously, only by what actually puts something there (a question asked, a run
  // shown or cleared). A claim alone does not change it: an open that claims and then fails has put nothing on screen.
  const screen = useRef(0);
  const stopFollowing = useRef<(() => void) | null>(null);
  // How many runs are ahead of the followed one on the model, as the API last said; null when it has not said.
  const [ahead, setAhead] = useState<number | null>(null);
  // Each question asked and each run shown is a newer intent. A caller that must wait before it can show a run
  // claims one first and shows nothing if another came after it: the newest intent owns the screen.
  const intent = useRef(0);

  /** Marks a newer intent and returns whether it is still the newest; check it after every await, before showing. */
  const claim = useCallback(() => {
    const mine = ++intent.current;
    return () => intent.current === mine;
  }, []);

  useEffect(() => () => stopFollowing.current?.(), []);

  const stop = useCallback(() => {
    stopFollowing.current?.();
    stopFollowing.current = null;
  }, []);

  const attach = useCallback(
    (runId: string) => {
      stop();
      setAhead(null);
      stopFollowing.current = followRun(
        runId,
        (stage, detail) => dispatch({ type: "stage", runId, stage, detail }),
        (finished) => dispatch({ type: "record", run: finished }),
        (message) => dispatch({ type: "stream_error", runId, error: message }),
        setAhead,
      );
    },
    [stop],
  );

  /**
   * False when the API refused the question and it is still on screen (the caller puts the words back); true
   * otherwise, including when the reader moved on before the answer: nothing of it is on screen to restore.
   */
  const ask = useCallback(
    async (documentId: string, guidanceId: string | null, question: string): Promise<boolean> => {
      ++intent.current;
      const owner = ++screen.current;
      stop();
      dispatch({ type: "start", documentId, question, hasGuidance: guidanceId !== null });
      try {
        const created = await createRun({ documentId, guidanceId, question });
        // The reader opened another contract or run, or asked again, while this was being created: the run is in the
        // record (Runs) and is not put over what is on screen now (2026-10-13: it landed on the other contract). When
        // nothing replaced the waiting question (an open that claimed and failed), it is shown as before (reviews).
        if (screen.current !== owner) return true;
        dispatch({ type: "created", documentId, run: created });
        if (!TERMINAL.includes(created.stage)) attach(created.id);
        return true;
      } catch (error) {
        // A refusal for a question the reader has left is not put over what is on screen now, nor its words into
        // that contract's composer (review: a late 502 marked the newer question failed, offered to send twice).
        if (screen.current !== owner) return true;
        dispatch({ type: "not_started", error: errorMessage(error) });
        return false;
      }
    },
    [stop, attach],
  );

  /**
   * A run loaded from the record: shown as it is, and followed when it is still in flight. `documentId` is the contract
   * the run reads (the record's RunDetail.documentId): a run is shown only beside it (`beside`).
   */
  const show = useCallback(
    (run: RunView | null, documentId: string | null = null) => {
      intent.current++;
      screen.current++;
      stop();
      if (run === null) dispatch({ type: "clear" });
      else {
        dispatch({ type: "show", documentId, run });
        if (!TERMINAL.includes(run.stage)) attach(run.id);
      }
    },
    [stop, attach],
  );

  /** Follow the run again after a dropped stream: the record is truth, so nothing is lost by reattaching. */
  const resume = useCallback(() => {
    if (state.phase === "disconnected") {
      dispatch({ type: "show", documentId: state.documentId, run: { ...state.run, stage: state.stage } });
      attach(state.run.id);
    }
  }, [state, attach]);

  /** A newer copy of the finished run on screen; ignored when the screen has moved to another run since. */
  const refresh = useCallback((run: RunView) => dispatch({ type: "refresh", run }), []);

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
  // A run is live from the moment its question is sent until its record is in, a dropped stream included: the phases in
  // which another question would abandon the one on screen. The one predicate every way to ask reads (one run at a time).
  const live = state.phase === "starting" || state.phase === "following" || state.phase === "loading_record" || state.phase === "disconnected";
  const stageDetails: StageDetails = "details" in state ? state.details : NO_DETAILS;

  return {
    state,
    /** The contract the run or the question on screen belongs to; null when there is neither. */
    documentId: "documentId" in state ? state.documentId : null,
    run,
    pending,
    live,
    runError: state.error,
    stageDetails,
    ahead: state.phase === "following" ? ahead : null,
    ask,
    show,
    refresh,
    claim,
    stop,
    resume,
    setRunError,
  };
}

export type RunController = ReturnType<typeof useRunFollower>;

/**
 * The follower as the screen beside a contract shows it: its run or its question only when they belong to that contract,
 * and otherwise nothing, as if idle. Every surface reads the run through this (the answer, the cards, the drawer, the live
 * region, the address, the memo and the revision check), so none can show one contract's answer over another. Until
 * 2026-10-30 the run carried no contract and the shell paired the two by the order its calls happened to land in: a verified
 * quote from contract X was shown over contract Y as "Found word for word in the document text" (stress test).
 */
export function beside(runs: RunController, documentId: string | null): RunController {
  if (runs.documentId === null ? runs.state.phase === "idle" : runs.documentId === documentId) return runs;
  return { ...runs, state: IDLE, documentId: null, run: null, pending: null, live: false, runError: null, stageDetails: NO_DETAILS, ahead: null };
}
