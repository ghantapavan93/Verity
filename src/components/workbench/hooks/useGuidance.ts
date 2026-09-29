"use client";

import { useCallback, useState } from "react";
import { createGuidance, errorMessage } from "@/lib/api";

export const DEFAULT_GUIDANCE = "We can accept termination for convenience at 30 days' notice or more. Anything below 30 days requires review.";

export interface GuidanceState {
  id: string;
  text: string;
}

/** The legal guidance attached to the scope: the saved record, the popover and its draft. */
export function useGuidance(onError: (message: string) => void) {
  const [guidance, setGuidance] = useState<GuidanceState | null>(null);
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [draft, setDraft] = useState(DEFAULT_GUIDANCE);

  const apply = useCallback(async () => {
    const text = draft.trim();
    if (!text) {
      setGuidance(null);
      setOpen(false);
      return;
    }
    setBusy(true);
    try {
      const record = await createGuidance(text);
      setGuidance({ id: record.id, text: record.text });
      setOpen(false);
    } catch (error) {
      onError(errorMessage(error));
    } finally {
      setBusy(false);
    }
  }, [draft, onError]);

  const remove = useCallback(() => setGuidance(null), []);

  return { guidance, setGuidance, open, setOpen, busy, draft, setDraft, apply, remove };
}

export type GuidanceController = ReturnType<typeof useGuidance>;
