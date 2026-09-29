"use client";

import { useCallback, useEffect, useState, type PointerEvent as ReactPointerEvent } from "react";

export const DEFAULT_DOC_WIDTH = 62;
export const MIN_DOC_WIDTH = 45;
export const MAX_DOC_WIDTH = 75;
const DOC_WIDTH_KEY = "workbench.docWidth";

/** The divider position survives a reload within the session. Only ever read on the client. */
function readDocWidth(): number {
  if (typeof window === "undefined") return DEFAULT_DOC_WIDTH;
  try {
    const saved = Number(window.sessionStorage.getItem(DOC_WIDTH_KEY));
    return saved >= MIN_DOC_WIDTH && saved <= MAX_DOC_WIDTH ? saved : DEFAULT_DOC_WIDTH;
  } catch {
    return DEFAULT_DOC_WIDTH;
  }
}

/** Width of the document pane as a percentage of the split, with pointer dragging and session persistence. */
export function useDocWidth() {
  const [docWidth, setDocWidth] = useState(readDocWidth);

  useEffect(() => {
    try {
      window.sessionStorage.setItem(DOC_WIDTH_KEY, String(Math.round(docWidth)));
    } catch {
      // storage unavailable; the divider simply starts at the default next time
    }
  }, [docWidth]);

  // The divider is a direct child of the split, so the split's box comes from the event.
  const startDrag = useCallback((event: ReactPointerEvent<HTMLDivElement>) => {
    const split = event.currentTarget.parentElement;
    if (!split) return;
    event.preventDefault();
    const rect = split.getBoundingClientRect();
    const move = (e: PointerEvent) => {
      const pct = ((e.clientX - rect.left) / rect.width) * 100;
      setDocWidth(Math.min(MAX_DOC_WIDTH, Math.max(MIN_DOC_WIDTH, pct)));
    };
    const up = () => {
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", up);
    };
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", up);
  }, []);

  return { docWidth, setDocWidth, startDrag };
}
