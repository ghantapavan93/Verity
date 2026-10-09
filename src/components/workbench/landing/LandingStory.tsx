"use client";

import { motion, useInView } from "framer-motion";
import { useEffect, useRef, useState, type ReactNode } from "react";
import styles from "./Landing.module.css";
import { IconArrowRight } from "../icons";
import type { CitationRecord, DocumentSummary, FindingView, RunSummary } from "@/lib/types";

const EASE = [0.16, 1, 0.3, 1] as const;
const grouped = new Intl.NumberFormat("en-US");

/** A number that counts up once it is on screen. Under reduced motion it is simply the number. */
function CountUp({ value, reduceMotion }: { value: number; reduceMotion: boolean }) {
  const ref = useRef<HTMLSpanElement>(null);
  const seen = useInView(ref, { once: true, margin: "-40px" });
  const [shown, setShown] = useState(reduceMotion ? value : 0);
  useEffect(() => {
    if (!seen || reduceMotion) return;
    const started = performance.now();
    const duration = 1100;
    let frame = 0;
    const tick = (now: number) => {
      const t = Math.min(1, (now - started) / duration);
      const eased = 1 - Math.pow(1 - t, 3);
      setShown(Math.round(value * eased));
      if (t < 1) frame = window.requestAnimationFrame(tick);
    };
    frame = window.requestAnimationFrame(tick);
    return () => window.cancelAnimationFrame(frame);
  }, [seen, value, reduceMotion]);
  return <span ref={ref}>{grouped.format(reduceMotion ? value : shown)}</span>;
}

/** A block that rises into view once, as the reader reaches it. Inside a list it is the list item itself. */
function Reveal({
  children,
  delay = 0,
  reduceMotion,
  className,
  as = "div",
}: {
  children: ReactNode;
  delay?: number;
  reduceMotion: boolean;
  className?: string;
  as?: "div" | "li";
}) {
  const Tag = as === "li" ? motion.li : motion.div;
  return (
    <Tag
      className={className}
      initial={reduceMotion ? false : { opacity: 0, y: 18 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, margin: "-60px" }}
      transition={{ duration: 0.7, delay, ease: EASE }}
    >
      {children}
    </Tag>
  );
}

const Stroke = ({ children }: { children: ReactNode }) => (
  <svg
    width="20"
    height="20"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="1.6"
    strokeLinecap="round"
    strokeLinejoin="round"
    aria-hidden="true"
  >
    {children}
  </svg>
);

/**
 * The record as a pipeline: every stage a question passes through, with the count the API keeps for it. The counts
 * are the store's own (GET /api/engineering/citations and /api/documents); nothing here is estimated.
 */
