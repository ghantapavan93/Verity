"use client";

/**
 * Break Verity: one recorded failure, investigated.
 *
 * A real question about a real SEC exhibit, an answer that passed every check Verity's code runs, and the clause it
 * quotes word for word giving the right to someone else. Then the record behind it, the deterministic fix that held on
 * the cases it was built on and missed every unseen one, and a policy rule that caught one wrong answer and flagged a
 * right one. Everything shown is the recording (break-record.json, re-checked by backend/tests/test_break_record.py);
 * the page generates no answer, runs no model and calls no API. Adjudications are AI-assisted and say so.
 */

import Link from "next/link";
import { createContext, Fragment, useContext, useId, useMemo, useRef, useState, type KeyboardEvent, type ReactNode } from "react";

import { StatusChip } from "../workbench/shell/primitives";
import { STATUS_SOURCE_LABELS } from "@/lib/types";
import { shortHash } from "@/lib/format";
import styles from "./BreakStory.module.css";
import {
  charDiff,
  definedParties,
  firstOccurrences,
  fixScore,
  listed,
  sharedRun,
  whyMissed,
  wordsOf,
  type CaseRecord,
  type CounterCase,
  type DefinedParty,
  type PageRecord,
  type SessionRecord,
  type SpanRecord,
  type VerdictRow,
} from "./record";

// The record, trimmed on the server to what the page renders (record.ts forPage); read through this context.
const RecordContext = createContext<PageRecord | null>(null);
function useRecord(): PageRecord {
  const record = useContext(RecordContext);
  if (!record) throw new Error("BreakStory's parts need the record");
  return record;
}
const REPO = "https://github.com/ghantapavan93/Verity";
// Where the live workbench runs, fixed when the interface is built: the cloud images set NEXT_PUBLIC_HOSTING=cloud
// (deploy/cloud/Dockerfile.web); the workstation's build leaves it unset. The page says only what is true of its host.
const CLOUD = process.env.NEXT_PUBLIC_HOSTING === "cloud";
// The static mirror (NEXT_PUBLIC_EXPORT=state, backend/scripts/export_state.py) has no workbench of its own: it links
// to the live one by its full address. Everywhere else the workbench is this site's own root.
const WORKBENCH = process.env.NEXT_PUBLIC_EXPORT === "state" ? process.env.NEXT_PUBLIC_WORKBENCH_URL || "/" : "/";
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

/** "10 Oct 2026, 11:55 UTC": the same on the server and in every browser. */
function utc(iso: string): string {
  const d = new Date(iso);
  return `${d.getUTCDate()} ${MONTHS[d.getUTCMonth()]} ${d.getUTCFullYear()}, ${String(d.getUTCHours()).padStart(2, "0")}:${String(d.getUTCMinutes()).padStart(2, "0")} UTC`;
}

const SESSION_NAME: Record<string, string> = { v1: "Session 1", v2: "Session 2", s1: "Session 1", s2: "Session 2" };
const SESSION_SHORT: Record<string, string> = { v1: "S1", v2: "S2", s1: "S1", s2: "S2" };

// ------------------------------------------------------------------------------------------------- sources

/** Where each number and claim on the page comes from, in the order the Sources list numbers them. */
const SOURCE_ORDER = ["filing", "record", "cases", "labels", "verdicts", "repeats", "trace"] as const;
type SourceId = (typeof SOURCE_ORDER)[number];

function Cite({ id }: { id: SourceId }) {
  const n = SOURCE_ORDER.indexOf(id) + 1;
  return (
    <sup className={styles.cite}>
      <a href={`#source-${id}`} aria-label={`Source ${n}`}>
        {n}
      </a>
    </sup>
  );
}

// ------------------------------------------------------------------------------------------------- small parts

/**
 * Text with the expected answer's words marked and each defined party boxed (solid for the first, dashed for the
 * second). Both are display aids found by text search on the record; neither is a check.
 */
function Annotated({ text, run, boxes }: { text: string; run: { start: number; end: number } | null; boxes: { start: number; end: number; kind: number }[] }) {
  // Boxes within [from, to), each clipped to it, between plain text.
  const boxed = (from: number, to: number) => {
    const pieces: ReactNode[] = [];
    let at = from;
    for (const b of boxes) {
      const [start, end] = [Math.max(b.start, from), Math.min(b.end, to)];
      if (start >= end) continue;
      if (at < start) pieces.push(<Fragment key={at}>{text.slice(at, start)}</Fragment>);
      pieces.push(
        <span key={start} className={b.kind === 0 ? styles.partyFirst : styles.partySecond}>
          {text.slice(start, end)}
        </span>,
      );
      at = end;
    }
    if (at < to) pieces.push(<Fragment key={at}>{text.slice(at, to)}</Fragment>);
    return pieces;
  };
  // The expected answer's words stay one mark, as before the boxes, with any box inside it.
  if (!run) return <>{boxed(0, text.length)}</>;
  return (
    <>
      {boxed(0, run.start)}
      <mark className={styles.mark}>{boxed(run.start, run.end)}</mark>
      {boxed(run.end, text.length)}
    </>
  );
}

/** Who is who in the quoted clause: each party's definition, as the expected answer cites it, and that answer's reading. */
function RoleKey({ parties, conditions }: { parties: DefinedParty[]; conditions: string[] }) {
  return (
    <div className={styles.roleKey} aria-label="Who is who in this clause" role="group">
      <p className={styles.roleKeyTitle}>Who is who</p>
      <ul className={styles.roleList}>
        {parties.map((p, i) => (
          <li key={p.term}>
            <span className={i === 0 ? styles.swatchFirst : styles.swatchSecond} aria-hidden="true" />
            <span>
              <strong>{p.term}</strong> is defined in “{p.heading}”: <q>{p.definition}</q>
            </span>
          </li>
        ))}
      </ul>
      {conditions.length > 0 && (
        <p className={styles.roleReading}>
          The pre-registered conditions, written before the run: {conditions.map((c, i) => [i > 0 ? " · " : "", <q key={c}>{c}</q>])}
          <Cite id="cases" />
        </p>
      )}
      <p className={styles.roleNote}>
        Boxes drawn by this page with a text search: in the quote for each defined term, in the answer for the name it defines. Who holds the right is the
        pre-registered reading; no released code checks it.
      </p>
    </div>
  );
}

