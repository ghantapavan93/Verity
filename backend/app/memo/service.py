"""The one artifact: a review memo built from verified findings, as HTML and as DOCX.

The DOCX is a working Word document, not a flattened export: built-in paragraph styles, a
sources table each citation links to (internal hyperlinks to bookmarks), a link from every
source back to the exact run and finding in the workbench, core properties naming the run, and a
custom-properties part carrying the run id, its fingerprint, the document hash, the model and
the prompt version and hash, so the file can be traced to its record from inside Word.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from html import escape
from pathlib import Path
from xml.sax.saxutils import escape as xml_escape

from docx import Document as DocxDocument
from docx.document import Document as WordDocument
from docx.enum.style import WD_STYLE_TYPE
from docx.opc.constants import RELATIONSHIP_TYPE as RT
from docx.opc.packuri import PackURI
from docx.opc.part import Part
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Pt, RGBColor
from docx.text.paragraph import Paragraph
from lxml import etree

from ..config import settings
from ..hashing import sha256_file
from ..models import EvidenceSpan, Finding, Run, iso, utcnow

STATUS_LABELS = {"pass": "Within guidance", "needs_review": "Needs review", "missing": "Not found", "unresolved": "Unresolved"}
AUTHOR = "Contract Workbench"
CUSTOM_PROPERTIES_CONTENT_TYPE = "application/vnd.openxmlformats-officedocument.custom-properties+xml"
CUSTOM_PROPERTIES_FMTID = "{D5CDD505-2E9C-101B-9397-08002B2CF9AE}"


@dataclass(frozen=True)
class Source:
    number: int
    finding: Finding
    span: EvidenceSpan
    title: str


def deep_link(run: Run, finding: Finding) -> str:
    """The workbench URL that reopens this run at this finding, with the cited passage highlighted."""
    return f"{settings.app_url}/?document={run.document_id}&run={run.id}&finding={finding.id}"


def _section_label(span: EvidenceSpan) -> str:
    return span.cited_section_label or ""


def _review_line(finding: Finding) -> str:
    """'Confirmed by A. Reviewer on 28 September 2026: note' from the finding's current review."""
    review = finding.review
    if review is None:
        return ""
    when = review.created_at.astimezone().strftime("%d %B %Y")
    note = f": {review.note}" if review.note else ""
    return f"{review.verdict.capitalize()} by {review.reviewer} on {when}{note}"


def _located(span: EvidenceSpan) -> str:
    if span.verified:
        return f"verified verbatim · {span.method} · characters {span.start}–{span.end}"
    return "not found in the document; withheld"


def _evidence_head(finding: Finding) -> str:
    return "Closest provision read" if finding.status == "missing" else "Observed language"


def _sources(findings: list[Finding], section_titles: dict[str, str]) -> list[Source]:
    sources: list[Source] = []
    for finding in findings:
        for span in finding.spans:
            title = section_titles.get(span.section_id or "", _section_label(span))
            sources.append(Source(len(sources) + 1, finding, span, title))
    return sources


# ----------------------------------------------------------------------------- HTML


