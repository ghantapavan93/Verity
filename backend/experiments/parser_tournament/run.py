"""The parser tournament harness (docs/PARSER-COMPARISON.md). Runs every adapter it can import over a set of
documents through one contract, records per document what each read, how long it took and how much memory it
used, replays the record's exact quotes over each challenger's text, and writes one JSON the document reads from.

    backend/data/tournament/venv/Scripts/python experiments/parser_tournament/run.py \
        --docs ../ivo-experiments/experiments/b1-word-structure/corpus --out data/tournament/result.json

Adapters: `current` (the workbench reader, always), `docling` (when importable in this interpreter). Docxodus is
listed as absent until an adapter exists for it. Nothing here touches the application or its database: the
record's quotes are read from the database read-only.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import time
import tracemalloc
from dataclasses import asdict, dataclass, field
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BACKEND))

from app.hashing import sha256_bytes  # noqa: E402
from app.ingest import TooLargeToRead, UnsupportedFile, ingest  # noqa: E402
from app.verify.spans import locate  # noqa: E402


@dataclass
class Reading:
    adapter: str
    document: str
    ok: bool
    error: str = ""
    seconds: float = 0.0
    peak_mb: float = 0.0
    sections: int = 0
    characters: int = 0
    headings: int = 0
    parts_read: list[str] = field(default_factory=list)
    text: str = ""  # joined section text, for the quote replay; not written to the result file


def read_current(path: Path, data: bytes) -> Reading:
    reading = Reading("current", path.name, True)
    try:
        parsed = ingest(path.name, data)
    except (UnsupportedFile, TooLargeToRead) as error:
        return Reading("current", path.name, False, str(error))
    reading.sections = len(parsed.sections)
    reading.characters = sum(len(s.text) for s in parsed.sections)
    reading.headings = sum(1 for s in parsed.sections if s.heading)
    reading.parts_read = [c.part for c in parsed.coverage if c.status.value in ("read", "accepted", "partial")]
    reading.text = "\n".join(s.text for s in parsed.sections)
    return reading


def read_docling(path: Path, data: bytes) -> Reading:
    try:
        from docling.document_converter import DocumentConverter
    except ImportError as error:
        return Reading("docling", path.name, False, f"not importable: {error}")
    reading = Reading("docling", path.name, True)
    try:
        result = DocumentConverter().convert(str(path))
        document = result.document
    except Exception as error:  # noqa: BLE001 - a challenger's failure is a measurement
        return Reading("docling", path.name, False, f"{type(error).__name__}: {str(error)[:120]}")
    texts: list[str] = []
    headings = 0
    furniture = 0
    for item, _level in document.iterate_items(with_groups=False):
        label = str(getattr(item, "label", ""))
        text = getattr(item, "text", "") or ""
        if not text:
            continue
        if "header" in label.lower() or "footer" in label.lower() or "footnote" in label.lower():
            furniture += 1
        if "heading" in label.lower() or "title" in label.lower():
            headings += 1
        texts.append(text)
    reading.sections = len(texts)
    reading.characters = sum(len(t) for t in texts)
    reading.headings = headings
    reading.parts_read = ["main_body"] + (["furniture"] if furniture else [])
    reading.text = "\n".join(texts)
    return reading


ADAPTERS = {"current": read_current, "docling": read_docling}


def measured(adapter: str, path: Path, data: bytes) -> Reading:
    tracemalloc.start()
    started = time.perf_counter()
    try:
        reading = ADAPTERS[adapter](path, data)
    finally:
        _current, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
    reading.seconds = round(time.perf_counter() - started, 3)
    reading.peak_mb = round(peak / (1024 * 1024), 1)
    return reading


def recorded_quotes(database: Path, sha256: str) -> list[str]:
    """Exact-tier quotes the record verified on a document with these bytes, under any reader version."""
    if not database.exists():
        return []
    connection = sqlite3.connect(f"file:{database}?mode=ro", uri=True)
    rows = connection.execute(
        "SELECT DISTINCT s.quote FROM evidence_spans s JOIN sections sec ON sec.id = s.section_id JOIN documents d ON d.id = sec.document_id "
        "WHERE d.sha256 = ? AND s.verified = 1 AND s.method = 'exact'",
        (sha256,),
    ).fetchall()
    connection.close()
    return [row[0] for row in rows]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--docs", action="append", required=True, help="a directory of .docx/.pdf/.txt files (repeatable)")
    parser.add_argument("--out", default=str(BACKEND / "data" / "tournament" / "result.json"))
    parser.add_argument("--database", default=str(BACKEND / "data" / "workbench.db"))
    parser.add_argument("--adapters", default="current,docling")
    args = parser.parse_args()
    paths = sorted(p for d in args.docs for p in Path(d).glob("*") if p.suffix.lower() in (".docx", ".pdf", ".txt"))
    adapters = [a.strip() for a in args.adapters.split(",")]
    results: list[dict[str, object]] = []
    for path in paths:
        data = path.read_bytes()
        quotes = recorded_quotes(Path(args.database), sha256_bytes(data))
        readings = {adapter: measured(adapter, path, data) for adapter in adapters}
        for adapter, reading in readings.items():
            retained = sum(1 for q in quotes if reading.ok and locate(q, reading.text) is not None and locate(q, reading.text).method == "exact")  # type: ignore[union-attr]
            row = asdict(reading)
            row.pop("text")
            row["exact_quotes_in_record"] = len(quotes)
            row["exact_quotes_retained"] = retained
            results.append(row)
            print(
                f"{path.name[:48]:<48} {adapter:<8} {'ok ' if reading.ok else 'ERR'} {reading.seconds:7.2f} s {reading.peak_mb:7.1f} MB "
                f"{reading.sections:5d} blocks {reading.characters:8d} chars quotes {retained}/{len(quotes)} {reading.error[:60]}"
            )
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(results, indent=1), encoding="utf-8")
    print(f"\nwritten {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
