"""Reader v16, PDF: a page is read in the order its text is laid out, and what it does not show is not read.

Found by the adversarial stress test (2026-10-30):

(1) A page set in two columns was read line by line across them: pypdf's layout mode groups all text on a baseline into
one line, and the reader then erased the gutter. "Customer may terminate this Agreement Supplier may terminate this
Agreement on thirty (30) days notice. on ninety (90) days notice." was stored, and the quote "Supplier may terminate
this Agreement on thirty (30) days notice." verified where the page gives the Supplier ninety days. The invariant: every
sentence in a reading exists on the page as a reader reads it, so no sentence is made across a gutter, whatever the
content stream's order or the columns' baselines; a table of short cells is still read a row at a time; and a page in
one column reads exactly as before.

(2) The text layer was trusted where it disagrees with the page: a TJ array's strings in stream order ("09" where the
glyphs show "90"), a ToUnicode entry naming another digit than the glyph drawn. The invariant: strings are read by
position, and a digit the text layer and the glyph disagree on is read as U+FFFD and counted.

(3) Displayed text was dropped while coverage said nothing: text in form XObjects (a page drawn wholly by them was
refused as "a scan?"), rotated text, filled form fields and free-text notes. The invariant: what the reading skipped is
reported with a count, and a page is "without a text layer" only when nothing on it draws text.

(4) Text that cannot be seen (render mode 3, white on nothing painted, a tenth of a point, off the page) was read and
verified (DECISIONS 2026-10-30, open). The invariant: it is left out and counted; invisible text laid over an image (a
scan's OCR layer) is read and counted as such.
"""

from __future__ import annotations

import io
import re
from itertools import pairwise

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from pypdf import PdfReader

from app.ingest import UnsupportedFile, ingest
from app.ingest.coverage import Status
from app.ingest.pdf_layout import page_text
from app.verify.spans import locate
from tests.support import FUZZ_SCALE

HELVETICA = b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>"


def escape(text: str) -> bytes:
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)").encode("latin-1")


def pdf(pages: list[bytes], *, xobjects: dict[str, bytes] | None = None, annotations: list[bytes] | None = None, tounicode: bytes | None = None) -> bytes:
    """A PDF of one or more pages, each a content stream in user space (0 0 612 792). /F1 is Helvetica; /F2, when
    ``tounicode`` is given, is Helvetica with that ToUnicode CMap. ``xobjects`` are form XObjects (their content, with
    /F1 in their own resources) or, named Im*, a 1x1 gray image. ``annotations`` go on the first page."""
    objects: list[bytes] = [HELVETICA]

    def add(body: bytes) -> int:
        objects.append(body)
        return len(objects)

    fonts = b"/F1 1 0 R"
    if tounicode is not None:
        cmap = add(b"<< /Length %d >>\nstream\n%s\nendstream" % (len(tounicode), tounicode))
        fonts += b" /F2 %d 0 R" % add(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding /ToUnicode %d 0 R >>" % cmap)
    named = b""
    for name, content in (xobjects or {}).items():
        if name.startswith("Im"):
            ref = add(b"<< /Type /XObject /Subtype /Image /Width 1 /Height 1 /ColorSpace /DeviceGray /BitsPerComponent 8 /Length 1 >>\nstream\n\x00\nendstream")
        else:
            ref = add(
                b"<< /Type /XObject /Subtype /Form /BBox [0 0 612 792] /Resources << /Font << /F1 1 0 R >> >> /Length %d >>\nstream\n%s\nendstream"
                % (len(content), content)
            )
        named += b"/%s %d 0 R " % (name.encode(), ref)
    pages_id = len(objects) + 2 * len(pages) + len(annotations or []) + 1
    page_ids = []
    for index, content in enumerate(pages):
        stream = add(b"<< /Length %d >>\nstream\n%s\nendstream" % (len(content), content))
        annots = b""
        if index == 0 and annotations:
            annots = b" /Annots [%s]" % b" ".join(b"%d 0 R" % add(a) for a in annotations)
        page_ids.append(
            add(
                b"<< /Type /Page /Parent %d 0 R /MediaBox [0 0 612 792] /Contents %d 0 R /Resources << /Font << %s >> /XObject << %s >> >>%s >>"
                % (pages_id, stream, fonts, named, annots)
            )
        )
    assert add(b"<< /Type /Pages /Kids [%s] /Count %d >>" % (b" ".join(b"%d 0 R" % i for i in page_ids), len(page_ids))) == pages_id
    catalog = add(b"<< /Type /Catalog /Pages %d 0 R >>" % pages_id)
    out, offsets = bytearray(b"%PDF-1.4\n"), []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += b"%d 0 obj\n%s\nendobj\n" % (number, body)
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1) + b"".join(b"%010d 00000 n \n" % o for o in offsets)
    out += b"trailer << /Size %d /Root %d 0 R >>\nstartxref\n%d\n%%%%EOF" % (len(objects) + 1, catalog, xref)
    return bytes(out)


