"""A record made under rules newer than the running build is never called "earlier" and never re-checked as if it were.

Found on 2026-10-30 (stress test, store evolution 3): on the documented code-only rollback, a844ebf and 2e8fe68 started on
a store written by the candidate, and their trust layer called verifier v11 "earlier rules" and established its spans
by running the older verifier, while their own pack failed the same spans. Versions were compared by inequality, so a
version the build did not know read as one it had replaced. The rule here: one ordered comparison, and three answers:
the build's own rules, rules it has replaced, or rules it does not know.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from hypothesis import given
from hypothesis import strategies as st
from sqlalchemy import select, text

from app.application.trust_run import manifest_of
from app.db import SessionLocal
from app.models import Run
from app.runs.versions import SEMANTIC_VERSIONS, compare_version, earlier_versions, stale_versions, unknown_versions
from app.trust.compile import FindingRecord, SpanRecord, compile_manifest
from app.trust.model import Need, SectionText, Standing, TrustState
from app.verify.spans import locate
from tests.support import upload_and_ask
from tests.test_status_script import status

PREFIXES = ("", "policy-", "retrieval-")


@given(st.sampled_from(PREFIXES), st.integers(0, 400), st.integers(0, 400))
def test_versions_are_compared_by_their_number_not_by_inequality(prefix: str, recorded: int, current: int) -> None:
    order = compare_version(f"{prefix}v{recorded}", f"{prefix}v{current}")
    assert order == ("current" if recorded == current else "earlier" if recorded < current else "unknown")


@pytest.mark.parametrize(
    ("recorded", "current", "order"),
    [
        ("v10", "v11", "earlier"),
        ("v9", "v11", "earlier"),  # by number, not by text: "v9" > "v11" as strings
        ("v11", "v11", "current"),
        ("v12", "v11", "unknown"),
        ("policy-v16", "policy-v17", "earlier"),
        ("policy-v18", "policy-v17", "unknown"),
        ("retrieval-v3", "retrieval-v3", "current"),
        (None, "v11", "earlier"),  # recorded before versions were recorded: as stale as a run can be
        ("", "v11", "earlier"),
        ("v11b", "v11", "unknown"),  # a form this build cannot read is not one it knows
        ("v11b", "v11b", "current"),  # whatever its form, the build's own version is its own
        ("retrieval-v3", "v3", "unknown"),  # another rule's version is not this one's
    ],
)
def test_examples_of_the_order(recorded: str | None, current: str, order: str) -> None:
    assert compare_version(recorded, current) == order


def test_a_newer_version_is_stale_but_never_earlier() -> None:
    """Stale (the build will not execute the run) covers both directions; earlier covers only what it has replaced."""
    newer = {**SEMANTIC_VERSIONS, "verifier_version": "v99"}
    assert stale_versions(newer) and unknown_versions(newer) == stale_versions(newer)
    assert earlier_versions(newer) == []
    older = {**SEMANTIC_VERSIONS, "policy_version": "policy-v1"}
    assert earlier_versions(older) == stale_versions(older) and unknown_versions(older) == []  # control
    assert stale_versions(SEMANTIC_VERSIONS) == earlier_versions(SEMANTIC_VERSIONS) == unknown_versions(SEMANTIC_VERSIONS) == []


def rules(unknown_rules: tuple[str, ...], stale_rules: tuple[str, ...] = ()) -> tuple[Standing, str]:
    """The rules obligation of a quote today's verifier finds where the record located it."""
    section = SectionText(0, "1", "Term", "Either party may terminate this Agreement on thirty (30) days' written notice.")
    quote = "terminate this Agreement on thirty (30) days' written notice"
    located = locate(quote, section.text, section.label)
    assert located is not None
    span = SpanRecord(0, quote, "sec_0", True, located.method, 0, located.start, located.end)
    manifest = compile_manifest(
        run_id="r", document_id="d", document_sha256="0" * 64, reader_version="v6", current_reader="v6", rule_versions={},
        stale_rules=stale_rules, unknown_rules=unknown_rules, sections=[section], findings=[FindingRecord("f", 0, "term", "pass", (span,))],
    )  # fmt: skip
    obligation = next(o for o in manifest.findings[0].obligations if o.need is Need.RULES_COMPATIBLE)
    return obligation.standing, obligation.reason


