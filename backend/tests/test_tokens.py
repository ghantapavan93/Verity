"""Typed tokens keep the meaning of numbers while forgiving punctuation, and a match is a whole number of tokens."""

from __future__ import annotations

import pytest

from app.verify.tokens import Kind, canonical_number, locate_tokens, significant, tokenize


def kinds(text: str) -> list[tuple[str, str]]:
    return [(t.kind.value, t.canonical) for t in significant(tokenize(text))]


def test_numbers_keep_their_value_and_lose_their_spelling() -> None:
    assert canonical_number("1,500") == "1500" and canonical_number("15.00") == "15.00" and canonical_number("1.50") == "1.50"
    assert kinds("$1,500") == [("currency", "$1500")]
    assert kinds("$15.00") == [("currency", "$15.00")]
    assert kinds("USD 10.50") == [("currency", "USD10.50")]
    assert kinds("15%") == [("percent", "15%")] and kinds("1.5 percent") == [("percent", "1.5%")]
    assert kinds("30 days") == [("number", "30"), ("word", "days")]
    assert kinds("8.1.2 Liability Caps") == [("section", "8.1.2"), ("word", "liability"), ("word", "caps")]
    assert kinds("Section 12.4(a)") == [("word", "section"), ("section", "12.4(a)")]


def test_punctuation_quotes_and_dashes_carry_no_meaning() -> None:
    assert kinds("days’ written notice") == kinds("days written notice")
    assert kinds("non- exclusive, non-transferable") == kinds("non-exclusive non-transferable")
    assert kinds("“GDPR” means") == kinds("GDPR means")


@pytest.mark.parametrize(
    ("quote", "text"),
    [
        ("$15.00 per user", "The fee of $1,500 per user is payable annually."),
        ("15% per annum", "Interest accrues at 1.5% per annum."),
        ("a cap of 2.0 times the fees", "A cap of 20 times the fees applies."),
        ("30 days", "Payment is due within 130 days."),
        ("ice cream", "Notice cream is served."),  # a word may not start inside another word
        ("able to terminate", "The Provider is unable to terminate."),
        ("$1,500", "The fee is $11,500 per year."),
    ],
)
def test_a_changed_value_or_a_split_word_never_matches(quote: str, text: str) -> None:
    assert locate_tokens(quote, text) is None


def test_the_same_value_written_differently_matches_and_reports_where() -> None:
    text = "The fee of “$1,500” per user is payable within thirty (30) days."
    found = locate_tokens("fee of $1500 per user", text)
    assert found is not None and text[found.start : found.end] == "fee of “$1,500” per user" and found.count == 1
    found = locate_tokens("within thirty (30) days", "Notice: within thirty (30) days.")
    assert found is not None and found.count == 1
    found = locate_tokens("fifteen (1 5) days", "upon fifteen (15) days’ notice")
    assert found is None, "a number split in two is two numbers"


def test_match_count_says_whether_the_location_is_unambiguous() -> None:
    text = "The receiving party shall keep it confidential. The receiving party shall keep it confidential. Always."
    found = locate_tokens("receiving party shall keep it confidential", text)
    assert found is not None and found.count == 2 and text[found.start : found.end] == "receiving party shall keep it confidential"
    assert locate_tokens("Always", text) is not None and locate_tokens("Always", text).count == 1  # type: ignore[union-attr]


def test_empty_or_punctuation_only_quotes_match_nothing() -> None:
    assert locate_tokens("", "some text") is None and locate_tokens("… — ,", "some text") is None
    assert tokenize("")[0:0] == [] and [t.kind for t in tokenize("—")] == [Kind.PUNCT]


def test_words_joined_or_split_by_the_reader_are_forgiven_at_word_boundaries_and_numbers_never_are() -> None:
    # Four recorded spans on 2026-09-29 were lost only because the reader's text carried "advisedof", "thesame", "speci fying".
    text = "has been advisedof the possibility of such damages"
    found = locate_tokens("has been advised of the possibility", text)
    assert found is not None and text[found.start : found.end] == "has been advisedof the possibility"
    text = "notice to the defaulting party speci fying the default"
    found = locate_tokens("party specifying the default", text)
    assert found is not None and text[found.start : found.end] == "party speci fying the default"
    assert locate_tokens("not ice", "Notice must be in writing.") is not None, "letters at word boundaries; the space is the reader's"
    assert locate_tokens("1 5 days", "within 15 days") is None and locate_tokens("15 days", "within 1 5 days") is None