def line(x: float, y: float, text: str, size: float = 10, font: str = "F1", setup: bytes = b"") -> bytes:
    return b"BT %s/%s %g Tf %g %g Td (%s) Tj ET\n" % (setup, font.encode(), size, x, y, escape(text))


def reading(data: bytes) -> tuple[str, dict[str, tuple[Status, int, str]]]:
    parsed = ingest("contract.pdf", data)
    text = "\n\n".join(f"{s.heading}\n{s.text}" for s in parsed.sections)
    return text, {c.part: (c.status, c.count, c.note) for c in parsed.coverage}


def sentences(text: str) -> list[str]:
    return [" ".join(s.split()) for s in re.split(r"(?<=[.])\s+", text) if s.strip()]


# ------------------------------------------------------------------------------------- (1) columns

LEFT = ["1. Termination by Customer", "Customer may terminate this Agreement", "on thirty (30) days notice."]
RIGHT = ["2. Termination by Supplier", "Supplier may terminate this Agreement", "on ninety (90) days notice."]


def two_columns(order: str, offset: float, gutter: float, left: list[str] = LEFT, right: list[str] = RIGHT, first_y: float = 700) -> bytes:
    """The stress test's page: two parallel clauses side by side, the right column ``gutter`` points right of the left's
    widest line and ``offset`` points lower, drawn column by column, row by row or in reverse."""
    width = max(len(t) for t in left) * 5.6  # Helvetica 10 pt averages under 5.6 pt a character
    right_x = 72 + width + gutter
    cells = [(72, first_y - 14 * i, t) for i, t in enumerate(left)], [(right_x, first_y - 14 * i - offset, t) for i, t in enumerate(right)]
    if order == "columns":
        drawn = [*cells[0], *cells[1]]
    elif order == "rows":
        drawn = [c for pair in zip(*cells, strict=True) for c in pair]
    else:
        drawn = [*reversed(cells[1]), *reversed(cells[0])]
    return b"".join(line(x, y, t) for x, y, t in drawn)


@settings(max_examples=80 * FUZZ_SCALE, deadline=None)
@given(st.sampled_from(["columns", "rows", "reversed"]), st.sampled_from([0, 3, 7, 14]), st.integers(min_value=10, max_value=40))
def test_no_sentence_is_made_across_a_gutter_and_the_supplier_has_ninety_days(order: str, offset: float, gutter: int) -> None:
    text, parts = reading(pdf([two_columns(order, offset, gutter)]))
    assert locate("Supplier may terminate this Agreement on thirty (30) days notice.", text) is None
    assert locate("Customer may terminate this Agreement Supplier", text) is None
    assert locate("Supplier may terminate this Agreement on ninety (90) days notice.", text) is not None
    assert locate("Customer may terminate this Agreement on thirty (30) days notice.", text) is not None
    for sentence in sentences(text):
        assert not ("Customer" in sentence and "Supplier" in sentence), sentence
    assert parts["columns"][:2] == (Status.READ, 1)


