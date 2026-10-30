"""The golden set is judged by code from run records. A present golden needs a verified citation in
one of its sections on a finding that does not call the point missing; an absent golden needs the
run not to assert the point. The comparison between prompt versions reads those verdicts only."""

from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app import db as db_module
from app.analysis.service import load_prompt
from app.db import SessionLocal
from app.goldens.replay import RECORDINGS_DIR, CommittedRecording, RecordedAnswers, load_recording, outcome_counts, replay
from app.goldens.service import (
    LOWERED_NOTE,
    Golden,
    Verdict,
    compare,
    ensure_golden_document,
    judge,
    load_set,
    lowered_passes,
    report,
    run_for,
    section_anchor,
)
from app.ingest import PARSER_VERSION, ingest
from app.models import Document, EvidenceSpan, Finding, FindingStatusName, Run, RunReasonName, RunStageName, Section
from app.providers.base import ProviderError
from app.schemas import GoldenRunOut


def span(number: str, verified: bool = True, method: str = "exact") -> EvidenceSpan:
    return EvidenceSpan(verified=verified, method=method, cited_section_label="sec_1", section=Section(number=number, heading="h", text="x"), quote="q")


def finding(status: FindingStatusName, *spans: EvidenceSpan) -> Finding:
    return Finding(status=status, status_source="model_hint", topic="t", conclusion="c", spans=list(spans))


def run_with(stage: RunStageName, findings: list[Finding], reason: RunReasonName | None = None) -> Run:
    return Run(
        stage=stage, reason=reason, findings=findings, question="q", provider="fake", model="fake", prompt_version="v", prompt_hash="h", document_sha256="d"
    )


PRESENT = Golden("g", "q", "present", ("5.3.1",), "")
ABSENT = Golden("g", "q", "absent", (), "")


def test_the_set_is_well_formed() -> None:
    golden_set = load_set()
    assert len(golden_set.goldens) == 44
    assert len({g.id for g in golden_set.goldens}) == 44
    assert all(g.sections for g in golden_set.goldens if g.kind == "present")
    assert sum(1 for g in golden_set.goldens if g.kind == "absent") == 6
    assert set(golden_set.categories) == {g.category for g in golden_set.goldens}, "every category is described and used"
    with_guidance = [g for g in golden_set.goldens if g.guidance]
    assert len(with_guidance) == 4 and all(g.status in ("pass", "needs_review") for g in with_guidance)
    assert all(g.status is None for g in golden_set.goldens if not g.guidance), "a status is only decided against guidance"
    assert len(golden_set.sha256) == 64
    assert golden_set.document_path.exists(), "the sample the set is written for ships in public/samples"


def test_a_present_golden_needs_a_verified_citation_in_its_sections() -> None:
    assert judge(PRESENT, run_with("complete", [finding("pass", span("5.3.1"))])).outcome == "pass"
    assert judge(PRESENT, run_with("complete", [finding("needs_review", span("5.4"), span("5.3.1", method="normalized"))])).outcome == "pass"
    assert judge(PRESENT, run_with("complete", [finding("pass", span("5.4"))])).outcome == "fail"
    assert judge(PRESENT, run_with("complete", [finding("pass", span("5.3.1", verified=False, method="none"))])).outcome == "fail"
    assert judge(PRESENT, run_with("complete", [finding("missing", span("5.3.1"))])).outcome == "fail"
    assert judge(PRESENT, run_with("unresolved", [], reason="citations_unverified")).outcome == "fail"
    assert judge(PRESENT, run_with("failed", [], reason="provider_error")).outcome == "fail"
    assert judge(PRESENT, None).outcome == "missing"
    assert judge(PRESENT, run_with("checking", [])).outcome == "missing"


def test_a_guidance_golden_also_needs_the_expected_status() -> None:
    golden = Golden("g", "q", "present", ("5.3.1",), "", category="guidance_comparison", guidance="at least 30 days", status="pass")
    assert judge(golden, run_with("complete", [finding("pass", span("5.3.1"))])).outcome == "pass"
    wrong = judge(golden, run_with("complete", [finding("needs_review", span("5.3.1"))]))
    assert wrong.outcome == "fail" and "decided needs_review where pass was expected" in wrong.because


