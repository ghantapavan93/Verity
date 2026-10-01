"use client";

import { useEffect, useState } from "react";
import { errorMessage, getRunExplanation } from "@/lib/api";
import type { RunExplanationView } from "@/lib/types";

export type ExplanationRead = { runId: string; explanation: RunExplanationView | null; problem: string | null };

/**
 * The explanation of a run, read once from the API (`GET /api/runs/{id}/explanation`) and kept by run id.
 * A null run id reads nothing. The caller renders what the record says and decides nothing.
 */
export function useRunExplanation(runId: string | null): ExplanationRead | null {
  const [read, setRead] = useState<ExplanationRead | null>(null);

  useEffect(() => {
    if (!runId) return;
    let cancelled = false;
    getRunExplanation(runId)
      .then((explanation) => {
        if (!cancelled) setRead({ runId, explanation, problem: null });
      })
      .catch((error: unknown) => {
        if (!cancelled) setRead({ runId, explanation: null, problem: errorMessage(error) });
      });
    return () => {
      cancelled = true;
    };
  }, [runId]);

  return read && read.runId === runId ? read : null;
}
