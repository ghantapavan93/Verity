"""retrieval-v2 (runs.links): after the ranking, the sections the top ranked ones depend on, where the contract says which.

The cases are the failure classes the retrieval study found on unfamiliar agreements (outside the repository): a defined
term whose definition shares no word with the question; an amendment that replaces a clause, read in a format that cut
it from the clause; a clause "subject to" another. Each has a control: a section the question already ranks is not added
twice, nothing is followed from the opening fallback, and the added text stays within what the ranked sections may
already carry.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from fastapi.testclient import TestClient

from app.runs.links import MAX_LINKS, because, linked, links_of
from app.runs.service import FrozenOptions, _retrieve
from tests.test_policy_v10_calendar import DisputeProvider


@dataclass
class S:
    number: str
    heading: str
    text: str
    id: str = ""


FILLER = [S(str(n), f"Miscellaneous {n}", f"This clause {n} concerns unrelated administrative matter number {n}.") for n in range(20, 34)]


def _sections() -> list[S]:
    return [
        S("1", "Definitions", '"Business Day" means any day other than a Saturday or Sunday. "Initial Term" means the first twelve months.'),
        S("4", "Fees", "Customer shall pay the Fees within thirty days of invoice."),
        S("8", "Termination", "Either party may terminate for convenience after the Initial Term, subject to Section 9 and on ten Business Days' notice."),
        S("9", "Early Termination Fee", "A party terminating under Section 8 shall pay an early termination fee of $5,000."),
        S("", "Amendment No. 1", "Section 4 of the Agreement is replaced: Customer shall pay the Fees within forty-five days of invoice."),
        *FILLER,
    ]


def test_a_clause_brings_its_definitions_the_clause_it_is_subject_to_and_its_amendments() -> None:
    sections = _sections()
    found = {(link.kind, link.index) for link in links_of(sections, 2)}  # §8
    assert ("definition", 0) in found and ("reference", 3) in found
    assert ("amendment", 4) in {(link.kind, link.index) for link in links_of(sections, 1)}  # §4, replaced by the amendment


def test_links_are_added_after_the_ranked_sections_amendments_first_and_at_most_two() -> None:
    sections = _sections()
    added = linked(sections, [1, 5, 6, 7, 8, 9], window=6000)  # §4 ranked first: its amendment comes before anything else
    assert [link.kind for link in added][:1] == ["amendment"] and added[0].index == 4 and len(added) <= MAX_LINKS
    assert because(added[0], sections) == "it amends or overrides §4, handed as §4"


def test_control_a_section_already_ranked_is_not_added_again() -> None:
    sections = _sections()
    assert all(link.index not in (2, 0, 3) for link in linked(sections, [2, 0, 3, 5, 6, 7], window=6000))


def test_control_the_added_text_stays_within_what_the_ranked_sections_may_carry() -> None:
    sections = _sections()
    sections[0] = S("1", "Definitions", '"Initial Term" means the first twelve months. ' + "x" * 5900)
    ranked = [2]  # one ranked section of ~120 characters may carry one window: a 5,900-character definition fits, two do not
    added = linked(sections, ranked, window=6000)
    assert sum(min(len(sections[i].text), 6000) for i in [*ranked, *(link.index for link in added)]) <= 6000


def test_control_nothing_is_followed_from_the_opening_fallback() -> None:
    sections = _sections()
    frozen = FrozenOptions(retrieval_k=6, retriever="bm25", aliases=True, embed_model="", window=6000, decoding={})
    chosen, mode, why = _retrieve(sections, "zzzz qqqq", None, frozen)  # type: ignore[arg-type]
    assert mode == "opening_fallback" and why == {} and chosen == sections[:6]


def test_a_run_records_why_a_linked_section_was_handed(client: TestClient) -> None:
    """The pilot's H4-Q5 clause, in an agreement long enough that the definitions are not handed by rank: the
    definition of the Closing Statement is linked from §7, and the run says why. (Guidance joins the retrieval query,
    and this guidance names the defined terms, so the question is asked without it.)"""
    from tests.test_policy_v10_calendar import CONTRACT_WITH_DEFINITION

    contract = CONTRACT_WITH_DEFINITION + "".join(f"\n{n}. Miscellaneous {n}\nUnrelated administrative matter number {n}.\n" for n in range(10, 30))
    client.app.state.provider = DisputeProvider()  # type: ignore[attr-defined]
    document = client.post("/api/documents", files={"file": ("apa.txt", contract.encode("utf-8"), "text/plain")}).json()
    question = "How long does the Seller have to object after receiving it?"  # no defined term in the question's words
    started = client.post("/api/runs", json={"documentId": document["id"], "guidanceId": None, "question": question})
    assert started.status_code == 202, started.text
    from app.db import SessionLocal
    from app.models import Run

    with SessionLocal() as session:
        run = session.get(Run, started.json()["id"])
        assert run is not None
        handed = json.loads(run.candidates_json or "[]")
    assert any(c.get("linked", "").startswith('the definition of "') for c in handed), handed
