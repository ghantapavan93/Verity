"""Verifier v7: a changed number is never found (agent D's measurement, triage 2026-10-09).

Until v6 a typed token could END inside a run of letters and digits ("30days" gave the number 3, "1,500USD" gave
1,50) and every comma was dropped from a number ("1,5%" was 15%). Five quotes with a changed number were reported as
found, and one recorded span verified "3,0 days" against "30 days". The invariant is the module's own: every letter
and digit of a text belongs to exactly one significant token, and two numbers compare equal only when their values
are equal.
"""

from __future__ import annotations

import json
import re
from decimal import Decimal, InvalidOperation

import pytest
from fastapi.testclient import TestClient
from hypothesis import given
from hypothesis import strategies as st

from app.application.reverify_run import reverify_run
from app.db import SessionLocal
from app.providers.base import Generation
from app.verify import spans, tokens
from app.verify.tokens import canonical_number, locate_tokens, significant, tokenize
from tests.support import FakeProvider

CHANGED_NUMBERS = [
    ("fee of 150 per month", "fee of 1,500USD per month"),
    ("payable within 3 of invoice", "payable within 30days of invoice"),
    ("on the 1 day after", "on the 10th day after"),
    ("15% per annum", "1,5% per annum"),
    ("a fee of $1,500", "a fee of $15,00"),
    ("following 3,0 days notice;", "following 30 days notice;"),
]


def test_a_changed_number_is_never_found() -> None:
    for quote, text in CHANGED_NUMBERS:
        assert locate_tokens(quote, text) is None, (quote, text)
        assert spans.locate(quote, text) is None, (quote, text)


def test_controls_spelling_is_still_forgiven_and_precision_is_not() -> None:
    assert locate_tokens("a fee of 1500 dollars", "a fee of 1,500 dollars") is not None, "thousands grouping is spelling"
    assert locate_tokens("pay EUR 1500 now", "pay EUR 1,500 now") is not None
    assert locate_tokens("costs 1,234,567.50 in total", "costs 1234567.50 in total") is not None
    assert locate_tokens("15.00 per hour", "1500 per hour") is None, "a moved decimal point is a different value"
    assert spans.locate("thirty (30) days", "thirty (30) days") is not None, "exact is unchanged"
    assert locate_tokens("within 30days of invoice", "within 30days of invoice") is not None, "a glued run matches itself, whole"


def test_a_comma_after_a_number_is_punctuation_not_part_of_it() -> None:
    """Found by replaying v7 over EDGAR before it was kept: a number's pattern took the comma after it ("16, 2024" read
    as "16,"), and once a comma no longer vanished, "March 16" stopped being found in "March 16, 2024"."""
    assert locate_tokens("March 23 November 16", "means March 23 November 16, 2024 and") is not None
    assert locate_tokens("within 30 days", "within 30, 60 or 90 days, or within 30 days, as") is not None
    assert locate_tokens("a fee of $1,500", "a fee of $1,500, payable") is not None
    assert locate_tokens("15%", "rises by 15%, then") is not None
    assert locate_tokens("following 3,0 days", "following 30 days, notice") is None, "control: the changed number still is not"


def test_the_version_names_the_new_rule() -> None:
    assert spans.VERIFIER_VERSION == "v7"


_alnum = st.text(alphabet=st.sampled_from(list("ab9x0Z1,. $%-()")), min_size=0, max_size=40)


@given(_alnum)
def test_every_letter_and_digit_belongs_to_one_significant_token(text: str) -> None:
    covered = [False] * len(text)
    for token in significant(tokenize(text)):
        for i in range(token.start, token.end):
            assert not covered[i], (text, token)
            covered[i] = True
    for i, ch in enumerate(text):
        if ch.isalnum():
            assert covered[i], (text, i)


_number = st.from_regex(re.compile(r"\d{1,7}(,\d{1,4})*(\.\d{1,3})?"), fullmatch=True)


@given(_number, _number)
def test_two_numbers_are_equal_only_when_their_values_are(a: str, b: str) -> None:
    def value(text: str) -> Decimal | None:
        grouped = re.fullmatch(r"\d{1,3}(,\d{3})+(\.\d+)?", text)
        if "," in text and not grouped:
            return None  # not a number with thousands grouping: no value to share
        return Decimal(text.replace(",", ""))

    if canonical_number(a) == canonical_number(b):
        assert a == b or (value(a) is not None and value(a) == value(b) and str(value(a)) == str(value(b))), (a, b)


class OldCommaProvider(FakeProvider):
    """Quotes the contract's "(15)" as "(1,5)", which v6 forgave: the record a v6 build made."""

    def generate_json(self, system: str, user: str, schema: dict[str, object]) -> Generation:
        generation = super().generate_json(system, user, schema)
        payload = json.loads(generation.text)
        quote = payload["findings"][0]["evidence"][0]["quote"]
        payload["findings"][0]["evidence"][0]["quote"] = quote.replace("fifteen (15)", "fifteen (1,5)")
        return Generation(text=json.dumps(payload), input_tokens=100, output_tokens=50, latency_ms=12.5, model=self.model)


def test_reverifying_a_v6_record_shows_the_span_would_now_be_withheld(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    from tests.support import upload_and_ask

    def v6_canonical(text: str) -> str:
        cleaned = text.replace(",", "").replace(" ", "")
        try:
            Decimal(cleaned)
        except InvalidOperation:
            return text
        return cleaned

    provider = OldCommaProvider()
    client.app.state.provider = provider  # type: ignore[attr-defined]
    current = tokens.canonical_number
    monkeypatch.setattr(tokens, "canonical_number", v6_canonical)
    run_id = upload_and_ask(client, "What notice period applies to termination for convenience?")["run_id"]
    detail = client.get(f"/api/runs/{run_id}/detail").json()
    assert detail["findings"][0]["spans"][0]["verified"] is True, "the v6 record: the changed number was found"
    monkeypatch.setattr(tokens, "canonical_number", current)
    with SessionLocal() as session:
        replay = reverify_run(session, run_id)
    assert replay.lost == 1 and replay.spans[0].change == "lost", "v7 would withhold it"
    assert client.get(f"/api/runs/{run_id}/detail").json()["findings"][0]["spans"][0]["verified"] is True, "the record is not rewritten"
