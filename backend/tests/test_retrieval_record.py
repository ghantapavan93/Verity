"""A run's record says which amendments of what it handed were left out for want of room, and which alias groups widened
its query (stress test, 2026-10-30, the retrieval team's report).

Links hand a handed section's amendments with it, at most MAX_LINKS of them: past that, an amendment of a section the
model read was not handed, and nothing on the run said so; and the alias table widened the query of a run whose
record named only the table's hash, not which concepts fired. Both are written on the finding-evidence stage as the run
finds them, so the record says what the model was not shown and why its sections were ranked as they were.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.db import SessionLocal
from app.models import RunStage
from app.retrieval.aliases import expand_query
from app.runs.links import MAX_LINKS
from app.runs.service import fired_alias_groups

CONTRACT = "\n".join(
    [
        "SERVICES AGREEMENT",
        "",
        "4. Fees",
        "",
        "Customer pays the Fees monthly in arrears.",
        "",
        "5. Late Fees",
        "",
        "Late Fees accrue at one percent a month on overdue Fees.",
        "",
        "6. Fee Review",
        "",
        "The Fees are reviewed each year by the parties.",
        "",
        *[f"{n}. Miscellaneous {n}\n\nUnrelated administrative matter number {n}.\n" for n in range(10, 30)],
        "30. Amendment No. 1",
        "",
        "Section 4 of the Agreement is hereby deleted and replaced with new text.",
        "",
        "31. Amendment No. 2",
        "",
        "Section 5 of the Agreement is hereby deleted and replaced with new text.",
        "",
        "32. Amendment No. 3",
        "",
        "Section 6 of the Agreement is hereby deleted and replaced with new text.",
    ]
)


def _finding_evidence(client: TestClient, question: str) -> str:
    document = client.post("/api/documents", files={"file": ("fees.txt", CONTRACT.encode("utf-8"), "text/plain")}).json()
    started = client.post("/api/runs", json={"documentId": document["id"], "guidanceId": None, "question": question})
    assert started.status_code == 202, started.text
    with SessionLocal() as session:
        row = session.query(RunStage).filter_by(run_id=started.json()["id"], stage="finding_evidence").one()
        return row.detail or ""


def test_an_amendment_of_a_handed_section_left_out_for_want_of_room_is_on_the_record(client: TestClient) -> None:
    detail = _finding_evidence(client, "What Fees does the customer pay?")
    assert f"and {MAX_LINKS} the contract points to from them" in detail
    assert "1 amendment of a section read was not handed for want of room: §32 Amendment No. 3 (it amends §6)" in detail, detail


def test_control_a_run_whose_amendments_all_fit_says_nothing_more() -> None:
    from app.runs.service import amendments_left_out
    from tests.test_retrieval_links import _sections

    sections = _sections()
    assert amendments_left_out(sections, handed={1, 4}, links_added=1) == []  # §4 and its amendment: nothing left


def test_the_alias_groups_that_widened_the_query_are_on_the_record(client: TestClient) -> None:
    detail = _finding_evidence(client, "Is there a non-compete covenant in this agreement?")
    assert "the query was widened by the alias groups: non-compete" in detail, detail


def test_the_groups_named_are_exactly_those_the_expansion_used() -> None:
    for query in ("Is there a non-compete?", "Is liability uncapped for gross negligence?", "What Fees are due?", ""):
        fired = fired_alias_groups(query)
        assert bool(fired) == (expand_query(query) != query), query
