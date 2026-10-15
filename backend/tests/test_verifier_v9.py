"""Verifier v9: a sign-inverted amount is never verified, whatever way the amount is written (legal evaluation B1).

The legal evaluation of 2026-10-14 served the answer "The Adjustment Amount is $5M" with the quote "Adjustment Amount
$5M" against a contract whose table reads "Adjustment Amount -$5M". Verifier v8 verified the quote at the typed tier, the
status stayed a pass, the card said "with the same words and numbers", the memo printed the quote as observed language
and the evidence pack's verify.py agreed. v8 already kept the sign of "-5%" and "($500)"; an amount written with a
magnitude letter ("$5M", "USD 10K", "2.5bn") was a word to it, so its sign, parentheses and currency were punctuation.

The invariant: a located span carries every number it covers with the sign, parentheses, currency and magnitude written
against it, and never begins or ends inside such a number; in a number written with a sign or parentheses, not even at
the space after its currency. A quote whose number differs from the source's in sign, parentheses, currency or magnitude
is withheld at every tier, and a quote that matches it is still found.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import types
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from hypothesis import given, settings
from hypothesis import strategies as st

from app.application.evidence_pack import render_verify_py
from app.hashing import sha256_bytes
from app.providers.base import Generation
from app.verify import tokens
from app.verify.spans import _INVISIBLE as INVISIBLE
from app.verify.spans import VERIFIER_VERSION, bounded, locate
from tests.support import FUZZ_SCALE, FakeProvider

SOURCE = "Closing Statement item Amount\n\nAdjustment Amount -$5M\n\n2.3 Buyer shall deliver the Closing Statement."

# The evaluation's own case (scripted probe S13), then its class: each was found under v8, each is withheld from v9.
SIGN_LOST = [
    pytest.param("Adjustment Amount $5M", SOURCE, id="B1-typed-sign-dropped"),
    pytest.param("$5M", SOURCE, id="B1-exact-inside-the-signed-amount"),
    pytest.param("Adjustment Amount ($5M)", SOURCE, id="parentheses-for-a-minus"),
    pytest.param("a credit of $5M", "a credit of ($5M) to Customer", id="typed-accounting-parentheses"),
    pytest.param("$5M", "a credit of ($5M) to Customer", id="exact-inside-accounting-parentheses"),
    pytest.param("a credit of $5M", "a credit of −$5M to Customer", id="typed-typeset-minus"),
    pytest.param("a credit of $5M", "a credit of –$5M to Customer", id="typed-en-dash-minus"),
    pytest.param("a credit of $5M", "a credit of －$5M to Customer", id="typed-fullwidth-minus"),
    pytest.param("a credit of USD 10K", "a credit of -USD 10K applies", id="typed-currency-code"),
    pytest.param("USD 10K", "a credit of -USD 10K applies", id="exact-currency-code-without-its-sign"),
    pytest.param("10K applies", "a credit of -USD 10K applies", id="exact-after-the-currency-space"),
    pytest.param("USD 10K", "a credit of (USD 10K) applies", id="exact-inside-parenthesised-code"),
    pytest.param("USD10K", "a credit of -USD 10K applies", id="typed-code-written-together"),
    pytest.param("a loss of 2.5bn", "a loss of -2.5bn", id="typed-decimal-billions"),
    pytest.param("2.5bn", "a loss of -2.5bn", id="exact-decimal-billions"),
    pytest.param("a loss of €4.5MM", "a loss of -€4.5MM", id="typed-euro-mm"),
    pytest.param("a fee of $ 5M", "a fee of -$ 5M", id="typed-currency-spacing"),
    pytest.param("a credit of US$500", "a credit of -US$500 applies", id="typed-letters-before-the-dollar"),
    pytest.param("US$500", "a credit of -US$500 applies", id="exact-letters-before-the-dollar"),
    pytest.param("500 per year", "a fee of -USD 500 per year", id="exact-unsuffixed-code-space"),
    pytest.param("a credit of 5m units", "a credit of -5m units", id="typed-bare-magnitude"),
    pytest.param("Fees 4 Adjustment Amount $5M", SOURCE, id="unprefixed-typed-sign-dropped"),
    # The independent review's counterexamples to the first repair: a currency outside the six codes, an invisible mark.
    pytest.param("INR 5M", "the amount is (INR 5M) today", id="review-iso-code-parentheses"),
    pytest.param("INR 5M", "the amount is -INR 5M today", id="review-iso-code-minus"),
    pytest.param("JPY 500", "the amount is -JPY 500 today", id="review-iso-code-unsuffixed"),
    pytest.param("₹5M", "the amount is -₹5M today", id="review-rupee-sign"),
    pytest.param("Rs. 5M", "the amount is -Rs. 5M today", id="review-rupee-abbreviation"),
    pytest.param("the amount is SGD 5M today", "the amount is -SGD 5M today", id="review-typed-iso-code"),
    pytest.param("5M", "the amount is -₩5M today", id="exact-after-a-won-sign"),
    pytest.param("Adjustment Amount $5M", "Adjustment Amount -‎$5M", id="review-direction-mark-after-the-sign"),
    pytest.param("Adjustment Amount $5M", "Adjustment Amount -​$5M", id="zero-width-space-after-the-sign"),
    # The second review's counterexample: a currency code glued to digits with no magnitude letter is one word as well.
    pytest.param("Amount INR500", "Amount -INR500", id="review2-code-glued-to-digits"),
    pytest.param("Amount JPY5 due", "Amount (JPY5) due", id="review2-code-glued-parentheses"),
    pytest.param("Amount SGD5", "Amount -‎SGD5", id="review2-code-glued-direction-mark"),
    pytest.param("INR1,500", "a fee of -INR1,500 is due", id="review2-code-glued-grouped-digits"),
]


@pytest.mark.parametrize(("quote", "text"), SIGN_LOST)
def test_a_quote_that_drops_a_sign_is_withheld_at_every_tier(quote: str, text: str) -> None:
    assert locate(quote, text, "4 Fees") is None


SIGN_ADDED = [
    pytest.param("Adjustment Amount -$5M", "Adjustment Amount $5M", id="minus-the-text-lacks"),
    pytest.param("a credit of ($5M)", "a credit of $5M", id="parentheses-the-text-lacks"),
    pytest.param("a credit of -USD 10K", "a credit of USD 10K", id="code-minus-the-text-lacks"),
    pytest.param("a credit of $5MM", "a credit of $5M", id="a-different-magnitude"),
    pytest.param("a credit of EUR 5M", "a credit of USD 5M", id="a-different-currency"),
    pytest.param("a credit of $5.0M", "a credit of $5M", id="a-different-precision"),
    pytest.param("Adjustment Amount -​$5M", "Adjustment Amount $5M", id="review-an-invisible-mark-adds-no-sign"),
    pytest.param("Amount -INR500", "Amount INR500", id="review2-code-glued-minus-the-text-lacks"),
    pytest.param("Amount USD500", "Amount INR500", id="review2-code-glued-another-currency"),
]


@pytest.mark.parametrize(("quote", "text"), SIGN_ADDED)
def test_a_quote_whose_amount_differs_in_sign_magnitude_currency_or_precision_is_withheld(quote: str, text: str) -> None:
    assert locate(quote, text) is None


# (quote, text, method, the characters highlighted): genuine amounts, positive and negative, are still found.
GENUINE = [
    pytest.param("Adjustment Amount -$5M", SOURCE, "exact", "Adjustment Amount -$5M", id="the-source-as-written"),
    pytest.param("Adjustment Amount −$5M", SOURCE, "normalized", "Adjustment Amount -$5M", id="typeset-minus-for-minus"),
    pytest.param("$5M", "a fee of $5M is due", "exact", "$5M", id="positive-amount"),
    pytest.param("($5M)", "a credit of ($5M) to Customer", "exact", "($5M)", id="accounting-negative-whole"),
    pytest.param("USD 10K", "a fee of USD 10K applies", "exact", "USD 10K", id="positive-currency-code"),
    pytest.param("usd 10k", "a fee of USD 10K applies", "casefold", "USD 10K", id="case-only"),
    pytest.param("USD10K", "a fee of USD 10K applies", "typed", "USD 10K", id="code-written-together"),
    pytest.param("a fee of $ 5M", "a fee of $5M applies", "typed", "a fee of $5M", id="currency-spacing"),
    pytest.param("-2.5bn", "a loss of -2.5bn", "exact", "-2.5bn", id="negative-decimal-billions"),
    pytest.param("US$500", "a fee of US$500 applies", "exact", "US$500", id="letters-before-the-dollar"),
    pytest.param("500 per year", "a fee of USD 500 per year", "exact", "500 per year", id="v8-control-a-space-is-still-an-edge"),
    pytest.param("$5M", "first -$5M, then $5M later", "exact", "$5M", id="repeated-the-signed-one-skipped"),
    pytest.param("$5M.", "The total is $5M.", "exact", "$5M.", id="before-a-full-stop"),
    pytest.param("$5M, payable", "a fee of $5M, payable in advance", "exact", "$5M, payable", id="before-a-comma"),
    pytest.param("($5M).", "a credit of ($5M).", "exact", "($5M).", id="parentheses-then-full-stop"),
    pytest.param(
        "$10M in aggregate per year",
        "The fee is capped at $10M (in aggregate) per year.",
        "typed",
        "$10M (in aggregate) per year",
        id="typed-around-punctuation",
    ),
    pytest.param("rate of -2.5% p.a.", "a rate of -2.5% p.a. applies", "exact", "rate of -2.5% p.a.", id="signed-decimal-percent"),
    pytest.param("5m units", "deliver 5m units", "exact", "5m units", id="bare-magnitude"),
    pytest.param("INR 5M", "the amount is INR 5M today", "exact", "INR 5M", id="iso-code"),
    pytest.param("₹5M", "the amount is ₹5M today", "exact", "₹5M", id="rupee-sign"),
    pytest.param("Rs. 5M", "the amount is Rs. 5M today", "exact", "Rs. 5M", id="rupee-abbreviation"),
    pytest.param("Adjustment Amount -$5M", "Adjustment Amount -‎$5M", "normalized", "Adjustment Amount -‎$5M", id="direction-mark-kept-with-its-sign"),
    pytest.param("$5M", "a payment of$5M is due", "exact", "$5M", id="lower-case-letters-glued-to-a-dollar-are-no-currency"),
    pytest.param("5M", "a fee of USD 5M", "exact", "5M", id="unsigned-code-apart-by-a-space-may-be-left-off"),
    pytest.param("NET 30 DAYS", "PAYMENT TERMS NET 30 DAYS", "exact", "NET 30 DAYS", id="capitals-before-a-number"),
    pytest.param("Amount -INR500", "the Amount -INR500 is due", "exact", "Amount -INR500", id="code-glued-signed-as-written"),
    pytest.param("amount inr500", "the Amount INR500 is due", "casefold", "Amount INR500", id="code-glued-case-only"),
    pytest.param("TOP 10 risks", "the TOP 10 risks", "exact", "TOP 10 risks", id="a-code-like-word-before-a-number"),
]


@pytest.mark.parametrize(("quote", "text", "method", "shown"), GENUINE)
def test_controls_a_genuine_amount_is_still_found(quote: str, text: str, method: str, shown: str) -> None:
    located = locate(quote, text)
    assert located is not None, (quote, text)
    assert (located.method, text[located.start : located.end]) == (method, shown)


def test_a_repeated_amount_counts_only_its_unsigned_places() -> None:
    located = locate("$5M", "first -$5M, then $5M, then ($5M) and $5M")
    assert located is not None and located.count == 2


def test_the_verifier_is_v9_or_later_and_v8_reads_as_it_did() -> None:
    assert VERIFIER_VERSION in ("v9", "v10")  # v10 keeps every v9 rule (test_post_pilot_repair.py)
    # v8's pattern is the one its evidence packs carry, to the character (its sha256 as de1f6de2 shipped it).
    assert hashlib.sha256(tokens._WRITTEN_V8.pattern.encode()).hexdigest() == "cc4fe06d589f0f21c6c1fe5bc2a57cdf35698eaef68305251fecd5e03a019119"
    v8 = [t.canonical for t in tokens.significant(tokens.signed(SOURCE, tokens.tokenize(SOURCE), 8))]
    quote = "Adjustment Amount $5M"
    assert [t.canonical for t in tokens.significant(tokens.signed(quote, tokens.tokenize(quote), 8))] == v8[4:7], "v8 read the two alike"
    assert "-$5m" in [t.canonical for t in tokens.significant(tokens.signed(SOURCE, tokens.tokenize(SOURCE)))]


def test_the_tokens_values_are_read_from_are_unchanged() -> None:
    """runs.values (policy) and trust.facts read `tokenize`, which v9 leaves alone: their values do not move."""
    assert [(t.kind, t.canonical) for t in tokens.significant(tokens.tokenize("-$5M and USD 10K"))] == [
        (tokens.Kind.WORD, "5m"),
        (tokens.Kind.WORD, "and"),
        (tokens.Kind.WORD, "usd"),
        (tokens.Kind.WORD, "10k"),
    ]


# ---------------------------------------------------------------------------------------------------- properties

CURRENCIES = ["$", "€", "£", "USD ", "EUR ", "US$", "", "$ ", "INR ", "JPY ", "₹", "₩", "Rs. ", "kr ", "INR", "JPY"]
MAGNITUDES = ["M", "m", "K", "k", "bn", "MM", "B", ""]
# How each sign is written -> its value class; an invisible mark beside a sign is no sign of its own.
SIGNS = {"": "", "-": "-", "−": "-", "–": "-", "(": "()", "-‎": "-", "​": ""}


@st.composite
def amount(draw: st.DrawFn) -> tuple[str, str, str]:
    """(currency, digits, magnitude) of a positive amount as written."""
    digits = draw(st.sampled_from(["5", "10", "2.5", "1,500", "0.75", "250"]))
    return draw(st.sampled_from(CURRENCIES)), digits, draw(st.sampled_from(MAGNITUDES))


def write(sign: str, parts: tuple[str, str, str]) -> str:
    body = "".join(parts)
    return f"({body})" if sign == "(" else sign + body


@settings(max_examples=600 * FUZZ_SCALE, deadline=None)
@given(parts=amount(), quote_sign=st.sampled_from(sorted(SIGNS)), text_sign=st.sampled_from(sorted(SIGNS)))
def test_an_amount_is_found_exactly_when_its_sign_agrees(parts: tuple[str, str, str], quote_sign: str, text_sign: str) -> None:
    """Over currency, digits, magnitude and every way a sign is written: the quote "a credit of <amount>" is found in
    the text "<...> a credit of <amount> applies" when, and only when, the two signs have one value. False acceptance
    and false rejection are both failures. Where found, the highlight is the text's own amount, sign included."""
    quote = f"a credit of {write(quote_sign, parts)}"
    text = f"The parties agree a credit of {write(text_sign, parts)} applies."
    located = locate(quote, text)
    same_sign = SIGNS[quote_sign] == SIGNS[text_sign]
    assert (located is not None) == same_sign, (quote, text, located)
    if located is not None:
        assert text[located.start : located.end].endswith(write(text_sign, parts)), (quote, text, located)


