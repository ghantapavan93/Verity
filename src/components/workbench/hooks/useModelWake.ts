"use client";

import { useCallback, useEffect, useRef } from "react";
import { wakeModel } from "@/lib/api";

// How often this page may ask the API to wake a hosted model: no more often than the API's own awake window
// (WORKBENCH_MODEL_AWAKE_S, 240 s), within which it would answer "awake" without waking anything.
export const WAKE_EVERY_MS = 4 * 60 * 1000;

/**
 * A hosted model sleeps when idle and takes minutes to wake. Opening a contract, and starting a question after a pause,
 * ask the API to wake it (backend application/wake_model.py), so the question finds it awake. The API bounds what that
 * spends; this page asks at most once in WAKE_EVERY_MS, never for a model on the server itself, and a refusal or a
 * failure changes nothing on the page.
 */
export function useModelWake(hosted: boolean, docId: string | null, typing: boolean): void {
  const lastWake = useRef<number | null>(null);
  const request = useCallback(() => {
    if (!hosted) return;
    const now = Date.now();
    if (lastWake.current !== null && now - lastWake.current < WAKE_EVERY_MS) return;
    lastWake.current = now;
    wakeModel().catch(() => undefined);
  }, [hosted]);
  useEffect(() => {
    if (docId) request();
  }, [docId, typing, request]);
}
