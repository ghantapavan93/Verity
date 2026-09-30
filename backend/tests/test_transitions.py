"""The run lifecycle is a table; what the table does not list cannot happen."""

from __future__ import annotations

import pytest

from app.models import RUN_STAGES, TERMINAL_STAGES
from app.runs.transitions import ALLOWED, CREATED, IllegalTransition, assert_transition


def test_the_happy_path_and_every_early_exit_are_allowed() -> None:
    assert_transition(None, "reading")
    assert_transition("reading", "finding_evidence")
    assert_transition("finding_evidence", "checking")
    assert_transition("checking", "verifying")
    assert_transition("verifying", "complete")
    assert_transition("verifying", "unresolved")
    assert_transition("checking", "unresolved")  # the model answered that the sections do not contain the point
    for stage in ("reading", "finding_evidence", "checking", "verifying"):
        assert_transition(stage, "failed")
    assert_transition(None, "failed")


@pytest.mark.parametrize("terminal", sorted(TERMINAL_STAGES))
@pytest.mark.parametrize("new", sorted(RUN_STAGES))
def test_a_finished_run_cannot_move(terminal: str, new: str) -> None:
    with pytest.raises(IllegalTransition, match="finished"):
        assert_transition(terminal, new)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("previous", "new"),
    [
        (None, "checking"),
        ("reading", "checking"),
        ("checking", "reading"),
        ("verifying", "checking"),
        ("finding_evidence", "complete"),
        ("reading", "unresolved"),
    ],
)
def test_skipping_ahead_and_going_back_are_impossible(previous: str | None, new: str) -> None:
    with pytest.raises(IllegalTransition):
        assert_transition(previous, new)  # type: ignore[arg-type]


def test_the_table_covers_every_stage_and_nothing_else() -> None:
    assert set(ALLOWED) == set(RUN_STAGES) | {CREATED}
    assert all(targets <= set(RUN_STAGES) for targets in ALLOWED.values())
    assert all(not ALLOWED[stage] for stage in TERMINAL_STAGES)
