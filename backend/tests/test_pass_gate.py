"""A pass is a claim about meaning, and code can only compare periods. So a pass is the model's to propose and code's
to confirm, from the source text alone (policy.proof); every case here was a pass computed by code before 2026-10-02
(policy-v1) or would have been one. The other direction is code's own: a shortfall, 60 days against a floor of 90."""

from __future__ import annotations

import itertools
from pathlib import Path
from typing import Any, get_args

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app import db as db_module
from app.analysis.schema import StatusHint
from app.models import FINDING_STATUSES, STATUS_SOURCES, STATUSES_BY_SOURCE
from app.policy.durations import parse_rule
from app.policy.proof import pass_blockers
from app.providers.base import Generation
from app.runs.status import Decision, Grounds, decide, enclosing_sentences, settle_together, unseen_references
from tests.support import GUIDANCE

GUIDANCE_90 = "We require at least 90 days' written notice for termination for convenience. Anything shorter needs review."
# A pass that code decided or confirmed: what a hostile input must never end as.
PASSES_BY_CODE = {("pass", "computed_days"), ("pass", "confirmed_days")}
# Policy v3: a pass is the model's; code reports the comparison and says what it did not establish.
SUBJECT = "; that the quoted period and the guidance concern the same point is the model's reading, not code's"
CONSISTENT = "; code found the day counts consistent, and that the quoted period and the guidance concern the same point is the model's reading, not code's"
TOPIC = "Termination for convenience"
CLEAN = "Either party may terminate this Agreement for convenience upon ninety (90) days' prior written notice."
HERO = "4.1 TERMINATION WITHOUT CAUSE. Either party may terminate this Agreement without cause upon sixty (60) days prior written notice to the other party."


def decided(quote: str, hint: StatusHint = "pass", guidance: str = GUIDANCE_90, dependencies: tuple[str, ...] = (), topic: str | None = TOPIC) -> Decision:
    return decide(hint, None, None, True, True, quotes=[quote], guidance=guidance, topic=topic, dependencies=dependencies)


def test_a_plain_clause_about_the_same_point_is_a_pass_the_model_proposed_and_code_confirmed() -> None:
    assert decided(CLEAN) == Decision(
        "pass", "model_hint", "the contract provides 90 calendar days; the guidance requires at least 90 calendar days" + CONSISTENT
    )
    assert pass_blockers([CLEAN], GUIDANCE_90, parse_rule(GUIDANCE_90, TOPIC)) == []  # type: ignore[arg-type]


def test_a_shortfall_is_still_decided_by_code_whatever_surrounds_it() -> None:
    assert decided(HERO) == Decision(
        "needs_review", "computed_days", "the contract provides 60 calendar days; the guidance requires at least 90 calendar days" + SUBJECT
    )
    # None of what blocks a pass stands in the way of reporting a shortfall: a person looks either way.
    assert decided(HERO, hint="needs_review").source == "computed_days"
    assert decided(HERO, dependencies=("§14.3",)).source == "computed_days"
    assert decided("Subject to Section 9, Provider may terminate on no more than 60 days' notice.").source == "computed_days"
    assert decided("Customer will pay each invoice within 45 days.") == Decision(
        "needs_review", "computed_days", "the contract provides 45 calendar days; the guidance requires at least 90 calendar days" + SUBJECT
    )


@pytest.mark.parametrize(
    ("quote", "why"),
    [
        # The period is a ceiling where the guidance sets a floor.
        ("Provider may terminate for convenience on no more than 90 days' notice.", "states its period as a ceiling"),
        ("Provider may terminate for convenience on notice of up to 120 days.", "states its period as a ceiling"),
        ("Provider may terminate for convenience on notice of less than 120 days.", "states its period as a ceiling"),
        # A window after an event, and a deadline before one, are not a length of notice.
        ("Customer may terminate for convenience within 90 days after each anniversary of the Effective Date.", "states its period as a ceiling"),
        ("Either party may terminate for convenience by notice given at least 90 days before the end of the then-current term.", "counted back from an event"),
        ("Termination for convenience takes effect only where notice was given 120 days prior to the anniversary.", "counted back from an event"),
        # A negation beside the period.
        ("Provider shall not be required to give 90 days' notice of termination for convenience.", "a negation stands beside the period"),
        ("Termination for convenience by Provider is effective without 90 days' notice.", "a negation stands beside the period"),
        # A condition or an exception in the clause.
        ("Either party may terminate for convenience on 120 days' notice, provided that all Fees have been paid.", "a condition or an exception"),
        ("Either party may terminate for convenience on 120 days' notice, subject to Section 14.3.", "a condition or an exception"),
        ("Notwithstanding Section 4, Customer may terminate for convenience on 120 days' notice.", "a condition or an exception"),
        ("Either party may terminate for convenience on 120 days' notice only if the Minimum Commitment has been met.", "a condition or an exception"),
        # Another subject altogether, with a period that happens to be long enough.
        ("Customer will pay each invoice within 120 days of the invoice date.", "share too few words"),
        (
            "Either party may terminate this Agreement if the other party fails to cure a material breach within one hundred twenty (120) days.",
            "share too few words",
        ),
        ("The Agreement renews for successive terms of 120 days.", "share too few words"),
        ("Either party may terminate upon one hundred twenty (120) days' written notice.", "share too few words"),
    ],
)
def test_what_was_a_computed_pass_is_now_the_models_view_with_the_reason(quote: str, why: str) -> None:
    decision = decided(quote)
    assert (decision.status, decision.source) == ("pass", "model_hint"), decision
    assert "but code does not confirm that as a pass" in decision.reason and why in decision.reason
    assert decision.reason.startswith("the contract provides "), "the arithmetic is still said, so a reader sees what was compared"


