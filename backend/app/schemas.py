"""API shapes. camelCase on the wire, snake_case in Python."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

from .models import FindingStatusName, RetrievalModeName, ReviewVerdictName, RunReasonName, RunStageName, StatusSourceName


class ApiModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, from_attributes=True)


class SectionOut(ApiModel):
    id: str
    number: str
    heading: str
    text: str


class CoverageOut(ApiModel):
    """What the reading did with one part of the file: read, accepted, excluded, partial, omitted, absent or unknown."""

    part: str
    status: str
    count: int = 0
    note: str = ""


class CoverageReport(ApiModel):
    """A reading's coverage with its provenance. persisted: recorded by the reading at upload. reconstructed: computed later
    from the stored bytes under the same reader version; the same facts, not captured at the time."""

    schema_version: int
    reader_version: str
    source: Literal["persisted", "reconstructed"]
    parts: list[CoverageOut]


class DocumentOut(ApiModel):
    id: str
    name: str
    pages: int | None
    sha256: str | None
    parse_ms: float | None = None
    parser_version: str | None = None
    # DOCX: revisions found in the file and hidden runs left out. The sections are the accepted view.
    tracked_changes: int | None = None
    hidden_runs: int | None = None
    # What this reading did with each part of the file; null when it cannot be described (bytes gone or an older reader).
    coverage: CoverageReport | None = None
    # True when POST /api/documents found these bytes already stored and handed back that document.
    reused: bool = False
    created_at: str = ""
    sections: list[SectionOut]


class DocumentSummary(ApiModel):
    id: str
    name: str
    pages: int | None
    sections: int
    findings: int = 0
    # Findings a person has confirmed or dismissed.
    reviewed_findings: int = 0
    last_run_at: str | None = None
    created_at: str


class GuidanceIn(ApiModel):
    text: str = Field(min_length=1, max_length=20000)


class GuidanceOut(ApiModel):
    id: str
    sha256: str
    text: str


class ReviewIn(ApiModel):
    verdict: ReviewVerdictName
    reviewer: str = Field(min_length=1, max_length=80)
    note: str | None = Field(default=None, max_length=2000)


class ReviewOut(ApiModel):
    """A person's current decision on a finding; absent when unreviewed or cleared."""

    verdict: Literal["confirmed", "dismissed"]
    reviewer: str
    note: str | None = None
    at: str
    # The invite subject the reviewer entered with, when the gate was on; the one identity the application verified.
    access_subject: str | None = None


class FindingReviewOut(ApiModel):
    finding_id: str
    review: ReviewOut | None = None


class RunIn(ApiModel):
    document_id: str
    guidance_id: str | None = None
    question: str = Field(min_length=1, max_length=2000)


class SpanOut(ApiModel):
    section_id: str | None
    start: int
    end: int
    quote: str
    verified: bool
    # How the quote was located: exact | normalized | casefold | typed (verifier v5; alnum before it) | relocated:<method> | none.
    method: str = "none"
    # How many places the quote occurs in the section under the tier that matched; null on records made before verifier v5.
    match_count: int | None = None
    # The label the model cited (sec_N); kept so a misattribution stays visible on the run record.
    cited_section_label: str = ""


class FindingOut(ApiModel):
    id: str
    topic: str
    status: FindingStatusName
    # Who decided the status (models.StatusSourceName). Empty only on a finding recorded before the source was.
    status_source: StatusSourceName | Literal[""] = ""
    # The policy evaluation's sentence when the status was computed ("the contract provides 15 calendar days; the guidance requires at least 30 calendar days").
    status_reason: str | None = None
    # passage: the spans support the conclusion. coverage: the point was not found and the spans are
    # the closest provisions that were read, cited so a reader can see what was searched.
    evidence_kind: Literal["passage", "coverage"] = "passage"
    # A person's decision, when one has been recorded and not cleared.
    review: ReviewOut | None = None
    # What the product says. For a point the model reported as not found it is the product's own sentence, about the
    # sections the model was given; otherwise it is the model's conclusion.
    conclusion: str
    # The model's own sentence, as recorded. Shown as the model's, never as the finding.
    model_conclusion: str = ""
    spans: list[SpanOut]
    guidance_reference: str | None
    observed: str | None
    required: str | None
    suggested_position: str | None