function SessionSwitch({ sessions, value, onChange, label }: { sessions: { session: string }[]; value: number; onChange: (i: number) => void; label: string }) {
  return (
    <div className={styles.switch} role="group" aria-label={label}>
      {sessions.map((s, i) => (
        <button key={s.session} type="button" className={styles.switchButton} aria-pressed={i === value} onClick={() => onChange(i)}>
          {SESSION_NAME[s.session] ?? s.session}
        </button>
      ))}
    </div>
  );
}

function Section({ id, kicker, title, children }: { id: string; kicker: string; title: string; children: ReactNode }) {
  return (
    <section id={id} className={styles.section} aria-labelledby={`${id}-title`}>
      <p className={styles.kicker}>{kicker}</p>
      <h2 id={`${id}-title`} className={styles.h2}>
        {title}
      </h2>
      {children}
    </section>
  );
}

function labelWord(label: string): string {
  return label === "wrong_party" ? "Wrong party" : label === "correct" ? "Correct" : "No party named";
}

// ------------------------------------------------------------------------------------------------- 1. the failure

function Failure({ headline }: { headline: CaseRecord }) {
  const first = headline.sessions[0];
  const span = first.finding.spans[0];
  const run = sharedRun(
    span.quote,
    headline.decisivePassages.map((p) => p.quote),
  );
  const heading = headline.sections[span.sectionId]?.heading ?? span.citedSectionLabel;
  const sameAnswer = new Set(headline.sessions.map((s) => s.finding.conclusion)).size === 1;
  // Who is who: the parties' definitions the expected answer cites from outside the quoted clause (display aids, record.ts).
  const parties = definedParties(headline, span.sectionId);
  const quoteBoxes = firstOccurrences(
    span.quote,
    parties.map((p, kind) => ({ phrase: p.term, kind })),
  );
  const answerBoxes = firstOccurrences(
    first.finding.conclusion,
    parties.map((p, kind) => ({ phrase: p.name, kind })),
  );
  const reading = headline.requiredConditions.filter((c) => parties.length > 1 && parties.every((p) => c.includes(p.term) || c.includes(p.name)));
  const premise = headline.expectedAnswer
    .split(/(?<=\.)\s+/)
    .slice(0, 2)
    .join(" ");
  const recordedUnder = String(first.options.policy_version);
  return (
    <section className={styles.hero} aria-labelledby="failure-title" id="failure">
      <p className={styles.kicker}>Break Verity · one recorded failure</p>
      <h1 id="failure-title" className={styles.h1}>
        A real clause, quoted word for word.
        <span className={styles.h1Quiet}> The right given to the wrong party.</span>
      </h1>
      <p className={styles.lead}>This answer passed every check Verity&apos;s code runs. The clause it quotes gives the right to someone else.</p>

      <figure className={styles.exhibit} aria-label="The question, the answer and the quote it cites">
        <div className={styles.exhibitQuestion}>
          <span className={styles.label}>Question</span>
          <p className={styles.question}>{headline.question}</p>
          {headline.family === "false_premise" && (
            <p className={styles.premise}>
              <span className={styles.premiseTag}>Planted false premise</span> The question was written wrong on purpose, before the run. The pre-registered
              answer begins: <q>{premise}</q>
              <Cite id="cases" />
            </p>
          )}
        </div>

        <div className={styles.exhibitAnswer}>
          <div className={styles.answerHead}>
            <span className={styles.label}>Answer</span>
            <StatusChip status={first.finding.status} hasGuidance={false} source={first.finding.statusSource} />
            <code className={styles.statusCode}>status: {first.finding.status}</code>
          </div>
          <p className={styles.answer}>
            <Annotated text={first.finding.conclusion} run={null} boxes={answerBoxes} />
          </p>
        </div>

        <div className={styles.exhibitQuote}>
          <span className={styles.labelDark}>The quote it cites · {heading}</span>
          <blockquote className={styles.paperQuote}>
            <Annotated text={span.quote} run={run} boxes={quoteBoxes} />
          </blockquote>
          {run && <p className={styles.markNote}>Marked: the words the pre-registered expected answer cites.</p>}
          {parties.length > 0 && <RoleKey parties={parties} conditions={reading} />}
        </div>

        <ul className={styles.checks} aria-label="What was checked">
          <li className={styles.checkOk}>
            <span className={styles.checkIcon} aria-hidden="true">
              ✓
            </span>
            <span>
              <strong>Found in the contract.</strong> Code located the quote at characters {span.start}–{span.end} of its section
              <Cite id="record" />. Found means the words are there. It does not mean they support the answer.
            </span>
            <span className={styles.by}>code</span>
          </li>
          <li className={styles.checkOk}>
            <span className={styles.checkIcon} aria-hidden="true">
              ✓
            </span>
            <span>
              <strong>No unsupported value.</strong> The released value rule (policy-v6), run again on this answer by the page&apos;s tests, decides it as
              recorded: every value it states is in the verified quote. The run itself was recorded under {recordedUnder}, policy-v6 plus the rejected party
              check, which did not fire on it
              <Cite id="record" />.
            </span>
            <span className={styles.by}>code</span>
          </li>
          <li className={styles.checkMiss}>
            <span className={styles.checkIcon} aria-hidden="true">
              ✗
            </span>
            <span>
              <strong>Who holds the right.</strong> Not checked by the released code (policy-v6). The experimental party check that ran on this answer passed it
              too
              <Cite id="verdicts" />.
            </span>
            <span className={styles.byNone}>not code</span>
          </li>
        </ul>

        <div className={styles.verdict}>
          <span className={styles.verdictWord}>{labelWord(first.adjudication.label)}</span>
          <span className={styles.verdictBy}>
            AI-assisted adjudication, blind
            <Cite id="labels" />
          </span>
          <p className={styles.verdictNote}>{first.adjudication.note}</p>
        </div>
      </figure>

      <section className={styles.matters} aria-labelledby="matters-title">
        <h2 id="matters-title" className={styles.mattersTitle}>
          Why it matters
        </h2>
        <p>
          A reader acting on this answer would plan an objection the agreement does not give Axogen, and miss what it does say:{" "}
          {/* The headline's pre-registered conditions in their recorded order: the delivery terms, then the objection right and finality. */}
          {headline.requiredConditions.slice(2).join("; ")}
          <Cite id="cases" />. The answer carries a real quote and no warning, so a quick triage may not escalate it.
        </p>
        <p className={styles.mattersNote}>Illustrative: what the clause implies for someone who relies on the answer, not a reported incident.</p>
      </section>

      <p className={styles.provenance}>
        {headline.source.title.toLowerCase().replace(/^\w/, (c) => c.toUpperCase())} · {headline.source.company.replace(/\s+\(CIK.*$/, "")} ·{" "}
        {headline.source.form} filed {headline.source.filingDate} ·{" "}
        <a href={headline.source.url} target="_blank" rel="noreferrer">
          the filing on SEC EDGAR
        </a>
        <Cite id="filing" /> · asked in {headline.sessions.length} separate model sessions{sameAnswer ? ", the same answer both times" : ""}
        <Cite id="record" />
      </p>
    </section>
  );
}

// ------------------------------------------------------------------------------------------------- 2. the investigation

const TABS = [
  { id: "input", name: "Input" },
  { id: "retrieval", name: "Retrieved" },
  { id: "output", name: "Output" },
  { id: "boundary", name: "What code checked" },
  { id: "adjudication", name: "Adjudication" },
] as const;
type TabId = (typeof TABS)[number]["id"];

function Tabs({ value, onChange, children }: { value: TabId; onChange: (t: TabId) => void; children: ReactNode }) {
  const base = useId();
  const refs = useRef<(HTMLButtonElement | null)[]>([]);
  const onKey = (event: KeyboardEvent<HTMLDivElement>) => {
    const i = TABS.findIndex((t) => t.id === value);
    const next =
      event.key === "ArrowRight"
        ? (i + 1) % TABS.length
        : event.key === "ArrowLeft"
          ? (i - 1 + TABS.length) % TABS.length
          : event.key === "Home"
            ? 0
            : event.key === "End"
              ? TABS.length - 1
              : -1;
    if (next < 0) return;
    event.preventDefault();
    onChange(TABS[next].id);
    refs.current[next]?.focus();
  };
  return (
    <>
      <div className={styles.tabs} role="tablist" aria-label="The record" onKeyDown={onKey}>
        {TABS.map((t, i) => (
          <button
            key={t.id}
            ref={(el) => {
              refs.current[i] = el;
            }}
            type="button"
            role="tab"
            id={`${base}-tab-${t.id}`}
            aria-selected={t.id === value}
            aria-controls={`${base}-panel`}
            tabIndex={t.id === value ? 0 : -1}
            className={styles.tab}
            onClick={() => onChange(t.id)}
          >
            <span className={styles.tabNumber} aria-hidden="true">
              {i + 1}
            </span>
            {t.name}
          </button>
        ))}
      </div>
      <div className={styles.panel} role="tabpanel" id={`${base}-panel`} aria-labelledby={`${base}-tab-${value}`} tabIndex={0}>
        {children}
      </div>
    </>
  );
}

function Pre({ text, label }: { text: string; label: string }) {
  const [open, setOpen] = useState(false);
  const long = text.length > 1400;
  return (
    <div className={styles.preWrap}>
      <pre className={`${styles.pre} ${long && !open ? styles.preClipped : ""}`} role="region" aria-label={label} tabIndex={0}>
        {text}
      </pre>
      {long && (
        <button type="button" className={styles.textButton} aria-expanded={open} onClick={() => setOpen((o) => !o)}>
          {open ? "Show less" : `Show all ${text.length.toLocaleString("en-US")} characters`}
        </button>
      )}
    </div>
  );
}

function InputPanel({ c, s }: { c: CaseRecord; s: SessionRecord }) {
  const record = useRecord();
  const opts = s.options;
  return (
    <div className={styles.stack}>
      <p className={styles.panelLead}>
        Exactly what the model was sent: the prompt&apos;s instructions, then the question and the six sections retrieval chose.
      </p>
      <dl className={styles.facts}>
        <div>
          <dt>Model</dt>
          <dd>
            {s.model} via {s.provider}
          </dd>
        </div>
        <div>
          <dt>Prompt</dt>
          <dd>
            {s.promptVersion} <code>{shortHash(s.promptHash)}</code>
          </dd>
        </div>
        <div>
          <dt>Decoding</dt>
          <dd>
            temperature {String(opts.temperature)}, seed {String(opts.seed)}
          </dd>
        </div>
        <div>
          <dt>Input</dt>
          <dd>{s.inputTokens?.toLocaleString("en-US")} tokens</dd>
        </div>
      </dl>
      <h3 className={styles.h4}>System</h3>
      <Pre text={c.input.system} label="The system message" />
      <h3 className={styles.h4}>User</h3>
      <Pre text={c.input.user} label="The user message" />
      <p className={styles.hashLine}>
        <span className={styles.hashTag}>sha256</span> <code>{c.input.sha256}</code>
        <br />
        Rebuilt from the record and equal to the hash the run recorded when it called the model
        <Cite id="record" />. {(record.masking.inInput > 0 || record.masking.names > 0) && <span>{maskingNote(record.masking)}</span>}
      </p>
    </div>
  );
}

function RetrievalPanel({ c, s }: { c: CaseRecord; s: SessionRecord }) {
  const cited = new Set(s.finding.spans.map((sp) => sp.sectionId));
  const [chosen, setChosen] = useState<string>(s.finding.spans[0]?.sectionId ?? s.retrieval[0]?.sectionId);
  const section = c.sections[chosen];
  const span = s.finding.spans.find((sp) => sp.sectionId === chosen) ?? null;
  return (
    <div className={styles.retrieval}>
      <ol className={styles.slices} aria-label="Sections handed to the model, in rank order">
        {s.retrieval.map((r) => (
          <li key={r.sectionId}>
            <button type="button" className={styles.slice} aria-pressed={r.sectionId === chosen} onClick={() => setChosen(r.sectionId)}>
              <span className={styles.sliceRank}>{r.rank}</span>
              <span className={styles.sliceHeading}>{r.heading || r.label}</span>
              <span className={styles.sliceMeta}>
                {r.characters.toLocaleString("en-US")} chars{r.truncated ? ", cut at the window" : ""}
                {cited.has(r.sectionId) && <span className={styles.citedTag}>quoted</span>}
              </span>
            </button>
          </li>
        ))}
      </ol>
      <div className={styles.paper} role="region" aria-label={`Section text: ${section?.heading ?? ""}`} tabIndex={0}>
        <p className={styles.paperHeading}>{section?.heading}</p>
        {section && section.text.length > 0 ? (
          <p className={styles.paperText}>
            {span ? (
              <>
                {section.text.slice(0, span.start)}
                <mark className={styles.paperMark}>{section.text.slice(span.start, span.end)}</mark>
                {section.text.slice(span.end)}
              </>
            ) : (
              section.text
            )}
          </p>
        ) : (
          <p className={styles.paperEmpty}>This section is a heading with no text of its own; the model was handed it empty.</p>
        )}
      </div>
    </div>
  );
}

function OutputPanel({ s }: { s: SessionRecord }) {
  const pretty = useMemo(() => {
    try {
      return JSON.stringify(JSON.parse(s.rawOutput), null, 2);
    } catch {
      return s.rawOutput;
    }
  }, [s.rawOutput]);
  return (
    <div className={styles.stack}>
      <p className={styles.panelLead}>
        The model&apos;s output as stored, unedited. It cited <code>{s.proposal.evidence.map((e) => e.citedLabel).join(", ")}</code> and hinted{" "}
        <code>{s.proposal.statusHint}</code>. {s.outputTokens} tokens, {Math.round(s.latencyMs / 1000)} s, {utc(s.createdAt)}.
      </p>
      <Pre text={pretty} label="The model's raw output" />
    </div>
  );
}

function BrowserCheck({ c, span }: { c: CaseRecord; span: SpanRecord }) {
  const [result, setResult] = useState<ReturnType<typeof check> | null>(null);
  function check() {
    const text = c.sections[span.sectionId].text.slice(span.start, span.end);
    const words = wordsOf(text);
    const quoteWords = wordsOf(span.quote);
    const diff = charDiff(text, span.quote);
    const changed =
      diff.left.filter((p) => p.changed).reduce((n, p) => n + p.text.length, 0) + diff.right.filter((p) => p.changed).reduce((n, p) => n + p.text.length, 0);
    const onlyPunctuation = [...diff.left, ...diff.right].filter((p) => p.changed).every((p) => !/[\p{L}\p{N}]/u.test(p.text));
    return { sameWords: words.join(" ") === quoteWords.join(" "), words: words.length, changed, onlyPunctuation, diff };
  }
  return (
    <div className={styles.browserCheck}>
      <button type="button" className={styles.actionButton} onClick={() => setResult(check())}>
        Check it in your browser
      </button>
      <div aria-live="polite">
        {result && (
          <div className={styles.checkResult}>
            <p className={result.sameWords ? styles.resultOk : styles.resultBad}>
              {result.sameWords
                ? `Same ${result.words} words in the same order. ${result.changed === 0 ? "No character differs." : `${result.changed} characters differ${result.onlyPunctuation ? ", all punctuation" : ""}.`}`
                : "The words differ: this quote would not be found at these offsets."}
            </p>
            <div className={styles.diffGrid}>
              <div>
                <span className={styles.label}>
                  The contract, characters {span.start}–{span.end}
                </span>
                <p className={styles.diffText}>
                  {result.diff.left.map((p, i) =>
                    p.changed ? (
                      <ins key={i} className={styles.diffMark}>
                        {p.text}
                      </ins>
                    ) : (
                      <span key={i}>{p.text}</span>
                    ),
                  )}
                </p>
              </div>
              <div>
                <span className={styles.label}>The model&apos;s quote</span>
                <p className={styles.diffText}>
                  {result.diff.right.map((p, i) =>
                    p.changed ? (
                      <ins key={i} className={styles.diffMark}>
                        {p.text}
                      </ins>
                    ) : (
                      <span key={i}>{p.text}</span>
                    ),
                  )}
                </p>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

const TIER: Record<string, string> = {
  exact: "the same characters",
  typed: "the same words in the same order; punctuation and quote marks may differ",
  normalized: "the same text once whitespace and quote marks are normalised",
};

function BoundaryPanel({ c, s }: { c: CaseRecord; s: SessionRecord }) {
  const span = s.finding.spans[0];
  const tier = span.method.replace(/^relocated:/, "");
  return (
    <div className={styles.boundary}>
      <div className={styles.boundaryCol}>
        <h3 className={styles.h4}>Checked by code</h3>
        <ul className={styles.boundaryList}>
          <li>
            <strong>The quote is in the contract.</strong> Located in “{c.sections[span.sectionId]?.heading}”, characters {span.start}–{span.end}, matched as{" "}
            <code>{span.method}</code>: {TIER[tier] ?? tier}.{" "}
            {span.matchCount == null ? "How many times it occurs was not recorded." : `Found ${span.matchCount} time${span.matchCount === 1 ? "" : "s"}.`}
            <BrowserCheck c={c} span={span} />
          </li>
          <li>
            <strong>Every value the answer states is in a verified quote.</strong> The released value rule (policy-v6), run again on this answer by the
            page&apos;s tests, decides it as recorded. The run was recorded under {String(s.options.policy_version)}: policy-v6 plus the rejected party check,
            which did not fire on it.
          </li>
          <li>
            <strong>Who set the status.</strong> {STATUS_SOURCE_LABELS[s.finding.statusSource] ?? s.finding.policy.summary}.
          </li>
        </ul>
      </div>
      <div className={`${styles.boundaryCol} ${styles.boundaryOut}`}>
        <h3 className={styles.h4}>Not checked by the released code</h3>
        <ul className={styles.boundaryList}>
          <li>Who holds the right or owes the duty.</li>
          <li>Whether the answer carries every condition and exception.</li>
          <li>Whether the question&apos;s premise is true.</li>
        </ul>
        <p className={styles.boundaryNote}>Each of these is a reading. This failure lives here.</p>
      </div>
    </div>
  );
}

function AdjudicationPanel({ c, s }: { c: CaseRecord; s: SessionRecord }) {
  return (
    <div className={styles.stack}>
      <div className={styles.verdictRow}>
        <span className={styles.verdictWord}>{labelWord(s.adjudication.label)}</span>
        {s.adjudication.premiseAccepted && <span className={styles.tagWarn}>accepted the question&apos;s false premise</span>}
      </div>
      <p className={styles.verdictNote}>{s.adjudication.note}</p>
      <h3 className={styles.h4}>
        The expected answer, written before any run
        <Cite id="cases" />
      </h3>
      <p className={styles.expected}>{c.expectedAnswer}</p>
      <h3 className={styles.h4}>Conditions a correct answer carries</h3>
      <ul className={styles.conditions}>
        {c.requiredConditions.map((r) => (
          <li key={r}>{r}</li>
        ))}
      </ul>
      <p className={styles.method}>
        AI-assisted, not a lawyer&apos;s review. One Claude agent wrote this case and its expected answer from the contract before any model run. Another
        labelled each answer against it, without seeing any check&apos;s verdict
        <Cite id="labels" />.
      </p>
    </div>
  );
}

function Investigation({ headline }: { headline: CaseRecord }) {
  const [session, setSession] = useState(0);
  const [tab, setTab] = useState<TabId>("input");
  const s = headline.sessions[session];
  const sameInput = new Set(headline.sessions.map((x) => x.recordedInputSha256)).size === 1;
  return (
    <Section id="investigate" kicker="The investigation" title="Every step of that answer is on record.">
      <div className={styles.recordBar}>
        <SessionSwitch sessions={headline.sessions} value={session} onChange={setSession} label="Model session" />
        <p className={styles.recordMeta}>
          run <code>{s.runId}</code> · {utc(s.createdAt)}
        </p>
      </div>
      <Tabs value={tab} onChange={setTab}>
        {tab === "input" && <InputPanel c={headline} s={s} />}
        {tab === "retrieval" && <RetrievalPanel key={s.runId} c={headline} s={s} />}
        {tab === "output" && <OutputPanel s={s} />}
        {tab === "boundary" && <BoundaryPanel key={s.runId} c={headline} s={s} />}
        {tab === "adjudication" && <AdjudicationPanel c={headline} s={s} />}
      </Tabs>
      <div className={styles.replay}>
        <div>
          <h3 className={styles.h3}>Replaying the record</h3>
          <p>
            Everything above is the stored record; only email addresses and the names of people the story does not need are masked. Nothing on this page asks a
            model anything, so opening it twice shows the same answer.
          </p>
        </div>
        <div>
          <h3 className={styles.h3}>Asking the model again</h3>
          <p>
            A new call is a new answer.{" "}
            {sameInput ? "Session 2 sent the identical input (same hash) and got the same wrong answer: two calls, one answer." : ""} That is not guaranteed: 8
            of 18 identical requests in an earlier measurement came back different
            <Cite id="repeats" />.
          </p>
        </div>
      </div>
    </Section>
  );
}

// ------------------------------------------------------------------------------------------------- 3. the rejected fix

function Score({ caught, of, label, tone }: { caught: number; of: number; label: string; tone: "good" | "bad" | "plain" }) {
  return (
    <div className={`${styles.score} ${tone === "good" ? styles.scoreGood : tone === "bad" ? styles.scoreBad : ""}`}>
      <span className={styles.scoreValue}>
        {caught}
        <span className={styles.scoreOf}> of {of}</span>
      </span>{" "}
      <span className={styles.scoreLabel}>{label}</span>
    </div>
  );
}

function VerdictCase({ rows }: { rows: VerdictRow[] }) {
  const [open, setOpen] = useState(false);
  const id = useId();
  const first = rows[0];
  return (
    <li className={styles.verdictItem}>
      <button type="button" className={styles.verdictButton} aria-expanded={open} aria-controls={id} onClick={() => setOpen((o) => !o)}>
        <span className={styles.verdictCase}>{first.case}</span>
        <span className={styles.sessionVerdicts}>
          {rows.map((r) => (
            <span key={r.finding} className={r.flagged ? styles.caught : styles.missed}>
              <span aria-hidden="true">{SESSION_SHORT[r.session]} </span>
              <span className="visually-hidden">{SESSION_NAME[r.session]}: </span>
              {r.flagged ? "caught" : "missed"}
            </span>
          ))}
        </span>
        <span className={styles.verdictConclusion}>{first.conclusion}</span>
      </button>
      {open && (
        <div id={id} className={styles.verdictDetail}>
          {rows.map((r) => (
            <div key={r.finding} className={styles.sessionVerdict}>
              <span className={styles.verdictCase}>
                {SESSION_NAME[r.session]} · {r.flagged ? "caught" : "missed"}
              </span>
              <span>{r.conclusion}</span>
              <span className={styles.dim}>{whyMissed(r)}</span>
            </div>
          ))}
          <p className={styles.dim}>Parties it read from the contract&apos;s opening: {listed(first.parties) || "none"}.</p>
          <p>
            <strong>Adjudication</strong> <span className={styles.dim}>(AI-assisted)</span>: {first.labelNote}
          </p>
          {first.quotes && first.quotes.length > 0 && <blockquote className={styles.smallQuote}>{first.quotes[0]}</blockquote>}
          <p className={styles.dim}>
            Question: {first.question} ·{" "}
            <a href={first.source} target="_blank" rel="noreferrer">
              contract on SEC EDGAR
            </a>
          </p>
        </div>
      )}
    </li>
  );
}

/** One evaluation set of the rejected check: its score in questions, then in findings, then its verdict per question. */
function FixSide({ set, title, note }: { set: VerdictRow["set"]; title: string; note: string }) {
  const record = useRecord();
  const rows = record.rejectedFix.rows;
  const score = fixScore(rows, set);
  const wrong = rows.filter((r) => r.set === set && r.label === "wrong_party");
  const byCase = [...new Set(wrong.map((r) => r.case))]
    .sort((a, b) => a.localeCompare(b, "en", { numeric: true }))
    .map((c) => wrong.filter((r) => r.case === c).sort((a, b) => a.session.localeCompare(b.session)));
  const headingId = useId();
  return (
    <section className={styles.fixSide} aria-labelledby={headingId}>
      <h3 id={headingId} className={styles.fixSideTitle}>
        {title}
      </h3>
      <p className={styles.fixSideNote}>{note}</p>
      <Score
        caught={score.caughtEverySession}
        of={score.questions}
        label="wrong-party questions caught in every session"
        tone={score.caughtEverySession > 0 ? "good" : "bad"}
      />
      <p className={styles.fixCounts}>
        {score.caughtFindings} of {score.findings} wrong-party findings caught across both sessions (a session can give a question more than one finding).
        Correct findings it lowered: {score.loweredFindings} of {score.correctFindings}.
      </p>
      <ul className={styles.verdictList} aria-label={`${title}: each question and the check's verdict`}>
        {byCase.map((caseRows) => (
          <VerdictCase key={caseRows[0].case} rows={caseRows} />
        ))}
      </ul>
    </section>
  );
}

function RejectedFix() {
  const record = useRecord();
  const fix = record.rejectedFix;
  const built = fixScore(fix.rows, "diagnostic");
  const unseen = fixScore(fix.rows, "unseen");
  const unseenMisses = fix.rows.filter((r) => r.set === "unseen" && r.label === "wrong_party" && !r.flagged);
  // In cases, not answers: each unseen case was asked once per session, so a case missed twice is one case.
  const missedCases = (why?: string) => new Set(unseenMisses.filter((r) => why === undefined || r.why === why).map((r) => r.case)).size;
  return (
    <Section
      id="fix"
      kicker="The rejected fix"
      title={`A check that caught ${built.caughtEverySession} of the ${built.questions} wrong-party questions it was built on, and ${unseen.caughtAnySession === 0 ? "missed every new one" : `${unseen.caughtEverySession} of ${unseen.questions} new ones`}.`}
    >
      <p className={styles.body}>
        The idea: read the parties from the contract&apos;s opening clause, find who acts in the answer and who acts in the quote, and lower the pass when they
        differ. Deterministic and cheap. Below are its verdicts, run again from its own code over the recorded answers
        <Cite id="verdicts" />, against the AI-assisted labels
        <Cite id="labels" />.
      </p>
      <p className={styles.fixSummary}>
        Wrong-party questions caught in every session. Built on: {built.caughtEverySession} of {built.questions}. Unseen: {unseen.caughtEverySession} of{" "}
        {unseen.questions}.
      </p>
      <div className={styles.fixSides}>
        <FixSide
          set="diagnostic"
          title="Cases it was built on"
          note="Written first; the check was revised against them. A score here says what it was tuned to do."
        />
        <FixSide
          set="unseen"
          title="Unseen cases"
          note={`Written afterwards by a separate annotator agent, on contracts the check itself had never read. ${unseenSummary(unseen.caughtFindings, unseen.findings, unseen.questions)}`}
        />
      </div>
      <div className={styles.why}>
        <h3 className={styles.h3}>Why it did not generalise</h3>
        <p>
          On the unseen cases, {missedCases("no_actor_in_answer")} of {missedCases()} missed cases had no party of the opening acting in the answer: the answer
          named its actor by a bank&apos;s name where the opening&apos;s list holds only a defined role. In the other {missedCases("actor_also_in_quote")}, the
          party the answer wrongly names also appears in the quote, though not as the one who holds the right. In this page&apos;s headline the real holder, the
          Stockholders&apos; Representative, is not among the parties the check read at all. Telling those apart is reading roles, which is the model&apos;s job
          and a reviewer&apos;s to check; a longer pattern list would be fitting these cases.
        </p>
        <p className={styles.decision}>
          Not adopted. Kept on the unpublished branch <code>party-check-experiment</code>, commit <code>{shortHash(fix.commit, 7)}</code>; its verdict on every
          answer is in this page&apos;s record.
        </p>
      </div>
    </Section>
  );
}

// ------------------------------------------------------------------------------------------------- 4. the counterexample

const FIGURE = /\$\s?\d+(?:[,.]\d+)*(?:\s?(?:million|billion))?/gi;

function Figures({ text }: { text: string }) {
  const parts: ReactNode[] = [];
  let last = 0;
  for (const m of text.matchAll(FIGURE)) {
    parts.push(text.slice(last, m.index));
    parts.push(
      <mark key={m.index} className={styles.figure}>
        {m[0]}
      </mark>,
    );
    last = (m.index ?? 0) + m[0].length;
  }
  parts.push(text.slice(last));
  return <>{parts}</>;
}

function RuleCard({
  title,
  tone,
  c,
  s,
  explanation,
  children,
}: {
  title: string;
  tone: "good" | "bad" | "plain";
  c: CounterCase;
  s: CounterCase["sessions"][number];
  explanation: string;
  children?: ReactNode;
}) {
  return (
    <article className={`${styles.ruleCard} ${tone === "good" ? styles.ruleGood : tone === "bad" ? styles.ruleBad : ""}`}>
      <p className={styles.ruleTitle}>{title}</p>
      {children}
      <span className={styles.label}>Question</span>
      <p className={styles.ruleQuestion}>
        <Figures text={c.question} />
      </p>
      <span className={styles.label}>Answer</span>
      <p className={styles.ruleAnswer}>
        <Figures text={s.finding.conclusion} />
      </p>
      <div className={styles.ruleStatus}>
        <StatusChip status={s.finding.status} hasGuidance={false} source={s.finding.statusSource} />
        {s.finding.statusReason ? (
          <span>{s.finding.statusReason}</span>
        ) : (
          <span>kept: the released value rule, run again by the page&apos;s tests, lowers nothing</span>
        )}
      </div>
      <span className={styles.label}>Its quotes · {s.finding.spans.length}</span>
      {s.finding.spans.map((sp) => (
        <blockquote key={`${sp.sectionId}-${sp.start}`} className={styles.smallQuote}>
          <Figures text={sp.quote} />
        </blockquote>
      ))}
      <p className={styles.ruleVerdict}>
        <strong>{labelWord(s.adjudication.label)}</strong> <span className={styles.dim}>(AI-assisted)</span>. {s.adjudication.note}
      </p>
      <p className={styles.ruleExplain}>{explanation}</p>
      <p className={styles.dim}>
        <a href={c.source.url} target="_blank" rel="noreferrer">
          {c.source.title.toLowerCase().replace(/^\w/, (ch) => ch.toUpperCase())} on SEC EDGAR
        </a>
      </p>
    </article>
  );
}

function Counterexample() {
  const { caught, falseAlarm } = useRecord().counterexample;
  const [alarmSession, setAlarmSession] = useState(falseAlarm.sessions.findIndex((s) => s.finding.status !== "pass"));
  const alarm = falseAlarm.sessions[alarmSession];
  return (
    <Section id="counterexample" kicker="The counterexample" title="One rule, one catch, one false alarm.">
      <p className={styles.body}>
        Policy-v6 lowers a pass when the answer states a value that no verified quote states. A figure taken from the question counts as unsupported: the
        question is what the reader asked, not what the contract says.
      </p>
      <div className={styles.ruleGrid}>
        <RuleCard
          title="Caught, for the wrong reason"
          tone="good"
          c={caught}
          s={caught.sessions[0]}
          explanation="The rule caught the $6 million the answer repeated from the question. The error that matters, giving the Company's election to Allegro, is one it cannot see."
        />
        <RuleCard
          title={alarm.finding.status === "pass" ? "Kept: its quote states the figure" : "A correct answer, flagged"}
          tone={alarm.finding.status === "pass" ? "plain" : "bad"}
          c={falseAlarm}
          s={alarm}
          explanation={
            alarm.finding.status === "pass"
              ? "Its first sentence is the other session's, and here the model also quoted the fee clause, which states $1,500,000, so the released value rule, run again by the page's tests, lowers nothing. The rule judges values only: this answer's added credit-bid sentence is garbled, as the adjudication notes."
              : "The answer is right that Lilly's subsidiary does not pay. But its quotes never state the $1.5 million, so the rule cannot tell a true figure from a repeated premise."
          }
        >
          <SessionSwitch sessions={falseAlarm.sessions} value={alarmSession} onChange={setAlarmSession} label="Model session for this question" />
        </RuleCard>
      </div>
      <p className={styles.setNote}>
        Across every recorded store, this rule lowered 11 passes: 5 had accepted a false premise, 3 answered wrongly or incompletely, and 3 were correct. Every
        way code could tell those 3 apart also released a valid warning, so the rule stands as it is
        <Cite id="trace" />.
      </p>
    </Section>
  );
}

// ------------------------------------------------------------------------------------------------- 5. your turn

function YourTurn() {
  return (
    <Section id="your-turn" kicker="Your turn" title="Try to break it with a contract of your own.">
      <div className={styles.turn}>
        <div>
          <p className={styles.body}>
            Add a public contract, ask a question, and open the evidence: every quote is located in the text, and the drawer says what code checked and what it
            did not. In Runs, each run downloads as an evidence pack: its record, its quotes and the hashes to check them.
          </p>
          <p className={styles.dim}>
            {CLOUD
              ? "The workbench runs live on one small cloud server, and the model on a GPU that starts when a question arrives: the first answer after a quiet spell can take a minute or two, and each answer usually half a minute or more. This page is a recording and works either way."
              : "The workbench runs live on one laptop with one GPU: each answer waits on the model, usually half a minute or more, and when the laptop is off so is the workbench. This page is a recording and works either way."}
          </p>
          <Link href={WORKBENCH} className={styles.primaryLink}>
            Open the workbench
          </Link>
        </div>
        <aside className={styles.warning} aria-label="Before you upload">
          <p className={styles.warningTitle}>Use public or synthetic contracts only.</p>
          <p>
            Do not upload confidential, privileged or personal documents. Verity does not detect sensitive content and does not refuse it: what you add is
            stored on the Verity server, in a workspace only your browser can open.
          </p>
        </aside>
      </div>
    </Section>
  );
}

// ------------------------------------------------------------------------------------------------- sources

function Sources({ headline }: { headline: CaseRecord }) {
  const record = useRecord();
  const ev = record.evaluation;
  const runs = headline.sessions.map((s) => s.runId).join(" and ");
  const items: Record<SourceId, ReactNode> = {
    filing: (
      <>
        {headline.source.company}, {headline.source.form}, accession {headline.source.accession}, {headline.source.exhibit}:{" "}
        <a href={headline.source.url} target="_blank" rel="noreferrer">
          {headline.source.url}
        </a>
        . The filing up to the script tag SEC appends to each response hashes to <code>{shortHash(headline.source.sha256Filing)}</code> (sha256), as downloaded
        for the corpus and as SEC served it when checked in a browser on 11 Oct 2026 (UTC). Converted to text by the corpus&apos;s converter (
        {headline.source.conversion.tool}, not in this repository); the text Verity read hashes to <code>{shortHash(headline.source.sha256Tested)}</code>, the
        same hash its runs record.
      </>
    ),
    record: (
      <>
        Runs {runs}, recorded on {utc(headline.sessions[0].createdAt).replace(/,.*$/, "")} by Verity&apos;s own pipeline (qwen3:8b on a local GPU) in evaluation
        stores separate from the public demo. Exported through the API&apos;s run detail and explanation by <code>backend/scripts/export_break_record.py</code>;
        every quote is located again and the value rule run again by <code>backend/tests/test_break_record.py</code>. Recorded under policy-v7, which is
        policy-v6 plus the rejected party check; that check fired on none of the answers shown.
      </>
    ),
    cases: (
      <>
        Pre-registered cases, <code>{ev.cases.file}</code> (sha256 <code>{shortHash(ev.cases.sha256)}</code>), and the first set{" "}
        <code>{ev.diagnosticCases.file}</code> (<code>{shortHash(ev.diagnosticCases.sha256)}</code>): written by separate Claude agents from the contracts
        before any run, each quote checked as an exact substring of the document. The files are not published; the question, answer, quotes and label of every
        case this page shows are in its record, and the headline&apos;s expected answer.
      </>
    ),
    labels: (
      <>
        AI-assisted labels: Claude agents, one per set, labelled each of the {record.rejectedFix.rows.length} answers (both sets, both sessions) as correct,
        wrong party or no party named, against the pre-registered answer, without seeing any check&apos;s verdict.{" "}
        {record.rejectedFix.rows.filter((r) => r.label === "wrong_party").length} were wrong party. Labels <code>{ev.diagnosticLabels.file}</code> (
        <code>{shortHash(ev.diagnosticLabels.sha256)}</code>) and <code>{ev.labels.file}</code> (<code>{shortHash(ev.labels.sha256)}</code>). Not a
        lawyer&apos;s review.
      </>
    ),
    verdicts: (
      <>
        <code>{record.rejectedFix.function}</code> at commit <code>{record.rejectedFix.commit}</code> ({record.rejectedFix.policy}, on the unpublished branch{" "}
        <code>party-check-experiment</code>), run over every recorded answer; file <code>{ev.verdicts.file}</code> (<code>{shortHash(ev.verdicts.sha256)}</code>
        ). Its verdict on each answer, with the parties it read, is in this page&apos;s record.
      </>
    ),
    repeats: (
      <>
        The same request under the same identity (prompt hash, seed 42, temperature 0, model digest) in a new model session gave a different answer in 8 of 18
        cases.{" "}
        <a href={`${REPO}/blob/main/DECISIONS.md`} target="_blank" rel="noreferrer">
          DECISIONS.md
        </a>
        , 10 Oct 2026.
      </>
    ),
    trace: (
      <>
        The question-figure rule traced over every recorded store, with each way to separate the correct answers and what it released.{" "}
        <a href={`${REPO}/blob/main/DECISIONS.md`} target="_blank" rel="noreferrer">
          DECISIONS.md
        </a>
        , &ldquo;The question-figure rule&apos;s false positive, traced&rdquo;.
      </>
    ),
  };
  return (
    <section className={styles.sources} aria-labelledby="sources-title">
      <h2 id="sources-title" className={styles.h3}>
        Sources
      </h2>
      <ol>
        {SOURCE_ORDER.map((id) => (
          <li key={id} id={`source-${id}`}>
            {items[id]}
          </li>
        ))}
      </ol>
    </section>
  );
}

// ------------------------------------------------------------------------------------------------- the page

const NAV = [
  ["failure", "The failure"],
  ["investigate", "Investigation"],
  ["fix", "Rejected fix"],
  ["counterexample", "Counterexample"],
  ["your-turn", "Your turn"],
] as const;

/**
 * The unseen score in questions, not findings: each question was asked once per session, and a session can give more
 * than one finding, so "0 of 8" would count the same four questions twice (first-visit review, m9; m10 review).
 */
export function unseenSummary(caught: number, findings: number, questions: number): string {
  if (caught === 0)
    return questions === 1
      ? "It missed the one wrong-party question, in both sessions."
      : `It caught none of the ${questions} wrong-party questions, in either session.`;
  return `It caught ${caught} of ${findings} wrong-party findings across both sessions, over ${questions} question${questions === 1 ? "" : "s"}.`;
}

/** What the exporter masked in the headline's input, or nothing when it masked nothing. */
function maskingNote({ inInput, names }: { inInput: number; names: number }): string {
  const masked = [
    inInput > 0 && `email addresses in the contract's notice clause (${inInput} places)`,
    names > 0 && "the names of its notice contacts and signatories",
  ]
    .filter(Boolean)
    .join(", and ");
  return `${masked.charAt(0).toUpperCase()}${masked.slice(1)} are masked here; the hash covers the record as stored.`;
}

export function BreakStory({ record }: { record: PageRecord }) {
  const headline = record.headline;
  return (
    <RecordContext.Provider value={record}>
      <div className={styles.page}>
        <header className={styles.top}>
          <Link href="/" className={styles.brand}>
            Verity
          </Link>
          <nav aria-label="Sections" className={styles.nav}>
            {NAV.map(([id, name]) => (
              <a key={id} href={`#${id}`} className={styles.navLink}>
                {name}
              </a>
            ))}
          </nav>
          <nav aria-label="Elsewhere" className={styles.navOut}>
            <Link href={WORKBENCH} className={styles.navLink}>
              Workbench
            </Link>
            <a href="/state" className={styles.navLink}>
              Research
            </a>
          </nav>
        </header>
        <main id="main" className={styles.main}>
          <Failure headline={headline} />
          <Investigation headline={headline} />
          <RejectedFix />
          <Counterexample />
          <YourTurn />
          <Sources headline={headline} />
        </main>
      </div>
    </RecordContext.Provider>
  );
}
