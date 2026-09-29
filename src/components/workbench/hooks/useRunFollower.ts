"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { createRun, errorMessage, followRun } from "@/lib/api";
import { STAGE_ORDER, type RunStage, type RunView } from "@/lib/types";

/**
 * The current run as the API reports it: created, followed stage by stage over SSE (with a
 * polling fallback inside the client), then replaced by the finished record. Stage details are
 * the API's own counts and timings; nothing here interprets the model's output.
 */
export function useRunFollower() {
  const [run, setRun] = useState<RunView | null>(null);
  const [runError, setRunError] = useState<string | null>(null);
  const [stageDetails, setStageDetails] = useState<Partial<Record<RunStage, string>>>({});
  const stopFollowing = useRef<(() => void) | null>(null);

  useEffect(() => () => stopFollowing.current?.(), []);

  const stop = useCallback(() => {
    stopFollowing.current?.();
  }, []);

  const ask = useCallback(async (documentId: string, guidanceId: string | null, question: string) => {
    stopFollowing.current?.();
    setRunError(null);
    setStageDetails({});
    setRun({
      id: "",
      question,
      stage: "reading",
      findings: [],
      withheld: [],
      model: "",
      promptVersion: "",
      promptHash: "",
      latencyMs: null,
      note: null,
      error: null,
      reason: null,
      reused: false,
    });
    try {
      const created = await createRun({ documentId, guidanceId, question });
      setRun(created);
      stopFollowing.current = followRun(
        created.id,
        (stage, detail) => {
          setRun((r) => (r && r.id === created.id ? { ...r, stage } : r));
          if (detail && (STAGE_ORDER as readonly string[]).includes(stage)) setStageDetails((d) => ({ ...d, [stage]: detail }));
        },
        (finished) => setRun(finished),
        (message) => setRunError(message),
      );
    } catch (error) {
      setRunError(errorMessage(error));
      setRun((r) => (r ? { ...r, stage: "failed", error: errorMessage(error), reason: null } : r));
    }
  }, []);

  return { run, setRun, runError, setRunError, stageDetails, setStageDetails, ask, stop };
}

export type RunController = ReturnType<typeof useRunFollower>;
