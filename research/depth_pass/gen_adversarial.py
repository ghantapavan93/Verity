"""Generate the adversarial and unusual files of the reader sweep of 2026-10-01 into a directory (default ./gen).

Nothing here touches the API. Seven of these files are the fixtures of backend/tests/test_reader_sweep.py; the
mapping is in README.md beside this script. Usage: python gen_adversarial.py [output-dir]
"""

from __future__ import annotations

import io
import json
import os
import random
import re
import sys
import zipfile
from pathlib import Path

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Pt
from pypdf import PdfReader, PdfWriter

GEN = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).parent / "gen"
GEN.mkdir(parents=True, exist_ok=True)
W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"

CLAUSES = [
    (
        "Definitions",
        "In this Agreement the following words have the following meanings. Business Day means a day other than a Saturday, Sunday or public holiday in England.",
    ),
    ("Term", "This Agreement starts on the Effective Date and continues for 24 months unless terminated earlier in accordance with clause 3."),
    (
        "Termination",
        "Either party may terminate this Agreement for convenience on giving the other party not less than 30 days written notice. Either party may terminate immediately if the other party commits a material breach which is not remedied within 14 days of notice.",
    ),
    (
        "Governing Law",
        "This Agreement and any dispute arising out of it are governed by the laws of England and Wales, and the courts of England have exclusive jurisdiction.",
    ),
    ("Notices", "Notices must be in writing and delivered by hand or sent by prepaid first-class post to the address of the receiving party set out above."),
]


def save_docx(doc: Document, name: str) -> Path:
    path = GEN / name
    doc.save(str(path))
    return path


def docx_bytes(doc: Document) -> bytes:
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def rewrite(
    data: bytes,
    name: str,
    edits: dict[str, object] | None = None,
    add: dict[str, bytes] | None = None,
    content_types: list[tuple[str, str]] | None = None,
    rels: list[tuple[str, str, str, bool]] | None = None,
) -> Path:
    """Rebuild a docx: ``edits`` maps member name -> bytes or callable(bytes)->bytes; ``add`` adds members;
    ``content_types`` adds <Override PartName ContentType>; ``rels`` adds (id, type, target, external) to document.xml.rels."""
    edits = dict(edits or {})
    src = zipfile.ZipFile(io.BytesIO(data))
    out_buf = io.BytesIO()
    members = {n: src.read(n) for n in src.namelist()}
    for member, edit in edits.items():
        members[member] = edit(members[member]) if callable(edit) else edit
    for member, blob in (add or {}).items():
        members[member] = blob
    if content_types:
        ct = members["[Content_Types].xml"].decode("utf-8")
        for part, ctype in content_types:
            ct = ct.replace("</Types>", f'<Override PartName="{part}" ContentType="{ctype}"/></Types>')
        members["[Content_Types].xml"] = ct.encode("utf-8")
    if rels:
        rel_xml = members["word/_rels/document.xml.rels"].decode("utf-8")
        for rid, rtype, target, external in rels:
            mode = ' TargetMode="External"' if external else ""
            rel_xml = rel_xml.replace("</Relationships>", f'<Relationship Id="{rid}" Type="{rtype}" Target="{target}"{mode}/></Relationships>')
        members["word/_rels/document.xml.rels"] = rel_xml.encode("utf-8")
    with zipfile.ZipFile(out_buf, "w", zipfile.ZIP_DEFLATED) as z:
        for member, blob in members.items():
            z.writestr(member, blob)
    path = GEN / name
    path.write_bytes(out_buf.getvalue())
    return path


def body_insert(xml: bytes, snippet: str, where: str = "end") -> bytes:
    """Insert raw WordprocessingML before w:sectPr (end of the body) or right after <w:body>."""
    text = xml.decode("utf-8")
    if where == "start":
        return text.replace("<w:body>", "<w:body>" + snippet, 1).encode("utf-8")
    idx = text.rfind("<w:sectPr")
    if idx == -1:
        idx = text.rfind("</w:body>")
    return (text[:idx] + snippet + text[idx:]).encode("utf-8")


def base_doc(headings: bool = True, numbering: str = "none") -> Document:
    """One short contract. numbering: 'none' (heading style, no number), 'typed' (Normal, '1. Term'), 'styled-typed' (Heading + typed number)."""
    doc = Document()
    doc.add_paragraph("SHORT SERVICES AGREEMENT")
    for i, (title, body) in enumerate(CLAUSES, 1):
        if numbering == "typed":
            doc.add_paragraph(f"{i}. {title}")
        elif numbering == "styled-typed":
            doc.add_heading(f"{i}. {title}", level=1)
        elif headings:
            doc.add_heading(title, level=1)
        else:
            doc.add_paragraph(title)
        doc.add_paragraph(body)
    return doc


made: list[tuple[str, Path]] = []

# ---------------------------------------------------------------- (a) numbering styles
made.append(("a1 heading styles, no numbers", save_docx(base_doc(headings=True), "a1_heading_styles.docx")))
made.append(("a2 typed '1.' numbers in Normal", save_docx(base_doc(numbering="typed"), "a2_typed_numbers_normal.docx")))
made.append(("a2b Heading style + typed number", save_docx(base_doc(numbering="styled-typed"), "a2b_heading_typed_numbers.docx")))
NUMBERING = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    f'<w:numbering xmlns:w="{W}"><w:abstractNum w:abstractNumId="0"><w:lvl w:ilvl="0"><w:start w:val="1"/><w:numFmt w:val="decimal"/>'
    '<w:lvlText w:val="%1."/><w:lvlJc w:val="left"/></w:lvl></w:abstractNum><w:num w:numId="1"><w:abstractNumId w:val="0"/></w:num></w:numbering>'
)
NUM_CT = [("/word/numbering.xml", "application/vnd.openxmlformats-officedocument.wordprocessingml.numbering+xml")]
NUM_REL = [("rIdNum1", "http://schemas.openxmlformats.org/officeDocument/2006/relationships/numbering", "numbering.xml", False)]


def add_numpr(xml: bytes) -> bytes:
    text = xml.decode("utf-8")
    for title, _ in CLAUSES:
        text = text.replace(
            f"<w:p><w:r><w:t>{title}</w:t></w:r></w:p>",
            f'<w:p><w:pPr><w:numPr><w:ilvl w:val="0"/><w:numId w:val="1"/></w:numPr></w:pPr><w:r><w:t>{title}</w:t></w:r></w:p>',
        )
    return text.encode("utf-8")


