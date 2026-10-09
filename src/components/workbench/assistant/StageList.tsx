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
}: {
  current: RunStage;
  details: Partial<Record<RunStage, string>>;
  checkingLabel: string;
  reduceMotion: boolean;
  /** Where the model runs, as the API said (lib/modelPlace); null says nothing about it. */
  modelPlace?: string | null;
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
          {modelPlace ? `The model runs on ${modelPlace}. ` : ""}Most answers take under two minutes; the stages above are the API&apos;s own.
        </p>
      )}
    </>
  );
}