def test_rules_this_build_does_not_know_are_not_established_by_running_the_older_verifier() -> None:
    standing, reason = rules(unknown_rules=("verifier version v99 then, v11 now",))
    assert standing is Standing.NOT_ESTABLISHED
    assert "earlier" not in reason and "this build does not know" in reason and "verifier version v99 then, v11 now" in reason


def test_under_rules_this_build_does_not_know_no_obligation_is_judged_by_its_own_verifier_or_reader() -> None:
    """The fresh review (2026-10-30): uniqueness was still counted by this build's verifier, and the reader obligation
    locates quotes with it too. Only what the record states (where a quote was found) and what the quote itself says
    stand; the finding cannot read supported."""
    section = SectionText(0, "1", "Term", "Either party may terminate this Agreement on thirty (30) days' written notice.")
    quote = "terminate this Agreement on thirty (30) days' written notice"
    located = locate(quote, section.text, section.label)
    assert located is not None
    span = SpanRecord(0, quote, "sec_0", True, located.method, 0, located.start, located.end)
    manifest = compile_manifest(
        run_id="r", document_id="d", document_sha256="0" * 64, reader_version="v99", current_reader="v6", rule_versions={},
        stale_rules=(), unknown_rules=("reader v99 then, v6 now",), sections=[section], findings=[FindingRecord("f", 0, "term", "pass", (span,))],
        current_reading=[section],
    )  # fmt: skip
    proof = manifest.findings[0]
    judged = {o.need for o in proof.obligations if o.standing is Standing.ESTABLISHED}
    assert judged <= {Need.QUOTE_EXISTS, Need.FACT_MATCHES}, judged
    for need in (Need.QUOTE_UNIQUE, Need.READER_COMPATIBLE, Need.RULES_COMPATIBLE):
        reasons = [o.reason for o in proof.obligations if o.need is need]
        assert reasons and all("this build does not know" in r and "earlier" not in r for r in reasons), (need, reasons)
    assert proof.state is not TrustState.SUPPORTED


def test_control_earlier_rules_are_still_asked_of_todays_verifier() -> None:
    standing, reason = rules(unknown_rules=(), stale_rules=("verifier version v5 then, v11 now",))
    assert standing is Standing.ESTABLISHED and "earlier rules" in reason


def _record_under(run_id: str, **versions: str) -> None:
    """The run as a newer build would have recorded it: a finished run is immutable, so its trigger is set aside."""
    with SessionLocal() as session:
        session.execute(text("DROP TRIGGER IF EXISTS trg_runs_no_update_when_finished"))
        run = session.get(Run, run_id)
        assert run is not None
        options = json.loads(run.options_json or "{}")
        run.options_json = json.dumps({**options, **versions})
        session.commit()


@pytest.mark.parametrize("newer", ["verifier", "reader"])
def test_a_run_recorded_by_a_newer_build_is_named_so_on_its_trust_page(client: TestClient, newer: str) -> None:
    run_id = upload_and_ask(client, "Is there an arbitration clause?")["run_id"]
    if newer == "verifier":
        _record_under(run_id, verifier_version="v99")
    else:
        with SessionLocal() as session:
            session.execute(text("DROP TRIGGER IF EXISTS trg_documents_no_update_when_finished"))
            session.execute(text("UPDATE documents SET parser_version = 'v99'"))
            session.commit()
    with SessionLocal() as session:
        run = session.scalars(select(Run).where(Run.id == run_id)).one()
        manifest = manifest_of(session, run)
    reasons = [o.reason for f in manifest.findings for o in f.obligations if o.need is Need.RULES_COMPATIBLE]
    assert reasons and all("this build does not know" in r and "earlier" not in r for r in reasons)


def test_status_counts_records_made_under_rules_this_build_does_not_know(client: TestClient, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    run_id = upload_and_ask(client, "Is there an arbitration clause?")["run_id"]
    assert status.check_rules(tmp_path / "test.db") is True  # control: everything is this build's
    assert "every run and document recorded under rules this build knows" in capsys.readouterr().out
    _record_under(run_id, policy_version="policy-v999")
    with SessionLocal() as session:
        session.execute(text("DROP TRIGGER IF EXISTS trg_documents_no_update_when_finished"))
        session.execute(text("UPDATE documents SET parser_version = 'v999'"))
        session.commit()
    assert status.check_rules(tmp_path / "test.db") is False
    out = capsys.readouterr().out
    assert "1 run(s) and 1 document(s) recorded under rules this build does not know" in out
    assert "policy_version policy-v999" in out and "reader v999" in out
