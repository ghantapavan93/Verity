"use client";

import { AnimatePresence, motion } from "framer-motion";
import { useState, type Ref } from "react";
import styles from "../Workbench.module.css";
import { useRunExplanation } from "../hooks/useRunExplanation";
import { IconCheck, IconClose } from "../icons";
import { EASE } from "../shell/constants";
import { StatusChip } from "../shell/primitives";
import { DayGauge, readComparison } from "./DayGauge";
import { WhyThisAnswer } from "./WhyThisAnswer";
import { absolute, errorMessage, reviewFinding } from "@/lib/api";
import { formatWhen } from "@/lib/format";
import { rememberReviewer, rememberedReviewer } from "@/lib/reviewer";
import {
  citationLabel,
  codeRole,
  decidedByCode,
  statusLabel,
  type FindingStatus,
  type FindingView,
  type ReviewVerdict,
  type ReviewView,
  type RunExplanationView,
  type RunView,
  type SectionView,
  type SpanView,
} from "@/lib/types";

/**
 * The glass panel beside a finding, read top-down in the order a stranger needs: what the model proposed,
 * what the source says, what code decided, what a person decided. Everything comes from the run's record
 * (the run itself and `GET /api/runs/{id}/explanation`); the drawer decides nothing. The machinery that
 * lets an engineer reproduce the run (labels, offsets, hashes, the pack) sits behind one toggle, "Prove it".
 */
export function EvidenceDrawer({
  finding,
  run,
  guidanceText,
  sectionsById,
  onJump,
  onClose,
  onReviewed,
  closeRef,
  reduceMotion,
}: {
  finding: FindingView | null;
  run: RunView | null;
  guidanceText: string | null;
  sectionsById: Map<string, SectionView>;
  onJump: (sectionId: string, span: SpanView | null) => void;
  onClose: () => void;
  onReviewed?: (findingId: string, review: ReviewView | null) => void;
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
            <div className={styles.drawerTitle}>
              <strong>Evidence</strong>
              <span>{finding.topic}</span>
            </div>
            <button ref={closeRef} type="button" className={styles.iconButton} aria-label="Close evidence" onClick={onClose}>
              <IconClose />
            </button>
          </header>
          <div className={styles.drawerBody}>
            <EvidenceBody
              finding={finding}
              run={run}
              guidance={run ? (run.guidanceText ?? null) : guidanceText}
              sectionsById={sectionsById}
              onJump={onJump}
              onReviewed={onReviewed}
            />
          </div>
        </motion.aside>
      )}
    </AnimatePresence>
  );
}

/** The model's proposal for this finding, correlated by ordinal in the explanation; null when the record cannot say. */
function proposalFor(explanation: RunExplanationView | null, findingId: string) {
  if (!explanation) return null;
  const ordinal = explanation.findings.find((f) => f.id === findingId)?.ordinal;
  if (ordinal === undefined) return null;
  return explanation.proposals.find((p) => p.ordinal === ordinal) ?? null;
}