def memo_html(run: Run, findings: list[Finding], section_titles: dict[str, str]) -> str:
    date = datetime.now().astimezone().strftime("%d %B %Y")
    issues = [f for f in findings if f.status in ("needs_review", "missing")]
    sources = _sources(findings, section_titles)
    by_span = {id(s.span): s for s in sources}
    parts = [
        "<!doctype html><html lang='en'><head><meta charset='utf-8'><title>Contract review memo</title>",
        "<style>"
        "body{font:15px/1.55 Georgia,serif;max-width:760px;margin:40px auto;padding:0 20px;color:#1b1a18}"
        "h1{font-size:22px;letter-spacing:.02em}h2{font-size:16px;margin-top:28px}"
        "dl{display:grid;grid-template-columns:140px 1fr;gap:6px 14px}dt{color:#6a655c}"
        "blockquote{margin:8px 0;padding-left:12px;border-left:3px solid #ccc}small{color:#6a655c}"
        "table{border-collapse:collapse;font-size:13px}td,th{padding:4px 8px;border-bottom:1px solid #ddd;text-align:left;vertical-align:top}"
        "a{color:#0b5cad}"
        "</style></head><body>",
        "<h1>Contract Review Memo</h1>",
        f"<dl><dt>Agreement</dt><dd>{escape(run.document.name)}</dd><dt>Date</dt><dd>{date}</dd><dt>Question</dt><dd>{escape(run.question)}</dd>",
        f"<dt>Guidance</dt><dd>{escape(run.guidance.text) if run.guidance else 'none supplied'}</dd></dl>",
        f"<h2>Issues requiring review ({len(issues)})</h2>",
    ]
    if issues:
        parts.append("<ol>" + "".join(f"<li>{escape(f.topic)}</li>" for f in issues) + "</ol>")
    else:
        parts.append("<p>None. Every finding was within guidance or a plain answer.</p>")
    for f in findings:
        parts.append(f"<h2>{escape(f.topic)} · {STATUS_LABELS.get(f.status, f.status)}</h2>")
        parts.append(f"<p>{escape(f.conclusion)}</p>")
        for span in f.spans:
            source = by_span[id(span)]
            parts.append(
                f"<p><strong>{_evidence_head(f)}</strong> <small>({escape(source.title)})</small> "
                f"<a href='#src-{source.number}'>[{source.number}]</a></p><blockquote>{escape(span.quote)}</blockquote>"
            )
        if f.guidance_reference:
            parts.append(f"<p><strong>Legal guidance.</strong> {escape(f.guidance_reference)}</p>")
        position = [
            f"<strong>Observed</strong> {escape(f.observed)}" if f.observed else "",
            f"<strong>Required</strong> {escape(f.required)}" if f.required else "",
        ]
        if any(position):
            parts.append("<p>" + " · ".join(p for p in position if p) + "</p>")
        if f.suggested_position:
            parts.append(f"<p><strong>Suggested position.</strong> {escape(f.suggested_position)}</p>")
        if f.review is not None:
            parts.append(f"<p><strong>Reviewed.</strong> {escape(_review_line(f))}</p>")
    parts.append("<h2>Sources</h2><table><tr><th>#</th><th>Section</th><th>Located</th><th></th></tr>")
    for source in sources:
        parts.append(
            f"<tr id='src-{source.number}'><td>{source.number}</td><td>{escape(source.title)}</td><td>{escape(_located(source.span))}</td>"
            f"<td><a href='{escape(deep_link(run, source.finding))}'>Open in the workbench</a></td></tr>"
        )
    parts.append("</table>")
    parts.append(
        f"<hr><p><small>Generated from run {escape(run.id)} · model {escape(run.model)} · "
        f"prompt {escape(run.prompt_version)} ({escape(run.prompt_hash[:12])}) · "
        "every quoted passage was verified verbatim against the document text before this memo was written.</small></p></body></html>"
    )
    return "".join(parts)


# ----------------------------------------------------------------------------- DOCX


def _ensure_hyperlink_style(document: WordDocument) -> None:
    if "Hyperlink" in [style.name for style in document.styles]:
        return
    style = document.styles.add_style("Hyperlink", WD_STYLE_TYPE.CHARACTER)
    style.font.color.rgb = RGBColor(0x0B, 0x5C, 0xAD)
    style.font.underline = True


def _bookmark(paragraph: Paragraph, name: str, text: str, bookmark_id: int) -> None:
    start = OxmlElement("w:bookmarkStart")
    start.set(qn("w:id"), str(bookmark_id))
    start.set(qn("w:name"), name)
    end = OxmlElement("w:bookmarkEnd")
    end.set(qn("w:id"), str(bookmark_id))
    paragraph._p.append(start)
    paragraph.add_run(text)
    paragraph._p.append(end)


def _hyperlink_run(text: str) -> etree._Element:
    run = OxmlElement("w:r")
    properties = OxmlElement("w:rPr")
    style = OxmlElement("w:rStyle")
    style.set(qn("w:val"), "Hyperlink")
    properties.append(style)
    run.append(properties)
    node = OxmlElement("w:t")
    node.text = text
    node.set(qn("xml:space"), "preserve")
    run.append(node)
    return run


def _internal_link(paragraph: Paragraph, anchor: str, text: str) -> None:
    hyperlink = OxmlElement("w:hyperlink")
    hyperlink.set(qn("w:anchor"), anchor)
    hyperlink.append(_hyperlink_run(text))
    paragraph._p.append(hyperlink)


def _external_link(paragraph: Paragraph, url: str, text: str) -> None:
    relationship_id = paragraph.part.relate_to(url, RT.HYPERLINK, is_external=True)
    hyperlink = OxmlElement("w:hyperlink")
    hyperlink.set(qn("r:id"), relationship_id)
    hyperlink.append(_hyperlink_run(text))
    paragraph._p.append(hyperlink)


def _custom_properties(document: WordDocument, values: dict[str, str]) -> None:
    """A docProps/custom.xml part: typed name/value pairs Word shows under File → Info → Properties → Advanced."""
    rows = "".join(
        f'<property fmtid="{CUSTOM_PROPERTIES_FMTID}" pid="{index}" name="{xml_escape(name, {chr(34): "&quot;"})}">'
        f"<vt:lpwstr>{xml_escape(value)}</vt:lpwstr></property>"
        for index, (name, value) in enumerate(values.items(), start=2)
    )
    xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/custom-properties" '
        'xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes">' + rows + "</Properties>"
    )
    package = document.part.package
    part = Part(PackURI("/docProps/custom.xml"), CUSTOM_PROPERTIES_CONTENT_TYPE, xml.encode("utf-8"), package)
    package.relate_to(part, RT.CUSTOM_PROPERTIES)


