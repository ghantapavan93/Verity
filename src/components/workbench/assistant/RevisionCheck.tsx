"use client";

import { useEffect, useId, useRef, useState } from "react";
import styles from "./RevisionCheck.module.css";
import { StatusChip, Visible } from "../shell/primitives";
import { createGuidance, createRun, errorMessage, followRun, getRunTrustDiff, recordSupersedes, uploadDocument } from "@/lib/api";
import { statusLabel } from "@/lib/types";
import type { FindingView, RelationView, RunView, TrustDiffView, TrustFindingChange } from "@/lib/types";
import { statementLine } from "./RelationNotes";

/** A revision prepared for the bundled sample, so the comparison can be tried without a file of one's own. It is a real
 * file, read, diffed and asked about like any other; the one change in it is ours, and the panel says so. */
export interface PreparedRevision {
  path: string;
  fileName: string;
  change: string;
}

export const SAMPLE_REVISION: PreparedRevision = {
  path: "/samples/cloud-service-agreement-revised.docx",
  fileName: "Cloud Service Agreement (Common Paper), revised.docx",
  change: "one change by Verity to Common Paper's agreement (CC BY 4.0): the cure period in §5.3(a), 30 days → 10 days",
};

type Again = { name: "idle" } | { name: "asking"; stage: string } | { name: "answered"; after: RunView } | { name: "failed"; message: string };

const STAGE_WORDS: Record<string, string> = {
  reading: "Reading the revision",
  finding_evidence: "Finding the sections",
  checking: "The model is answering",
  verifying: "Checking the quotes",
};

function FindingSummary({ finding, hasGuidance }: { finding: FindingView; hasGuidance: boolean }) {
  const quoted = finding.spans.find((span) => span.verified);
  return (
    <div className={styles.summaryCard}>
      <div className={styles.summaryHead}>
        <span className={styles.summaryTopic}>
          <Visible text={finding.topic} />
        </span>
        <StatusChip status={finding.status} hasGuidance={hasGuidance} source={finding.statusSource} />
      </div>
      <p className={styles.summaryText}>
        <Visible text={finding.conclusion} />
      </p>
      <p className={styles.summaryWho}>
        {finding.decidedBy === "code" ? "Code set this status" : finding.decidedBy === "withheld" ? "Withheld: no quote found" : "The model's call"}
        {finding.statusReason ? `: ${finding.statusReason}` : ""}
      </p>
      {quoted && (
        <blockquote className={styles.summaryQuote}>
          <span className={styles.summaryCite}>{quoted.clauseLabel || quoted.sectionLabel}</span> <Visible text={quoted.quote} />
        </blockquote>
      )}
    </div>
  );
}

/**
 * The contract's own replacement and precedence statements each run recorded, where the revision changed them: a ranking
 * reordered, a replacement added or removed. A changed statement is a fact about the two texts; what it does to the answer
 * is in the two answers above, each its own run.
 */
function StatementsChanged({ before, after }: { before: RelationView[]; after: RelationView[] }) {
  const said = (relations: RelationView[]) => new Set(relations.map((r) => r.statement.text.replace(/\s+/g, " ").trim()));
  const was = said(before);
  const now = said(after);
  const gone = before.filter((r) => !now.has(r.statement.text.replace(/\s+/g, " ").trim()));
  const added = after.filter((r) => !was.has(r.statement.text.replace(/\s+/g, " ").trim()));
  if (gone.length === 0 && added.length === 0) return null;
  return (
    <div className={styles.statements} data-testid="statements-changed">
      <div className={styles.columnHead}>The contract&apos;s own statements changed · located by code</div>
      <ul className={styles.why}>
        {gone.map((r) => (
          <li key={`was-${r.statement.start}`}>This version: {statementLine(r)}</li>
        ))}
        {added.map((r) => (
          <li key={`now-${r.statement.start}`}>The revision: {statementLine(r)}</li>
        ))}
      </ul>
    </div>
  );
}

/**
 * The same question asked of the revision: a new run on the revised file, with the same guidance, recorded like any other.
 * The two answers are shown side by side as recorded; neither changes the other, and which finding answers the same point
 * is the reader's to judge.
 */