def test_a_status_golden_fails_when_its_clause_is_decided_both_ways() -> None:
    """GOLDENS.md: a run that "decides the other status fails the golden". The judge failed it only when no finding in
    the section had the expected status, so a pass and a needs-review on the same quote satisfied either expectation,
    in either order (stress test EVL-3, 2026-10-30)."""
    for expected, other in (("pass", "needs_review"), ("needs_review", "pass")):
        golden = Golden("g", "q", "present", ("5.3.1",), "", category="guidance_comparison", guidance="at least 30 days", status=expected)  # type: ignore[arg-type]
        for first, second in ((expected, other), (other, expected)):
            verdict = judge(golden, run_with("complete", [finding(first, span("5.3.1")), finding(second, span("5.3.1"))]))  # type: ignore[arg-type]
            assert verdict.outcome == "fail", (expected, first, second)
            assert f"decided both {expected} and {other}" in verdict.because
        # Controls: one finding with the expected status passes, two that agree pass, and a finding with the other
        # status on a clause the golden does not name decides nothing about it.
        assert judge(golden, run_with("complete", [finding(expected, span("5.3.1"))])).outcome == "pass"  # type: ignore[arg-type]
        assert judge(golden, run_with("complete", [finding(expected, span("5.3.1")), finding(expected, span("5.3.1"))])).outcome == "pass"  # type: ignore[arg-type]
        assert judge(golden, run_with("complete", [finding(expected, span("5.3.1")), finding(other, span("9.9"))])).outcome == "pass"  # type: ignore[arg-type]


def test_a_golden_without_a_status_is_not_judged_on_statuses() -> None:
    """Unguided answers mix statuses in one section when they answer two points of it (a recorded run timed one point
    and asked review of the cap); only a golden that names a status is judged on it."""
    assert judge(PRESENT, run_with("complete", [finding("pass", span("5.3.1")), finding("needs_review", span("5.3.1"))])).outcome == "pass"


def lowered(source: str, *spans: EvidenceSpan) -> Finding:
    return Finding(status="needs_review", status_source=source, topic="t", conclusion="c", spans=list(spans))


def test_a_pass_carried_by_a_finding_code_lowered_says_so_and_is_counted() -> None:
    """A wrong number that code lowered (position_check) passed a golden as a plain pass, and so did a right answer whose
    prose named a section the document does not have (reference_check, Recording 6c's g38). Neither verdict changes: a
    lowering can be right about a wrong reference in a right answer. The verdict names the lowering, and the report
    counts the passes that rest on one (stress test EVL-3, 2026-10-30)."""
    for source in ("position_check", "reference_check", "ambiguous_fact"):
        verdict = judge(PRESENT, run_with("complete", [lowered(source, span("5.3.1"))]))
        assert verdict.outcome == "pass" and verdict.lowered == source
        assert f"{LOWERED_NOTE} ({source})" in verdict.because
    # A finding code did not lower carries the pass when the run has one, in either order.
    plain, by_code = finding("pass", span("5.3.1")), lowered("position_check", span("5.3.1"))
    for findings in ([by_code, plain], [plain, by_code]):
        verdict = judge(PRESENT, run_with("complete", findings))
        assert verdict.outcome == "pass" and verdict.lowered is None and LOWERED_NOTE not in verdict.because
    # Control: a needs review the model itself asked for, or code computed from the day counts, is not a lowering.
    assert judge(PRESENT, run_with("complete", [finding("needs_review", span("5.3.1"))])).lowered is None
    assert judge(PRESENT, run_with("complete", [lowered("computed_days", span("5.3.1"))])).lowered is None
    rows = [
        GoldenRunOut(golden_id="a", verdict="pass", because=f"verified citation in §5.3.1 (exact); {LOWERED_NOTE} (position_check)"),
        GoldenRunOut(golden_id="b", verdict="pass", because="verified citation in §5.3.1 (exact)"),
        GoldenRunOut(golden_id="c", verdict="fail", because=f"no verified citation; {LOWERED_NOTE}"),
    ]
    assert lowered_passes(rows) == ["a"]


