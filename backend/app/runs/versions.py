"""The versions of the code that decides what a run's answer means, in one place.

A run's identity already carried its inputs (document, guidance, question, prompt, decoding and retrieval options).
It did not carry the rules applied to them, so a status decided by rules that were later found wrong was handed
back, as the answer, to the same question asked after the rules were fixed: on 2026-10-02, 49 recorded runs carried
exactly the identity a new request would have. These three versions are recorded on every run from then on and are
part of its fingerprint. A change to what a status means, to what "verified" means, or to how sections are ranked
is a change of version, made by hand where the rule lives, and never a commit hash: two commits with the same rules
answer alike, and one commit can change none of them.

An old run is not touched by any of this. It keeps the options it recorded, opens as recorded, and is simply no longer
the answer to a new request.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Literal

from ..analysis.service import INPUT_VERSION
from ..retrieval.lexical import RETRIEVAL_VERSION
from ..verify.spans import VERIFIER_VERSION
from .status import POLICY_VERSION

SEMANTIC_VERSIONS: dict[str, str] = {
    "policy_version": POLICY_VERSION,  # runs.status and policy: how a status is decided
    "verifier_version": VERIFIER_VERSION,  # verify.spans: when a quote counts as found
    "retrieval_version": RETRIEVAL_VERSION,  # retrieval.lexical and the fallback: which sections are handed over
    "input_version": INPUT_VERSION,  # analysis.service: what the model is handed of them, and how its answer is read (2026-10-30)
}


Order = Literal["current", "earlier", "unknown"]
_NUMBERED = re.compile(r"(?P<rule>[a-z]+-)?v(?P<number>\d+)")


def compare_version(recorded: object, current: str) -> Order:
    """Where a recorded version stands against the build's own: its rules ("current"), rules it has replaced
    ("earlier"), or rules it does not know ("unknown"), by the number each version ends in, never by inequality.

    Compared by inequality, a version from a newer build read as one this build had replaced: on the documented
    rollback, a844ebf's trust layer called verifier v11 "earlier rules" and established its spans by running v10
    (stress test, 2026-10-30). Nothing recorded is earlier (a run made before versions were recorded); a form this
    build cannot read, or another rule's version, is unknown."""
    if not recorded:
        return "earlier"
    seen, own = _NUMBERED.fullmatch(str(recorded)), _NUMBERED.fullmatch(current)
    if seen is None or own is None or seen["rule"] != own["rule"]:
        return "unknown"
    number, current_number = int(seen["number"]), int(own["number"])
    return "current" if number == current_number else "earlier" if number < current_number else "unknown"


def _differences(options: Mapping[str, object], orders: frozenset[Order]) -> list[str]:
    return [
        f"{name.replace('_', ' ')} {options.get(name) or 'not recorded'} then, {current} now"
        for name, current in SEMANTIC_VERSIONS.items()
        if compare_version(options.get(name), current) in orders
    ]


def stale_versions(options: Mapping[str, object]) -> list[str]:
    """What separates the versions a run was created under from the code about to execute it; empty when nothing does.
    A run that recorded no version was created before versions were recorded, which is as stale as a run can be."""
    return _differences(options, frozenset({"earlier", "unknown"}))


def earlier_versions(options: Mapping[str, object]) -> list[str]:
    """The versions a run recorded that this build has replaced: its evidence can be asked of today's verifier."""
    return _differences(options, frozenset({"earlier"}))


def unknown_versions(options: Mapping[str, object]) -> list[str]:
    """The versions a run recorded that this build does not know, as after a rollback: nothing of it is re-checked."""
    return _differences(options, frozenset({"unknown"}))


def without_versions(options: Mapping[str, float | int | str]) -> dict[str, float | int | str]:
    """The options as a run recorded them before versions were part of its identity: how the record made until
    2026-10-02 is still found by what it was asked (the golden report reads its recordings this way)."""
    return {name: value for name, value in options.items() if name not in SEMANTIC_VERSIONS}
