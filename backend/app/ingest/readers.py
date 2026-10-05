"""Read DOCX, PDF and TXT into blocks. Nothing here calls a model.

DOCX is read as Word shows it with every tracked change accepted: inserted text is kept, deleted
and moved-away text is dropped, runs marked hidden are dropped, deleted table rows are skipped and
a deleted paragraph mark joins its paragraph to the next. python-docx's `paragraph.text` does none
of this; it walks only the runs that hang directly off the paragraph, so on negotiated paper it
loses both the old wording and the new. What the reader left out is counted and stored, so the
interface can say which view of the file the model read.
"""

from __future__ import annotations

import codecs
import io
import re
import zipfile
from dataclasses import dataclass, field
from typing import cast

from docx import Document as DocxDocument
from docx.opc.exceptions import PackageNotFoundError
from docx.oxml.ns import qn
from docx.oxml.text.paragraph import CT_P
from docx.text.paragraph import Paragraph
from lxml import etree
from pypdf import PdfReader
from pypdf.errors import PyPdfError

from .coverage import PartCoverage, docx_coverage, pdf_coverage, txt_coverage
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
    # What this reading did with each part of the file (ingest.coverage); anything unread is listed as unread.
    coverage: list[PartCoverage] = field(default_factory=list)


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
_SDT = qn("w:sdt")
_SDT_CONTENT = qn("w:sdtContent")
_ROW = qn("w:tr")
_CELL = qn("w:tc")
# A title or a heading is a line, not a page: a paragraph longer than this becomes body text under a shortened heading,
# so a 100,000-character paragraph no longer rides into every prompt whole as the section's name (sweep, 2026-10-01).
MAX_TITLE_CHARS = 200


@dataclass
class _Walk:
    """What the walk over a DOCX body left out, and the styles that decide what is hidden."""

    styles: _Styles
    hidden_runs: int = 0
    # Runs hidden only through a style (a character style named Hidden, a paragraph style whose runs vanish) or
    # through w:specVanish; counted apart so the coverage report can say which door was closed.
    style_hidden_runs: int = 0


_STYLE_DEPTH = 12


class _Styles:
    """The document's styles, read once: for each style id, the style it is based on and whether its run
    properties hide text. Word hides text through styles as readily as through a run's own properties, and a
    reader that resolves only the run's own w:vanish hands style-hidden text to the model (reader v6)."""

    def __init__(self, styles: etree._Element | None) -> None:
        self._based_on: dict[str, str | None] = {}
        self._hidden: dict[str, bool | None] = {}
        self.default_hidden = False
        if styles is None:
            return
        defaults = styles.find(f"{qn('w:docDefaults')}/{qn('w:rPrDefault')}/{qn('w:rPr')}")
        self.default_hidden = _vanish_state(defaults) is True
        for style in styles.iterfind(qn("w:style")):
            style_id = style.get(qn("w:styleId"))
            if not style_id:
                continue
            based = style.find(qn("w:basedOn"))
            self._based_on[style_id] = based.get(qn("w:val")) if based is not None else None
            self._hidden[style_id] = _vanish_state(style.find(qn("w:rPr")))

    def hides(self, style_id: str | None) -> bool | None:
        """True or False when a style in the chain says; None when none does."""
        seen = 0
        while style_id and seen < _STYLE_DEPTH:
            state = self._hidden.get(style_id)
            if state is not None:
                return state
            style_id = self._based_on.get(style_id)
            seen += 1
        return None


def _vanish_state(properties: etree._Element | None) -> bool | None:
    """What a run-properties bag says about hiding: w:vanish (on unless its value is off), or w:specVanish; None when silent."""
    if properties is None:
        return None
    vanish = properties.find(qn("w:vanish"))
    if vanish is not None:
        return vanish.get(qn("w:val")) not in ("0", "false")
    if properties.find(qn("w:specVanish")) is not None:
        return True
    return None


def _style_id(properties: etree._Element | None, tag: str) -> str | None:
    style = properties.find(qn(tag)) if properties is not None else None
    return style.get(qn("w:val")) if style is not None else None


def _paragraph_hides(paragraph: etree._Element, styles: _Styles) -> bool:
    """Whether the paragraph's style chain hides its runs. The paragraph mark's own run properties (w:pPr/w:rPr)
    speak for the mark alone, not for the runs, and are not consulted."""
    return styles.hides(_style_id(paragraph.find(qn("w:pPr")), "w:pStyle")) is True