def test_a_numeric_golden_needs_the_expected_period_in_the_answer() -> None:
    """numeric_precision exists for the tempting wrong number beside the right one, and the judge read no number: a run
    answering 30 days for g36's 60 passed, lowered by code or not (stress test EVL-3). The periods the answer states,
    in its conclusion and its observed value, are read by the parser the status decision uses."""
    golden = Golden("g36", "q", "present", ("5.3(b)",), "", category="numeric_precision", expected_value="60 days")

    def answer(conclusion: str, observed: str | None = None) -> Finding:
        return Finding(status="pass", status_source="model_hint", topic="t", conclusion=conclusion, observed=observed, spans=[span("5.3(b)")])

    right = answer("Proceedings may continue for 60 days.", "60 days")
    both = answer("60 days, not the 30-day cure period.")
    words = answer("Sixty (60) days.")
    wrong = answer("They may continue for 30 days.", "30 days")
    silent = answer("Insolvency is a ground to terminate.")
    assert all(judge(golden, run_with("complete", [f])).outcome == "pass" for f in (right, both, words))
    for f in (wrong, silent):
        verdict = judge(golden, run_with("complete", [f]))
        assert verdict.outcome == "fail" and "60 days" in verdict.because
    # A wrong finding beside a right one on the same clause: the right one carries it.
    assert judge(golden, run_with("complete", [wrong, right])).outcome == "pass"
    golden_set = load_set()
    numeric = {g.id: g.expected_value for g in golden_set.goldens if g.category == "numeric_precision"}
    assert numeric == {"g35": "30 days", "g36": "60 days"}, "every numeric_precision golden carries the period it asks for"


def test_an_absent_golden_passes_when_nothing_is_asserted() -> None:
    assert judge(ABSENT, run_with("complete", [finding("missing", span("5.3.1"))])).outcome == "pass"
    assert judge(ABSENT, run_with("unresolved", [], reason="insufficient_evidence")).outcome == "pass"
    assert (
        judge(ABSENT, run_with("unresolved", [finding("unresolved", span("13.19", verified=False, method="none"))], reason="citations_unverified")).outcome
        == "pass"
    )
    assert judge(ABSENT, run_with("complete", [finding("pass", span("5.3.1"))])).outcome == "fail"
    assert judge(ABSENT, run_with("complete", [finding("missing"), finding("needs_review", span("2.1.1"))])).outcome == "fail"
    assert judge(ABSENT, run_with("failed", [], reason="internal_error")).outcome == "fail"


def test_verdicts_carry_what_the_run_cited() -> None:
    verdict = judge(PRESENT, run_with("complete", [finding("pass", span("5.4"), span("5.3.1", verified=False, method="none"))]))
    assert verdict.cited == ("5.4 exact", "5.3.1 none")
    assert verdict.statuses == ("pass",)
    assert "§5.3.1" in verdict.because and "§5.4" in verdict.because


def test_compare_reads_verdicts_only() -> None:
    goldens = (
        Golden("a", "q", "present", ("1",), ""),
        Golden("b", "q", "absent", (), ""),
        Golden("c", "q", "present", ("2",), ""),
        Golden("d", "q", "present", ("3",), ""),
    )
    base = {
        "a": Verdict("fail", "x", ("pass",), ("1.1 exact",)),
        "b": Verdict("pass", "x", ("missing",), ()),
        "c": Verdict("pass", "x", ("pass",), ("2 exact",)),
        "d": Verdict("missing", "x"),
    }
    head = {
        "a": Verdict("pass", "y", ("pass",), ("1 exact",)),
        "b": Verdict("fail", "y", ("pass",), ("9 exact",)),
        "c": Verdict("pass", "y", ("pass",), ("2 normalized",)),
        "d": Verdict("pass", "y", ("pass",), ("3 exact",)),
    }
    out = compare(base, head, "answer-v1", "answer-v2", goldens)
    assert (out.better, out.worse, out.same, out.changed) == (1, 1, 2, 3)
    by_id = {r.golden_id: r for r in out.rows}
    assert by_id["a"].change == "better" and by_id["b"].change == "worse"
    assert by_id["c"].change == "same" and by_id["c"].changed, "same verdict, different location: still a change"
    assert by_id["d"].change == "same" and "not recorded under answer-v1" in by_id["d"].note