class RunOut(ApiModel):
    id: str
    question: str
    stage: RunStageName
    # A curated record: readable by every workspace, changed by none. Every run from before workspaces existed.
    shared: bool = False
    findings: list[FindingOut]
    # Findings the model proposed whose evidence did not verify: kept and shown as withheld, never as answers.
    withheld: list[FindingOut] = []
    model: str
    prompt_version: str
    prompt_hash: str
    latency_ms: float | None
    note: str | None
    error: str | None
    # Why the run ended without findings; null on a complete run.
    reason: RunReasonName | None = None
    # True when POST /api/runs handed back an existing run for the same inputs instead of starting one.
    reused: bool = False
    # Whether the run was given legal guidance. A pass is "within guidance" only when it was; otherwise it is a plain answer.
    has_guidance: bool = False
    # The identity of the findings' current review state; a memo carries the head it was written under.
    review_head: str = ""
    # The guidance the run was given, as stored; the drawer shows this, never the text in the composer at the time.
    guidance_text: str | None = None
    # How many of the document's sections were handed to the model (the run's recorded candidates); null before
    # retrieval has run. Everything the model said, absence included, is about these and no others.
    sections_read: int | None = None
    # How those sections were chosen: ranked for the question, or the opening sections because the retriever ranked
    # none. Null before retrieval has run and on every run recorded before 2026-10-02.
    retrieval_mode: RetrievalModeName | None = None
    # How many sections the run asked the retriever for (its recorded retrieval_k); null when the run recorded none.
    sections_requested: int | None = None


class RunSummary(ApiModel):
    id: str
    question: str
    stage: RunStageName
    shared: bool = False
    model: str
    prompt_version: str
    prompt_hash: str
    latency_ms: float | None
    reason: RunReasonName | None = None
    findings: int
    has_guidance: bool
    document_id: str
    document_name: str
    created_at: str


class FindingRecord(ApiModel):
    id: str
    run_id: str
    # The run is curated: its review is kept as recorded and cannot be changed here.
    shared: bool = False
    document_id: str
    document_name: str
    question: str
    topic: str
    status: FindingStatusName
    conclusion: str
    verified_spans: int
    evidence_kind: Literal["passage", "coverage"] = "passage"
    review: ReviewOut | None = None
    # Section labels of the verified citations, e.g. ["§5.4", "§5.3.1"].
    citations: list[str] = []
    has_guidance: bool = False
    # Who decided the status: code from the day counts, or the model's hint (FindingOut.status_source).
    status_source: StatusSourceName | Literal[""] = "model_hint"
    created_at: str


class StageOut(ApiModel):
    stage: RunStageName
    at: str
    detail: str | None = None
    completed_at: str | None = None
    duration_ms: float | None = None
    status: Literal["running", "ok", "failed"] | None = None
    attempt: int | None = None
    input_hash: str | None = None
    output_hash: str | None = None
    error_code: str | None = None


class CandidateOut(ApiModel):
    """A section handed to the model, by the label it cites."""

    label: str
    section_id: str
    number: str = ""
    heading: str = ""


class RunDetail(RunOut):
    document_id: str
    guidance_id: str | None
    provider: str
    options: dict[str, float | int | str]
    document_name: str = ""
    document_parse_ms: float | None = None
    # clause_lookup | guidance_comparison, and why this model answered it.
    task: str | None = None
    routing_reason: str | None = None
    verified_spans: int = 0
    total_spans: int = 0
    document_sha256: str
    guidance_sha256: str | None
    input_tokens: int | None
    output_tokens: int | None
    candidates: list[CandidateOut]
    raw_output: str | None
    stages: list[StageOut]
    created_at: str
    finished_at: str | None


