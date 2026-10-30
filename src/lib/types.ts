/**
 * The shapes the interface renders, derived from the API's OpenAPI document (`openapi.json`,
 * generated into `api.schema.ts` by `npm run api:types`). The backend schema is the source of
 * truth; nothing here is declared by hand except labels and a few narrowing helpers.
 */

import type { components } from "./api.schema";

type Schemas = components["schemas"];

export type SectionView = Schemas["SectionOut"];
export type DocumentView = Schemas["DocumentOut"];
export type DocumentSummary = Schemas["DocumentSummary"];
export type SpanView = Schemas["SpanOut"];
export type FindingView = Schemas["FindingOut"];
export type RunView = Schemas["RunOut"];
export type AccessView = Schemas["AccessOut"];
export type RunSummary = Schemas["RunSummary"];
export type RunDetailView = Schemas["RunDetail"];
export type RunExplanationView = Schemas["RunExplanation"];
export type FindingRecord = Schemas["FindingRecord"];
export type ExperimentRecord = Schemas["ExperimentRecord"];
export type ExperimentsView = Schemas["ExperimentsOut"];
export type ContractStateView = Schemas["ContractStateOut"];
export type StateArrivalView = Schemas["StateArrival"];
export type GoldensView = Schemas["GoldensOut"];
export type GoldenRunView = Schemas["GoldenRunOut"];
export type CitationRecord = Schemas["CitationRecordOut"];
export type BatchSummary = Schemas["BatchSummary"];
export type BatchView = Schemas["BatchOut"];
export type BatchValue = Schemas["BatchValue"];
export type FamiliesView = Schemas["FamiliesOut"];
export type ReviewIn = Schemas["ReviewIn"];
export type ReviewView = Schemas["ReviewOut"];
export type FindingReviewOut = Schemas["FindingReviewOut"];
export type ReviewVerdict = ReviewIn["verdict"];
export type GoldenVerdict = GoldenRunView["verdict"];
export type GuidanceRecord = Schemas["GuidanceOut"];
export type MemoRecord = Schemas["MemoOut"];
export type Health = Schemas["HealthOut"];
export type ModelWake = Schemas["ModelWakeOut"];
export type TrustDiffView = Schemas["TrustDiffOut"];
export type TrustFindingChange = Schemas["TrustFindingChangeOut"];
export type DocumentVersionView = Schemas["DocumentVersionOut"];
export type PassageView = Schemas["PassageOut"];
export type RelationView = Schemas["RelationOut"];
export type RelationNoteView = Schemas["RelationNoteOut"];

export type RunStage = RunView["stage"];
export type FindingStatus = FindingView["status"];
export type RunReason = NonNullable<RunView["reason"]>;

/** A span the API located in a section: verified, with the section it belongs to. */
export type LocatedSpan = SpanView & { sectionId: string; verified: true };

export function isLocated(span: SpanView): span is LocatedSpan {
  return span.verified && span.sectionId !== null;
}

/**
 * A passage code located for a relation (an original clause, its replacement, a ranking), as the document pane marks
 * one: the same jump and highlight as a quote. Located by code, not quoted by the model (runs.relations).
 */
export function passageSpan(passage: PassageView): LocatedSpan {
  return {
    sectionId: passage.sectionId,
    start: passage.start,
    end: passage.end,
    quote: passage.text,
    verified: true,
    method: "located",
    matchCount: 1,
    citedSectionLabel: "",
    clauseLabel: null,
    sectionLabel: passage.label,
  };
}

/**
 * The passage the document jumps to when a finding's evidence drawer opens: its first located span. None for a finding
 * the verifier withheld (its passage would be marked as if it were relied on), nor on a phone, where the document is not
 * shown and a jump would leave it scrolled to a mark nobody saw.
 */
export function evidenceJump(finding: FindingView, { shown, narrow }: { shown: boolean; narrow: boolean }): LocatedSpan | null {
  if (!shown || narrow) return null;
  return finding.spans.find(isLocated) ?? null;
}

