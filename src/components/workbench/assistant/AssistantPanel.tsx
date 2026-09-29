"use client";

import { AnimatePresence, motion } from "framer-motion";
import type { Dispatch, Ref, SetStateAction } from "react";
import styles from "../Workbench.module.css";
import { IconArrowUp, IconCommand } from "../icons";
import { transitions } from "../shell/constants";
import type { GuidanceController } from "../hooks/useGuidance";
import type { MemoController } from "../hooks/useMemoAction";
import type { RunController } from "../hooks/useRunFollower";
import { EvidenceDrawer } from "./EvidenceDrawer";
import { FindingCard } from "./FindingCard";
import { GuidanceScope } from "./GuidanceScope";
import { RunOutcome, WithheldList } from "./RunOutcome";
import { StageList } from "./StageList";
import { absolute } from "@/lib/api";
import { STAGE_LABELS, type DocumentView, type FindingView, type SectionView, type SpanView } from "@/lib/types";

// The third question has no answer in the sample; on it the model tends to propose a quote that
// is not there, and the verifier withholds it. That moment is meant to be one click away.
export const ASSISTANT_SUGGESTIONS = [
  "Review against instructions",
  "What notice is needed to terminate for convenience?",
  "Is there a most favoured nation clause?",
  "What is the limitation of liability?",
];

/**
 * The Assistant beside the document: scope, one question at a time, the run's progress as the
 * API reports it, findings as objects, the memo action and the evidence drawer. It renders what
 * the API decided; it does not decide anything about evidence itself.
 */
export function AssistantPanel({
  doc,
  runs,
  guidance,
  memo,
  composerText,
  setComposerText,
  onAsk,
  inputRef,
  onFollowUp,
  evidence,
  onOpenEvidence,
  onCloseEvidence,
  drawerCloseRef,
  sectionsById,
  onJump,
  onOpenPalette,
  reduceMotion,
}: {
  doc: DocumentView | null;
  runs: RunController;
  guidance: GuidanceController;
  memo: MemoController;
  composerText: string;
  setComposerText: Dispatch<SetStateAction<string>>;
  onAsk: (text: string) => void;
  inputRef: Ref<HTMLTextAreaElement>;
  onFollowUp: () => void;
  evidence: FindingView | null;
  onOpenEvidence: (finding: FindingView, trigger: HTMLElement | null) => void;
  onCloseEvidence: () => void;
  drawerCloseRef: Ref<HTMLButtonElement>;
  sectionsById: Map<string, SectionView>;
  onJump: (sectionId: string, span: SpanView | null) => void;
  onOpenPalette: () => void;
  reduceMotion: boolean;
}) {
  const { morph, quick } = transitions(reduceMotion);
  const { run, runError, stageDetails } = runs;
  const stageLabel = run && run.stage in STAGE_LABELS ? STAGE_LABELS[run.stage as keyof typeof STAGE_LABELS] : null;
  const checkingLabel = guidance.guidance ? "Checking against guidance" : "Checking the contract";

  return (
    <div className={styles.assistantPane}>
      <header className={styles.assistantHeader}>
        <div className={styles.assistantTitleRow}>
          <div className={styles.assistantTitle}>Assistant</div>
          <button type="button" className={styles.kbdHint} onClick={onOpenPalette} aria-label="Open commands">
            <IconCommand /> K
          </button>
        </div>
        <GuidanceScope documentName={doc?.name.replace(/\.[^.]+$/, "") ?? ""} guidance={guidance} reduceMotion={reduceMotion} />
      </header>

      <div className={styles.assistantBody}>
        {!run ? (
          <div className={styles.assistantIdle}>
            <p className={styles.assistantPrompt}>What would you like to know?</p>
            <div className={styles.actionList}>
              {ASSISTANT_SUGGESTIONS.map((s) => (
                <button key={s} type="button" className={styles.actionItem} onClick={() => onAsk(s)}>
                  {s}
                </button>
              ))}
            </div>
            {runError && (
              <p className={styles.errorLine} role="alert">
                {runError}
              </p>
            )}
          </div>
        ) : (
          <div className={styles.thread}>
            <div className={styles.userTurn}>{run.question}</div>
            <AnimatePresence mode="wait" initial={false}>
              {stageLabel ? (
                <motion.div
                  key="thinking"
                  className={styles.stageList}
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  exit={{ opacity: 0 }}
                  transition={quick}
                >
                  <StageList current={run.stage} details={stageDetails} checkingLabel={checkingLabel} reduceMotion={reduceMotion} />
                </motion.div>
              ) : run.stage === "complete" && run.findings.length > 0 ? (
                <motion.div
                  key="results"
                  className={styles.results}
                  initial={{ opacity: 0, y: reduceMotion ? 0 : 6 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={morph}
                >
                  {run.findings.map((finding) => (
                    <FindingCard
                      key={finding.id}
                      finding={finding}
                      sectionsById={sectionsById}
                      onJump={onJump}
                      onEvidence={(trigger) => onOpenEvidence(finding, trigger)}
                      onFollowUp={onFollowUp}
                    />
                  ))}
                  {run.withheld.length > 0 && <WithheldList findings={run.withheld} sectionsById={sectionsById} onEvidence={onOpenEvidence} />}
                  <div className={styles.memoRow}>
                    {memo.memo ? (
                      <>
                        <span className={styles.memoDone}>Review memo ready</span>
                        <a className={styles.actionLink} href={absolute(memo.memo.htmlUrl)} target="_blank" rel="noreferrer">
                          Open
                        </a>
                        <a className={styles.actionLink} href={absolute(memo.memo.docxUrl)}>
                          Download .docx
                        </a>
                      </>
                    ) : (
                      <button type="button" className={styles.memoButton} onClick={() => void memo.generate(run)} disabled={memo.busy}>
                        {memo.busy ? "Writing memo…" : "Generate review memo"}
                      </button>
                    )}
                    {memo.error && <span className={styles.errorLine}>{memo.error}</span>}
                  </div>
                  <p className={styles.runMeta}>
                    {run.reused ? "answered earlier for this exact question · " : ""}
                    {run.model} · prompt {run.promptVersion} · {run.latencyMs !== null ? `${(run.latencyMs / 1000).toFixed(0)} s` : ""} · every citation
                    verified against the document text{run.withheld.length > 0 ? ` · ${run.withheld.length} withheld` : ""}
                  </p>
                </motion.div>
              ) : (
                <motion.div key="unresolved" className={styles.unresolved} initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={quick}>
                  <RunOutcome run={run} runError={runError} sectionsById={sectionsById} onRetry={onAsk} onEvidence={onOpenEvidence} />
                </motion.div>
              )}
            </AnimatePresence>
          </div>
        )}
      </div>

      <motion.div layoutId="composer" className={`${styles.composer} ${styles.assistantComposer}`} transition={morph}>
        <textarea
          ref={inputRef}
          className={styles.composerInput}
          placeholder="Ask anything about this contract…"
          rows={1}
          value={composerText}
          onChange={(e) => setComposerText(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              onAsk(composerText);
            }
          }}
        />
        <button type="button" className={styles.sendButton} aria-label="Send" onClick={() => onAsk(composerText)} disabled={!!stageLabel}>
          <IconArrowUp />
        </button>
      </motion.div>

      <EvidenceDrawer
        finding={evidence}
        run={run}
        guidanceText={guidance.guidance?.text ?? null}
        sectionsById={sectionsById}
        onJump={onJump}
        onClose={onCloseEvidence}
        closeRef={drawerCloseRef}
        reduceMotion={reduceMotion}
      />
    </div>
  );
}