def test_the_models_doubt_is_not_overruled_by_arithmetic() -> None:
    doubted = decided(CLEAN, hint="needs_review")
    assert (doubted.status, doubted.source) == ("needs_review", "model_hint") and "the model asked for review" in doubted.reason
    assert decided(CLEAN, hint="missing").status == "missing"


def test_who_owns_each_direction_is_what_the_record_says() -> None:
    """Same verified quote, same guidance; only the model's hint changes. A pass disappears with the model's hint, so
    it is recorded as the model's pass confirmed by code, never as code's decision. A shortfall does not move with the
    hint, so it is recorded as code's decision."""
    by_hint = {hint: decided(CLEAN, hint=hint) for hint in get_args(StatusHint)}
    assert (by_hint["pass"].status, by_hint["pass"].source) == ("pass", "model_hint")
    assert "code found the day counts consistent" in (by_hint["pass"].reason or "")
    assert (by_hint["needs_review"].status, by_hint["needs_review"].source) == ("needs_review", "model_hint")
    assert (by_hint["missing"].status, by_hint["missing"].source) == ("missing", "model_hint")
    assert "pass" not in STATUSES_BY_SOURCE["position_check"] + STATUSES_BY_SOURCE["ambiguous_fact"] + STATUSES_BY_SOURCE["reference_check"]
    assert STATUSES_BY_SOURCE["confirmed_days"] == ("pass",), "a confirmation is of a pass and of nothing else"

    short = {hint: decided(HERO, hint=hint) for hint in ("pass", "needs_review")}
    assert (
        short["pass"]
        == short["needs_review"]
        == Decision("needs_review", "computed_days", "the contract provides 60 calendar days; the guidance requires at least 90 calendar days" + SUBJECT)
    )


def test_a_passage_that_points_at_an_unseen_section_is_not_passed_by_code() -> None:
    decision = decided(CLEAN, dependencies=("§14.3", "Schedule B"))
    assert (decision.status, decision.source) == ("pass", "model_hint")
    assert "refers to §14.3, Schedule B, which the model was not handed" in decision.reason


def test_the_models_wording_cannot_earn_a_pass_and_cannot_change_one() -> None:
    """Same verified quote, same guidance; only the model's own fields change. Whether code passes is settled by the
    source text: nothing the model writes turns a blocked quote into a computed pass, and nothing but its own hint or a
    number the quote does not carry takes a computed pass away."""
    topics = (TOPIC, "Payment terms", "Renewal", "", None)
    observed = (None, "", "90 days", "ninety (90) days' prior written notice", "120 days")
    required = (None, "", "at least 90 days", "30 days")
    hints: tuple[StatusHint, ...] = get_args(StatusHint)
    blocked = "Provider may terminate for convenience on no more than 90 days' notice."
    for topic, seen, wanted, hint in itertools.product(topics, observed, required, hints):
        refused = decide(hint, seen, wanted, True, True, quotes=[blocked], guidance=GUIDANCE_90, topic=topic)
        assert (refused.status, refused.source) not in PASSES_BY_CODE, refused
        clean = decide(hint, seen, wanted, True, True, quotes=[CLEAN], guidance=GUIDANCE_90, topic=topic)
        lowered_by_the_model = hint != "pass" or seen == "120 days" or wanted == "30 days"
        assert (clean == Decision("pass", "model_hint", clean.reason) and "consistent" in (clean.reason or "")) == (not lowered_by_the_model), (
            topic,
            seen,
            wanted,
            hint,
            clean,
        )
        assert (clean.status, clean.source) != ("pass", "computed_days"), "no new decision says code decided a pass"