/** The stages a run passes through before it ends, in order. */
export const STAGE_ORDER = ["reading", "finding_evidence", "checking", "verifying"] as const satisfies readonly RunStage[];

export const STAGE_LABELS: Record<(typeof STAGE_ORDER)[number], string> = {
  reading: "Reading contract",
  finding_evidence: "Finding relevant language",
  checking: "Checking",
  verifying: "Verifying citations",
};

/**
 * What the live region says while a run is in a stage. On a hosted model the first answer may wait for the model to wake,
 * and the visible note beside the stages says so (StageList); the live region said only "Checking", and a screen reader
 * then heard nothing for up to three minutes (war room UX-06, 2026-10-13).
 */
export function stageAnnouncement(stage: (typeof STAGE_ORDER)[number], modelSleeps: boolean): string {
  const label = STAGE_LABELS[stage];
  return stage === "checking" && modelSleeps ? `${label}. The model may be waking, which adds one and a half to three minutes to the first answer.` : label;
}

export const OUTCOME_LABELS: Record<RunStage, string> = {
  ...STAGE_LABELS,
  complete: "Complete",
  unresolved: "Unresolved",
  failed: "Failed",
};

/** Titles for runs that ended without findings, by the reason the API recorded. Exhaustive by type. */
export const REASON_TITLES: Record<RunReason, string> = {
  insufficient_evidence: "No supporting passage found",
  citations_unverified: "Evidence could not be verified",
  invalid_output: "The model's output was not usable",
  provider_error: "The model could not be reached",
  internal_error: "The run did not complete",
};

const STATUS_LABELS: Record<Exclude<FindingStatus, "pass">, string> = {
  needs_review: "Needs review",
  // About the sections the model was handed, never about the agreement (prompt rule 8); and the model's call: code never
  // checks an absence (authority review, 2026-10-14).
  missing: "Not found in the sections read (model's view)",
  unresolved: "Unresolved",
};

/**
 * A pass is "within guidance" only when the run had guidance; without it the model gave a plain answer (prompt rule 5).
 * When the pass is the model's own hint rather than a comparison code made, the label says so: the sweep of
 * 2026-10-01 found "Within guidance" on findings that said the contract provides no notice period at all.
 */
// A caller that does not say who decided gets the weaker claim, never "code decided".
export function statusLabel(status: FindingStatus, hasGuidance: boolean, source: string = "model_hint"): string {
  if (status === "pass") {
    if (!hasGuidance) return "Model's answer";
    // The model proposed the pass and code confirmed it; had the model asked for review there would be no pass, so
    // the label does not present it as a decision code made (policy-v2).
    if (source === "confirmed_days") return "Within guidance (confirmed by code)";
    if (source === "computed_days") return "Within guidance"; // code computed it from the day counts, before policy-v2
    // The model's hint, or a source this label does not know: never more of code than the record says (2026-10-30).
    return "Within guidance (model's view)";
  }
  return STATUS_LABELS[status];
}

export const STATUS_SOURCE_LABELS: Record<string, string> = {
  computed_days: "Needs review: code found the contract's period and the guidance's in conflict; that they concern the same point is the model's reading",
  confirmed_days:
    "Pass proposed by the model and confirmed by code from the day counts and the source text (a record made under policy v2; code no longer confirms a pass)",
  model_hint: "Status taken from the model's hint; code did not decide it",
  no_evidence: "No verified evidence, so no status was given",
  reference_check: "Lowered to needs review by code: the conclusion names a section this document does not have",
  // A value no quote states, a stated position the quote does not carry, or periods code cannot put in order: one sentence
  // for all three, with the recorded reason beside it. "a value the evidence does not establish" was shown for a calendar
  // against Business Day comparison, which is none of that (authority review, 2026-10-14).
  position_check: "Lowered to needs review by code: the evidence shown does not establish the model's answer",
  ambiguous_fact: "Lowered to needs review by code: the quote does not state one period (its words and digits disagree, or its periods differ)",
};

