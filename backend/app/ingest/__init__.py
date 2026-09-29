"""Files in, numbered sections out."""

from __future__ import annotations

from dataclasses import dataclass

from ..hashing import sha256_bytes
from .readers import SUPPORTED, ReadResult, TooLargeToRead, UnsupportedFile, read
from .sections import ParsedSection, build_sections

__all__ = ["PARSER_VERSION", "SUPPORTED", "Ingested", "TooLargeToRead", "UnsupportedFile", "ingest"]

# Stored on every document so a run record says which reader produced the text its citations
# point into. Bump it whenever the reader changes what a file's text is.
#   (null) python-docx paragraph.text: lost tracked insertions and deletions, kept hidden text.
#   v2     the accepted view (readers.read_docx); PDF and TXT unchanged.
#   v3     headings from any style named *heading* or carrying an outline level (own or inherited);
#          a numbered sentence is body under its parent's label, a definition is labelled by its
#          term, trailing stops are dropped from headings.
#   v4     a lead-in is a title only when short (60 characters, 8 words); a sentence ending in a
#          colon stays body under a short label, so every word of it can be quoted and highlighted.
PARSER_VERSION = "v4"


@dataclass
class Ingested:
    name: str
    media_type: str
    sha256: str
    pages: int | None
    sections: list[ParsedSection]
    tracked_changes: int
    hidden_runs: int


def ingest(filename: str, data: bytes) -> Ingested:
    result: ReadResult = read(filename, data)
    sections = build_sections(result.blocks, title=result.title)
    if not sections or not any(s.text for s in sections):
        raise UnsupportedFile("no readable text found in the file")
    suffix = "." + filename.rsplit(".", 1)[-1].lower()
    return Ingested(
        name=filename,
        media_type=SUPPORTED[suffix],
        sha256=sha256_bytes(data),
        pages=result.pages,
        sections=sections,
        tracked_changes=result.tracked_changes,
        hidden_runs=result.hidden_runs,
    )