made.append(
    (
        "a3 w:numPr auto numbering, Normal style",
        rewrite(
            docx_bytes(base_doc(headings=False)),
            "a3_numpr_auto_numbering.docx",
            {"word/document.xml": add_numpr},
            add={"word/numbering.xml": NUMBERING.encode()},
            content_types=NUM_CT,
            rels=NUM_REL,
        ),
    )
)


def add_numpr_heading(xml: bytes) -> bytes:
    return re.sub(r'(<w:pStyle w:val="Heading1"/>)', r'\1<w:numPr><w:ilvl w:val="0"/><w:numId w:val="1"/></w:numPr>', xml.decode("utf-8")).encode("utf-8")


made.append(
    (
        "a3b w:numPr on Heading 1 paragraphs",
        rewrite(
            docx_bytes(base_doc(headings=True)),
            "a3b_numpr_on_headings.docx",
            {"word/document.xml": add_numpr_heading},
            add={"word/numbering.xml": NUMBERING.encode()},
            content_types=NUM_CT,
            rels=NUM_REL,
        ),
    )
)

# ---------------------------------------------------------------- (b) formatting
doc = Document()
para = doc.add_paragraph()
run = para.add_run("MASTER SUBSCRIPTION AGREEMENT")
run.bold = True
run.font.size = Pt(16)
run.font.name = "Arial"
para = doc.add_paragraph()
run = para.add_run("1. Scope of Services")
run.bold = True
run.font.size = Pt(14)  # Normal style, 14pt
doc.add_paragraph("The Provider shall supply the services described in the Order Form. ").add_run("Italic emphasis here.").italic = True
para = doc.add_paragraph()
run = para.add_run("TERMINATION")
run.underline = True  # all-caps Normal paragraph
para = doc.add_paragraph()
r1 = para.add_run("Either party may terminate on ")
r1.font.name = "Courier New"
r1.font.size = Pt(9)
r2 = para.add_run("ninety (90) days")
r2.bold = True
r2.font.size = Pt(18)
r3 = para.add_run(" notice.")
r3.font.name = "Times New Roman"
r3.font.size = Pt(11)
para = doc.add_paragraph()
run = para.add_run("Governing law")
run.font.size = Pt(14)
run.bold = True
doc.add_paragraph("This Agreement is governed by the laws of the State of New York.")
made.append(("b1 mixed fonts, caps, 14pt Normal heading", save_docx(doc, "b1_mixed_formatting.docx")))

# ---------------------------------------------------------------- (c) tables
doc = Document()
t = doc.add_table(rows=4, cols=3)
rows = [
    ("Clause", "Heading", "Text"),
    ("1", "Term", "The term is 12 months."),
    ("2", "Termination", "Either party may terminate on 30 days notice."),
    ("3", "Governing law", "Governed by the laws of Ireland."),
]
for r, vals in zip(t.rows, rows):
    for c, v in zip(r.cells, vals):
        c.text = v
made.append(("c1 tables only (no paragraphs)", save_docx(doc, "c1_tables_only.docx")))

doc = Document()
doc.add_paragraph("Schedule of charges")
t = doc.add_table(rows=2, cols=2)
t.cell(0, 0).text = "Outer A1"
t.cell(0, 1).text = "Outer A2"
t.cell(1, 0).text = "Outer B1"
inner = t.cell(1, 1).add_table(rows=2, cols=2)
inner.cell(0, 0).text = "Inner 1"
inner.cell(0, 1).text = "Inner 2: termination fee 5,000 EUR"
inner.cell(1, 0).text = "Inner 3"
inner.cell(1, 1).text = "Inner 4"
made.append(("c2 nested table (inner carries the fee)", save_docx(doc, "c2_nested_tables.docx")))

doc = Document()
doc.add_paragraph("Merged cells")
t = doc.add_table(rows=3, cols=3)
for i in range(3):
    for j in range(3):
        t.cell(i, j).text = f"R{i}C{j}"
m = t.cell(0, 0).merge(t.cell(0, 2))
m.text = "Spanning header: Payment terms"
v = t.cell(1, 0).merge(t.cell(2, 0))
v.text = "Vertical: Fees"
made.append(("c3 merged cells (horizontal + vertical)", save_docx(doc, "c3_merged_cells.docx")))

# ---------------------------------------------------------------- (d) parts outside the body
doc = base_doc()
doc.sections[0].header.paragraphs[0].text = "HEADER: Confidential - Governing law is Scotland (header only)"
doc.sections[0].footer.paragraphs[0].text = "FOOTER: Page footer text, version 7, termination fee 1,000 GBP (footer only)"
made.append(("d1 header + footer text", save_docx(doc, "d1_header_footer.docx")))

FOOTNOTES = (
    f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:footnotes xmlns:w="{W}">'
    '<w:footnote w:type="separator" w:id="-1"><w:p><w:r><w:separator/></w:r></w:p></w:footnote>'
    '<w:footnote w:type="continuationSeparator" w:id="0"><w:p><w:r><w:continuationSeparator/></w:r></w:p></w:footnote>'
    '<w:footnote w:id="1"><w:p><w:r><w:footnoteRef/></w:r><w:r><w:t xml:space="preserve"> FOOTNOTE: the notice period in clause 3 is reduced to 10 days for SMEs.</w:t></w:r></w:p></w:footnote></w:footnotes>'
)
ENDNOTES = (
    f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:endnotes xmlns:w="{W}">'
    '<w:endnote w:type="separator" w:id="-1"><w:p><w:r><w:separator/></w:r></w:p></w:endnote>'
    '<w:endnote w:type="continuationSeparator" w:id="0"><w:p><w:r><w:continuationSeparator/></w:r></w:p></w:endnote>'
    '<w:endnote w:id="1"><w:p><w:r><w:endnoteRef/></w:r><w:r><w:t xml:space="preserve"> ENDNOTE: governing law overridden to Delaware.</w:t></w:r></w:p></w:endnote></w:endnotes>'
)
COMMENTS = (
    f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:comments xmlns:w="{W}">'
    '<w:comment w:id="0" w:author="Reviewer" w:date="2026-01-01T00:00:00Z"><w:p><w:r><w:t>COMMENT: please change 30 days to 60 days.</w:t></w:r></w:p></w:comment></w:comments>'
)