/** The sources under which code, not the model, decided the status (the API's DETERMINISTIC_SOURCES). */
const DECIDED_BY_CODE: ReadonlySet<string> = new Set(["computed_days", "position_check", "ambiguous_fact", "reference_check"]);

export function decidedByCode(source: string | null | undefined): boolean {
  return source != null && DECIDED_BY_CODE.has(source);
}

/**
 * What code did about a finding's status, in the words the interface heads it with. "Code found a conflict" is what
 * a day comparison establishes: two periods that do not agree. Whether they concern the same point is the model's
 * reading. "Code confirmed" is a record made under policy v2, when code still confirmed a pass; it no longer does.
 */
export function codeRole(source: string | null | undefined, status?: FindingStatus): CodeAccount["role"] {
  return codeAccount(source, status).role;
}

export interface CodeAccount {
  role: "Code found a conflict" | "Code passed it on the day counts" | "Code lowered it" | "Code confirmed" | "Code withheld" | "Code did not decide";
  /** A few words for the drawer's summary strip. */
  note: string;
  /** What the check did, when the record carries no sentence of its own. */
  sentence: string;
}

/**
 * What code did about a finding, by the check recorded as its status source: the one table every surface reads. Only a
 * day comparison finds a conflict; the other checks lower a finding for their own reason, and say which. Until
 * 2026-10-08 every code-set status was headed "Code found a conflict" and noted "the day counts conflict", including a
 * reference check that compared no days (QA review: an amendment citing its base agreement's sections).
 */
const CODE_ACCOUNTS: Record<string, CodeAccount> = {
  computed_days: { role: "Code found a conflict", note: "the day counts conflict", sentence: STATUS_SOURCE_LABELS.computed_days },
  reference_check: { role: "Code lowered it", note: "names a section not in this document", sentence: STATUS_SOURCE_LABELS.reference_check },
  position_check: { role: "Code lowered it", note: "the evidence does not establish the answer", sentence: STATUS_SOURCE_LABELS.position_check },
  ambiguous_fact: { role: "Code lowered it", note: "the quote states no one period", sentence: STATUS_SOURCE_LABELS.ambiguous_fact },
  confirmed_days: { role: "Code confirmed", note: "confirmed the model's call", sentence: STATUS_SOURCE_LABELS.confirmed_days },
  no_evidence: { role: "Code withheld", note: "no passage found", sentence: STATUS_SOURCE_LABELS.no_evidence },
};
const NOT_DECIDED: CodeAccount = { role: "Code did not decide", note: "", sentence: STATUS_SOURCE_LABELS.model_hint };

/**
 * computed_days is the one source the API allows with opposite statuses (STATUSES_BY_SOURCE): a conflict code found, or,
 * before policy v2, a pass code computed from the day counts alone, whatever the model's own hint was. Such a pass was
 * headed "Code found a conflict" on every surface that read the source alone (stress test, 2026-10-30, store
 * evolution); it is described as what it is, and whether anything is raised against it is the API's account.
 */
const PASSED_ON_DAYS: CodeAccount = {
  role: "Code passed it on the day counts",
  note: "on the day counts alone, a rule since withdrawn",
  sentence: "Pass computed by code from the day counts alone, under a rule withdrawn in policy v2: a record made before it, not a decision code makes now",
};

/** What code did about a status, by what its (status, source) pair means; a caller with no status reads the source alone. */
export function codeAccount(source: string | null | undefined, status?: FindingStatus): CodeAccount {
  if (source === "computed_days" && status === "pass") return PASSED_ON_DAYS;
  return (source != null && CODE_ACCOUNTS[source]) || NOT_DECIDED;
}

/** The sentence for who set a status (STATUS_SOURCE_LABELS), by its (status, source) pair, as codeAccount reads it. */
export function statusSourceLabel(source: string, status: FindingStatus): string {
  return source === "computed_days" && status === "pass" ? PASSED_ON_DAYS.sentence : (STATUS_SOURCE_LABELS[source] ?? source);
}

