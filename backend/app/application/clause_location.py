"""Where a verified passage sits, said by the clause it is in when the document's own text names one.

A section's label is the reading's: a clause written inline ("13.2 Governing Law. This Agreement …") stays body under
the last standalone heading, so the label can name a different clause than the passage is in. The clause is read from
the stored section text (`ingest.sections.clause_label_in`), never from a fresh reading, so an old run shows what its own
text says; nothing on the record is changed. None leaves the section's label to speak.
"""

from __future__ import annotations

from collections.abc import Sequence

from ..ingest.sections import clause_label_in
from ..models import EvidenceSpan, Section


class ClauseLocator:
    """Clause labels for the spans of one document, its sections read once."""

    def __init__(self, sections: Sequence[Section]) -> None:
        ordered = sorted(sections, key=lambda s: s.ordinal)
        self._rows = [(s.number, s.heading, s.text) for s in ordered]
        self._index = {s.id: i for i, s in enumerate(ordered)}

    def label(self, span: EvidenceSpan) -> str | None:
        if not span.verified or span.section_id not in self._index or span.start < 0:
            return None
        return clause_label_in(self._rows, self._index[span.section_id], span.start)
