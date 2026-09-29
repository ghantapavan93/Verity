"""The record and replay providers behind the browser tests: what was recorded comes back byte for
byte, anything else fails loudly, and the default provider is untouched."""

from pathlib import Path

import pytest

from app.providers import make_provider
from app.providers.base import Generation, ProviderError
from app.providers.replay import RecordingProvider, ReplayProvider, load_answers, request_key

SCHEMA: dict[str, object] = {"type": "object"}


class LiveStandIn:
    """Plays the live model for the recorder; counts the calls it received."""

    name = "stand-in"
    model = "qwen3:8b"

    def __init__(self) -> None:
        self.calls = 0

    def healthy(self) -> tuple[bool, str]:
        return True, "stand-in"

    def generate_json(self, system: str, user: str, schema: dict[str, object]) -> Generation:
        self.calls += 1
        return Generation(text='{"findings": []}', input_tokens=12, output_tokens=4, latency_ms=8.5, model=self.model)


def test_what_the_recorder_writes_the_replayer_returns_unchanged(tmp_path: Path) -> None:
    path = tmp_path / "replay.json"
    live = LiveStandIn()
    recorder = RecordingProvider(live, path)
    first = recorder.generate_json("system prompt", "user message\nsecond line", SCHEMA)

    replay = ReplayProvider(path)
    again = replay.generate_json("system prompt", "user message\nsecond line", SCHEMA)
    assert again == first
    assert again.model == "qwen3:8b"
    assert live.calls == 1
    assert replay.healthy() == (True, "replaying 1 recorded answers from replay.json")
    assert load_answers(path)[request_key("system prompt", "user message\nsecond line")]["user_head"] == "user message"


def test_a_request_that_was_not_recorded_fails_and_says_how_to_record(tmp_path: Path) -> None:
    path = tmp_path / "replay.json"
    RecordingProvider(LiveStandIn(), path).generate_json("system prompt", "one question", SCHEMA)
    replay = ReplayProvider(path)
    with pytest.raises(ProviderError, match="WORKBENCH_PROVIDER=record"):
        replay.generate_json("system prompt", "another question", SCHEMA)
    with pytest.raises(ProviderError):
        replay.generate_json("system prompt" + "one question", "", SCHEMA)  # a different split of the same characters is a different request


def test_an_empty_replay_file_is_reported_unhealthy(tmp_path: Path) -> None:
    replay = ReplayProvider(tmp_path / "missing.json")
    ok, detail = replay.healthy()
    assert not ok
    assert "no recorded answers" in detail


def test_the_factory_keeps_ollama_as_the_default_and_knows_the_two_test_providers(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from app import config

    monkeypatch.setattr(config.settings, "replay_file", tmp_path / "replay.json")
    assert make_provider().name == "ollama"
    assert make_provider("replay").name == "replay"
    assert make_provider("record").name == "record"
    with pytest.raises(ProviderError, match="unknown provider"):
        make_provider("openai")
