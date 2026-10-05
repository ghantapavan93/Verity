"use client";

import { useId, useRef, useState } from "react";
import styles from "./RevisionCheck.module.css";
import { errorMessage, getRunTrustDiff, recordSupersedes, uploadDocument } from "@/lib/api";
import type { TrustDiffView, TrustFindingChange } from "@/lib/types";

/**
 * "Has this contract been revised?" Under a finished run: the reader hands over the revised file, says by doing so
 * that it is the next version of the document this run read, and is shown what the revision does to each finding.
 *
 * It renders what the API decided and decides nothing. Which findings are stale, why, and which were not reached
 * are the API's answers (`/api/runs/{id}/trust/diff`); the run itself is never changed.
 */

const VERDICT_LABEL: Record<string, string> = { stale: "Stale", revalidated: "Established again", unchanged: "Still supported" };
const VERDICT_NOTE: Record<string, string> = {
  revalidated: "The section it cites was revised. Its evidence was found again and every check still holds.",
  unchanged: "Its source evidence did not change.",
};
const STATE_LABEL: Record<string, string> = { supported: "supported", needs_review: "needs review", unsupported: "unsupported" };
const ORDER = ["stale", "revalidated", "unchanged"];

type Phase =
  { name: "idle" } | { name: "working"; step: string } | { name: "done"; diff: TrustDiffView; fileName: string } | { name: "failed"; message: string };

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
          <span className={styles.topic}>{change.topic}</span>
          {moved && (
            <span className={styles.states}>
              {STATE_LABEL[change.before] ?? change.before} → {STATE_LABEL[change.after] ?? change.after}
            </span>
          )}
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

export function RevisionCheck({ runId, documentId }: { runId: string; documentId: string }) {
  const [phase, setPhase] = useState<Phase>({ name: "idle" });
  const input = useRef<HTMLInputElement>(null);
  const inputId = useId();

  async function check(file: File) {
    try {
      setPhase({ name: "working", step: "Reading the revised file" });
      const revised = await uploadDocument(file);
      if (revised.id === documentId) {
        setPhase({ name: "failed", message: "That file is the document this run already read. Nothing has been revised." });
        return;
      }
      setPhase({ name: "working", step: "Recording it as the next version" });
      await recordSupersedes(revised.id, documentId);
      setPhase({ name: "working", step: "Checking each finding against it" });
      setPhase({ name: "done", diff: await getRunTrustDiff(runId, revised.id), fileName: file.name });
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
          onChange={(event) => {
            const file = event.target.files?.[0];
            event.target.value = "";
            if (file) void check(file);
          }}
        />
        <button type="button" className={styles.button} onClick={() => input.current?.click()} disabled={busy}>
          {busy ? phase.step : phase.name === "done" ? "Check another revision" : "Check a revised version"}
        </button>
      </div>

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
        </div>
      )}
    </section>
  );
}
