"""A definition an amendment replaces is the replaced text, wherever the amendment says so (policy-v17).

The stress test of 2026-10-30 (retrieval finding 1, the relations side): the agreement defines "Notice Period" as
ninety (90) days, and Amendment No. 1, handed to the model, changes it to thirty (30). A pass quoting the old definition
stood, with code's "the contract provides 90 calendar days … code found the day counts consistent", in every wording of
the amendment: two wordings ("amended and restated", "deleted and the following is substituted") were located only as a
replacement of Section 1 limited to the definition, a concern beside the status, and three ("amended by deleting the
definition … and replacing it", "amended to read as follows", "in lieu thereof") were not located at all.

The rule: where the statement names one definition of a clause and the clause's text holds it, the replaced text is
that definition, not the clause: a quote of it, for a question about the agreement as it stands, is text the contract
replaced (`check_replaced`), and a quote of any other definition in the clause is not. A definition code cannot find
stays a limit, as before (FAILURE-ENVELOPE: "never generalised to the clause"). The verbs read are one family.
"""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.runs.relations import assess, locate_relations, parts_of
from tests.test_relations_oracle import OracleModel

AS_OF = date(2026, 10, 30)
OLD_DEFINITION = '"Notice Period" means ninety (90) days.'
OTHER_DEFINITION = '"Fees" means the fees set out in the Order Form.'
DEFINITIONS = f"1. Definitions. {OTHER_DEFINITION}\n{OLD_DEFINITION}"
CLAUSE_8 = "Either party may terminate this Agreement for convenience by giving the other party prior written notice of not less than the Notice Period."

NEW_DEFINITION = '"\\"Notice Period\\" means thirty (30) days."'
NEW_CLAUSE = '"8. Either party may terminate on thirty (30) days\' notice."'
WORDINGS = [
    f'The definition of "Notice Period" in Section 1 of the Agreement is amended and restated in its entirety as follows: {NEW_DEFINITION}',
    f'The definition of "Notice Period" in Section 1 of the Agreement is deleted and the following is substituted: {NEW_DEFINITION}',
    'Section 1 of the Agreement is hereby amended by deleting the definition of "Notice Period" in its entirety and replacing it with '
    f"the following: {NEW_DEFINITION}",
]
# An amendment that states the definition afresh, naming no clause or naming one without a replacing verb (wave 2).
DATED = 'This Amendment No. 1 is dated September 18, 2025 (the "Amendment Date"). '
FRESH = [
    f'{DATED}With effect from the Amendment Date, "Notice Period" means thirty (30) days.',
    f'{DATED}Section 1 of the Agreement is amended so that "Notice Period" now means thirty (30) days.',
]
WHOLE = [
    f"Section 8 of the Agreement is hereby amended to read in its entirety as follows: {NEW_CLAUSE}",
    f"The Agreement is amended by deleting Section 8 in its entirety and inserting the following in lieu thereof: {NEW_CLAUSE}",
    f"Section 8 of the Agreement shall read as follows: {NEW_CLAUSE}",
]


def _sections(statement: str) -> list[SimpleNamespace]:
    return [
        SimpleNamespace(id="s1", number="1", heading="Definitions", text=DEFINITIONS),
        SimpleNamespace(id="s8", number="8", heading="Termination", text=CLAUSE_8),
        SimpleNamespace(id="am", number="", heading="AMENDMENT NO. 1", text=statement.replace('\\"', '"')),
    ]


def _span(sections: list[SimpleNamespace], section_id: str, quote: str) -> tuple[str, int, int]:
    text = next(s.text for s in sections if s.id == section_id)
    start = text.index(quote)
    return section_id, start, start + len(quote)


@pytest.mark.parametrize("statement", WORDINGS + FRESH)
def test_a_replaced_definition_is_the_replaced_text_and_no_other_definition_is(statement: str) -> None:
    sections = _sections(statement)
    (relation,) = [r for r in locate_relations(sections, AS_OF) if r.kind == "replaces"]
    assert relation.target == "1" and relation.replaced is not None and relation.scope is None
    assert relation.replaced.section_id == "s1" and relation.replaced.text.startswith('"Notice Period" means ninety (90) days')
    question = "Under the agreement as amended, on what notice may either party currently terminate for convenience?"
    quoted = [_span(sections, "s8", CLAUSE_8), _span(sections, "s1", OLD_DEFINITION)]
    notes = assess([relation], quoted, "Either party may terminate on ninety (90) days' notice.", question, parts_of(sections))
    assert [n.effect for n in notes] == ["replaced"]
    # The other definition of the same clause is not touched by it.
    other = assess([relation], [_span(sections, "s1", OTHER_DEFINITION)], "Fees are those in the Order Form.", question, parts_of(sections))
    assert other == []


