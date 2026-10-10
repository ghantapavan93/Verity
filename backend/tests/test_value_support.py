"""A pass must not state a value its evidence does not show (policy-v6).

Found by the Contract Reality Lab, 2026-10-09. A verified quote proves a passage is in the contract; it does not prove the
conclusion attributed to it. Two forms of that gap are decidable by code, and both were shown as a pass:

* a value the conclusion states that no verified quote, nor the reader's own question or guidance, states ("$10,000 a
  month" over a quote of hours, its rate unquoted; "45 days" over a quote that stops before the period). 12 of 896
  recorded passes across the owner and lab stores;
* a redaction mark the conclusion presents as the value ("set at [***]%", "the cap is [***]"), where the filed contract
  withholds the figure. 4 of 896.

Both were already disclosed beside the answer at read time; the status still said pass. Now the decision itself lowers
the pass to needs review, with the reason, when the run is decided. Recorded runs keep the status they were decided with.
"""

from __future__ import annotations

import json
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.providers.base import Generation
from app.runs.status import Decision, check_values

PASS = Decision("pass", "model_hint")
HOURS = "Service Provider will allocate a minimum of 20 hours per month, but will not exceed 40 hours per month, without prior approval."


def lowered(decision: Decision) -> bool:
    return (decision.status, decision.source) == ("needs_review", "position_check")


def test_a_pass_stating_a_value_no_quote_states_is_lowered_with_the_value_named() -> None:
    decision = check_values(PASS, "The most FirstBank can be billed in a month is $10,000.", [HOURS], "What is the most FirstBank can be billed?", None)
    assert lowered(decision)
    assert decision.reason == "the evidence shown does not establish $10,000: no verified quote or guidance states it"


def test_a_value_the_quote_states_in_another_form_keeps_the_pass() -> None:
    quote = "Provider shall give thirty (30) days' written notice."
    assert check_values(PASS, "Provider must give 30 days' written notice.", [quote], None, None) == PASS
    assert check_values(PASS, "Provider must give thirty days' written notice.", [quote], None, None) == PASS


def test_a_value_the_guidance_states_keeps_the_pass() -> None:
    # The guidance is the standard the answer is compared with: its values count as stated.
    quote = "Customer may terminate on ninety (90) days' notice."
    assert check_values(PASS, "90 days meets the 45-day minimum.", [quote], "Is the notice period acceptable?", "At least 45 days' notice.") == PASS


def test_a_value_taken_from_the_question_is_a_premise_not_evidence() -> None:
    # A question can assert what the contract does not say; an answer that repeats its figure as the contract's has
    # repeated the premise (Reality Lab: every confident wrong answer stood on a false premise). The reason says so.
    question = "When is the Buyer's $1,000,000 cash payment due?"
    quote = "Buyer shall issue 700,000 shares of Series A Preferred Stock at Closing."
    decision = check_values(PASS, "The Buyer's $1,000,000 cash payment is due at Closing.", [quote], question, None)
    assert lowered(decision)
    assert decision.reason == "$1,000,000 comes from the question, and no verified quote states it"
    # The same figure in a verified quote is evidence, whoever asked about it.
    assert check_values(PASS, "The $1,000,000 payment is due at Closing.", ["Buyer shall pay $1,000,000 at Closing."], question, None) == PASS
    # Both kinds in one answer: each named for what it is.
    both = check_values(PASS, "The $1,000,000 payment is due within 30 days.", [quote], question, None)
    assert (
        both.reason == "the evidence shown does not establish 30 days: no verified quote or guidance states it; "
        "$1,000,000 comes from the question, and no verified quote states it"
    )


def test_changing_the_quoted_amount_does_not_let_the_old_answer_stand() -> None:
    # Metamorphic: the same conclusion over a quote whose amount was changed is no longer shown by its evidence.
    answer = "The annual fee is $40,000."
    assert check_values(PASS, answer, ["The annual fee is $40,000, payable in advance."], None, None) == PASS
    assert lowered(check_values(PASS, answer, ["The annual fee is $45,000, payable in advance."], None, None))