function AskAgain({ run, revisedId }: { run: RunView; revisedId: string }) {
  const [again, setAgain] = useState<Again>({ name: "idle" });
  const stop = useRef<(() => void) | null>(null);
  useEffect(() => () => stop.current?.(), []);

  async function ask() {
    try {
      setAgain({ name: "asking", stage: "Starting the run" });
      const guidanceId = run.guidanceText ? (await createGuidance(run.guidanceText)).id : null;
      const started = await createRun({ documentId: revisedId, guidanceId, question: run.question });
      if (["complete", "unresolved", "failed"].includes(started.stage)) {
        setAgain({ name: "answered", after: started });
        return;
      }
      stop.current = followRun(
        started.id,
        (stage) => setAgain({ name: "asking", stage: STAGE_WORDS[stage] ?? "Working" }),
        (after) => setAgain({ name: "answered", after }),
        (message) => setAgain({ name: "failed", message }),
      );
    } catch (error) {
      setAgain({ name: "failed", message: errorMessage(error) });
    }
  }

  return (
    <div className={styles.again}>
      {again.name !== "answered" && (
        <button type="button" className={styles.button} onClick={() => void ask()} disabled={again.name === "asking"}>
          {again.name === "asking" ? `${again.stage}…` : "Ask the same question of the revision"}
        </button>
      )}
      {again.name === "failed" && (
        <p className={styles.error} role="alert">
          {again.message}
        </p>
      )}
      {again.name === "answered" && (
        <div className={styles.compare} aria-live="polite">
          <div className={styles.kicker}>The same question, both versions</div>
          {run.findings.length === 1 && again.after.findings.length === 1 && (
            <p className={styles.changeLine}>
              {statusLabel(run.findings[0].status, run.hasGuidance, run.findings[0].statusSource)}
              <span aria-hidden="true"> → </span>
              <span className={styles.visuallyHidden}> became </span>
              {statusLabel(again.after.findings[0].status, again.after.hasGuidance, again.after.findings[0].statusSource)}
              {again.after.findings[0].decidedBy === "code" ? ", set by code" : ", the model's call"}
            </p>
          )}
          <div className={styles.columns}>
            <div>
              <div className={styles.columnHead}>This version</div>
              {run.findings.map((finding) => (
                <FindingSummary key={finding.id} finding={finding} hasGuidance={run.hasGuidance} />
              ))}
            </div>
            <div>
              <div className={styles.columnHead}>The revision</div>
              {again.after.findings.length > 0 ? (
                again.after.findings.map((finding) => <FindingSummary key={finding.id} finding={finding} hasGuidance={again.after.hasGuidance} />)
              ) : (
                <p className={styles.summaryText}>{again.after.note ?? again.after.error ?? "The run ended without a finding."}</p>
              )}
            </div>
          </div>
          <StatementsChanged before={run.relations ?? []} after={again.after.relations ?? []} />
          <p className={styles.foot}>
            Two recorded runs, each answered by the model from its own version and checked by code; neither changes the other. Which finding answers the same
            point is your reading. <a href={`?document=${revisedId}&run=${again.after.id}`}>Open the revision&apos;s answer</a>
          </p>
        </div>
      )}
    </div>
  );
}

/**
 * "Has this contract been revised?" Under a finished run: the reader hands over the revised file, says by doing so
 * that it is the next version of the document this run read, and is shown what the revision does to each finding.
 *
 * Saying a file is the next version is permanent (a line of versions is never rewritten), so it is never said by picking
 * a file: the reader is asked, with the file's name and that it cannot be undone, before anything is recorded.
 *
 * It renders what the API decided and decides nothing. Which findings are stale, why, and which were not reached
 * are the API's answers (`/api/runs/{id}/trust/diff`); the run itself is never changed.
 */

