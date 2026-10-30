"use client";

import styles from "../Workbench.module.css";
import { VerityMark } from "../icons";
import { revealInvisible } from "@/lib/text";
import { statusLabel, type FindingStatus } from "@/lib/types";

/** A finding's status as the API decided it, worded by whether its run had guidance. The tone is presentation; the status is not decided here. */
export function StatusChip({ status, hasGuidance, source }: { status: FindingStatus; hasGuidance: boolean; source?: string }) {
  // The pass colour is for a pass code stood behind (a record made under policy v2); the model's own pass is shown plain.
  const codeBacked = status === "pass" && source != null && source !== "model_hint";
  const tone =
    status === "needs_review" ? styles.statusReview : status === "missing" ? styles.statusAbsent : codeBacked ? styles.statusPass : styles.statusMuted;
  return <span className={`${styles.statusChip} ${tone}`}>{statusLabel(status, hasGuidance, source)}</span>;
}

/** The spectral dot that marks model or upload work in progress. */
export function Shimmer() {
  return <span className={styles.shimmer} aria-hidden="true" />;
}

/** The product's name and mark, as the landing, the door and the memo show it. */
export function Brand() {
  return (
    <div className={styles.brand}>
      <VerityMark size={20} />
      <span className={styles.wordmark}>Verity</span>
    </div>
  );
}

/**
 * Stored text as it is: an invisible format character an older reading still holds, or one a model wrote into its quote,
 * topic or conclusion, is shown as a marker naming it, so the screen never displays different text from what was checked
 * (lib/text revealInvisible). Every string a model or a file wrote is rendered through this, or through shownText where
 * it must be a string. `start` and `end` (code points) show a stretch of the text, read in the context of the whole.
 * A missing value renders nothing, as React renders it in place of a string.
 */
export function Visible({ text, start, end }: { text: string | null | undefined; start?: number; end?: number }) {
  if (text == null) return null;
  return (
    <>
      {revealInvisible(text, start, end).map((piece, i) =>
        piece.invisible ? (
          <span key={i} className={styles.invisibleMark} title={`An invisible character (${piece.codePoint}) in the recorded text`}>
            {piece.codePoint}
          </span>
        ) : (
          piece.text
        ),
      )}
    </>
  );
}
