"use client";

import { AnimatePresence, motion } from "framer-motion";
import type { Ref } from "react";
import styles from "../Workbench.module.css";
import { IconClose } from "../icons";
import { EASE } from "../shell/constants";
import { StatusChip } from "../shell/primitives";
import { formatWhen } from "@/lib/format";
import { citationLabel, type FindingView, type RunView, type SectionView, type SpanView } from "@/lib/types";

/**
 * The glass panel that shows where a finding came from: each quoted passage with the API's
 * verification verdict, the guidance it was checked against, the result, and the run record.
 */
export function EvidenceDrawer({
  finding,
  run,
  guidanceText,
  sectionsById,
  onJump,
  onClose,
  closeRef,
  reduceMotion,
}: {
  finding: FindingView | null;
  run: RunView | null;
  guidanceText: string | null;
  sectionsById: Map<string, SectionView>;
  onJump: (sectionId: string, span: SpanView | null) => void;
  onClose: () => void;
  closeRef: Ref<HTMLButtonElement>;
  reduceMotion: boolean;
}) {
  return (
    <AnimatePresence initial={false}>
      {finding && (
        <motion.aside
          className={styles.drawer}
          initial={{ opacity: 0, x: reduceMotion ? 0 : 24 }}
          animate={{ opacity: 1, x: 0 }}
          exit={{ opacity: 0, x: reduceMotion ? 0 : 24 }}
          transition={{ duration: reduceMotion ? 0 : 0.22, ease: EASE }}
          aria-label="Evidence"
        >
          <header className={styles.drawerHead}>
            <span>Evidence</span>
            <button ref={closeRef} type="button" className={styles.iconButton} aria-label="Close evidence" onClick={onClose}>
              <IconClose />
            </button>
          </header>
          <EvidenceBody finding={finding} run={run} guidance={run ? (run.guidanceText ?? null) : guidanceText} sectionsById={sectionsById} onJump={onJump} />
        </motion.aside>
      )}
    </AnimatePresence>
  );
}

function EvidenceBody({
  finding,
  run,
  guidance,
  sectionsById,
  onJump,
}: {
  finding: FindingView;
  run: RunView | null;
  guidance: string | null;
  sectionsById: Map<string, SectionView>;
  onJump: (sectionId: string, span: SpanView | null) => void;
}) {
  return (
    <>
      <section className={styles.drawerSection}>
        <h4>Contract</h4>
        {finding.spans.map((span, i) => {
          const section = span.sectionId ? sectionsById.get(span.sectionId) : undefined;
          return (
            <div key={i} className={styles.drawerSpan}>
              {section && span.verified ? (
                <button type="button" className={styles.drawerRef} onClick={() => onJump(section.id, span)}>
                  {citationLabel(section)}
                </button>
              ) : (
                <div className={styles.drawerRefStatic}>{section ? citationLabel(section) : "Section not identified"}</div>
              )}
              <blockquote className={span.verified ? styles.drawerQuote : `${styles.drawerQuote} ${styles.quoteWithheld}`}>“{span.quote}”</blockquote>
              <span className={styles.verifiedTag}>
                {!span.verified
                  ? `Not found verbatim in the document · withheld${span.citedSectionLabel ? ` · the model cited ${span.citedSectionLabel}` : ""}`
                  : finding.evidenceKind === "coverage"
                    ? "Verified verbatim · the closest provision read; it does not state the point"
                    : `Verified verbatim in the document text · ${span.method}`}
              </span>
            </div>
          );
        })}
      </section>
      {(finding.guidanceReference || guidance) && (
        <section className={styles.drawerSection}>
          <h4>Guidance</h4>
          {finding.guidanceReference && <div className={styles.drawerRefStatic}>{finding.guidanceReference}</div>}
          {guidance && guidance !== finding.guidanceReference && <blockquote className={styles.drawerQuote}>“{guidance}”</blockquote>}
        </section>
      )}
      <section className={styles.drawerSection}>
        <h4>Result</h4>
        <dl className={styles.drawerFacts}>
          {finding.observed && (
            <div>
              <dt>Observed</dt>
              <dd>{finding.observed}</dd>
            </div>
          )}
          {finding.required && (
            <div>
              <dt>Required</dt>
              <dd>{finding.required}</dd>
            </div>
          )}
          <div>
            <dt>Result</dt>
            <dd>
              <StatusChip status={finding.status} hasGuidance={run?.hasGuidance ?? false} />
            </dd>
          </div>
          {finding.review && (
            <div>
              <dt>Reviewed</dt>
              <dd>
                {finding.review.verdict === "confirmed" ? "Confirmed" : "Dismissed"} by {finding.review.reviewer} · {formatWhen(finding.review.at)}
                {finding.review.note ? ` · ${finding.review.note}` : ""}
              </dd>
            </div>
          )}
        </dl>
        {finding.suggestedPosition && (
          <p className={styles.drawerPosition}>
            <strong>Suggested position.</strong> {finding.suggestedPosition}
          </p>
        )}
      </section>
      {run && (
        <section className={styles.drawerSection}>
          <h4>Run</h4>
          <dl className={styles.drawerFacts}>
            <div>
              <dt>Model</dt>
              <dd>{run.model}</dd>
            </div>
            <div>
              <dt>Prompt</dt>
              <dd>
                {run.promptVersion} · {run.promptHash.slice(0, 8)}
              </dd>
            </div>
            <div>
              <dt>Sources</dt>
              <dd>
                {finding.spans.filter((s) => s.verified).length} verified
                {finding.spans.some((s) => !s.verified) ? ` · ${finding.spans.filter((s) => !s.verified).length} withheld` : ""}
              </dd>
            </div>
            {run.latencyMs !== null && (
              <div>
                <dt>Latency</dt>
                <dd>{(run.latencyMs / 1000).toFixed(1)} s</dd>
              </div>
            )}
            <div>
              <dt>Run ID</dt>
              <dd>{run.id}</dd>
            </div>
          </dl>
        </section>
      )}
    </>
  );
}
