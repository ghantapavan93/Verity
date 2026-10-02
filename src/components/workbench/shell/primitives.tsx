"use client";

import styles from "../Workbench.module.css";
import { VerityMark } from "../icons";
import { statusLabel, type FindingStatus } from "@/lib/types";

/** A finding's status as the API decided it, worded by whether its run had guidance. The tone is presentation; the status is not decided here. */
export function StatusChip({ status, hasGuidance, source }: { status: FindingStatus; hasGuidance: boolean; source?: string }) {
  const tone = status === "needs_review" ? styles.statusReview : status === "pass" ? styles.statusPass : styles.statusMuted;
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
