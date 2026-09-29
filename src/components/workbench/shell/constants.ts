import type { RunStage } from "@/lib/types";

/** The shell's own state machine: empty composer → drag → upload in flight → workspace. */
export type Stage = "empty" | "dragging" | "processing" | "workspace";

/** The four destinations on the rail. Only the Assistant needs a document on screen. */
export type View = "assistant" | "documents" | "findings" | "runs";

export const VIEWS: readonly View[] = ["assistant", "documents", "findings", "runs"];
export const TERMINAL: readonly RunStage[] = ["complete", "unresolved", "failed"];

/** The one easing curve of the frozen motion system. */
export const EASE = [0.2, 0, 0, 1] as const;

/** The two transition presets the shell uses; instant when the person prefers reduced motion. */
export function transitions(reduceMotion: boolean) {
  return {
    morph: reduceMotion ? { duration: 0 } : { duration: 0.32, ease: EASE },
    quick: reduceMotion ? { duration: 0 } : { duration: 0.18, ease: EASE },
  };
}
