"use client";

import { motion } from "framer-motion";
import type { Ref } from "react";
import styles from "../Workbench.module.css";
import { transitions } from "../shell/constants";
import { formatWhen, plural } from "@/lib/format";
import { codePointLength, splitByCodePoints } from "@/lib/text";
import { EvidenceSpine } from "./EvidenceSpine";
import type { DocumentView, FindingView, LocatedSpan, SectionView, SpanView } from "@/lib/types";

/** The passage to mark: a section, and within it the exact span the API located. */
export interface Highlight {
  sectionId: string;
  span: SpanView | null;
}

/** The parts of the file this reading did not read, with what the file had of them. Recorded by the API at upload. */
function notRead(doc: DocumentView): string[] {
  return (doc.coverage?.parts ?? []).filter((c) => c.status === "omitted" && c.count > 0).map((c) => `${c.part.replace(/_/g, " ")} (${c.count})`);
}

/** What is on the paper, and which view of the file it is when the file carried revisions or hidden text. */
function describe(doc: DocumentView): string {
  const parts = [doc.pages ? plural(doc.pages, "page") : "", plural(doc.sections.length, "section")];
  if (doc.trackedChanges) parts.push(`accepted view of ${plural(doc.trackedChanges, "tracked change")}`);
  if (doc.hiddenRuns) parts.push(`${plural(doc.hiddenRuns, "hidden run")} left out`);
  const unread = notRead(doc);
  if (unread.length) parts.push(`${plural(unread.length, "part")} not read`);
  if (doc.reused) parts.push("already in the workbench, opened as stored");
  return parts.filter(Boolean).join(" · ");
}

/** The contract on paper: the source of truth on screen. Renders sections and marks stored offsets; decides nothing. */
export function DocumentPane({
  doc,
  isSample,
  lit,
  highlight,
  reduceMotion,
  paneRef,
  findings = [],
  onJump,
}: {
  doc: DocumentView | null;
  isSample: boolean;
  lit: string | null;
  highlight: Highlight | null;
  reduceMotion: boolean;
  paneRef: Ref<HTMLDivElement>;
  /** The run on screen's findings, for the spine of marks down the paper's edge. */
  findings?: FindingView[];
  onJump?: (sectionId: string, span: LocatedSpan) => void;
}) {
  const { morph } = transitions(reduceMotion);
  const docMeta = doc ? describe(doc) : "";
  return (
    <motion.div
      className={styles.docPane}
      tabIndex={0}
      aria-label="Contract text"
      ref={paneRef}
      initial={{ opacity: 0, x: reduceMotion ? 0 : -12 }}
      animate={{ opacity: 1, x: 0 }}
      transition={{ ...morph, delay: reduceMotion ? 0 : 0.05 }}
    >
      {doc && onJump && <EvidenceSpine doc={doc} findings={findings} highlight={highlight} onJump={onJump} />}
      <header className={styles.docHeader}>
        <div className={styles.docKicker}>Contract</div>
        <div className={styles.docTitle}>{doc?.name}</div>
        <div className={styles.docMeta}>
          {docMeta} · Uploaded {doc ? formatWhen(doc.createdAt) : ""}
        </div>
        {doc && notRead(doc).length > 0 && (
          <p className={styles.docNote} data-testid="coverage-note">
            Not read by this reading: {notRead(doc).join(", ")}. Citations come only from what was read.
            {doc.coverage?.source === "reconstructed" ? " (Described from the stored file; this reading did not record it at the time.)" : ""}
          </p>
        )}
        {doc && doc.sections.length > 0 && doc.sections.filter((s) => s.number).length < 3 && (
          <p className={styles.docNotice}>
            Little structure was found in this file&apos;s text, so sections are approximate. Citations are still verified against the text itself.
          </p>
        )}
      </header>
      <article className={styles.paper}>
        {doc?.sections.map((section) => (
          <SectionBlock key={section.id} section={section} lit={lit === section.id} span={highlight?.sectionId === section.id ? highlight.span : null} />
        ))}
        {isSample && <p className={styles.paperNote}>Sample · Common Paper Cloud Service Agreement · CC BY 4.0 · a real standard agreement, unmodified</p>}
      </article>
    </motion.div>
  );
}

function SectionBlock({ section, lit, span }: { section: SectionView; lit: boolean; span: SpanView | null }) {
  // Offsets are code points (the API's), so the slice is by code points too (src/lib/text.ts).
  const located =
    span && span.verified && span.start >= 0 && span.end <= codePointLength(section.text) ? splitByCodePoints(section.text, span.start, span.end) : null;
  const body = located ? (
    <>
      {located[0]}
      <mark className={styles.passage}>{located[1]}</mark>
      {located[2]}
    </>
  ) : (
    section.text
  );
  return (
    <section data-section={section.id} className={`${styles.clause} ${lit ? styles.clauseLit : ""}`}>
      {section.number ? (
        <h3 className={styles.clauseTitle}>
          <span className={styles.clauseNumber}>{section.number}</span> {section.heading}
        </h3>
      ) : (
        <h2 className={styles.docHeading}>{section.heading}</h2>
      )}
      {section.text && <p className={styles.clauseBody}>{body}</p>}
    </section>
  );
}
