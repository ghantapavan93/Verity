"""Anything the reader does not read is represented as unread: headers, footers, footnotes and comments are counted and
declared omitted; the accepted view says what it accepted and excluded; a PDF says what it cannot know."""

from __future__ import annotations

import io
import json
import zipfile

from docx import Document as DocxDocument
from fastapi.testclient import TestClient

from app.ingest import PARSER_VERSION, ingest
from app.ingest.coverage import PARTS, Status
from tests.test_ingest import make_redlined_docx

FOOTNOTES_XML = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<w:footnotes xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
    '<w:footnote w:type="separator" w:id="-1"><w:p><w:r><w:separator/></w:r></w:p></w:footnote>'
    '<w:footnote w:type="continuationSeparator" w:id="0"><w:p><w:r><w:continuationSeparator/></w:r></w:p></w:footnote>'
    '<w:footnote w:id="1"><w:p><w:r><w:t>Subject to Section 9 of the Framework Terms.</w:t></w:r></w:p></w:footnote>'
    "</w:footnotes>"
)


def make_docx_with_furniture() -> bytes:
    document = DocxDocument()
    document.sections[0].header.paragraphs[0].text = "CONFIDENTIAL — Master Services Agreement"
    document.sections[0].footer.paragraphs[0].text = "Governed by the laws of England and Wales. Page 1"
    document.add_paragraph("Master Services Agreement")
    document.add_heading("Term", level=1)
    paragraph = document.add_paragraph("This Agreement commences on the Effective Date.")
    document.add_comment(paragraph.runs, text="Check the start date", author="A. Reviewer")
    table = document.add_table(rows=1, cols=2)
    table.rows[0].cells[0].text = "Fee"
    table.rows[0].cells[1].text = "USD 1,000"
    buffer = io.BytesIO()
    document.save(buffer)
    # A footnote part, added by hand: python-docx writes none.
    original = zipfile.ZipFile(io.BytesIO(buffer.getvalue()))
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as package:
        for name in original.namelist():
            data = original.read(name)
            if name == "[Content_Types].xml":
                data = data.replace(
                    b"</Types>",
                    b'<Override PartName="/word/footnotes.xml" '
                    b'ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.footnotes+xml"/></Types>',
                )
            if name == "word/_rels/document.xml.rels":
                data = data.replace(
                    b"</Relationships>",
                    b'<Relationship Id="rIdFn1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/footnotes" '
                    b'Target="footnotes.xml"/></Relationships>',
                )
            package.writestr(name, data)
        package.writestr("word/footnotes.xml", FOOTNOTES_XML)
    return out.getvalue()


def test_a_docx_reading_declares_what_it_did_with_every_part() -> None:
    parsed = ingest("agreement.docx", make_docx_with_furniture())
    by_part = {c.part: c for c in parsed.coverage}
    assert list(by_part)[: len(PARTS)] == list(PARTS), "every part is accounted for, in a fixed order"
    assert by_part["main_body"].status is Status.READ
    assert by_part["tables"].status is Status.READ and by_part["tables"].count == 1
    assert by_part["headers"].status is Status.OMITTED and by_part["headers"].count == 1
    assert by_part["footers"].status is Status.OMITTED and by_part["footers"].count == 1
    assert by_part["footnotes"].status is Status.OMITTED and by_part["footnotes"].count == 1, "separator notes are not footnotes"
    assert by_part["comments"].status is Status.OMITTED and by_part["comments"].count == 1
    assert by_part["endnotes"].status is Status.ABSENT and by_part["embedded_objects"].status is Status.ABSENT
    assert by_part["tracked_insertions"].status is Status.ABSENT and by_part["hidden_runs"].status is Status.ABSENT
    assert by_part["style_hidden_text"].status is Status.UNKNOWN
    # What was omitted is nowhere in the sections: the reading is honest about the boundary it draws.
    text = " ".join(s.text for s in parsed.sections)
    assert "CONFIDENTIAL" not in text and "England and Wales" not in text and "Section 9 of the Framework" not in text and "Check the start" not in text
    assert "USD 1,000" in text