@pytest.mark.parametrize("statement", WHOLE)
def test_every_wording_of_a_whole_clause_replacement_is_located(statement: str) -> None:
    sections = _sections(statement)
    (relation,) = [r for r in locate_relations(sections, AS_OF) if r.kind == "replaces"]
    assert relation.target == "8" and relation.replaced is not None and relation.replaced.section_id == "s8" and relation.scope is None


def test_control_a_definition_code_cannot_find_stays_a_limit() -> None:
    statement = 'The definition of "Applicable Margin" in Section 1 of the Agreement is amended and restated in its entirety as follows: "x".'
    (relation,) = locate_relations(_sections(statement), AS_OF)
    assert relation.scope is not None and "Applicable Margin" in relation.scope and relation.replaced is not None and relation.replaced.section_id == "s1"


def test_control_a_mention_of_reading_is_no_replacement() -> None:
    for text in (
        "Section 8 shall be read together with Schedule 2.",
        "Notices under Section 8 shall read as plain text emails.",
        "This clause is amended from time to time.",
    ):
        assert (
            locate_relations(
                [*_sections("This Amendment No. 1 changes nothing.")[:2], SimpleNamespace(id="am", number="", heading="AMENDMENT NO. 1", text=text)], AS_OF
            )
            == []
        )


@pytest.mark.parametrize("statement", WORDINGS + FRESH)
def test_through_the_run_a_pass_quoting_the_replaced_definition_is_codes_review_not_its_count(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, statement: str
) -> None:
    """The retrieval skeptic's case: the amendment handed, the model quoting §8 and the old definition, the guidance a
    60-day floor. Code's "the contract provides 90 calendar days … consistent" was false of the contract as amended."""
    from app.runs import service

    agreement = "\n\n".join(
        [
            "SERVICES AGREEMENT",
            "1. Definitions",
            f"{OTHER_DEFINITION}\n{OLD_DEFINITION}",
            "8. Termination",
            CLAUSE_8,
            "AMENDMENT NO. 1",
            statement.replace('\\"', '"'),
        ]
    )
    monkeypatch.setattr(service, "_retrieve", lambda sections, q, g, frozen: (list(sections), "lexical_match", {}))
    client.app.state.provider = OracleModel(  # type: ignore[attr-defined]
        {
            "topic": "Termination for convenience",
            "conclusion": "Either party may terminate on ninety (90) days' notice.",
            "observed": "ninety (90) days",
            "quotes": [CLAUSE_8, OLD_DEFINITION],
        }
    )
    document = client.post("/api/documents", files={"file": ("services.txt", agreement.encode("utf-8"), "text/plain")}).json()
    guidance = client.post("/api/guidance", json={"text": "We can accept termination for convenience at 60 days' notice or more."}).json()["id"]
    question = "Under the agreement as amended, on what notice may either party currently terminate for convenience?"
    started = client.post("/api/runs", json={"documentId": document["id"], "guidanceId": guidance, "question": question})
    assert started.status_code == 202, started.text
    finding = client.get(f"/api/runs/{started.json()['id']}/detail").json()["findings"][0]
    assert all(span["verified"] for span in finding["spans"])
    assert (finding["status"], finding["statusSource"], finding["decidedBy"]) == ("needs_review", "position_check", "code")
    assert "consistent" not in (finding["statusReason"] or "") and "replace" in finding["statusReason"]


def test_controls_a_term_only_the_amendment_defines_or_its_quoted_new_wording_is_no_second_statement() -> None:
    new_term = _sections(f'{DATED}"Effective Notice" means the notice given under this Amendment.')
    assert locate_relations(new_term, AS_OF) == []
    quoted = _sections(WORDINGS[0])
    assert len([r for r in locate_relations(quoted, AS_OF) if r.kind == "replaces"]) == 1
    # A body section that restates a definition is no amendment of it.
    body = _sections("This Amendment No. 1 changes nothing.")
    body[1] = SimpleNamespace(id="s8", number="8", heading="Termination", text=f'{CLAUSE_8} "Notice Period" means the period in Section 1.')
    assert locate_relations(body, AS_OF) == []
