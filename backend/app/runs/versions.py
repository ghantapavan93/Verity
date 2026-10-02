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

from collections.abc import Mapping

from ..retrieval.lexical import RETRIEVAL_VERSION
from ..verify.spans import VERIFIER_VERSION
from .status import POLICY_VERSION

SEMANTIC_VERSIONS: dict[str, str] = {
    "policy_version": POLICY_VERSION,  # runs.status and policy: how a status is decided
    "verifier_version": VERIFIER_VERSION,  # verify.spans: when a quote counts as found
    "retrieval_version": RETRIEVAL_VERSION,  # retrieval.lexical and the fallback: which sections are handed over
}


def stale_versions(options: Mapping[str, object]) -> list[str]:
    """What separates the versions a run was created under from the code about to execute it; empty when nothing does.
    A run that recorded no version was created before versions were recorded, which is as stale as a run can be."""
    return [
        f"{name.replace('_', ' ')} {options.get(name) or 'not recorded'} then, {current} now"
        for name, current in SEMANTIC_VERSIONS.items()
        if options.get(name) != current
    ]


def without_versions(options: Mapping[str, float | int | str]) -> dict[str, float | int | str]:
    """The options as a run recorded them before versions were part of its identity: how the record made until
    2026-10-02 is still found by what it was asked (the golden report reads its recordings this way)."""
    return {name: value for name, value in options.items() if name not in SEMANTIC_VERSIONS}