@pytest.mark.parametrize(
    ("quotes", "guidance"),
    [
        (["", "   "], GUIDANCE_90),  # empty evidence text
        ([CLEAN, CLEAN], "at least 90 days"),  # guidance that names no subject
        ([CLEAN, "Provider may terminate immediately."], GUIDANCE_90),  # a carve-out in a second quote
        (["on 90 days' notice, 30 days to cure and 120 days to renew"], GUIDANCE_90),  # several periods, no subject
        (
            [CLEAN],
            "Termination for convenience needs at least 90 days' notice. Termination for convenience needs no more than 30 days' notice.",
        ),  # contradictory
        ([CLEAN], "Termination for convenience: notice no later than 90 days before the end of the term."),  # the guidance counts back, the quote does not
        (["Termination for convenience on twenty-one (90) days' notice."], GUIDANCE_90),  # words and digits disagree
        (["Termination for convenience on 3 months' notice."], GUIDANCE_90),  # a month is not thirty days
        (["Termination for convenience on 90 business days' notice."], GUIDANCE_90),  # business days are not calendar days
    ],
)
def test_hostile_inputs_never_end_as_a_pass_by_code(quotes: list[str], guidance: str) -> None:
    for hint in get_args(StatusHint):
        for topic in (TOPIC, "", None):
            decision = decide(hint, None, None, True, True, quotes=quotes, guidance=guidance, topic=topic)
            assert (decision.status, decision.source) not in PASSES_BY_CODE, decision


def test_the_same_quote_twice_is_one_quote() -> None:
    twice = decide("pass", None, None, True, True, quotes=[CLEAN, CLEAN], guidance=GUIDANCE_90, topic=TOPIC)
    assert twice == decided(CLEAN)


# ---------------------------------------------------------------- what a passage points at


SECTIONS = [
    ("4", "Termination"),
    ("14.3", "Limits"),
    ("0.15.11", "Prefixed"),
    ("7", "Fees (part 1)"),
    ("7", "Fees (part 2)"),
    ("", "Schedule B Fees"),
    ("", "Cover"),
]


def test_a_reference_is_unseen_when_the_section_exists_and_was_not_handed() -> None:
    handed = [("4", "Termination")]
    assert unseen_references("Subject to Section 14.3 and Schedule B, either party may terminate.", SECTIONS, handed) == ["§14.3", "Schedule B"]
    assert unseen_references("as defined in clause 15.11", SECTIONS, handed) == ["§15.11"], "a reader's prefixed numbering is the same section"
    # Handed, or the passage's own section: seen.
    assert unseen_references("Subject to Section 14.3, see Section 4.", SECTIONS, [*handed, ("14.3", "Limits")]) == []
    # A section split into parts is seen only when every part was handed.
    assert unseen_references("under Section 7", SECTIONS, [*handed, ("7", "Fees (part 1)")]) == ["§7"]
    assert unseen_references("under Section 7", SECTIONS, [*handed, ("7", "Fees (part 1)"), ("7", "Fees (part 2)")]) == []
    # What this reading of the document does not have cannot be called unseen: another agreement's section, a schedule in another file.
    assert unseen_references("Section 99 of the DPA and Exhibit Q apply.", SECTIONS, handed) == []
    # Malformed references name nothing.
    assert (
        unseen_references("Section , §, Section 14..3x, clause .5, Schedule", SECTIONS, handed) == ["§14"]
        or unseen_references("Section , §, Section 14..3x, clause .5, Schedule", SECTIONS, handed) == []
    )


def test_the_sentences_around_a_quote_are_read_not_only_the_quote() -> None:
    section = "Scope. Subject to Section 14.3, either party may terminate for convenience on 120 days' notice. Fees remain due."
    start = section.index("either party")
    assert enclosing_sentences(section, start, start + 20) == "Subject to Section 14.3, either party may terminate for convenience on 120 days' notice."
    assert enclosing_sentences("one sentence only", 0, 3) == "one sentence only"
    assert enclosing_sentences("First.\nSecond line here.\nThird.", 8, 14) == "Second line here."