def test_report_says_what_is_missing_before_any_run(tmp_path: Path) -> None:
    engine = db_module.make_engine(f"sqlite:///{(tmp_path / 'g.db').as_posix()}")
    db_module.init_db(engine)
    with Session(engine) as session:
        before = report(session)
        assert not before.available and "run_goldens" in (before.detail or "")
        assert [g.id for g in before.goldens][:2] == ["g01", "g02"]

        document = ensure_golden_document(session, load_set())
        assert document.parser_version == PARSER_VERSION and len(document.sections) > 100
        after = report(session)
        assert after.available and after.document_id == document.id
        assert after.prompts == [] and after.compare is None and after.categories
        assert "no golden run is recorded" in (after.detail or "")
        assert ensure_golden_document(session, load_set()).id == document.id, "the sample is ingested once per reader version"


def test_model_comparison_groups_goldens_by_task_and_needs_the_sample(tmp_path: Path) -> None:
    from app.goldens.service import compare_models, task_of

    golden_set = load_set()
    tasks = {task_of(g) for g in golden_set.goldens}
    assert tasks == {"clause_lookup", "guidance_comparison"}
    assert sum(1 for g in golden_set.goldens if task_of(g) == "guidance_comparison") == 4

    engine = db_module.make_engine(f"sqlite:///{(tmp_path / 'm.db').as_posix()}")
    db_module.init_db(engine)
    with Session(engine) as session, pytest.raises(ValueError, match="run the golden set first"):
        compare_models(session, "answer-v2", "qwen3:8b", "qwen3:4b")


# ----------------------------------------------------------------------------- recordings under other readers and rules
#
# Every committed golden recording judged 37 of 44 under the set as it stood and 28 under today's, because reader v14
# renumbered 14 of the sample's 123 sections (5.3.1 became 5.3(a)) and the set was relabelled with them; and the report
# found runs only under today's fingerprint, so a store with 673 golden runs said "no golden run is recorded yet"
# (stress test EVL-2, 2026-10-30). A golden names its sections by text, and the report reads recordings by what each run
# stored.


def renumbered(number: str) -> str:
    """Reader v5's number for a sub-clause reader v15 numbers by letter: 5.3(a) was 5.3.1."""
    match = re.fullmatch(r"(.+)\(([a-z])\)", number)
    return f"{match.group(1)}.{ord(match.group(2)) - ord('a') + 1}" if match else number


def test_the_set_names_each_section_by_its_text_under_todays_reading() -> None:
    golden_set = load_set()
    path = golden_set.document_path
    parsed = ingest(path.name, path.read_bytes())
    by_number = {s.number: s for s in parsed.sections if s.number}
    anchors = Counter(section_anchor(s.text) for s in parsed.sections)
    named = {number for g in golden_set.goldens for number in g.sections}
    assert set(golden_set.anchors) == {n for n in named if section_anchor(by_number[n].text)}, "every named section with text is anchored"
    for number, anchor in golden_set.anchors.items():
        assert section_anchor(by_number[number].text) == anchor, f"§{number}'s text is not the text the set anchors"
        assert anchors[anchor] == 1, f"§{number}'s text is not unique in the sample, so it cannot name the section"
    g02 = next(g for g in golden_set.goldens if g.id == "g02")
    assert g02.anchors == (("5.3(a)", golden_set.anchors["5.3(a)"]),)
    # An earlier reader's text of a section is that section's too, and no other section's today.
    for number, earlier in golden_set.earlier_anchors.items():
        assert number in golden_set.anchors and not set(earlier) & set(anchors), number


