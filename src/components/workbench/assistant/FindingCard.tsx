"use client";

import styles from "../Workbench.module.css";
import { NARROW_QUERY } from "../shell/constants";
import { StatusChip, Visible } from "../shell/primitives";
import { checkLedger, valueNotes } from "@/lib/checks";
import { isLocated, passageLabel, type FindingView, type SectionView, type SpanView } from "@/lib/types";

function excerpt(quote: string, max = 150): string {
  return quote.length > max ? `${quote.slice(0, max - 3).trimEnd()}…` : quote;
}

/**
 * One finding as an object: topic, status, conclusion, the passages the API verified, actions.
 * Only spans the API marked verified are shown; the card never decides what counts as evidence.
 */
export function FindingCard({
  finding,
  hasGuidance,
  sectionsById,
  context = null,
  onJump,
  onEvidence,
  onFollowUp,
}: {
  finding: FindingView;
  hasGuidance: boolean;
  sectionsById: Map<string, SectionView>;
  /** How much of the document the model was handed (lib/types sectionsReadNote); null when the run did not record it. */
  context?: { text: string; partial: boolean } | null;
  onJump: (sectionId: string, span: SpanView | null) => void;
  onEvidence: (trigger: HTMLElement | null) => void;
  onFollowUp: () => void;
}) {
  const evidence = finding.spans.flatMap((span) => {
    const section = isLocated(span) ? sectionsById.get(span.sectionId) : undefined;
    return section ? [{ span, section }] : [];
  });
  const primary = evidence[0] ?? null;
  return (
    <article className={styles.result}>
      <header className={styles.resultHead}>
        <span className={styles.resultTopic}>{finding.topic}</span>
        <StatusChip status={finding.status} hasGuidance={hasGuidance} source={finding.statusSource} />
      </header>
      <p className={styles.resultText}>{finding.conclusion}</p>
      {/* The passages come straight after the conclusion, whole (each is at most 150 characters), so the answer can be
          read against its source on the card itself (frontend review, 2026-10-09: the quote was below the fold in 99 of 99
          renders, behind the ledger). */}
      {evidence.length > 0 && (
        <div className={styles.evidenceList}>
          <div className={styles.evidenceHead}>
            {finding.evidenceKind === "coverage"
              ? `Closest provisions read · ${evidence.length} · the model found none that states the point`
              : `Evidence · ${evidence.length} passage${evidence.length === 1 ? "" : "s"}`}
          </div>
          {evidence.map(({ span, section }, i) => (
            <button
              key={i}
              type="button"
              className={styles.citationRow}
              // The paper is hidden on a narrow screen: the passage is shown in the evidence sheet, not jumped to on nothing.
              onClick={(e) => (window.matchMedia(NARROW_QUERY).matches ? onEvidence(e.currentTarget) : onJump(section.id, span))}
              title="Show in the document"
            >
              <span className={styles.citationLabel}>{passageLabel(span, section)}</span>
              <span className={styles.citationExcerpt}>
                <Visible text={excerpt(span.quote)} />
              </span>
            </button>
          ))}
          {/* Code's word on a choice among values, beside the passages that offered it (lib/checks valueNotes). */}
          {valueNotes(finding).map((note, i) => (
            <p key={`${i}-${note}`} className={styles.valueNote}>
              {/* Read aloud as what it is: a check code made, not a stray "code" (browser QA, 2026-10-09). */}
              <span className={styles.checkBy} aria-hidden="true">
                code
              </span>
              <span className={styles.visuallyHidden}>Checked by code: </span>
              {note}
            </p>
          ))}
        </div>
      )}
      {/* What was checked, by whom: one row per recorded fact (lib/checks). A located quote and a supported answer are
          two facts; only the first is ever established by code. */}
      <dl className={styles.checks} aria-label="What was checked">
        {checkLedger(finding, hasGuidance, sectionsById, context).map((row) => (
          <div key={row.key} className={styles.checkRow} data-by={row.by}>
            <dt className={styles.checkKey}>{row.label}</dt>
            <dd className={styles.checkText}>
              <span className={styles.checkBy}>{row.by === "code" ? "code" : row.by === "model" ? "model" : row.by === "person" ? "person" : "—"}</span>
              {row.text}
            </dd>
          </div>
        ))}
      </dl>
      <div className={styles.resultActions}>
        <button
          type="button"
          className={`${styles.actionButton} ${styles.wideOnly}`}
          onClick={() => primary && onJump(primary.section.id, primary.span)}
          disabled={!primary}
        >
          View in document
        </button>
        <button type="button" className={`${styles.actionButton} ${styles.actionPrimary}`} onClick={(e) => onEvidence(e.currentTarget)}>
          Inspect evidence
        </button>
        <button type="button" className={styles.actionButton} onClick={onFollowUp}>
          Ask another question
        </button>
      </div>
    </article>
  );
}