export function RecordPipeline({
  citations,
  documents,
  reduceMotion,
}: {
  citations: CitationRecord | null;
  documents: DocumentSummary[] | null;
  reduceMotion: boolean;
}) {
  const reviewed = documents ? documents.reduce((n, d) => n + d.reviewedFindings, 0) : null;
  const sections = documents ? documents.reduce((n, d) => n + d.sections, 0) : null;
  const nodes: { label: string; value: number | null; note: string; icon: ReactNode; tone?: "accent" | "bad" | "pass" }[] = [
    {
      label: "Contracts",
      value: documents?.length ?? null,
      note: sections !== null ? `${grouped.format(sections)} sections read` : "read into sections",
      icon: (
        <Stroke>
          <path d="M7 3h7l5 5v13H7z" />
          <path d="M14 3v5h5M10 13h6M10 17h6" />
        </Stroke>
      ),
    },
    {
      label: "Questions",
      value: citations?.runs ?? null,
      note: "runs where the model answered",
      icon: (
        <Stroke>
          <path d="M4 5h16v11H9l-5 4z" />
          <path d="M9 9h6M9 12h4" />
        </Stroke>
      ),
    },
    {
      label: "Model proposed",
      value: citations?.spans ?? null,
      note: "quoted passages",
      icon: (
        <Stroke>
          <path d="M5 6h14M5 10h14M5 14h9M5 18h6" />
        </Stroke>
      ),
    },
    {
      label: "Code found",
      value: citations?.verifiedSpans ?? null,
      note: "in the document text",
      tone: "accent",
      icon: (
        <Stroke>
          <circle cx="11" cy="11" r="6" />
          <path d="m20 20-4-4M8.5 11l2 2 3.5-4" />
        </Stroke>
      ),
    },
    {
      label: "Code withheld",
      value: citations ? citations.spans - citations.verifiedSpans : null,
      note: citations ? `${grouped.format(citations.withheldFindings)} findings held back` : "not found, not shown",
      tone: "bad",
      icon: (
        <Stroke>
          <path d="M5 6h14M5 10h14M5 14h9" />
          <path d="M4 19 20 5" />
        </Stroke>
      ),
    },
    {
      label: "A person decided",
      value: reviewed,
      note: "confirmed or dismissed, under a name",
      tone: "pass",
      icon: (
        <Stroke>
          <circle cx="12" cy="8" r="3.5" />
          <path d="M5 20a7 7 0 0 1 14 0" />
        </Stroke>
      ),
    },
  ];
  const tones = { accent: styles.nodeAccent, bad: styles.nodeBad, pass: styles.nodePass };
  return (
    <section className={styles.story} aria-labelledby="pipeline-title">
      <Reveal reduceMotion={reduceMotion}>
        <p className={styles.kicker}>
          <span className={styles.kickerRule} />
          The record so far
        </p>
        <h2 id="pipeline-title" className={styles.storyTitle}>
          Every question passes through the same six hands.
        </h2>
        <p className={styles.storyLead}>The counts are the store&apos;s own, read from the API when this page opened. They move as the record grows.</p>
      </Reveal>
      <ol className={styles.pipeline} aria-label="The record as a pipeline">
        {nodes.map((node, i) => (
          <motion.li
            key={node.label}
            className={`${styles.node} ${node.tone ? tones[node.tone] : ""}`}
            initial={reduceMotion ? false : { opacity: 0, y: 14 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true, margin: "-40px" }}
            transition={{ duration: 0.55, delay: 0.08 * i, ease: EASE }}
          >
            {i > 0 && (
              <motion.span
                className={styles.nodeLink}
                aria-hidden="true"
                initial={reduceMotion ? false : { scaleX: 0 }}
                whileInView={{ scaleX: 1 }}
                viewport={{ once: true, margin: "-40px" }}
                transition={{ duration: 0.5, delay: 0.08 * i + 0.1, ease: EASE }}
              />
            )}
            <span className={styles.nodeIcon}>{node.icon}</span>
            <span className={styles.nodeValue}>
              {node.value === null ? <span className={styles.nodeWaiting}>reading</span> : <CountUp value={node.value} reduceMotion={reduceMotion} />}
            </span>
            <span className={styles.nodeLabel}>{node.label}</span>
            <span className={styles.nodeNote}>{node.note}</span>
          </motion.li>
        ))}
      </ol>
    </section>
  );
}

