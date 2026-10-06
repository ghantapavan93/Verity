"""The lineage record is a file the experiment exported; the API reads it, checks its hash, and shows it as it is."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ARRIVAL = {
    "document": {
        "record_id": "edgar:a-1:f.htm",
        "title": "AMENDMENT NO. 1 TO CREDIT AGREEMENT",
        "date": "2023-07-17",
        "filer": "0000000001",
        "filer_name": "ACME CORP",
        "instrument": "AMENDMENT",
        "agreement_type": "CREDIT AGREEMENT",
    },
    "portfolio_documents": 5414,
    "documents_examined": 29,
    "relationship": {
        "target": {
            "record_id": "edgar:a-0:f.htm",
            "title": "CREDIT AGREEMENT",
            "date": "2023-05-17",
            "filer": "0000000001",
            "filer_name": "ACME CORP",
            "instrument": "BASE",
            "agreement_type": "CREDIT AGREEMENT",
        },
        "relation": "AMENDS",
    },
    "relationship_is_gold": True,
    "family": "family:abc",
    "families_rebuilt": 1,
    "unrelated_families_recomputed": 0,
    "family_nodes_changed": 1,
    "composite_sections_changed": ["2.2", "2.3"],
    "trust_dependencies_reached": ["family:abc:2.2->2.2"],
    "findings_invalidated": ["family:abc:2.2"],
    "findings_preserved": 11,
    "model_calls": 0,
    "seconds": 0.35,
}


def record(**overrides: object) -> dict[str, object]:
    body: dict[str, object] = {
        "schema": "lineage-arrivals/1",
        "generated_at": "2026-10-05T23:00:00+00:00",
        "generated_by": "experiments/contract-lineage/evals/export_arrivals.py",
        "source_repository": "ivo-experiments",
        "source_commit": "148007b0000000000000000000000000000000000",
        "feature_version": "f96b85282717",
        "portfolio": {"documents_at_start": 5414, "families_at_start": 4918, "findings_at_start": 31676, "source": "test"},
        "summary": {
            "arrivals": 1,
            "portfolio_documents_at_start": 5414,
            "families_at_start": 4918,
            "findings_at_start": 31676,
            "unrelated_families_recomputed_total": 0,
            "documents_examined_mean": 29.3,
            "documents_examined_max": 64,
            "edges_bound": 1,
            "edges_bound_to_gold_base": 1,
            "findings_invalidated_total": 1,
            "findings_preserved_total": 11,
            "model_asks_total": 0,
            "wall_seconds_p50": 0.35,
            "wall_seconds_p95": 5.0,
            "an_extra_key_the_api_ignores": 1,
        },
        "candidate_generation_held_out": {
            "hybrid-norefs": {"recall@10": 0.89, "recall@20": 1.0, "candidates_examined_per_query_mean": 83.2, "latency_ms_p50": None}
        },
        "adjudication_held_out": {"deterministic": {"precision": 1.0, "recall": 1.0, "false_family_rate": 0.0, "positives": 274, "hard_negatives": 483}},
        "arrivals": [ARRIVAL],
        "what_this_is": "A recording. Not a live run.",
    }
    body.update(overrides)
    digest = hashlib.sha256(json.dumps(body, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()
    return {**body, "sha256": digest}


def test_the_record_is_read_from_its_file_hash_checked_and_shown_as_it_is(client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from app import config
    from app.api import engineering

    missing = tmp_path / "nowhere" / "lineage-arrivals.json"
    monkeypatch.setattr(config.settings, "lineage_arrivals", missing)
    unavailable = client.get("/api/engineering/lineage").json()
    assert unavailable["available"] is False and "not found" in unavailable["detail"] and unavailable["arrivals"] == []

    path = tmp_path / "lineage-arrivals.json"
    path.write_text(json.dumps(record()), encoding="utf-8")
    monkeypatch.setattr(config.settings, "lineage_arrivals", path)
    assert engineering.arrivals_path() == path
    loaded = client.get("/api/engineering/lineage").json()
    assert loaded["available"] is True and loaded["sha256Verified"] is True and loaded["schemaVersion"] == "lineage-arrivals/1"
    assert loaded["sourceCommit"].startswith("148007b") and loaded["portfolio"]["documentsAtStart"] == 5414
    assert loaded["summary"]["unrelatedFamiliesRecomputedTotal"] == 0 and "anExtraKeyTheApiIgnores" not in loaded["summary"]
    arrival = loaded["arrivals"][0]
    assert arrival["relationship"]["relation"] == "AMENDS" and arrival["relationship"]["target"]["date"] == "2023-05-17"
    assert arrival["documentsExamined"] == 29 and arrival["findingsPreserved"] == 11 and arrival["compositeSectionsChanged"] == ["2.2", "2.3"]
    assert loaded["candidateGenerationHeldOut"]["hybrid-norefs"]["recall@20"] == 1.0
    assert loaded["adjudicationHeldOut"]["deterministic"]["positives"] == 274
    assert loaded["whatThisIs"] == "A recording. Not a live run."


def test_an_edited_record_is_shown_with_its_hash_unverified_and_a_foreign_file_is_not_shown(
    client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app import config

    edited = record()
    edited["summary"]["unrelated_families_recomputed_total"] = 3  # type: ignore[index]
    path = tmp_path / "lineage-arrivals.json"
    path.write_text(json.dumps(edited), encoding="utf-8")
    monkeypatch.setattr(config.settings, "lineage_arrivals", path)
    loaded = client.get("/api/engineering/lineage").json()
    assert loaded["available"] is True and loaded["sha256Verified"] is False, "an edited number is shown, and the hash says the file was edited"

    path.write_text(json.dumps({"schema": "something-else/1", "arrivals": []}), encoding="utf-8")
    foreign = client.get("/api/engineering/lineage").json()
    assert foreign["available"] is False and "lineage-arrivals/1" in foreign["detail"]

    path.write_text("{not json", encoding="utf-8")
    broken = client.get("/api/engineering/lineage").json()
    assert broken["available"] is False and "unreadable" in broken["detail"]

    path.write_text(json.dumps(record(arrivals=[{"document": {"record_id": "x"}}])), encoding="utf-8")
    unfit = client.get("/api/engineering/lineage").json()
    assert unfit["available"] is False and "does not fit" in unfit["detail"]
