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

// Clearing asks for a name too when none is remembered (it used to return silently, m7 audit 2026-10-10).
const VERB: Record<ReviewVerdict, string> = { confirmed: "Confirm", dismissed: "Dismiss", cleared: "Clear" };

/**
 * Findings across runs, grouped by document. Model proposes, code verifies, a person adjudicates:
 * each row carries the person's decision as the API recorded it, and the controls to record one.
 */
/**
 * What needs a person first, within each document: undecided needs review, then other undecided answers, then decided
 * ones (a needs-review finding someone decided has had its person). Documents keep the API's order, newest run first,
 * and a stable sort keeps it inside each rank. Read once, when the list loads: a row decided here stays where it is,
 * under the reader's hand, until the list is read again (a live re-sort moved it away from the click).
 */
export function forAttention(rows: FindingRecord[]): FindingRecord[] {
  const documents = new Map<string, number>();
  for (const r of rows) if (!documents.has(r.documentId)) documents.set(r.documentId, documents.size);
  const rank = (r: FindingRecord) => (r.review ? 2 : r.status === "needs_review" ? 0 : 1);
  return [...rows].sort((a, b) => (documents.get(a.documentId) ?? 0) - (documents.get(b.documentId) ?? 0) || rank(a) - rank(b));
}

/** A list read again while it is shown keeps its rows where they are: a refused decision reads it again, and the row the
 *  reader just clicked must not move. Rows it did not show go after them, in attention order. */
function inShownOrder(rows: FindingRecord[], shown: FindingRecord[]): FindingRecord[] {
  const at = new Map(shown.map((r, i) => [r.id, i]));
  const known = rows.filter((r) => at.has(r.id)).sort((a, b) => (at.get(a.id) ?? 0) - (at.get(b.id) ?? 0));
  return [...known, ...forAttention(rows.filter((r) => !at.has(r.id)))];
}

export function FindingsView({
  notice,
  onOpen,
  onStart,
}: {
  notice: string | null;
  onOpen: (record: FindingRecord) => void;
  /** Opens the amended sample: the empty list's next step. */
  onStart?: () => void;
}) {
  const [records, setRecords] = useState<FindingRecord[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [pending, setPending] = useState<{ id: string; verdict: ReviewVerdict } | null>(null);
  const [filter, setFilter] = useState<Filter>("all");
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    let cancelled = false;
    listFindings()
      .then((rows) => !cancelled && setRecords((shown) => (shown ? inShownOrder(rows, shown) : forAttention(rows))))
      .catch((e: unknown) => !cancelled && setError(errorMessage(e)));
    return () => {
      cancelled = true;
    };
  }, [attempt]);

  // Grouped by document, newest run first, in the order forAttention left them.
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
      setPending({ id: record.id, verdict });
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
          Every finding cites text code found in the contract. Found is not right: open one, read the passage, decide.
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
            <p>No findings yet. A finding is one answer to a question about a contract, with the passages it cites.</p>
            {onStart && (
              <button type="button" className={wb.ghostButton} onClick={onStart}>
                Try the amendment challenge
              </button>
            )}
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
                  {r.flagged && r.concerns.length > 0 && (
                    // What code raised, or the model asked, said before anyone decides: until 2026-10-14 a finding could be
                    // confirmed from this list without its concerns ever showing (authority review).
                    <div className={styles.concerns} id={`concerns-${r.id}`}>
                      <span className={styles.concernsLabel}>Flagged</span>
                      <ul>
                        {r.concerns.map((concern) => (
                          <li key={concern}>{concern}</li>
                        ))}
                      </ul>
                    </div>
                  )}
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
                        <button type="submit" className={styles.reviewButton} aria-label={`${VERB[pending.verdict]}: ${r.topic}`}>
                          {VERB[pending.verdict]}
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
                          aria-describedby={r.flagged && r.concerns.length > 0 ? `concerns-${r.id}` : undefined}
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
