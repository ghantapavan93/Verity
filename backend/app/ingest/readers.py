"""Read DOCX, PDF and TXT into blocks. Nothing here calls a model.

DOCX is read as Word shows it with every tracked change accepted: inserted text is kept, deleted
and moved-away text is dropped, runs marked hidden are dropped, deleted table rows are skipped and
a deleted paragraph mark joins its paragraph to the next. python-docx's `paragraph.text` does none
of this; it walks only the runs that hang directly off the paragraph, so on negotiated paper it
loses both the old wording and the new. What the reader left out is counted and stored, so the
interface can say which view of the file the model read.
"""

from __future__ import annotations

import io
import re
import zipfile
from dataclasses import dataclass

from docx import Document as DocxDocument
from docx.opc.exceptions import PackageNotFoundError
from docx.oxml.ns import qn
from docx.table import Table
from docx.text.paragraph import Paragraph
from lxml import etree
from pypdf import PdfReader
from pypdf.errors import PyPdfError

from .sections import HEADING_NUMBER, Block, looks_like_heading

SUPPORTED = {
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".pdf": "application/pdf",
    ".txt": "text/plain",
}


MAX_DOCX_UNPACKED_BYTES = 256 * 1024 * 1024  # a 25 MB upload that unpacks past this is a bomb, not a contract
MAX_PDF_PAGES = 2000


class UnsupportedFile(ValueError):
    pass


@dataclass
class ReadResult:
    blocks: list[Block]
    pages: int | None
    title: str
    # DOCX only. Revisions the file carried (insertions, deletions, moves, including paragraph
    # marks and table rows) and runs marked hidden. Both are left out of the blocks.
    tracked_changes: int = 0
    hidden_runs: int = 0


def read(filename: str, data: bytes) -> ReadResult:
    suffix = ("." + filename.rsplit(".", 1)[-1].lower()) if "." in filename else ""
    if suffix == ".docx":
        return read_docx(data)
    if suffix == ".pdf":
        return read_pdf(data)
    if suffix == ".txt":
        return read_txt(data)
    raise UnsupportedFile(f"unsupported file type {suffix or '(none)'}; upload .docx, .pdf or .txt")


# --------------------------------------------------------------------------- DOCX

_PARAGRAPH = qn("w:p")
_TABLE = qn("w:tbl")
_RUN = qn("w:r")
_TEXT = qn("w:t")
# Content that Word removes when the change is accepted.
_DELETED = frozenset({qn("w:del"), qn("w:moveFrom")})
# Property bags hold no visible text. Skipping them also keeps mark-level revision elements
# (w:pPr/w:rPr/w:ins, w:trPr/w:del) out of the text walk.
_PROPERTIES = frozenset({qn(tag) for tag in ("w:pPr", "w:rPr", "w:sdtPr", "w:sdtEndPr", "w:tblPr", "w:tblGrid", "w:trPr", "w:tcPr")})
_RUN_BREAKS = {qn("w:tab"): "\t", qn("w:ptab"): "\t", qn("w:br"): "\n", qn("w:cr"): "\n", qn("w:noBreakHyphen"): "-"}
_REVISIONS_XPATH = ".//w:ins | .//w:del | .//w:moveFrom | .//w:moveTo"
_DELETED_MARK = f"{qn('w:pPr')}/{qn('w:rPr')}/{qn('w:del')}"
_DELETED_ROW = f"{qn('w:trPr')}/{qn('w:del')}"


@dataclass
class _Walk:
    """What the walk over a DOCX body left out."""

    hidden_runs: int = 0


def _is_hidden(run: etree._Element) -> bool:
    properties = run.find(qn("w:rPr"))
    vanish = properties.find(qn("w:vanish")) if properties is not None else None
    return vanish is not None and vanish.get(qn("w:val")) not in ("0", "false")


