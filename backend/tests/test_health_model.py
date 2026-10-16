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
    ("url", "label", "on_server", "location", "host"),
    [
        ("http://localhost:11434", "", False, "server", ""),
        ("http://127.0.0.1:11434", "", False, "server", ""),
        ("https://verity--ollama.modal.run", "a Modal GPU in the US", False, "hosted", "a Modal GPU in the US"),
        ("http://host.docker.internal:11434", "", False, "hosted", ""),
        # The Hetzner layout: the model is another container on this machine, and the deployment says so (env.example).
        ("http://ollama:11434", "", True, "server", ""),
        # Control: a name that is not loopback counts as elsewhere unless the deployment says otherwise (review, 2026-10-16:
        # the kit first left it unsaid, and the interface would have told visitors their text went to a hosted GPU).
        ("http://ollama:11434", "", False, "hosted", ""),
    ],
)
def test_health_says_where_the_model_runs(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, url: str, label: str, on_server: bool, location: str, host: str
) -> None:
    monkeypatch.setattr(config.settings, "ollama_url", url)
    monkeypatch.setattr(config.settings, "model_host", label)
    monkeypatch.setattr(config.settings, "model_on_server", on_server)
    body = client.get("/api/health").json()
    assert (body["modelLocation"], body["modelHost"]) == (location, host)


def test_a_model_said_to_be_on_the_server_and_elsewhere_stops_the_start() -> None:
    with pytest.raises(ValueError, match="two places for the model"):
        config.Settings(model_on_server=True, model_host="a GPU service in the US")


@pytest.mark.parametrize(
    "url",
    [
        "https://gpu.example.com",
        "http://10.0.0.7:11434",
        "http://203.0.113.9:11434",
        "http://[2001:db8::7]:11434",
        "http://2130706433:11434",
        "http://host.docker.internal:11434",
        "http://0xcb007109:11434",
        "http://gpu．example．com:11434",
    ],
)
def test_a_model_on_another_machine_cannot_be_said_to_be_on_this_server(url: str) -> None:
    with pytest.raises(ValueError, match="an address elsewhere"):
        config.Settings(model_on_server=True, ollama_url=url)


@pytest.mark.parametrize("url", ["http://ollama:11434", "http://127.0.0.1:11434", "http://localhost:11434", "http://[::1]:11434"])
def test_control_a_container_or_loopback_can_be_said_to_be_on_this_server(url: str) -> None:
    assert config.Settings(model_on_server=True, ollama_url=url).model_on_server


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


def test_the_default_model_address_is_an_ip_literal_not_a_name() -> None:
    # Final release review, 2026-10-11: "localhost" resolved to ::1 first on Windows while Ollama listens on 127.0.0.1
    # only, so every request to the model endpoint (health, the build check, each answer) waited about two seconds for
    # the IPv6 attempt to fail: /api/health took 2.4 s for every visitor who had entered; about 0.35 s after, most of it
    # a real request for the model's tags.
    import ipaddress
    from urllib.parse import urlsplit

    host = urlsplit(config.DEFAULT_OLLAMA_URL).hostname
    assert host is not None
    assert ipaddress.ip_address(host).is_loopback
