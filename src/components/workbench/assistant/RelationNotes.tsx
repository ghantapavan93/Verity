"use client";

import styles from "../Workbench.module.css";
import { NARROW_QUERY } from "../shell/constants";
import { Visible } from "../shell/primitives";
import { aroundChanges, wordContrast, type DiffPiece } from "@/lib/diff";
import { passageSpan, type PassageView, type RelationNoteView, type RelationView, type SpanView } from "@/lib/types";

/**
 * The contract's own replacement and precedence statements (runs.relations, policy-v11), each with the passages it
 * joins. Every end is a passage code located in this document, and opens it. Nothing here says which wording governs.
 */

function excerpt(text: string, max = 150): string {
  const flat = text.replace(/\s+/g, " ").trim();
  return flat.length > max ? `${flat.slice(0, max - 1).trimEnd()}…` : flat;
}

type Side = "original" | "replacement" | null;

/** The passages a relation joins, in the order a reader checks them, and which side of a replacement each is. */
export function relationEnds(relation: RelationView): { role: string; passage: PassageView; side: Side }[] {
  if (relation.kind === "precedence") return [{ role: "Order of precedence", passage: relation.statement, side: null }];
  const ends: { role: string; passage: PassageView; side: Side }[] = [];
  if (relation.replaced) ends.push({ role: `Original clause ${relation.target ?? ""}`.trim(), passage: relation.replaced, side: "original" });
  ends.push(
    relation.replacement
      ? { role: "Replacement", passage: relation.replacement, side: "replacement" }
      : { role: "Replacing statement", passage: relation.statement, side: null },
  );
  return ends;
}

function Pieces({ pieces }: { pieces: readonly DiffPiece[] }) {
  return (
    <>
      {pieces.map((piece, i) =>
        piece.changed ? (
          <mark key={i} className={styles.changed}>
            <Visible text={piece.text} />
          </mark>
        ) : (
          <Visible key={i} text={piece.text} />
        ),
      )}
    </>
  );
}

/** What the contract states, and nothing about any answer. */
export function statementLine(relation: RelationView): string {
  const by = relation.statement.label;
  if (relation.kind === "precedence") return `${by} ranks ${relation.parts.join(", ")} for a conflict.`;
  const since = relation.effective ? `, in effect from ${relation.effective.split(",")[0]}` : "";
  return relation.scope
    ? `${by} changes clause ${relation.target} only within a stated limit (${relation.scope}).`
    : `${by} ${relation.replacement ? "replaces" : "deletes or replaces"} clause ${relation.target} in full${since}.`;
}

/** What the statement means for the answer, in one line, from the effect code recorded (the drawer has code's sentence). */
export function relationSummary(note: RelationNoteView): string {
  const line = statementLine(note.relation);
  switch (note.effect) {
    case "replaced":
      return `${line} The answer quotes the replaced wording, and neither quotes the replacement nor states a value only it states. Which wording governs is not decided by code.`;
    case "scoped":
      return `${line} Whether the limit applies here is not settled by code.`;
    case "dated":
      return `${line} The question names a time; which wording applied then is not settled by code.`;
    case "old_value":
      return `${line} The answer quotes the replacement but states only values of the replaced wording.`;
    case "precedence":
      return `${line} The quoted passages come from parts it ranks; which applies here is not settled by code.`;
    default:
      return `${line} Context only: code raised no concern from it.`;
  }
}

