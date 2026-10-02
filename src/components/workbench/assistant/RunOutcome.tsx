"use client";

import styles from "../Workbench.module.css";
import { citationLabel, REASON_TITLES, type FindingView, type RunView, type SectionView } from "@/lib/types";

/** The title for a run that ended without findings, from the reason the API recorded. */
export function outcomeTitle(run: RunView): string {
  if (run.reason) return REASON_TITLES[run.reason];
  return run.stage === "failed" ? "The run did not complete" : "No supporting passage found";
}

/**
 * The body of an unresolved or failed run. Failures offer a retry; unresolved runs state what was
 * searched and show the proposal the verifier withheld, as the model wrote it, struck through.
 */
export function RunOutcome({
  run,
  runError,
  sectionsById,
  onRetry,
  onEvidence,
}: {
  run: RunView;
  runError: string | null;
  sectionsById: Map<string, SectionView>;
  onRetry: (question: string) => void;
  onEvidence: (finding: FindingView, trigger: HTMLElement | null) => void;
}) {
  return (
    <>
      <div className={styles.resultHead}>
        <span className={styles.resultTopic}>{outcomeTitle(run)}</span>
        <span className={`${styles.statusChip} ${run.stage === "failed" ? styles.statusBad : styles.statusMuted}`}>
          {run.stage === "failed" ? "Failed" : "Unresolved"}
        </span>
      </div>
      <p className={styles.resultText}>{run.error ?? runError ?? run.note ?? "No passage in the sections retrieved for this question could be verified."}</p>
      {run.withheld.length > 0 && <WithheldList findings={run.withheld} sectionsById={sectionsById} onEvidence={onEvidence} />}
      {run.stage === "failed" && (
        <div className={styles.resultActions}>
          <button type="button" className={styles.actionButton} onClick={() => onRetry(run.question)}>
            Try again
          </button>
        </div>
      )}
    </>
  );
}

/**
 * Findings the model proposed whose quotes code could not find in the document. Shown exactly as
 * proposed, with each unfound quote struck through beside the verifier's verdict, so the trust
 * boundary is visible rather than claimed.
 */
export function WithheldList({
  findings,
  sectionsById,
  onEvidence,
}: {
  findings: FindingView[];
  sectionsById: Map<string, SectionView>;
  onEvidence: (finding: FindingView, trigger: HTMLElement | null) => void;
}) {
  return (
    <div className={styles.withheldList}>
      <div className={styles.evidenceHead}>What the model proposed · withheld by the verifier</div>
      {findings.map((finding) => (
        <div key={finding.id} className={styles.withheld}>
          <div className={styles.withheldTopic}>{finding.topic}</div>
          <p className={styles.withheldText}>{finding.conclusion}</p>
          {finding.spans.map((span, i) => {
            const section = span.sectionId ? sectionsById.get(span.sectionId) : undefined;
            const where = section ? citationLabel(section) : span.citedSectionLabel ? `the model's ${span.citedSectionLabel}` : "the sections handed over";
            return (
              <div key={i} className={styles.withheldSpan}>
                <span className={span.verified ? styles.withheldQuoteKept : `${styles.withheldQuote} ${styles.quoteWithheld}`}>{span.quote}</span>
                <span className={styles.verifiedTag}>{span.verified ? `verified in ${where}` : `not found verbatim in ${where}`}</span>
              </div>
            );
          })}
          <div className={styles.resultActions}>
            <button type="button" className={styles.actionButton} onClick={(e) => onEvidence(finding, e.currentTarget)}>
              Inspect evidence
            </button>
          </div>
        </div>
      ))}
    </div>
  );
}