def test_a_run_on_an_older_reading_is_judged_by_the_text_it_cites_not_the_number() -> None:
    golden_set = load_set()
    g02 = next(g for g in golden_set.goldens if g.id == "g02")
    path = golden_set.document_path
    today = next(s for s in ingest(path.name, path.read_bytes()).sections if s.number == "5.3(a)")
    older = Section(number="5.3.1", heading=today.heading, text=today.text)
    cited = EvidenceSpan(verified=True, method="exact", cited_section_label="sec_40", section=older, quote="q")
    verdict = judge(g02, run_with("complete", [finding("pass", cited)]))
    assert verdict.outcome == "pass" and "§5.3(a)" in verdict.because and "§5.3.1" in verdict.because
    # Control: today's number on other text is another section, whatever it is called.
    elsewhere = Section(number="5.3(a)", heading="h", text="Either party may terminate on thirty days' notice.")
    other = EvidenceSpan(verified=True, method="exact", cited_section_label="sec_40", section=elsewhere, quote="q")
    assert judge(g02, run_with("complete", [finding("pass", other)])).outcome == "fail"


def test_a_named_section_with_no_text_today_is_still_named_by_its_number() -> None:
    """Reader v15 reads §5.6 as a heading alone, so it has no anchor; reader v3 kept the survival lead-in under §5.6,
    and a recording on that reading that quoted it (ROUTING's qwen3:4b g23) cites the golden's section."""
    golden_set = load_set()
    g23 = next(g for g in golden_set.goldens if g.id == "g23")
    assert g23.sections == ("5.6(a)", "5.6") and {label for label, _anchor in g23.anchors} == {"5.6(a)"}
    lead_in = Section(number="5.6", heading="Survival", text="The following sections will survive expiration or termination of this Agreement.")
    cited = EvidenceSpan(verified=True, method="exact", cited_section_label="sec_60", section=lead_in, quote="q")
    assert judge(g23, run_with("complete", [finding("pass", cited)])).outcome == "pass"
    # Control: an anchored section is still named by its text only.
    other = Section(number="5.6(a)", heading="h", text="Either party may terminate on thirty days' notice.")
    stranger = EvidenceSpan(verified=True, method="exact", cited_section_label="sec_61", section=other, quote="q")
    assert judge(g23, run_with("complete", [finding("pass", stranger)])).outcome == "fail"


def older_reading(session: Session, today: Document) -> Document:
    """The sample's bytes as reader v5 read them: the same sections, texts and order, sub-clauses numbered 5.3.1."""
    sections = [Section(ordinal=s.ordinal, number=renumbered(s.number), heading=s.heading, text=s.text) for s in today.sections]
    document = Document(name="cloud-service-agreement.docx", media_type=today.media_type, sha256=today.sha256, parser_version="v5", sections=sections)
    session.add(document)
    session.flush()
    return document


def recorded_run(document: Document, golden: Golden, number: str, options: dict[str, object], session: Session) -> Run:
    prompt = load_prompt("answer-v2")
    section = next(s for s in document.sections if s.number == number)
    quote = section.text[:60]
    span_ = EvidenceSpan(
        ordinal=0, section_id=section.id, cited_section_label=f"sec_{section.ordinal}", start=0, end=len(quote), quote=quote, verified=True, method="exact"
    )
    run = Run(
        document_id=document.id,
        question=golden.question,
        stage="complete",
        provider="ollama",
        model="qwen3:8b",
        prompt_version=prompt.version,
        prompt_hash=prompt.sha256,
        options_json=json.dumps(options, sort_keys=True),
        document_sha256=document.sha256,
        fingerprint=f"recorded-{golden.id}-{document.id}-k{options['retrieval_k']}",
        findings=[Finding(ordinal=0, topic="t", status="pass", status_source="model_hint", conclusion="c", spans=[span_])],
    )
    session.add(run)
    return run


