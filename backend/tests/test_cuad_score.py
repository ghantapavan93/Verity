"""The CUAD scorer judges the answer the batch reports, over the whole pre-registered population, failures counted.

Two ways the published CUAD-30 figures were kinder than the rule in docs/CUAD.md (stress test EVL-4, EVL-5, 2026-10-30):
- the scorer took the located texts of every asserting finding of a run, so a later finding could make a reported
  answer that missed the experts' span count as correct (2 of 210 values; uncapped liability precision 0.60 against
  0.20 on the reported answer), and the SkillOpt rollout, which the docstring said scored the same way, did not;
- the population was the batch's own items, so a failed run, one still in progress, or a pair the batch never asked
  left every denominator: 6 of 7 questions failed read "recall 1.00, fit to draft".

The invariant: the scored unit is the reported answer (one primitive, cuad_match.answer_index, picks it for the batch,
the scorer and the rollout), and every (contract, question) pair of the manifest gets exactly one outcome; recall counts
the unfinished ones as misses and the verdict refuses a recording that did not finish.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import re
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
from fastapi.testclient import TestClient
from hypothesis import given, settings
from hypothesis import strategies as st

from app import db as db_module
from app.batch.cuad_match import OUTCOMES, answer_index, answered_texts, hits, outcome
from app.batch.service import run_batch, value_for
from app.models import EvidenceSpan, Finding, FindingStatusName, Run, RunStageName, Section
from app.providers.base import Generation, ProviderError
from tests.support import CONTRACT, FUZZ_SCALE

BACKEND = Path(__file__).resolve().parents[1]
ROOT = BACKEND.parent


def _load(name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


score_cuad = _load("score_cuad", BACKEND / "scripts" / "score_cuad.py")
rollout = _load("skillopt_rollout", ROOT / "research" / "skillopt" / "workbench_env" / "rollout.py")

EXPERT = "This Agreement is governed by the laws of the State of Delaware."
ELSEWHERE = "This Agreement commences on the Effective Date and continues for twelve (12) months."


def span(text: str, verified: bool = True) -> EvidenceSpan:
    section = Section(number="1", heading="h", text=text)
    return EvidenceSpan(
        verified=verified, method="exact" if verified else "none", start=0 if verified else -1, end=len(text) if verified else -1, section=section, quote=text
    )


def finding(status: FindingStatusName, *spans: EvidenceSpan) -> Finding:
    return Finding(status=status, status_source="model_hint", topic="t", conclusion="c", spans=list(spans))


def run_of(findings: list[Finding], stage: RunStageName = "complete") -> Run:
    return Run(id="r1", stage=stage, findings=findings, question="q", provider="fake", model="fake", prompt_version="v", prompt_hash="h", document_sha256="d")


def scored_outcome(run: Run, experts: list[str]) -> str:
    """What scripts/score_cuad.py counts for one run against these experts' spans."""
    result: str = score_cuad.judge_run(run, experts)[0]
    return result


# ----------------------------------------------------------------------------- the unit: the reported answer


def test_the_answer_is_the_first_asserting_finding_with_a_located_text() -> None:
    assert answer_index([("missing", []), ("pass", []), ("needs_review", ["b"]), ("pass", ["c"])]) == 2
    assert answered_texts([("unresolved", ["a"]), ("pass", ["b", "c"])]) == ["b", "c"]
    assert answered_texts([("missing", ["a"]), ("unresolved", ["b"])]) is None
    assert answered_texts([]) is None


def test_a_later_finding_does_not_make_a_reported_answer_that_missed_correct() -> None:
    """The shape of 04-audibleinc and 24-raesystemsinc in CUAD-30: the reported value cites a passage the experts did not
    mark, and a later finding of the same run quotes theirs. The batch reports the first; so is it scored."""
    run = run_of([finding("pass", span(ELSEWHERE)), finding("pass", span(EXPERT))])
    assert value_for(run).value == "c" and value_for(run).citation == "§1"
    assert scored_outcome(run, [EXPERT]) == "cited elsewhere"
    # Control: the same run with the experts' passage reported first is correct.
    assert scored_outcome(run_of([finding("pass", span(EXPERT)), finding("pass", span(ELSEWHERE))]), [EXPERT]) == "correct"


