"""What a reading of a file did with each part of it. Anything the reader does not read is represented as unread.

A parse "succeeding" says only that one reading of certain parts was produced. A DOCX carries parts the body walk
never visits (headers, footers, footnotes, endnotes, comments, block-level content controls, embedded objects,
external chunks) and constructs it reads only in part (fields keep their cached result, automatic numbering is not
rendered, text hidden by a style is kept). Each is listed here with its status and a count, computed from the
package and the body at upload, stored on the document and shown to the reader of the record. The list is fixed
so that a part missing from it is a bug, not an omission.
"""

from __future__ import annotations

import io
import re
import zipfile
from dataclasses import dataclass
from enum import StrEnum

# Every part a reading accounts for, in the order they are reported.
PARTS: tuple[str, ...] = (
    "main_body",
    "tables",
    "tracked_insertions",
    "tracked_deletions",
    "move_revisions",
    "hidden_runs",
    "style_hidden_text",
    "headers",
    "footers",
    "footnotes",
    "endnotes",
    "comments",
    "content_controls",
    "fields",
    "automatic_numbering",
    "embedded_objects",
    "external_chunks",
)


class Status(StrEnum):
    READ = "read"  # in the sections
    ACCEPTED = "accepted"  # tracked insertions: kept, as Word shows them once accepted
    EXCLUDED = "excluded"  # left out on purpose, and counted
    PARTIAL = "partial"  # some of it is in the sections; the note says which
    OMITTED = "omitted"  # present in the file, not read
    ABSENT = "absent"  # the file has none
    UNKNOWN = "unknown"  # the reader cannot tell


@dataclass(frozen=True)
class PartCoverage:
    part: str
    status: Status
    count: int = 0
    note: str = ""

    def as_dict(self) -> dict[str, object]:
        return {"part": self.part, "status": self.status.value, "count": self.count, "note": self.note}


COVERAGE_SCHEMA_VERSION = 1


def coverage_report(parts: list[PartCoverage], reader_version: str, source: str) -> dict[str, object]:
    """The stored and served form of a reading's coverage. ``source`` is "persisted" when the reading recorded it at
    upload and "reconstructed" when it was computed later from the stored bytes under the same reader: the same
    facts, but not facts the reading captured at the time, and never shown as if they were."""
    return {
        "schema_version": COVERAGE_SCHEMA_VERSION,
        "reader_version": reader_version,
        "source": source,
        "parts": [part.as_dict() for part in parts],
    }


def _strip_tags(xml: str) -> str:
    return re.sub(r"<[^>]+>", "", xml)


def _text_bearing(members: list[bytes], minimum: int = 1) -> int:
    """How many of these parts carry visible text (separator-only footnotes and empty headers do not count)."""
    return sum(1 for data in members if len(_strip_tags(data.decode("utf-8", "replace")).strip()) >= minimum)


