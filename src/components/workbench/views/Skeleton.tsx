"use client";

import styles from "./Views.module.css";

/** Rows the shape of the list that is coming, so the page does not jump when the record arrives. Still, not shimmering. */
export function ListSkeleton({ rows = 5, label }: { rows?: number; label: string }) {
  return (
    <ul className={`${styles.list} ${styles.skeleton}`} aria-busy="true" aria-label={`${label}, loading`}>
      {Array.from({ length: rows }, (_, i) => (
        <li key={i} className={styles.skeletonRow} aria-hidden="true">
          <span className={styles.skeletonIndex} />
          <span className={styles.skeletonMain}>
            <span className={styles.skeletonBar} style={{ width: `${44 + ((i * 17) % 36)}%` }} />
            <span className={`${styles.skeletonBar} ${styles.skeletonBarQuiet}`} style={{ width: `${28 + ((i * 11) % 30)}%` }} />
          </span>
          <span className={styles.skeletonSide} />
        </li>
      ))}
    </ul>
  );
}

/** A read that failed is said, not shown as an empty list; the reader can ask for it again. */
export function ReadFailed({ what, error, onRetry }: { what: string; error: string; onRetry: () => void }) {
  return (
    <div className={styles.failed} role="alert">
      <p className={styles.failedHead}>Could not read {what}. Nothing here is known.</p>
      <p className={styles.failedText}>{error}</p>
      <button type="button" className={styles.reviewButton} onClick={onRetry}>
        Read it again
      </button>
    </div>
  );
}