def add_refs(xml: bytes) -> bytes:
    snippet = (
        '<w:p><w:r><w:t xml:space="preserve">Body paragraph with a footnote</w:t></w:r><w:r><w:rPr><w:vertAlign w:val="superscript"/></w:rPr><w:footnoteReference w:id="1"/></w:r>'
        '<w:r><w:t xml:space="preserve"> and an endnote</w:t></w:r><w:r><w:endnoteReference w:id="1"/></w:r>'
        '<w:commentRangeStart w:id="0"/><w:r><w:t xml:space="preserve"> and a commented span.</w:t></w:r><w:commentRangeEnd w:id="0"/><w:r><w:commentReference w:id="0"/></w:r></w:p>'
    )
    return body_insert(xml, snippet)


made.append(
    (
        "d2 footnote + endnote + comment (raw parts)",
        rewrite(
            docx_bytes(base_doc()),
            "d2_footnotes_endnotes_comments.docx",
            {"word/document.xml": add_refs},
            add={"word/footnotes.xml": FOOTNOTES.encode(), "word/endnotes.xml": ENDNOTES.encode(), "word/comments.xml": COMMENTS.encode()},
            content_types=[
                ("/word/footnotes.xml", "application/vnd.openxmlformats-officedocument.wordprocessingml.footnotes+xml"),
                ("/word/endnotes.xml", "application/vnd.openxmlformats-officedocument.wordprocessingml.endnotes+xml"),
                ("/word/comments.xml", "application/vnd.openxmlformats-officedocument.wordprocessingml.comments+xml"),
            ],
            rels=[
                ("rIdFn", "http://schemas.openxmlformats.org/officeDocument/2006/relationships/footnotes", "footnotes.xml", False),
                ("rIdEn", "http://schemas.openxmlformats.org/officeDocument/2006/relationships/endnotes", "endnotes.xml", False),
                ("rIdCm", "http://schemas.openxmlformats.org/officeDocument/2006/relationships/comments", "comments.xml", False),
            ],
        ),
    )
)


def add_sdt(xml: bytes) -> bytes:
    block = (
        '<w:sdt><w:sdtPr><w:alias w:val="Block control"/><w:id w:val="1"/></w:sdtPr><w:sdtContent>'
        '<w:p><w:pPr><w:pStyle w:val="Heading1"/></w:pPr><w:r><w:t>Liability (inside a block-level content control)</w:t></w:r></w:p>'
        "<w:p><w:r><w:t>BLOCK SDT: liability is capped at 100,000 USD.</w:t></w:r></w:p></w:sdtContent></w:sdt>"
    )
    inline = (
        '<w:p><w:r><w:t xml:space="preserve">Inline control: the fee is </w:t></w:r>'
        '<w:sdt><w:sdtPr><w:alias w:val="Inline control"/><w:id w:val="2"/></w:sdtPr><w:sdtContent><w:r><w:t>INLINE SDT 2,500 USD</w:t></w:r></w:sdtContent></w:sdt>'
        '<w:r><w:t xml:space="preserve"> per month.</w:t></w:r></w:p>'
    )
    return body_insert(xml, block + inline)


made.append(("d3 content controls: block-level + inline", rewrite(docx_bytes(base_doc()), "d3_content_controls.docx", {"word/document.xml": add_sdt})))


def add_fields(xml: bytes) -> bytes:
    simple_page = '<w:p><w:r><w:t xml:space="preserve">Page </w:t></w:r><w:fldSimple w:instr=" PAGE "><w:r><w:t>7</w:t></w:r></w:fldSimple><w:r><w:t xml:space="preserve"> of the agreement.</w:t></w:r></w:p>'
    complex_ref = (
        '<w:p><w:r><w:t xml:space="preserve">As set out in clause </w:t></w:r>'
        '<w:r><w:fldChar w:fldCharType="begin"/></w:r><w:r><w:instrText xml:space="preserve"> REF _Ref123 \\r \\h </w:instrText></w:r>'
        '<w:r><w:fldChar w:fldCharType="separate"/></w:r><w:r><w:t>3</w:t></w:r><w:r><w:fldChar w:fldCharType="end"/></w:r>'
        '<w:r><w:t xml:space="preserve"> (Termination), notice is 30 days.</w:t></w:r></w:p>'
    )
    stale_ref = (
        '<w:p><w:r><w:t xml:space="preserve">Stale cross-reference: see clause </w:t></w:r>'
        '<w:r><w:fldChar w:fldCharType="begin"/></w:r><w:r><w:instrText xml:space="preserve"> REF _Ref999 \\r \\h </w:instrText></w:r>'
        '<w:r><w:fldChar w:fldCharType="separate"/></w:r><w:r><w:t>Error! Reference source not found.</w:t></w:r><w:r><w:fldChar w:fldCharType="end"/></w:r></w:p>'
    )
    toc = (
        '<w:p><w:r><w:fldChar w:fldCharType="begin"/></w:r><w:r><w:instrText xml:space="preserve"> TOC \\o "1-3" \\h </w:instrText></w:r><w:r><w:fldChar w:fldCharType="separate"/></w:r></w:p>'
        '<w:p><w:pPr><w:pStyle w:val="TOC1"/></w:pPr><w:r><w:t>1 Definitions 2</w:t></w:r></w:p>'
        '<w:p><w:pPr><w:pStyle w:val="TOC1"/></w:pPr><w:r><w:t>3 Termination 4</w:t></w:r></w:p>'
        '<w:p><w:r><w:fldChar w:fldCharType="end"/></w:r></w:p>'
    )
    no_result = '<w:p><w:r><w:t xml:space="preserve">Date signed: </w:t></w:r><w:r><w:fldChar w:fldCharType="begin"/></w:r><w:r><w:instrText xml:space="preserve"> DATE </w:instrText></w:r><w:r><w:fldChar w:fldCharType="end"/></w:r><w:r><w:t>.</w:t></w:r></w:p>'
    return body_insert(body_insert(xml, toc, "start"), simple_page + complex_ref + stale_ref + no_result)


made.append(
    ("d4 fields: PAGE, REF (cached), stale REF, TOC, DATE (no cache)", rewrite(docx_bytes(base_doc()), "d4_fields.docx", {"word/document.xml": add_fields}))
)


