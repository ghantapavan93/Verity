"use client";

import styles from "../Workbench.module.css";
import { StatusChip } from "../shell/primitives";
import { citationLabel, isLocated, type FindingView, type SectionView, type SpanView } from "@/lib/types";

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
  onJump,
  onEvidence,
  onFollowUp,
}: {
  finding: FindingView;
  hasGuidance: boolean;
  sectionsById: Map<string, SectionView>;
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
        <StatusChip status={finding.status} hasGuidance={hasGuidance} />
      </header>
      <p className={styles.resultText}>{finding.conclusion}</p>
      {evidence.length > 0 && (
        <div className={styles.evidenceList}>
          <div className={styles.evidenceHead}>
            {finding.evidenceKind === "coverage"
              ? `Closest provisions read · ${evidence.length} · none states the point`
              : `Evidence · ${evidence.length} verified passage${evidence.length === 1 ? "" : "s"}`}
          </div>
          {evidence.map(({ span, section }, i) => (
            <button key={i} type="button" className={styles.citationRow} onClick={() => onJump(section.id, span)} title="Show in the document">
              <span className={styles.citationLabel}>{citationLabel(section)}</span>
              <span className={styles.citationExcerpt}>“{excerpt(span.quote)}”</span>
            </button>
          ))}
        </div>
      )}
      <div className={styles.resultActions}>
        <button type="button" className={styles.actionButton} onClick={() => primary && onJump(primary.section.id, primary.span)} disabled={!primary}>
          View in document
        </button>
        <button type="button" className={styles.actionButton} onClick={(e) => onEvidence(e.currentTarget)}>
          Inspect evidence
        </button>
        <button type="button" className={styles.actionButton} onClick={onFollowUp}>
          Ask follow-up
        </button>
      </div>
    </article>
  );
}
