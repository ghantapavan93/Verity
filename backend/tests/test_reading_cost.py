"""What reading an upload may cost is bounded, whatever its bytes say about themselves (ingest/readers.py).

An 84 KB .docx of six million empty paragraphs unpacked to 35 MB, under the old 256 MB bound, and took 848 MB and 35 s
to read; a 41 KB PDF of two pages inflating to 20 MB each read for 3.2 s, so a 25 MB upload of such pages read for about
half an hour (gstack /cso trial and its checks, 2026-10-13). The bounds are now on what a file would become, counted
before it is built: a package's elements in every member, whatever its name or encoding, and its unpacked size; a PDF's
inflated drawing instructions across its pages. Each case below is refused before the costly step runs; the controls
read as before.
"""

from __future__ import annotations

import contextlib
import io
import time
import zipfile
import zlib
from collections.abc import Callable
from pathlib import Path

import pytest
from docx import Document as DocxDocument
from lxml import etree

from app.ingest import TooLargeToRead, ingest
from app.ingest import readers as readers_module
from tests.test_hostile_packages import _base, _rebuild

PAGE_TEXT = b"BT /F1 12 Tf 72 720 Td (Clause) Tj ET\n"


def _no_tree(monkeypatch: pytest.MonkeyPatch) -> None:
    """Refused before python-docx builds any part into a tree."""

    def built(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("a tree was built")

    monkeypatch.setattr(readers_module, "DocxDocument", built)


def _elements(package: bytes) -> int:
    """The elements of every member that parses as markup, counted independently of the reader."""
    total = 0
    with zipfile.ZipFile(io.BytesIO(package)) as archive:
        for name in archive.namelist():
            with contextlib.suppress(etree.XMLSyntaxError):  # media, not markup
                total += sum(1 for _ in etree.fromstring(archive.read(name)).iter())
    return total


def _in_body(markup: str) -> Callable[[str, bytes], bytes | None]:
    def mutate(name: str, data: bytes) -> bytes | None:
        return data.decode("utf-8").replace("</w:body>", markup + "</w:body>", 1).encode("utf-8") if name == "word/document.xml" else None

    return mutate


def _utf16_fan_out(name: str, data: bytes) -> bytes | None:
    if name != "word/document.xml":
        return None
    text = data.decode("utf-8").replace('encoding="UTF-8"', 'encoding="UTF-16"', 1).replace("</w:body>", "<w:p/>" * 25_000 + "</w:body>", 1)
    return text.encode("utf-16")


def _styles_fan_out(name: str, data: bytes) -> bytes | None:
    return data.decode("utf-8").replace("</w:styles>", "<w:style/>" * 25_000 + "</w:styles>", 1).encode("utf-8") if name == "word/styles.xml" else None


def _extra_member(name: str, data: bytes) -> Callable[[zipfile.ZipFile], None]:
    return lambda package: package.writestr(name, data)


def test_the_tiny_docx_of_six_million_paragraphs_is_refused_before_any_tree(monkeypatch: pytest.MonkeyPatch) -> None:
    """The original, at the real bound."""
    package = _rebuild(_in_body("<w:p/>" * 6_000_000))
    assert len(package) < 100_000, "a small upload"
    _no_tree(monkeypatch)
    started = time.perf_counter()
    with pytest.raises(TooLargeToRead, match=r"over 1,000,000 XML elements"):
        ingest("fan-out.docx", package)
    assert time.perf_counter() - started < 2, "refused within the count, not after a parse (35 s before)"


@pytest.mark.parametrize(
    ("shape", "package"),
    [
        ("paragraphs of runs of text", lambda: _rebuild(_in_body("<w:p><w:r><w:t>x</w:t></w:r></w:p>" * 6_000))),
        ("the styles part, not the document", lambda: _rebuild(_styles_fan_out)),
        ("a member of any name", lambda: _rebuild(lambda _n, _d: None, _extra_member("customXml/item9.dat", b"<x>" + b"<y/>" * 25_000 + b"</x>"))),
        ("markup in UTF-16", lambda: _rebuild(_utf16_fan_out)),
    ],
)
def test_every_shape_of_too_many_elements_is_refused_before_any_tree(shape: str, package: Callable[[], bytes], monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(readers_module, "MAX_DOCX_XML_ELEMENTS", 20_000)
    data = package()
    _no_tree(monkeypatch)
    with pytest.raises(TooLargeToRead, match=r"over 20,000 XML elements"):
        ingest(f"{shape}.docx", data)


def test_a_member_that_inflates_past_the_package_bound_is_refused_unread(monkeypatch: pytest.MonkeyPatch) -> None:
    package = _rebuild(lambda _n, _d: None, _extra_member("word/media/image1.png", b"\0" * (70 * 1024 * 1024)))
    assert len(package) < 1_000_000
    _no_tree(monkeypatch)
    with pytest.raises(TooLargeToRead, match=r"unpacks to 70 MB; the limit is 64 MB"):
        ingest("blob.docx", package)


def test_the_element_bound_is_exact(monkeypatch: pytest.MonkeyPatch) -> None:
    """At the bound a package reads; one element past it, it is refused."""
    monkeypatch.setattr(readers_module, "MAX_DOCX_XML_ELEMENTS", _elements(_base()) + 100)
    assert "Effective Date" in " ".join(section.text for section in ingest("at.docx", _rebuild(_in_body("<w:p/>" * 100))).sections)
    with pytest.raises(TooLargeToRead):
        ingest("past.docx", _rebuild(_in_body("<w:p/>" * 101)))


def test_a_member_nothing_refers_to_that_fails_its_own_checks_is_left_as_it_was() -> None:
    """Control: the count reads every member, but a member that fails its zip checks is still python-docx's to judge;
    one declared as 1 byte and referred to by nothing was accepted before the count existed, and still is (g3b)."""
    package = bytearray(_rebuild(lambda _n, _d: None, _extra_member("word/media/zeros.bin", b"\0" * 1_000_000)))
    entry = package.rfind(b"PK\x01\x02", 0, package.rfind(b"word/media/zeros.bin"))
    package[entry + 24 : entry + 28] = (1).to_bytes(4, "little")  # the central directory under-declares it
    assert "Effective Date" in " ".join(section.text for section in ingest("under-declared.docx", bytes(package)).sections)


def test_a_long_contract_reads_within_the_bounds() -> None:
    """Control: the bounds sit several times above the largest real contract (204,093 elements, 6.4 MB unpacked)."""
    document = DocxDocument()
    for number in range(1, 3001):
        document.add_paragraph(f"{number}. Obligation {number}")
        document.add_paragraph(f"The Provider shall perform obligation {number} within thirty (30) days of written notice.")
    buffer = io.BytesIO()
    document.save(buffer)
    text = " ".join(section.text for section in ingest("long.docx", buffer.getvalue()).sections)
    assert "obligation 1 within" in text and "obligation 3000 within" in text


def _inflating_pdf(pages: int, megabytes: int) -> bytes:
    """Pages whose drawing instructions inflate to `megabytes` each, every page its own stream, as an attacker's would be."""
    packed = zlib.compress(PAGE_TEXT + b" " * (megabytes * 1024 * 1024), 9)
    stream = f"<< /Length {len(packed)} /Filter /FlateDecode >>\nstream\n".encode() + packed + b"\nendstream"
    font = 3 + 2 * pages
    kids = " ".join(f"{3 + 2 * i} 0 R" for i in range(pages))
    objects = [b"<< /Type /Catalog /Pages 2 0 R >>", f"<< /Type /Pages /Kids [{kids}] /Count {pages} >>".encode()]
    for i in range(pages):
        page = f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 {font} 0 R >> >> /Contents {4 + 2 * i} 0 R >>"
        objects += [page.encode(), stream]
    objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    out = bytearray(b"%PDF-1.7\n")
    offsets = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{number} 0 obj\n".encode() + body + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode() + b"".join(f"{offset:010d} 00000 n \n".encode() for offset in offsets)
    out += f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    return bytes(out)


def test_a_small_pdf_whose_pages_inflate_past_the_content_bound_is_refused_before_their_text_is_read() -> None:
    package = _inflating_pdf(3, 7)
    assert len(package) < 100_000
    started = time.perf_counter()
    with pytest.raises(TooLargeToRead, match=r"over 16 MB of drawing instructions"):
        ingest("inflating.pdf", package)
    assert time.perf_counter() - started < 2


def test_the_pdf_content_bound_is_exact(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(readers_module, "MAX_PDF_CONTENT_BYTES", 2 * (len(PAGE_TEXT) + 1024 * 1024))
    assert ingest("two.pdf", _inflating_pdf(2, 1)).sections
    with pytest.raises(TooLargeToRead):
        ingest("three.pdf", _inflating_pdf(3, 1))


def test_a_real_pdf_reads_within_the_content_bound() -> None:
    """Control: the largest of 171 real PDFs holds 2.71 MB of drawing instructions; the bound is 16 MB."""
    fixture = Path(__file__).parent / "fixtures" / "services-agreement.pdf"
    assert ingest(fixture.name, fixture.read_bytes()).sections
