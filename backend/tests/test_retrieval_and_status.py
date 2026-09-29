from app.retrieval.hybrid import HybridIndex, fuse
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


def fake_embed(texts: list[str]) -> list[list[float]]:
    """A toy embedding: counts of a few topic words, so similarity follows meaning words, not exact tokens."""
    words = ("terminate", "convenience", "notice", "liability", "cap", "damages", "governing", "law")
    return [[float(t.lower().count(w)) for w in words] for t in texts]


def test_reciprocal_rank_fusion_prefers_what_both_rankings_like() -> None:
    assert fuse([[0, 1, 2], [1, 0, 2]], 3) == [0, 1, 2]
    assert fuse([[2, 0], [2, 1]], 1) == [2]
    assert fuse([[0, 1], []], 2) == [0, 1]


def test_hybrid_index_fuses_lexical_and_embedding_rankings() -> None:
    sections = [
        ("Fees", "Customer pays the fees within thirty days of invoice."),
        ("Ending the agreement", "Either party may end this agreement for convenience on ninety days notice."),
        ("Liability", "Neither party is liable for indirect damages; the cap is the fees paid in twelve months."),
    ]
    index = HybridIndex(sections, embed=fake_embed)
    top = index.search("How may a party terminate for convenience?", 2)
    assert top[0].index == 1
    assert index.search("anything", 3) != [] and HybridIndex([], embed=fake_embed).search("x", 3) == []


def test_run_identity_carries_the_retriever_only_when_it_is_not_the_default(monkeypatch: object) -> None:
    from app import config
    from app.application.start_run import run_options

    assert "retrieval" not in run_options()
    import pytest

    mp = monkeypatch if isinstance(monkeypatch, pytest.MonkeyPatch) else None
    assert mp is not None
    mp.setattr(config.settings, "retrieval", "hybrid")
    assert run_options()["retrieval"] == "hybrid" and run_options()["embed_model"] == config.settings.embed_model
