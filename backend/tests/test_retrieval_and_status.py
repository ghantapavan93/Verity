from app.retrieval.lexical import LexicalIndex, tokenize
from app.runs.status import days_in, decide

SECTIONS = [
    ("Master Services Agreement", "This Agreement is entered into between Acme and Northwind."),
    ("Fees and Payment", "Fees are due within thirty (30) days of the invoice date."),
    ("Termination for Convenience", "Customer may terminate this Agreement for convenience upon fifteen (15) days' written notice to Provider."),
    ("Governing Law", "This Agreement is governed by the laws of Delaware."),
]


def test_tokenize_drops_stopwords_and_keeps_numbers() -> None:
    assert tokenize("What is the notice period, 15 days?") == ["notice", "period", "15", "days"]


def test_termination_question_ranks_the_termination_clause_first() -> None:
    index = LexicalIndex(SECTIONS)
    top = index.search("How much notice does the customer need to terminate for convenience?", k=3)
    assert top and top[0].index == 2


def test_no_overlap_returns_nothing() -> None:
    assert LexicalIndex(SECTIONS).search("zzzz qqqq", k=3) == []


def test_days_parsing() -> None:
    assert days_in("fifteen (15) days' written notice") == 15
    assert days_in("at least 30 days") == 30
    assert days_in("thirty days") == 30
    assert days_in("immediately") is None


def test_status_is_computed_from_days_when_both_sides_have_them() -> None:
    assert decide("pass", "15 days", "at least 30 days", True, True).status == "needs_review"
    assert decide("needs_review", "45 days", "at least 30 days", True, True).status == "pass"
    assert decide("pass", "60 days", "no more than 30 days", True, True).status == "needs_review"
    assert decide("pass", "15 days", "at least 30 days", True, True).source == "computed_days"


def test_status_falls_back_to_the_hint_and_never_trusts_unverified_evidence() -> None:
    assert decide("needs_review", "quarterly", "monthly", True, True) == decide("needs_review", None, None, True, True)
    assert decide("pass", None, None, False, True).status == "pass"
    assert decide("pass", "15 days", "at least 30 days", True, False).status == "unresolved"
