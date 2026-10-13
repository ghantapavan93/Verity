"use client";

import { useCallback, useEffect, useRef } from "react";
import { wakeModel } from "@/lib/api";

// How often this page may ask the API to wake a hosted model: no more often than the API's own awake window
// (WORKBENCH_MODEL_AWAKE_S, 240 s), within which it would answer "awake" without waking anything.
export const WAKE_EVERY_MS = 4 * 60 * 1000;

/**
 * A hosted model sleeps when idle and takes one and a half to three minutes to wake. Waking it costs GPU time whether
 * or not a question follows, so it is asked for only when the reader does something that leads to a question: adds a
 * contract (`added` counts those), or starts typing one (`typing`). Opening a contract from a link, a reload, Back, or a
 * recorded run only looks, and wakes nothing (2026-10-13: before, any opened contract woke the model). The API bounds
 * what is spent (backend application/wake_model.py); this page asks at most once in WAKE_EVERY_MS, never for a model on
 * the server itself, and a refusal or a failure changes nothing on the page.
 */
export function useModelWake(hosted: boolean, added: number, typing: boolean): void {
  const lastWake = useRef<number | null>(null);
  const request = useCallback(() => {
    if (!hosted) return;
    const now = Date.now();
    if (lastWake.current !== null && now - lastWake.current < WAKE_EVERY_MS) return;
    lastWake.current = now;
    wakeModel().catch(() => undefined);
  }, [hosted]);
  // Only an action wakes it: a contract added, or a question started. A change of `hosted` alone (health answering
  // again after a blip) is not one (review, 2026-10-13); an action made before health answered is served once it does.
  const seen = useRef({ added, typing: false });
  const pending = useRef(false);
  useEffect(() => {
    const acted = added > seen.current.added || (typing && !seen.current.typing);
    seen.current = { added, typing };
    if (acted) pending.current = true;
    if (pending.current && hosted) {
      pending.current = false;
      request();
    }
  }, [added, typing, hosted, request]);
}
