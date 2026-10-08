"use client";

import { useEffect, useMemo, useState } from "react";
import wb from "../Workbench.module.css";
import styles from "./Views.module.css";
import { StatusChip } from "../shell/primitives";
import { Figures } from "./Figures";
import { ListSkeleton, ReadFailed } from "./Skeleton";
import { errorMessage, isConflict, listFindings, reviewFinding } from "@/lib/api";
import { formatWhen, plural } from "@/lib/format";
import { rememberReviewer, rememberedReviewer } from "@/lib/reviewer";
import { type FindingRecord, type FindingStatus, type ReviewVerdict } from "@/lib/types";

/** What the figures at the top can narrow the list to. */
type Filter = "all" | "needs_review" | "pass" | "missing" | "awaiting";

function keep(filter: Filter, r: FindingRecord): boolean {
  if (filter === "all") return true;
  if (filter === "awaiting") return !r.review;
  return r.status === filter;
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
  const [filter, setFilter] = useState<Filter>("all");
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    let cancelled = false;
    listFindings()
      .then((rows) => !cancelled && setRecords(rows))
      .catch((e: unknown) => !cancelled && setError(errorMessage(e)));
    return () => {
      cancelled = true;
    };
  }, [attempt]);

  // Grouped by document, newest run first, in the order the API returned them.
  const groups = useMemo(() => {
    const byDocument = new Map<string, { name: string; items: FindingRecord[] }>();
    for (const r of (records ?? []).filter((row) => keep(filter, row))) {
      const group = byDocument.get(r.documentId) ?? {
        name: r.documentName,
        items: [],
      };
      group.items.push(r);
      byDocument.set(r.documentId, group);
    }
    return [...byDocument.entries()];
  }, [records, filter]);

  const reviewed = (records ?? []).filter((r) => r.review).length;
  const awaiting = (records ?? []).length - reviewed;
  const count = (status: FindingStatus) => (records ?? []).filter((r) => r.status === status).length;
  const toggle = (next: Filter) => setFilter((current) => (current === next ? "all" : next));

  const decide = async (record: FindingRecord, verdict: ReviewVerdict, name?: string) => {
    const reviewer = name ?? rememberedReviewer();
    if (!reviewer) {
      if (verdict !== "cleared") setPending({ id: record.id, verdict });
      return;
    }
    setBusyId(record.id);
    setError(null);
    try {
      // Decided against the review state this row shows; one recorded since, in another tab or by another person, refuses it.
      const out = await reviewFinding(record.id, { verdict, reviewer, note: null, basedOn: record.latestReviewId });
      setRecords((rows) => rows?.map((r) => (r.id === record.id ? { ...r, review: out.review ?? null, latestReviewId: out.latestReviewId } : r)) ?? rows);
    } catch (e) {
      setError(errorMessage(e));
      if (isConflict(e)) {
        // Show the decision that was recorded instead: the list is read again.
        setPending(null);
        setAttempt((n) => n + 1);
      }
    } finally {
      setBusyId(null);
    }
  };

  return (
    <div className={styles.pane}>
      <div className={styles.inner}>
        <div className={styles.kicker}>Findings</div>
        <h1 className={styles.title}>
          Findings and their passages
          {records && <span className={styles.count}>{records.length}</span>}
        </h1>
        <p className={styles.lede}>
          Every finding here cites contract text that code found in the document: word for word, or differing only in spacing, case, punctuation, how a number
          is written, or the section&rsquo;s own number and heading at the quote&rsquo;s start. Open one to see the passage marked in its document and how it
          was matched. Where a point was not found, the citations marked <em>searched</em> are the closest provisions that were read, not support for a claim.
          {records && records.length > 0 && ` ${plural(awaiting, "finding")} awaiting review · ${reviewed} reviewed.`}
        </p>
        {records && records.length > 0 && (
          <Figures
            label="Filter the findings"
            items={[
              { label: "Needs review", value: count("needs_review"), onSelect: () => toggle("needs_review"), active: filter === "needs_review" },
              { label: "Within guidance or answered", value: count("pass"), onSelect: () => toggle("pass"), active: filter === "pass" },
              { label: "Not found", value: count("missing"), onSelect: () => toggle("missing"), active: filter === "missing" },
              { label: "Awaiting a person", value: awaiting, onSelect: () => toggle("awaiting"), active: filter === "awaiting" },
            ]}
          />
        )}
        {notice && <p className={styles.notice}>{notice}</p>}
        {error && !records && (
          <ReadFailed
            what="the findings"
            error={error}
            onRetry={() => {
              setError(null);
              setAttempt((n) => n + 1);
            }}
          />
        )}
        {error && records && <p className={styles.notice}>{error}</p>}
        {!records && !error && <ListSkeleton rows={6} label="Findings" />}

        {records && records.length === 0 && (
          <div className={styles.empty}>
            <p>No findings yet. Open a contract and ask it a question.</p>
          </div>
        )}
        {records && records.length > 0 && groups.length === 0 && (
          <div className={styles.empty}>
            <p>Nothing matches this filter.</p>
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
            <div className={styles.groupTitle}>
              <span>{group.name}</span>
              <small>{plural(group.items.length, "finding")}</small>
            </div>
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
                          className={`${styles.tag} ${r.evidenceKind === "coverage" ? styles.tagSearched : ""}`}
                          title={
                            r.evidenceKind === "coverage"
                              ? `${c}: read while searching; in the model's view it does not state the point`
                              : `${c}: a passage found in the document text`
                          }
                        >
                          {r.evidenceKind === "coverage" ? `searched ${c}` : c}
                        </span>
                      ))}
                      {r.citations.length === 0 && <span className={styles.tag}>{plural(r.verifiedSpans, "passage")}</span>}
                    </div>
                    <div className={styles.rowSide}>
                      <StatusChip status={r.status} hasGuidance={r.hasGuidance} source={r.statusSource} />
                      <span>{formatWhen(r.createdAt)}</span>
                    </div>
                  </button>
                  <div className={styles.reviewBar}>
                    {r.shared ? (
                      <>
                        {r.review && (
                          <span className={`${wb.statusChip} ${r.review.verdict === "confirmed" ? wb.statusPass : wb.statusMuted}`}>
                            {r.review.verdict === "confirmed" ? "Confirmed" : "Dismissed"}
                          </span>
                        )}
                        <span>{r.review ? `by ${r.review.reviewer} · ` : ""}curated record, kept as recorded</span>
                      </>
                    ) : r.review ? (
                      <>
                        <span className={`${wb.statusChip} ${r.review.verdict === "confirmed" ? wb.statusPass : wb.statusMuted}`}>
                          {r.review.verdict === "confirmed" ? "Confirmed" : "Dismissed"}
                        </span>
                        <span>
                          by {r.review.reviewer} · {formatWhen(r.review.at)}
                          {r.review.note ? ` · ${r.review.note}` : ""}
                        </span>
                        <button
                          type="button"
                          className={styles.reviewButton}
                          disabled={busyId === r.id}
                          onClick={() => void decide(r, "cleared")}
                          aria-label={`Undo: ${r.topic}`}
                        >
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
                          aria-label="Your name, recorded with the decision"
                          maxLength={80}
                          required
                          ref={(element) => element?.focus()}
                        />
                        <button
                          type="submit"
                          className={styles.reviewButton}
                          aria-label={`${pending.verdict === "confirmed" ? "Confirm" : "Dismiss"}: ${r.topic}`}
                        >
                          {pending.verdict === "confirmed" ? "Confirm" : "Dismiss"}
                        </button>
                        <button type="button" className={styles.reviewButton} onClick={() => setPending(null)}>
                          Cancel
                        </button>
                      </form>
                    ) : (
                      <>
                        <span>Review</span>
                        <button
                          type="button"
                          className={styles.reviewButton}
                          disabled={busyId === r.id}
                          onClick={() => void decide(r, "confirmed")}
                          aria-label={`Confirm: ${r.topic}`}
                        >
                          Confirm
                        </button>
                        <button
                          type="button"
                          className={styles.reviewButton}
                          disabled={busyId === r.id}
                          onClick={() => void decide(r, "dismissed")}
                          aria-label={`Dismiss: ${r.topic}`}
                        >
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
