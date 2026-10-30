"""A pass resting on text an amendment the model was not handed changes is not established (policy-v17, wave 2).

The retrieval corner of the stress test (2026-10-30): links hand at most two linked sections, so an amendment can be
located in the document and still not reach the model. A full replacement already sets the status for a question about
the agreement as it stands (`check_replaced`); a limited change ("For the second Contract Year only, clause 4.1 … is
amended and restated"), a dated question or a definition did not, and the model's pass stood on the wording before a
change it never saw.

The rule: where a verified quote lies in text a located statement changes, and the statement's section was not among
those handed to the model, a pass is needs review set by code, with the statement named (`relations.unhanded_amendment`,
`status.check_unhanded`). It reads the run's located relations, not what retrieval recorded about the links it could
not hand. Controls: the amendment handed; a question about the original agreement; a status that is not a pass.
"""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.models import Section
from app.runs.relations import locate_relations, unhanded_amendment
from app.runs.status import Decision, check_unhanded
from tests.test_relations_oracle import OracleModel

AS_OF = date(2026, 10, 30)
CLAUSE = "4.1 Customer may terminate this Agreement for convenience on thirty (30) days' written notice."
SCOPED = (
    "For the second Contract Year only, clause 4.1 of the Agreement is amended and restated to read as follows: "
    '"4.1 Customer may terminate this Agreement for convenience on ninety (90) days\' written notice."'
)
CURRENT = "As the agreement now stands, on what notice may Customer terminate for convenience?"
SECTIONS = [
    SimpleNamespace(id="s4", number="4", heading="TERMINATION", text=CLAUSE),
    SimpleNamespace(id="am", number="", heading="AMENDMENT NO. 1", text=SCOPED),
]
QUOTED = [("s4", 0, len(CLAUSE))]


def test_a_quote_of_text_an_unhanded_statement_changes_is_named() -> None:
    relations = locate_relations(SECTIONS, AS_OF)
    sentence = unhanded_amendment(relations, QUOTED, {"s4"}, CURRENT)
    assert sentence is not None and "AMENDMENT NO. 1" in sentence and "which was not handed to the model" in sentence
    lowered = check_unhanded(Decision("pass", "model_hint"), sentence)
    assert (lowered.status, lowered.source, lowered.reason) == ("needs_review", "position_check", sentence)


@pytest.mark.parametrize(
    ("handed", "question"),
    [({"s4", "am"}, CURRENT), ({"s4"}, "What notice did the agreement originally require for termination for convenience?")],
)
def test_controls_the_amendment_handed_or_a_question_about_the_original_raise_nothing(handed: set[str], question: str) -> None:
    assert unhanded_amendment(locate_relations(SECTIONS, AS_OF), QUOTED, handed, question) is None


def test_controls_only_a_pass_is_lowered() -> None:
    review = Decision("needs_review", "computed_days", "the contract provides 30 calendar days")
    assert check_unhanded(review, "the quoted clause 4.1 is changed by …") == review
    assert check_unhanded(Decision("pass", "model_hint"), None) == Decision("pass", "model_hint")


AGREEMENT = "\n\n".join(["SERVICES AGREEMENT", "4. TERMINATION", CLAUSE, "AMENDMENT NO. 1", SCOPED])


@pytest.mark.parametrize("amendment_handed", [False, True])
def test_through_the_run(client: TestClient, monkeypatch: pytest.MonkeyPatch, amendment_handed: bool) -> None:
    from app.runs import service

    def handed(sections: list[Section], question: str, guidance: str | None, frozen: object) -> tuple[list[Section], str, dict[str, str]]:
        chosen = [s for s in sections if amendment_handed or "AMENDMENT" not in (s.heading or "") + s.text[:20]]
        return chosen, "lexical_match", {}

    monkeypatch.setattr(service, "_retrieve", handed)
    client.app.state.provider = OracleModel(  # type: ignore[attr-defined]
        {
            "topic": "Termination for convenience",
            "conclusion": "Customer may terminate on 30 days' written notice.",
            "observed": "30 days",
            "quotes": [CLAUSE[4:]],
        }
    )
    document = client.post("/api/documents", files={"file": ("services.txt", AGREEMENT.encode("utf-8"), "text/plain")}).json()
    started = client.post("/api/runs", json={"documentId": document["id"], "guidanceId": None, "question": CURRENT})
    assert started.status_code == 202, started.text
    finding = client.get(f"/api/runs/{started.json()['id']}/detail").json()["findings"][0]
    assert finding["spans"][0]["verified"] is True
    if amendment_handed:  # the limited change is a concern beside the model's pass, as before
        assert finding["status"] == "pass"
    else:
        assert (finding["status"], finding["statusSource"], finding["decidedBy"]) == ("needs_review", "position_check", "code")
        assert "which was not handed to the model" in finding["statusReason"]
