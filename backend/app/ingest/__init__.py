"""Files in, numbered sections out."""

from __future__ import annotations

from dataclasses import dataclass

from ..hashing import sha256_bytes
from .coverage import PartCoverage
from .invisible import visible_text
from .readers import SUPPORTED, ReadResult, TooLargeToRead, UnsupportedFile, read
from .sections import ParsedSection, build_sections

__all__ = ["PARSER_VERSION", "SUPPORTED", "Ingested", "TooLargeToRead", "UnsupportedFile", "ingest"]

MAX_NAME = 255

# Stored on every document so a run record says which reader produced the text its citations
# point into. Bump it whenever the reader changes what a file's text is.
#   (null) python-docx paragraph.text: lost tracked insertions and deletions, kept hidden text.
#   v2     the accepted view (readers.read_docx); PDF and TXT unchanged.
#   v3     headings from any style named *heading* or carrying an outline level (own or inherited);
#          a numbered sentence is body under its parent's label, a definition is labelled by its
#          term, trailing stops are dropped from headings.
#   v4     a lead-in is a title only when short (60 characters, 8 words); a sentence ending in a
#          colon stays body under a short label, so every word of it can be quoted and highlighted.
# v5 (2026-10-01): block-level content controls and nested tables are read, UTF-16 and Windows-1252 text files are
# decoded, a wall of text is split into sections and named by its first words, a textless PDF page is counted.
# v6 (2026-10-02): text hidden through a style is left out. The reader resolves w:vanish through the run's character
# style, the paragraph's style and their basedOn chains, and treats w:specVanish as hidden; before, only a run's own
# w:vanish was honoured, so a Word "Hidden" character style carried text to the model that Word never showed.
# v7 (2026-10-08): plain text and PDF. A heading's number is one its text states: a heading without one is labelled by its
# heading alone (v6 computed one from levels, a number the document never shows: "§7 MILESTONE 1" beside the agreement's own
# clause 7), and a stated number that does not continue the clause numbering is not a heading ("15285 Minnetonka Blvd." was
# §15285, and the schedules after it §15408 onward). DOCX is read as in v6. The file's bytes must agree with its type.
# v8 (2026-10-08): plain text and PDF. A numbered line whose words open in lower case is not a heading: a wrapped
# sentence ("Section 19 of the Facility Lease, or modify …"), a figure ("3.00 to 1.00", "15 years") or a list item inside a
# clause ("3.1.14 make available for …"), which now stays body under its clause. DOCX is read as in v7.
# v9 (2026-10-08): every format. Invisible format characters (Unicode Cf: zero-width space, soft hyphen, word joiner,
# byte-order mark, tag characters, direction controls) are removed where the text is first read, and counted in the
# coverage; a file that held "\u202e09\u202c days" displayed "90 days" while everything that checks it read "09".
# v10 (2026-10-08): every format. Also removed: the default-ignorable characters that are not Cf (variation selectors,
# the combining grapheme joiner, Hangul fillers) where they sit between two ASCII letters or digits; v9 kept them, and
# "9\ufe0f0 days" displayed "90 days" while the day parser read 0. Nothing else a v9 reading holds changes.
# v11 (2026-10-09): every format. A page's running header or footer ("1 \u2013 LEASE AGREEMENT" on every page) is text
# where it stands, never a heading (sections.running_lines); a lease's rent clause had been cut at a page break into a
# section of its own. Measured: 6 of 1,310 CUAD and EDGAR texts and the audit's lease read differently; the other
# 1,321 readings compared are identical.
# v12 (2026-10-13): PDF. A line printed the same on most pages, with no page number to rise ("ACME SERVICES AGREEMENT"
# at the top of each, "CONFIDENTIAL", a company name, a document number), is page furniture: text where it stands, never
# a heading (sections.page_furniture); a header had cut a liability cap from its exception at a page break (war room
# F-04). Plain text and DOCX are read as in v11: they do not say where a page begins. Measured: 1 of 33 readable real
# PDFs reads differently (CUAD's eGain hosting agreement); 190 DOCX and 6,073 plain texts read the same.
# v13 (2026-10-14): DOCX. A heading is given a number computed from heading levels only when Word numbers it (a w:numPr
# on the paragraph or its style chain); a heading Word does not number and whose text states none is labelled by its
# heading alone, and leaves the count of the numbered headings around it untouched. An unnumbered "SCHEDULE A" after
# "9. Governing Law" was "§9.1", the governing-law clause's own number, on the card, in the memo and in the evidence pack
# (the legal evaluation's blocker B2). Plain text and PDF are read as in v12. Measured on the corpus: see DECISIONS.md.
# v14 (2026-10-14): DOCX. A heading Word numbers carries the number Word prints for it, worked out from its list's own
# counters (start values, an instance's override, deeper levels restarting; decimal, roman and letters), never a count of
# headings: v13 called a list starting at 3 "1", a restarted list "3", a Heading 2 on a list's first level "0.1".
# Where the reader cannot say exactly what Word prints (two instances of one list in use, a restart rule of its own, a
# text box, a tracked change), the heading has no number. All formats: a heading's lead-in title never ends at a
# reference word before a number ("AMENDMENT NO. 1 TO …" was "AMENDMENT NO"), and a heading line holding a sentence end
# followed by more words is a wrapped clause, read as body under a short label. Measured on the corpus: DECISIONS.md.
PARSER_VERSION = "v14"