@settings(max_examples=600 * FUZZ_SCALE, deadline=None)
@given(parts=amount(), sign=st.sampled_from(["-", "−", "("]), data=st.data())
def test_no_span_begins_or_ends_inside_a_signed_amount(parts: tuple[str, str, str], sign: str, data: st.DataObject) -> None:
    """No piece of a signed amount, cut anywhere but at its own ends, is a bounded span: the sign cannot be left out."""
    written = write(sign, parts)
    text = f"a credit of {written} applies"
    low = text.index(written)
    high = low + len(written)
    start = data.draw(st.integers(low + 1, high - 1)) if high - low > 1 else low
    assert not bounded(text, start, high), (text, start, high)


def _checker(folder: Path) -> types.ModuleType:
    module = types.ModuleType("pack_verify")
    module.__dict__["__file__"] = str(folder / "verify.py")
    exec(compile(render_verify_py(), "verify.py", "exec"), module.__dict__)
    return module


AMOUNTISH = st.text(alphabet="0123456789,.%$€₹()-−– USDINRKMbnk‎​", min_size=1, max_size=24)


@settings(max_examples=500 * FUZZ_SCALE, deadline=None)
@given(text=AMOUNTISH, data=st.data())
def test_the_pack_reads_every_edge_of_an_amount_as_the_workbench_does(tmp_path_factory: pytest.TempPathFactory, text: str, data: st.DataObject) -> None:
    checker = _checker(tmp_path_factory.mktemp("edges-v9"))
    start = data.draw(st.integers(0, len(text)))
    end = data.draw(st.integers(start, len(text)))
    # The runtime reads at its own version (v10 since 2026-10-14: "-D0" is a signed number there, not under v9). That the
    # pack still reads a v9 run as v9 did is pinned by the v9 pattern's hash (test_post_pilot_repair.py).
    assert checker.edges_hold(text, start, end, tokens.VERSION) == bounded(text, start, end), (text, start, end)


