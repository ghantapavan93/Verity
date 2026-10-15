"""Every model output a run keeps is stored, or reconstructable, together with the exact input that produced it; a
pack, an explanation and a record never claim more than that (F-14, war room 2026-10-13).

A first answer that fails validation is followed by a corrected retry: the first message plus a note quoting why the
answer was rejected. The run keeps the second answer and neither the first answer nor that message. Until this file,
the evidence pack packed the first message as "the exact messages the model was given", verify.py printed PASS for it,
and the explanation called it the exact input. A transport retry resends the same message and must still PASS.
"""

from __future__ import annotations

import io
import json
import subprocess
import sys
import zipfile
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app import db as db_module
from app.analysis import service as analysis_service
from app.application.reconstruct_input import reconstruct_input
from app.db import SessionLocal
from app.models import Run, RunStage
from app.providers.base import Generation, ProviderError
from tests.support import FakeProvider, upload_and_ask

QUESTION = "How much notice does the customer need to give to terminate for convenience?"
MODEL_INPUT_PASS = "PASS model input:"

# What one call can do: answer validly, answer invalidly (wrong shape, or not JSON at all), or fail in transport.
VALID, INVALID, TRANSPORT = "V", "I", "E"
# What one validation round can be: a call, or a transport failure and its one retry (two failures end the run).
ROUNDS = ((VALID,), (INVALID,), (TRANSPORT, VALID), (TRANSPORT, INVALID), (TRANSPORT, TRANSPORT))


def retry_shapes() -> list[tuple[str, ...]]:
    """Every sequence of call outcomes analyze can see: a round that ends invalid is followed by one more round."""
    shapes: list[tuple[str, ...]] = []
    for first in ROUNDS:
        if first[-1] != INVALID:
            shapes.append(first)
            continue
        shapes += [first + second for second in ROUNDS]
    return shapes


SHAPES = retry_shapes()


def rounds_of(outcomes: tuple[str, ...]) -> int:
    """How many validation rounds a shape makes: a transport failure and its retry are one round."""
    rounds = index = 0
    while index < len(outcomes):
        rounds += 1
        index += 2 if outcomes[index] == TRANSPORT else 1
    return rounds


class Script:
    """The provider's answers in a fixed order. Records each call's user message and whether it returned an answer."""

    def __init__(self, provider: FakeProvider, outcomes: tuple[str, ...]) -> None:
        self.provider = provider
        self.outcomes = list(outcomes)
        self.calls: list[tuple[str, bool]] = []
        self.invalid = 0

    def __call__(self, system: str, user: str, schema: dict[str, Any]) -> Generation:
        outcome = self.outcomes.pop(0)
        self.calls.append((user, outcome != TRANSPORT))
        if outcome == TRANSPORT:
            raise ProviderError("Ollama request failed: timed out")
        if outcome == INVALID:
            self.invalid += 1
            # Both kinds a validation round rejects: well-formed JSON in the wrong shape, then no JSON at all.
            text = '{"findings": "not a list"}' if self.invalid == 1 else "this is not the JSON you asked for"
            return Generation(text=text, input_tokens=10, output_tokens=3, latency_ms=5.0, model=self.provider.model)
        return FakeProvider.generate_json(self.provider, system, user, schema)

    @property
    def answered_message(self) -> str | None:
        """The user message of the last call that returned an answer: the input of the output the run keeps."""
        answered = [user for user, returned in self.calls if returned]
        return answered[-1] if answered else None


def run_shape(client: TestClient, monkeypatch: pytest.MonkeyPatch, outcomes: tuple[str, ...]) -> tuple[Script, str]:
    monkeypatch.setattr(analysis_service, "PROVIDER_RETRY_DELAY_S", 0.0)
    script = Script(client.provider, outcomes)
    monkeypatch.setattr(client.provider, "generate_json", script)
    run_id = upload_and_ask(client, QUESTION)["run_id"]
    assert script.outcomes == [], "the shape was not used up: analyze made fewer calls than it describes"
    return script, run_id


def open_pack(client: TestClient, run_id: str, folder: Path) -> tuple[dict[str, Any], set[str], subprocess.CompletedProcess[str]]:
    with zipfile.ZipFile(io.BytesIO(client.get(f"/api/runs/{run_id}/evidence-pack").content)) as pack:
        names = set(pack.namelist())
        record = json.loads(pack.read("run.json"))
        pack.extractall(folder)
    checked = subprocess.run([sys.executable, str(folder / "verify.py")], capture_output=True, text=True, cwd=folder, check=False)
    return record, names, checked


