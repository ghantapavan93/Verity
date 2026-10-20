"""Health tells the truth about the store as well as the model: a store that cannot take a write is not a healthy
workbench, though every page still loads. Checked without a transaction, so a long write never holds the check up.
"""

from __future__ import annotations

import os
import shutil
from collections import namedtuple
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

Usage = namedtuple("Usage", "total used free")


def test_a_read_only_store_is_not_healthy_and_says_why(client: TestClient, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    real_access = os.access
    monkeypatch.setattr(os, "access", lambda path, mode: False if Path(path) == tmp_path else real_access(path, mode))
    body = client.get("/api/health").json()
    assert body["ok"] is False and "read-only" in body["detail"] and body["fault"] == "store"


def test_a_nearly_full_store_is_not_healthy_and_publishes_no_byte_count(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(shutil, "disk_usage", lambda _path: Usage(10**12, 10**12 - 10**6, 10**6))
    body = client.get("/api/health").json()
    assert body["ok"] is False and "nearly full" in body["detail"] and body["fault"] == "store"
    assert not any(ch.isdigit() for ch in body["detail"]), "the public endpoint names no sizes"


def test_control_a_writable_store_with_room_leaves_health_to_the_model(client: TestClient) -> None:
    body = client.get("/api/health").json()
    assert body["ok"] is True and body["fault"] == "" and shutil.disk_usage(Path.cwd()).free > 0


def test_a_model_that_does_not_answer_is_the_fault_named_and_the_store_is_not(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """The interface tells a reader which part is failing: "the model is offline" only when it is the model (F-19)."""
    monkeypatch.setattr(client.provider, "healthy", lambda: (False, "the model endpoint is not reachable (ConnectError)"))
    body = client.get("/api/health").json()
    assert body["ok"] is False and body["fault"] == "model"


@pytest.mark.parametrize(("public", "healthy"), [(True, False), (False, True)])
def test_health_and_the_write_refusal_share_one_floor(client: TestClient, monkeypatch: pytest.MonkeyPatch, public: bool, healthy: bool) -> None:
    """Ops audit, 2026-10-19: a public store refuses uploads below its 2 GiB floor (access.refuse_if_disk_low), and health
    said ok between 256 MiB and that floor. With 1 GiB free a public store is not healthy; an owner's store still is."""
    from app import config

    monkeypatch.setattr(config.settings, "anonymous_sessions", public)
    monkeypatch.setattr(shutil, "disk_usage", lambda _path: Usage(10**12, 10**12 - 2**30, 2**30))
    body = client.get("/api/health").json()
    assert body["ok"] is healthy and (body["fault"] == "store") is not healthy