class BatchValue(ApiModel):
    """What a batch extracted for one document and field: the first finding whose citation verified, or why there is none."""

    run_id: str
    # answered | not_found | withheld | failed | in_progress
    outcome: Literal["answered", "not_found", "withheld", "failed", "in_progress"]
    value: str | None = None
    status: FindingStatusName | None = None
    citation: str | None = None
    method: str | None = None
    reason: RunReasonName | None = None


class BatchField(ApiModel):
    key: str
    label: str
    question: str


class BatchRow(ApiModel):
    document_id: str
    document_name: str
    values: dict[str, BatchValue]


class BatchSummary(ApiModel):
    id: str
    task: str
    corpus: str
    model: str
    prompt_version: str = ""
    concurrency: int
    documents: int
    requested: int
    started_at: str
    finished_at: str | None = None


class BatchOut(BatchSummary):
    task_description: str = ""
    fields: list[BatchField] = []
    runs_created: int = 0
    runs_reused: int = 0
    wall_minutes: float = 0
    documents_per_minute: float | None = None
    values_per_minute: float | None = None
    answered: int = 0
    model_latency_p50_ms: float | None = None
    model_latency_p95_ms: float | None = None
    model_latency_mean_ms: float | None = None
    invalid_output_runs: int = 0
    provider_error_runs: int = 0
    failed_runs_by_reason: dict[str, int] = {}
    findings: int = 0
    withheld_findings: int = 0
    spans: int = 0
    verified_spans: int = 0
    retries: int = 0
    rows: list[BatchRow] = []


class MemoIn(ApiModel):
    run_id: str


class MemoOut(ApiModel):
    id: str
    run_id: str
    docx_url: str
    html_url: str
    docx_sha256: str
    # The review state this memo describes; when the run's head differs, a later review is not in it.
    review_head: str = ""


class HealthOut(ApiModel):
    ok: bool
    provider: str
    model: str
    detail: str
    # The gate (api/access.py): off, required (this browser has not entered; provider and model are then left blank), or entered.
    access: Literal["off", "required", "entered"] = "off"


class InviteIn(ApiModel):
    # The invite token, or the whole link it arrived in.
    invite: str = Field(min_length=1, max_length=4096)


class AccessOut(ApiModel):
    """Whether the gate is on and whether this browser is through it."""

    required: bool
    entered: bool
    # The name the invite was made for; null until entered, and when the gate is off.
    subject: str | None = None


class CitationRecordOut(ApiModel):
    """What the verifier did across every run where the model answered, counted from the records."""

    runs: int
    complete_runs: int
    unresolved_runs: int
    findings: int
    withheld_findings: int
    spans: int
    verified_spans: int
    # Verified spans by how they were located: exact, normalized, casefold, relocated:<method>.
    by_method: dict[str, int] = {}
    first_run_at: str | None = None
    last_run_at: str | None = None


class FamilyOut(ApiModel):
    members: list[str]
    titles: list[str] = []
    min_similarity: float | None = None
    max_similarity: float | None = None


class FamilyPair(ApiModel):
    a: str
    b: str
    combined: float
    shingles: float
    headings: float
    terms: float
    labeled: bool = False


class FamilyThresholdPoint(ApiModel):
    threshold: float
    precision: float
    recall: float
    f1: float


class FamilyEvaluation(ApiModel):
    label_set: str
    description: str = ""
    labeled_pairs: int = 0
    precision: float
    recall: float
    f1: float
    best_threshold: float
    best_f1: float
    sweep: list[FamilyThresholdPoint] = []


class FamiliesOut(ApiModel):
    available: bool
    detail: str | None = None
    threshold: float
    weights: dict[str, float] = {}
    documents: int = 0
    missing: list[str] = []
    families: list[FamilyOut] = []
    pairs: list[FamilyPair] = []
    evaluations: list[FamilyEvaluation] = []
    note: str = ""