@settings(max_examples=500 * FUZZ_SCALE, deadline=None)
@given(a=AMOUNTISH, b=AMOUNTISH)
def test_the_pack_compares_amounts_as_the_workbench_does(tmp_path_factory: pytest.TempPathFactory, a: str, b: str) -> None:
    checker = _checker(tmp_path_factory.mktemp("typed-v9"))

    # The runtime as the verifier calls it (tokens.locate_tokens): invisible marks read as absent, at its own version, as
    # the sibling test above reads the edges. Without them this compared a reading no run makes: "-​0" read as 0, and
    # the pack (rightly) as -0 (found by a random draw in the acceptance test's suite run, 2026-10-14).
    def runtime(text: str) -> list[tuple[str, str]]:
        return [(str(t.kind), t.canonical) for t in tokens.significant(tokens.signed(text, tokens.tokenize(text), invisible=INVISIBLE))]

    expected = bool(runtime(a)) and runtime(a) == runtime(b)
    assert checker.same(a, b, "typed", tokens.VERSION) == expected, (a, b)


# The second review: a shortcut that skipped any edge with no digit in the next 16 characters let "-15" stand alone in
# "-15 percent" (the pack refused it), made the verdict depend on what followed the number, and let invisible marks
# between a currency and its digits carry a cut past it. Each edge is now read against the numbers themselves.
EDGE_CASES = [
    pytest.param("a fee of -15", "a fee of -15 percent of the fee.", id="review2-signed-percent-word"),
    pytest.param("a fee of -15", "a fee of -15 percent of 2024 fees.", id="review2-a-digit-after-changes-nothing"),
    pytest.param("‎" * 16 + " 5M is due", "Amount -USD" + "‎" * 16 + " 5M is due", id="review2-invisible-marks-after-the-code"),
]


