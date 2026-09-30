"""Persistence model. Runs are append-only; findings and spans belong to exactly one run."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Literal, get_args

from sqlalchemy import Boolean, CheckConstraint, DateTime, Float, ForeignKey, Index, Integer, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def new_id() -> str:
    return uuid.uuid4().hex[:16]


# The vocabularies every layer shares, declared once as types so the ORM, the API schemas and the
# run service agree at type-check time. The database checks them on files it creates; code checks
# them everywhere (SQLite cannot add a CHECK to an existing table without rebuilding it).
RunStageName = Literal["reading", "finding_evidence", "checking", "verifying", "complete", "unresolved", "failed"]
FindingStatusName = Literal["pass", "needs_review", "missing", "unresolved"]
RunReasonName = Literal["insufficient_evidence", "citations_unverified", "invalid_output", "provider_error", "internal_error"]
RUN_STAGES: tuple[RunStageName, ...] = get_args(RunStageName)
TERMINAL_STAGES: tuple[RunStageName, ...] = ("complete", "unresolved", "failed")
FINDING_STATUSES: tuple[FindingStatusName, ...] = get_args(FindingStatusName)
RUN_REASONS: tuple[RunReasonName, ...] = get_args(RunReasonName)
StageStatusName = Literal["running", "ok", "failed"]
STAGE_STATUSES: tuple[StageStatusName, ...] = get_args(StageStatusName)
ReviewVerdictName = Literal["confirmed", "dismissed", "cleared"]
REVIEW_VERDICTS: tuple[ReviewVerdictName, ...] = get_args(ReviewVerdictName)


def _in_list(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


def utcnow() -> datetime:
    return datetime.now(UTC)


def as_utc(value: datetime) -> datetime:
    """SQLite returns naive datetimes; they were stored as UTC, so say so."""
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def iso(value: datetime | None) -> str | None:
    """ISO 8601 with an explicit UTC offset."""
    return None if value is None else as_utc(value).isoformat()


class Document(Base):
    __tablename__ = "documents"
    # One row per (bytes, reader): a concurrent first upload of the same file loses the insert and is handed the winner
    # (found while tracing, 2026-09-29). Rows from before reader versioning carry NULL, which the index treats as distinct.
    __table_args__ = (Index("ux_documents_sha256_parser", "sha256", "parser_version", unique=True),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(255))
    media_type: Mapped[str] = mapped_column(String(64))
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    pages: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Wall time of the parse at upload, so the run record can show where time goes.
    parse_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    # Which reader produced the section text (ingest.PARSER_VERSION); NULL is the first reader.
    parser_version: Mapped[str | None] = mapped_column(String(16), nullable=True)
    # DOCX: revisions the file carried and runs marked hidden. The text is the accepted view without them.
    tracked_changes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    hidden_runs: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    sections: Mapped[list[Section]] = relationship(back_populates="document", order_by="Section.ordinal", cascade="all, delete-orphan")


class Section(Base):
    __tablename__ = "sections"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), index=True)
    ordinal: Mapped[int] = mapped_column(Integer)
    number: Mapped[str] = mapped_column(String(32), default="")
    heading: Mapped[str] = mapped_column(String(512), default="")
    text: Mapped[str] = mapped_column(Text)

    document: Mapped[Document] = relationship(back_populates="sections")


class Guidance(Base):
    __tablename__ = "guidance"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    text: Mapped[str] = mapped_column(Text)
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    source: Mapped[str] = mapped_column(String(32), default="pasted")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Run(Base):
    __tablename__ = "runs"
    # One running or completed run per set of inputs; failed runs stay retryable.
    __table_args__ = (
        Index("ux_runs_fingerprint_active", "fingerprint", unique=True, sqlite_where=text("stage != 'failed'"), postgresql_where=text("stage != 'failed'")),
        CheckConstraint(_in_list("stage", RUN_STAGES), name="ck_runs_stage"),
        CheckConstraint(f"reason IS NULL OR {_in_list('reason', RUN_REASONS)}", name="ck_runs_reason"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id"), index=True)
    guidance_id: Mapped[str | None] = mapped_column(ForeignKey("guidance.id"), nullable=True)
    question: Mapped[str] = mapped_column(Text)
    stage: Mapped[RunStageName] = mapped_column(String(32), default="reading")
    provider: Mapped[str] = mapped_column(String(32))
    model: Mapped[str] = mapped_column(String(128))
    # What kind of question this was and why this model answered it (routing.router).
    task: Mapped[str | None] = mapped_column(String(32), nullable=True)
    routing_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    prompt_version: Mapped[str] = mapped_column(String(64))
    prompt_hash: Mapped[str] = mapped_column(String(64))
    options_json: Mapped[str] = mapped_column(Text, default="{}")
    document_sha256: Mapped[str] = mapped_column(String(64))
    guidance_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    candidates_json: Mapped[str] = mapped_column(Text, default="[]")
    raw_output: Mapped[str | None] = mapped_column(Text, nullable=True)
    input_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    output_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    latency_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Why a run ended without findings: insufficient_evidence | citations_unverified |
    # invalid_output | provider_error | internal_error. Null on a complete run.
    reason: Mapped[RunReasonName | None] = mapped_column(String(32), nullable=True)
    # Identity of the inputs (document, guidance, question, prompt hash, options); see application.start_run.
    fingerprint: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    document: Mapped[Document] = relationship()
    guidance: Mapped[Guidance | None] = relationship()
    stages: Mapped[list[RunStage]] = relationship(back_populates="run", order_by="RunStage.at", cascade="all, delete-orphan")
    findings: Mapped[list[Finding]] = relationship(back_populates="run", order_by="Finding.ordinal", cascade="all, delete-orphan")


class RunStage(Base):
    """One stage of one run: when it started and ended, what it read and produced (as hashes), how
    many attempts the model call took, and how it ended. The Runs surface renders these rows; a
    model timeout or a restart leaves a failed row, never a run stuck in flight."""

    __tablename__ = "run_stages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id", ondelete="CASCADE"), index=True)
    stage: Mapped[RunStageName] = mapped_column(String(32))
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    status: Mapped[StageStatusName | None] = mapped_column(String(16), nullable=True)
    attempt: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # sha256 of what the stage consumed and what it produced, so a stage can be replayed and compared.
    input_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    output_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # The run reason when the stage ended the run without a result.
    error_code: Mapped[str | None] = mapped_column(String(32), nullable=True)

    run: Mapped[Run] = relationship(back_populates="stages")


class Finding(Base):
    __tablename__ = "findings"
    __table_args__ = (CheckConstraint(_in_list("status", FINDING_STATUSES), name="ck_findings_status"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id", ondelete="CASCADE"), index=True)
    ordinal: Mapped[int] = mapped_column(Integer, default=0)
    topic: Mapped[str] = mapped_column(String(255))
    status: Mapped[FindingStatusName] = mapped_column(String(32))
    status_source: Mapped[str] = mapped_column(String(32))
    conclusion: Mapped[str] = mapped_column(Text)
    guidance_reference: Mapped[str | None] = mapped_column(String(255), nullable=True)
    observed: Mapped[str | None] = mapped_column(String(255), nullable=True)
    required: Mapped[str | None] = mapped_column(String(255), nullable=True)
    suggested_position: Mapped[str | None] = mapped_column(Text, nullable=True)

    run: Mapped[Run] = relationship(back_populates="findings")
    spans: Mapped[list[EvidenceSpan]] = relationship(back_populates="finding", order_by="EvidenceSpan.ordinal", cascade="all, delete-orphan")
    reviews: Mapped[list[FindingReview]] = relationship(back_populates="finding", order_by="FindingReview.id", cascade="all, delete-orphan")

    @property
    def review(self) -> FindingReview | None:
        """The person's current decision: the latest review, unless it cleared the finding."""
        latest = self.reviews[-1] if self.reviews else None
        return None if latest is None or latest.verdict == "cleared" else latest


