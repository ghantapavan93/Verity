"use client";

import styles from "./Views.module.css";
import type { CitationRecord } from "@/lib/types";

export interface Figure {
  label: string;
  value: number | string;
  note?: string;
  /** When set, the figure is a filter: pressing it shows only what it counts. */
  onSelect?: () => void;
  active?: boolean;
}

const grouped = new Intl.NumberFormat("en-US");

/** The numbers a screen is about, set as numerals. Counted from the rows on screen or the API's record; never estimated. */
export function Figures({ items, label }: { items: Figure[]; label: string }) {
  return (
    <div className={styles.figures} role="group" aria-label={label}>
      {items.map((item) => {
        const value = typeof item.value === "number" ? grouped.format(item.value) : item.value;
        const body = (
          <>
            <span className={styles.figureLabel}>{item.label}</span>
            <span className={`${styles.figureValue} ${item.value === 0 ? styles.figureZero : ""}`}>{value}</span>
            {item.note && <span className={styles.figureNote}>{item.note}</span>}
          </>
        );
        return item.onSelect ? (
          <button
            key={item.label}
            type="button"
            className={`${styles.figure} ${item.active ? styles.figureActive : ""}`}
            aria-pressed={!!item.active}
            onClick={item.onSelect}
          >
            {body}
          </button>
        ) : (
          <div key={item.label} className={styles.figure}>
            {body}
          </div>
        );
      })}
    </div>
  );
}

/** How a quote was found, by the tiers of backend/app/verify/spans.py, exact first and the misses last. */
const METHOD_FAMILIES: { key: string; label: string; colour: string; match: (method: string) => boolean }[] = [
  { key: "exact", label: "exact", colour: "#a6d6b8", match: (m) => m === "exact" },
  { key: "normalized", label: "spacing, quote marks or case", colour: "#7eba96", match: (m) => m === "normalized" || m === "casefold" },
  { key: "tokens", label: "word and number tokens", colour: "#5f8f74", match: (m) => m === "typed" || m === "alnum" },
  { key: "relocated", label: "in another section", colour: "#d8b46a", match: (m) => m.startsWith("relocated:") },
  { key: "unprefixed", label: "without its section label", colour: "#a8894e", match: (m) => m.startsWith("unprefixed:") },
];

/**
 * Every quoted passage the model has proposed, as one bar: how each verified quote was found, and the share that
 * was not found and was withheld. The counts are the API's citation record (GET /api/citations).
 */
export function MethodBar({ record }: { record: CitationRecord }) {
  const total = record.spans;
  if (total <= 0) return null;
  const families = METHOD_FAMILIES.map((family) => ({
    ...family,
    count: Object.entries(record.byMethod)
      .filter(([method]) => family.match(method))
      .reduce((sum, [, n]) => sum + n, 0),
  }));
  const counted = families.reduce((sum, f) => sum + f.count, 0);
  const other = record.verifiedSpans - counted;
  const missed = total - record.verifiedSpans;
  const segments = [
    ...families.filter((f) => f.count > 0),
    ...(other > 0 ? [{ key: "other", label: "other methods", colour: "#6f6c66", count: other }] : []),
    ...(missed > 0 ? [{ key: "missed", label: "not found, withheld", colour: "#e5857d", count: missed }] : []),
  ];
  const share = ((record.verifiedSpans / total) * 100).toFixed(1);
  return (
    <figure className={styles.methods} aria-label="How every quoted passage was found">
      <figcaption className={styles.methodsHead}>
        <span>
          <strong>
            {grouped.format(record.verifiedSpans)} of {grouped.format(total)}
          </strong>{" "}
          quoted passages found in the document text ({share} percent)
        </span>
        <span>
          {grouped.format(record.withheldFindings)} of {grouped.format(record.findings)} findings withheld
        </span>
      </figcaption>
      <div className={styles.methodBar} aria-hidden="true">
        {segments.map((s) => (
          <span key={s.key} style={{ flexGrow: s.count, background: s.colour }} title={`${s.count} ${s.label}`} />
        ))}
      </div>
      <ul className={styles.methodLegend}>
        {segments.map((s) => (
          <li key={s.key}>
            <i style={{ background: s.colour }} aria-hidden="true" />
            <b>{grouped.format(s.count)}</b> {s.label}
          </li>
        ))}
      </ul>
    </figure>
  );
}