def test_a_redaction_mark_given_as_the_value_is_lowered() -> None:
    quote = "Sublicense Revenue Payments means the payments of [***]% of Sublicense Revenue."
    decision = check_values(PASS, "The Licensee pays [***]% of Sublicense Revenue to the Assignor.", [quote], None, None)
    assert lowered(decision)
    assert (
        decision.reason
        == "the answer gives [***], a redaction mark, as its value: this copy of the contract withholds the figure, so the evidence cannot establish it"
    )
    assert lowered(check_values(PASS, "The cap is the amounts paid in the [*] period before the claim.", ["AMOUNTS PAID IN THE [*] PERIOD"], None, None))


def test_an_answer_that_says_the_figure_is_redacted_keeps_the_pass() -> None:
    quote = "Royalty Percentage: [***]"
    for answer in (
        "The royalty percentage is redacted ([***]) in this copy, so it cannot be determined from the document.",
        "The percentage is not disclosed: Exhibit A shows [***] where it would be.",
        "The figure was omitted as confidential ([***]).",
    ):
        assert check_values(PASS, answer, [quote], None, None) == PASS, answer


def test_an_answer_with_no_value_and_no_redaction_keeps_the_pass() -> None:
    quote = "FirstBank may terminate this Agreement, without cause, at any time."
    assert check_values(PASS, "FirstBank may terminate without cause at any time.", [quote], None, None) == PASS


@pytest.mark.parametrize(("status", "source"), [("needs_review", "model_hint"), ("missing", "model_hint"), ("unresolved", "no_evidence")])
def test_only_a_pass_is_lowered(status: str, source: str) -> None:
    other = Decision(status, source)  # type: ignore[arg-type]
    assert check_values(other, "The fee is $10,000 and the period is [***].", [HOURS], None, None) == other


def test_a_pass_without_verified_quotes_is_not_this_checks_to_decide() -> None:
    # A finding with no verified quote is unresolved before this check; nothing here may turn absence into a value.
    assert check_values(PASS, "The fee is $10,000.", [], None, None) == PASS


