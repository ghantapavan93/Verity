"use client";

import { AnimatePresence, motion } from "framer-motion";
import type { Dispatch, SetStateAction } from "react";
import styles from "../Workbench.module.css";
import { IconArrowUp, IconFile, IconPlus } from "../icons";
import { transitions, type Stage } from "../shell/constants";
import { Shimmer, UserChip } from "../shell/primitives";
import type { Health } from "@/lib/api";
import type { DocumentSummary, RunSummary } from "@/lib/types";

/** The first screen: one question and one composer. The composer morphs into the Assistant's when a contract arrives. */
export function Landing({
  stage,
  processingLabel,
  pendingName,
  composerText,
  setComposerText,
  onPickFile,
  onLoadSample,
  proof,
  onOpenProof,
  uploadError,
  apiHealth,
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
  onPickFile: () => void;
  onLoadSample: () => void;
  proof: RunSummary | null;
  onOpenProof: (runId: string) => void;
  uploadError: string | null;
  apiHealth: Health | null;
  recent: DocumentSummary[];
  onOpenDocument: (id: string) => void;
  onAllDocuments: () => void;
  viewError: string | null;
  reduceMotion: boolean;
}) {
  const { morph, quick } = transitions(reduceMotion);
  return (
    <motion.section className={styles.landing} initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0, transition: quick }} transition={quick}>
      <header className={styles.topbar}>
        <div className={styles.brand}>
          <span className={styles.mark} aria-hidden="true" />
          <span className={styles.wordmark}>Workbench</span>
        </div>
        <UserChip />
      </header>

      <div className={`${styles.landingBody} ${stage === "dragging" ? styles.dimmed : ""}`}>
        <h1 className={styles.prompt}>What are you reviewing?</h1>

        <motion.div layoutId="composer" className={`${styles.composer} ${stage !== "empty" ? styles.composerActive : ""}`} transition={morph}>
          {stage === "processing" ? (
            <div className={styles.processing}>
              <span className={styles.fileChip}>
                <IconFile /> {pendingName}
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
            <div className={styles.dropHint}>Release to add your contract</div>
          ) : (
            <>
              <textarea
                className={styles.composerInput}
                placeholder="Drop a contract here, or add one to start…"
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
              <div className={styles.composerBar}>
                <button type="button" className={styles.ghostButton} onClick={onPickFile}>
                  <IconPlus /> Add contract
                </button>
                <button type="button" className={styles.sendButton} aria-label="Add a contract" onClick={onPickFile}>
                  <IconArrowUp />
                </button>
              </div>
            </>
          )}
        </motion.div>

        {stage === "empty" && (
          <>
            <p className={styles.sampleNote}>
              PDF, DOCX or TXT. Or{" "}
              <button type="button" className={styles.linkButton} onClick={onLoadSample}>
                try a sample agreement
              </button>
              .
            </p>
            {proof && (
              <p className={styles.proofNote}>
                Or open a finished review:{" "}
                <button type="button" className={styles.linkButton} onClick={() => onOpenProof(proof.id)} title={`Open run ${proof.id}`}>
                  “{proof.question}”
                </button>{" "}
                on {proof.documentName}, {proof.findings} finding{proof.findings === 1 ? "" : "s"} with verified citations.
              </p>
            )}
            {uploadError && (
              <p className={styles.errorLine} role="alert">
                {uploadError}
              </p>
            )}
            {apiHealth && !apiHealth.ok && (
              <p className={styles.errorLine} role="status">
                Model offline: {apiHealth.detail}
              </p>
            )}
            {recent.length > 0 && (
              <p className={styles.recent}>
                <span>Recent</span>
                {recent.map((d) => (
                  <button key={d.id} type="button" className={styles.recentButton} title={d.name} onClick={() => onOpenDocument(d.id)}>
                    {d.name}
                  </button>
                ))}
                <button type="button" className={styles.linkButton} onClick={onAllDocuments}>
                  All documents
                </button>
              </p>
            )}
            {viewError && (
              <p className={styles.errorLine} role="alert">
                {viewError}
              </p>
            )}
          </>
        )}
      </div>
    </motion.section>
  );
}