def _run_text(run: etree._Element) -> str:
    """Visible text of one run: w:t, tabs and breaks. Field codes, deleted text and drawings carry none."""
    parts: list[str] = []
    for child in run:
        if child.tag == _TEXT:
            parts.append(child.text or "")
        elif child.tag in _RUN_BREAKS:
            parts.append(_RUN_BREAKS[child.tag])
    return "".join(parts)


def accepted_text(element: etree._Element, walk: _Walk) -> str:
    """Text of a paragraph, as Word shows it with all changes accepted.

    Runs are collected in document order through every container that can hold them (w:ins,
    w:moveTo, w:hyperlink, w:fldSimple, w:smartTag, w:sdtContent, w:customXml); deleted and
    moved-away containers and hidden runs are left out.
    """
    parts: list[str] = []
    for child in element:
        tag = child.tag
        if tag in _DELETED or tag in _PROPERTIES:
            continue
        if tag == _RUN:
            if _is_hidden(child):
                walk.hidden_runs += 1
            else:
                parts.append(_run_text(child))
        elif len(child):
            parts.append(accepted_text(child, walk))
    return "".join(parts)


def _heading_level(paragraph: Paragraph) -> int:
    """1-based outline level from the style name (Heading 2, SchLevel1Heading, Title), the paragraph's own
    w:outlineLvl, or the outline level its style chain declares; 0 for body text."""
    style = paragraph.style
    name = (style.name if style is not None else "") or ""
    if name.lower() == "title":
        return 1
    if re.search(r"heading", name, re.IGNORECASE):
        digit = re.search(r"(\d)", name)
        if digit:
            return int(digit.group(1))
    own = _outline_level(paragraph._p.pPr)
    if own is not None:
        return own + 1
    depth = 0
    while style is not None and depth < 8:
        declared = _outline_level(style.element.find(qn("w:pPr")))
        if declared is not None:
            return declared + 1
        style = style.base_style
        depth += 1
    return 0


def _outline_level(properties: etree._Element | None) -> int | None:
    """w:outlineLvl as Word stores it: 0–8 are heading levels, 9 is body text."""
    outline = properties.find(qn("w:outlineLvl")) if properties is not None else None
    value = outline.get(qn("w:val")) if outline is not None else None
    if value is None:
        return None
    try:
        level = int(value)
    except ValueError:
        return None
    return level if 0 <= level <= 8 else None


def _docx_pages(data: bytes) -> int | None:
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            app_xml = archive.read("docProps/app.xml").decode("utf-8", errors="replace")
    except (KeyError, zipfile.BadZipFile):
        return None
    match = re.search(r"<Pages>(\d+)</Pages>", app_xml)
    return int(match.group(1)) if match else None


class TooLargeToRead(UnsupportedFile):
    """Well-formed, but it would cost more memory or time than any contract needs; refused before parsing."""


def _unpacked_size(data: bytes) -> int | None:
    """The declared uncompressed size of a zip package; zipfile never reads a member past its declaration."""
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            return sum(info.file_size for info in archive.infolist())
    except zipfile.BadZipFile:
        return None