def add_links(xml: bytes) -> bytes:
    ext = (
        '<w:p><w:r><w:t xml:space="preserve">Standard terms: </w:t></w:r><w:hyperlink r:id="rIdLink1" xmlns:r="'
        + R
        + '"><w:r><w:rPr><w:rStyle w:val="Hyperlink"/></w:rPr><w:t>commonpaper.com/standards</w:t></w:r></w:hyperlink><w:r><w:t>.</w:t></w:r></w:p>'
    )
    anchor = '<w:p><w:r><w:t xml:space="preserve">See </w:t></w:r><w:hyperlink w:anchor="_Termination"><w:r><w:t>clause 3</w:t></w:r></w:hyperlink><w:r><w:t xml:space="preserve"> above.</w:t></w:r></w:p>'
    return body_insert(xml, ext + anchor)


made.append(
    (
        "d5 hyperlinks: external + internal anchor",
        rewrite(
            docx_bytes(base_doc()),
            "d5_hyperlinks.docx",
            {"word/document.xml": add_links},
            rels=[("rIdLink1", "http://schemas.openxmlformats.org/officeDocument/2006/relationships/hyperlink", "https://commonpaper.com/standards/", True)],
        ),
    )
)

# ---------------------------------------------------------------- (e) hidden and tracked
doc = base_doc()
para = doc.add_paragraph()
para.add_run("Visible start. ")
hidden = para.add_run("HIDDEN RUN: the real notice period is 90 days. ")
hidden.font.hidden = True
para.add_run("Visible end.")
st = doc.styles.add_style("HiddenPara", 1)  # paragraph style
st.font.hidden = True
doc.add_paragraph("STYLE-HIDDEN PARAGRAPH: the liability cap is 1 USD.", style="HiddenPara")
cst = doc.styles.add_style("HiddenChar", 2)  # character style
cst.font.hidden = True
para = doc.add_paragraph("Char-style hidden: ")
para.add_run("STYLE-HIDDEN RUN: jurisdiction is Texas.", style="HiddenChar")
made.append(("e1 hidden run + style-hidden paragraph + style-hidden run", save_docx(doc, "e1_hidden_runs_and_styles.docx")))


def add_tracked(xml: bytes) -> bytes:
    ins_del = (
        '<w:p><w:r><w:t xml:space="preserve">Notice period: </w:t></w:r>'
        '<w:del w:id="1" w:author="A" w:date="2026-01-01T00:00:00Z"><w:r><w:delText>thirty (30)</w:delText></w:r></w:del>'
        '<w:ins w:id="2" w:author="A" w:date="2026-01-01T00:00:00Z"><w:r><w:t>sixty (60)</w:t></w:r></w:ins>'
        '<w:r><w:t xml:space="preserve"> days.</w:t></w:r></w:p>'
    )
    move = (
        '<w:p><w:moveFromRangeStart w:id="3" w:name="move1"/><w:moveFrom w:id="4" w:author="A" w:date="2026-01-01T00:00:00Z"><w:r><w:t>MOVED SENTENCE: Disputes go to arbitration in Geneva.</w:t></w:r></w:moveFrom><w:moveFromRangeEnd w:id="3"/></w:p>'
        "<w:p><w:r><w:t>Paragraph between the move source and destination.</w:t></w:r></w:p>"
        '<w:p><w:moveToRangeStart w:id="5" w:name="move1"/><w:moveTo w:id="6" w:author="A" w:date="2026-01-01T00:00:00Z"><w:r><w:t>MOVED SENTENCE: Disputes go to arbitration in Geneva.</w:t></w:r></w:moveTo><w:moveToRangeEnd w:id="5"/></w:p>'
    )
    fmt = (
        '<w:p><w:r><w:rPr><w:b/><w:rPrChange w:id="7" w:author="A" w:date="2026-01-01T00:00:00Z"><w:rPr/></w:rPrChange></w:rPr><w:t>Bold made by a tracked formatting change.</w:t></w:r></w:p>'
        '<w:p><w:pPr><w:rPr><w:ins w:id="8" w:author="A" w:date="2026-01-01T00:00:00Z"/></w:rPr></w:pPr><w:r><w:t>Paragraph whose mark is a tracked insertion.</w:t></w:r></w:p>'
    )
    delmark = (
        '<w:p><w:pPr><w:rPr><w:del w:id="9" w:author="A" w:date="2026-01-01T00:00:00Z"/></w:rPr></w:pPr><w:r><w:t xml:space="preserve">First half of a sentence</w:t></w:r></w:p>'
        '<w:p><w:r><w:t xml:space="preserve">second half after a deleted paragraph mark.</w:t></w:r></w:p>'
    )
    delmark_heading = (
        '<w:p><w:pPr><w:pStyle w:val="Heading1"/><w:rPr><w:del w:id="10" w:author="A" w:date="2026-01-01T00:00:00Z"/></w:rPr></w:pPr><w:r><w:t>Deleted-mark heading</w:t></w:r></w:p>'
        "<w:p><w:r><w:t>Body following the heading whose mark was deleted.</w:t></w:r></w:p>"
    )
    whole_del = (
        '<w:p><w:pPr><w:rPr><w:del w:id="11" w:author="A" w:date="2026-01-01T00:00:00Z"/></w:rPr></w:pPr><w:del w:id="12" w:author="A" w:date="2026-01-01T00:00:00Z"><w:r><w:delText>WHOLLY DELETED PARAGRAPH.</w:delText></w:r></w:del></w:p>'
        "<w:p><w:r><w:t>Paragraph after the wholly deleted one.</w:t></w:r></w:p>"
    )
    return body_insert(xml, ins_del + move + fmt + delmark + delmark_heading + whole_del)


made.append(
    (
        "e2 tracked ins/del/move/format + deleted paragraph marks",
        rewrite(docx_bytes(base_doc()), "e2_tracked_changes_raw.docx", {"word/document.xml": add_tracked}),
    )
)

