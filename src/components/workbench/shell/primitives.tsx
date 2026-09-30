"use client";

import styles from "../Workbench.module.css";
import { statusLabel, type FindingStatus } from "@/lib/types";

/** A finding's status as the API decided it, worded by whether its run had guidance. The tone is presentation; the status is not decided here. */
export function StatusChip({ status, hasGuidance }: { status: FindingStatus; hasGuidance: boolean }) {
  const tone = status === "needs_review" ? styles.statusReview : status === "pass" ? styles.statusPass : styles.statusMuted;
  return <span className={`${styles.statusChip} ${tone}`}>{statusLabel(status, hasGuidance)}</span>;
}

/** The spectral dot that marks model or upload work in progress. */
export function Shimmer() {
  return <span className={styles.shimmer} aria-hidden="true" />;
}

export function UserChip() {
  return (
    <div className={styles.user}>
      <span className={styles.avatar} aria-hidden="true">
        PG
      </span>
      <span className={styles.userName}>Pavan G.</span>
    </div>
  );
}
