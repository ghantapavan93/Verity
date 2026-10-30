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

from app.retrieval.lexical import STOPWORDS, LexicalIndex, tokenize, words
from app.runs.service import FrozenOptions, _retrieve
from app.verify.spans import _QUOTE_MAP

APOSTROPHES = ["\u2019", "\u2018", "\u201a", "\u201b", "\u02bc", "\uff07", "`", "\u00b4"]
FROZEN = FrozenOptions(retrieval_k=6, retriever="bm25", aliases=True, embed_model="", window=6000, decoding={})

# Letters, digits, every apostrophe and quotation glyph, dashes, ligatures and the characters casefold changes.
_ALPHABET = st.sampled_from(list("abcdeABCDE sS19'.-") + APOSTROPHES + ["\u201c", "\u201d", "\u2013", "\ufb01", "\u00df", "\u0130", "\u200b"])


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
    assert tokenize("Which state\u2019s law governs this contract?") == ["state", "law", "governs", "contract"]
    assert tokenize("con\ufb01dential") == ["confidential"], "a PDF ligature is the letters it stands for, as casefold reads it"


def test_control_words_without_an_apostrophe_are_unchanged() -> None:
    assert tokenize("What is the notice period, 15 days? Section 12.3") == ["notice", "period", "15", "days", "section", "12", "3"]
    assert tokenize("can't") == tokenize("can\u2019t") == ["can't"], "a contraction stays one word"
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
    for contract in ("'", "\u2019"):
        sections = _contract(contract)
        handed = {
            glyph: [s.id for s in _retrieve(sections, f"What is the cap on each party{glyph}s liability?", None, FROZEN)[0]]  # type: ignore[arg-type]
            for glyph in ("'", *APOSTROPHES)
        }
        assert len({tuple(v) for v in handed.values()}) == 1, handed
        dropped = [s.id for s in _retrieve(sections, "What is the cap on each party liability?", None, FROZEN)[0]]  # type: ignore[arg-type]
        assert handed["'"] == dropped and handed["'"][0] == "3:Limitation of Liability"


# --------------------------------------------------------------------------------------------------- the cut (finding 5)

FOUR = [
    S("1", "Supply", "The Seller shall supply the Products at the prices in the price list."),
    S("2", "Warranty", "The Seller warrants that the Products comply with applicable law."),
    S("3", "Term", "This Agreement has a term of two years."),
    S("4", "Compliance", "Each party shall comply with every law that applies to its business."),
    S("5", "Governing Law", "This Agreement is governed by the law of the State of New York."),
    S("6", "Notices", "Notices are given in writing to the addresses above."),
]


def test_a_section_holding_the_question_word_is_handed_while_places_are_free() -> None:
    index = LexicalIndex([(s.heading, s.text) for s in FOUR])
    found = index.search("Which law applies to the prices?", 6)
    # "law" is in three of six sections: BM25Okapi's IDF for it is exactly 0, and Governing Law scored 0.0.
    assert {c.index for c in found} == {0, 1, 3, 4}, found
    assert {c.index for c in found[:2]} == {0, 3} and all(c.score > 0 for c in found[:2]), "the sections scored above zero come first"
    assert [c.index for c in found[2:]] == [1, 4], "then those weighted zero, in document order"
    chosen, mode, _ = _retrieve(FOUR, "Which law applies to the prices?", None, FROZEN)  # type: ignore[arg-type]
    assert mode == "lexical_match" and "5:Governing Law" in [s.id for s in chosen]


def test_control_a_question_that_shares_no_word_still_gets_the_opening_sections() -> None:
    chosen, mode, why = _retrieve(FOUR, "zzzz qqqq", None, FROZEN)  # type: ignore[arg-type]
    assert mode == "opening_fallback" and chosen == FOUR and why == {}
    assert LexicalIndex([(s.heading, s.text) for s in FOUR]).search("zzzz qqqq", 6) == []


def test_control_two_sections_that_both_hold_the_question_word_are_both_ranked() -> None:
    """The known two-section item (docs/STATUS.md): BM25 scores both at or below zero; both share the words, so both
    are candidates for the question, not opening sections handed for want of a match."""
    two = [S("1", "Term", "The term is one year from the date of signature."), S("2", "Law", "The law of Ohio applies to the term.")]
    chosen, mode, _ = _retrieve(two, "What is the term?", None, FROZEN)  # type: ignore[arg-type]
    assert mode == "lexical_match" and len(chosen) == 2


def test_control_sections_that_hold_no_word_rank_nothing_and_raise_nothing() -> None:
    assert LexicalIndex([("", "the of"), ("", "")]).search("the law", 3) == []


_VOCAB = ["law", "price", "term", "notice", "party", "fee", "cap", "the", "of"]


@settings(max_examples=300, deadline=None)
@given(
    st.lists(st.lists(st.sampled_from(_VOCAB), max_size=8), min_size=1, max_size=9),
    st.lists(st.sampled_from(_VOCAB), min_size=1, max_size=4),
    st.integers(min_value=1, max_value=7),
)
def test_every_section_sharing_a_word_is_ranked_while_places_remain(texts: list[list[str]], query: list[str], k: int) -> None:
    index = LexicalIndex([("", " ".join(t)) for t in texts])
    found = [c.index for c in index.search(" ".join(query), k)]
    asked = set(query) - STOPWORDS
    sharing = [i for i, t in enumerate(texts) if asked & set(t)]
    if len(sharing) <= k:
        assert set(found) == set(sharing)
    else:
        assert len(found) == k
    assert all(asked & set(texts[i]) for i in found), "a section sharing no word is never ranked"
    if sharing:
        # What the score > 0 cut handed (retrieval-v2) is the head of what is handed now, in the same order.
        assert index._bm25 is not None
        scores = index._bm25.get_scores(tokenize(" ".join(query)))
        before = [i for i in sorted(range(len(texts)), key=lambda i: (-scores[i], i))[:k] if scores[i] > 0]
        assert found[: len(before)] == before
