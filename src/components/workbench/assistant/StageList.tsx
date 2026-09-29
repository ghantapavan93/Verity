"use client";

import { motion } from "framer-motion";
import styles from "../Workbench.module.css";
import { IconCheck } from "../icons";
import { EASE } from "../shell/constants";
import { Shimmer } from "../shell/primitives";
import { STAGE_LABELS, STAGE_ORDER, type RunStage } from "@/lib/types";

/** Run progress as system state: each row is a stage the API actually passed, with what it produced. */
export function StageList({
  current,
  details,
  checkingLabel,
  reduceMotion,
}: {
  current: RunStage;
  details: Partial<Record<RunStage, string>>;
  checkingLabel: string;
  reduceMotion: boolean;
}) {
  const index = (STAGE_ORDER as readonly string[]).indexOf(current);
  const shown = index >= 0 ? STAGE_ORDER.slice(0, index + 1) : STAGE_ORDER;
  return (
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
          </motion.li>
        );
      })}
    </ol>
  );
}
