"""The alias table is data: deterministic, versioned by its hash, on by default since its measurement (docs/RETRIEVAL.md), recorded on a run only when on."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app import config
from app.retrieval.aliases import ALIAS_GROUPS, ALIASES_SHA256, WORDING, expand_query
from app.retrieval.lexical import LexicalIndex, tokenize
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


# retrieval-v3 (stress test 2026-10-30, retrieval corner, finding 4): a group fires only on a phrase that names its concept.
# Contract wording the table adds ("at any time", "for any reason", "not limited") collapsed, once stopwords were removed,
# to one generic word or to boilerplate ("time", "reason"; "including but not limited to"), so an insurance question
# with "how much time" was handed the termination clauses and not the insurance clause (CUAD-510: 0.976 to 0.928).

NAMING = {
    "What law governs this agreement and where must disputes be brought?": "jurisdiction",
    "May either party terminate this agreement for convenience, without cause, and on what notice?": "reason",
    "Which liabilities are excluded from the cap or left uncapped?": "negligence",
    "Does this agreement restrict either party from competing with the other, and how?": "restrictive",
    "What happens to this agreement if a party undergoes a change of control?": "merger",
    "Is there a most favoured nation clause?": "favorable",
    "What happens if a party is acquired or merges with another company?": "merger",
}
NOT_NAMING = [
    "How much time does a party have to obtain the required insurance?",
    "Within what time must the vendor provide certificates of insurance?",
    "Can a party audit the other's records at any time?",
    "For what reason may a party withhold its consent?",
    "Is there a minimum quantity a party must purchase in each period of time?",
    "How many days' notice must the Supplier give before a price change?",
    "Is the appointment exclusive? Exclusivity covers the products, including but not limited to the initial Products.",
    "Does the indemnity apply? Notwithstanding the foregoing, the warranty shall not apply to misuse.",
    "Are payments due on prior written notice? The fees shall not exceed the budget.",
]


def test_a_question_naming_a_concept_still_gains_its_phrases() -> None:
    for question, added in NAMING.items():
        assert added in expand_query(question).removeprefix(question).split(), question


def test_contract_wording_in_a_question_or_its_guidance_fires_no_group() -> None:
    for question in NOT_NAMING:
        assert expand_query(question) == question


def test_every_wording_phrase_is_in_a_group_and_none_fires() -> None:
    assert WORDING.issubset(phrase for group in ALIAS_GROUPS for phrase in group), "wording is part of a group, added on expansion"
    for phrase in WORDING:
        assert expand_query(f"Is there anything about {phrase} here?") == f"Is there anything about {phrase} here?"
    assert all(set(group) - WORDING for group in ALIAS_GROUPS), "every group keeps a phrase that names it"


def test_every_name_fires_its_group_and_its_wording_joins() -> None:
    for group in ALIAS_GROUPS:
        wording = {token for phrase in group if phrase in WORDING for token in tokenize(phrase)}
        for name in (p for p in group if p not in WORDING):
            assert wording <= set(tokenize(expand_query(f"Tell me about {name}."))), name


def test_a_question_that_names_no_concept_is_handed_the_same_sections_with_the_table_on_or_off() -> None:
    from app.runs.service import FrozenOptions, _retrieve
    from tests.test_retrieval_links import FILLER, S

    sections = [
        S("3", "Insurance", "The Vendor shall obtain the insurance below within thirty days of the Effective Date."),
        S("7", "Termination", "Either party may terminate at any time for any reason on thirty days' prior written notice."),
        S("9", "Force Majeure", "Neither party is liable for delay caused by events beyond its control, for the time they last."),
        *FILLER,
    ]
    on, off = (FrozenOptions(retrieval_k=6, retriever="bm25", aliases=a, embed_model="", window=6000, decoding={}) for a in (True, False))
    for question in NOT_NAMING[:3]:
        assert _retrieve(sections, question, None, on)[0] == _retrieve(sections, question, None, off)[0], question  # type: ignore[arg-type]