function EvidenceBody({
  finding,
  run,
  guidance,
  sectionsById,
  onJump,
  onReviewed,
}: {
  finding: FindingView;
  run: RunView | null;
  guidance: string | null;
  sectionsById: Map<string, SectionView>;
  onJump: (sectionId: string, span: SpanView | null) => void;
  onReviewed?: (findingId: string, review: ReviewView | null) => void;
}) {
  const [prove, setProve] = useState(false);
  // Read once when the drawer opens: the first layer needs it, and "Prove it" renders the same read.
  const read = useRunExplanation(run ? run.id : null);
  const explanation = read?.explanation ?? null;
  const explained = explanation?.findings.find((f) => f.id === finding.id) ?? null;
  const proposal = proposalFor(explanation, finding.id);
  const hasGuidance = run?.hasGuidance ?? false;
  const verified = finding.spans.filter((s) => s.verified).length;
  const withheld = finding.spans.length - verified;
  // The model proposed this pass and code confirmed it: the layer says so, and does not say code decided.
  const confirmed = finding.statusSource === "confirmed_days";
  // The layer where the status on screen was set: the model's, when its hint stands; otherwise code's.
  const setByModel = finding.statusSource === "model_hint";
  const setTag = <span className={styles.layerTag}>{confirmed ? "Confirmed here" : "Status set here"}</span>;
  // The comparison code wrote, as a picture, when its sentence parses exactly (DayGauge.tsx).
  const comparison = readComparison(finding.statusReason);

  const relocated = explained?.sourceMatches.some((m) => m?.relocated) ?? false;
  const overruled = !setByModel && proposal !== null && proposal.statusHint !== finding.status;

  return (
    <>
      <DecisionStrip
        cells={[
          {
            who: "Model",
            what: proposal ? plainLabel(statusLabel(proposal.statusHint as FindingStatus, hasGuidance, "model_hint")) : "not rebuilt",
            tone: proposal ? toneOf(proposal.statusHint as FindingStatus) : "muted",
            note: proposal ? "its proposal" : undefined,
            struck: overruled,
          },
          {
            who: "Source",
            what: finding.spans.length ? `${verified} of ${finding.spans.length} found` : "nothing cited",
            tone: finding.spans.length && verified === finding.spans.length ? "pass" : finding.spans.length ? "review" : "muted",
            note: relocated ? "in another section" : finding.spans.length ? "where it was cited" : undefined,
          },
          {
            who: "Code",
            what: setByModel ? "did not decide" : plainLabel(statusLabel(finding.status, hasGuidance, finding.statusSource)),
            tone: setByModel ? "muted" : toneOf(finding.status),
            note: overruled ? "the day counts conflict" : confirmed ? "confirmed the model's call" : undefined,
            decisive: !setByModel,
          },
          {
            who: "Person",
            what: finding.review ? (finding.review.verdict === "confirmed" ? "confirmed" : "dismissed") : "not yet",
            tone: finding.review ? (finding.review.verdict === "confirmed" ? "pass" : "muted") : "muted",
            note: finding.review ? `by ${finding.review.reviewer}` : undefined,
          },
        ]}
      />
      <section className={`${styles.drawerSection} ${styles.layer} ${setByModel ? styles.layerSet : ""}`} data-testid="layer-model">
        <div className={styles.layerHead}>
          <h4>Model proposed</h4>
          {setByModel && setTag}
        </div>
        {!run ? (
          <p className={styles.drawerRefStatic}>No run on record for this finding.</p>
        ) : !read ? (
          <p className={styles.drawerRefStatic}>Reading the run&apos;s record</p>
        ) : read.problem ? (
          <p className={styles.drawerRefStatic}>The record could not be read: {read.problem}</p>
        ) : explanation?.proposalsProblem || !proposal ? (
          <p className={styles.drawerRefStatic}>{explanation?.proposalsProblem ?? "Model proposal not reconstructable for this run."}</p>
        ) : (
          <dl className={styles.drawerFacts}>
            <div>
              <dt>Its hint</dt>
              <dd>
                <StatusChip status={proposal.statusHint as FindingStatus} hasGuidance={hasGuidance} source="model_hint" />
              </dd>
            </div>
            {(proposal.observed || proposal.required) && (
              <div>
                <dt>In its words</dt>
                <dd>
                  <ModelWords observed={proposal.observed} required={proposal.required} />
                </dd>
              </div>
            )}
            <div>
              <dt>It cited</dt>
              <dd>
                {proposal.evidence.length} passage{proposal.evidence.length === 1 ? "" : "s"}
                {finding.spans.length > 0 ? `; ${verified} found in the document text${withheld ? `, ${withheld} withheld` : ""}` : ""}
              </dd>
            </div>
          </dl>
        )}
        {/* Where the product does not repeat the model's sentence (a point reported as not found), it is kept here,
            as the model's: it may word the absence as a fact about the agreement, which the sections read cannot show. */}
        {finding.modelConclusion && finding.modelConclusion !== finding.conclusion && (
          <dl className={styles.drawerFacts} data-testid="model-sentence">
            <div>
              <dt>Its sentence</dt>
              <dd>
                <span className={styles.modelPassage}>{finding.modelConclusion}</span>
              </dd>
            </div>
          </dl>
        )}
        {/* The model's own fields as the run stored them: shown here whether or not the proposal could be rebuilt. */}
        {(finding.guidanceReference || finding.suggestedPosition || (!proposal && (finding.observed || finding.required))) && (
          <dl className={styles.drawerFacts}>
            {!proposal && (finding.observed || finding.required) && (
              <div>
                <dt>In its words</dt>
                <dd>
                  <ModelWords observed={finding.observed} required={finding.required} />
                </dd>
              </div>
            )}
            {finding.guidanceReference && (
              <div>
                <dt>It pointed at</dt>
                <dd>
                  <span className={styles.modelPassage}>{finding.guidanceReference}</span>
                </dd>
              </div>
            )}
            {finding.suggestedPosition && (
              <div>
                <dt>It suggested</dt>
                <dd>{finding.suggestedPosition}</dd>
              </div>
            )}
          </dl>
        )}
      </section>

      <section className={`${styles.drawerSection} ${styles.layer}`} data-testid="layer-source">
        <div className={styles.layerHead}>
          <h4>Source</h4>
        </div>
        {finding.spans.map((span, i) => {
          const section = span.sectionId ? sectionsById.get(span.sectionId) : undefined;
          const match = explained?.sourceMatches[i] ?? null;
          return (
            <div key={i} className={styles.drawerSpan}>
              {section && span.verified ? (
                <button type="button" className={styles.drawerRef} onClick={() => onJump(section.id, span)}>
                  {citationLabel(section)}
                </button>
              ) : (
                <div className={styles.drawerRefStatic}>{section ? citationLabel(section) : "Section not identified"}</div>
              )}
              <blockquote className={span.verified ? styles.drawerQuote : `${styles.drawerQuote} ${styles.quoteWithheld}`}>{span.quote}</blockquote>
              <span className={styles.verifiedTag}>
                {span.verified && <IconCheck className={styles.verifiedMark} />}
                <span>
                  {!span.verified
                    ? `Not found verbatim in the document · withheld${span.citedSectionLabel ? ` · the model cited ${span.citedSectionLabel}` : ""}`
                    : finding.evidenceKind === "coverage"
                      ? "Found in the document text · the closest provision read; in the model's view it does not state the point"
                      : span.method === "exact"
                        ? "Found word for word in the document text · exact"
                        : `Found in the document text · ${span.method}`}
                </span>
              </span>
              {span.verified && match && (
                <div className={styles.drawerRefStatic}>
                  {match.relocated
                    ? `Found in ${match.locatedHeading || "another section"}, not in the section the model cited.`
                    : "Found where the model cited it."}
                  {match.matchCount != null && match.matchCount > 1 ? ` It occurs ${match.matchCount} times there; the first is highlighted.` : ""}
                  {match.insideModelVisibleContext === false ? " It lies outside the text the model was shown." : ""}
                </div>
              )}
              {span.verified && !match && span.matchCount != null && span.matchCount > 1 && (
                <div className={styles.drawerRefStatic}>This passage occurs {span.matchCount} times in the section; the first is highlighted.</div>
              )}
            </div>
          );
        })}
        {finding.spans.length === 0 && <p className={styles.drawerRefStatic}>No passage was cited.</p>}
        {finding.spans.some((span) => span.verified) && (
          <p className={styles.drawerRefStatic} data-testid="source-limit">
            Code checked that each passage is in the document text. Whether it supports the answer is the model&apos;s reading, and yours to decide.
          </p>
        )}
      </section>

      <section className={`${styles.drawerSection} ${styles.layer} ${setByModel ? "" : styles.layerSet}`} data-testid="layer-code">
        {/* The heading is a claim. It says "Code found a conflict" only under a source where code compared two periods; the
            model's own phrases, its pointer into the guidance and its suggestion are in the layer above, never here. */}
        <div className={styles.layerHead}>
          <h4>{codeRole(finding.statusSource)}</h4>
          {!setByModel && setTag}
        </div>
        {guidance && (
          <div className={styles.guidanceBlock}>
            <h5 className={styles.drawerSubhead}>{decidedByCode(finding.statusSource) || confirmed ? "Guidance" : "Guidance given"}</h5>
            <blockquote className={styles.guidanceQuote}>{guidance}</blockquote>
          </div>
        )}
        {(decidedByCode(finding.statusSource) || confirmed) && comparison && <DayGauge comparison={comparison} />}
        <dl className={styles.drawerFacts}>
          <div>
            <dt>{decidedByCode(finding.statusSource) ? "Code found" : confirmed ? "Confirmed by code" : "Status"}</dt>
            <dd>
              {finding.statusReason ??
                (finding.statusSource === "model_hint"
                  ? "No comparable day counts, so the model's hint stands as its view."
                  : finding.statusSource === "no_evidence"
                    ? "No verified passage, so no status was given."
                    : "Lowered by code: " + statusLabel(finding.status, hasGuidance, finding.statusSource).toLowerCase())}
            </dd>
          </div>
          <div>
            <dt>Result</dt>
            <dd>
              <StatusChip status={finding.status} hasGuidance={hasGuidance} source={finding.statusSource} />
            </dd>
          </div>
        </dl>
      </section>

      <HumanLayer finding={finding} onReviewed={run?.shared ? undefined : onReviewed} curated={run?.shared ?? false} />

      {run && (
        <section className={`${styles.drawerSection} ${styles.proveSection}`}>
          <p className={styles.proveLede}>The model&apos;s exact input, rebuilt from the record and checked against the hash taken when it ran.</p>
          <button type="button" className={styles.whyToggle} aria-expanded={prove} onClick={() => setProve((open) => !open)}>
            {prove ? "Hide the proof" : "Prove it"}
          </button>
          {prove && (
            <div className={styles.proof}>
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
                    {verified} found in the document text{withheld ? ` · ${withheld} withheld` : ""}
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
                  <dd className={styles.whyMono}>{run.id}</dd>
                </div>
                <div>
                  <dt>Take it away</dt>
                  <dd>
                    <a
                      className={styles.actionLink}
                      href={absolute(`/api/runs/${run.id}/evidence-pack`)}
                      title="The original bytes, the sections, every located span and a verify.py that checks them without this service"
                    >
                      Download evidence pack
                    </a>
                  </dd>
                </div>
              </dl>
              <WhyThisAnswer runId={run.id} findingId={finding.id} explanation={explanation} problem={read?.problem ?? null} />
            </div>
          )}
        </section>
      )}
    </>
  );
}