def test_a_finding_whose_quotes_did_not_verify_is_not_the_answer() -> None:
    run = run_of([finding("pass", span(ELSEWHERE, verified=False)), finding("needs_review", span(EXPERT))])
    assert value_for(run).status == "needs_review"
    assert scored_outcome(run, [EXPERT]) == "correct"


TEXTS = (EXPERT, ELSEWHERE, "Customer may terminate this Agreement for convenience upon fifteen (15) days’ written notice to Provider.")
findings_strategy = st.lists(
    st.tuples(st.sampled_from(["pass", "needs_review", "missing", "unresolved"]), st.lists(st.tuples(st.sampled_from(TEXTS), st.booleans()), max_size=3)),
    max_size=4,
)


def _built(shape: list[tuple[str, list[tuple[str, bool]]]]) -> Run:
    return run_of([finding(status, *(span(text, verified) for text, verified in spans)) for status, spans in shape])  # type: ignore[arg-type]


@settings(max_examples=300 * FUZZ_SCALE, deadline=None)
@given(shape=findings_strategy, experts=st.sets(st.sampled_from(TEXTS), max_size=2))
def test_property_the_scored_text_is_the_text_of_the_finding_the_batch_reports(shape: list[tuple[str, list[tuple[str, bool]]]], experts: set[str]) -> None:
    """An oracle written from docs/CUAD.md, not from the code: the value is the first pass or needs-review finding with a
    verified quote, and it is correct when one of that finding's located texts hits a span."""
    run, expert_list = _built(shape), sorted(experts)
    reported = next((s for s in shape if s[0] in ("pass", "needs_review") and any(v for _t, v in s[1])), None)
    if reported is None:
        expected = "missed" if expert_list else "correct absence"
    elif not expert_list:
        expected = "asserted where experts found none"
    else:
        expected = "correct" if any(v and hits(t, expert_list) for t, v in reported[1]) else "cited elsewhere"
    assert scored_outcome(run, expert_list) == expected
    # The SkillOpt rollout scores a proposal by the same unit and rule (research/skillopt/workbench_env/rollout.py).
    decided = [(status, [text for text, verified in spans if verified]) for status, spans in shape]
    assert rollout.scored(decided, expert_list)[0] == expected


@settings(max_examples=200 * FUZZ_SCALE, deadline=None)
@given(shape=findings_strategy, experts=st.sets(st.sampled_from(TEXTS), max_size=2))
def test_control_a_run_with_one_asserting_finding_scores_as_it_always_did(shape: list[tuple[str, list[tuple[str, bool]]]], experts: set[str]) -> None:
    """The old unit, every asserting finding's located texts, differs from the reported answer only when a run has two."""
    asserting = [s for s in shape if s[0] in ("pass", "needs_review")]
    if len(asserting) > 1:
        return
    run, expert_list = _built(shape), sorted(experts)
    old_texts = [text for _status, spans in asserting for text, verified in spans if verified]
    value = value_for(run)
    old = outcome(value.outcome, old_texts, expert_list)
    assert scored_outcome(run, expert_list) == old


def test_an_outcome_is_one_of_the_closed_set_and_an_unknown_value_is_refused() -> None:
    assert set(OUTCOMES) == {
        "correct",
        "cited elsewhere",
        "missed",
        "correct absence",
        "asserted where experts found none",
        "failed",
        "in progress",
        "not run",
    }
    assert outcome("failed", [], [EXPERT]) == "failed" and outcome("in_progress", [], []) == "in progress" and outcome("not_run", [], [EXPERT]) == "not run"
    with pytest.raises(ValueError, match="no outcome"):
        outcome("answred", [], [EXPERT])


# ----------------------------------------------------------------------------- the population: every pre-registered pair


def scored_row(outcome_name: str, experts: int, category: str = "Governing Law") -> object:
    return score_cuad.Scored(
        contract="c",
        file="f",
        field="governing_law",
        category=category,
        outcome=outcome_name,
        run_id=None,
        expert_spans=experts,
        located=None,
        citation=None,
        method=None,
        latency_ms=None,
        reused=False,
        expert_in_retrieved=None,
    )


