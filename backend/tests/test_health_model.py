"""Health says where the model runs, from the configuration, so the interface never claims a contract stays on a machine
it has left; and asking for health never wakes a model that bills by the second. Triage risk review, 2026-10-09: the
interface said "run on this machine; no contract is sent to a hosted model" whatever the deployment, and every page load,
signed in or not, asked the model endpoint for its tags.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app import config
from tests.test_access import ORIGIN, SECRET


@pytest.fixture
def probes(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> list[int]:
    calls: list[int] = []
    real = client.provider.healthy

    def counted() -> tuple[bool, str]:
        calls.append(1)
        ok, detail = real()
        return bool(ok), str(detail)

    monkeypatch.setattr(client.provider, "healthy", counted)
    return calls


@pytest.mark.parametrize(
    ("url", "label", "location", "host"),
    [
        ("http://localhost:11434", "", "server", ""),
        ("http://127.0.0.1:11434", "", "server", ""),
        ("https://verity--ollama.modal.run", "a Modal GPU in the US", "hosted", "a Modal GPU in the US"),
        ("http://host.docker.internal:11434", "", "hosted", ""),
    ],
)
def test_health_says_where_the_model_runs(client: TestClient, monkeypatch: pytest.MonkeyPatch, url: str, label: str, location: str, host: str) -> None:
    monkeypatch.setattr(config.settings, "ollama_url", url)
    monkeypatch.setattr(config.settings, "model_host", label)
    body = client.get("/api/health").json()
    assert (body["modelLocation"], body["modelHost"]) == (location, host)


def test_an_anonymous_visitor_never_wakes_the_model(client: TestClient, monkeypatch: pytest.MonkeyPatch, probes: list[int]) -> None:
    monkeypatch.setattr(config.settings, "access_secret", SECRET)
    monkeypatch.setattr(config.settings, "app_url", ORIGIN)
    body = client.get("/api/health").json()
    assert body["access"] == "required" and probes == []
    assert body["ok"] is True, "the store is writable: the workbench is up, though no one has entered"


def test_a_deployment_can_leave_the_model_to_the_answer(client: TestClient, monkeypatch: pytest.MonkeyPatch, probes: list[int]) -> None:
    monkeypatch.setattr(config.settings, "health_probes_model", False)
    body = client.get("/api/health").json()
    assert probes == [] and body["ok"] is True and "checked before every answer" in body["detail"]


def test_control_by_default_a_signed_in_or_open_health_check_asks_the_model(client: TestClient, probes: list[int]) -> None:
    client.get("/api/health")
    assert probes == [1]
