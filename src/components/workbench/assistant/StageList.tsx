"use client";

import { motion } from "framer-motion";
import { useEffect, useState } from "react";
import styles from "../Workbench.module.css";
import { IconCheck } from "../icons";
import { EASE } from "../shell/constants";
import { Shimmer } from "../shell/primitives";
import { STAGE_LABELS, STAGE_ORDER, type RunStage } from "@/lib/types";

/**
 * Seconds since the stage on screen began, counted in this browser from the moment it arrived: a clock, not a forecast.
 * Keyed by the stage, so a new stage starts a new count.
 */
function StageClock() {
  const [seconds, setSeconds] = useState(0);
  useEffect(() => {
    const start = Date.now();
    const timer = window.setInterval(() => setSeconds(Math.floor((Date.now() - start) / 1000)), 1000);
    return () => window.clearInterval(timer);
  }, []);
  return seconds > 0 ? (
    <span className={styles.stageClock} aria-hidden="true">
      {seconds} s
    </span>
  ) : null;
}

/** Run progress as system state: each row is a stage the API actually passed, with what it produced. */
export function StageList({
  current,
  details,
  checkingLabel,
  reduceMotion,
  modelPlace = null,
  modelSleeps = false,
  ahead = null,
}: {
  current: RunStage;
  details: Partial<Record<RunStage, string>>;
  checkingLabel: string;
  reduceMotion: boolean;
  /** Where the model runs, as the API said (lib/modelPlace); null says nothing about it. */
  modelPlace?: string | null;
  /** A hosted model that sleeps when idle (HealthOut.modelLocation "hosted"): the wait can include waking it. */
  modelSleeps?: boolean;
  /** Runs the API says are ahead of this one on the model (RunOut.ahead); null when it has not said. */
  ahead?: number | null;
}) {
  const index = (STAGE_ORDER as readonly string[]).indexOf(current);
  const shown = index >= 0 ? STAGE_ORDER.slice(0, index + 1) : STAGE_ORDER;
  return (
    <>
      <ol className={styles.stages} aria-label="Run progress">
        {shown.map((stage, i) => {
          const done = i < index;
          return (
            <motion.li
              key={stage}
              className={`${styles.stageRow} ${done ? styles.stageDone : ""}`}
              initial={{ opacity: 0, y: reduceMotion ? 0 : 4 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: reduceMotion ? 0 : 0.18, ease: EASE }}
            >
              <span className={styles.stageIcon}>{done ? <IconCheck /> : <Shimmer />}</span>
              <span className={styles.stageLabel}>{stage === "checking" ? checkingLabel : STAGE_LABELS[stage]}</span>
              {done && details[stage] && <span className={styles.stageDetail}>{details[stage]}</span>}
              {!done && <StageClock key={stage} />}
            </motion.li>
          );
        })}
      </ol>
      {current === "checking" && (
        <p className={styles.stageNote}>
          {modelPlace ? `The model runs on ${modelPlace}. ` : ""}
          {ahead !== null && ahead > 0
            ? // What is counted, said as counted: questions asked earlier and not yet answered. Which of them the model is
              // answering now is not known here (a later question on a shorter contract can reach it first). Under load
              // the sentence below was the only one, while thirty questions were waiting (audit, 2026-10-19).
              `${modelPlace ? "It" : "The model"} answers one question at a time, and ${ahead === 1 ? "one question" : `${ahead} questions`} asked before this one ${ahead === 1 ? "is" : "are"} still being answered. These stages are the server's own reports, not an estimate.`
            : modelSleeps
              ? // Measured on Modal, 2026-10-13: 95-168 s from asleep to the first token; awake, a run's p95 was 14.5 s.
                "It sleeps after a few idle minutes. Waking it adds 1.5 to 3 minutes to the first answer; awake, most answers take under 30 seconds. These stages are the server's own reports, not an estimate."
              : "Most answers take under two minutes. These stages are the server's own reports, not an estimate."}
        </p>
      )}
    </>
  );
}
