"""Every answer is computed from its prompt's first token (docs/CASEBOOK.md, case 6).

llama-server starts a prompt from the longest prefix its one slot already holds. One recorded input therefore gave two
answers depending on what was asked before it: on Ollama 0.40.7 the convenience question gave 3 quotes computed from
token 0 and 1 quote computed from token 620, after the liability question. With the server's host-RAM prompt cache off
(LLAMA_ARG_CACHE_RAM=0) the slot is the only place a prefix comes from, and a one-token raw prompt sent just before the
answer leaves it holding nothing the answer's prompt starts with. Measured 2026-10-21 on the serving machine: in both
orders every answer started at token 0 and each input gave one answer; the control, with no such prompt, started at 620
and gave the other.

These tests hold what Verity sends. The measurement is the model server's, and its record is in DECISIONS.md.
"""

from __future__ import annotations

import httpx
import pytest

from app import config
from app.providers.base import ProviderError
from app.providers.ollama import NEVER_CUT, OllamaProvider
from tests.support import through_get_and_post
from tests.test_model_wake import Endpoint


@pytest.fixture
def endpoint(monkeypatch: pytest.MonkeyPatch) -> Endpoint:
    server = Endpoint()
    monkeypatch.setattr(httpx, "get", server.get)
    monkeypatch.setattr(httpx, "post", server.post)
    monkeypatch.setattr(httpx, "stream", through_get_and_post)
    monkeypatch.setattr(config.settings, "ollama_url", "https://model.example.invalid")
    return server


def test_every_answer_is_preceded_by_a_prompt_that_shares_no_token_with_it(endpoint: Endpoint) -> None:
    OllamaProvider().generate_json("system", "user", {"type": "object"})
    OllamaProvider().generate_json("system", "another user", {"type": "object"})
    sent = [(url.rsplit("/", 1)[1], body) for url, body, _ in endpoint.posts]
    assert [name for name, _ in sent] == ["generate", "chat", "generate", "chat"]
    for name, body in sent:
        if name == "generate":
            # Raw, so no chat template is put in front of it: its first token is "x", never the template's opening.
            assert body["raw"] is True and body["prompt"] == "x" and body["options"]["num_predict"] == 1


def test_the_clean_start_loads_the_model_exactly_as_the_answer_does(endpoint: Endpoint) -> None:
    # Any load setting that differs makes the server start the model again: the answer would then be a cold start, which
    # looks like this fix and costs a load every time (a request without NEVER_CUT did exactly that on 0.40.7).
    provider = OllamaProvider()
    provider.generate_json("system", "user", {"type": "object"})
    (_, clean, clean_headers), (_, chat, chat_headers) = endpoint.posts
    assert {k: v for k, v in clean["options"].items() if k != "num_predict"} == chat["options"] == provider.options()
    assert {k: clean[k] for k in NEVER_CUT} == {k: chat[k] for k in NEVER_CUT} == NEVER_CUT
    assert clean["model"] == chat["model"] and clean_headers == chat_headers


def test_a_clean_start_the_endpoint_refuses_is_an_error_and_no_answer_is_asked_for(endpoint: Endpoint) -> None:
    endpoint.fail = True
    with pytest.raises(ProviderError, match="could not be prepared"):
        OllamaProvider().generate_json("system", "user", {"type": "object"})
    assert [url.rsplit("/", 1)[1] for url, _, _ in endpoint.posts] == ["generate"]


def test_control_a_wake_up_is_not_preceded_by_one(endpoint: Endpoint) -> None:
    # A wake-up computes one token of its own prompt to load the model; what its slot holds afterwards is cleared by the
    # answer's own clean start.
    OllamaProvider().wake()
    assert [url.rsplit("/", 1)[1] for url, _, _ in endpoint.posts] == ["generate"]