class ExperimentRecord(ApiModel):
    id: str
    code: str
    title: str
    date: str
    expected: str = ""
    gate: str
    observed: str


class ExperimentPage(ApiModel):
    title: str | None = None
    subtitle: str | None = None
    author: str | None = None
    period: str | None = None
    repo_url: str | None = None
    branch: str | None = None


class GoldenExpectation(ApiModel):
    # present: the contract addresses the point and one of `sections` answers it; absent: it does not.
    kind: Literal["present", "absent"]
    sections: list[str] = []
    # Required on the finding that carries the citation, for goldens run with guidance.
    status: Literal["pass", "needs_review"] | None = None


class GoldenOut(ApiModel):
    id: str
    question: str
    why: str
    category: str = ""
    # The policy text the run is given, for guidance goldens.
    guidance: str | None = None
    expect: GoldenExpectation


class GoldenRunOut(ApiModel):
    """One golden under one prompt version: the run found by fingerprint and the verdict code gave it."""

    golden_id: str
    run_id: str | None = None
    stage: RunStageName | None = None
    reason: RunReasonName | None = None
    latency_ms: float | None = None
    statuses: list[FindingStatusName] = []
    # "5.3.1 exact", "sec_9 not found": every citation the run made and how it was located.
    cited: list[str] = []
    verdict: Literal["pass", "fail", "missing"]
    because: str


class GoldenCategoryCount(ApiModel):
    category: str
    passes: int
    recorded: int


class GoldenPromptOut(ApiModel):
    version: str
    hash: str
    runs: list[GoldenRunOut]
    passes: int
    recorded: int
    mean_latency_ms: float | None = None
    by_category: list[GoldenCategoryCount] = []


class GoldenDelta(ApiModel):
    golden_id: str
    base: Literal["pass", "fail", "missing"]
    head: Literal["pass", "fail", "missing"]
    change: Literal["better", "worse", "same"]
    # True when the citations or statuses differ even if the verdict did not.
    changed: bool
    note: str


class GoldenCompareOut(ApiModel):
    base: str
    head: str
    better: int
    worse: int
    same: int
    changed: int
    # Mean model latency of the head version minus the base version, over the goldens each recorded.
    latency_delta_ms: float | None = None
    rows: list[GoldenDelta]


class GoldensOut(ApiModel):
    available: bool
    detail: str | None = None
    set_sha256: str
    document_id: str | None = None
    document_name: str = ""
    document_sha256: str | None = None
    rules: str = ""
    categories: dict[str, str] = {}
    goldens: list[GoldenOut] = []
    prompts: list[GoldenPromptOut] = []
    compare: GoldenCompareOut | None = None


class ExperimentsOut(ApiModel):
    available: bool
    source: str | None
    page_url: str | None = None
    detail: str | None = None
    page: ExperimentPage = ExperimentPage()
    repo_head: str | None = None
    generated_at: str | None = None
    board: list[ExperimentRecord] = []
    baselines: list[ExperimentRecord] = []


# ------------------------------------------------------------------ "Why this answer?": the explanation of a run
# A read-only projection of the record (application/explain_run.py). Nothing here is computed by a model, and
# nothing is recomputed by today's code and presented as what the run established: the model's proposal is
# its stored words, the SourceMatch is the stored location, the policy evaluation is the recorded status,
# source and sentence.


class ExplanationReading(ApiModel):
    document_id: str
    document_name: str
    document_sha256: str
    reader_version: str | None
    pages: int | None
    sections: int
    # Sections with a number; the paper calls the structure approximate below three, and so does the explanation.
    numbered_sections: int
    tracked_changes: int
    hidden_runs: int
    coverage: CoverageReport | None
    # The parts the reading omitted with content, as the paper prints them: "footers (1)".
    not_read: list[str]
    # The reading stage's output hash: the sections' text as the run read it.
    recorded_sections_hash: str | None


