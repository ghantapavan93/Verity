"""A revision check compares a bounded number of section pairs, whatever two versions it is given (stress test,
2026-10-30, abuse 1 / performance 6 / K24).

align() scored and kept every pair of sections still loose after its exact passes: memory and time grew with the
square of that number, 2 GiB and 23 s at 3,000 retitled sections in one GET, and any two documents a visitor declares
versions get there. Sections keep their order in a revision, so each loose section is compared by wording only with the
loose sections within WORDING_BAND places of its own, the pairs that cannot reach SAME_SECTION by their sizes are not
scored at all, and a pass stops at a budget of comparisons and of shingles read; the sections it did not reach are
reported as removed and added and counted as not compared. Nothing false follows from that: a quote is still searched
for in every section of the revision.
"""

from __future__ import annotations

import tracemalloc

import pytest

from app.trust import diff as diff_module
from app.trust.diff import WORDING_BAND, align
from app.trust.model import SectionText


def _version(n: int, heading: str, party: str, *, boilerplate: bool = False) -> list[SectionText]:
    def text(i: int) -> str:
        if boilerplate:  # every pair shares most of its wording: all of them reach SAME_SECTION
            return f"The {party} shall deliver the goods described in the schedule on time and in full, item {i}."
        return f"The {party} shall deliver goods number {i} on time."

    return [SectionText(i, "", f"{heading} {i:05d}", text(i)) for i in range(n)]


def _retitled(n: int, *, boilerplate: bool = False) -> tuple[list[SectionText], list[SectionText]]:
    return _version(n, "TERM", "Supplier", boilerplate=boilerplate), _version(n, "CLAUSE", "Vendor", boilerplate=boilerplate)


@pytest.mark.parametrize("boilerplate", [False, True])
def test_doubling_the_loose_sections_at_most_doubles_the_comparisons(boilerplate: bool) -> None:
    small = align(*_retitled(400, boilerplate=boilerplate))
    large = align(*_retitled(800, boilerplate=boilerplate))
    assert large.compared <= 2.1 * small.compared
    assert large.compared <= 800 * (2 * WORDING_BAND + 1)


def test_doubling_the_loose_sections_at_most_doubles_the_memory() -> None:
    def peak(n: int) -> int:
        old, new = _retitled(n, boilerplate=True)
        tracemalloc.start()
        try:
            align(old, new)
            return tracemalloc.get_traced_memory()[1]
        finally:
            tracemalloc.stop()

    assert peak(1600) <= 2.5 * peak(800)


def test_control_a_long_retitled_and_reworded_revision_still_pairs_every_section() -> None:
    old, new = _retitled(3000)
    alignment = align(old, new)
    assert len(alignment.changes.changed) == 3000 and alignment.changes.removed == () and alignment.changes.added == ()
    assert all(alignment.counterpart[s.key].text.endswith(f"number {s.ordinal} on time.") for s in old)
    assert alignment.changes.not_compared == 0


def test_a_pass_that_reaches_its_budget_says_how_many_sections_it_did_not_compare(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(diff_module, "MAX_WORDING_COMPARISONS", 100)
    old, new = _retitled(200, boilerplate=True)
    alignment = align(old, new)
    assert alignment.compared <= 100
    assert 0 < alignment.changes.not_compared <= len(alignment.changes.removed)
    assert len(alignment.changes.changed) + len(alignment.changes.removed) == 200, "every old section is accounted for"


def test_control_two_documents_of_unrelated_wording_pair_nothing_by_wording() -> None:
    old = [SectionText(i, "", f"A {i}", f"alpha bravo charlie delta {i} echo") for i in range(300)]
    new = [SectionText(i, "", f"B {i}", f"zulu yankee xray whiskey {i} victor") for i in range(300)]
    alignment = align(old, new)
    assert alignment.changes.changed == () and len(alignment.changes.removed) == 300 and alignment.changes.not_compared == 0
