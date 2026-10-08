"use client";

import { AnimatePresence, motion } from "framer-motion";
import { useSyncExternalStore, type Dispatch, type Ref, type SetStateAction } from "react";
import styles from "../Workbench.module.css";
import { IconArrowRight, IconArrowUp, IconCheck, IconCommand } from "../icons";
import { transitions } from "../shell/constants";
import type { GuidanceController } from "../hooks/useGuidance";
import type { MemoController } from "../hooks/useMemoAction";
import type { RunController } from "../hooks/useRunFollower";
import { EvidenceDrawer } from "./EvidenceDrawer";
import { FindingCard } from "./FindingCard";
import { GuidanceScope } from "./GuidanceScope";
import { RevisionCheck } from "./RevisionCheck";
import { RunOutcome, WithheldList } from "./RunOutcome";
import { StageList } from "./StageList";
import { absolute } from "@/lib/api";
import {
  STAGE_LABELS,
  sectionsReadNote,
  type DocumentView,
  type FindingView,
  type ReviewView,
  type SectionView,
  type SpanView,
  type RunStage,
} from "@/lib/types";

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
const noSubscription = () => () => undefined;
const isApplePlatform = () => /Mac|iPhone|iPad/.test(navigator.platform);

/** The API accepts a question of at most this many characters (RunCreate.question). */
export const MAX_QUESTION_CHARS = 2000;

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
  onReviewed,
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
  onReviewed: (findingId: string, review: ReviewView | null) => void;
  drawerCloseRef: Ref<HTMLButtonElement>;
  sectionsById: Map<string, SectionView>;
  onJump: (sectionId: string, span: SpanView | null) => void;
  onOpenPalette: () => void;
  reduceMotion: boolean;
}) {
  const { morph, quick } = transitions(reduceMotion);
  const { run, pending, runError, stageDetails } = runs;
  // The shortcut as this keyboard writes it. The server render says Ctrl; the client reads the platform once.
  const apple = useSyncExternalStore(noSubscription, isApplePlatform, () => false);
  // A run being created shows as reading; a run in flight shows the API's stage; a run that could not start shows its error.
  const liveStage: RunStage | null = pending && !runError ? "reading" : run && run.stage in STAGE_LABELS ? run.stage : null;
  const stageLabel = liveStage ? STAGE_LABELS[liveStage as keyof typeof STAGE_LABELS] : null;
  const question = run?.question ?? pending?.question ?? "";
  const checkingLabel = guidance.guidance ? "Checking against guidance" : "Checking the contract";

  return (
    <div className={styles.assistantPane}>
      <header className={styles.assistantHeader}>
        <div className={styles.assistantTitleRow}>
          <div className={styles.assistantTitle}>Questions</div>
          <button type="button" className={styles.kbdHint} onClick={onOpenPalette} aria-label="Open commands">
            {apple ? (
              <>
                <IconCommand /> K
              </>
            ) : (
              "Ctrl K"
            )}
          </button>
        </div>
        <GuidanceScope documentName={doc?.name.replace(/\.[^.]+$/, "") ?? ""} guidance={guidance} reduceMotion={reduceMotion} />
      </header>

      <div className={styles.assistantBody}>
        {!run && !pending ? (
          <div className={styles.assistantIdle}>
            <div className={styles.assistantKicker}>Ask about this contract</div>
            <p className={styles.assistantPrompt}>One question at a time, answered from the contract&apos;s own words.</p>
            <div className={styles.actionList}>
              {ASSISTANT_SUGGESTIONS.map((s, i) => (
                <button key={s} type="button" className={styles.actionItem} onClick={() => onAsk(s)}>
                  <span className={styles.actionIndex} aria-hidden="true">
                    {String(i + 1).padStart(2, "0")}
                  </span>
                  <span>{s}</span>
                  <span className={styles.actionArrow} aria-hidden="true">
                    <IconArrowRight />
                  </span>
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
            <div className={styles.userTurn}>{question}</div>
            {runs.state.phase === "disconnected" && (
              <p className={styles.errorLine} role="alert">
                {runs.state.error} The run continues on the server.{" "}
                <button type="button" className={styles.linkButton} onClick={runs.resume}>
                  Reconnect
                </button>
              </p>
            )}
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
                  <StageList current={liveStage ?? "reading"} details={stageDetails} checkingLabel={checkingLabel} reduceMotion={reduceMotion} />
                </motion.div>
              ) : run && run.stage === "complete" && run.findings.length > 0 ? (
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
                      hasGuidance={run.hasGuidance}
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
                        <span className={styles.memoDone}>
                          {memo.memo.reviewHead === run.reviewHead ? (
                            <>
                              <IconCheck /> Review memo ready
                            </>
                          ) : (
                            "Review memo predates a later review"
                          )}
                        </span>
                        <a className={styles.actionLink} href={absolute(memo.memo.htmlUrl)} target="_blank" rel="noreferrer">
                          Open
                        </a>
                        <a className={styles.actionLink} href={absolute(memo.memo.docxUrl)}>
                          Download .docx
                        </a>
                        {memo.memo.reviewHead !== run.reviewHead && (
                          <button type="button" className={styles.memoButton} onClick={() => void memo.generate(run)} disabled={memo.busy}>
                            {memo.busy ? "Writing the memo" : "Write a new memo"}
                          </button>
                        )}
                      </>
                    ) : (
                      <button type="button" className={styles.memoButton} onClick={() => void memo.generate(run)} disabled={memo.busy}>
                        {memo.busy ? "Writing the memo" : "Generate review memo"}
                      </button>
                    )}
                    {memo.error && <span className={styles.errorLine}>{memo.error}</span>}
                  </div>
                  <p className={styles.runMeta}>
                    {run.reused && <span>answered earlier for this exact question</span>}
                    <span>
                      <code>{run.model}</code> · prompt <code>{run.promptVersion}</code>
                      {run.latencyMs !== null ? ` · ${(run.latencyMs / 1000).toFixed(0)} s` : ""}
                    </span>
                    <span>every quoted passage found in the document text{run.withheld.length > 0 ? ` · ${run.withheld.length} withheld` : ""}</span>
                    {run.sectionsRead != null && doc && <span>{sectionsReadNote(run.retrievalMode, run.sectionsRead, doc.sections.length)}</span>}
                  </p>
                  {doc && <RevisionCheck key={run.id} runId={run.id} documentId={doc.id} />}
                </motion.div>
              ) : (
                <motion.div key="unresolved" className={styles.unresolved} initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={quick}>
                  {run ? (
                    <RunOutcome run={run} runError={runError} sectionsById={sectionsById} onRetry={onAsk} onEvidence={onOpenEvidence} />
                  ) : (
                    <p className={styles.errorLine} role="alert">
                      {runError}
                    </p>
                  )}
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
          placeholder="Ask a question about this contract"
          rows={1}
          maxLength={MAX_QUESTION_CHARS}
          value={composerText}
          onChange={(e) => setComposerText(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              // The same rule as the Send button: one run at a time. Enter used to start another run and abandon
              // the one on screen (sweep, 2026-10-01).
              if (!stageLabel) onAsk(composerText);
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
        onReviewed={onReviewed}
        closeRef={drawerCloseRef}
        reduceMotion={reduceMotion}
      />
    </div>
  );
}