class ExplanationCandidate(ApiModel):
    """A section retrieval handed to the model, in rank order, with the ContextSlice of it the prompt carried."""

    rank: int
    label: str
    section_id: str
    number: str = ""
    heading: str = ""
    characters: int
    slice_start: int | None
    slice_end: int | None
    # From the reconstructed ContextSlice; null when the input could not be reconstructed.
    truncated: bool | None


class ExplanationReconstruction(ApiModel):
    """The exact model input, rebuilt from the record and checked against the hash the checking stage wrote."""

    reconstructable: bool
    problem: str | None
    recorded_input_sha256: str | None
    rebuilt_input_sha256: str | None
    window_chars: int
    # Characters of the handed sections that lay beyond their ContextSlice and never reached the model; null without slices.
    characters_outside_context: int | None
    question: str
    has_guidance: bool
    guidance_text: str | None
    prompt_version: str
    prompt_hash: str
    model: str
    options: dict[str, float | int | str]
    # The admission wait the checking stage recorded, when there was one ("queued 12 s behind 3").
    queue_note: str | None


class ProposalEvidence(ApiModel):
    cited_label: str
    quote: str


class ModelProposal(ApiModel):
    """What the model proposed, in its own words, parsed from the stored raw output; correlated to a finding by ordinal."""

    ordinal: int
    topic: str
    conclusion: str
    status_hint: str
    observed: str | None
    required: str | None
    guidance_reference: str | None
    suggested_position: str | None
    evidence: list[ProposalEvidence]


class SourceMatch(ApiModel):
    """What the verifier established for one proposed quote: where it is in the stored text, if anywhere."""

    quote: str
    cited_label: str
    located_section_id: str | None
    located_label: str | None
    located_heading: str
    verified: bool
    method: str
    match_count: int | None
    start: int
    end: int
    relocated: bool
    # Whether the located offsets fall within the ContextSlice the model was shown for that section; null when
    # the quote was not located or the slices could not be reconstructed.
    inside_model_visible_context: bool | None


class RecordedPolicyEvaluation(ApiModel):
    """The status as it was recorded when the run finished, with its source and its sentence. Nothing re-derived."""

    status: FindingStatusName
    status_source: str
    status_reason: str | None
    # True when code decided the status (computed_days, position_check, ambiguous_fact, reference_check). False for
    # `confirmed_days`: there the model proposed the pass and code confirmed it, which is not code's decision alone.
    deterministic: bool
    summary: str


class ExplanationFinding(ApiModel):
    id: str
    ordinal: int
    topic: str
    conclusion: str
    status: FindingStatusName
    shown: bool
    source_matches: list[SourceMatch]
    recorded_policy_evaluation: RecordedPolicyEvaluation
    review: ReviewOut | None = None


class ExplanationReproducibility(ApiModel):
    run_id: str
    document_id: str
    document_sha256: str
    reader_version: str | None
    guidance_sha256: str | None
    prompt_version: str
    prompt_hash: str
    recorded_input_sha256: str | None
    input_matches: bool
    evidence_pack_path: str


class RunExplanation(ApiModel):
    run_id: str
    question: str
    stage: RunStageName
    reason: RunReasonName | None
    reading: ExplanationReading
    retrieval: list[ExplanationCandidate]
    # Whether `retrieval` is a ranking for the question or the opening sections handed over because nothing ranked.
    retrieval_mode: RetrievalModeName | None = None
    reconstruction: ExplanationReconstruction
    proposals: list[ModelProposal]
    # "Model proposal not reconstructable for this run." when the stored raw output does not parse under the
    # shape the model was asked for or does not line up with the findings by ordinal; never guessed from text.
    proposals_problem: str | None
    findings: list[ExplanationFinding]
    reproducibility: ExplanationReproducibility