def test_the_report_shows_a_recording_made_on_an_older_reading_under_older_rules(client: TestClient) -> None:
    golden_set = load_set()
    g02, g13 = (next(g for g in golden_set.goldens if g.id == gid) for gid in ("g02", "g13"))
    legacy = {"model": "qwen3:8b", "num_ctx": 16384, "retrieval_k": 6, "seed": 42, "temperature": 0.0}
    with SessionLocal() as session:
        today = ensure_golden_document(session, golden_set)
        older = older_reading(session, today)
        recorded_run(older, g02, "5.3.1", legacy, session)
        recorded_run(older, g13, renumbered(g13.sections[0]), legacy, session)
        session.commit()
        out = report(session, golden_set)
        assert [p.version for p in out.prompts] == ["answer-v2"], out.detail
        prompt = out.prompts[0]
        assert (prompt.passes, prompt.recorded) == (2, 2)
        assert {r.golden_id: r.verdict for r in prompt.runs if r.verdict != "missing"} == {"g02": "pass", "g13": "pass"}
        detail = out.detail or ""
        assert "reader v5" in detail and "rules not recorded" in detail and "today's rules" in detail
        # The CLI says the same, and its counts are the report's.
        verdicts = {g.id: judge(g, run_for(session, older, g, load_prompt("answer-v2"))) for g in (g02, g13)}
        assert {gid: v.outcome for gid, v in verdicts.items()} == {"g02": "pass", "g13": "pass"}


def test_the_report_prefers_the_most_complete_recording_and_compares_only_like_with_like(client: TestClient) -> None:
    golden_set = load_set()
    g02, g13 = (next(g for g in golden_set.goldens if g.id == gid) for gid in ("g02", "g13"))
    legacy = {"model": "qwen3:8b", "num_ctx": 16384, "retrieval_k": 6, "seed": 42, "temperature": 0.0}
    wider = legacy | {"retrieval_k": 10}
    with SessionLocal() as session:
        today = ensure_golden_document(session, golden_set)
        older = older_reading(session, today)
        recorded_run(older, g02, "5.3.1", legacy, session)
        recorded_run(older, g13, renumbered(g13.sections[0]), legacy, session)
        session.flush()
        later = recorded_run(older, g02, "5.3.1", wider, session)  # a later recording of one golden, at k = 10
        session.commit()
        out = report(session, golden_set)
        shown = {r.golden_id: r.run_id for r in out.prompts[0].runs if r.run_id}
        assert set(shown) == {"g02", "g13"} and shown["g02"] != later.id, "two goldens recorded together outrank one recorded later"
        assert out.compare is None


# ----------------------------------------------------------------------------- the published figure, derived by code


def test_recording_6c_replayed_through_the_code_in_force_is_the_figure_its_file_states(client: TestClient) -> None:
    """The figure docs/STATUS.md publishes is Recording 6c's 44 recorded answers replayed through today's reader,
    retrieval, verifier, policy and judge (tests/test_docs_claims.py holds the prose to the file). A change to any of
    them that moves a golden fails here until the file is re-derived (`scripts/run_goldens.py --replay ... --write`) and
    the prose follows (stress test EVL-2, 2026-10-30: no code derived the published 37 of 44)."""
    recording = load_recording(RECORDINGS_DIR / "6c.json")
    assert len(recording.answers) == 44 and recording.prompt_version == "answer-v2" and "reader v5" in recording.label
    with SessionLocal() as session:
        verdicts = replay(session, load_set(), recording)
        assert outcome_counts(verdicts) == recording.replayed
        runs = session.query(Run).all()
        assert len(runs) == 44 and {run.provider for run in runs} == {"recorded"}, "one run per golden, every answer the recording's"


def test_a_replay_answers_only_what_was_recorded_and_only_to_the_prompt_it_answered() -> None:
    provider = RecordedAnswers("qwen3:8b", {"What is the term?": '{"findings": []}'})
    assert provider.generate_json("s", "QUESTION: What is the term?\n\nLEGAL GUIDANCE: none supplied", {}).text == '{"findings": []}'
    with pytest.raises(ProviderError, match="holds no answer"):
        provider.generate_json("s", "QUESTION: What is the cap?\n", {})
    recording = load_recording(RECORDINGS_DIR / "6c.json")
    changed = CommittedRecording(**{**recording.__dict__, "prompt_hash": "0" * 64})
    with pytest.raises(ValueError, match="is not the prompt the recording answered"):
        replay(None, load_set(), changed)  # type: ignore[arg-type]
