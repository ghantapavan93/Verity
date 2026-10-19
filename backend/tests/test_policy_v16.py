"""Quoting the replacement is not following it (policy-v16, the owner's decision on the amendment challenge, 2026-10-17).

An answer to a question about the agreement as it stands that quotes the replacement but states only values the replaced
wording states (runs.relations' old_value) was a concern beside the model's pass from policy-v11 to v15; on the live
amendment challenge that left "ninety (90) days", the replaced value, standing as a pass once v15 removed its false
reason. `status.check_old_value` now lowers such a pass to needs review set by code. The review of v16 found what the
first version got wrong, held here: a clause number is not a value of either wording, and a status code computed on the
quoted replacement stays. What it does not change, also held here: code does not read prose, so an answer naming a
removed value ("the amendment removed the 12-month minimum") is lowered, here by the value check, as under v15.
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

from tests.test_relations_oracle import OracleModel


def _document(old: str, new: str) -> bytes:
    return "\n\n".join(
        [
            "SUPPLY AGREEMENT",
            "1. TERM",
            "1.1 This Agreement runs for three (3) years from 1 March 2025.",
            f"1.2 {old}",
            "AMENDMENT NO. 1",
            'This Amendment No. 1 is dated September 18, 2025 (the "Amendment Date").',
            f'1. With effect from the Amendment Date, clause 1.2 of the Agreement is deleted in its entirety and replaced with the following: "{new}"',
        ]
    ).encode("utf-8")


def _ask(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, document: bytes, question: str, finding: dict[str, Any], guidance: str | None = None
) -> dict[str, Any]:
    from app.runs import service

    monkeypatch.setattr(service, "_retrieve", lambda sections, q, g, frozen: (list(sections), "lexical_match", {}))
    client.app.state.provider = OracleModel(finding)  # type: ignore[attr-defined]
    document_id = client.post("/api/documents", files={"file": ("supply.txt", document, "text/plain")}).json()["id"]
    guidance_id = client.post("/api/guidance", json={"text": guidance}).json()["id"] if guidance else None
    started = client.post("/api/runs", json={"documentId": document_id, "guidanceId": guidance_id, "question": question})
    assert started.status_code == 202, started.text
    recorded: dict[str, Any] = client.get(f"/api/runs/{started.json()['id']}/detail").json()["findings"][0]
    return recorded


def test_a_clause_number_is_not_a_value_of_either_wording(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """Review of policy-v16: "1.2" opened the replaced clause and not the quoted replacement, and the answer's "clause 1.2"
    was read as a value only the replaced wording states, so a correct answer was lowered with a false sentence."""
    old = "Either party may terminate this Agreement on ninety (90) days' written notice."
    new = "Either party may terminate this Agreement on ninety (90) days' written notice delivered by courier."
    finding = _ask(
        client,
        monkeypatch,
        _document(old, new),
        "How much notice must a party give to terminate?",
        {
            "topic": "Termination notice",
            "conclusion": "Under clause 1.2 as amended, a party must give 90 days' written notice, delivered by courier.",
            "quotes": [new],
        },
    )
    assert [note["effect"] for note in finding["relations"]] == ["context"]
    assert (finding["status"], finding["statusSource"]) == ("pass", "model_hint")


def test_a_status_code_computed_on_the_quoted_replacement_stays(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """Review of policy-v16: the replacement's sixty days fall short of the guidance's ninety, which code computes on the text
    in force. The answer gives the replaced 120 days: the old_value sentence is a concern beside code's shortfall, never
    in its place."""
    new = "1.2 Customer must give sixty (60) days' written notice of non-renewal."
    finding = _ask(
        client,
        monkeypatch,
        _document("Customer must give one hundred twenty (120) days' written notice of non-renewal.", new),
        "How much notice of non-renewal must the Customer give?",
        {"topic": "Non-renewal notice", "conclusion": "Customer must give 120 days' written notice of non-renewal.", "quotes": [new]},
        guidance="Notice of non-renewal must be at least ninety (90) days.",
    )
    (note,) = finding["relations"]
    assert note["effect"] == "old_value"
    assert (finding["status"], finding["statusSource"]) == ("needs_review", "computed_days")
    assert finding["statusReason"] != note["sentence"] and f"code: {note['sentence']}" in finding["concerns"]


def test_an_answer_naming_a_removed_value_keeps_the_value_checks_reason(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """Code does not read prose: "the amendment removed the 12-month minimum" states the replaced wording's twelve months
    and nothing only the replacement states. The value check lowered this right answer already (no verified quote states
    12), as under v15; the old_value sentence, true of what the answer states, stands beside it as a concern."""
    new = "1.2 Customer may terminate this Agreement on thirty (30) days' written notice."
    finding = _ask(
        client,
        monkeypatch,
        _document("Customer may terminate this Agreement on thirty (30) days' written notice given after the first twelve (12) months.", new),
        "Can the Customer terminate at any time now?",
        {"topic": "Termination", "conclusion": "Yes, on 30 days' written notice; the amendment removed the 12-month minimum.", "quotes": [new]},
    )
    (note,) = finding["relations"]
    assert note["effect"] == "old_value" and "states a value only the replaced wording states" in note["sentence"]
    assert (finding["status"], finding["statusSource"]) == ("needs_review", "position_check")
    assert "does not establish 12" in finding["statusReason"] and f"code: {note['sentence']}" in finding["concerns"]


def test_a_section_pointer_in_either_wording_or_the_answer_is_no_value(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """Second review of policy-v16: the replaced wording pointed at another clause and the replacement did not, and the
    answer's "Sections 7.2 and 7.3" read 7.3 as a value only the replaced wording states (here clauses 1.2 and 1.1). Pointers are names in both wordings and
    in the answer; a plural reads its list, as v14 does."""
    old = "Either party may terminate this Agreement on ninety (90) days' notice under clause 1.1."
    new = "Either party may terminate this Agreement on ninety (90) days' notice by courier."
    finding = _ask(
        client,
        monkeypatch,
        _document(old, new),
        "How much notice must a party give to terminate?",
        {"topic": "Termination notice", "conclusion": "Under clauses 1.2 and 1.1 as amended, 90 days' notice by courier.", "quotes": [new]},
    )
    assert [note["effect"] for note in finding["relations"]] == ["context"]
    assert (finding["status"], finding["statusSource"]) == ("pass", "model_hint")


def test_a_wording_that_opens_with_a_quantity_keeps_it() -> None:
    """Second review of policy-v16: a clause 5 whose wording opens "5 Business Days' notice" lost its 5 with the clause
    number. Only a number that is no quantity is the clause's name."""
    from app.runs.relations import _without_number

    assert _without_number("1.2 Either party may terminate.", "1.2") == " Either party may terminate."
    assert _without_number("5 Business Days' notice is required.", "5") == "5 Business Days' notice is required."


def test_a_lowered_pass_keeps_what_its_reason_said() -> None:
    """Second review of policy-v16: a pass that said its sentence points at a section the model was not handed keeps
    saying so when old_value lowers it, as every other lowering does."""
    from app.runs.status import Decision, check_old_value

    lowered = check_old_value(Decision("pass", "model_hint", "the sentence points at §9, which was not handed to the model"), "S")
    assert lowered == Decision("needs_review", "position_check", "S; the sentence points at §9, which was not handed to the model")