FINISHED = ("correct", "cited elsewhere", "missed", "correct absence", "asserted where experts found none")
pairs_strategy = st.lists(
    st.one_of(
        st.tuples(st.sampled_from(["correct", "cited elsewhere", "missed"]), st.just(1)),
        st.tuples(st.sampled_from(["correct absence", "asserted where experts found none"]), st.just(0)),
    ),
    min_size=1,
    max_size=30,
)


@settings(max_examples=300 * FUZZ_SCALE, deadline=None)
@given(pairs=pairs_strategy, data=st.data())
def test_property_a_pair_that_did_not_finish_never_raises_recall_or_earns_the_verdict(pairs: list[tuple[str, int]], data: st.DataObject) -> None:
    """Monotonicity: turning any expert-labelled pair from a miss into failed, in progress or not run never raises
    recall, and a recording with any such pair never reads "fit to draft"."""
    complete = [scored_row(name, experts) for name, experts in pairs]
    labelled = [i for i, (_name, experts) in enumerate(pairs) if experts]
    if not labelled:
        return
    index = data.draw(st.sampled_from(labelled))
    unfinished = data.draw(st.sampled_from(["failed", "in progress", "not run"]))
    as_missed = [*complete[:index], scored_row("missed", 1), *complete[index + 1 :]]
    as_unfinished = [*complete[:index], scored_row(unfinished, 1), *complete[index + 1 :]]
    assert score_cuad.rates(as_unfinished)["all"].recall <= score_cuad.rates(as_missed)["all"].recall
    assert "fit to draft" not in score_cuad.verdict(as_unfinished).replace("NOT fit to draft", "")
    assert "not scorable" in score_cuad.verdict(as_unfinished)


def test_recall_counts_every_labelled_pair_and_the_table_shows_what_did_not_finish() -> None:
    rows = [scored_row("correct", 1), scored_row("failed", 1), scored_row("in progress", 1), scored_row("not run", 1), scored_row("correct absence", 0)]
    rate = score_cuad.rates(rows)["all"]
    assert (rate.precision, rate.recall, rate.absence) == (1.0, 0.25, 1.0)
    header, _rule, *body = score_cuad.table(rows).splitlines()
    assert "| failed | in progress | not run |" in header
    assert body[-1].startswith("| **all** | 4 | 1 | 0 | 0 | 1 | 0 | 1 | 1 | 1 | 1.00 | 0.25 | 1.00 |")
    verdict = score_cuad.verdict(rows)
    assert "not scorable" in verdict and "1 failed, 1 in progress and 1 not run of 5 values" in verdict


def test_control_a_finished_recording_keeps_its_verdict() -> None:
    fit = [scored_row("correct", 1)] * 9 + [scored_row("cited elsewhere", 1), scored_row("correct absence", 0)]
    assert "verdict: fit to draft" in score_cuad.verdict(fit)
    unfit = [scored_row("correct", 1), scored_row("missed", 1), scored_row("missed", 1)]
    assert "verdict: NOT fit to draft" in score_cuad.verdict(unfit)
    assert "fit to draft" not in score_cuad.verdict(fit, refusals=["the batch never finished"]).replace("NOT fit to draft", "")


# ----------------------------------------------------------------------------- end to end: a real batch, a scripted model


class Scripted:
    """Answers governing law with the clause, and every other question either with a failure or with "not found"."""

    name = "scripted"
    model = "scripted-1"

    def __init__(self, others: str) -> None:
        self.others = others

    def healthy(self) -> tuple[bool, str]:
        return True, "scripted"

    def generate_json(self, system: str, user: str, schema: dict[str, Any]) -> Generation:
        if "What law governs" in user.splitlines()[0]:
            label = re.search(r"\[(sec_\d+)\] 3 Governing Law", user)
            assert label, "the governing-law section was not handed to the model"
            evidence = [{"section_id": label.group(1), "quote": EXPERT}]
            finding = {"topic": "Law", "conclusion": "Delaware law governs.", "status_hint": "pass", "evidence": evidence}
            payload = {"findings": [finding | {"guidance_reference": None, "observed": None, "required": None, "suggested_position": None}]}
            return Generation(
                text=json.dumps(payload | {"insufficient_evidence": False, "note": None}), input_tokens=1, output_tokens=1, latency_ms=1.0, model=self.model
            )
        if self.others == "fail":
            raise ProviderError("Ollama request failed: timed out")
        empty = {"findings": [], "insufficient_evidence": True, "note": "The sections do not address this."}
        return Generation(text=json.dumps(empty), input_tokens=1, output_tokens=1, latency_ms=1.0, model=self.model)