# ---------------------------------------------------------------- (f) scripts and text oddities
for code, name, title, clauses in [
    (
        "hi",
        "f1_hindi.docx",
        "सेवा समझौता",
        [
            ("परिभाषाएँ", "इस समझौते में निम्नलिखित शब्दों के निम्नलिखित अर्थ होंगे।"),
            ("अवधि", "यह समझौता प्रभावी तिथि से 24 महीने तक चलेगा।"),
            ("समाप्ति", "कोई भी पक्ष 30 दिनों की लिखित सूचना देकर इस समझौते को समाप्त कर सकता है।"),
            ("शासी कानून", "यह समझौता भारत के कानूनों द्वारा शासित होगा और दिल्ली की अदालतों का विशेष क्षेत्राधिकार होगा।"),
        ],
    ),
    (
        "zh",
        "f2_chinese.docx",
        "服务协议",
        [
            ("定义", "本协议中下列词语具有以下含义。"),
            ("期限", "本协议自生效日起有效期为24个月。"),
            ("终止", "任何一方均可提前30天书面通知终止本协议。"),
            ("管辖法律", "本协议受中华人民共和国法律管辖，由上海法院专属管辖。"),
        ],
    ),
    (
        "el",
        "f4_greek.docx",
        "ΣΥΜΒΑΣΗ ΠΑΡΟΧΗΣ ΥΠΗΡΕΣΙΩΝ",
        [
            ("Ορισμοί", "Στην παρούσα σύμβαση οι ακόλουθοι όροι έχουν τις ακόλουθες έννοιες."),
            ("Διάρκεια", "Η σύμβαση διαρκεί 24 μήνες από την ημερομηνία έναρξης ισχύος."),
            ("Καταγγελία", "Κάθε μέρος μπορεί να καταγγείλει τη σύμβαση με έγγραφη προειδοποίηση 30 ημερών."),
            ("Εφαρμοστέο δίκαιο", "Η σύμβαση διέπεται από το ελληνικό δίκαιο και αρμόδια είναι τα δικαστήρια της Αθήνας."),
        ],
    ),
]:
    doc = Document()
    doc.add_paragraph(title)
    for i, (h, b) in enumerate(clauses, 1):
        doc.add_heading(f"{i}. {h}", level=1)
        doc.add_paragraph(b)
    made.append((f"f {code} script", save_docx(doc, name)))
doc = Document()
doc.add_paragraph("اتفاقية خدمات")
for i, (h, b) in enumerate(
    [
        ("التعريفات", "في هذه الاتفاقية يكون للكلمات التالية المعاني التالية."),
        ("المدة", "تبدأ هذه الاتفاقية من تاريخ السريان وتستمر لمدة 24 شهراً."),
        ("الإنهاء", "يجوز لأي طرف إنهاء هذه الاتفاقية بإشعار كتابي مدته 30 يوماً."),
        ("القانون الحاكم", "تخضع هذه الاتفاقية لقوانين دولة الإمارات العربية المتحدة وتختص محاكم دبي."),
    ],
    1,
):
    hp = doc.add_heading(f"{i}. {h}", level=1)
    hp.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    bp = doc.add_paragraph(b)
    bp.alignment = WD_ALIGN_PARAGRAPH.RIGHT


def add_bidi(xml: bytes) -> bytes:
    return xml.decode("utf-8").replace('<w:jc w:val="right"/>', '<w:bidi/><w:jc w:val="right"/>').encode("utf-8")


made.append(("f3 Arabic RTL (w:bidi)", rewrite(docx_bytes(doc), "f3_arabic_rtl.docx", {"word/document.xml": add_bidi})))

doc = Document()
doc.add_paragraph("Emoji and astral-plane agreement 📜")
doc.add_heading("1. Term 🕒", level=1)
doc.add_paragraph("The term is 12 months 🗓️. Mathematical bold 𝐓𝐞𝐫𝐦𝐢𝐧𝐚𝐭𝐢𝐨𝐧 𝟑𝟎 days. Gothic 𐌰𐌱𐌲. Flag 🇬🇧. Family 👨‍👩‍👧‍👦.")
doc.add_heading("2. Termination 🛑", level=1)
doc.add_paragraph("Either party may terminate on thirty (30) days notice 📬.")
made.append(("f5 emoji + non-BMP characters", save_docx(doc, "f5_emoji_astral.docx")))

doc = Document()
doc.add_paragraph("Invisible characters agreement")
doc.add_heading("1. Term", level=1)
doc.add_paragraph("The term is 1​2 months (zero-width space inside the number).")
doc.add_heading("2. Termi­nation", level=1)
doc.add_paragraph("Either party may ter‍min‍ate this Agreement on 3­0 days writ­ten notice. Non-breaking space and a word⁠joiner here.")
doc.add_heading("3. Governing law", level=1)
doc.add_paragraph("Governed by the laws of Eng​land ‪and Wales‬ with directional embedding marks.")
made.append(("f6 ZWJ/ZWSP/soft hyphen inside words and numbers", save_docx(doc, "f6_zero_width_soft_hyphen.docx")))

doc = Document()
doc.add_paragraph("Typographic punctuation agreement")
doc.add_heading("1. Definitions", level=1)
doc.add_paragraph(
    "“Agreement” means this document – including its schedules — and the parties’ order forms… Fees are €1,500·00 per month; the ‘Term’ is 12 months. Non‑breaking hyphen in non‑compete."
)
doc.add_heading("2. Termination", level=1)
doc.add_paragraph("Either party may terminate on thirty (30) days’ notice – see clause 1.")
made.append(("f7 typographic quotes and dashes", save_docx(doc, "f7_typographic.docx")))

random.seed(7)
words = ["termination", "notice", "party", "agreement", "days", "shall", "governing", "law", "liability", "payment", "thirty", "England"]
big = " ".join(random.choice(words) for _ in range(20000))[:100000]
assert len(big) == 100000
doc = Document()
doc.add_paragraph(big)
made.append(("f8 100,000-char single paragraph (first text = title)", save_docx(doc, "f8_100k_paragraph.docx")))
doc = Document()
doc.add_paragraph("LONG PARAGRAPH AGREEMENT")
doc.add_heading("1. Everything", level=1)
doc.add_paragraph(big)
made.append(("f8b 100,000-char paragraph under a heading", save_docx(doc, "f8b_100k_paragraph_under_heading.docx")))

doc = Document()
doc.add_paragraph("MANY SECTIONS AGREEMENT")
for i in range(1, 2501):
    doc.add_heading(f"{i}. Clause {i}", level=1)
    doc.add_paragraph(
        f"Clause {i} body: the party shall do thing number {i} within {i % 60 + 1} days."
        + (" Governing law: this Agreement is governed by the laws of Singapore." if i == 1777 else "")
    )
made.append(("f9 2,500 short numbered sections", save_docx(doc, "f9_2500_sections.docx")))

# ---------------------------------------------------------------- (g) size and type
LIMIT = 25 * 1024 * 1024
base = docx_bytes(base_doc())


