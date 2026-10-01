"""The alias table is data: deterministic, versioned by its hash, on by default since its measurement (docs/RETRIEVAL.md), recorded on a run only when on."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app import config
from app.retrieval.aliases import ALIAS_GROUPS, ALIASES_SHA256, expand_query
from app.retrieval.lexical import LexicalIndex
from tests.support import upload_and_ask


def test_a_query_naming_no_concept_is_unchanged() -> None:
    assert expand_query("What is the effective date?") == "What is the effective date?"
    assert expand_query("") == ""


def test_a_query_naming_a_concept_gains_its_other_phrases_once_in_table_order() -> None:
    expanded = expand_query("Does this agreement restrict either party from competing with the other?")
    assert expanded.startswith("Does this agreement restrict either party from competing with the other? ")
    extra = expanded.split("? ", 1)[1].split()
    assert "compete" in extra and "restrictive" in extra and "covenant" in extra and "solicit" in extra
    assert "competing" not in extra, "a token already in the query is not repeated"
    assert len(extra) == len(set(extra)), "every added token appears once"
    assert expand_query(expanded) == expanded, "expanding twice adds nothing"


def test_the_table_hash_names_its_contents() -> None:
    assert len(ALIASES_SHA256) == 64
    assert all(len(group) >= 3 for group in ALIAS_GROUPS)


def test_aliases_let_bm25_reach_a_clause_that_shares_no_word_with_the_question() -> None:
    sections = [
        ("Definitions", "Capitalised terms have the meanings given in Schedule 1."),
        (
            "Restrictive Covenants",
            "During the Term the Reseller shall not, directly or indirectly, engage in any business that is in restraint of trade with the Supplier.",
        ),
        ("Fees", "The Reseller pays the Fees within thirty days of invoice."),
    ]
    index = LexicalIndex(sections)
    question = "Is there a non-compete?"
    assert [c.index for c in index.search(question, 3)] == [], "the plain question shares no token with the clause"
    assert next(c.index for c in index.search(expand_query(question), 3)) == 1


def test_the_option_is_recorded_only_when_the_table_is_on(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    assert config.settings.retrieval_aliases is True, "the measured default"
    on = upload_and_ask(client, "Is there a non-compete clause in this agreement?", with_guidance=False)
    options = client.get(f"/api/runs/{on['run_id']}/detail").json()["options"]
    assert options["retrieval_aliases"] == ALIASES_SHA256[:12]
    monkeypatch.setattr(config.settings, "retrieval_aliases", False)
    off = upload_and_ask(client, "What law governs this agreement?", with_guidance=False)
    assert "retrieval_aliases" not in client.get(f"/api/runs/{off['run_id']}/detail").json()["options"], (
        "a run without the table keeps the fingerprint every old run has"
    )
