"use client";

import { AnimatePresence, motion } from "framer-motion";
import { useEffect, useState, type Dispatch, type SetStateAction } from "react";
import styles from "./Landing.module.css";
import { IconArrowRight, IconFile } from "../icons";
import { transitions, type Stage } from "../shell/constants";
import { Brand, Shimmer, StatusChip } from "../shell/primitives";
import { OneRun, RecordPipeline, Refusals } from "./LandingStory";
import { getCitations, getRun, listDocuments, type Health } from "@/lib/api";
import { plural } from "@/lib/format";
import { decidedByCode, type CitationRecord, type DocumentSummary, type FindingView, type RunSummary } from "@/lib/types";

/** How a status is set, in the order the evidence drawer reads it. Static: it describes the product, not one run. */
const LAYERS = [
  {
    name: "Model proposed",
    text: "A local model reads the sections retrieval chose for the question and proposes an answer, quoting the contract.",
  },
  { name: "Source checked", text: "Code looks for every quote in the document text. A quote it cannot find is withheld, not shown." },
  {
    name: "Code compared",
    text: "Where the contract and your guidance both state a period, code compares the days. A conflict sends the finding to review. A pass stays the model's, with the numbers checked.",
  },
  { name: "Person reviewed", text: "A reviewer confirms or dismisses each finding. The decision is kept with the run, under their name." },
] as const;