def padded_docx(target: int, name: str) -> Path:
    """A valid docx padded with a stored (incompressible) media member to exactly ``target`` bytes."""
    pad_len = target
    for _ in range(8):
        buf = io.BytesIO()
        src = zipfile.ZipFile(io.BytesIO(base))
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
            for n in src.namelist():
                z.writestr(n, src.read(n))
            z.writestr(zipfile.ZipInfo("word/media/pad.bin"), os.urandom(pad_len), compress_type=zipfile.ZIP_STORED)
        data = buf.getvalue()
        if len(data) == target:
            break
        pad_len += target - len(data)
    assert len(data) == target, (len(data), target)
    path = GEN / name
    path.write_bytes(data)
    return path


made.append(("g1 DOCX exactly 25 MB (limit)", padded_docx(LIMIT, "g1_at_25mb.docx")))
made.append(("g1b DOCX 25 MB minus 1", padded_docx(LIMIT - 1, "g1b_under_25mb.docx")))
made.append(("g2 DOCX 25 MB plus 1", padded_docx(LIMIT + 1, "g2_over_25mb.docx")))

buf = io.BytesIO()
src = zipfile.ZipFile(io.BytesIO(base))
with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
    for n in src.namelist():
        z.writestr(n, src.read(n))
    z.writestr("word/media/zeros.bin", b"\0" * (300 * 1024 * 1024))
raw = buf.getvalue()
(GEN / "g3_declares_300mb.docx").write_bytes(raw)
made.append(("g3 DOCX declaring 300 MB unpacked", GEN / "g3_declares_300mb.docx"))
# g3b: the central directory under-declares the 300 MB member as 1 byte
idx = raw.rfind(b"word/media/zeros.bin")
hdr = raw.rfind(b"PK\x01\x02", 0, idx)
patched = bytearray(raw)
patched[hdr + 24 : hdr + 28] = (1).to_bytes(4, "little")
(GEN / "g3b_underdeclared_300mb.docx").write_bytes(bytes(patched))
made.append(("g3b DOCX under-declaring a 300 MB member", GEN / "g3b_underdeclared_300mb.docx"))

(GEN / "g4_macro.docm").write_bytes(base)
made.append(("g4 .docm (plain docx bytes)", GEN / "g4_macro.docm"))
made.append(
    (
        "g4b docm content type renamed .docx",
        rewrite(
            base,
            "g4b_docm_as_docx.docx",
            {
                "[Content_Types].xml": lambda b: b.replace(
                    b"application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml",
                    b"application/vnd.ms-word.document.macroEnabled.main+xml",
                )
            },
        ),
    )
)
(GEN / "g5_docx_renamed.pdf").write_bytes(base)
made.append(("g5 DOCX bytes named .pdf", GEN / "g5_docx_renamed.pdf"))


