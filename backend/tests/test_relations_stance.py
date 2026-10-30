"""An answer's conclusion and its stated value are each read for the replaced wording's values (policy-v17).

The stress test of 2026-10-30 (policy finding 4, the amendment hole): an answer quoted both a replaced clause and its
replacement and concluded "on 90 days' written notice", the replaced value, while its stated value (`observed`) gave the
replacement's 60 days. Since policy-v13 the stated value was the answer's stance whenever it named one of the values the
two wordings differ in, so the conclusion the reader sees was never read, and the pass policy-v16 exists to lower stood.

The rule: old_value when either the conclusion alone or the stated value alone gives a value only the replaced wording
states and none only the new wording states. Reading the two together (their union) would leave the hole open.
Controls: a conclusion that states both values ("changed 30 to 60") with the new one stated is no old value, nor is
one that states the new value, whatever is stated; policy-v13's case (both in the prose, the old one stated) still is.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.runs.relations import assess, locate_relations, parts_of
from tests.test_relations import AS_OF, COMPETING
from tests.test_relations_oracle import OracleModel
from tests.test_relations_surfaces import AGREEMENT, NEW, OLD

QUESTION = "How much notice must Supplier give before raising prices?"
OLD_ONLY = "Supplier must give 30 days' notice of a price increase."
NEW_ONLY = "Supplier must give 60 days' notice of a price increase."
BOTH = "The amendment changed Supplier's notice of a price increase from 30 to 60 days."


def _effects(conclusion: str, observed: str | None) -> list[str]:
    relations = locate_relations(COMPETING, AS_OF)
    (relation,) = relations
    assert relation.replaced is not None and relation.replacement is not None
    spans = [(p.section_id, p.start, p.end) for p in (relation.replaced, relation.replacement)]
    answer = f"{conclusion} {observed or ''}".strip()
    return [n.effect for n in assess(relations, spans, answer, QUESTION, parts_of(COMPETING), observed, conclusion=conclusion)]


@pytest.mark.parametrize("observed", [None, "30 days", "60 days", "sixty (60) days", "30 or 60 days", "upon notice"])
def test_a_conclusion_stating_only_the_replaced_value_is_an_old_value_whatever_is_stated(observed: str | None) -> None:
    assert _effects(OLD_ONLY, observed) == ["old_value"]


@pytest.mark.parametrize("observed", [None, "60 days", "sixty (60) days", "upon notice"])
@pytest.mark.parametrize("conclusion", [NEW_ONLY, BOTH])
def test_controls_a_conclusion_with_the_new_value_is_no_old_value_unless_the_stated_value_alone_is(conclusion: str, observed: str | None) -> None:
    assert _effects(conclusion, observed) == ["context"]


def test_controls_policy_v13_the_stated_value_alone_still_gives_the_old_value() -> None:
    assert _effects(BOTH, "30 days") == ["old_value"]


def test_through_the_run_the_pass_concluding_the_replaced_value_is_lowered(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """The skeptic's case end to end: both wordings quoted, the conclusion the replaced 210 to 150 days, the stated value
    the replacement's 120 to 45 days, the question about the agreement as it stands."""
    from app.runs import service

    monkeypatch.setattr(service, "_retrieve", lambda sections, q, g, frozen: (list(sections), "lexical_match", {}))
    client.app.state.provider = OracleModel(  # type: ignore[attr-defined]
        {"topic": "Renewal notice", "conclusion": "Notice of renewal is due 210 to 150 days before expiry.", "observed": "120 to 45 days", "quotes": [OLD, NEW]}
    )
    document = client.post("/api/documents", files={"file": ("distribution.txt", AGREEMENT.encode("utf-8"), "text/plain")}).json()
    started = client.post(
        "/api/runs", json={"documentId": document["id"], "guidanceId": None, "question": "As the agreement now stands, when must notice of renewal be given?"}
    )
    assert started.status_code == 202, started.text
    finding = client.get(f"/api/runs/{started.json()['id']}/detail").json()["findings"][0]
    assert (finding["status"], finding["statusSource"], finding["decidedBy"]) == ("needs_review", "position_check", "code")
    assert (
        "old_value" in {n["effect"] for n in finding["relations"]}
        and "its conclusion states a value only the replaced wording states" in finding["statusReason"]
    )