WORDS = ["the", "Supplier", "shall", "deliver", "goods", "within", "thirty", "days", "of", "each", "Order", "and", "Customer", "pays", "fees"]


@st.composite
def prose_columns(draw: st.DrawFn) -> tuple[list[str], list[str]]:
    """Two columns of random prose lines, five to eight words each; the left column's words are lower-case, the right
    column's carry a marker, so a sentence holding both is a junction."""
    rows = draw(st.integers(min_value=3, max_value=8))
    left = [" ".join(draw(st.lists(st.sampled_from(WORDS), min_size=5, max_size=8))).lower() for _ in range(rows)]
    right = [" ".join(f"R{w}" for w in draw(st.lists(st.sampled_from(WORDS), min_size=5, max_size=8))) for _ in range(rows)]
    return left, right


@settings(max_examples=80 * FUZZ_SCALE, deadline=None)
@given(prose_columns(), st.sampled_from(["columns", "rows", "reversed"]), st.sampled_from([0, 2, 7, 13]), st.integers(min_value=10, max_value=40))
def test_every_line_of_a_two_column_page_reads_within_its_column(columns: tuple[list[str], list[str]], order: str, offset: float, gutter: int) -> None:
    left, right = columns
    text, _ = reading(pdf([line(72, 760, "AGREEMENT") + two_columns(order, offset, gutter, left, right)]))
    words = text.split()
    switches = sum(1 for a, b in pairwise(words) if a.startswith("R") != b.startswith("R"))
    assert switches <= 2, f"the columns are read one after the other, not interleaved: {text}"


def by_character(x: float, y: float, text: str) -> bytes:
    """A cell drawn a character at a time, as many producers draw a table (one string per glyph, placed by Td)."""
    return b"".join(line(x + 5.6 * i, y, ch) for i, ch in enumerate(text) if ch != " ")


@pytest.mark.parametrize("draw", [line, by_character])
def test_control_a_table_of_short_cells_is_read_a_row_at_a_time(draw: object) -> None:
    rows = [("Quantity per order", "Price per kg"), ("Up to 500 kg", "EUR 4.20"), ("501 kg to 2,000 kg", "EUR 3.80"), ("Above 2,000 kg", "EUR 3.10")]
    cell = line if draw is line else by_character
    content = b"".join(cell(72, 700 - 14 * i, a) + cell(300, 700 - 14 * i, b) for i, (a, b) in enumerate(rows))
    text, parts = reading(pdf([line(72, 760, "PRICING") + content]))
    joined = "".join(text.split())  # spacing aside: each row's cells are read together, the rows in order
    assert "Upto500kgEUR4.20501kgto2,000kgEUR3.80Above2,000kgEUR3.10" in joined
    assert parts["columns"][0] is Status.PARTIAL, "side by side, read a row at a time"


def justified(rows: list[list[tuple[str, int]]], y: float = 700) -> bytes:
    """A justified paragraph as producers draw one: a TJ array a line, each word a string of its own and each space a
    space glyph widened by its own adjustment (thousandths of an em), as the justification spreads the line."""
    out = b""
    for i, words in enumerate(rows):
        items = b" ".join(b"(%s) %d ( )" % (escape(word), -stretch) for word, stretch in words)
        out += b"BT /F1 10 Tf 72 %g Td [%s] TJ ET\n" % (y - 14 * i, items)
    return out


@settings(max_examples=60 * FUZZ_SCALE, deadline=None)
@given(st.lists(st.lists(st.tuples(st.sampled_from(WORDS), st.integers(min_value=0, max_value=350)), min_size=8, max_size=14), min_size=2, max_size=12))
def test_control_a_justified_one_column_page_reads_as_pypdf_reads_it(rows: list[list[tuple[str, int]]]) -> None:
    data = pdf([line(72, 760, "1. Supply") + justified(rows)])
    page = PdfReader(io.BytesIO(data)).pages[0]
    assert page_text(page).text == page.extract_text(extraction_mode="layout")