@pytest.mark.parametrize(("quote", "text"), EDGE_CASES)
def test_a_cut_inside_a_signed_number_is_refused_and_the_pack_agrees(tmp_path: Path, quote: str, text: str) -> None:
    assert locate(quote, text) is None
    start = text.index(quote) if quote in text else 0
    end = start + len(quote)
    checker = _checker(tmp_path)
    assert not bounded(text, start, end)
    assert checker.edges_hold(text, start, end, 9) is False


# ---------------------------------------------------------------------------------------------------- packs


def _pack(folder: Path, text: str, start: int, end: int, quote: str, method: str, verifier: str) -> Path:
    folder.mkdir(parents=True)
    sections = [{"id": "s1", "ordinal": 0, "number": "2", "heading": "PURCHASE PRICE", "text": text}]
    sections_json = json.dumps(sections, ensure_ascii=False, indent=1)
    (folder / "sections.json").write_text(sections_json, encoding="utf-8", newline="\n")
    run = {
        "document": {"file": None, "sha256": "x"},
        "sections_sha256": sha256_bytes(sections_json.encode("utf-8")),
        "prompt_version": "answer-v2",
        "prompt_hash": "",
        "options": {"verifier_version": verifier},
        "verifier": {"window_chars": 6000},
    }
    (folder / "run.json").write_text(json.dumps(run), encoding="utf-8")
    span = {"ordinal": 0, "section_id": "s1", "start": start, "end": end, "quote": quote, "verified": True, "method": method}
    (folder / "findings.json").write_text(json.dumps([{"ordinal": 0, "spans": [span]}]), encoding="utf-8")
    (folder / "verify.py").write_text(render_verify_py(), encoding="utf-8")
    return folder


