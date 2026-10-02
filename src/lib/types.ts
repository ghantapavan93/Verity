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
export type RunSummary = Schemas["RunSummary"];
export type RunDetailView = Schemas["RunDetail"];
export type RunExplanationView = Schemas["RunExplanation"];
export type StageEventView = Schemas["StageOut"];
export type CandidateView = Schemas["CandidateOut"];
export type FindingRecord = Schemas["FindingRecord"];
export type ExperimentRecord = Schemas["ExperimentRecord"];
export type ExperimentsView = Schemas["ExperimentsOut"];
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

export type RunStage = RunView["stage"];
export type FindingStatus = FindingView["status"];
export type RunReason = NonNullable<RunView["reason"]>;

/** A span the API located in a section: verified, with the section it belongs to. */
export type LocatedSpan = SpanView & { sectionId: string; verified: true };

export function isLocated(span: SpanView): span is LocatedSpan {
  return span.verified && span.sectionId !== null;
}

/** The stages a run passes through before it ends, in order. */
export const STAGE_ORDER = ["reading", "finding_evidence", "checking", "verifying"] as const satisfies readonly RunStage[];

export const STAGE_LABELS: Record<(typeof STAGE_ORDER)[number], string> = {
  reading: "Reading contract",
  finding_evidence: "Finding relevant language",
  checking: "Checking",
  verifying: "Verifying citations",
};

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
  invalid_output: "Analysis couldn't complete",
  provider_error: "The model could not be reached",
  internal_error: "The run did not complete",
};

const STATUS_LABELS: Record<Exclude<FindingStatus, "pass">, string> = {
  needs_review: "Needs review",
  // About the sections the model was handed, never about the agreement (prompt rule 8).
  missing: "Not found in the sections read",
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
    if (!hasGuidance) return "Answered";
    return source === "model_hint" ? "Within guidance (model's view)" : "Within guidance";
  }
  return STATUS_LABELS[status];
}

export const STATUS_SOURCE_LABELS: Record<string, string> = {
  computed_days: "Status decided by code from the day counts",
  model_hint: "Status taken from the model's hint; no comparable day counts",
  no_evidence: "No verified evidence, so no status was given",
  reference_check: "Lowered to needs review by code: the conclusion names a section this document does not have",
  position_check: "Lowered to needs review by code: the day count the model stated is not in the verified quote or the guidance",
  ambiguous_fact: "Lowered to needs review by code: the quote does not state one period (its words and digits disagree, or its periods differ)",
};

/** The sources under which code, not the model, decided the status (the API's DETERMINISTIC_SOURCES). */
const DECIDED_BY_CODE: ReadonlySet<string> = new Set(["computed_days", "position_check", "ambiguous_fact", "reference_check"]);

export function decidedByCode(source: string | null | undefined): boolean {
  return source != null && DECIDED_BY_CODE.has(source);
}

export function citationLabel(section: SectionView): string {
  return section.number ? `§${section.number} · ${section.heading}` : section.heading;
}