def _hidden_by(run: etree._Element, paragraph_hides: bool, styles: _Styles) -> str | None:
    """How this run is hidden, if it is: "run" by its own properties, "style" by a style or the paragraph's; None when shown.
    Precedence is Word's: the run's own w:vanish decides either way; then its character style; then the paragraph's style;
    then the document default."""
    properties = run.find(qn("w:rPr"))
    own = _vanish_state(properties)
    if own is not None:
        return "run" if own else None
    by_character_style = styles.hides(_style_id(properties, "w:rStyle"))
    if by_character_style is not None:
        return "style" if by_character_style else None
    if paragraph_hides or styles.default_hidden:
        return "style"
    return None


def _run_text(run: etree._Element) -> str:
    """Visible text of one run: w:t, tabs and breaks. Field codes, deleted text and drawings carry none."""
    parts: list[str] = []
    for child in run:
        if child.tag == _TEXT:
            parts.append(child.text or "")
        elif child.tag in _RUN_BREAKS:
            parts.append(_RUN_BREAKS[child.tag])
    return "".join(parts)


def accepted_text(element: etree._Element, walk: _Walk, paragraph_hides: bool | None = None) -> str:
    """Text of a paragraph, as Word shows it with all changes accepted.

    Runs are collected in document order through every container that can hold them (w:ins,
    w:moveTo, w:hyperlink, w:fldSimple, w:smartTag, w:sdtContent, w:customXml); deleted and
    moved-away containers and hidden runs are left out, whether hidden by their own properties or by a style.
    """
    if paragraph_hides is None:
        paragraph_hides = element.tag == _PARAGRAPH and _paragraph_hides(element, walk.styles)
    parts: list[str] = []
    for child in element:
        tag = child.tag
        if tag in _DELETED or tag in _PROPERTIES:
            continue
        if tag == _RUN:
            hidden = _hidden_by(child, paragraph_hides, walk.styles)
            if hidden == "run":
                walk.hidden_runs += 1
            elif hidden == "style":
                walk.style_hidden_runs += 1
            else:
                parts.append(_run_text(child))
        elif len(child):
            parts.append(accepted_text(child, walk, paragraph_hides))
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
    match = re.search(r"<Pages>(\d{1,9})</Pages>", app_xml)
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
    except (PackageNotFoundError, zipfile.BadZipFile, KeyError, ValueError, AttributeError, TypeError, etree.XMLSyntaxError) as error:
        # A valid zip with a broken or hostile package inside: python-docx fails in many shapes, all of them a 422 here.
        raise UnsupportedFile("the file is not a readable .docx package") from error
    body = document.element.body
    try:
        styles_element: etree._Element | None = document.styles.element
    except (KeyError, AttributeError):  # a package without a styles part: nothing hides through a style
        styles_element = None
    walk = _Walk(styles=_Styles(styles_element))
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
            title = shorten_title(text)
        blocks.append(Block("text", text))

    def cell_text(cell: etree._Element) -> str:
        """A cell's paragraphs, the rows of any table nested in it, and the content of any control in it."""
        parts: list[str] = []
        for child in cell.iterchildren():
            if child.tag == _PARAGRAPH:
                parts.append(accepted_text(child, walk).strip())
            elif child.tag == _TABLE:
                parts.extend(table_rows(child))
            elif child.tag == _SDT:
                content = child.find(_SDT_CONTENT)
                if content is not None:
                    parts.append(cell_text(content))
        return " ".join(part for part in parts if part)

    def table_rows(table: etree._Element) -> list[str]:
        """Each row as its cells joined with ' | ': a merged cell once, a deleted row not at all, a row inside a
        content control like any other. Nested tables were dropped before 2026-10-01; coverage said they were read."""
        rows: list[str] = []
        for child in table.iterchildren():
            if child.tag == _SDT:
                content = child.find(_SDT_CONTENT)
                if content is not None:
                    rows.extend(table_rows(content))
                continue
            if child.tag != _ROW or child.find(_DELETED_ROW) is not None:
                continue
            cells: list[str] = []
            for cell in child.iterchildren(_CELL):
                text = cell_text(cell)
                if text and text not in cells:  # a horizontally merged cell is one cell; a vertical continuation is empty
                    cells.append(text)
            if cells:
                rows.append(" | ".join(cells))
        return rows

    def walk_container(container: etree._Element) -> None:
        """Paragraphs and tables in document order, entering block-level content controls (w:sdt), which wrap a
        heading, a clause or a whole table and were skipped before 2026-10-01 while coverage called them read."""
        nonlocal carry
        for child in container.iterchildren():
            if child.tag == _PARAGRAPH:
                text = accepted_text(child, walk)
                if child.find(_DELETED_MARK) is not None:
                    carry += text
                    continue
                text = (carry + text).strip()
                carry = ""
                if text:
                    add(text, _heading_level(Paragraph(cast(CT_P, child), document)))
            elif child.tag == _TABLE:
                add(carry.strip())
                carry = ""
                for row in table_rows(child):
                    add(row)
            elif child.tag == _SDT:
                content = child.find(_SDT_CONTENT)
                if content is not None:
                    walk_container(content)

    walk_container(body)
    add(carry.strip())
    tracked = len(body.xpath(_REVISIONS_XPATH))
    return ReadResult(
        blocks=blocks,
        pages=_docx_pages(data),
        title=title,
        tracked_changes=tracked,
        hidden_runs=walk.hidden_runs + walk.style_hidden_runs,
        coverage=docx_coverage(data, etree.tostring(body, encoding="unicode"), tracked, walk.hidden_runs, walk.style_hidden_runs),
    )