def _passes(folder: Path) -> bool:
    done = subprocess.run([sys.executable, "verify.py"], cwd=folder, capture_output=True, text=True, check=False)
    assert ("PASS finding 1 span 1" in done.stdout) != ("FAIL finding 1 span 1" in done.stdout), done.stdout
    return done.returncode == 0


def test_the_b1_record_fails_a_v9_pack_and_its_historical_v8_pack_keeps_its_verdict(tmp_path: Path) -> None:
    """The record v8 made of the evaluation's case (typed, offsets on "Adjustment Amount -$5M"): a pack of a v8 run
    still says what v8 said, and the same record claimed for a v9 run fails, as the workbench refuses it."""
    start = SOURCE.index("Adjustment Amount -$5M")
    end = start + len("Adjustment Amount -$5M")
    quote = "Adjustment Amount $5M"
    assert _passes(_pack(tmp_path / "v8", SOURCE, start, end, quote, "typed", "v8")), "a v8 pack keeps v8's verdict"
    assert not _passes(_pack(tmp_path / "v9", SOURCE, start, end, quote, "typed", "v9"))


def test_control_a_genuine_v9_span_passes_its_pack(tmp_path: Path) -> None:
    located = locate("Adjustment Amount -$5M", SOURCE)
    assert located is not None
    assert _passes(_pack(tmp_path / "ok", SOURCE, located.start, located.end, "Adjustment Amount -$5M", located.method, "v9"))
    typed = locate("a fee of $ 5M", "a fee of $5M applies")
    assert typed is not None and typed.method == "typed"
    assert _passes(_pack(tmp_path / "typed", "a fee of $5M applies", typed.start, typed.end, "a fee of $ 5M", "typed", "v9"))