def test_through_the_run_the_finding_is_decided_needs_review_and_says_why(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    contract = (
        "PROFESSIONAL SERVICES AGREEMENT\n\n"
        "1. Services\nService Provider will allocate a minimum of 20 hours per month, but will not exceed 40 hours per month, without prior approval.\n\n"
        "2. Fees\nFees are invoiced monthly.\n"
    )

    def answer(system: str, user: str, schema: dict[str, object]) -> Generation:
        label = next(line.split("]")[0][1:] for line in user.splitlines() if line.startswith("[sec_") and "Services" in line)
        payload: dict[str, Any] = {
            "findings": [
                {
                    "topic": "Monthly ceiling",
                    "conclusion": "The most FirstBank can be billed in a month without prior approval is $10,000.",
                    "status_hint": "pass",
                    "evidence": [{"section_id": label, "quote": HOURS}],
                    "guidance_reference": None,
                    "observed": None,
                    "required": None,
                    "suggested_position": None,
                }
            ],
            "insufficient_evidence": False,
            "note": None,
        }
        return Generation(text=json.dumps(payload), input_tokens=10, output_tokens=10, latency_ms=1.0, model="fake-1")

    monkeypatch.setattr(client.provider, "generate_json", answer)
    uploaded = client.post("/api/documents", files={"file": ("psa.txt", contract.encode("utf-8"), "text/plain")})
    assert uploaded.status_code == 201, uploaded.text
    started = client.post("/api/runs", json={"documentId": uploaded.json()["id"], "question": "What is the most that can be billed in a month?"})
    assert started.status_code == 202, started.text
    run_id = started.json()["id"]
    finding = client.get(f"/api/runs/{run_id}/detail").json()["findings"][0]
    assert (finding["status"], finding["statusSource"]) == ("needs_review", "position_check"), finding
    assert "$10,000" in finding["statusReason"] and finding["unquotedValues"] == ["$10,000"]
    explained = client.get(f"/api/runs/{run_id}/explanation").json()
    assert json.dumps(explained).count("needs_review") >= 1


# The review of policy-v6 (2026-10-10), each probe kept as a test.


def test_a_duration_quoted_in_another_unit_of_its_family_keeps_the_pass() -> None:
    assert check_values(PASS, "The initial term is 1 year.", ["This Agreement shall continue for twelve (12) months."], None, None) == PASS
    assert check_values(PASS, "Notice must be given 2 weeks ahead.", ["upon fourteen (14) days' notice"], None, None) == PASS
    # Across families code does not compare: three months is not ninety days.
    assert lowered(check_values(PASS, "Notice must be given 3 months ahead.", ["within ninety (90) days"], None, None))


def test_every_bracketed_redaction_mark_is_read_and_emphasis_is_not() -> None:
    assert lowered(check_values(PASS, "The fee is [ REDACTED ].", ["Fee: [REDACTED]"], None, None))
    assert check_values(PASS, "***Important***: the fee is 5%.", ["The fee is 5%."], None, None) == PASS


def test_withheld_words_count_only_in_the_marks_own_sentence() -> None:
    quote = "Liability shall not exceed [***]."
    assert lowered(check_values(PASS, "The cap is [***]. Confidential Information is defined in §1.", [quote], None, None))
    assert check_values(PASS, "Payable in the [*] period; the period is not disclosed.", ["in the [*] period"], None, None) == PASS


def test_a_dotted_clause_number_the_document_has_points_rather_than_states() -> None:
    # New-Qwen run on an independent case (2026-10-10): "... CONDITIONS (part 16)(11.4)" was reported as the value 11.4.
    quote = "Client shall be entitled to terminate this Agreement."
    answer = "Grayscale may terminate, as stated in TERMS AND CONDITIONS (part 16)(11.4)."
    assert check_values(PASS, answer, [quote], None, None, {"11.4"}) == PASS
    assert lowered(check_values(PASS, answer, [quote], None, None, set())), "a number the document never opens a clause with is still a value"
    # With a unit it is a value whatever the clause numbers; a whole number is never set aside this way.
    assert lowered(check_values(PASS, "The rate is 11.4 percent.", ["the rate"], None, None, {"11.4"}))
    assert lowered(check_values(PASS, "Newcorp must buy 6 Machines a year.", ["Minimum Purchase Commitment"], None, None, {"6"}))


def test_the_card_and_the_decision_read_the_same_clause_numbers(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    contract = (
        "SERVICES AGREEMENT\n\n11.4 Reports\nClient shall be entitled to terminate this Agreement if no report is delivered.\n\n"
        "12. Fees\nFees are due monthly.\n"
    )

    def answer(system: str, user: str, schema: dict[str, object]) -> Generation:
        label = next(line.split("]")[0][1:] for line in user.splitlines() if line.startswith("[sec_") and "Reports" in line)
        payload: dict[str, Any] = {
            "findings": [
                {
                    "topic": "Termination for reports",
                    "conclusion": "The Client may terminate if no report is delivered (11.4).",
                    "status_hint": "pass",
                    "evidence": [{"section_id": label, "quote": "Client shall be entitled to terminate this Agreement if no report is delivered."}],
                    "guidance_reference": None,
                    "observed": None,
                    "required": None,
                    "suggested_position": None,
                }
            ],
            "insufficient_evidence": False,
            "note": None,
        }
        return Generation(text=json.dumps(payload), input_tokens=10, output_tokens=10, latency_ms=1.0, model="fake-1")

    monkeypatch.setattr(client.provider, "generate_json", answer)
    uploaded = client.post("/api/documents", files={"file": ("reports.txt", contract.encode("utf-8"), "text/plain")})
    assert uploaded.status_code == 201, uploaded.text
    started = client.post("/api/runs", json={"documentId": uploaded.json()["id"], "question": "When can the Client terminate?"})
    finding = client.get(f"/api/runs/{started.json()['id']}/detail").json()["findings"][0]
    assert finding["status"] == "pass" and finding["unquotedValues"] == [], finding