// "Still supported" was shown for every finding the revision did not reach, a withheld one and one code had flagged among
// them: the trust state says only whether the quotes stand, never that the answer is supported (authority review H3,
// 2026-10-14). The verdict names what the revision did; the state names what it is.
const VERDICT_LABEL: Record<string, string> = { stale: "Stale", revalidated: "Established again", unchanged: "Not reached" };
const VERDICT_NOTE: Record<string, string> = {
  revalidated: "The section it cites was revised. Its quotes were found again and every check still holds.",
  unchanged: "The revision did not change the text its quotes stand on. Its status is as it was recorded.",
};
const STATE_LABEL: Record<string, string> = { supported: "quotes stand", needs_review: "quotes need review", unsupported: "quotes do not stand" };
const ORDER = ["stale", "revalidated", "unchanged"];

type Phase =
  | { name: "idle" }
  | { name: "working"; step: string }
  | { name: "confirm"; revisedId: string; fileName: string }
  | { name: "done"; diff: TrustDiffView; fileName: string; revisedId: string }
  | { name: "failed"; message: string };

function plural(count: number, one: string, many: string): string {
  return `${count} ${count === 1 ? one : many}`;
}

function FindingRow({ change }: { change: TrustFindingChange }) {
  const moved = change.before !== change.after;
  return (
    <li className={styles.finding} data-verdict={change.verdict}>
      <details open={change.verdict === "stale"}>
        <summary className={styles.summary}>
          <span className={styles.verdict} data-verdict={change.verdict}>
            {VERDICT_LABEL[change.verdict] ?? change.verdict}
          </span>
          <span className={styles.topic}>
            <Visible text={change.topic} />
          </span>
          <span className={styles.states}>
            {moved
              ? `${STATE_LABEL[change.before] ?? change.before} → ${STATE_LABEL[change.after] ?? change.after}`
              : (STATE_LABEL[change.after] ?? change.after)}
          </span>
        </summary>
        {change.why.length > 0 ? (
          <ul className={styles.why}>
            {change.why.map((sentence) => (
              <li key={sentence}>{sentence}</li>
            ))}
          </ul>
        ) : (
          <p className={styles.note}>{VERDICT_NOTE[change.verdict]}</p>
        )}
      </details>
    </li>
  );
}