def pdf_escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def make_pdf(pages: list[str], image: bool = False) -> bytes:
    """A minimal PDF with Helvetica; each page is a content stream. ``image`` adds a 2x2 gray XObject resource."""
    objects: list[bytes] = []

    def add(obj: bytes) -> int:
        objects.append(obj)
        return len(objects)

    font = add(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>")
    img = (
        add(b"<< /Type /XObject /Subtype /Image /Width 2 /Height 2 /ColorSpace /DeviceGray /BitsPerComponent 8 /Length 4 >>stream\n\x00\xff\xff\x00\nendstream")
        if image
        else None
    )
    contents = []
    for content in pages:
        stream = content.encode("latin-1", "replace")
        contents.append(add(b"<< /Length %d >>stream\n" % len(stream) + stream + b"\nendstream"))
    pages_obj = len(objects) + len(pages) + 1
    page_ids = []
    for cid in contents:
        res = b"<< /Font << /F1 %d 0 R >>" % font + (b" /XObject << /Im1 %d 0 R >>" % img if img else b"") + b" >>"
        page_ids.append(add(b"<< /Type /Page /Parent %d 0 R /MediaBox [0 0 612 792] /Resources %s /Contents %d 0 R >>" % (pages_obj, res, cid)))
    kids = b" ".join(b"%d 0 R" % i for i in page_ids)
    assert add(b"<< /Type /Pages /Kids [%s] /Count %d >>" % (kids, len(page_ids))) == pages_obj
    catalog = add(b"<< /Type /Catalog /Pages %d 0 R >>" % pages_obj)
    out = io.BytesIO()
    out.write(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = []
    for i, obj in enumerate(objects, 1):
        offsets.append(out.tell())
        out.write(b"%d 0 obj\n" % i + obj + b"\nendobj\n")
    xref = out.tell()
    out.write(b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1))
    for off in offsets:
        out.write(b"%010d 00000 n \n" % off)
    out.write(b"trailer\n<< /Size %d /Root %d 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objects) + 1, catalog, xref))
    return out.getvalue()


def text_ops(lines: list[tuple[float, float, str, float]]) -> str:
    return "".join(f"BT /F1 {size} Tf {x} {y} Td ({pdf_escape(t)}) Tj ET\n" for x, y, t, size in lines)


left = [
    "1. TERM",
    "The term of this Agreement is",
    "twelve (12) months from the",
    "Effective Date.",
    "",
    "2. TERMINATION",
    "Either party may terminate on",
    "thirty (30) days written notice.",
]
right = [
    "3. GOVERNING LAW",
    "This Agreement is governed by",
    "the laws of the State of",
    "Delaware.",
    "",
    "4. NOTICES",
    "Notices must be in writing and",
    "sent by courier.",
]
ops = text_ops([(60, 700 - 16 * i, t, 11) for i, t in enumerate(left) if t] + [(330, 700 - 16 * i, t, 11) for i, t in enumerate(right) if t])
(GEN / "h1_multicolumn.pdf").write_bytes(make_pdf([ops]))
made.append(("h1 PDF two-column layout", GEN / "h1_multicolumn.pdf"))

pages = []
body = [
    ["1. TERM", "The term is twelve months."],
    ["2. TERMINATION", "Either party may terminate on thirty days notice."],
    ["3. GOVERNING LAW", "Governed by the laws of Delaware."],
]
for n, lines in enumerate(body, 1):
    pages.append(
        text_ops(
            [(60, 760, "ACME MASTER SERVICES AGREEMENT - CONFIDENTIAL", 9)]
            + [(60, 700 - 16 * i, t, 11) for i, t in enumerate(lines)]
            + [(60, 40, f"Page {n} of 3    Doc ref 380 INTERLOCKEN CRESCENT", 9)]
        )
    )
(GEN / "h2_running_header_footer.pdf").write_bytes(make_pdf(pages))
made.append(("h2 PDF running header + footer, 3 pages", GEN / "h2_running_header_footer.pdf"))

(GEN / "h3_image_only_page.pdf").write_bytes(
    make_pdf(
        [
            text_ops([(60, 700, "1. TERM", 11), (60, 684, "Page one has text.", 11)]),
            "q 200 0 0 200 100 400 cm /Im1 Do Q\n",
            text_ops([(60, 700, "3. GOVERNING LAW", 11), (60, 684, "Page three has text: governed by Delaware law.", 11)]),
        ],
        image=True,
    )
)
made.append(("h3 PDF with an image-only (scanned) middle page", GEN / "h3_image_only_page.pdf"))
(GEN / "h3b_image_only.pdf").write_bytes(make_pdf(["q 200 0 0 200 100 400 cm /Im1 Do Q\n"], image=True))
made.append(("h3b PDF image-only, no text at all", GEN / "h3b_image_only.pdf"))

src_pdf = make_pdf([text_ops([(60, 700, "1. GOVERNING LAW", 11), (60, 684, "Governed by the laws of Delaware.", 11)])])
w = PdfWriter(clone_from=PdfReader(io.BytesIO(src_pdf)))
w.encrypt("secret")
buf = io.BytesIO()
w.write(buf)
(GEN / "h4_encrypted.pdf").write_bytes(buf.getvalue())
made.append(("h4 PDF encrypted with a user password", GEN / "h4_encrypted.pdf"))
w = PdfWriter(clone_from=PdfReader(io.BytesIO(src_pdf)))
w.encrypt(user_password="", owner_password="owner")
buf = io.BytesIO()
w.write(buf)
(GEN / "h4b_encrypted_empty_user_pw.pdf").write_bytes(buf.getvalue())
made.append(("h4b PDF owner-password only (opens without a password)", GEN / "h4b_encrypted_empty_user_pw.pdf"))

w = PdfWriter()
for _ in range(2001):
    w.add_blank_page(612, 792)
buf = io.BytesIO()
w.write(buf)
(GEN / "h5_2001_pages.pdf").write_bytes(buf.getvalue())
made.append(("h5 PDF 2,001 blank pages", GEN / "h5_2001_pages.pdf"))
w = PdfWriter()
w.add_blank_page(612, 792)
w.add_blank_page(612, 792)
buf = io.BytesIO()
w.write(buf)
(GEN / "h6_blank_pages.pdf").write_bytes(buf.getvalue())
made.append(("h6 PDF blank pages (no text layer)", GEN / "h6_blank_pages.pdf"))
(GEN / "h6b_empty.pdf").write_bytes(b"")
made.append(("h6b 0-byte .pdf", GEN / "h6b_empty.pdf"))
(GEN / "g6_pdf_renamed.docx").write_bytes(src_pdf)
made.append(("g6 PDF bytes named .docx", GEN / "g6_pdf_renamed.docx"))


def add_linked_image(xml: bytes) -> bytes:
    drawing = (
        '<w:p><w:r><w:drawing><wp:inline xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing"><wp:extent cx="914400" cy="914400"/><wp:docPr id="1" name="Linked"/>'
        '<a:graphic xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"><a:graphicData uri="http://schemas.openxmlformats.org/drawingml/2006/picture">'
        '<pic:pic xmlns:pic="http://schemas.openxmlformats.org/drawingml/2006/picture"><pic:nvPicPr><pic:cNvPr id="1" name="x.png"/><pic:cNvPicPr/></pic:nvPicPr>'
        '<pic:blipFill><a:blip r:link="rIdImgExt" xmlns:r="' + R + '"/><a:stretch><a:fillRect/></a:stretch></pic:blipFill>'
        '<pic:spPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="914400" cy="914400"/></a:xfrm><a:prstGeom prst="rect"><a:avLst/></a:prstGeom></pic:spPr></pic:pic></a:graphicData></a:graphic></wp:inline></w:drawing></w:r>'
        "<w:r><w:t>Text after a linked picture.</w:t></w:r></w:p>"
    )
    return body_insert(xml, drawing)


made.append(
    (
        "g7 DOCX with an external (linked) image relationship",
        rewrite(
            base,
            "g7_external_image.docx",
            {"word/document.xml": add_linked_image},
            rels=[("rIdImgExt", "http://schemas.openxmlformats.org/officeDocument/2006/relationships/image", "http://127.0.0.1:9/never.png", True)],
        ),
    )
)

(GEN / "g8_empty.docx").write_bytes(b"")
made.append(("g8 0-byte .docx", GEN / "g8_empty.docx"))
(GEN / "g9_UPPER.DOCX").write_bytes(base)
made.append(("g9 .DOCX uppercase extension", GEN / "g9_UPPER.DOCX"))
(GEN / "g10_noext").write_bytes(base)
made.append(("g10 no extension", GEN / "g10_noext"))
(GEN / "g11_docx_renamed.txt").write_bytes(base)
made.append(("g11 DOCX bytes named .txt", GEN / "g11_docx_renamed.txt"))
made.append(("g12 broken document.xml (truncated)", rewrite(base, "g12_broken_document_xml.docx", {"word/document.xml": lambda b: b[: len(b) // 2]})))
made.append(
    (
        "g13 broken footnotes part referenced by rels",
        rewrite(
            base,
            "g13_broken_footnotes.docx",
            add={"word/footnotes.xml": b"<w:footnotes><w:footnote"},
            content_types=[("/word/footnotes.xml", "application/vnd.openxmlformats-officedocument.wordprocessingml.footnotes+xml")],
            rels=[("rIdFn", "http://schemas.openxmlformats.org/officeDocument/2006/relationships/footnotes", "footnotes.xml", False)],
        ),
    )
)
made.append(
    (
        "g14 degenerate tables (empty tbl, row without cells, sdt-wrapped table)",
        rewrite(
            base,
            "g14_degenerate_tables.docx",
            {
                "word/document.xml": lambda b: body_insert(
                    b,
                    "<w:tbl><w:tblPr/><w:tblGrid/></w:tbl>"
                    "<w:tbl><w:tblPr/><w:tblGrid><w:gridCol/></w:tblGrid><w:tr></w:tr><w:tr><w:tc><w:p><w:r><w:t>Only cell</w:t></w:r></w:p></w:tc></w:tr></w:tbl>"
                    '<w:sdt><w:sdtPr><w:id w:val="5"/></w:sdtPr><w:sdtContent><w:tbl><w:tblPr/><w:tblGrid><w:gridCol/></w:tblGrid><w:tr><w:tc><w:p><w:r><w:t>Table inside a block content control: fee 9,999 USD</w:t></w:r></w:p></w:tc></w:tr></w:tbl></w:sdtContent></w:sdt>'
                    "<w:p><w:r><w:t>Paragraph after degenerate tables.</w:t></w:r></w:p>",
                )
            },
        ),
    )
)
made.append(
    (
        "g15 missing style id + outlineLvl 42 / x",
        rewrite(
            base,
            "g15_missing_style.docx",
            {
                "word/document.xml": lambda b: body_insert(
                    b,
                    '<w:p><w:pPr><w:pStyle w:val="NoSuchStyle"/></w:pPr><w:r><w:t>Paragraph with a missing style.</w:t></w:r></w:p>'
                    '<w:p><w:pPr><w:outlineLvl w:val="42"/></w:pPr><w:r><w:t>Outline level forty-two.</w:t></w:r></w:p>'
                    '<w:p><w:pPr><w:outlineLvl w:val="x"/></w:pPr><w:r><w:t>Outline level x.</w:t></w:r></w:p>',
                )
            },
        ),
    )
)
made.append(
    (
        "g16 gridSpan larger than the grid + vMerge",
        rewrite(
            base,
            "g16_gridspan_overflow.docx",
            {
                "word/document.xml": lambda b: body_insert(
                    b,
                    "<w:tbl><w:tblPr/><w:tblGrid><w:gridCol/><w:gridCol/></w:tblGrid>"
                    '<w:tr><w:tc><w:tcPr><w:gridSpan w:val="5"/></w:tcPr><w:p><w:r><w:t>Spans five of two columns</w:t></w:r></w:p></w:tc></w:tr>'
                    '<w:tr><w:tc><w:tcPr><w:vMerge w:val="restart"/></w:tcPr><w:p><w:r><w:t>A</w:t></w:r></w:p></w:tc><w:tc><w:p><w:r><w:t>B</w:t></w:r></w:p></w:tc></w:tr>'
                    "<w:tr><w:tc><w:tcPr><w:vMerge/></w:tcPr><w:p/></w:tc><w:tc><w:p><w:r><w:t>C</w:t></w:r></w:p></w:tc></w:tr></w:tbl>",
                )
            },
        ),
    )
)
# a deleted table row and a table with a deleted cell paragraph mark
made.append(
    (
        "g17 deleted table row (w:trPr/w:del)",
        rewrite(
            base,
            "g17_deleted_row.docx",
            {
                "word/document.xml": lambda b: body_insert(
                    b,
                    "<w:tbl><w:tblPr/><w:tblGrid><w:gridCol/></w:tblGrid>"
                    "<w:tr><w:tc><w:p><w:r><w:t>Row kept: fee 100</w:t></w:r></w:p></w:tc></w:tr>"
                    '<w:tr><w:trPr><w:del w:id="20" w:author="A" w:date="2026-01-01T00:00:00Z"/></w:trPr><w:tc><w:p><w:r><w:t>Row deleted: fee 999</w:t></w:r></w:p></w:tc></w:tr>'
                    '<w:tr><w:trPr><w:ins w:id="21" w:author="A" w:date="2026-01-01T00:00:00Z"/></w:trPr><w:tc><w:p><w:r><w:t>Row inserted: fee 200</w:t></w:r></w:p></w:tc></w:tr></w:tbl>',
                )
            },
        ),
    )
)

# ---------------------------------------------------------------- (i) TXT
txt = "SERVICES AGREEMENT\n\n1. Term\nThe term is twelve months.\n\n2. Termination\nEither party may terminate on 30 days notice.\n\n3. Governing law\nGoverned by the laws of Ireland.\n"
(GEN / "i1_utf8_bom.txt").write_bytes(b"\xef\xbb\xbf" + txt.encode("utf-8"))
made.append(("i1 TXT UTF-8 with BOM", GEN / "i1_utf8_bom.txt"))
(GEN / "i2_utf16.txt").write_bytes(txt.encode("utf-16"))
made.append(("i2 TXT UTF-16 LE with BOM", GEN / "i2_utf16.txt"))
(GEN / "i3_crlf.txt").write_bytes(txt.replace("\n", "\r\n").encode("utf-8"))
made.append(("i3 TXT CRLF", GEN / "i3_crlf.txt"))
latin = "SERVICES AGREEMENT\n\n1. Fees\nFees are €1,500 per month, payable to Société Générale; the «Term» is 12 months.\n\n2. Termination\n30 days’ notice.\n"
(GEN / "i4_latin1.txt").write_bytes(latin.encode("cp1252"))
made.append(("i4 TXT cp1252/Latin-1 bytes", GEN / "i4_latin1.txt"))
(GEN / "i5_empty.txt").write_bytes(b"")
made.append(("i5 0-byte TXT", GEN / "i5_empty.txt"))
addr = (
    "NOTICE OF TERMINATION\n\nTo the Supplier\n380 INTERLOCKEN CRESCENT\nBROOMFIELD, CO 80021\n\n30 June 2026\n\n30 days notice is hereby given under clause 12.\n12 Baker Street is the registered office.\n2026 Annual Report follows.\n"
    "1 January 2027 is the end date.\n\n7. Governing law\nThis notice is governed by Colorado law.\n"
)
(GEN / "i6_addresses_dates.txt").write_bytes(addr.encode("utf-8"))
made.append(("i6 TXT lines starting with addresses and dates", GEN / "i6_addresses_dates.txt"))
(GEN / "i7_cr_only.txt").write_bytes(txt.replace("\n", "\r").encode("utf-8"))
made.append(("i7 TXT classic-Mac CR line endings", GEN / "i7_cr_only.txt"))
(GEN / "i8_nul_bytes.txt").write_bytes(b"1. Term\x00\nThe term\x00 is 12 months.\n")
made.append(("i8 TXT with NUL bytes", GEN / "i8_nul_bytes.txt"))
(GEN / "i9_whitespace_only.txt").write_bytes(b"   \n\n\t\n")
made.append(("i9 TXT whitespace only", GEN / "i9_whitespace_only.txt"))

(GEN / "manifest.json").write_text(json.dumps([{"label": l, "file": str(p), "bytes": p.stat().st_size} for l, p in made], indent=1), encoding="utf-8")
print(f"generated {len(made)} files")
for l, p in made:
    print(f"{p.stat().st_size:>12,}  {p.name:45s} {l}")