def read_docx(data: bytes) -> ReadResult:
    unpacked = _unpacked_size(data)
    if unpacked is not None and unpacked > MAX_DOCX_UNPACKED_BYTES:
        raise TooLargeToRead(f"the .docx unpacks to {unpacked // (1024 * 1024)} MB; the limit is {MAX_DOCX_UNPACKED_BYTES // (1024 * 1024)} MB")
    try:
        document = DocxDocument(io.BytesIO(data))
    except (PackageNotFoundError, zipfile.BadZipFile, KeyError, ValueError) as error:
        raise UnsupportedFile("the file is not a readable .docx package") from error
    body = document.element.body
    walk = _Walk()
    blocks: list[Block] = []
    title = ""
    # Text of paragraphs whose mark is deleted: once accepted, they run into the next paragraph.
    carry = ""

    def add(text: str, level: int = 0) -> None:
        nonlocal title
        if not text:
            return
        if level:
            blocks.append(Block("heading", text, level))
            return
        if not title and not blocks:
            title = text
        blocks.append(Block("text", text))

    for child in body.iterchildren():
        if child.tag == _PARAGRAPH:
            text = accepted_text(child, walk)
            if child.find(_DELETED_MARK) is not None:
                carry += text
                continue
            text = (carry + text).strip()
            carry = ""
            if text:
                add(text, _heading_level(Paragraph(child, document)))
        elif child.tag == _TABLE:
            add(carry.strip())
            carry = ""
            for row in Table(child, document).rows:
                if row._tr.find(_DELETED_ROW) is not None:
                    continue
                cells: list[str] = []
                for cell in row.cells:
                    cell_text = " ".join(t for t in (accepted_text(p._p, walk).strip() for p in cell.paragraphs) if t)
                    if cell_text and cell_text not in cells:  # merged cells repeat
                        cells.append(cell_text)
                if cells:
                    add(" | ".join(cells))
    add(carry.strip())
    return ReadResult(
        blocks=blocks,
        pages=_docx_pages(data),
        title=title,
        tracked_changes=len(body.xpath(_REVISIONS_XPATH)),
        hidden_runs=walk.hidden_runs,
    )


# ---------------------------------------------------------------------------- PDF


def read_pdf(data: bytes) -> ReadResult:
    try:
        reader = PdfReader(io.BytesIO(data))
        page_count = len(reader.pages)
    except (PyPdfError, ValueError, KeyError) as error:
        raise UnsupportedFile("the file is not a readable PDF") from error
    if page_count > MAX_PDF_PAGES:
        raise TooLargeToRead(f"the PDF has {page_count} pages; the limit is {MAX_PDF_PAGES}")
    try:
        pages = list(reader.pages)
    except (PyPdfError, ValueError, KeyError) as error:
        raise UnsupportedFile("the file is not a readable PDF") from error
    lines: list[str] = []
    for page in pages:
        # Layout mode keeps blank lines between paragraphs, which is the only structure most PDFs carry.
        try:
            text = page.extract_text(extraction_mode="layout") or ""
        except Exception:  # noqa: BLE001 - fall back to the plain extractor for odd PDFs
            text = page.extract_text() or ""
        lines.extend(re.sub(r"[ \t]{2,}", " ", line) for line in text.splitlines())
        lines.append("")
    return ReadResult(blocks=_blocks_from_lines(lines), pages=len(pages), title=_first_line(lines))


# ---------------------------------------------------------------------------- TXT


def read_txt(data: bytes) -> ReadResult:
    text = data.decode("utf-8", errors="replace")
    lines = text.splitlines()
    return ReadResult(blocks=_blocks_from_lines(lines), pages=None, title=_first_line(lines))


def _first_line(lines: list[str]) -> str:
    for line in lines:
        if line.strip():
            return line.strip()
    return ""


def _blocks_from_lines(lines: list[str]) -> list[Block]:
    """Paragraphs are separated by blank lines; short numbered or all-caps lines are headings."""
    blocks: list[Block] = []
    paragraph: list[str] = []

    def flush() -> None:
        if paragraph:
            blocks.append(Block("text", " ".join(paragraph)))
            paragraph.clear()

    seen_heading = False
    for raw in lines:
        line = raw.strip()
        if not line:
            flush()
            continue
        if looks_like_heading(line):
            flush()
            numbered = bool(HEADING_NUMBER.match(line))
            if not numbered and not seen_heading and not blocks:
                # An all-caps first line is the title, not clause 1.
                blocks.append(Block("text", line))
                continue
            seen_heading = True
            blocks.append(Block("heading", line, 1 if "." not in line.split(" ", 1)[0].rstrip(".") else 2))
            continue
        paragraph.append(line)
    flush()
    return blocks
