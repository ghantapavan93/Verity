"""The run's lifecycle as an explicit transition table, the smallest mechanism that makes an impossible transition
impossible: a finished run cannot move, a run cannot skip back, and the only ways out of each stage are named.

    created ─▶ reading ─▶ finding_evidence ─▶ checking ─▶ verifying ─▶ complete | unresolved
                  │               │               │            │
                  └───────────────┴───────────────┴────────────┴─────▶ failed

"created" is the run row before its first stage row; "unresolved" may also follow checking directly (the model
answered that the sections do not contain the point, so there is nothing to verify). No framework: a mapping and
one function, checked wherever a stage is written.
"""

from __future__ import annotations

from ..models import TERMINAL_STAGES, RunStageName

CREATED = "created"

ALLOWED: dict[str, frozenset[str]] = {
    CREATED: frozenset({"reading", "failed"}),
    "reading": frozenset({"finding_evidence", "failed"}),
    "finding_evidence": frozenset({"checking", "failed"}),
    "checking": frozenset({"verifying", "unresolved", "failed"}),
    "verifying": frozenset({"complete", "unresolved", "failed"}),
    "complete": frozenset(),
    "unresolved": frozenset(),
    "failed": frozenset(),
}


class IllegalTransition(RuntimeError):
    pass


def assert_transition(previous: str | None, new: RunStageName) -> None:
    """Raise when a run at ``previous`` (None: no stage row yet) may not enter ``new``."""
    origin = previous or CREATED
    if new not in ALLOWED.get(origin, frozenset()):
        if origin in TERMINAL_STAGES:
            raise IllegalTransition(f"a {origin} run is finished and cannot enter {new}")
        raise IllegalTransition(f"a run at {origin} cannot enter {new}; it may enter {', '.join(sorted(ALLOWED.get(origin, ()))) or 'nothing'}")
