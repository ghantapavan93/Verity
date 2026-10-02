"""Run a field-extraction task over a corpus and report what happened.

Each (document, field) is an ordinary run through the same start_run and execute_run the
interface uses: same fingerprint, same verification, same immutable record. The batch adds
bounded concurrency, a record of which runs belong to it, and numbers: throughput, latency,
invalid output, verified citations, withheld findings, reuse and retries. Nothing here changes
how a value is decided.
"""

from __future__ import annotations

import json
import logging
import statistics
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy.orm import Session, sessionmaker

from ..application.ingest_document import ingest_document
from ..application.start_run import start_run
from ..errors import InvalidInput, NotFound
from ..hashing import sha256_bytes
from ..ingest import SUPPORTED
from ..models import Batch, BatchItem, Document, Run, as_utc, iso, utcnow
from ..providers.base import ModelProvider
from ..runs.service import execute_run
from ..schemas import BatchField, BatchOut, BatchRow, BatchSummary, BatchValue

log = logging.getLogger(__name__)
TASKS_DIR = Path(__file__).with_name("tasks")


@dataclass(frozen=True)
class Field:
    key: str
    label: str
    question: str


@dataclass(frozen=True)
class Task:
    name: str
    description: str
    fields: tuple[Field, ...]
    sha256: str


def load_task(name: str) -> Task:
    path = TASKS_DIR / f"{name}.json"
    if not path.exists():
        raise NotFound("task", name)
    raw = path.read_bytes()
    data = json.loads(raw)
    fields = tuple(Field(key=str(f["key"]), label=str(f["label"]), question=str(f["question"]).strip()) for f in data["fields"])
    if len({f.key for f in fields}) != len(fields):
        raise ValueError(f"task {name}: field keys must be unique")
    return Task(name=str(data["name"]), description=str(data.get("description", "")), fields=fields, sha256=sha256_bytes(raw))


def corpus_files(corpus_dir: Path) -> list[Path]:
    files = sorted(p for p in corpus_dir.iterdir() if p.is_file() and p.suffix.lower() in SUPPORTED)
    if not files:
        raise InvalidInput(f"no .docx, .pdf or .txt files in {corpus_dir}")
    return files


def ingest_corpus(session: Session, files: list[Path]) -> list[Document]:
    """Every file becomes (or already is) a document; the same bytes are one document."""
    documents: list[Document] = []
    seen: set[str] = set()
    for path in files:
        try:
            document = ingest_document(session, path.name, path.read_bytes()).document
        except InvalidInput as error:
            log.warning("corpus file skipped: %s: %s", path.name, error)
            continue
        if document.id in seen:  # the same bytes under another name or directory are one document
            continue
        seen.add(document.id)
        documents.append(document)
    return documents


def run_batch(
    session_factory: sessionmaker[Session],
    provider: ModelProvider,
    corpus_dirs: list[Path],
    task_name: str,
    *,
    corpus_label: str | None = None,
    concurrency: int = 1,
    prompt_version: str | None = None,
    model: str | None = None,
) -> str:
    """Ingest the corpus, start one run per document per field with at most ``concurrency`` in
    flight, and record the batch. Returns the batch id. Runs that already exist are reused."""
    task = load_task(task_name)
    files = [path for corpus_dir in corpus_dirs for path in corpus_files(corpus_dir)]
    with session_factory() as session:
        documents = ingest_corpus(session, files)
        batch = Batch(
            task=task.name,
            task_sha256=task.sha256,
            corpus=corpus_label or " + ".join(corpus_dir.name for corpus_dir in corpus_dirs),
            model=model or provider.model,
            prompt_version=prompt_version or "",
            concurrency=max(1, concurrency),
            documents=len(documents),
            requested=len(documents) * len(task.fields),
        )
        session.add(batch)
        session.commit()
        batch_id = batch.id
        jobs = [(d.id, field) for d in documents for field in task.fields]

    def work(job: tuple[str, Field]) -> None:
        document_id, field = job
        began = time.perf_counter()
        with session_factory() as session:
            started = start_run(session, document_id, None, field.question, provider, prompt_version=prompt_version, model=model)
            item = BatchItem(batch_id=batch_id, document_id=document_id, field=field.key, run_id=started.run.id, reused=not started.created)
            session.add(item)
            session.commit()
            if started.created:
                execute_run(session, started.run.id, provider)
            item.wall_ms = round((time.perf_counter() - began) * 1000, 1)
            session.commit()

    with ThreadPoolExecutor(max_workers=max(1, concurrency)) as pool:
        list(pool.map(work, jobs))

    with session_factory() as session:
        finished = session.get(Batch, batch_id)
        if finished is not None:
            finished.finished_at = utcnow()
            session.commit()
    return batch_id


# ----------------------------------------------------------------------------- the report


def _percentile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, round(fraction * (len(ordered) - 1))))
    return round(ordered[index], 1)


