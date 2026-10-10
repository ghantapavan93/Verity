"""Where a verified passage sits, said by the clause it is in when the document's own text names one.

A section's label is the reading's: a clause written inline ("13.2 Governing Law. This Agreement …") stays body under
the last standalone heading, so the label can name a different clause than the passage is in. The clause is read from
the stored section text (`ingest.sections.clause_label_in`), never from a fresh reading, so an old run shows what its own
text says; nothing on the record is changed. None leaves the section's label to speak.
"""

from __future__ import annotations

import threading
from collections import OrderedDict
from collections.abc import Sequence

from ..ingest.sections import clause_label_in, stated_clause_numbers
from ..models import EvidenceSpan, Section

# A document's clause numbers, by its reading: the stored sections are written once, at ingest, so the same section ids
# always give the same numbers. Reading them takes a scan of every section (about 50 ms on a 750 KB contract, over 2 s on
# a crafted 6 MB upload), and every view of a run asked for them again (Triage, 2026-10-10). Bounded, least recently used.
_CLAUSE_NUMBERS_CACHED = 256
_clause_numbers: OrderedDict[tuple[str, ...], frozenset[str]] = OrderedDict()
_clause_numbers_lock = threading.Lock()


def _document_clause_numbers(reading: tuple[str, ...], rows: Sequence[tuple[str, str, str]]) -> frozenset[str]:
    with _clause_numbers_lock:
        if reading in _clause_numbers:
            _clause_numbers.move_to_end(reading)
            return _clause_numbers[reading]
    numbers = frozenset(n for n, _, _ in rows if n) | frozenset(stated_clause_numbers([t for _, _, t in rows]))
    with _clause_numbers_lock:
        _clause_numbers[reading] = numbers
        while len(_clause_numbers) > _CLAUSE_NUMBERS_CACHED:
            _clause_numbers.popitem(last=False)
    return numbers


class ClauseLocator:
    """Clause labels for the spans of one document, its sections read once."""

    def __init__(self, sections: Sequence[Section]) -> None:
        ordered = sorted(sections, key=lambda s: s.ordinal)
        self._rows = [(s.number, s.heading, s.text) for s in ordered]
        self._index = {s.id: i for i, s in enumerate(ordered)}
        self._reading = tuple(s.id for s in ordered)

    @property
    def clause_numbers(self) -> frozenset[str]:
        """The document's clause numbers: its sections' and those its text opens a clause with, read once per reading."""
        return _document_clause_numbers(self._reading, self._rows)

    def label(self, span: EvidenceSpan) -> str | None:
        if not span.verified or span.section_id not in self._index or span.start < 0:
            return None
        return clause_label_in(self._rows, self._index[span.section_id], span.start)
