"""Locating relations costs a bounded amount per statement, whatever the document's length (policy-v17).

The stress test of 2026-10-30 (performance finding 1): runs.relations promised "one regex pass over each section; a
target is found through a clause index built once", but three lookups made once per statement read the whole
document: a stated start named by a defined term compiled a pattern and scanned every section (`date_named`), a
provision's section was found by scanning every section's number (`provision`), and the relations a run records were
chosen by list membership through the dataclass's equality (`relevant`). A crafted 5 MB upload took 65 s to locate,
in the POST /api/runs request thread and again in the worker.

The invariant, held by counting rather than timing: the section reads and comparisons grow with the statements and the
sections, not with their product; and what is located is what was located before.
"""

from __future__ import annotations

from datetime import date

import pytest

from app.runs import relations as relations_module
from app.runs.relations import Relation, locate_relations, relevant

AS_OF = date(2026, 10, 30)


class Counted:
    """A section whose text and number count how often they are read."""

    reads = 0

    def __init__(self, id: str, number: str, heading: str, text: str) -> None:
        self.id, self.heading, self._number, self._text = id, heading, number, text

    @property
    def text(self) -> str:
        Counted.reads += 1
        return self._text

    @property
    def number(self) -> str:
        Counted.reads += 1
        return self._number


def _document(statements: int) -> list[Counted]:
    """``statements`` clauses, each replaced by a statement in an amendment that starts on a defined date."""
    body = [Counted(f"c{k}", f"1.{k}", f"Clause {k}", f"1.{k} The Supplier shall deliver lot {k} within thirty (30) days.") for k in range(statements)]
    amendment = [
        Counted("a0", "", "AMENDMENT NO. 1", 'This Amendment No. 1 is dated September 18, 2025 (the "Amendment Date").'),
        *(
            Counted(
                f"a{k + 1}",
                "",
                "AMENDMENT NO. 1",
                f'With effect from the "Amendment Date", Section 1.{k} of the Agreement is deleted in its entirety and replaced with the following: '
                f'"1.{k} The Supplier shall deliver lot {k} within ten (10) days."',
            )
            for k in range(statements)
        ),
    ]
    return body + amendment


def _reads(statements: int) -> tuple[int, list[Relation]]:
    Counted.reads = 0
    found = locate_relations(_document(statements), AS_OF)
    return Counted.reads, found


def test_locating_reads_each_section_a_bounded_number_of_times() -> None:
    small, found_small = _reads(40)
    large, found_large = _reads(80)
    assert len(found_small) == 40 and len(found_large) == 80
    # Twice the statements in twice the sections: about twice the reads, never four times (the quadratic lookups).
    assert large <= 2.3 * small, (small, large)


def test_what_is_located_is_unchanged() -> None:
    _, found = _reads(5)
    for k, relation in enumerate(found):
        assert relation.kind == "replaces" and relation.target == f"1.{k}"
        assert relation.replaced is not None and relation.replaced.section_id == f"c{k}"
        assert relation.replacement is not None and f"lot {k} within ten (10) days" in relation.replacement.text
        assert relation.effective == '2025-09-18, the "Amendment Date"'
        assert relation.starts == ("2025-09-18",)


def test_choosing_the_relations_a_run_records_compares_no_two_relations(monkeypatch: pytest.MonkeyPatch) -> None:
    _, found = _reads(60)
    compared = 0
    equal = Relation.__eq__

    def counting(self: Relation, other: object) -> bool:
        nonlocal compared
        compared += 1
        return equal(self, other)

    monkeypatch.setattr(Relation, "__eq__", counting)
    chosen = relevant(found, {"c59", "a60"})
    assert compared == 0
    # The relations touching the sections read first, then the rest in reading order, up to the cap.
    assert chosen[0].target == "1.59" and len(chosen) == relations_module.MAX_RELATIONS
    assert [r.target for r in chosen[1:]] == [f"1.{k}" for k in range(relations_module.MAX_RELATIONS - 1)]