def test_control_a_page_in_one_column_reads_as_pypdf_reads_it() -> None:
    lines = [line(72, 760 - 14 * i, f"{i}. Clause {i}. The Supplier shall deliver the goods described in Order {i}.") for i in range(1, 30)]
    page = PdfReader(io.BytesIO(pdf([b"".join(lines)]))).pages[0]
    assert page_text(page).text == page.extract_text(extraction_mode="layout")


# ------------------------------------------------------------------------------------- (2) the text layer and the glyphs


@pytest.mark.parametrize(
    "clause",
    [
        # The 9 is drawn 1.112 em back from the end of the 0, so it lands left of it: the page shows "90".
        b"BT /F1 10 Tf 72 700 Td (Supplier may terminate on ) Tj ET BT /F1 10 Tf 202 700 Td [(0) 1112 (9)] TJ ET\n" + line(212, 700, " days notice."),
        # The stress test's file: one block, the sentence going on after the 0 in the same TJ.
        b"BT /F1 10 Tf 1 0 0 1 72 700 Tm (Supplier may terminate on   ) Tj [(0) 1112 (9) -556 ( days notice.)] TJ ET\n",
    ],
)
def test_strings_drawn_out_of_stream_order_read_by_position(clause: bytes) -> None:
    text, _ = reading(pdf([line(72, 760, "AGREEMENT") + clause]))
    assert "terminate on 90 days notice." in " ".join(text.split())


NINE_AS_THREE = (
    b"/CIDInit /ProcSet findresource begin 12 dict begin begincmap 1 begincodespacerange <00> <FF> endcodespacerange "
    b"1 beginbfchar <39> <0033> endbfchar endcmap CMapName currentdict /CMap defineresource pop end end"
)


def test_a_digit_whose_text_layer_names_another_is_read_as_a_replacement_and_counted() -> None:
    clause = line(72, 700, "Supplier may terminate on ") + b"BT /F2 10 Tf 202 700 Td (90) Tj ET" + line(220, 700, " days notice.")
    text, parts = reading(pdf([line(72, 760, "AGREEMENT") + clause], tounicode=NINE_AS_THREE))
    assert "30 days" not in text and "\ufffd0" in text
    assert parts["text_layer"][:2] == (Status.PARTIAL, 1)


def test_control_an_embedded_fonts_text_layer_is_not_second_guessed() -> None:
    """An embedded subset font draws whatever its program holds at a code, so its encoding's names say nothing of the glyph:
    checking them read Chrome's "fourteen (14)" as "fourteen (1\ufffd)". Only a font drawn by glyph name is checked."""
    from pypdf.generic import DictionaryObject, NameObject

    from app.ingest.pdf_layout import _draws_by_name

    def font(subtype: str, embedded: str | None) -> DictionaryObject:
        descriptor = DictionaryObject({NameObject(embedded): NameObject("/x")}) if embedded else DictionaryObject()
        return DictionaryObject({NameObject("/Subtype"): NameObject(subtype), NameObject("/FontDescriptor"): descriptor})

    assert _draws_by_name(font("/Type1", None)) and _draws_by_name(font("/TrueType", None))
    assert not any(_draws_by_name(font(kind, key)) for kind in ("/Type1", "/TrueType") for key in ("/FontFile", "/FontFile2", "/FontFile3"))
    assert not _draws_by_name(font("/Type0", None))


# ------------------------------------------------------------------------------------- (3) what is drawn is read or counted


def test_text_in_a_form_xobject_is_read() -> None:
    clause = line(72, 650, "3. Liability. Liability is capped at the fees paid.")
    page = line(72, 760, "AGREEMENT") + line(72, 700, "2. Term. One year.") + b"q 1 0 0 1 0 0 cm /Fx1 Do Q" + line(72, 600, "4. Law. Delaware.")
    text, _ = reading(pdf([page], xobjects={"Fx1": clause}))
    assert "Liability is capped at the fees paid." in text