type Decision = Exclude<ReviewVerdict, "cleared">;

/** The person's decision on the finding, as the API recorded it, and the controls to record one. */
function HumanLayer({
  finding,
  onReviewed,
  curated = false,
}: {
  finding: FindingView;
  onReviewed?: (findingId: string, review: ReviewView | null) => void;
  /** A curated record: the review is kept as recorded, and no control to change it is offered. */
  curated?: boolean;
}) {
  const [busy, setBusy] = useState(false);
  const [pending, setPending] = useState<Decision | null>(null);
  const [name, setName] = useState("");
  const [error, setError] = useState<string | null>(null);

  const decide = async (verdict: ReviewVerdict, reviewerName?: string) => {
    const reviewer = reviewerName ?? rememberedReviewer();
    if (!reviewer) {
      if (verdict !== "cleared") setPending(verdict);
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const out = await reviewFinding(finding.id, { verdict, reviewer, note: null });
      rememberReviewer(reviewer);
      setPending(null);
      onReviewed?.(finding.id, out.review ?? null);
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className={`${styles.drawerSection} ${styles.layer} ${styles.layerLast} ${finding.review ? styles.layerHuman : ""}`} data-testid="layer-human">
      <div className={styles.layerHead}>
        <h4>Human</h4>
      </div>
      {finding.review ? (
        <dl className={styles.drawerFacts}>
          <div>
            <dt>{finding.review.verdict === "confirmed" ? "Confirmed" : "Dismissed"}</dt>
            <dd>
              by {finding.review.reviewer} · {formatWhen(finding.review.at)}
              {finding.review.note ? ` · ${finding.review.note}` : ""}
            </dd>
          </div>
        </dl>
      ) : (
        <p className={styles.drawerRefStatic}>No one has decided on this finding yet.</p>
      )}
      {curated && <p className={styles.drawerRefStatic}>A curated record: the review above is kept as it was made and is not changed here.</p>}
      {onReviewed && (
        <div className={styles.resultActions}>
          {finding.review ? (
            <button type="button" className={styles.actionButton} disabled={busy} onClick={() => void decide("cleared")}>
              Clear the decision
            </button>
          ) : (
            <>
              <button type="button" className={styles.actionButton} disabled={busy} onClick={() => void decide("confirmed")}>
                Confirm
              </button>
              <button type="button" className={styles.actionButton} disabled={busy} onClick={() => void decide("dismissed")}>
                Dismiss
              </button>
            </>
          )}
        </div>
      )}
      {pending && (
        <form
          className={styles.reviewerForm}
          onSubmit={(event) => {
            event.preventDefault();
            const typed = name.trim();
            if (typed) void decide(pending, typed);
          }}
        >
          <label htmlFor="drawer-reviewer">Your name, recorded with the decision</label>
          <input id="drawer-reviewer" className={styles.popoverInput} value={name} onChange={(e) => setName(e.target.value)} maxLength={80} autoFocus />
          <button type="submit" className={styles.actionButton} disabled={busy || !name.trim()}>
            {pending === "confirmed" ? "Confirm as" : "Dismiss as"} {name.trim() || "you"}
          </button>
        </form>
      )}
      {error && (
        <p className={styles.errorLine} role="alert">
          {error}
        </p>
      )}
    </section>
  );
}

/** The model's own phrases, set apart so they are never read as the contract's or the guidance's. */
function ModelWords({ observed, required }: { observed: string | null | undefined; required: string | null | undefined }) {
  return (
    <>
      {observed ? <span className={styles.modelWords}>{observed}</span> : "nothing observed"}
      {required ? (
        <>
          {" "}
          against <span className={styles.modelWords}>{required}</span>
        </>
      ) : null}
    </>
  );
}

type Tone = "pass" | "review" | "muted";

function toneOf(status: FindingStatus): Tone {
  return status === "pass" ? "pass" : status === "needs_review" ? "review" : "muted";
}

/** A status label without its parenthesis: the strip says whose view it is by its column. */
function plainLabel(label: string): string {
  return label.replace(/\s*\([^)]*\)$/, "");
}

interface StripCell {
  who: string;
  what: string;
  tone: Tone;
  note?: string;
  /** The model's call, when code changed it. */
  struck?: boolean;
  /** The column whose call is the status on screen. */
  decisive?: boolean;
}

/**
 * The finding's trail in one line, read left to right: what the model called it, whether its quotes were found,
 * what code made of it, what a person decided. Every cell is read from the same record as the layers below it.
 */
function DecisionStrip({ cells }: { cells: StripCell[] }) {
  const tones: Record<Tone, string> = { pass: styles.stripPass, review: styles.stripReview, muted: styles.stripMuted };
  return (
    <ol className={styles.strip} aria-label="The finding's trail">
      {cells.map((cell) => (
        <li key={cell.who} className={`${styles.stripCell} ${tones[cell.tone]} ${cell.decisive ? styles.stripDecisive : ""}`}>
          <span className={styles.stripWho}>{cell.who}</span>
          <span className={`${styles.stripWhat} ${cell.struck ? styles.stripStruck : ""}`}>{cell.what}</span>
          {cell.note && <span className={styles.stripNote}>{cell.note}</span>}
        </li>
      ))}
    </ol>
  );
}
