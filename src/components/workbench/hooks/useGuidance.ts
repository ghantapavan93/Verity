"use client";

import { useCallback, useState } from "react";
import { createGuidance, errorMessage } from "@/lib/api";

export const DEFAULT_GUIDANCE = "We can accept termination for convenience at 30 days' notice or more. Anything below 30 days requires review.";

export interface GuidanceState {
  id: string;
  text: string;
}

/** The legal guidance attached to the scope: the saved record, the popover, its draft, and why a save was refused.
 * The refusal is the popover's own: handed to the run's error slot, it was dropped while a run was in progress and not
 * shown beside a finished run's findings, so a refused guidance explained nothing (m7 audit, 2026-10-10). */
export function useGuidance() {
  const [guidance, setGuidance] = useState<GuidanceState | null>(null);
  const [open, setOpenState] = useState(false);
  const [busy, setBusy] = useState(false);
  const [draft, setDraft] = useState(DEFAULT_GUIDANCE);
  const [error, setError] = useState<string | null>(null);
  // Opening or closing the popover starts it without a stale refusal.
  const setOpen = useCallback((next: boolean | ((open: boolean) => boolean)) => {
    setOpenState(next);
    setError(null);
  }, []);

  const apply = useCallback(async () => {
    const text = draft.trim();
    if (!text) {
      setGuidance(null);
      setOpen(false);
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const record = await createGuidance(text);
      setGuidance({ id: record.id, text: record.text });
      setOpen(false);
    } catch (refused) {
      setError(errorMessage(refused));
    } finally {
      setBusy(false);
    }
  }, [draft, setOpen]);

  const remove = useCallback(() => setGuidance(null), []);

  return { guidance, setGuidance, open, setOpen, busy, draft, setDraft, apply, remove, error };
}

export type GuidanceController = ReturnType<typeof useGuidance>;