/**
 * How a run's sections were chosen, said beside them. The API records it as a field (`retrievalMode`); a run recorded
 * before it was one carries null, and nothing is claimed for it.
 */
export function retrievalNote(mode: RunView["retrievalMode"]): string {
  if (mode === "opening_fallback")
    return "retrieval ranked no section for this question: these are the opening sections, in document order, not ones chosen for it";
  if (mode === "hybrid_match") return "lexical and embedding retrieval, in rank order: the first row was ranked first";
  if (mode === "lexical_match") return "lexical retrieval, in rank order: the first row was ranked first";
  return "in the order they were handed over; how they were chosen was not recorded for this run";
}

/** What the answer panel says about how much the model was given. */
export function sectionsReadNote(mode: RunView["retrievalMode"], read: number, total: number): string {
  return mode === "opening_fallback"
    ? `retrieval ranked no section for this question, so the model was handed the opening ${read} of this document's ${total} sections`
    : `the model was handed ${read} of this document's ${total} sections`;
}

/**
 * A section longer than the reader's limit is stored as parts headed "<heading> (part N)" (backend
 * `ingest.sections.PART_HEADING`, mirrored here exactly). The suffix is the reading's division, not the document's
 * text: the paper shows the heading once and marks later parts as continued; citation labels keep the suffix.
 */
const PART_HEADING = /^(.*) \(part (\d+)\)$/;

export function partOf(heading: string): { base: string; index: number } | null {
  const match = PART_HEADING.exec(heading);
  return match ? { base: match[1], index: Number(match[2]) } : null;
}

/**
 * The sections the reader split for size, by id, each with its base heading and its part: only a run of two or more in
 * reading order, from an explicit part 1, each the next part of the same base under the same number, since the reader
 * writes parts only so (backend ingest.sections _push). Any other heading ending in " (part N)" is the document's own and
 * is shown as written: the paper read the suffix off any heading, so "2. Definitions (part 2)" lost its words and was
 * shown as a continuation the reader made (stress test, 2026-10-30). Two unnumbered headings the document wrote as
 * "X (part 1)" and "X (part 2)" cannot be told from a split by their text: since reader v17 the API says which it made
 * (`part`), and the headings are read only for a reading made before it.
 */
export function readingParts(sections: readonly SectionView[]): Map<string, { base: string; index: number }> {
  const parts = new Map<string, { base: string; index: number }>();
  // Reader v17 records its splits as data (SectionOut.part: 1..n for a split, 0 for a section not split): the record
  // decides, so a document's own "X (part 2)" is never joined to another section. Only a reading made before it (part
  // null) is read by its headings, below (2026-10-30).
  if (sections.some((section) => section.part != null)) {
    for (const section of sections) {
      if (!section.part) continue;
      const suffix = ` (part ${section.part})`;
      parts.set(section.id, { base: section.heading.endsWith(suffix) ? section.heading.slice(0, -suffix.length) : section.heading, index: section.part });
    }
    return parts;
  }
  let run: { section: SectionView; base: string }[] = [];
  const close = () => {
    if (run.length >= 2) run.forEach(({ section, base }, i) => parts.set(section.id, { base, index: i + 1 }));
    run = [];
  };
  for (const section of sections) {
    const part = partOf(section.heading);
    const last = run.at(-1);
    if (part && last && part.index === run.length + 1 && part.base === last.base && section.number === last.section.number) {
      run.push({ section, base: part.base });
      continue;
    }
    close();
    if (part?.index === 1) run = [{ section, base: part.base }];
  }
  close();
  return parts;
}

export function citationLabel(section: SectionView): string {
  return section.number ? `§${section.number} · ${section.heading}` : section.heading;
}

/**
 * Where a passage is, in the words a reader can check: the clause it sits in when the document's own text names one
 * (the API's `clauseLabel`, "§13.2 Governing Law"), else its section. A clause written inline is body under the last
 * standalone heading, so the section alone could name a different clause (2026-10-08).
 */
export function passageLabel(span: SpanView, section: SectionView): string {
  return span.clauseLabel ?? citationLabel(section);
}
