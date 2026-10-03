"use client";

import styles from "../Workbench.module.css";

/**
 * The comparison code made, read back from the sentence it wrote. The sentence is code's own template
 * (backend/app/policy/durations.py, `evaluate`), so the parse is exact or it is nothing: a reason that does not
 * match draws no gauge, and a comparison across units draws none either.
 */
const REASON = /^the contract provides (\d+) ([a-z ]+?)s; the guidance requires (at least|at most|exactly|between) (\d+)(?: and (\d+))? ([a-z ]+?)s$/;

export interface DayComparison {
  provided: number;
  required: number;
  ceiling: number | null;
  operator: "at least" | "at most" | "exactly" | "between";
  unit: string;
  met: boolean;
}

export function readComparison(reason: string | null | undefined): DayComparison | null {
  if (!reason) return null;
  const found = REASON.exec(reason.trim());
  if (!found) return null;
  const [, a, unitA, operator, b, top, unitB] = found;
  if (unitA !== unitB) return null;
  const provided = Number(a);
  const required = Number(b);
  const ceiling = top ? Number(top) : null;
  const met =
    operator === "at least"
      ? provided >= required
      : operator === "at most"
        ? provided <= required
        : operator === "exactly"
          ? provided === required
          : ceiling !== null && provided >= required && provided <= ceiling;
  return { provided, required, ceiling, operator: operator as DayComparison["operator"], unit: unitA, met };
}

/**
 * One axis, both numbers on it: the guidance's bound as a brass line, the contract's figure as a dot, and the gap
 * between them drawn, so the arithmetic in the sentence above is also a picture. The picture decides nothing.
 */
export function DayGauge({ comparison }: { comparison: DayComparison }) {
  const { provided, required, ceiling, operator, unit, met } = comparison;
  const top = Math.max(provided, ceiling ?? required) * 1.2 || 1;
  const pct = (n: number) => `${Math.min(100, Math.max(0, (n / top) * 100))}%`;
  const gap = Math.abs(provided - required);
  const words = met
    ? gap === 0
      ? `meets the ${operator === "at most" ? "ceiling" : "floor"} exactly`
      : `${gap} ${unit}s inside the guidance`
    : operator === "at most"
      ? `${gap} ${unit}s over the ceiling`
      : `${gap} ${unit}s short`;
  const boundName = operator === "at most" ? "ceiling" : operator === "exactly" ? "required" : "floor";
  const low = Math.min(provided, required);
  const high = Math.max(provided, required);
  return (
    <figure
      className={styles.gauge}
      aria-label={`The contract provides ${provided} ${unit}s; the guidance requires ${operator} ${required}${ceiling !== null ? ` and ${ceiling}` : ""} ${unit}s: ${words}.`}
    >
      <div className={styles.gaugeAxis} aria-hidden="true">
        {ceiling !== null && <span className={styles.gaugeBand} style={{ left: pct(required), width: `calc(${pct(ceiling)} - ${pct(required)})` }} />}
        <span
          className={`${styles.gaugeGap} ${met ? styles.gaugeGapMet : styles.gaugeGapShort}`}
          style={{ left: pct(low), width: `calc(${pct(high)} - ${pct(low)})` }}
        />
        <span className={styles.gaugeBound} style={{ left: pct(required) }}>
          <b>{required}</b>
          <i>{ceiling !== null ? "from" : boundName}</i>
        </span>
        {ceiling !== null && (
          <span className={styles.gaugeBound} style={{ left: pct(ceiling) }}>
            <b>{ceiling}</b>
            <i>to</i>
          </span>
        )}
        <span className={`${styles.gaugeDot} ${met ? styles.gaugeDotMet : styles.gaugeDotShort}`} style={{ left: pct(provided) }}>
          <b>{provided}</b>
          <i>contract</i>
        </span>
      </div>
      <figcaption className={`${styles.gaugeWords} ${met ? styles.gaugeWordsMet : styles.gaugeWordsShort}`}>{words}</figcaption>
    </figure>
  );
}