def corpus_and_manifest(tmp_path: Path, extra_contract: bool = False, wrong_bytes: bool = False) -> tuple[Path, Path, Path]:
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    (corpus / "alpha.txt").write_text(CONTRACT, encoding="utf-8")
    sha = hashlib.sha256((corpus / "alpha.txt").read_bytes()).hexdigest()
    contracts = [{"file": "alpha.txt", "title": "Alpha", "sha256": "0" * 64 if wrong_bytes else sha}]
    if extra_contract:  # in the manifest, never asked: a file the corpus skipped, or a batch killed before it
        contracts.append({"file": "beta.txt", "title": "Beta", "sha256": "1" * 64})
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({"contracts": contracts}), encoding="utf-8")
    labels = tmp_path / "labels.json"
    spans = {"Governing Law": [EXPERT], "Termination For Convenience": [TEXTS[2]], "Cap On Liability": ["Liability is capped at the fees paid."]}
    labels.write_text(json.dumps({"Alpha": spans, "Beta": {"Governing Law": [EXPERT]}}), encoding="utf-8")
    return corpus, manifest, labels


def batch_scored(client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, others: str, **manifest: bool) -> tuple[Any, list[Any]]:
    import app.analysis.service as analysis

    monkeypatch.setattr(analysis, "PROVIDER_RETRY_DELAY_S", 0.0)
    corpus, manifest_path, labels_path = corpus_and_manifest(tmp_path, **manifest)
    batch_id = run_batch(db_module.SessionLocal, Scripted(others), [corpus], "cuad-clauses", corpus_label="cuad-30", model="scripted-1")
    with db_module.SessionLocal() as session:
        batch, scored = score_cuad.score(session, batch_id, manifest_path=manifest_path, labels_path=labels_path)
        return score_cuad.refusals(batch), scored


def test_failed_runs_count_against_recall_and_the_verdict_is_refused(client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """EVL-5's reproduction: six of seven questions fail. Before, "recall 1.00, fit to draft"."""
    refusals, scored = batch_scored(client, tmp_path, monkeypatch, "fail")
    assert {s.field: s.outcome for s in scored}["governing_law"] == "correct"
    assert sorted(s.outcome for s in scored).count("failed") == 6
    recall = score_cuad.rates(scored)["all"].recall
    assert recall == pytest.approx(1 / 3), "governing law of three labelled categories"
    verdict = score_cuad.verdict(scored, refusals=refusals)
    assert "not scorable" in verdict and "fit to draft" not in verdict.replace("NOT fit to draft", "")
    assert "6 failed" in verdict


def test_control_the_same_model_answering_not_found_is_scored_and_not_fit(client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    refusals, scored = batch_scored(client, tmp_path, monkeypatch, "not found")
    assert refusals == []
    assert sorted({s.outcome for s in scored}) == ["correct", "correct absence", "missed"]
    assert score_cuad.rates(scored)["all"].recall == pytest.approx(1 / 3), "failing instead of answering never scores higher"
    assert "verdict: NOT fit to draft" in score_cuad.verdict(scored, refusals=refusals)


def test_a_pair_the_batch_never_asked_is_not_run(client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    refusals, scored = batch_scored(client, tmp_path, monkeypatch, "not found", extra_contract=True)
    assert len(scored) == 14, "two contracts of the manifest, seven questions each"
    beta = [s for s in scored if s.file == "beta.txt"]
    assert {s.outcome for s in beta} == {"not run"} and sum(s.expert_spans > 0 for s in beta) == 1
    assert score_cuad.rates(scored)["all"].recall == pytest.approx(1 / 4)
    assert "not scorable" in score_cuad.verdict(scored, refusals=refusals) and "7 not run" in score_cuad.verdict(scored, refusals=refusals)
    assert "not run" in score_cuad.misses_to_read(scored, {})


def test_bytes_other_than_the_manifests_are_not_scored_against_the_experts(client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _refusals, scored = batch_scored(client, tmp_path, monkeypatch, "not found", wrong_bytes=True)
    assert {s.outcome for s in scored} == {"not run"}