LONG_CONTRACT = """MASTER SERVICES AGREEMENT

1. Term

This Agreement commences on the Effective Date and continues for twelve (12) months.

2. Termination for Convenience

{lead}Customer may terminate this Agreement for convenience upon ninety (90) days’ written notice to Provider.

3. Governing Law

This Agreement is governed by the laws of the State of Delaware.

4. Confidentiality

Each side keeps the other's information secret.

5. Insurance

Provider maintains commercial general liability cover.

6. Publicity

Neither side uses the other's marks.

7. Records

Provider keeps books for audit.

8. Special Conditions

Where spend falls beneath the floor, the vendor has the right to end things early.
"""
QUOTE = "Customer may terminate this Agreement for convenience upon ninety (90) days’ written notice to Provider."


def ask(client: TestClient, monkeypatch: pytest.MonkeyPatch, lead: str) -> dict[str, Any]:
    def answer(system: str, user: str, schema: dict[str, object]) -> Generation:
        label = next(line.split("]")[0][1:] for line in user.splitlines() if line.startswith("[sec_") and "Termination for Convenience" in line)
        payload = {
            "findings": [
                {
                    "topic": TOPIC,
                    "conclusion": "Customer may terminate for convenience on 90 days' written notice.",
                    "status_hint": "pass",
                    "evidence": [{"section_id": label, "quote": QUOTE}],
                    "guidance_reference": "at 30 days' notice or more",
                    "observed": "90 days' written notice",
                    "required": "at least 30 days",
                    "suggested_position": None,
                }
            ],
            "insufficient_evidence": False,
            "note": None,
        }
        import json

        return Generation(text=json.dumps(payload), input_tokens=10, output_tokens=10, latency_ms=1.0, model="fake-1")

    monkeypatch.setattr(client.provider, "generate_json", answer)
    uploaded = client.post("/api/documents", files={"file": ("msa.txt", LONG_CONTRACT.format(lead=lead).encode("utf-8"), "text/plain")})
    assert uploaded.status_code == 201, uploaded.text
    guidance_id = client.post("/api/guidance", json={"text": GUIDANCE}).json()["id"]
    started = client.post(
        "/api/runs",
        json={"documentId": uploaded.json()["id"], "guidanceId": guidance_id, "question": "How much notice must Customer give to terminate for convenience?"},
    )
    assert started.status_code == 202, started.text
    detail: dict[str, Any] = client.get(f"/api/runs/{started.json()['id']}/detail").json()
    return detail


def test_through_the_run_a_clause_subject_to_an_unseen_section_is_the_models_view(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    plain = ask(client, monkeypatch, lead="")
    finding = plain["findings"][0]
    assert (finding["status"], finding["statusSource"]) == ("pass", "model_hint"), finding
    assert "code found the day counts consistent" in finding["statusReason"]

    dependent = ask(client, monkeypatch, lead="Subject to Section 8, ")
    assert "8" not in [c["number"] for c in dependent["candidates"]], "section 8 shares no word with the question, so it was not handed over"
    finding = dependent["findings"][0]
    assert (finding["status"], finding["statusSource"]) == ("pass", "model_hint"), finding
    assert "refers to §8, which the model was not handed" in finding["statusReason"]
    assert 'a condition or an exception ("subject to")' in finding["statusReason"], "the words outside the quote, in its sentence, were read too"


def test_what_the_quote_left_out_of_its_own_sentence_still_blocks_a_pass() -> None:
    quote = "Customer may terminate for convenience on 120 days' notice"
    for sentence, why in (
        (f"Unless the Minimum Commitment is unmet, {quote}.", 'a condition or an exception ("unless")'),
        (f"{quote}, or on 10 days' notice in the first year.", "states another period that the quote left out"),
        (f"{quote}; Provider may terminate immediately.", "states another period that the quote left out"),
    ):
        decision = decide("pass", None, None, True, True, quotes=[quote], guidance=GUIDANCE_90, topic=TOPIC, passages=[sentence])
        assert (decision.status, decision.source) == ("pass", "model_hint") and why in decision.reason, decision
    assert "consistent" in (decide("pass", None, None, True, True, quotes=[quote], guidance=GUIDANCE_90, topic=TOPIC, passages=[quote + "."]).reason or "")


# ---------------------------------------------------------------- pairs that are not decisions


@pytest.mark.parametrize(("source", "status"), list(itertools.product(STATUS_SOURCES, FINDING_STATUSES)))
def test_a_decision_exists_only_for_the_pairs_the_system_can_make(source: str, status: str) -> None:
    if status in STATUSES_BY_SOURCE[source]:  # type: ignore[index]
        assert Decision(status, source).status == status  # type: ignore[arg-type]
    else:
        with pytest.raises(ValueError, match="cannot decide"):
            Decision(status, source)  # type: ignore[arg-type]


def test_a_fresh_database_refuses_a_status_its_source_cannot_decide(tmp_path: Path) -> None:
    engine = db_module.make_engine(f"sqlite:///{(tmp_path / 'new.db').as_posix()}")
    db_module.init_db(engine)
    insert = "INSERT INTO findings (id, run_id, ordinal, topic, status, status_source, conclusion) VALUES ('{id}', 'r1', 0, 't', '{status}', '{source}', 'c')"
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO documents (id, name, media_type, sha256, pages, created_at) VALUES ('d1', 'a.txt', 'text/plain', 'abc', 1, '2026-10-02 00:00:00')"
            )
        )
        connection.execute(
            text(
                "INSERT INTO runs (id, document_id, question, stage, provider, model, prompt_version, prompt_hash, options_json, document_sha256, "
                "candidates_json, created_at) VALUES ('r1', 'd1', 'q', 'reading', 'fake', 'fake-1', 'v', 'h', '{}', 'abc', '[]', '2026-10-02 00:00:00')"
            )
        )
        connection.execute(text(insert.format(id="ok", status="needs_review", source="computed_days")))
    for bad_id, status, source in (
        ("b1", "missing", "computed_days"),
        ("b2", "pass", "no_evidence"),
        ("b3", "unresolved", "computed_days"),
        ("b4", "pass", "guessed"),
    ):
        with pytest.raises(IntegrityError, match="ck_findings_status_source"), engine.begin() as connection:
            connection.execute(text(insert.format(id=bad_id, status=status, source=source)))