# ---------------------------------------------------------------------------------------------------- the whole run

CONTRACT = "PURCHASE AGREEMENT\n\n2. Purchase Price\n\nThe Purchase Price is the Base Price plus the Adjustment Amount.\n\nAdjustment Amount -$5M\n"


class AmountProvider(FakeProvider):
    """Answers the purchase-price question quoting the amount as ``quote`` (the evaluation's S13 answer by default)."""

    def __init__(self, quote: str) -> None:
        super().__init__()
        self.quote = quote

    def generate_json(self, system: str, user: str, schema: dict[str, object]) -> Generation:
        label = next(part.split("]")[0] for part in user.split("[") if part.startswith("sec_") and "Purchase Price" in part.split("\n")[0])
        payload = {
            "findings": [
                {
                    "topic": "Adjustment Amount",
                    "conclusion": "The Adjustment Amount is $5M, which is added to the Base Price.",
                    "status_hint": "pass",
                    "evidence": [{"section_id": label, "quote": self.quote}],
                    "guidance_reference": None,
                    "observed": None,
                    "required": None,
                    "suggested_position": None,
                }
            ],
            "insufficient_evidence": False,
            "note": None,
        }
        return Generation(text=json.dumps(payload), input_tokens=100, output_tokens=50, latency_ms=12.5, model=self.model)


def _ask(client: TestClient, quote: str) -> dict[str, Any]:
    client.app.state.provider = AmountProvider(quote)  # type: ignore[attr-defined]
    document = client.post("/api/documents", files={"file": ("apa.txt", CONTRACT.encode("utf-8"), "text/plain")}).json()
    started = client.post("/api/runs", json={"documentId": document["id"], "question": "What is the Adjustment Amount?"})
    assert started.status_code == 202, started.text
    detail: dict[str, Any] = client.get(f"/api/runs/{started.json()['id']}/detail").json()
    return detail


def test_the_b1_answer_is_withheld_from_the_run_the_memo_and_the_pack(client: TestClient, tmp_path: Path) -> None:
    detail = _ask(client, "Adjustment Amount $5M")
    spans = [s for f in detail["findings"] + detail["withheld"] for s in f["spans"]]
    assert spans and not any(s["verified"] for s in spans), "the sign-dropped quote is not verified"
    assert detail["stage"] == "unresolved" and detail["reason"] == "citations_unverified"
    assert client.post("/api/memos", json={"runId": detail["id"]}).status_code == 409, "no memo prints it as observed language"
    pack = client.get(f"/api/runs/{detail['id']}/evidence-pack")
    assert pack.status_code == 200
    import io
    import zipfile

    with zipfile.ZipFile(io.BytesIO(pack.content)) as archive:
        archive.extractall(tmp_path / "pack")
    done = subprocess.run([sys.executable, "verify.py"], cwd=tmp_path / "pack", capture_output=True, text=True, check=False)
    assert done.returncode == 0 and "0 located span(s) checked, 1 withheld" in done.stdout, done.stdout


def test_control_the_quote_as_written_is_verified_end_to_end(client: TestClient) -> None:
    detail = _ask(client, "Adjustment Amount -$5M")
    spans = [s for f in detail["findings"] for s in f["spans"]]
    assert detail["stage"] == "complete" and spans and all(s["verified"] and s["method"] == "exact" for s in spans)
