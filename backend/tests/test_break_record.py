"""The record /break tells is the recording, checked again by the product's own code.

src/components/break/break-record.json is written by scripts/export_break_record.py from recorded stores through the
API's projections. These tests do not trust the exporter: every quote is located again by the verifier in the section
text the record carries, the policy-v6 value rule is run again over every finding the page shows, and the numbers the
page states about the rejected party check are counted again from the per-finding verdicts.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path

import pytest

from app.runs.status import Decision, check_values
from app.verify.spans import locate

RECORD = Path(__file__).resolve().parents[2] / "src" / "components" / "break" / "break-record.json"


@pytest.fixture(scope="module")
def record() -> dict:
    return json.loads(RECORD.read_text(encoding="utf-8"))


def shown_cases(record: dict) -> list[dict]:
    return [record["headline"], record["counterexample"]["caught"], record["counterexample"]["falseAlarm"]]


def test_the_headline_passed_with_a_verified_quote_and_was_adjudicated_wrong_party_in_both_sessions(record: dict) -> None:
    headline = record["headline"]
    assert len(headline["sessions"]) == 2
    for session in headline["sessions"]:
        assert session["finding"]["status"] == "pass"
        assert session["finding"]["spans"] and all(span["verified"] for span in session["finding"]["spans"])
        assert session["adjudication"]["label"] == "wrong_party"
    # Two model sessions, one input: the same rebuilt input hash, and the same answer.
    assert len({s["recordedInputSha256"] for s in headline["sessions"]}) == 1
    assert len({s["finding"]["conclusion"] for s in headline["sessions"]}) == 1


def test_every_quote_is_found_again_where_the_record_says(record: dict) -> None:
    for case in shown_cases(record):
        for session in case["sessions"]:
            for span in session["finding"]["spans"]:
                text = case["sections"][span["sectionId"]]["text"]
                found = locate(span["quote"], text)
                assert found is not None, (case["id"], session["session"], span["quote"][:60])
                assert (found.start, found.end) == (span["start"], span["end"])


def test_the_published_input_carries_every_section_the_model_was_handed(record: dict) -> None:
    for case in shown_cases(record):
        for session in case["sessions"]:
            for slice_ in session["retrieval"]:
                text = case["sections"][slice_["sectionId"]]["text"][slice_["sliceStart"] : slice_["sliceEnd"]]
                assert text in case["input"]["user"], (case["id"], slice_["label"])
        assert case["input"]["sha256"] == case["sessions"][0]["recordedInputSha256"]


def test_each_document_is_the_one_its_source_names(record: dict) -> None:
    for case in shown_cases(record):
        assert case["source"]["url"].startswith("https://www.sec.gov/Archives/edgar/data/")
        assert re.fullmatch(r"[0-9a-f]{64}", case["source"]["sha256Filing"])
        for session in case["sessions"]:
            assert session["documentSha256"] == case["source"]["sha256Tested"]


def test_policy_v6_decides_each_shown_finding_as_recorded(record: dict) -> None:
    # The runs were recorded under policy-v7, which is policy-v6 plus the party check as its last step. Where the party
    # check did not fire, the recorded decision is v6's; the value rule is run again here to say so.
    fired = {r["finding"] for r in record["rejectedFix"]["rows"] if r["flagged"]}
    for case in shown_cases(record):
        for session in case["sessions"]:
            finding = session["finding"]
            assert finding["id"] not in fired
            quotes = [s["quote"] for s in finding["spans"] if s["verified"]]
            again = check_values(Decision("pass", "model_hint"), finding["conclusion"], quotes, case["question"], None)
            assert (again.status, again.reason or None) == (finding["status"], finding["statusReason"]), (case["id"], session["session"])


def test_the_false_alarm_and_the_kept_pass_open_alike_and_only_the_kept_ones_quotes_state_the_figure(record: dict) -> None:
    sessions = {s["session"]: s for s in record["counterexample"]["falseAlarm"]["sessions"]}
    kept, lowered = sessions["v1"], sessions["v2"]
    assert kept["finding"]["status"] == "pass" and lowered["finding"]["status"] == "needs_review"
    assert kept["adjudication"]["label"] == lowered["adjudication"]["label"] == "correct"
    # The same first sentence, the premise denied; the kept answer goes on to say more, which the rule does not judge.
    first = re.compile(r"^.*?[.!?](?=\s|$)")
    opening = [first.match(s["finding"]["conclusion"]) for s in (kept, lowered)]
    assert opening[0] and opening[1] and opening[0].group(0) == opening[1].group(0)
    assert any("$1,500,000" in s["quote"] for s in kept["finding"]["spans"])
    assert not any(re.search(r"1,500,000|1\.5 million", s["quote"]) for s in lowered["finding"]["spans"])


def test_the_party_check_numbers_the_page_states(record: dict) -> None:
    rows = record["rejectedFix"]["rows"]
    caught = Counter((r["set"], r["session"]) for r in rows if r["label"] == "wrong_party" and r["flagged"])
    wrong = Counter((r["set"], r["session"]) for r in rows if r["label"] == "wrong_party")
    lowered = Counter((r["set"], r["session"]) for r in rows if r["label"] == "correct" and r["flagged"])
    correct = Counter((r["set"], r["session"]) for r in rows if r["label"] == "correct")
    for session in ("s1", "s2"):
        assert (caught[("diagnostic", session)], wrong[("diagnostic", session)]) == (4, 6)
        assert (lowered[("diagnostic", session)], correct[("diagnostic", session)]) == (0, 13)
    for session in ("v1", "v2"):
        assert (caught[("unseen", session)], wrong[("unseen", session)]) == (0, 4)
        assert (lowered[("unseen", session)], correct[("unseen", session)]) == (0, 16)
    assert re.fullmatch(r"[0-9a-f]{40}", record["rejectedFix"]["commit"])
    # Across both sets and both sessions: every labelled finding, and the wrong-party ones among them.
    labels = Counter(r["label"] for r in rows)
    assert (sum(labels.values()), labels["wrong_party"]) == (80, 20)


def test_the_record_carries_no_email_address_or_machine_path(record: dict) -> None:
    text = RECORD.read_text(encoding="utf-8")
    assert not re.search(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", text)
    assert not re.search(r"[A-Za-z]:[\\/](Users|Temp)|/Users/|AppData", text)
    assert record["masking"]["inInput"] == record["headline"]["input"]["user"].count(record["masking"]["mask"]) > 0


def test_people_the_story_does_not_need_are_not_named(record: dict) -> None:
    # Release hygiene, 2026-10-11: the published record named notice contacts (law-firm and company addresses'
    # "Attention:" lines), signatories ("/s/ …", "Name: …") and an executive in one diagnostic case. None of them is part
    # of the story. The headline keeps the stockholders' representative: the question's false premise is about her role.
    text = RECORD.read_text(encoding="utf-8")
    assert not re.search(r"Attention:\s*\|?\s*[A-Z][a-z]", text)
    assert not re.search(r"/s/\s*[A-Z][a-z]", text)
    assert not re.search(r"Name:\s*\|?\s*[A-Z][a-z]+\s+[A-Z]", text)
    assert "Doug Stiles" not in text
    assert "Michelle Jarrard" in record["headline"]["question"]
    assert record["masking"]["names"] > 0


def test_a_signature_block_loses_every_name_and_keeps_its_shape() -> None:
    # A name never spans a line break: "/s/ Jane Roe\n\nName: Jane Roe" read as one three-word name hid the "Name:" line.
    import importlib.util

    path = Path(__file__).resolve().parents[1] / "scripts" / "export_break_record.py"
    spec = importlib.util.spec_from_file_location("export_break_record", path)
    assert spec and spec.loader
    exporter = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(exporter)
    block = "ACME, INC\nBy: | /s/ Jane Q. Roe\n\nName: | Jane Q. Roe\n\nTitle: | Chief Executive Officer\nAttention: John Doe, General Counsel"
    count = {"emails": 0, "names": 0}
    out = exporter.masked(block, count, [])
    assert "Roe" not in out and "John Doe" not in out
    assert out == ("ACME, INC\nBy: | /s/ [name masked]\n\nName: | [name masked]\n\nTitle: | Chief Executive Officer\nAttention: [name masked], General Counsel")
    assert count["names"] == 3
