"""The golden set is judged by code from run records. A present golden needs a verified citation in
one of its sections on a finding that does not call the point missing; an absent golden needs the
run not to assert the point. The comparison between prompt versions reads those verdicts only."""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy.orm import Session

from app import db as db_module
from app.goldens.service import LOWERED_NOTE, Golden, Verdict, compare, ensure_golden_document, judge, load_set, lowered_passes, report
from app.ingest import PARSER_VERSION
from app.models import EvidenceSpan, Finding, FindingStatusName, Run, RunReasonName, RunStageName, Section
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