def test_a_page_drawn_wholly_by_form_xobjects_is_not_a_scan() -> None:
    body = line(72, 760, "SERVICES AGREEMENT") + line(72, 700, "1. Term") + line(72, 680, "The Agreement lasts one year.")
    text, parts = reading(pdf([b"/Fx1 Do"], xobjects={"Fx1": body}))
    assert "The Agreement lasts one year." in text and parts["scanned_pages"][0] is Status.ABSENT


def test_rotated_text_is_counted_and_a_page_of_it_is_not_a_scan() -> None:
    rotated = b"BT /F1 10 Tf 0 1 -1 0 300 300 Tm (The fees are set out in this schedule.) Tj ET"
    _, parts = reading(pdf([line(72, 760, "AGREEMENT") + line(72, 700, "1. Fees are due monthly.") + rotated]))
    assert parts["rotated_text"][0] is Status.OMITTED and parts["rotated_text"][1] > 20
    with pytest.raises(UnsupportedFile, match="no readable text"):
        ingest("rotated.pdf", pdf([rotated]))


def test_filled_form_fields_and_free_text_notes_are_counted() -> None:
    widget = b"<< /Type /Annot /Subtype /Widget /FT /Tx /T (term) /V (thirty-six \\(36\\) months) /Rect [200 690 400 710] >>"
    note = b"<< /Type /Annot /Subtype /FreeText /Contents (Cap amended to 3x fees - initialled) /Rect [72 600 300 620] >>"
    _, parts = reading(pdf([line(72, 760, "AGREEMENT") + line(72, 700, "4. Initial Term:")], annotations=[widget, note]))
    assert parts["annotations"][:2] == (Status.OMITTED, 2)


# ------------------------------------------------------------------------------------- (4) text that cannot be seen


@pytest.mark.parametrize(
    ("setup", "size", "x", "why"),
    [
        (b"3 Tr ", 10, 202, "render mode"),
        (b"1 g ", 10, 202, "white"),
        (b"1 1 1 rg ", 10, 202, "white"),
        (b"0 0 0 0 k ", 10, 202, "white"),
        (b"", 0.1, 202, "1 pt"),
        (b"", 10, 900, "off the page"),
    ],
)
def test_text_drawn_so_it_cannot_be_seen_is_left_out_and_counted(setup: bytes, size: float, x: float, why: str) -> None:
    clause = line(72, 700, "Supplier may terminate on ") + line(x, 700, "thirty (30) days notice. Supplier may terminate on ", size, setup=setup)
    clause += line(72, 686, "ninety (90) days notice.")
    text, parts = reading(pdf([line(72, 760, "AGREEMENT") + clause]))
    assert "thirty" not in text
    status, count, note = parts["invisible_text"]
    assert status is Status.EXCLUDED and count > 20 and why in note


def test_control_white_text_on_a_dark_box_and_coloured_text_are_read() -> None:
    box = b"q 0 0 0.5 rg 60 690 400 24 re f Q "
    page = line(72, 760, "AGREEMENT") + box + line(72, 700, "Fees are due monthly.", setup=b"1 g ") + line(72, 650, "Red ink.", setup=b"1 0 0 rg ")
    text, parts = reading(pdf([page]))
    assert "Fees are due monthly." in text and "Red ink." in text and "invisible_text" not in parts


def test_invisible_text_over_an_image_is_a_scans_ocr_layer_read_and_counted() -> None:
    image = b"q 612 0 0 792 0 0 cm /Im1 Do Q "
    ocr = line(72, 700, "Fees are due monthly.", setup=b"3 Tr ")
    text, parts = reading(pdf([image + line(72, 760, "AGREEMENT", setup=b"3 Tr ") + ocr], xobjects={"Im1": b""}))
    assert "Fees are due monthly." in text
    assert parts["image_text"][0] is Status.PARTIAL and "invisible_text" not in parts
