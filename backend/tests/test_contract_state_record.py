"""The contract-state record is a file the experiment exported; the API reads it, checks its hash, and shows it as it is."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

DOC = {
    "record_id": "edgar:a-1:f.htm",
    "title": "AMENDMENT NO. 1 TO CREDIT AGREEMENT",
    "date": "2023-07-17",
    "instrument": "AMENDMENT",
    "type": "CREDIT AGREEMENT",
    "filer": "0000000001",
    "filer_name": "ACME CORP",
}
BASE = {**DOC, "record_id": "edgar:a-0:f.htm", "title": "CREDIT AGREEMENT", "date": "2023-05-17", "instrument": "BASE"}

ARRIVAL = {
    "document": DOC,
    "edge": {
        "state": "bound",
        "relation": "AMENDS",
        "proof": "ACCEPTED",
        "source": DOC["record_id"],
        "target": BASE,
        "evidence": "that certain Credit Agreement, dated as of May 17, 2023",
        "candidates": 4,
        "left_for_model": False,
    },
    "family": {
        "id": "Fabc",
        "review": [],
        "members": [
            {**BASE, "acts_on": None, "relation": None, "arrived": False},
            {**DOC, "acts_on": BASE["record_id"], "relation": "AMENDS", "arrived": True},
        ],
    },
    "effective": {
        "as_of": "2030-01-01",
        "before": {"GOVERNING_LAW": "New York", "MATURITY_DATE": "2027-05-17"},
        "after": {"GOVERNING_LAW": "New York", "MATURITY_DATE": "2028-05-17"},
        "operations": 2,
        "applied": 1,
        "needs_review": 1,
        "unsupported_mutations": 0,
    },
    "context": {
        "template": {"type": "CREDIT AGREEMENT", "cluster_size": 3, "exemplar": BASE, "base_is_exemplar": True},
        "cohort": {"type": "CREDIT AGREEMENT", "governing_law": "New York", "comparable": 43, "maturity_date_stated": 12},
        "deviations_from_exemplar": [],
    },
    "findings": {"in_family_after": 12, "changed": 1, "stale_examples": ["2.2"]},
    "plan": {
        "planned": 9,
        "planned_by_kind": {"EDGE": 1, "FAMILY": 1, "EFFECTIVE": 1, "FINDING": 4, "MEMBER": 2},
        "documents_examined": 4,
        "moved_keys": 31,
        "plan_seconds": 0.002,
    },
    "changed": {"total": 5, "by_kind": {"EDGE": 1, "FAMILY": 1, "EFFECTIVE": 1, "FINDING": 1, "MEMBER": 1}},
    "work": {
        "text_reads": 7,
        "adjudications": 4,
        "pair_scores": 0,
        "computed": 6,
        "kept_by_input_check": 3,
        "disturbed_without_dependency_change": 0,
        "model_calls_if_findings_were_model_made": 1,
        "characters_a_model_would_read": 900,
    },
    "latency_ms": 41.5,
    "documents_before": 5414,
    "objects_before": 48000,
    "verified": {"state_equal_to_rebuild": True, "changed_not_planned": 0, "rebuild_seconds": 300.0},
    "edge_on_gold_target": True,
}


def record(**overrides: object) -> dict[str, object]:
    body: dict[str, object] = {
        "schema": "contract-state/1",
        "source_commit": "148007b0000000000000000000000000000000000",
        "generated_at": "2026-10-06T23:00:00+00:00",
        "what_this_is": "A recording. Not a live run.",
        "portfolio": {"documents_at_start": 5414, "objects_at_start": 48000, "families_at_start": 4900, "findings_at_end": 31000, "source": "test"},
        "summary": {
            "arrivals": 1,
            "portfolio_documents_at_start": 5414,
            "objects_at_start": 48000,
            "verified_against_rebuild": 1,
            "verified_state_equal": 1,
            "false_negative_reach": 0,
            "stability_budget_disturbed_without_dependency_change": 0,
            "planned_mean": 9.0,
            "planned_max": 9,
            "changed_mean": 5.0,
            "false_positive_reach_share": 0.44,
            "documents_examined_mean": 4.0,
            "documents_examined_max": 4,
            "edges_accepted": 1,
            "edges_on_gold_target": 1,
            "left_for_model": 0,
            "model_calls_executed": 0,
            "per_arrival": {"objects_recomputed_mean": 6.0},
            "naive_rebuild_per_change": {"objects_recomputed": 48000},
            "work_avoided_per_arrival_mean": {"findings_not_recomputed": 30999.0},
            "an_extra_key_the_api_ignores": 1,
        },
        "evidence": {"relationship_audit": {"set": "audit2", "metrics": {"precision": 1.0, "recall": 0.6364}}},
        "arrivals": [ARRIVAL],
    }
    body.update(overrides)
    digest = hashlib.sha256(json.dumps(body, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()
    return {**body, "sha256": digest}


def test_the_record_is_read_from_its_file_hash_checked_and_shown_as_it_is(client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from app import config
    from app.api import engineering

    missing = tmp_path / "nowhere" / "contract-state.json"
    monkeypatch.setattr(config.settings, "contract_state", missing)
    unavailable = client.get("/api/engineering/contract-state").json()
    assert unavailable["available"] is False and "not found" in unavailable["detail"] and unavailable["arrivals"] == []

    path = tmp_path / "contract-state.json"
    path.write_text(json.dumps(record()), encoding="utf-8")
    monkeypatch.setattr(config.settings, "contract_state", path)
    assert engineering.contract_state_path() == path
    loaded = client.get("/api/engineering/contract-state").json()
    assert loaded["available"] is True and loaded["sha256Verified"] is True and loaded["schemaVersion"] == "contract-state/1"
    assert (
        loaded["portfolio"]["documentsAtStart"] == 5414 and loaded["summary"]["falseNegativeReach"] == 0 and "anExtraKeyTheApiIgnores" not in loaded["summary"]
    )
    arrival = loaded["arrivals"][0]
    assert arrival["edge"]["relation"] == "AMENDS" and arrival["edge"]["source"] == DOC["record_id"] and arrival["edge"]["target"]["date"] == "2023-05-17"
    assert arrival["effective"]["before"]["MATURITY_DATE"] == "2027-05-17" and arrival["effective"]["after"]["MATURITY_DATE"] == "2028-05-17", (
        "fact names are data, not keys to recase"
    )
    assert arrival["context"]["cohort"]["comparable"] == 43 and arrival["plan"]["plannedByKind"]["FINDING"] == 4
    assert arrival["verified"]["changedNotPlanned"] == 0 and arrival["family"]["members"][1]["arrived"] is True
    assert loaded["evidence"]["relationship_audit"]["metrics"]["recall"] == 0.6364
    assert loaded["whatThisIs"] == "A recording. Not a live run."


def test_an_edited_record_is_shown_with_its_hash_unverified_and_a_foreign_file_is_not_shown(
    client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app import config

    edited = record()
    edited["summary"]["false_negative_reach"] = 3  # type: ignore[index]
    path = tmp_path / "contract-state.json"
    path.write_text(json.dumps(edited), encoding="utf-8")
    monkeypatch.setattr(config.settings, "contract_state", path)
    loaded = client.get("/api/engineering/contract-state").json()
    assert loaded["available"] is True and loaded["sha256Verified"] is False, "an edited number is shown, and the hash says the file was edited"

    path.write_text(json.dumps({"schema": "lineage-arrivals/1", "arrivals": []}), encoding="utf-8")
    foreign = client.get("/api/engineering/contract-state").json()
    assert foreign["available"] is False and "contract-state/1" in foreign["detail"]

    path.write_text("{not json", encoding="utf-8")
    broken = client.get("/api/engineering/contract-state").json()
    assert broken["available"] is False and "unreadable" in broken["detail"]

    path.write_text(json.dumps(record(arrivals=[{"document": {"record_id": "x"}}])), encoding="utf-8")
    unfit = client.get("/api/engineering/contract-state").json()
    assert unfit["available"] is False and "does not fit" in unfit["detail"]