def checking_stage(run_id: str) -> tuple[int | None, int | None, str | None]:
    with SessionLocal() as session:
        row = session.query(RunStage).filter_by(run_id=run_id, stage="checking").one()
        run = session.get(Run, run_id)
        assert run is not None
        return row.attempt, row.rounds, run.raw_output


# --------------------------------------------------------------------------- the original case (ENG-04), kept


def test_eng04_an_answer_given_to_the_corrected_retry_is_never_packed_as_given_to_the_first_message(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    script, run_id = run_shape(client, monkeypatch, (INVALID, VALID))
    detail = client.get(f"/api/runs/{run_id}/detail").json()
    checking = next(s for s in detail["stages"] if s["stage"] == "checking")
    assert detail["stage"] == "complete" and checking["attempt"] == 2
    assert script.answered_message != script.calls[0][0], "the answer was given to the corrected message, not the first"

    # The pack and its checker: no message is offered as the answer's input, and no PASS vouches for one.
    record, names, checked = open_pack(client, run_id, tmp_path)
    model_input = record["model_input"]
    assert checked.returncode == 0, checked.stdout + checked.stderr
    assert MODEL_INPUT_PASS not in checked.stdout, "verify.py vouches for an input the answer was not given"
    assert model_input["reconstructable"] is False, "the pack calls the first message the input of an answer given to the second"
    assert not {"model_input/system.txt", "model_input/user.txt"} & names, "no message is packed as the answer's input"
    assert model_input["system_file"] is None and model_input["user_file"] is None
    assert "validation round 2" in model_input["problem"] and "not reconstructable" in model_input["problem"]
    assert "NOTE the model input could not be rebuilt from the record: the recorded answer came from validation round 2" in checked.stdout
    assert model_input["validation_rounds"] == 2 and model_input["model_calls"] == 2

    # The explanation says the same; no byte is misstated: the first message still hashes to what was recorded.
    explanation = client.get(f"/api/runs/{run_id}/explanation").json()
    assert explanation["reconstruction"]["reconstructable"] is False and "validation round 2" in explanation["reconstruction"]["problem"]
    assert explanation["reproducibility"]["inputMatches"] is True
    with SessionLocal() as session:
        rebuilt = reconstruct_input(session, run_id)
    assert rebuilt.matches and not rebuilt.answered and rebuilt.user == script.calls[0][0]

    # The run record keeps calls and rounds apart, and its stage sentence says where the answer came from.
    assert "after a rejected first answer" in checking["detail"]
    assert checking_stage(run_id)[:2] == (2, 2)


# --------------------------------------------------------------------------- the property, over every retry shape


def test_the_shapes_are_every_path_through_analyze() -> None:
    # Two rounds of at most one transport retry each: three shapes end in the first round, ten reach the second.
    assert len(SHAPES) == len(set(SHAPES)) == 13
    assert all(1 <= len(shape) <= 4 for shape in SHAPES)


@pytest.mark.parametrize("outcomes", SHAPES, ids=["-".join(shape) for shape in SHAPES])
def test_a_pack_holds_the_input_of_the_kept_answer_or_says_it_cannot(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, outcomes: tuple[str, ...]
) -> None:
    script, run_id = run_shape(client, monkeypatch, outcomes)
    first_message = script.calls[0][0]
    kept = client.get(f"/api/runs/{run_id}/detail").json()["rawOutput"] is not None
    answered = script.answered_message if kept else None
    the_kept_answer_had_the_first_message = answered is None or answered == first_message

    record, names, checked = open_pack(client, run_id, tmp_path)
    model_input = record["model_input"]
    assert checked.returncode == 0, checked.stdout + checked.stderr  # nothing true is failed either
    assert model_input["reconstructable"] is the_kept_answer_had_the_first_message
    if model_input["reconstructable"]:
        user = (tmp_path / "model_input" / "user.txt").read_text(encoding="utf-8")
        assert user == (answered if answered is not None else first_message), "the packed message is the one the kept answer was given"
        assert MODEL_INPUT_PASS in checked.stdout
    else:
        assert "model_input/user.txt" not in names and model_input["problem"]
        assert MODEL_INPUT_PASS not in checked.stdout and "not reconstructable" in checked.stdout

    explanation = client.get(f"/api/runs/{run_id}/explanation").json()
    assert explanation["reconstruction"]["reconstructable"] is the_kept_answer_had_the_first_message
    assert explanation["reproducibility"]["inputMatches"] is True, "the first message hashes to the record in every shape"

    # The run's own record keeps calls and rounds apart; a round is a distinct message, a transport retry resends one.
    assert len({user for user, _ in script.calls}) == rounds_of(outcomes)
    if kept:
        assert checking_stage(run_id)[:2] == (len(outcomes), rounds_of(outcomes))


# --------------------------------------------------------------------------- controls: what must still PASS


@pytest.mark.parametrize("outcomes", [(VALID,), (TRANSPORT, VALID)], ids=["one-round", "transport-retry"])
def test_control_one_round_and_a_transport_retry_still_pass(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, outcomes: tuple[str, ...]
) -> None:
    script, run_id = run_shape(client, monkeypatch, outcomes)
    record, names, checked = open_pack(client, run_id, tmp_path)
    model_input = record["model_input"]
    assert checked.returncode == 0 and f"{MODEL_INPUT_PASS} rebuilt messages hash to what the run recorded" in checked.stdout
    assert "PASS context slice" in checked.stdout and "NOTE the model input" not in checked.stdout
    assert model_input["reconstructable"] is True and model_input["problem"] is None
    assert {"model_input/system.txt", "model_input/user.txt"} <= names
    assert (tmp_path / "model_input" / "user.txt").read_text(encoding="utf-8") == script.answered_message
    reconstruction = client.get(f"/api/runs/{run_id}/explanation").json()["reconstruction"]
    assert reconstruction["reconstructable"] is True and reconstruction["problem"] is None
    # New in the record: calls and rounds apart (a transport retry is a second call in the same round).
    assert model_input["validation_rounds"] == 1 and model_input["model_calls"] == len(outcomes)


# --------------------------------------------------------------------------- historical records, read as they are


def _as_written_before_rounds(run_id: str, *, attempt: int | str | None = "keep") -> None:
    """A checking stage as every run before 2026-10-13 wrote it: no rounds. Made by hand, the triggers forbid it; they
    are put back, so the reads below would fail if anything tried to rewrite the record."""
    with db_module.engine.begin() as connection:
        connection.exec_driver_sql("DROP TRIGGER trg_run_stages_no_update_when_finished")
        connection.exec_driver_sql("UPDATE run_stages SET rounds = NULL WHERE run_id = ? AND stage = 'checking'", (run_id,))
        if attempt != "keep":
            connection.exec_driver_sql("UPDATE run_stages SET attempt = ? WHERE run_id = ? AND stage = 'checking'", (attempt, run_id))
    db_module.ensure_immutability(db_module.engine)


@pytest.mark.parametrize(
    ("outcomes", "attempt", "rounds", "answered"),
    [
        ((VALID,), "keep", 1, True),  # one call is one round: the old record still PASSES
        ((TRANSPORT, VALID), "keep", None, False),  # two calls: a transport retry or a corrected one; the record cannot say
        ((INVALID, VALID), "keep", None, False),
        ((INVALID, INVALID), "keep", 2, False),  # invalid_output: every round was used, so the answer is round 2's
        ((TRANSPORT, INVALID, VALID), "keep", 2, False),  # three calls do not fit in one round
        ((VALID,), None, None, False),  # an answer kept with no calls noted (the process ended between the two writes)
    ],
    ids=["1-call", "2-calls-transport", "2-calls-corrected", "invalid-output", "3-calls", "calls-not-noted"],
)
def test_an_old_record_reads_honestly_and_is_not_rewritten(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    outcomes: tuple[str, ...],
    attempt: int | str | None,
    rounds: int | None,
    answered: bool,
) -> None:
    _, run_id = run_shape(client, monkeypatch, outcomes)
    _as_written_before_rounds(run_id, attempt=attempt)
    before = checking_stage(run_id)
    with SessionLocal() as session:
        rebuilt = reconstruct_input(session, run_id)
    assert rebuilt.matches, "the first message rebuilds and hashes to the record in every case"
    assert rebuilt.rounds == rounds and rebuilt.answered is answered
    record, _, checked = open_pack(client, run_id, tmp_path)
    assert record["model_input"]["reconstructable"] is answered and (MODEL_INPUT_PASS in checked.stdout) is answered
    if rounds is None:
        assert "cannot show which input the recorded answer was given" in record["model_input"]["problem"]
    assert checked.returncode == 0, checked.stdout
    assert checking_stage(run_id) == before == (before[0], None, before[2]), "reading an old record wrote nothing to it"


def test_a_run_that_kept_no_answer_still_packs_and_checks_its_first_message(client: TestClient, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    # The provider failed twice: no output was kept, so there is no answer whose input could be another message.
    _, run_id = run_shape(client, monkeypatch, (TRANSPORT, TRANSPORT))
    assert checking_stage(run_id) == (None, None, None)
    record, _, checked = open_pack(client, run_id, tmp_path)
    assert record["model_input"]["reconstructable"] is True and MODEL_INPUT_PASS in checked.stdout