def _properties(document: WordDocument, run: Run, verified: int, total: int) -> None:
    core = document.core_properties
    core.title = f"Contract review memo · {run.document.name}"
    core.subject = run.question
    core.author = AUTHOR
    core.last_modified_by = AUTHOR
    core.category = "Review memo"
    core.keywords = "contract review; verified citations; contract workbench"
    core.identifier = run.id
    core.version = run.prompt_version
    core.comments = f"run {run.id} · document sha256 {run.document_sha256} · model {run.model} · prompt {run.prompt_version} {run.prompt_hash}"
    _custom_properties(
        document,
        {
            "workbench_run_id": run.id,
            "workbench_run_fingerprint": run.fingerprint or "",
            "workbench_document_id": run.document_id,
            "workbench_document_sha256": run.document_sha256,
            "workbench_guidance_sha256": run.guidance_sha256 or "",
            "workbench_model": run.model,
            "workbench_prompt_version": run.prompt_version,
            "workbench_prompt_hash": run.prompt_hash,
            "workbench_citations_verified": f"{verified} of {total}",
            "workbench_generated_at": iso(utcnow()) or "",
            "workbench_link": f"{settings.app_url}/?document={run.document_id}&run={run.id}",
        },
    )


def memo_docx(run: Run, findings: list[Finding], section_titles: dict[str, str], out_dir: Path) -> tuple[Path, str]:
    out_dir.mkdir(parents=True, exist_ok=True)
    document = DocxDocument()
    normal = document.styles["Normal"]
    normal.font.name = "Georgia"
    normal.font.size = Pt(11)
    _ensure_hyperlink_style(document)
    sources = _sources(findings, section_titles)
    by_span = {id(s.span): s for s in sources}
    _properties(document, run, sum(1 for s in sources if s.span.verified), len(sources))

    document.add_heading("Contract Review Memo", level=1)
    date = datetime.now().astimezone().strftime("%d %B %Y")
    table = document.add_table(rows=0, cols=2)
    table.style = "Table Grid"
    for label, value in (
        ("Agreement", run.document.name),
        ("Date", date),
        ("Question", run.question),
        ("Guidance", run.guidance.text if run.guidance else "none supplied"),
    ):
        row = table.add_row().cells
        row[0].text = label
        row[1].text = value

    issues = [f for f in findings if f.status in ("needs_review", "missing")]
    document.add_heading(f"Issues requiring review ({len(issues)})", level=2)
    if issues:
        for f in issues:
            document.add_paragraph(f.topic, style="List Number")
    else:
        document.add_paragraph("None. Every finding was within guidance or a plain answer.")

    for f in findings:
        document.add_heading(f"{f.topic} · {STATUS_LABELS.get(f.status, f.status)}", level=2)
        document.add_paragraph(f.conclusion)
        for span in f.spans:
            source = by_span[id(span)]
            p = document.add_paragraph()
            p.add_run(f"{_evidence_head(f)} ").bold = True
            p.add_run(f"({source.title}) ")
            _internal_link(p, f"src_{source.number}", f"[{source.number}]")
            quote = document.add_paragraph(span.quote)
            quote.paragraph_format.left_indent = Pt(18)
        if f.guidance_reference:
            p = document.add_paragraph()
            p.add_run("Legal guidance. ").bold = True
            p.add_run(f.guidance_reference)
        if f.observed or f.required:
            p = document.add_paragraph()
            if f.observed:
                p.add_run("Observed ").bold = True
                p.add_run(f"{f.observed}   ")
            if f.required:
                p.add_run("Required ").bold = True
                p.add_run(f.required)
        if f.suggested_position:
            p = document.add_paragraph()
            p.add_run("Suggested position. ").bold = True
            p.add_run(f.suggested_position)
        if f.review is not None:
            p = document.add_paragraph()
            p.add_run("Reviewed. ").bold = True
            p.add_run(_review_line(f))

    document.add_heading("Sources", level=2)
    sources_table = document.add_table(rows=1, cols=4)
    sources_table.style = "Table Grid"
    header = sources_table.rows[0].cells
    for cell, text in zip(header, ("#", "Section", "Located", "Record"), strict=True):
        cell.text = text
    for source in sources:
        row = sources_table.add_row().cells
        _bookmark(row[0].paragraphs[0], f"src_{source.number}", str(source.number), source.number)
        row[1].text = source.title
        row[2].text = _located(source.span)
        _external_link(row[3].paragraphs[0], deep_link(run, source.finding), "Open in the workbench")

    footer = document.add_paragraph()
    footer.add_run(
        f"Generated from run {run.id} · model {run.model} · prompt {run.prompt_version} ({run.prompt_hash[:12]}). "
        "Every quoted passage was verified verbatim against the document text before this memo was written. "
        "The run id, document hash, model and prompt are also in this file's document properties."
    ).italic = True
    path = out_dir / f"memo-{run.id}.docx"
    document.save(str(path))
    return path, sha256_file(path)
