"use client";

import { useSyncExternalStore } from "react";
import { NARROW_QUERY } from "../shell/constants";

function narrowQuery(): MediaQueryList | null {
  return typeof window !== "undefined" && typeof window.matchMedia === "function" ? window.matchMedia(NARROW_QUERY) : null;
}

function subscribe(change: () => void): () => void {
  const query = narrowQuery();
  query?.addEventListener("change", change);
  return () => query?.removeEventListener("change", change);
}

/**
 * Whether the window is as narrow as NARROW_QUERY, where the contract text is hidden: an action that shows a passage in
 * it has nothing to show there (the 375 px review, 2026-10-15: the evidence sheet's passage buttons marked text no one
 * could see). False on the server and wherever matchMedia is absent.
 */
export function useNarrow(): boolean {
  return useSyncExternalStore(
    subscribe,
    () => narrowQuery()?.matches ?? false,
    () => false,
  );
}