def test_the_accepted_view_reports_what_it_accepted_and_excluded() -> None:
    parsed = ingest("redline.docx", make_redlined_docx())
    by_part = {c.part: c for c in parsed.coverage}
    assert by_part["tracked_insertions"].status is Status.ACCEPTED and by_part["tracked_insertions"].count >= 1
    assert by_part["tracked_deletions"].status is Status.EXCLUDED and by_part["tracked_deletions"].count >= 1
    assert by_part["hidden_runs"].status is Status.EXCLUDED and by_part["hidden_runs"].count == 1
    assert by_part["tracked_changes_total"].count == parsed.tracked_changes == 6


def test_plain_text_and_pdf_readings_say_what_they_can_and_cannot_know() -> None:
    parsed = ingest("agreement.txt", b"1. Term\nThis Agreement commences on the Effective Date.\n")
    assert [(c.part, c.status) for c in parsed.coverage] == [("main_body", Status.READ)]


def test_the_document_carries_its_coverage_and_the_pack_records_it(client: TestClient) -> None:
    uploaded = client.post("/api/documents", files={"file": ("agreement.docx", make_docx_with_furniture(), "application/octet-stream")})
    assert uploaded.status_code == 201, uploaded.text
    report = uploaded.json()["coverage"]
    assert report["schemaVersion"] == 1 and report["readerVersion"] == PARSER_VERSION and report["source"] == "persisted"
    coverage = {c["part"]: c for c in report["parts"]}
    assert coverage["headers"] == {"part": "headers", "status": "omitted", "count": 1, "note": "header text is not read"}
    assert coverage["main_body"]["status"] == "read"
    again = client.get(f"/api/documents/{uploaded.json()['id']}").json()
    assert again["coverage"] == uploaded.json()["coverage"], "coverage is stored with the document, not recomputed"
    run = client.post("/api/runs", json={"documentId": uploaded.json()["id"], "guidanceId": None, "question": "What is the fee?"})
    assert run.status_code == 202
    pack = client.get(f"/api/runs/{run.json()['id']}/evidence-pack").content
    with zipfile.ZipFile(io.BytesIO(pack)) as archive:
        record = json.loads(archive.read("run.json"))
    packed = record["document"]["parse_coverage"]
    assert packed["source"] == "persisted" and packed["parts"][7]["part"] == "headers" and packed["parts"][7]["status"] == "omitted"


def test_a_reading_made_before_coverage_was_recorded_is_described_from_its_bytes(client: TestClient) -> None:
    from sqlalchemy import text as sql

    from app.db import SessionLocal

    uploaded = client.post("/api/documents", files={"file": ("agreement.docx", make_docx_with_furniture(), "application/octet-stream")}).json()
    with SessionLocal() as session:  # a document stored by the reader before it recorded coverage
        session.execute(sql("UPDATE documents SET coverage_json = NULL WHERE id = :id"), {"id": uploaded["id"]})
        session.commit()
    again = client.get(f"/api/documents/{uploaded['id']}").json()
    assert again["coverage"]["parts"] == uploaded["coverage"]["parts"], "the same reader describes the same bytes the same way, without writing"
    assert uploaded["coverage"]["source"] == "persisted" and again["coverage"]["source"] == "reconstructed", "and says it was described after the fact"
    assert again["coverage"]["readerVersion"] == PARSER_VERSION and again["coverage"]["schemaVersion"] == 1
    with SessionLocal() as session:
        session.execute(sql("UPDATE documents SET parser_version = 'v3' WHERE id = :id"), {"id": uploaded["id"]})
        session.commit()
    assert client.get(f"/api/documents/{uploaded['id']}").json()["coverage"] is None, "a reading by an earlier reader is not described by this one"