def docx_coverage(data: bytes, body_xml: str, tracked_changes: int, hidden_runs: int, style_hidden_runs: int = 0) -> list[PartCoverage]:
    """The coverage of the accepted-view DOCX reading. ``body_xml`` is the serialised w:body the reader walked."""
    with zipfile.ZipFile(io.BytesIO(data)) as package:
        names = set(package.namelist())

        def parts(prefix: str) -> list[bytes]:
            return [package.read(name) for name in sorted(names) if name.startswith(prefix)]

        headers, footers = parts("word/header"), parts("word/footer")
        footnotes = parts("word/footnotes.xml")
        endnotes = parts("word/endnotes.xml")
        comments = parts("word/comments.xml")
        embeddings = [name for name in names if name.startswith("word/embeddings/") or (name.startswith("word/media/") and name.endswith((".emf", ".bin")))]

    def counted(part: str, present: int, status: Status, note: str) -> PartCoverage:
        return PartCoverage(part, status if present else Status.ABSENT, present, note if present else "")

    insertions = len(re.findall(r"<w:ins\b", body_xml))
    deletions = len(re.findall(r"<w:del\b", body_xml))
    moves = len(re.findall(r"<w:move(?:From|To)\b", body_xml))
    tables = len(re.findall(r"<w:tbl>", body_xml))  # nested tables included: each is read inside its cell
    # Block-level content controls are children of the body the walk does not enter; inline ones are read through their content.
    block_controls = len(re.findall(r"<w:body>(?:(?!</w:body>).)*?<w:sdt>", body_xml, re.DOTALL)) and len(
        re.findall(r"(?<=</w:p>|<w:body>)\s*<w:sdt>", body_xml)
    )
    inline_controls = len(re.findall(r"<w:sdt>", body_xml)) - block_controls
    fields = len(re.findall(r"<w:fldSimple\b|<w:instrText\b", body_xml))
    numbered = len(re.findall(r"<w:numPr>", body_xml))
    alt_chunks = len(re.findall(r"<w:altChunk\b", body_xml))
    footnote_texts = _text_bearing(footnotes, minimum=1)
    # A footnotes part always carries the separator notes; real footnotes are w:footnote elements with a positive id.
    real_footnotes = sum(len(re.findall(r'<w:footnote\b[^>]*w:id="[1-9]\d*"', part.decode("utf-8", "replace"))) for part in footnotes) if footnote_texts else 0
    real_endnotes = sum(len(re.findall(r'<w:endnote\b[^>]*w:id="[1-9]\d*"', part.decode("utf-8", "replace"))) for part in endnotes)
    real_comments = sum(len(re.findall(r"<w:comment\b", part.decode("utf-8", "replace"))) for part in comments)

    return [
        PartCoverage("main_body", Status.READ, note="paragraphs and tables of the body, in document order"),
        counted(
            "tables", tables, Status.READ, "rows as text, cells joined with ' | '; nested tables inside their cell; merged cells once; deleted rows skipped"
        ),
        counted("tracked_insertions", insertions, Status.ACCEPTED, "kept, as Word shows them once every change is accepted"),
        counted("tracked_deletions", deletions, Status.EXCLUDED, "left out; a deleted paragraph mark joins its paragraphs"),
        counted("move_revisions", moves, Status.ACCEPTED, "text moved to its new place is read there; the old place is left out"),
        counted("hidden_runs", hidden_runs, Status.EXCLUDED, "runs hidden by their own properties (w:vanish, w:specVanish) are left out"),
        counted(
            "style_hidden_text",
            style_hidden_runs,
            Status.EXCLUDED,
            "runs hidden through a character or paragraph style are left out (reader v6); text hidden only in Word's web view (w:webHidden) is read",
        ),
        counted("headers", _text_bearing(headers), Status.OMITTED, "header text is not read"),
        counted("footers", _text_bearing(footers), Status.OMITTED, "footer text is not read"),
        counted("footnotes", real_footnotes, Status.OMITTED, "footnote text is not read; the reference marks are not in the sections"),
        counted("endnotes", real_endnotes, Status.OMITTED, "endnote text is not read"),
        counted("comments", real_comments, Status.OMITTED, "comments are not read"),
        counted("content_controls", block_controls + inline_controls, Status.READ, "controls are read through their content, block-level and inline alike"),
        counted("fields", fields, Status.PARTIAL, "the cached result of a field is read; its instruction is not evaluated"),
        counted("automatic_numbering", numbered, Status.OMITTED, "numbers Word generates are not rendered; headings are numbered from their outline level"),
        counted("embedded_objects", len(embeddings), Status.OMITTED, "embedded objects and drawings are not read"),
        counted("external_chunks", alt_chunks, Status.OMITTED, "content imported by reference (altChunk) is not read"),
    ] + (
        [PartCoverage("tracked_changes_total", Status.ACCEPTED, tracked_changes, "revisions the file carried, all resolved to the accepted view")]
        if tracked_changes
        else []
    )


def pdf_coverage(pages: int | None, textless_pages: int = 0) -> list[PartCoverage]:
    scanned = (
        PartCoverage("scanned_pages", Status.OMITTED, textless_pages, "pages with no text layer; nothing is read from them and no OCR is run")
        if textless_pages
        else PartCoverage("scanned_pages", Status.ABSENT, 0, "every page has a text layer")
    )
    return [
        PartCoverage("main_body", Status.READ, pages or 0, "the text layer of every page, in reading order as the PDF gives it"),
        PartCoverage("tables", Status.PARTIAL, note="table cells come out as running text; columns are not reconstructed"),
        PartCoverage("headers", Status.UNKNOWN, note="a PDF does not mark headers; page furniture may be in the text"),
        PartCoverage("footers", Status.UNKNOWN, note="a PDF does not mark footers; page numbers may be in the text"),
        PartCoverage("footnotes", Status.UNKNOWN, note="footnotes are text on the page like any other"),
        scanned,
        PartCoverage("embedded_objects", Status.OMITTED, note="images and attachments are not read"),
    ]


def txt_coverage(encoding: str = "UTF-8") -> list[PartCoverage]:
    return [PartCoverage("main_body", Status.READ, note=f"the whole file, decoded as {encoding}")]
