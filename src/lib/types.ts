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
  missing: "Not found",
  unresolved: "Unresolved",
};

/** A pass is "within guidance" only when the run had guidance; without it the model gave a plain answer (prompt rule 5). */
export function statusLabel(status: FindingStatus, hasGuidance: boolean): string {
  if (status === "pass") return hasGuidance ? "Within guidance" : "Answered";
  return STATUS_LABELS[status];
}

export const STATUS_SOURCE_LABELS: Record<string, string> = {
  computed_days: "Status decided by code from the day counts",
  model_hint: "Status taken from the model's hint; no comparable day counts",
  no_evidence: "No verified evidence, so no status was given",
  reference_check: "Lowered to needs review by code: the conclusion names a section this document does not have",
  position_check: "Lowered to needs review by code: the day count the model stated is not in the verified quote or the guidance",
  ambiguous_fact: "Lowered to needs review by code: the quote states a duration two ways that disagree",
};

export function citationLabel(section: SectionView): string {
  return section.number ? `§${section.number} · ${section.heading}` : section.heading;
}