# ---------------------------------------------------------------------------- PDF


def read_pdf(data: bytes) -> ReadResult:
    try:
        reader = PdfReader(io.BytesIO(data))
        encrypted = bool(reader.is_encrypted)
        page_count = 0 if encrypted else len(reader.pages)
    except (PyPdfError, ValueError, KeyError) as error:
        raise UnsupportedFile("the file is not a readable PDF") from error
    if encrypted:
        raise UnsupportedFile("the PDF is encrypted; remove the password and upload it again")
    if page_count > MAX_PDF_PAGES:
        raise TooLargeToRead(f"the PDF has {page_count} pages; the limit is {MAX_PDF_PAGES}")
    try:
        pages = list(reader.pages)
    except (PyPdfError, ValueError, KeyError) as error:
        raise UnsupportedFile("the file is not a readable PDF") from error
    lines: list[str] = []
    textless = 0
    for page in pages:
        # Layout mode keeps blank lines between paragraphs, which is the only structure most PDFs carry.
        try:
            text = page.extract_text(extraction_mode="layout") or ""
        except Exception:  # noqa: BLE001 - fall back to the plain extractor for odd PDFs
            text = page.extract_text() or ""
        if not text.strip():
            textless += 1  # an image-only (scanned) page: the record says so instead of "unknown"
        lines.extend(re.sub(r"[ \t]{2,}", " ", line) for line in text.splitlines())
        lines.append("")
    return ReadResult(coverage=pdf_coverage(page_count, textless), blocks=_blocks_from_lines(lines), pages=len(pages), title=_first_line(lines))


# ---------------------------------------------------------------------------- TXT


_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def decode_text(data: bytes) -> tuple[str, str]:
    """The text of a plain-text file and the name of the encoding it was read with. A byte-order mark decides; then
    UTF-16 when every other byte is a NUL; then strict UTF-8; then Windows-1252, the encoding of text saved from Word
    on a Western-locale machine. Before 2026-10-01 everything was read as UTF-8 with replacement characters, so a
    UTF-16 file became NUL-interleaved garbage with a 201 and "€1,500" became "\ufffd1,500"."""
    if data.startswith(codecs.BOM_UTF8):
        return data[len(codecs.BOM_UTF8) :].decode("utf-8", errors="replace"), "UTF-8"
    if data.startswith((codecs.BOM_UTF16_LE, codecs.BOM_UTF16_BE)):
        return data.decode("utf-16", errors="replace"), "UTF-16"
    sample = data[:4096]
    if sample.count(b"\x00") > len(sample) // 4:
        # Every other byte a NUL: UTF-16 without its mark, which strict UTF-8 would accept as NUL-interleaved text.
        little_endian = sample[1:2] == b"\x00"
        return data.decode("utf-16-le" if little_endian else "utf-16-be", errors="replace"), "UTF-16"
    try:
        return data.decode("utf-8"), "UTF-8"
    except UnicodeDecodeError:
        return data.decode("cp1252", errors="replace"), "Windows-1252"


def read_txt(data: bytes) -> ReadResult:
    text, encoding = decode_text(data)
    lines = _CONTROL_CHARS.sub("", text).splitlines()
    return ReadResult(coverage=txt_coverage(encoding), blocks=_blocks_from_lines(lines), pages=None, title=_first_line(lines))


def _first_line(lines: list[str]) -> str:
    for line in lines:
        if line.strip():
            return shorten_title(line.strip())
    return ""


def shorten_title(text: str) -> str:
    """The text as a title: whole when it is a line, else its first words and an ellipsis."""
    if len(text) <= MAX_TITLE_CHARS:
        return text
    cut = text.rfind(" ", MAX_TITLE_CHARS // 2, MAX_TITLE_CHARS)
    return text[: cut if cut > 0 else MAX_TITLE_CHARS].rstrip() + "…"


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
