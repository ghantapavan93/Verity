"use client";

/**
 * One contract changes. What doesn't need to move?
 *
 * The contract-state experiment's recording, told in five moments: the funnel from every derived object to what one
 * arrival actually changed; one real relationship and the certificate that says why it was safe; one recorded arrival
 * step by step; the predecessor engine beside it; and the relationship audit that did not pass. Every number comes
 * from the record the API reads (contract-state/2, its own sha256 checked on load); this component computes nothing
 * but sums and differences of recorded counts, and says so where it does.
 */

import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import styles from "./StateStory.module.css";
import { errorMessage, getContractState } from "@/lib/api";
import { shortHash } from "@/lib/format";
import type { ContractStateView, StateArrivalView } from "@/lib/types";

const grouped = new Intl.NumberFormat("en-US");
const fmt = (n: number | null | undefined, digits = 0) =>
  n === null || n === undefined ? "–" : new Intl.NumberFormat("en-US", { maximumFractionDigits: digits, minimumFractionDigits: digits }).format(n);

// ---------------------------------------------------------------------------------------------- the record's shapes

interface Certificate {
  support: {
    reference: [string | null, string | null];
    cited_span: string;
    target: string;
    target_sha256: string;
    target_type: string | null;
    target_date: string | null;
    principal: string | null;
    target_role: string;
    citation: string;
    relation: string;
    direction: [string, string];
  };
  guard: {
    reference: [string | null, string | null];
    satisfying_texts: number;
    narrowed_by: string[];
    guarded_dates: string[];
    documents_under_guard: Record<string, number>;
  };
  scope: { id: string };
  rule: string;
  reads: number;
  bucket_baseline_reads: number;
  candidates_adjudicated: number;
  certificate_sha256: string;
  replayed: string;
}

interface ArrivalRun {
  edge_mode: string;
  arrivals: number;
  adjudications_mean: number;
  text_reads_mean: number;
  impact_envelope_mean: number;
  recompute_plan_mean: number;
  state_delta_mean: number;
  edges: {
    edges_revalidated: number;
    edge_value_changed: number;
    edge_value_and_certificate_unchanged: number;
    edge_certificate_changed_value_unchanged: number;
  } | null;
  wall_seconds_p50: number;
  final_check: { state_equal_to_rebuild: boolean; objects_differing: number } | null;
  rebuild: { objects: number; adjudications: number; wall_seconds: number };
}

interface MutationTotals {
  scenarios: number;
  focal_outcomes_met: number;
  final_state_equal_to_oracle: number;
  missed_invalidations: number;
  unnecessary_invalidations: number;
  relationships_revalidated: number;
}

interface MutationScenario {
  scenario: string;
  expect: string;
  control: boolean;
  why: string;
  modes: Record<string, { focal_outcome_met: boolean; final_state_equal_to_oracle: boolean; missed_invalidations: number; unnecessary_invalidations: number }>;
}

interface Evidence {
  featured_arrival?: number;
  comparison?: {
    arrivals?: Record<string, ArrivalRun | null>;
    refilings?: Record<string, { recompute_plan_total: number; verified: number; verified_state_equal: number; changed_outside_envelope: number } | null>;
  };
  mutations?: { suite?: string; totals?: Record<string, MutationTotals>; scenarios?: MutationScenario[]; expectations_hold_on_the_oracle?: boolean };
  relationship_audit?: {
    metrics?: Record<string, number | null>;
    gates?: Record<string, string>;
    pairs?: number;
    readers_related?: number;
    ambiguous_rate?: number;
  };
  relationship_misses?: { counts?: Record<string, number>; misses?: { pair: string; class: string; what: string }[]; candidate_generation?: string };
  authorization?: {
    cross_scope_leakage_observations?: number;
    changes_in_room_0?: number;
    r1_objects_in_envelope?: number;
    naive_global_then_filter_leaks?: Record<string, number>;
  };
  revisions?: {
    doc_hash_invalidated_total?: number;
    doc_hash_disturbed_without_change_total?: number;
    doc_hash_missed_changes_total?: number;
    recompute_plan_total?: number;
    events?: number;
  };
  crash_resume?: { all_byte_identical?: boolean; records_written_twice?: number; links_differing_from_unbroken_run?: number; population?: string };
  faults?: { applicable?: number; rejected?: number; escaped?: number; stale?: number; dominated?: number };
}

const KIND_WORDS: Record<string, [string, string]> = {
  EDGE: ["relationship", "relationships"],
  FAMILY: ["family", "families"],
  EFFECTIVE: ["effective state", "effective states"],
  FINDING: ["finding", "findings"],
  MEMBER: ["collection membership", "collection memberships"],
  COLLECTION: ["collection", "collections"],
  TEMPLATES: ["template block", "template blocks"],
  DEVIATION: ["deviation", "deviations"],
  COHORT: ["cohort", "cohorts"],
};

function kinds(byKind: Record<string, number> | undefined): string {
  const order = Object.keys(KIND_WORDS);
  return Object.entries(byKind ?? {})
    .filter(([, n]) => n > 0)
    .sort(([a], [b]) => order.indexOf(a) - order.indexOf(b))
    .map(([k, n]) => `${grouped.format(n)} ${(KIND_WORDS[k] ?? [k.toLowerCase(), k.toLowerCase()])[n === 1 ? 0 : 1]}`)
    .join(" · ");
}