class EvidenceSpan(Base):
    __tablename__ = "evidence_spans"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    finding_id: Mapped[str] = mapped_column(ForeignKey("findings.id", ondelete="CASCADE"), index=True)
    ordinal: Mapped[int] = mapped_column(Integer, default=0)
    section_id: Mapped[str | None] = mapped_column(ForeignKey("sections.id"), nullable=True)
    cited_section_label: Mapped[str] = mapped_column(String(32), default="")
    start: Mapped[int] = mapped_column(Integer, default=-1)
    end: Mapped[int] = mapped_column(Integer, default=-1)
    quote: Mapped[str] = mapped_column(Text)
    verified: Mapped[bool] = mapped_column(Boolean, default=False)
    method: Mapped[str] = mapped_column(String(32), default="none")

    finding: Mapped[Finding] = relationship(back_populates="spans")
    section: Mapped[Section | None] = relationship()


class FindingReview(Base):
    """A person's decision about a finding, appended, never edited: model proposes, code verifies,
    a person adjudicates. The latest row is the state; a `cleared` row returns the finding to
    unreviewed. The finding itself is never changed by a review."""

    __tablename__ = "finding_reviews"
    __table_args__ = (CheckConstraint(_in_list("verdict", REVIEW_VERDICTS), name="ck_finding_reviews_verdict"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    finding_id: Mapped[str] = mapped_column(ForeignKey("findings.id", ondelete="CASCADE"), index=True)
    verdict: Mapped[ReviewVerdictName] = mapped_column(String(16))
    reviewer: Mapped[str] = mapped_column(String(80))
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    finding: Mapped[Finding] = relationship(back_populates="reviews")


class Batch(Base):
    """A field-extraction task run over a corpus: which task, which corpus, how many in flight, when.
    Its items point at ordinary runs; the numbers are computed from those runs, never stored."""

    __tablename__ = "batches"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    task: Mapped[str] = mapped_column(String(64))
    task_sha256: Mapped[str] = mapped_column(String(64))
    corpus: Mapped[str] = mapped_column(String(255))
    model: Mapped[str] = mapped_column(String(128))
    prompt_version: Mapped[str] = mapped_column(String(64), default="")
    concurrency: Mapped[int] = mapped_column(Integer, default=1)
    documents: Mapped[int] = mapped_column(Integer, default=0)
    requested: Mapped[int] = mapped_column(Integer, default=0)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    items: Mapped[list[BatchItem]] = relationship(back_populates="batch", order_by="BatchItem.id", cascade="all, delete-orphan")


class BatchItem(Base):
    """One document and one field of a batch, and the run that answered it (created or reused)."""

    __tablename__ = "batch_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    batch_id: Mapped[str] = mapped_column(ForeignKey("batches.id", ondelete="CASCADE"), index=True)
    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id"), index=True)
    field: Mapped[str] = mapped_column(String(64))
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id"), index=True)
    reused: Mapped[bool] = mapped_column(Boolean, default=False)
    wall_ms: Mapped[float | None] = mapped_column(Float, nullable=True)

    batch: Mapped[Batch] = relationship(back_populates="items")
    run: Mapped[Run] = relationship()


class Memo(Base):
    __tablename__ = "memos"
    # One memo per (run, review state): the run is immutable, the reviews of its findings are not, and a memo describes
    # both. A later review earns a new memo; the old one stays what it was (found while tracing, 2026-09-29).
    __table_args__ = (Index("ux_memos_run_review", "run_id", "review_head", unique=True),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id"), index=True)
    # sha256 over the findings' latest review rows at the time of writing (application.create_memo.review_head).
    review_head: Mapped[str | None] = mapped_column(String(64), nullable=True, default="")
    docx_path: Mapped[str] = mapped_column(String(512))
    docx_sha256: Mapped[str] = mapped_column(String(64))
    html: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