/** The hero run, told in four steps, each a door into the exact place in the product where that step is on the record. */
export function OneRun({
  proof,
  lead,
  onOpen,
  reduceMotion,
}: {
  proof: RunSummary;
  lead: FindingView | null;
  onOpen: (runId: string, findingId?: string) => void;
  reduceMotion: boolean;
}) {
  const observed = lead?.observed ?? "60 days' written notice";
  const required = lead?.required ?? "at least 90 days";
  const steps = [
    {
      n: "01",
      title: "A question is asked with guidance beside it",
      text: `${proof.question} The team's rule: ${proof.hasGuidance ? "written guidance was attached to the run" : "no guidance was attached"}.`,
      link: "Open the run",
      finding: false,
    },
    {
      n: "02",
      title: "The model proposes, and quotes the contract",
      text: `It read ${observed} against ${required}, called the clause within guidance, and cited a section. Its exact words are kept as its own.`,
      link: "See what it proposed",
      finding: true,
    },
    {
      n: "03",
      title: "Code checks the quote, then the arithmetic",
      text: lead?.statusReason
        ? `The quote was found verbatim, in a different section from the one cited. Then: ${lead.statusReason}. Needs review.`
        : "The quote was found verbatim, in a different section from the one cited. Then code compared the days and set the status.",
      link: "See what code decided",
      finding: true,
    },
    {
      n: "04",
      title: "A person has the last word",
      text: lead?.review
        ? `${lead.review.reviewer} ${lead.review.verdict === "confirmed" ? "confirmed" : "dismissed"} the finding. The decision is kept with the run, and the memo names it.`
        : "A reviewer confirms or dismisses the finding. The decision is kept with the run, under their name.",
      link: "See the decision",
      finding: true,
    },
  ];
  return (
    <section className={styles.story} aria-labelledby="one-run-title">
      <Reveal reduceMotion={reduceMotion}>
        <p className={styles.kicker}>
          <span className={styles.kickerRule} />
          One run, end to end
        </p>
        <h2 id="one-run-title" className={styles.storyTitle}>
          The model missed a 90 day floor. <span className={styles.titleQuiet}>Here is each hand it passed through.</span>
        </h2>
      </Reveal>
      <ol className={styles.steps}>
        {steps.map((step, i) => (
          <Reveal key={step.n} as="li" delay={0.07 * i} reduceMotion={reduceMotion} className={styles.step}>
            <span className={styles.stepIndex} aria-hidden="true">
              {step.n}
            </span>
            <h3 className={styles.stepTitle}>{step.title}</h3>
            <p className={styles.stepText}>{step.text}</p>
            <button type="button" className={styles.stepLink} onClick={() => onOpen(proof.id, step.finding ? (lead?.id ?? undefined) : undefined)}>
              {step.link} <IconArrowRight />
            </button>
          </Reveal>
        ))}
      </ol>
    </section>
  );
}

/** What Verity will not do, stated as plainly as what it does. Each line is a property of the code, not a promise. */
const COUNT_WORDS = ["None", "One", "Two", "Three", "Four", "Five"];

/** The fourth refusal is about where a contract's text goes, so it is said only once the API has said where its model
 * runs (lib/modelPlace), and said truthfully for a hosted one. */
function whereItGoes(place: { hosted: boolean; place: string } | null): { head: string; text: string } | null {
  if (!place) return null;
  const record = "The run keeps the hash of every input, and the evidence pack checks itself without this service.";
  return place.hosted
    ? {
        head: "It sends the contract to its model and nowhere else.",
        text: `The model runs on ${place.place}: the question, the guidance and the sections retrieval chose go there to be answered. ${record}`,
      }
    : { head: "It does not send the contract anywhere.", text: `The model runs on ${place.place}. ${record}` };
}

export function Refusals({ reduceMotion, place }: { reduceMotion: boolean; place: { hosted: boolean; place: string } | null }) {
  const lines = [
    {
      head: "It does not read the whole agreement.",
      text: "Six sections per question, chosen by retrieval. Every answer says how many it was handed, and the memo repeats it.",
    },
    {
      head: "It does not pass a clause on its own.",
      text: "A pass is the model's proposal. Code confirms it only when the quote, the guidance and the day counts agree; a shortfall is code's call alone.",
    },
    {
      head: "It does not hide a miss.",
      text: "A quote code cannot find in the document is withheld and shown struck through, beside the model's words, not deleted.",
    },
    whereItGoes(place),
  ].filter((line): line is { head: string; text: string } => line !== null);
  return (
    <section className={styles.story} aria-labelledby="refusals-title">
      <Reveal reduceMotion={reduceMotion}>
        <p className={styles.kicker}>
          <span className={styles.kickerRule} />
          Said plainly
        </p>
        <h2 id="refusals-title" className={styles.storyTitle}>
          {COUNT_WORDS[lines.length]} things it refuses to do.
        </h2>
      </Reveal>
      <ul className={styles.refusals}>
        {lines.map((line, i) => (
          <Reveal key={line.head} as="li" delay={0.06 * i} reduceMotion={reduceMotion} className={styles.refusal}>
            <h3 className={styles.refusalHead}>{line.head}</h3>
            <p className={styles.refusalText}>{line.text}</p>
          </Reveal>
        ))}
      </ul>
    </section>
  );
}
