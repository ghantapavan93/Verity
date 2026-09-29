"use client";

import type { Dispatch, PointerEvent as ReactPointerEvent, SetStateAction } from "react";
import styles from "../Workbench.module.css";
import { DEFAULT_DOC_WIDTH, MAX_DOC_WIDTH, MIN_DOC_WIDTH } from "../hooks/useDocWidth";

/** The draggable, keyboard-operable split between the document and the Assistant. */
export function Divider({
  docWidth,
  setDocWidth,
  onPointerDown,
}: {
  docWidth: number;
  setDocWidth: Dispatch<SetStateAction<number>>;
  onPointerDown: (event: ReactPointerEvent<HTMLDivElement>) => void;
}) {
  return (
    <div
      className={styles.divider}
      role="separator"
      aria-orientation="vertical"
      aria-label="Resize document and Assistant"
      aria-valuenow={Math.round(docWidth)}
      aria-valuemin={MIN_DOC_WIDTH}
      aria-valuemax={MAX_DOC_WIDTH}
      tabIndex={0}
      title="Drag to resize · double-click to reset"
      onPointerDown={onPointerDown}
      onDoubleClick={() => setDocWidth(DEFAULT_DOC_WIDTH)}
      onKeyDown={(e) => {
        if (e.key === "ArrowLeft") setDocWidth((w) => Math.max(MIN_DOC_WIDTH, w - 2));
        if (e.key === "ArrowRight") setDocWidth((w) => Math.min(MAX_DOC_WIDTH, w + 2));
        if (e.key === "Home") setDocWidth(DEFAULT_DOC_WIDTH);
      }}
    >
      <span className={styles.dividerHandle} />
    </div>
  );
}