function RelationRow({
  line,
  relation,
  full,
  onJump,
  onEvidence,
  effect,
}: {
  line: string;
  relation: RelationView;
  full: boolean;
  /** Absent where the contract text is hidden (the evidence sheet on a phone): each end is then shown, not offered. */
  onJump?: (sectionId: string, span: SpanView | null) => void;
  onEvidence?: (trigger: HTMLElement | null) => void;
  effect: RelationNoteView["effect"] | "stated";
}) {
  // Where the statement gives both the clause and its new wording, the words they differ in are marked, and the card
  // shows each end around them: a replacement usually keeps the clause's opening, so the first 150 characters of each
  // were the same words, cut before the change. The sheet shows both in full, qualifications included.
  const contrast = relation.replaced && relation.replacement ? wordContrast(relation.replaced.text, relation.replacement.text) : null;
  return (
    <div className={styles.relation} data-effect={effect}>
      <p className={styles.valueNote}>
        <span className={styles.checkBy} aria-hidden="true">
          code
        </span>
        <span className={styles.visuallyHidden}>Located by code: </span>
        {line}
      </p>
      {contrast && <p className={styles.contrastNote}>Marked: the words in which the original and the replacement differ.</p>}
      {relationEnds(relation).map(({ role, passage, side }) => {
        const pieces = contrast && side ? contrast[side] : null;
        const content = (
          <>
            <span className={styles.citationLabel}>
              {role} · {passage.label}
            </span>
            <span className={styles.citationExcerpt}>
              {pieces ? <Pieces pieces={full ? pieces : aroundChanges(pieces)} /> : <Visible text={full ? passage.text : excerpt(passage.text)} />}
            </span>
          </>
        );
        if (!onJump) {
          return (
            <div key={role} className={`${styles.citationRow} ${styles.citationStatic}`}>
              {content}
            </div>
          );
        }
        return (
          <button
            key={role}
            type="button"
            className={styles.citationRow}
            // As a quote does: on a phone the paper is hidden, so the evidence sheet opens instead (FindingCard).
            onClick={(e) =>
              onEvidence && window.matchMedia(NARROW_QUERY).matches ? onEvidence(e.currentTarget) : onJump(passage.sectionId, passageSpan(passage))
            }
            title="Show in the document"
          >
            {content}
          </button>
        );
      })}
    </div>
  );
}

/** What the statements mean for one answer: one line on the card, code's whole sentence in the evidence drawer. */
export function RelationNotes({
  notes,
  full = false,
  onJump,
  onEvidence,
}: {
  notes: RelationNoteView[];
  full?: boolean;
  onJump?: (sectionId: string, span: SpanView | null) => void;
  onEvidence?: (trigger: HTMLElement | null) => void;
}) {
  if (notes.length === 0) return null;
  return (
    <div className={styles.relations} data-testid="relations">
      {notes.map((note, i) => (
        <RelationRow
          key={i}
          line={full ? note.sentence : relationSummary(note)}
          relation={note.relation}
          effect={note.effect}
          full={full}
          onJump={onJump}
          onEvidence={onEvidence}
        />
      ))}
    </div>
  );
}

/** A relation's identity across the run's list and an answer's notes: its statement's place. */
export function relationKey(relation: RelationView): string {
  return `${relation.kind}:${relation.statement.sectionId}:${relation.statement.start}`;
}

/**
 * The run's located statements no shown answer accounts for. A withheld answer (its quote was not found) grounds no
 * effect, and a failed run has none, but the statement is still a fact about the sections chosen for the question (the first-visitor acceptance test: the renewal
 * answer was withheld, and the amendment that replaced its clause was on no screen).
 */
export function UnclaimedRelations({
  relations,
  claimed,
  onJump,
}: {
  relations: RelationView[];
  claimed: Set<string>;
  onJump: (sectionId: string, span: SpanView | null) => void;
}) {
  const open = relations.filter((r) => !claimed.has(relationKey(r)));
  if (open.length === 0) return null;
  return (
    <section className={styles.relationsRun} aria-label="The contract's own statements in the sections chosen for this question" data-testid="run-relations">
      <div className={styles.evidenceHead}>The contract&apos;s own statements in the sections chosen for this question · located by code</div>
      <div className={styles.relations}>
        {open.map((relation) => (
          <RelationRow key={relationKey(relation)} line={statementLine(relation)} relation={relation} effect="stated" full={false} onJump={onJump} />
        ))}
      </div>
    </section>
  );
}
