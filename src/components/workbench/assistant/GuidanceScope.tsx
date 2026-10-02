"use client";

import { AnimatePresence, motion } from "framer-motion";
import styles from "../Workbench.module.css";
import { IconClose, IconPlus } from "../icons";
import { transitions } from "../shell/constants";
import type { GuidanceController } from "../hooks/useGuidance";

/** The first words of the guidance, so the chip says what the run is checked against rather than that something is. */
function excerpt(text: string, max = 44): string {
  const line = text.replace(/\s+/g, " ").trim();
  return line.length > max ? `${line.slice(0, max - 1).trimEnd()}…` : line;
}

/** The scope line under the Assistant title: the document chip and the guidance chip with its popover. */
export function GuidanceScope({ documentName, guidance, reduceMotion }: { documentName: string; guidance: GuidanceController; reduceMotion: boolean }) {
  const { quick } = transitions(reduceMotion);
  return (
    <>
      <div className={styles.scope}>
        <span className={styles.scopeLabel}>Scope</span>
        <span className={styles.chip}>{documentName}</span>
        {guidance.guidance ? (
          <span className={styles.chip}>
            <button
              type="button"
              className={styles.chipText}
              onClick={() => guidance.setOpen((o) => !o)}
              aria-expanded={guidance.open}
              aria-label={`Legal instructions: ${guidance.guidance.text}`}
              title={guidance.guidance.text}
            >
              {excerpt(guidance.guidance.text)}
            </button>
            <button type="button" className={styles.chipRemove} aria-label="Remove legal instructions" onClick={guidance.remove}>
              <IconClose />
            </button>
          </span>
        ) : (
          <button type="button" className={`${styles.chip} ${styles.chipGhost}`} onClick={() => guidance.setOpen((o) => !o)} aria-expanded={guidance.open}>
            <IconPlus /> Add guidance
          </button>
        )}
      </div>
      <AnimatePresence initial={false}>
        {guidance.open && (
          <motion.div
            className={styles.popover}
            initial={{ opacity: 0, y: -6, scale: 0.98 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: -6, scale: 0.98 }}
            transition={quick}
          >
            <label className={styles.popoverLabel} htmlFor="guidance">
              Legal guidance
            </label>
            <textarea
              id="guidance"
              className={styles.popoverInput}
              rows={3}
              autoFocus
              value={guidance.draft}
              onChange={(e) => guidance.setDraft(e.target.value)}
              placeholder="Paste a playbook rule, a lawyer's note or a review instruction"
            />
            <div className={styles.popoverBar}>
              <span className={styles.popoverHint}>Applies to every question in this scope</span>
              <div className={styles.popoverActions}>
                <button type="button" className={styles.ghostButton} onClick={() => guidance.setOpen(false)}>
                  Cancel
                </button>
                <button type="button" className={styles.primaryButton} onClick={() => void guidance.apply()} disabled={guidance.busy}>
                  {guidance.busy ? "Saving" : "Use"}
                </button>
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </>
  );
}