/** The first screen: what Verity is, where a contract goes, and one finished review a stranger can open. */
export function Landing({
  stage,
  processingLabel,
  pendingName,
  composerText,
  setComposerText,
  onHome,
  onPickFile,
  onLoadSample,
  proof,
  onOpenProof,
  uploadError,
  apiHealth,
  accessKnown,
  recent,
  onOpenDocument,
  onAllDocuments,
  viewError,
  reduceMotion,
}: {
  stage: Stage;
  processingLabel: string;
  pendingName: string;
  composerText: string;
  setComposerText: Dispatch<SetStateAction<string>>;
  onHome: () => void;
  onPickFile: () => void;
  onLoadSample: () => void;
  proof: RunSummary | null;
  onOpenProof: (runId: string, findingId?: string) => void;
  uploadError: string | null;
  apiHealth: Health | null;
  /** Whether the API has said what its door is; until it has, the screen claims neither open nor private. */
  accessKnown: boolean;
  recent: DocumentSummary[];
  onOpenDocument: (id: string) => void;
  onAllDocuments: () => void;
  viewError: string | null;
  reduceMotion: boolean;
}) {
  const { morph, quick } = transitions(reduceMotion);
  // The finished review's first finding, read from its run, so the card can say what was decided and by whom.
  const [lead, setLead] = useState<FindingView | null>(null);
  const proofId = proof?.id ?? null;
  useEffect(() => {
    if (!proofId) return;
    let cancelled = false;
    getRun(proofId)
      .then((run) => !cancelled && setLead(run.findings[0] ?? null))
      .catch(() => !cancelled && setLead(null));
    return () => {
      cancelled = true;
    };
  }, [proofId]);
  // The record's counts for the pipeline below the fold: read once per visit to the first screen, never estimated.
  const [citations, setCitations] = useState<CitationRecord | null>(null);
  const [documents, setDocuments] = useState<DocumentSummary[] | null>(null);
  useEffect(() => {
    if (stage !== "empty") return;
    let cancelled = false;
    getCitations()
      .then((record) => !cancelled && setCitations(record))
      .catch(() => !cancelled && setCitations(null));
    listDocuments()
      .then((rows) => !cancelled && setDocuments(rows))
      .catch(() => !cancelled && setDocuments(null));
    return () => {
      cancelled = true;
    };
  }, [stage]);
  const rise = (delay: number) =>
    reduceMotion
      ? {}
      : { initial: { opacity: 0, y: 10 }, animate: { opacity: 1, y: 0 }, transition: { duration: 0.6, delay, ease: [0.16, 1, 0.3, 1] as const } };

  // What the API says the door is: off means every record made here is readable by whoever reaches the site, and
  // the first screen must say so rather than call it private. Until the API has said (or when it could not be asked),
  // the screen claims neither: it used to read "Private preview … readable through your invite and no other" for the
  // first seconds of an open site (QA review, 2026-10-08).
  const openPreview = accessKnown && apiHealth?.access === "off";
  const privatePreview = accessKnown && (apiHealth?.access === "required" || apiHealth?.access === "entered");

  return (
    <motion.section
      id="main"
      tabIndex={-1}
      className={styles.page}
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0, transition: quick }}
      transition={quick}
    >
      <header className={styles.topbar}>
        <button type="button" className={styles.home} aria-label="Verity: the first screen" onClick={onHome}>
          <Brand />
        </button>
        <span className={styles.preview}>
          <span className={styles.previewDot} aria-hidden="true" />
          {openPreview ? "Open preview" : privatePreview ? "Private preview" : "Preview"}
        </span>
      </header>

      <div className={`${styles.body} ${stage === "dragging" ? styles.dimmed : ""}`}>
        <div>
          <motion.p className={styles.kicker} {...rise(0)}>
            <motion.span
              className={styles.kickerRule}
              initial={reduceMotion ? false : { scaleX: 0 }}
              animate={{ scaleX: 1 }}
              transition={{ duration: 0.7, delay: 0.15, ease: [0.16, 1, 0.3, 1] }}
            />
            Contract review
          </motion.p>
          <motion.h1 className={styles.title} {...rise(0.06)}>
            Ask about a contract. <span className={styles.titleQuiet}>See who decided each answer.</span>
          </motion.h1>
          <motion.p className={styles.lead} {...rise(0.12)}>
            Verity hands a local model the sections your question needs, checks every passage it quotes against the document text, and lets code compare the day
            counts it can compute. A person has the last word on every finding.
          </motion.p>

          <motion.div layoutId="composer" className={`${styles.drop} ${stage !== "empty" ? styles.dropActive : ""}`} transition={morph}>
            {stage === "processing" ? (
              <div className={styles.processing}>
                <span className={styles.fileName}>
                  <IconFile /> <span>{pendingName}</span>
                </span>
                <span className={styles.stateLine}>
                  <Shimmer />
                  <AnimatePresence mode="wait" initial={false}>
                    <motion.span
                      key={processingLabel}
                      initial={{ opacity: 0, y: 4 }}
                      animate={{ opacity: 1, y: 0 }}
                      exit={{ opacity: 0, y: -4 }}
                      transition={quick}
                    >
                      {processingLabel}
                    </motion.span>
                  </AnimatePresence>
                </span>
              </div>
            ) : stage === "dragging" ? (
              <div className={styles.releaseHint}>Release to add the contract</div>
            ) : (
              <>
                <textarea
                  className={styles.dropInput}
                  aria-label="Your question, asked once the contract is added"
                  placeholder="Ask a question about the contract, then add it"
                  rows={2}
                  value={composerText}
                  onChange={(e) => setComposerText(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" && !e.shiftKey) {
                      e.preventDefault();
                      onPickFile();
                    }
                  }}
                />
                <div className={styles.dropRow}>
                  <span className={styles.dropIcon} aria-hidden="true">
                    <span />
                    <span />
                    <span />
                    <span />
                  </span>
                  <div className={styles.dropText}>
                    <div className={styles.dropTitle}>Drop a contract here</div>
                    <div className={styles.dropHint}>
                      PDF, DOCX or TXT. It is read into numbered sections and stored with its SHA-256 on this machine
                      {openPreview
                        ? ", where anyone with this address can open it: this preview is open."
                        : privatePreview
                          ? ", readable through your invite and no other."
                          : "."}
                    </div>
                  </div>
                  <button type="button" className={styles.primary} aria-label="Add a contract" onClick={onPickFile}>
                    Add a contract
                  </button>
                </div>
              </>
            )}
          </motion.div>

          {stage === "empty" && (
            <>
              <p className={styles.after}>
                No contract to hand? Use the sample, a real standard agreement:{" "}
                <button type="button" className={styles.link} onClick={onLoadSample}>
                  try a sample agreement
                </button>
              </p>
              {uploadError && (
                <p className={styles.error} role="alert">
                  {uploadError}
                </p>
              )}
              {apiHealth && !apiHealth.ok && (
                <p className={styles.error} role="status">
                  Model offline: {apiHealth.detail}
                </p>
              )}
              {viewError && (
                <p className={styles.error} role="alert">
                  {viewError}
                </p>
              )}
              {recent.length > 0 && (
                <motion.div className={styles.ledger} {...rise(0.24)}>
                  <div className={styles.ledgerHead}>
                    <span>Recent contracts</span>
                    <button type="button" className={styles.link} onClick={onAllDocuments}>
                      All documents
                    </button>
                  </div>
                  {recent.map((d, i) => (
                    <button key={d.id} type="button" className={styles.ledgerRow} title={d.name} onClick={() => onOpenDocument(d.id)}>
                      <span className={styles.ledgerIndex} aria-hidden="true">
                        {String(i + 1).padStart(2, "0")}
                      </span>
                      <span className={styles.ledgerName}>{d.name}</span>
                      <span className={styles.ledgerMeta}>
                        {plural(d.sections, "section")} · {plural(d.findings, "finding")}
                      </span>
                    </button>
                  ))}
                </motion.div>
              )}
            </>
          )}
        </div>

        {stage === "empty" && (
          <motion.aside className={styles.aside} aria-label="A finished review" {...rise(0.18)}>
            {proof && (
              <article className={styles.receipt}>
                <div className={styles.receiptHead}>
                  <span>A finished review</span>
                  <span className={styles.receiptId}>run {proof.id.slice(0, 8)}</span>
                </div>
                <div className={styles.receiptBody}>
                  <p className={styles.receiptQuestion}>{proof.question}</p>
                  <dl className={styles.receiptFacts}>
                    <div>
                      <dt>Contract</dt>
                      <dd title={proof.documentName}>{proof.documentName}</dd>
                    </div>
                    <div>
                      <dt>Findings</dt>
                      <dd>{plural(proof.findings, "finding")}, every quoted passage found in the document</dd>
                    </div>
                    <div>
                      <dt>Model</dt>
                      <dd>
                        {proof.model}
                        {proof.latencyMs !== null ? `, ${Math.round(proof.latencyMs / 1000)} s` : ""}
                      </dd>
                    </div>
                  </dl>
                  {lead && (
                    <div className={styles.receiptDecision}>
                      <div className={styles.receiptDecisionHead}>
                        <span className={styles.receiptTopic}>{lead.topic}</span>
                        <StatusChip status={lead.status} hasGuidance={proof.hasGuidance} source={lead.statusSource} />
                      </div>
                      {lead.statusReason && (
                        <p className={styles.receiptReason}>
                          <span className={styles.receiptWho}>{decidedByCode(lead.statusSource) ? "Code found" : "Status"}</span>
                          {lead.statusReason}
                        </p>
                      )}
                      {lead.review && (
                        <p className={styles.receiptReason}>
                          <span className={styles.receiptWho}>{lead.review.verdict === "confirmed" ? "Confirmed" : "Dismissed"}</span>
                          by {lead.review.reviewer}
                        </p>
                      )}
                    </div>
                  )}
                </div>
                <div className={styles.receiptFoot}>
                  <span>{proof.hasGuidance ? "Checked against written guidance" : "Answered from the contract alone"}</span>
                  <button type="button" className={styles.receiptOpen} onClick={() => onOpenProof(proof.id, lead?.id)} title={`Open run ${proof.id}`}>
                    Open the review <IconArrowRight />
                  </button>
                </div>
              </article>
            )}
            <ol className={styles.layers}>
              <li className={styles.layersHead}>How each status is set</li>
              {LAYERS.map((layer, i) => (
                <li key={layer.name} className={styles.layer}>
                  <span className={`${styles.layerNode} ${i === 2 ? styles.layerNodeCode : ""}`}>{i + 1}</span>
                  <span>
                    <span className={styles.layerName}>{layer.name}</span>
                    <p className={styles.layerText}>{layer.text}</p>
                  </span>
                </li>
              ))}
            </ol>
          </motion.aside>
        )}
      </div>

      {stage === "empty" && (
        <div className={styles.below}>
          <RecordPipeline citations={citations} documents={documents} reduceMotion={reduceMotion} />
          {proof && <OneRun proof={proof} lead={lead} onOpen={onOpenProof} reduceMotion={reduceMotion} />}
          <Refusals reduceMotion={reduceMotion} />
        </div>
      )}

      <footer className={styles.footer}>
        <span>
          {apiHealth?.model ? (
            <>
              Model <code>{apiHealth.model}</code>, run on this machine. No contract is sent to a hosted model.
            </>
          ) : (
            "The model runs on this machine."
          )}
        </span>
        <span>Every run is kept as a record: what the model saw, what it said, what code checked.</span>
      </footer>
    </motion.section>
  );
}
