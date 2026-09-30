"use client";

import { useEffect, useMemo, useState } from "react";
import wb from "../Workbench.module.css";
import styles from "./Views.module.css";
import { errorMessage, listFindings, reviewFinding } from "@/lib/api";
import { formatWhen, plural } from "@/lib/format";
import { statusLabel, type FindingRecord, type FindingStatus, type ReviewVerdict } from "@/lib/types";

export function statusTone(status: FindingStatus): string {
  return status === "needs_review" ? wb.statusReview : status === "pass" ? wb.statusPass : wb.statusMuted;
}

// The reviewer's name is a per-browser convenience, typed once; the decision itself is a record on the API.
const REVIEWER_KEY = "workbench.reviewer";

function rememberedReviewer(): string {
  try {
    return window.localStorage.getItem(REVIEWER_KEY) ?? "";
  } catch {
    return "";
  }
}

function rememberReviewer(name: string): void {
  try {
    window.localStorage.setItem(REVIEWER_KEY, name);
  } catch {
    // Storage may be unavailable; the review is still recorded by the API.
  }
}

type Decision = Exclude<ReviewVerdict, "cleared">;

/**
 * Findings across runs, grouped by document. Model proposes, code verifies, a person adjudicates:
 * each row carries the person's decision as the API recorded it, and the controls to record one.
 */
export function FindingsView({ notice, onOpen }: { notice: string | null; onOpen: (record: FindingRecord) => void }) {
  const [records, setRecords] = useState<FindingRecord[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [pending, setPending] = useState<{ id: string; verdict: Decision } | null>(null);

  useEffect(() => {
    let cancelled = false;
    listFindings()
      .then((rows) => !cancelled && setRecords(rows))
      .catch((e: unknown) => !cancelled && setError(errorMessage(e)));
    return () => {
      cancelled = true;
    };
  }, []);

  // Grouped by document, newest run first, in the order the API returned them.
  const groups = useMemo(() => {
    const byDocument = new Map<string, { name: string; items: FindingRecord[] }>();
    for (const r of records ?? []) {
      const group = byDocument.get(r.documentId) ?? {
        name: r.documentName,
        items: [],
      };
      group.items.push(r);
      byDocument.set(r.documentId, group);
    }
    return [...byDocument.entries()];
  }, [records]);

  const reviewed = (records ?? []).filter((r) => r.review).length;
  const awaiting = (records ?? []).length - reviewed;

  const decide = async (record: FindingRecord, verdict: ReviewVerdict, name?: string) => {
    const reviewer = name ?? rememberedReviewer();
    if (!reviewer) {
      if (verdict !== "cleared") setPending({ id: record.id, verdict });
      return;
    }
    setBusyId(record.id);
    setError(null);
    try {
      const out = await reviewFinding(record.id, { verdict, reviewer, note: null });
      setRecords((rows) => rows?.map((r) => (r.id === record.id ? { ...r, review: out.review ?? null } : r)) ?? rows);
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusyId(null);
    }
  };

  return (
    <div className={styles.pane}>
      <div className={styles.inner}>
        <div className={styles.kicker}>Findings</div>
        <h1 className={styles.title}>
          Findings with verified evidence
          {records && <span className={styles.count}>{records.length}</span>}
        </h1>
        <p className={styles.lede}>
          Every finding here cites contract text that code verified verbatim. Open one to see the exact passage highlighted in its document. Where a point was
          not found, the citations marked <em>searched</em> are the closest provisions that were read, not support for a claim.
          {records && records.length > 0 && ` ${plural(awaiting, "finding")} awaiting review · ${reviewed} reviewed.`}
        </p>
        {(notice || error) && <p className={styles.notice}>{notice ?? error}</p>}

        {records && records.length === 0 && (
          <div className={styles.empty}>
            <p>No findings yet. Ask a question about a contract in the Assistant.</p>
          </div>
        )}

        {groups.length > 0 && (
          <div className={styles.tableHead} aria-hidden="true">
            <span>Topic</span>
            <span>Finding</span>
            <span>Evidence</span>
            <span>Status</span>
          </div>
        )}
        {groups.map(([documentId, group]) => (
          <section key={documentId} className={styles.group}>
            <div className={styles.groupTitle}>{group.name}</div>
            <ul className={styles.list} style={{ marginTop: 0 }}>
              {group.items.map((r) => (
                <li key={r.id} className={styles.findingItem}>
                  <button type="button" className={`${styles.row} ${styles.findingRow}`} onClick={() => onOpen(r)}>
                    <div className={styles.rowMain}>
                      <div className={styles.rowTitle}>{r.topic}</div>
                      <div className={styles.rowMeta}>
                        <span title={r.question}>Asked: {r.question}</span>
                      </div>
                    </div>
                    <p className={styles.cellText}>{r.conclusion}</p>
                    <div className={styles.cellEvidence}>
                      {r.citations.map((c) => (
                        <span
                          key={c}
                          className={styles.tag}
                          title={r.evidenceKind === "coverage" ? "Read while searching; does not state the point" : "Verified passage"}
                        >
                          {r.evidenceKind === "coverage" ? `searched ${c}` : c}
                        </span>
                      ))}
                      {r.citations.length === 0 && <span className={styles.tag}>{plural(r.verifiedSpans, "passage")}</span>}
                    </div>
                    <div className={styles.rowSide}>
                      <span className={`${wb.statusChip} ${statusTone(r.status)}`}>{statusLabel(r.status, r.hasGuidance)}</span>
                      <span>{formatWhen(r.createdAt)}</span>
                    </div>
                  </button>
                  <div className={styles.reviewBar}>
                    {r.review ? (
                      <>
                        <span className={`${wb.statusChip} ${r.review.verdict === "confirmed" ? wb.statusPass : wb.statusMuted}`}>
                          {r.review.verdict === "confirmed" ? "Confirmed" : "Dismissed"}
                        </span>
                        <span>
                          by {r.review.reviewer} · {formatWhen(r.review.at)}
                          {r.review.note ? ` · ${r.review.note}` : ""}
                        </span>
                        <button type="button" className={styles.reviewButton} disabled={busyId === r.id} onClick={() => void decide(r, "cleared")}>
                          Undo
                        </button>
                      </>
                    ) : pending?.id === r.id ? (
                      <form
                        className={styles.reviewForm}
                        onSubmit={(event) => {
                          event.preventDefault();
                          const name = String(new FormData(event.currentTarget).get("reviewer") ?? "").trim();
                          if (!name) return;
                          rememberReviewer(name);
                          setPending(null);
                          void decide(r, pending.verdict, name);
                        }}
                      >
                        <input
                          name="reviewer"
                          className={styles.reviewInput}
                          placeholder="Your name, asked once"
                          maxLength={80}
                          required
                          ref={(element) => element?.focus()}
                        />
                        <button type="submit" className={styles.reviewButton}>
                          {pending.verdict === "confirmed" ? "Confirm" : "Dismiss"}
                        </button>
                        <button type="button" className={styles.reviewButton} onClick={() => setPending(null)}>
                          Cancel
                        </button>
                      </form>
                    ) : (
                      <>
                        <span>Review</span>
                        <button type="button" className={styles.reviewButton} disabled={busyId === r.id} onClick={() => void decide(r, "confirmed")}>
                          Confirm
                        </button>
                        <button type="button" className={styles.reviewButton} disabled={busyId === r.id} onClick={() => void decide(r, "dismissed")}>
                          Dismiss
                        </button>
                      </>
                    )}
                  </div>
                </li>
              ))}
            </ul>
          </section>
        ))}
      </div>
    </div>
  );
}