def value_for(run: Run) -> BatchValue:
    """The extracted value for one run: the first finding whose citation verified, or why there is none."""
    if run.stage == "failed":
        return BatchValue(run_id=run.id, outcome="failed", reason=run.reason)
    if run.stage != "complete":
        if run.stage == "unresolved":
            return BatchValue(run_id=run.id, outcome="withheld" if run.reason == "citations_unverified" else "not_found", reason=run.reason)
        return BatchValue(run_id=run.id, outcome="in_progress")
    for finding in run.findings:
        if finding.status in ("pass", "needs_review"):
            located = next((s for s in finding.spans if s.verified and s.section is not None), None)
            if located is not None and located.section is not None:
                citation = f"§{located.section.number}" if located.section.number else located.section.heading
                return BatchValue(run_id=run.id, outcome="answered", value=finding.conclusion, status=finding.status, citation=citation, method=located.method)
    if any(f.status == "missing" for f in run.findings):
        first = next(f for f in run.findings if f.status == "missing")
        # The product's sentence, not the model's: its own may state the absence about the whole agreement (models.NOT_FOUND_CONCLUSION).
        return BatchValue(run_id=run.id, outcome="not_found", value=first.shown_conclusion, status="missing")
    return BatchValue(run_id=run.id, outcome="withheld", reason=run.reason)


def summary(batch: Batch) -> BatchSummary:
    """Counts are distinct documents and distinct (document, field) pairs, whatever the corpus listing repeated."""
    pairs = {(item.document_id, item.field) for item in batch.items}
    return BatchSummary(
        id=batch.id,
        task=batch.task,
        corpus=batch.corpus,
        model=batch.model,
        prompt_version=batch.prompt_version,
        concurrency=batch.concurrency,
        documents=len({document_id for document_id, _ in pairs}) if pairs else batch.documents,
        requested=len(pairs) if pairs else batch.requested,
        started_at=iso(batch.started_at) or "",
        finished_at=iso(batch.finished_at),
    )


def report(session: Session, batch_id: str) -> BatchOut:
    batch = session.get(Batch, batch_id)
    if batch is None:
        raise NotFound("batch", batch_id)
    task = load_task(batch.task)
    # Distinct (document, field) pairs: a corpus that listed the same bytes twice made two items for one run.
    items: list[BatchItem] = []
    seen_pairs: set[tuple[str, str]] = set()
    for item in batch.items:
        if (item.document_id, item.field) in seen_pairs:
            continue
        seen_pairs.add((item.document_id, item.field))
        items.append(item)
    runs = {item.run_id: item.run for item in items}
    started_at = as_utc(batch.started_at)
    # A run counts as created by this batch when it began after the batch did; anything older was reused.
    created = [run for run in runs.values() if as_utc(run.created_at) >= started_at]
    finished_at = as_utc(batch.finished_at) if batch.finished_at else utcnow()
    wall_min = max((finished_at - started_at).total_seconds() / 60, 1e-6)

    values: dict[str, dict[str, BatchValue]] = {}
    for item in items:
        values.setdefault(item.document_id, {})[item.field] = value_for(item.run)
    answered = sum(1 for by_field in values.values() for v in by_field.values() if v.outcome == "answered")
    distinct_documents = len(values)

    latencies = [r.latency_ms for r in created if r.latency_ms is not None]
    findings = [f for r in runs.values() for f in r.findings]
    spans = [s for f in findings for s in f.spans]
    retries = sum(1 for r in created for stage in r.stages if stage.stage == "checking" and (stage.attempt or 1) > 1)
    by_reason: dict[str, int] = {}
    for r in created:
        if r.stage == "failed" and r.reason:
            by_reason[r.reason] = by_reason.get(r.reason, 0) + 1

    documents = {d.id: d for d in session.query(Document).filter(Document.id.in_(list(values))).all()}
    rows = [
        BatchRow(
            document_id=document_id,
            document_name=documents[document_id].name if document_id in documents else document_id,
            values={field.key: by_field.get(field.key, BatchValue(run_id="", outcome="in_progress")) for field in task.fields},
        )
        for document_id, by_field in values.items()
    ]
    rows.sort(key=lambda row: row.document_name)
    return BatchOut(
        **summary(batch).model_dump(by_alias=False),
        task_description=task.description,
        fields=[BatchField(key=f.key, label=f.label, question=f.question) for f in task.fields],
        runs_created=len(created),
        runs_reused=len(runs) - len(created),
        wall_minutes=round(wall_min, 2),
        documents_per_minute=round(distinct_documents / wall_min, 2) if batch.finished_at else None,
        values_per_minute=round(answered / wall_min, 2) if batch.finished_at else None,
        answered=answered,
        model_latency_p50_ms=_percentile(latencies, 0.5),
        model_latency_p95_ms=_percentile(latencies, 0.95),
        model_latency_mean_ms=round(statistics.fmean(latencies), 1) if latencies else None,
        invalid_output_runs=by_reason.get("invalid_output", 0),
        provider_error_runs=by_reason.get("provider_error", 0),
        failed_runs_by_reason=by_reason,
        findings=len(findings),
        withheld_findings=sum(1 for f in findings if f.status == "unresolved"),
        spans=len(spans),
        verified_spans=sum(1 for s in spans if s.verified),
        retries=retries,
        rows=rows,
    )


def list_batches(session: Session) -> list[BatchSummary]:
    return [summary(b) for b in session.query(Batch).order_by(Batch.started_at.desc()).all()]