const SMALL = new Set(["to", "of", "and", "the", "a", "an", "for", "in", "on", "by"]);

/** EDGAR titles arrive in capitals; set them in title case for reading. The record keeps them as filed. */
function titled(text: string | null | undefined): string {
  if (!text) return "–";
  return text
    .toLowerCase()
    .split(/(\s+)/)
    .map((w, i) => (i > 0 && SMALL.has(w) ? w : w.replace(/^([a-z])/, (c) => c.toUpperCase())))
    .join("")
    .replace(/\bNo\.\s/g, "No. ");
}

function longDate(iso: string | null | undefined): string {
  if (!iso) return "undated";
  const d = new Date(`${iso}T00:00:00Z`);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleDateString("en-US", { year: "numeric", month: "long", day: "numeric", timeZone: "UTC" });
}

/**
 * The recorded sentence, cut around the words that name the agreement; those words are marked only when the year they
 * carry is the reference's own. A recorded snippet can end before the reference and name the source instead ("… is made
 * as of December 15, 2006" for a 2005 agreement); it is then shown unmarked (2026-10-08: arrivals 30, 37 and 49).
 */
function citation(text: string, type: string | null, referenceDate: string | null): { before: string; marked: string; after: string } {
  const words = (type ?? "")
    .split(/\s+/)
    .filter(Boolean)
    .map((w) => w.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"));
  const year = (referenceDate ?? "").slice(0, 4);
  const pattern = words.length ? new RegExp(`${words.join("\\s+")}[^.;]{0,90}?\\b((?:19|20)\\d{2})\\b`, "gi") : null;
  const match = pattern ? [...text.matchAll(pattern)].find((m) => m[1] === year) : undefined;
  if (!match || match.index === undefined) return { before: text, marked: "", after: "" };
  // cut at word boundaries, so the excerpt never starts or ends inside a word
  let start = Math.max(0, match.index - 150);
  if (start > 0) start = text.indexOf(" ", start) + 1 || start;
  let end = Math.min(text.length, match.index + match[0].length + 40);
  if (end < text.length) end = Math.max(match.index + match[0].length, text.lastIndexOf(" ", end));
  return {
    before: `${start > 0 ? "…" : ""}${text.slice(start, match.index)}`,
    marked: match[0],
    after: `${text.slice(match.index + match[0].length, end)}${end < text.length ? "…" : ""}`,
  };
}

// ---------------------------------------------------------------------------------------------- small parts

function Tone({ ok, children }: { ok: boolean; children: React.ReactNode }) {
  return <span className={`${styles.tone} ${ok ? styles.tonePass : styles.toneFail}`}>{children}</span>;
}

function Section({ id, kicker, title, children }: { id: string; kicker: string; title: string; children: React.ReactNode }) {
  return (
    <section id={id} className={styles.section} aria-labelledby={`${id}-title`}>
      <div className={styles.kicker}>{kicker}</div>
      <h2 id={`${id}-title`} className={styles.h2}>
        {title}
      </h2>
      {children}
    </section>
  );
}

// ---------------------------------------------------------------------------------------------- the page

function readArrival(count: number, featured: number): number {
  if (typeof window === "undefined") return featured;
  const raw = new URLSearchParams(window.location.search).get("arrival");
  const n = raw === null ? NaN : Number(raw);
  return Number.isInteger(n) && n >= 1 && n <= count ? n - 1 : featured;
}

export function StateStory({ initial }: { initial?: ContractStateView }) {
  const [view, setView] = useState<ContractStateView | null>(initial ?? null);
  const [failure, setFailure] = useState<string | null>(null);
  const [chosen, setChosen] = useState<number | null>(null);

  const fetchRecord = useCallback(() => {
    getContractState()
      .then(setView)
      .catch((error) => setFailure(errorMessage(error)));
  }, []);

  useEffect(() => {
    if (!initial) fetchRecord();
  }, [initial, fetchRecord]);

  const retry = useCallback(() => {
    setFailure(null);
    fetchRecord();
  }, [fetchRecord]);

  // A shared link to a section (#audit) arrives before the record does, so the browser had nowhere to scroll: land on it
  // once, when the record has rendered, and never again on later renders.
  const landed = useRef(false);
  useEffect(() => {
    if (landed.current || !view?.available) return;
    landed.current = true;
    const id = decodeURIComponent(window.location.hash.slice(1));
    if (id) document.getElementById(id)?.scrollIntoView({ behavior: "auto", block: "start" });
  }, [view]);

  const evidence = (view?.evidence ?? {}) as Evidence;
  const featured = Math.min(Math.max(evidence.featured_arrival ?? 0, 0), Math.max((view?.arrivals.length ?? 1) - 1, 0));
  // The arrival shown: the one the reader chose, else the one the URL names, else the record's featured arrival.
  const index = view?.available ? (chosen ?? readArrival(view.arrivals.length, featured)) : null;

  const choose = useCallback((i: number) => {
    setChosen(i);
    const url = new URL(window.location.href);
    url.searchParams.set("arrival", String(i + 1));
    window.history.replaceState(null, "", url.toString());
  }, []);

  const arrival: StateArrivalView | null = view?.available && index !== null ? (view.arrivals[index] ?? null) : null;

  if (failure) {
    return (
      <Shell>
        <div className={styles.notice} role="alert">
          <h1 className={styles.noticeTitle}>The recorded evidence did not load.</h1>
          <p>{failure}</p>
          <button type="button" className={styles.button} onClick={retry}>
            Try again
          </button>
        </div>
      </Shell>
    );
  }
  if (!view) {
    return (
      <Shell>
        <p className={styles.loading} role="status">
          Loading the recorded evidence…
        </p>
      </Shell>
    );
  }
  if (!view.available || !view.summary || !view.portfolio) {
    return (
      <Shell>
        <div className={styles.notice} role="alert">
          <h1 className={styles.noticeTitle}>The contract-state record is not connected.</h1>
          <p>{view.detail}</p>
        </div>
      </Shell>
    );
  }

  return (
    <Shell provenance={view}>
      <Hero view={view} evidence={evidence} />
      {arrival && <CertificateMoment arrival={arrival} />}
      {arrival && <ArrivalMoment view={view} arrival={arrival} index={index ?? 0} featured={featured} onChoose={choose} />}
      <ComparisonMoment evidence={evidence} />
      <AuditMoment evidence={evidence} />
      <AuthorizationMoment evidence={evidence} />
      <EngineeringView view={view} evidence={evidence} arrival={arrival} />
    </Shell>
  );
}

const NAV = [
  ["certificate", "Why it works"],
  ["arrival", "One arrival"],
  ["comparison", "Predecessor"],
  ["audit", "What didn't pass"],
  ["authorization", "Scopes"],
  ["engineering", "Engineering"],
] as const;

function Shell({ children, provenance }: { children: React.ReactNode; provenance?: ContractStateView }) {
  return (
    <div className={styles.page}>
      <header className={styles.top}>
        <Link className={styles.brand} href="/">
          Verity
        </Link>
        <nav aria-label="Sections" className={styles.nav}>
          {NAV.map(([id, label]) => (
            <a key={id} href={`#${id}`} className={styles.navLink}>
              {label}
            </a>
          ))}
        </nav>
      </header>
      <main id="main" className={styles.main}>
        {children}
      </main>
      {provenance && (
        <footer className={styles.footer}>
          <p>
            Recorded by the contract-state experiment{provenance.sourceCommit ? ` at commit ${shortHash(provenance.sourceCommit, 7)}` : ""}. Replayed here from{" "}
            <code>{provenance.source}</code>
            {provenance.sha256 ? (
              <>
                {" "}
                · sha256 <code>{shortHash(provenance.sha256, 12)}</code>
              </>
            ) : null}
            {provenance.sha256Verified === true
              ? " · the file matches its hash."
              : provenance.sha256Verified === false
                ? " · THE FILE DOES NOT MATCH ITS HASH: it was edited after export."
                : "."}{" "}
            Nothing on this page is live.
          </p>
        </footer>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------------------------- 1. the funnel

function Hero({ view, evidence }: { view: ContractStateView; evidence: Evidence }) {
  const s = view.summary!;
  const cert = evidence.comparison?.arrivals?.certificate;
  const total = cert?.rebuild.objects ?? view.portfolio!.objectsAtStart;
  const steps: [string, number, string, number][] = [
    ["Derived objects", total, cert ? "what one full rebuild recomputed, in the comparison run" : "before the first recorded arrival", 0],
    ["Impact envelope", s.impactEnvelopeMean, "what one arrival could reach, on average", 0],
    ["Recompute plan", s.recomputePlanMean, "what needed another look, on average", 1],
    ["State delta", s.stateDeltaMean, "what actually changed, on average", 1],
  ];
  const top = Math.log10(total);
  return (
    <section className={styles.hero} aria-labelledby="hero-title">
      <div className={styles.kicker}>
        Recorded on {grouped.format(view.portfolio!.documentsAtStart)} real SEC exhibits · {s.arrivals} contracts arriving one at a time
      </div>
      <h1 id="hero-title" className={styles.h1}>
        One contract changes.
        <span className={styles.h1Quiet}> What doesn&rsquo;t need to move?</span>
      </h1>
      <ol className={styles.funnel} aria-label="From every derived object to what one arrival changed">
        {steps.map(([label, value, note, digits]) => (
          <li key={label} className={styles.funnelStep}>
            <span className={styles.funnelLabel}>{label}</span>
            <span className={styles.funnelValue}>{fmt(value, digits)}</span>
            <span className={styles.funnelBar} aria-hidden="true">
              <span style={{ width: `${Math.max(3, (Math.log10(Math.max(value, 1.01)) / top) * 100)}%` }} />
            </span>
            <span className={styles.funnelNote}>{note}</span>
          </li>
        ))}
      </ol>
      <p className={styles.heroClaim}>
        <strong>{s.changedOutsideEnvelope} observed changes outside the envelope.</strong> {s.verifiedStateEqual} of {s.verifiedAgainstRebuild} arrivals were
        checked object by object against a full rebuild
        {cert?.final_check?.state_equal_to_rebuild ? `, and the state after all ${s.arrivals} equals one` : ""}.
      </p>
      <p className={styles.lede}>
        Each derived result is stored with the evidence that justified it. When a document arrives, only the results whose justification it touches get another
        look. Bar lengths are on a log scale.
      </p>
    </section>
  );
}

// ---------------------------------------------------------------------------------------------- 2. the certificate

function CertificateMoment({ arrival }: { arrival: StateArrivalView }) {
  const cert = arrival.certificate as unknown as Certificate | null | undefined;
  const edge = arrival.edge;
  if (!cert || !edge?.target) {
    return (
      <Section id="certificate" kicker="Why it works" title="This arrival established no relationship.">
        <p className={styles.body}>
          {edge?.state === "ambiguous"
            ? "Two distinct texts satisfied its reference, and nothing the source states told them apart, so the engine accepted neither."
            : "No candidate satisfied its reference with every piece of evidence; it is left for review, and no certificate exists."}{" "}
          Choose another arrival below.
        </p>
      </Section>
    );
  }
  const quote = citation(edge.evidence ?? cert.support.cited_span, cert.support.reference[0], cert.support.reference[1] ?? null);
  const underGuard = cert.guard.documents_under_guard[cert.support.reference[1] ?? ""] ?? null;
  const otherDates = cert.guard.guarded_dates.filter((d) => d !== cert.support.reference[1]).length;
  return (
    <Section id="certificate" kicker="Why it works" title="The result is stored with the evidence that justified it.">
      <div className={styles.chain}>
        <article className={styles.card} aria-label="Source">
          <div className={styles.cardLabel}>Source</div>
          <h3 className={styles.cardTitle}>{titled(arrival.document.title)}</h3>
          <p className={styles.meta}>
            {arrival.document.filerName ?? arrival.document.filer} · {longDate(arrival.document.date)}
          </p>
          <blockquote className={styles.quote}>
            {quote.before}
            {quote.marked && <mark className={styles.mark}>{quote.marked}</mark>}
            {quote.after}
          </blockquote>
        </article>

        <div className={styles.arrow} aria-hidden="true">
          ↓
        </div>

        <article className={`${styles.card} ${styles.certificate}`} aria-label="Derivation certificate">
          <div className={styles.cardLabel}>Derivation certificate</div>
          <dl className={styles.cert}>
            <div className={styles.certBlock}>
              <dt>Support</dt>
              <dd>
                <ul className={styles.facts}>
                  <li>
                    Reference: {titled(cert.support.reference[0])}, {longDate(cert.support.reference[1])}
                  </li>
                  <li>
                    Target: {titled(edge.target.title)}, {longDate(cert.support.target_date)}{" "}
                    <code title={cert.support.target_sha256}>{shortHash(cert.support.target_sha256, 8)}</code>
                  </li>
                  <li>
                    Principal:{" "}
                    {cert.support.principal === "forward"
                      ? "the source's first party is a party to the target"
                      : cert.support.principal === "reverse"
                        ? "the target's principal is named in the source, in no participant role"
                        : "not established"}
                  </li>
                  <li>
                    Role: {cert.support.target_role === "AGREEMENT" ? "the agreement itself, not an instrument citing it" : cert.support.target_role}; citation{" "}
                    {cert.support.citation === "OPERATIVE" ? "operative, not history" : cert.support.citation.toLowerCase()}
                  </li>
                  <li>Relationship: {cert.support.relation}, source → target</li>
                </ul>
              </dd>
            </div>
            <div className={styles.certBlock}>
              <dt>Guard</dt>
              <dd>
                <p className={styles.certLead}>Exactly {cert.guard.satisfying_texts} visible text satisfies this reference.</p>
                <p className={styles.certNote}>
                  {underGuard !== null
                    ? `${grouped.format(underGuard)} ${underGuard === 1 ? "document of this filer carries that date and is" : "documents of this filer carry that date and are"} watched`
                    : "The filer's documents of that date are watched"}
                  {otherDates ? `, with the source's ${otherDates} other dated ${otherDates === 1 ? "reference" : "references"}` : ""}. A second text satisfying
                  the reference would reopen this edge; a document answering another reference does not.
                </p>
              </dd>
            </div>
            <div className={styles.certBlock}>
              <dt>Scope</dt>
              <dd>
                <p className={styles.certNote}>
                  Uniqueness was established among the documents scope <code>{cert.scope.id}</code> can see. Documents outside it never enter a guard.
                </p>
              </dd>
            </div>
          </dl>
          <p className={styles.certFoot}>
            This edge depends on {cert.reads} keys. The predecessor read {cert.bucket_baseline_reads}.{" "}
            <span className={styles.quiet}>
              Certificate <code>{shortHash(cert.certificate_sha256, 10)}</code>, replayed {cert.replayed}.
            </span>
          </p>
        </article>

        <div className={styles.arrow} aria-hidden="true">
          ↓
        </div>

        <p className={styles.established}>
          Relationship established: {edge.relation} → {titled(edge.target.title)}, {longDate(edge.target.date)}
        </p>
      </div>
    </Section>
  );
}

// ---------------------------------------------------------------------------------------------- 3. one arrival

function ArrivalMoment({
  view,
  arrival,
  index,
  featured,
  onChoose,
}: {
  view: ContractStateView;
  arrival: StateArrivalView;
  index: number;
  featured: number;
  onChoose: (i: number) => void;
}) {
  const env = arrival.impactEnvelope;
  const edges = arrival.edges ?? null;
  const outside = Math.max(0, arrival.objectsBefore - env.impactEnvelope);
  const steps: [string, string, string][] = [
    [
      "New contract",
      `${titled(arrival.document.title)}, ${longDate(arrival.document.date)}`,
      `${grouped.format(arrival.documentsBefore)} documents already in the portfolio`,
    ],
    ["Keys it moved", `${grouped.format(env.movedKeys)} keys`, "the facts about the new document that derived results can read"],
    [
      "Impact envelope",
      `${grouped.format(env.impactEnvelope)} objects`,
      `every result whose recorded dependencies or certificate the new keys reach: ${kinds(env.impactEnvelopeByKind)}`,
    ],
    [
      "Input and certificate checks",
      `${grouped.format(arrival.work.keptByInputCheck)} kept as computed`,
      edges
        ? `inputs unchanged, so kept as computed; of ${edges.edges_revalidated} ${edges.edges_revalidated === 1 ? "relationship" : "relationships"} re-evaluated, ${edges.edge_value_and_certificate_unchanged} came back with the same value and certificate and reached nothing downstream`
        : "inputs unchanged, so kept as computed",
    ],
    ["Recompute plan", `${grouped.format(arrival.recomputePlan.total)} objects`, kinds(arrival.recomputePlan.byKind)],
    ["State delta", `${grouped.format(arrival.stateDelta.total)} objects changed`, kinds(arrival.stateDelta.byKind)],
    [
      "Everything else",
      `at least ${grouped.format(outside)} untouched`,
      arrival.verified
        ? `of the ${grouped.format(arrival.objectsBefore)} objects that existed just before this arrival, outside the envelope and never looked at. Checked against a full rebuild: ${arrival.verified.stateEqualToRebuild ? "equal" : "DIFFERENT"}, ${arrival.verified.changedOutsideEnvelope} changed outside the envelope.`
        : `of the ${grouped.format(arrival.objectsBefore)} objects that existed just before this arrival, outside the envelope and never looked at. This arrival was not checked one by one; the state after all ${view.arrivals.length} arrivals equals a rebuild.`,
    ],
  ];
  return (
    <Section
      id="arrival"
      kicker="One new contract arrives"
      title={`One document arrived. ${grouped.format(arrival.recomputePlan.total)} objects needed another look.`}
    >
      <p className={styles.body}>
        The other {grouped.format(Math.max(0, arrival.objectsBefore - arrival.recomputePlan.total))} did not. Each step below is a number the engine recorded
        for this arrival.
      </p>
      <div className={styles.picker}>
        <label htmlFor="arrival-pick">Recorded arrival</label>
        <select id="arrival-pick" value={index} onChange={(event) => onChoose(Number(event.target.value))}>
          {view.arrivals.map((a, i) => (
            <option key={`${a.document.recordId}-${i}`} value={i}>
              {i + 1}. {titled(a.document.title)}
              {a.document.date ? ` · ${a.document.date}` : ""}
              {i === featured ? " · shown first" : ""}
              {a.verified ? " · checked against a rebuild" : ""}
            </option>
          ))}
        </select>
      </div>
      <ol className={styles.trace} aria-label="The recorded trace of this arrival">
        {steps.map(([name, value, note], i) => (
          <li key={name} className={styles.traceStep}>
            <span className={styles.traceNumber} aria-hidden="true">
              {i + 1}
            </span>
            <span className={styles.traceName}>{name}</span>
            <span className={styles.traceValue}>{value}</span>
            <span className={styles.traceNote}>{note}</span>
          </li>
        ))}
      </ol>
    </Section>
  );
}

// ---------------------------------------------------------------------------------------------- 4. the predecessor

function ComparisonMoment({ evidence }: { evidence: Evidence }) {
  const cert = evidence.comparison?.arrivals?.certificate;
  const bucket = evidence.comparison?.arrivals?.bucket;
  const mc = evidence.mutations?.totals?.certificate;
  const mb = evidence.mutations?.totals?.bucket;
  if (!cert || !bucket) return null;
  const rows: [string, string, string, boolean | null][] = [
    ["Adjudications per arrival", fmt(cert.adjudications_mean), fmt(bucket.adjudications_mean), null],
    ["Recompute plan per arrival", fmt(cert.recompute_plan_mean, 1), fmt(bucket.recompute_plan_mean, 1), null],
    [`Relationships re-evaluated, ${cert.arrivals} arrivals`, fmt(cert.edges?.edges_revalidated), fmt(bucket.edges?.edges_revalidated), null],
  ];
  if (mc && mb) {
    rows.push(
      [`Mutation suite: missed invalidations`, fmt(mc.missed_invalidations), fmt(mb.missed_invalidations), null],
      [`Mutation suite: unnecessary invalidations`, fmt(mc.unnecessary_invalidations), fmt(mb.unnecessary_invalidations), null],
      [
        `Final state equal to the rebuild oracle`,
        `${mc.final_state_equal_to_oracle} of ${mc.scenarios}`,
        `${mb.final_state_equal_to_oracle} of ${mb.scenarios}`,
        null,
      ],
    );
  }
  return (
    <Section id="comparison" kicker="Against the predecessor" title="The same arrivals, the engine that came before.">
      <p className={styles.body}>
        The predecessor is the real earlier engine, not a strawman: every relationship read its whole blocking bucket. It was never wrong about documents or
        scopes; it did not declare the version of the rules, which is where its three misses come from.
      </p>
      <div className={styles.tableWrap}>
        <table className={styles.table}>
          <caption className="visually-hidden">Certificate-aware engine against the bucket-guard predecessor</caption>
          <thead>
            <tr>
              <th scope="col">Recorded</th>
              <th scope="col">Certificates</th>
              <th scope="col">Bucket guard (predecessor)</th>
            </tr>
          </thead>
          <tbody>
            {rows.map(([label, a, b]) => (
              <tr key={label}>
                <th scope="row">{label}</th>
                <td>{a}</td>
                <td>{b}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className={styles.quiet}>
        Recorded medians of wall time, one run each on the same machine: {fmt(cert.wall_seconds_p50, 2)} s and {fmt(bucket.wall_seconds_p50, 2)} s per arrival;
        a full rebuild took {fmt(cert.rebuild.wall_seconds)} s. Machine load moves these; the counts above are the result.
      </p>
    </Section>
  );
}

// ---------------------------------------------------------------------------------------------- 5. the failed gate

const GATES: [string, string, string][] = [
  ["precision>=0.98", "Precision ≥ 0.98", "precision"],
  ["recall>=0.85", "Recall ≥ 0.85", "recall"],
  ["false-family<=0.02", "False families ≤ 0.02", "false_family_rate"],
  ["direction==1.00", "Direction = 1.00", "direction_accuracy"],
];

const CLASS_WORDS: Record<string, string> = {
  FEATURE_READER: "feature-reader gaps: the reading before binding missed a reference, a date, the parties or the instrument",
  BINDER: "binder gap: a rule that does not exist yet",
  STRUCTURAL: "missing structural capabilities: one instrument acting on several agreements, or a consent",
};

function AuditMoment({ evidence }: { evidence: Evidence }) {
  const audit = evidence.relationship_audit;
  const misses = evidence.relationship_misses;
  if (!audit?.metrics || !audit.gates) return null;
  const m = audit.metrics;
  const passed = audit.gates.PRIMARY === "PASS";
  return (
    <Section
      id="audit"
      kicker="What didn't pass"
      title={passed ? "The preregistered gate was met." : `We preregistered 0.85 recall. The system reached ${fmt(m.recall, 3)}, so this run failed.`}
    >
      <p className={styles.body}>
        Set 4: {audit.pairs} pairs of real exhibits, read blind by language-model readers (not people) and frozen before the relationship engine was run on it
        once. The gates were written before the pairs were read. Failures stayed in the record.
      </p>
      <div className={styles.tableWrap}>
        <table className={styles.table}>
          <caption className="visually-hidden">The preregistered gate on set 4</caption>
          <thead>
            <tr>
              <th scope="col">Preregistered</th>
              <th scope="col">Recorded</th>
              <th scope="col">Gate</th>
            </tr>
          </thead>
          <tbody>
            {GATES.map(([key, label, metric]) => (
              <tr key={key}>
                <th scope="row">{label}</th>
                <td>{fmt(m[metric], 3)}</td>
                <td>
                  <Tone ok={audit.gates![key] === "PASS"}>{audit.gates![key] === "PASS" ? "PASS" : "FAIL"}</Tone>
                </td>
              </tr>
            ))}
          </tbody>
          <tfoot>
            <tr>
              <th scope="row">Result</th>
              <td colSpan={2}>
                <Tone ok={passed}>{passed ? "PASSED" : "NOT PASSED"}</Tone>
              </td>
            </tr>
          </tfoot>
        </table>
      </div>
      {misses?.counts && misses.misses && (
        <>
          <h3 className={styles.h3}>{misses.misses.length} missed relationships</h3>
          <ul className={styles.missList}>
            {Object.entries(misses.counts).map(([cls, n]) => (
              <li key={cls}>
                <span className={styles.missCount}>{n}</span> {CLASS_WORDS[cls] ?? cls}
              </li>
            ))}
          </ul>
          <details className={styles.details}>
            <summary>Each miss, as classified after the result was committed</summary>
            <ul className={styles.missDetail}>
              {misses.misses.map((x) => (
                <li key={x.pair}>
                  <code>{x.pair}</code> · {x.what}
                </li>
              ))}
            </ul>
          </details>
        </>
      )}
      <h3 className={styles.h3}>Where the evidence points next</h3>
      <ul className={styles.future}>
        <li>
          <strong>Reference and instrument reading.</strong> {misses?.counts?.FEATURE_READER ?? 8} of the {misses?.misses?.length ?? 12} misses happened before
          binding.
        </li>
        <li>
          <strong>One-to-many relationships.</strong> A real omnibus amendment acts on several agreements at once.
        </li>
        <li>
          <strong>Consent and other non-mutating relationships.</strong> Not every related instrument changes the agreement it names.
        </li>
        <li>
          <strong>Human validation.</strong> Every label came from blind model readers; no person has read set 4.
        </li>
      </ul>
      <p className={styles.quiet}>
        Also recorded: false families {fmt(m.false_family_rate, 3)}, relation-type agreement {fmt(m.relation_agreement, 3)}, UNKNOWN on{" "}
        {fmt((m.unknown_rate ?? 0) * 100, 1)}% of decided pairs, {fmt((audit.ambiguous_rate ?? 0) * 100, 1)}% of pairs marked unsure by the readers and kept.
        None of these is being fixed: research on this engine is frozen.
      </p>
    </Section>
  );
}

// ---------------------------------------------------------------------------------------------- scopes

function AuthorizationMoment({ evidence }: { evidence: Evidence }) {
  const auth = evidence.authorization;
  if (!auth) return null;
  const naive = Object.values(auth.naive_global_then_filter_leaks ?? {}).reduce((a, b) => a + b, 0);
  return (
    <Section id="authorization" kicker="Scopes" title="A viewer of one room, while documents arrive in another.">
      <div className={styles.pair}>
        <div className={styles.pairCell}>
          <span className={styles.pairValue}>{fmt(auth.cross_scope_leakage_observations)}</span>
          <span className={styles.pairLabel}>observed cross-scope changes, authorization first</span>
          <span className={styles.quiet}>
            over {auth.changes_in_room_0} recorded arrivals; {fmt(auth.r1_objects_in_envelope)} of the other room&rsquo;s objects ever entered an envelope
          </span>
        </div>
        <div className={styles.pairCell}>
          <span className={styles.pairValue}>{fmt(naive)}</span>
          <span className={styles.pairLabel}>observable leaks, global state filtered afterwards</span>
          <span className={styles.quiet}>counts, exemplars, cohorts and candidates that include documents the viewer cannot see</span>
        </div>
      </div>
      <p className={styles.quiet}>What was measured is what the viewer could observe in the recorded test. Timing side channels were not tested.</p>
    </Section>
  );
}

// ---------------------------------------------------------------------------------------------- engineering

function EngineeringView({ view, evidence, arrival }: { view: ContractStateView; evidence: Evidence; arrival: StateArrivalView | null }) {
  const s = view.summary!;
  const muts = evidence.mutations;
  const modes = ["certificate", "bucket", "positive"] as const;
  const modeNames: Record<string, string> = { certificate: "Certificates", bucket: "Bucket guard", positive: "Positive-only ablation" };
  const rev = evidence.revisions;
  const refilings = evidence.comparison?.refilings?.certificate;
  const cert = arrival?.certificate as unknown as Certificate | null | undefined;
  const orderedMuts = useMemo(() => [...(muts?.scenarios ?? [])].sort((a, b) => Number(a.control) - Number(b.control)), [muts]);
  return (
    <Section id="engineering" kicker="Engineering view" title="The pipeline and the checks behind it.">
      <details className={styles.details}>
        <summary>SourceDelta → ImpactEnvelope → RecomputePlan → StateDelta</summary>
        <div className={styles.detailBody}>
          <ul className={styles.facts}>
            <li>SourceDelta: the keys a change moves (atoms of the document, the buckets and guards it enters).</li>
            <li>
              ImpactEnvelope: every derived object those keys can reach through declared reads, drawn before anything is recomputed. An upper bound, not a
              forecast. Mean {fmt(s.impactEnvelopeMean, 1)}, max {fmt(s.impactEnvelopeMax)}.
            </li>
            <li>RecomputePlan: the envelope&rsquo;s objects whose inputs moved, resolved in dependency order. Mean {fmt(s.recomputePlanMean, 1)}.</li>
            <li>StateDelta: what changed. Mean {fmt(s.stateDeltaMean, 1)}.</li>
            <li>
              Invariants over the recorded arrivals: {s.changedOutsideEnvelope} objects changed outside the envelope;{" "}
              {s.stabilityBudgetDisturbedWithoutDependencyChange} recomputed with no input moved; {s.verifiedStateEqual} of {s.verifiedAgainstRebuild} checked
              arrivals equal to a full rebuild.
            </li>
          </ul>
        </div>
      </details>
      {cert && (
        <details className={styles.details}>
          <summary>What a certified relationship reads</summary>
          <div className={styles.detailBody}>
            <ul className={styles.facts}>
              <li>Support: the source&rsquo;s profile and opening (its reference and the cited span); the target&rsquo;s profile, opening and fingerprint.</li>
              <li>
                Guard: one key per dated reference of the source, per scope: the documents of that filer and date, with their profiles, openings and
                fingerprints. This one watches {cert.guard.guarded_dates.length} dates.
              </li>
              <li>Scope: guards are kept per scope over visible documents only.</li>
              <li>
                The rule version (<code>{cert.rule}</code>): a change of rules reopens every certified edge.
              </li>
              <li>
                In all, {cert.reads} keys against the predecessor&rsquo;s {cert.bucket_baseline_reads}. A relationship that is not established keeps the
                predecessor&rsquo;s whole-bucket reads.
              </li>
            </ul>
          </div>
        </details>
      )}
      {muts?.totals && (
        <details className={styles.details}>
          <summary>
            Mutation suite: {muts.totals.certificate?.scenarios} scenarios against a rebuild oracle ({muts.suite})
          </summary>
          <div className={styles.detailBody}>
            <p className={styles.body}>
              Each scenario changes one thing about one accepted relationship; what must become of it (preserve, revalidate, become unknown) was written before
              the run. The positive-only ablation reads only the source and the target: an intentionally incomplete engine kept to measure what guards and scope
              add, not a predecessor.
            </p>
            <div className={styles.tableWrap}>
              <table className={`${styles.table} ${styles.tableDense}`}>
                <caption className="visually-hidden">Mutation suite results per engine</caption>
                <thead>
                  <tr>
                    <th scope="col">Scenario</th>
                    <th scope="col">Must</th>
                    {modes.map((m) => (
                      <th key={m} scope="col">
                        {modeNames[m]}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {orderedMuts.map((sc) => (
                    <tr key={sc.scenario}>
                      <th scope="row">{sc.scenario}</th>
                      <td data-label="Must">{sc.expect.replace("_", " ").toLowerCase()}</td>
                      {modes.map((m) => {
                        const r = sc.modes[m];
                        const ok = !!r && r.focal_outcome_met && r.final_state_equal_to_oracle && r.missed_invalidations === 0;
                        const why = !r
                          ? "not run"
                          : r.missed_invalidations
                            ? `${r.missed_invalidations} missed`
                            : sc.expect === "PRESERVE"
                              ? "re-evaluated without need"
                              : "not re-evaluated";
                        return (
                          <td key={m} data-label={modeNames[m]}>
                            <Tone ok={ok}>{ok ? "as required" : why}</Tone>
                          </td>
                        );
                      })}
                    </tr>
                  ))}
                </tbody>
                <tfoot>
                  <tr>
                    <th scope="row" colSpan={2}>
                      Missed / unnecessary
                    </th>
                    {modes.map((m) => (
                      <td key={m} data-label={modeNames[m]}>
                        {muts.totals?.[m]?.missed_invalidations} / {muts.totals?.[m]?.unnecessary_invalidations}
                      </td>
                    ))}
                  </tr>
                </tfoot>
              </table>
            </div>
          </div>
        </details>
      )}
      {rev && (
        <details className={styles.details}>
          <summary>Refilings: the same agreement filed again</summary>
          <div className={styles.detailBody}>
            <p className={styles.body}>
              Over {rev.events} real refilings the certificate engine recomputed {fmt(refilings?.recompute_plan_total ?? rev.recompute_plan_total)} objects,
              against {fmt(rev.doc_hash_invalidated_total)} invalidated by the whole-document-hash cache defined in the experiment (
              {fmt(rev.doc_hash_disturbed_without_change_total)} of them did not change; it missed {fmt(rev.doc_hash_missed_changes_total)} changed objects).{" "}
              {refilings ? `${refilings.verified_state_equal} of ${refilings.verified} checked refilings equal a rebuild.` : ""}
            </p>
          </div>
        </details>
      )}
      {evidence.crash_resume && evidence.faults && (
        <details className={styles.details}>
          <summary>Crash and restart, fault injection</summary>
          <div className={styles.detailBody}>
            <ul className={styles.facts}>
              <li>
                Crash and restart over {evidence.crash_resume.population}: output{" "}
                {evidence.crash_resume.all_byte_identical ? "byte-identical to an unbroken run" : "DIFFERENT from an unbroken run"},{" "}
                {evidence.crash_resume.records_written_twice} records written twice.
              </li>
              <li>
                Fault injection: {evidence.faults.rejected} of {evidence.faults.applicable} injected faults caught by the tests, {evidence.faults.escaped}{" "}
                escaped, {evidence.faults.dominated} covered by a second path and caught with both broken.
              </li>
            </ul>
          </div>
        </details>
      )}
      <details className={styles.details}>
        <summary>How these numbers were made</summary>
        <div className={styles.detailBody}>
          <pre className={styles.code}>
            {[
              "python -m evals.state_eval arrivals --verify 8 --final-check",
              "python -m evals.state_eval arrivals --verify 0 --final-check --mode bucket",
              "python -m evals.certificate_mutations",
              "python -m evals.audit_eval --set audit4",
              "python -m evals.state_eval authorization",
              "python -m evals.export_state",
            ].join("\n")}
          </pre>
          <p className={styles.quiet}>
            These ran in the contract-lineage experiment, a private research repository, over SEC EDGAR filings kept outside it. Neither is published, so these
            commands cannot be run from this page or from Verity&apos;s repository; they record what produced each number. The record itself, with its sha256,
            is named at the foot of this page.
          </p>
        </div>
      </details>
    </Section>
  );
}