# ---------------------------------------------------------------- findings that bear on each other


PAYMENT = "Customer will pay each invoice within fifteen (15) days of the invoice date."
OVERRIDE = "Notwithstanding Section 4, Provider may terminate this Agreement for convenience upon ten (10) days' written notice."


def grounds(quote: str, section: tuple[str, str], sentence: str | None = None) -> Grounds:
    return Grounds((quote,), (sentence or quote,), (section,))


def test_a_shortfall_in_an_unrelated_finding_takes_nothing_from_a_consistent_pass() -> None:
    """A question that asks two things: termination, 90 days against a floor of 90, and payment, which code measures
    against the same floor and finds short. Being findings of one run is not a relation between them."""
    confirmed, short = decided(CLEAN), decided(PAYMENT)
    assert (confirmed.source, short.source) == ("model_hint", "computed_days")
    settled = settle_together([confirmed, short], [grounds(CLEAN, ("s4", "4")), grounds(PAYMENT, ("s2", "2"))], GUIDANCE_90)
    assert settled == [confirmed, short]
    # Nor does a lowering that is about the model's wording, or the model's own hint.
    others = [Decision("needs_review", "reference_check"), Decision("needs_review", "model_hint"), Decision("pass", "model_hint")]
    assert settle_together([confirmed, *others], [grounds(CLEAN, ("s4", "4"))] + [grounds(CLEAN, ("s4", "4"))] * 3, GUIDANCE_90)[0] == confirmed
    assert settle_together([confirmed], [grounds(CLEAN, ("s4", "4"))], GUIDANCE_90) == [confirmed]


@pytest.mark.parametrize(
    ("short_quote", "short_grounds", "relation"),
    [
        # The live model's own case: another clause about the same point, shorter.
        (OVERRIDE, grounds(OVERRIDE, ("s11", "11")), "refers to §4"),
        # About the same point of the guidance, with no reference at all.
        (
            "Provider may terminate this Agreement for convenience upon ten (10) days' written notice.",
            grounds("Provider may terminate this Agreement for convenience upon ten (10) days' written notice.", ("s11", "11")),
            "about the same point",
        ),
        # Another subject, but the clause points at the section the pass rests on.
        (PAYMENT, grounds(PAYMENT, ("s2", "2"), "Subject to Section 4, " + PAYMENT), "refers to §4"),
        # Another subject, found in the same section as the pass.
        (PAYMENT, grounds(PAYMENT, ("s4", "4")), "cites the same section"),
    ],
)
def test_a_consistent_pass_names_a_shortfall_that_bears_on_it(short_quote: str, short_grounds: Grounds, relation: str) -> None:
    confirmed, short = decided(CLEAN), decided(short_quote)
    assert short.status == "needs_review" and short.source in ("computed_days", "ambiguous_fact"), short
    settled = settle_together([confirmed, short], [grounds(CLEAN, ("s4", "4")), short_grounds], GUIDANCE_90)
    assert (settled[0].status, settled[0].source) == ("pass", "model_hint")
    assert settled[0].reason.startswith(confirmed.reason) and "code does not confirm that as a pass" in settled[0].reason and relation in settled[0].reason
    assert settled[1] == short, "the shortfall is what it was"