export function RevisionCheck({
  runId,
  documentId,
  run = null,
  prepared = null,
}: {
  runId: string;
  documentId: string;
  /** The run the findings come from: its question and guidance are asked again of the revision. */
  run?: RunView | null;
  prepared?: PreparedRevision | null;
}) {
  const [phase, setPhase] = useState<Phase>({ name: "idle" });
  const input = useRef<HTMLInputElement>(null);
  const inputId = useId();

  async function read(file: File) {
    try {
      setPhase({ name: "working", step: "Reading the revised file" });
      const revised = await uploadDocument(file);
      if (revised.id === documentId) {
        setPhase({ name: "failed", message: "That file is the document this run already read. Nothing has been revised." });
        return;
      }
      setPhase({ name: "confirm", revisedId: revised.id, fileName: file.name });
    } catch (error) {
      setPhase({ name: "failed", message: errorMessage(error) });
    }
  }

  async function readPrepared(revision: PreparedRevision) {
    try {
      setPhase({ name: "working", step: "Fetching the prepared revision" });
      // eslint-disable-next-line no-restricted-globals -- the prepared revision is a static file of this origin, not the API
      const response = await fetch(revision.path);
      if (!response.ok) throw new Error("The prepared revision is missing from this build.");
      await read(new File([await response.blob()], revision.fileName, { type: "application/vnd.openxmlformats-officedocument.wordprocessingml.document" }));
    } catch (error) {
      setPhase({ name: "failed", message: errorMessage(error) });
    }
  }

  async function record(revisedId: string, fileName: string) {
    try {
      setPhase({ name: "working", step: "Recording it as the next version" });
      await recordSupersedes(revisedId, documentId);
      setPhase({ name: "working", step: "Checking each finding against it" });
      setPhase({ name: "done", diff: await getRunTrustDiff(runId, revisedId), fileName, revisedId });
    } catch (error) {
      setPhase({ name: "failed", message: errorMessage(error) });
    }
  }

  const busy = phase.name === "working";
  return (
    <section className={styles.panel} aria-label="Revised version" data-testid="revision-check">
      <div className={styles.head}>
        <div>
          <div className={styles.kicker}>Revised version</div>
          <p className={styles.lede}>
            Has this contract changed since these findings were made? Check the new file against them. The findings are not rerun or replaced.
          </p>
        </div>
        <input
          id={inputId}
          ref={input}
          type="file"
          accept=".docx,.pdf,.txt"
          className={styles.file}
          aria-label="Revised contract file"
          // The button below opens it. Reached by Tab, this clipped one-pixel input took focus with nothing to show for
          // it and scrolled the answer pane 434 px, out of reach until a reload (war-room UX-01, 2026-10-13); hidden from
          // assistive technology too, so a screen reader meets one control, the button, not two.
          tabIndex={-1}
          aria-hidden="true"
          onChange={(event) => {
            const file = event.target.files?.[0];
            event.target.value = "";
            if (file) void read(file);
          }}
        />
        <div className={styles.actions}>
          {prepared && phase.name === "idle" && (
            <button type="button" className={styles.quiet} onClick={() => void readPrepared(prepared)}>
              Use a prepared revision
            </button>
          )}
          <button type="button" className={styles.button} onClick={() => input.current?.click()} disabled={busy || phase.name === "confirm"}>
            {busy ? phase.step : phase.name === "done" ? "Check another revision" : "Check a revised version"}
          </button>
        </div>
      </div>
      {prepared && phase.name === "idle" && <p className={styles.preparedNote}>The prepared revision makes {prepared.change}.</p>}

      {phase.name === "confirm" && (
        <div className={styles.confirm} role="group" aria-label="Confirm the next version">
          <p className={styles.confirmText}>
            Record <strong>{phase.fileName}</strong> as the next version of the contract this run read? This cannot be undone: a document keeps its place in a
            line of versions. Only record a file that is a revision of this same agreement.
          </p>
          <div className={styles.confirmActions}>
            <button type="button" className={styles.button} onClick={() => void record(phase.revisedId, phase.fileName)}>
              Record as the next version
            </button>
            <button type="button" className={styles.quiet} onClick={() => setPhase({ name: "idle" })}>
              Cancel
            </button>
          </div>
        </div>
      )}

      {phase.name === "failed" && (
        <p className={styles.error} role="alert">
          {phase.message}
        </p>
      )}

      {phase.name === "done" && (
        <div className={styles.result} aria-live="polite">
          <p className={styles.headline}>
            <strong>{plural(phase.diff.counts.stale ?? 0, "finding is", "findings are")} stale.</strong>{" "}
            {plural(phase.diff.counts.revalidated ?? 0, "was", "were")} established again. {plural(phase.diff.counts.unchanged ?? 0, "was", "were")} not reached
            by the revision.
          </p>
          <p className={styles.meta}>
            <span>{phase.fileName}</span>
            {phase.diff.sections.changed.length > 0 && <span>changed: {phase.diff.sections.changed.join(", ")}</span>}
            {phase.diff.sections.added.length > 0 && <span>added: {phase.diff.sections.added.join(", ")}</span>}
            {phase.diff.sections.removed.length > 0 && <span>removed: {phase.diff.sections.removed.join(", ")}</span>}
            <span>
              {phase.diff.sectionsSearched} of {plural(phase.diff.sectionsTotal, "section", "sections")} searched again
            </span>
            <span>{phase.diff.sectionsReused} carried over unchanged, with the counts they had</span>
          </p>
          <ul className={styles.findings}>
            {[...phase.diff.findings]
              .sort((a, b) => ORDER.indexOf(a.verdict) - ORDER.indexOf(b.verdict) || a.ordinal - b.ordinal)
              .map((change) => (
                <FindingRow key={change.findingId} change={change} />
              ))}
          </ul>
          <p className={styles.foot}>
            A stale finding is not wrong. It is no longer shown to be supported by the revised text, and should be asked again of the new version.
          </p>
          {run && <AskAgain run={run} revisedId={phase.revisedId} />}
        </div>
      )}
    </section>
  );
}
