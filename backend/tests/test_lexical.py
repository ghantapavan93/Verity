"""retrieval-v3, the tokenizer and the cut (stress test, 2026-10-30, retrieval corner findings 3 and 5).

Two invariants of what BM25 hands over. Text the verifier treats as one is one text to retrieval: the same question typed
with a straight apostrophe (a desktop keyboard) or a curly one (iOS smart punctuation, a Word paste) hands the same
sections, and a possessive is its word ("party's" is "party"). And when fewer than k sections are handed, none that
shares a word with the question is left out: BM25Okapi gives a word in exactly half the sections an IDF of 0, and the
score > 0 cut dropped the section that held the answer while places were free (CUAD's Minkang outsourcing agreement:
one of four sections handed, the governing-law part not).
"""

from __future__ import annotations

from dataclasses import dataclass

from hypothesis import given, settings
from hypothesis import strategies as st

from app.retrieval.lexical import tokenize, words
from app.runs.service import FrozenOptions, _retrieve
from app.verify.spans import _QUOTE_MAP

APOSTROPHES = ["’", "‘", "‚", "‛", "ʼ", "＇", "`", "´"]
FROZEN = FrozenOptions(retrieval_k=6, retriever="bm25", aliases=True, embed_model="", window=6000, decoding={})

# Letters, digits, every apostrophe and quotation glyph, dashes, ligatures and the characters casefold changes.
_ALPHABET = st.sampled_from(list("abcdeABCDE sS19'.-") + APOSTROPHES + ["“", "”", "–", "ﬁ", "ß", "İ", "​"])


@dataclass
class S:
    number: str
    heading: str
    text: str
    id: str = ""

    def __post_init__(self) -> None:
        self.id = self.id or f"{self.number}:{self.heading}"


@settings(max_examples=400, deadline=None)
@given(st.text(_ALPHABET, max_size=40))
def test_text_the_verifier_reads_as_one_is_one_token_stream(text: str) -> None:
    assert tokenize(text) == tokenize(text.translate(_QUOTE_MAP)), "the verifier's normalized tier folds these glyphs"
    assert tokenize(text) == tokenize(text.casefold()), "the verifier's casefold tier compares caseless"


@settings(max_examples=200, deadline=None)
@given(st.from_regex(r"[A-Za-z][a-z]{1,10}", fullmatch=True), st.sampled_from(["'", *APOSTROPHES]))
def test_a_possessive_is_its_word_whatever_the_apostrophe(word: str, mark: str) -> None:
    assert tokenize(f"each {word}{mark}s liability") == tokenize(f"each {word} liability")
    assert "s" not in tokenize(f"{word}{mark}s"), "no lone 's' that matches 'U.S.' or 'Product(s)'"


def test_the_glyphs_the_stress_test_named() -> None:
    assert tokenize("Which state's law governs this contract?") == ["state", "law", "governs", "contract"]
    assert tokenize("Which state’s law governs this contract?") == ["state", "law", "governs", "contract"]
    assert tokenize("conﬁdential") == ["confidential"], "a PDF ligature is the letters it stands for, as casefold reads it"


def test_control_words_without_an_apostrophe_are_unchanged() -> None:
    assert tokenize("What is the notice period, 15 days? Section 12.3") == ["notice", "period", "15", "days", "section", "12", "3"]
    assert tokenize("can't") == tokenize("can’t") == ["can't"], "a contraction stays one word"
    assert tokenize("the Parties' rights") == ["parties", "rights"]
    assert words("at any time") == ["at", "any", "time"] and tokenize("at any time") == ["time"], "words() keeps the stopwords"


def _contract(apostrophe: str) -> list[S]:
    """Twelve sections; the liability clause holds the possessive, two others the words a lone 's' meets."""
    a = apostrophe
    return [
        S("1", "Definitions", f"Product(s) means the goods. Each party{a}s Affiliates are bound."),
        S("2", "Payment", "All amounts are payable in U.S. dollars within thirty days."),
        S("3", "Limitation of Liability", f"Each Party{a}s aggregate liability shall not exceed the fees paid in the prior year."),
        S("4", "Shipping", "Products are shipped from the U.S. warehouse."),
        *[S(str(n), f"Miscellaneous {n}", f"Administrative matter number {n} for each party.") for n in range(5, 13)],
    ]


def test_the_same_question_typed_on_a_desktop_or_a_phone_hands_the_same_sections() -> None:
    for contract in ("'", "’"):
        sections = _contract(contract)
        handed = {
            glyph: [s.id for s in _retrieve(sections, f"What is the cap on each party{glyph}s liability?", None, FROZEN)[0]]  # type: ignore[arg-type]
            for glyph in ("'", *APOSTROPHES)
        }
        assert len({tuple(v) for v in handed.values()}) == 1, handed
        dropped = [s.id for s in _retrieve(sections, "What is the cap on each party liability?", None, FROZEN)[0]]  # type: ignore[arg-type]
        assert handed["'"] == dropped and handed["'"][0] == "3:Limitation of Liability"