@dataclass
class Ingested:
    name: str
    media_type: str
    sha256: str
    pages: int | None
    sections: list[ParsedSection]
    tracked_changes: int
    hidden_runs: int
    coverage: list[PartCoverage]


def base_name(filename: str) -> str:
    """The name a person gave the file, without directories or control characters: it names a stored document, a zip
    entry in the evidence pack and the CONTRACT line of the prompt, none of which may carry a path (hostile review, 2026-10-01)."""
    name = filename.replace("\\", "/").rsplit("/", 1)[-1]
    # Invisible format characters too: "Invoice-\u202efdp.exe.txt" displayed as "Invoice-exe.pdf" (2026-10-08).
    name = visible_text("".join(ch for ch in name if ch >= " " and ch != "\x7f")).strip()
    if len(name) > MAX_NAME:
        # Cut the stem, not a supported extension: "....-copy-v12.txt" at 269 characters was stored without ".txt"
        # (QA campaign, 2026-10-08). Any other ending is only part of the name and is cut as before.
        stem, dot, suffix = name.rpartition(".")
        keep = bool(dot and stem) and f".{suffix.lower()}" in SUPPORTED
        name = f"{stem[: MAX_NAME - len(suffix) - 1]}.{suffix}" if keep else name[:MAX_NAME]
    return name or "document"


def ingest(filename: str, data: bytes) -> Ingested:
    result: ReadResult = read(filename, data)
    sections = build_sections(result.blocks, title=result.title)
    if not sections or not any(s.text for s in sections):
        # A PDF whose every page has no text layer is a scan: say so, since "no readable text" left the reader to guess why.
        scanned = next((part.count for part in result.coverage if part.part == "scanned_pages"), 0)
        if result.pages and scanned >= result.pages:
            raise UnsupportedFile("the PDF has no text layer on any page (a scan?); no OCR is run, so upload a PDF with selectable text")
        raise UnsupportedFile("no readable text found in the file")
    suffix = "." + filename.rsplit(".", 1)[-1].lower()
    return Ingested(
        name=base_name(filename),
        media_type=SUPPORTED[suffix],
        sha256=sha256_bytes(data),
        pages=result.pages,
        sections=sections,
        tracked_changes=result.tracked_changes,
        hidden_runs=result.hidden_runs,
        coverage=result.coverage,
    )
