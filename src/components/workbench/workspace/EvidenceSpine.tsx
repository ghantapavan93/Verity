"use client";

import styles from "../Workbench.module.css";
import type { Highlight } from "./DocumentPane";
import { codePointLength } from "@/lib/text";
import { isLocated, passageLabel, type DocumentView, type FindingView, type LocatedSpan, type SectionView } from "@/lib/types";

/** One verified quote, placed along the contract: how far into the text it begins, as a share of the whole. */
interface Tick {
  span: LocatedSpan;
  section: SectionView;
  topic: string;
  at: number;
}

/**
 * Where the evidence sits in the contract: a thin rule the height of the pane, with a mark for every verified quote
 * of the run on screen, at the place in the text where it begins. The marks are the record's located spans; a quote
 * code did not find has no mark. Clicking one jumps to it, as the citation rows do.
 */
export function EvidenceSpine({
  doc,
  findings,
  highlight,
  onJump,
}: {
  doc: DocumentView;
  findings: FindingView[];
  highlight: Highlight | null;
  onJump: (sectionId: string, span: LocatedSpan) => void;
}) {
  const starts = new Map<string, number>();
  let total = 0;
  for (const section of doc.sections) {
    starts.set(section.id, total);
    total += codePointLength(section.text) + 1;
  }
  if (total <= 1) return null;
  const sections = new Map(doc.sections.map((s) => [s.id, s]));
  const ticks: Tick[] = [];
  for (const finding of findings) {
    for (const span of finding.spans) {
      if (!isLocated(span)) continue;
      const section = sections.get(span.sectionId);
      const start = starts.get(span.sectionId);
      if (!section || start === undefined) continue;
      ticks.push({ span, section, topic: finding.topic, at: (start + span.start) / total });
    }
  }
  if (ticks.length === 0) return null;
  return (
    <nav className={styles.spine} aria-label="Where the evidence sits in the contract">
      <span className={styles.spineRule} aria-hidden="true" />
      {ticks.map((tick, i) => {
        const current = highlight?.sectionId === tick.span.sectionId && highlight.span?.start === tick.span.start;
        return (
          <button
            key={`${tick.span.sectionId}-${tick.span.start}-${i}`}
            type="button"
            className={`${styles.spineTick} ${current ? styles.spineTickCurrent : ""}`}
            style={{ top: `${Math.min(99, Math.max(1, tick.at * 100))}%` }}
            title={`${tick.topic}: ${passageLabel(tick.span, tick.section)}`}
            aria-label={`${tick.topic}, ${passageLabel(tick.span, tick.section)}: show in the document`}
            onClick={() => onJump(tick.span.sectionId, tick.span)}
          />
        );
      })}
    </nav>
  );
}
