"""A semantic version cannot be forgotten.

A run's identity carries three versions (runs.versions): what a status means, when a quote counts as found, which
sections are handed to the model. They only protect a reader of the record if the code behind each cannot change
while its version stays the same: then a fixed rule would hand back the answers the broken rule made, which is the
defect the versions exist to end.

So each version is recorded here beside a fingerprint of the code it names. Change that code and the test fails until
someone decides, by hand and in this file, which of two things happened:

  the rule changed       bump the version where it is declared, and add the new version and fingerprint below
                         (never replace an old one: runs recorded under it still carry its name);
  the rule did not       (a rename, a reworded reason, a refactor): replace the fingerprint of the current version.

The fingerprint is of the syntax tree with docstrings removed, so comments, formatting and documentation never trip
it, and it is written out by this file, not by `ast.dump`, so it does not move with the Python that runs the test.
Nothing here is read at runtime, and nothing is a commit hash.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from app.hashing import sha256_text
from app.retrieval.lexical import RETRIEVAL_VERSION
from app.runs.status import POLICY_VERSION
from app.runs.versions import SEMANTIC_VERSIONS
from app.verify.spans import VERIFIER_VERSION

APP = Path(__file__).resolve().parents[1] / "app"

# What each version names: whole modules, or one function of a module that also does other things.
BOUNDARIES: dict[str, tuple[str | tuple[str, str], ...]] = {
    "policy_version": ("runs/status.py", "policy/durations.py", "policy/proof.py"),
    "verifier_version": ("verify/spans.py", "verify/tokens.py", ("runs/service.py", "verify_evidence")),
    "retrieval_version": (
        "retrieval/lexical.py",
        "retrieval/hybrid.py",
        ("retrieval/aliases.py", "expand_query"),  # the table itself is versioned by its own hash, on every run
        ("retrieval/aliases.py", "_phrase_in"),
        ("runs/service.py", "_retrieve"),  # the opening-sections fallback
    ),
}

# version -> fingerprint of the code it names. One line per version that ever recorded a run.
RECORDED: dict[str, str] = {
    "policy-v2": "f680f205d5dca0c0",
    "policy-v3": "157d0c3d7711b18b",
    "v6": "d73590a20b16ec34",
    "v7": "e9127a10c244afaa",
    "retrieval-v1": "12dfe9555e1c2275",  # 2026-10-09: the embed call carries the endpoint's credentials; what retrieval decides is unchanged
}


def _without_docstrings(tree: ast.AST) -> ast.AST:
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)) and node.body:
            first = node.body[0]
            if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant) and isinstance(first.value.value, str):
                node.body = node.body[1:] or [ast.Pass()]
    return tree


def fingerprint_of(source: str, symbol: str | None = None) -> str:
    """The syntax of a module, or of one top-level definition in it, with docstrings, comments and layout left out."""
    tree: ast.AST = ast.parse(source)
    if symbol is not None:
        assert isinstance(tree, ast.Module)
        found = [node for node in tree.body if isinstance(node, (ast.FunctionDef, ast.ClassDef)) and node.name == symbol]
        assert len(found) == 1, f"{symbol} is not a top-level definition; the boundary moved and this file must say where to"
        tree = found[0]
    return repr(_canonical(_without_docstrings(tree)))


def _canonical(node: object) -> object:
    """The tree as nested tuples of node names and the fields that carry something. Positions are not fields, and an
    empty or absent field is left out, so a Python that adds an optional field to a node does not change the result."""
    if isinstance(node, ast.AST):
        return (type(node).__name__, tuple((name, _canonical(value)) for name, value in ast.iter_fields(node) if value not in (None, [], ())))
    if isinstance(node, list):
        return tuple(_canonical(item) for item in node)
    return repr(node)


def fingerprint(boundary: str) -> str:
    parts = []
    for entry in BOUNDARIES[boundary]:
        path, symbol = (entry, None) if isinstance(entry, str) else entry
        parts.append(f"{path}:{symbol or '*'}\n{fingerprint_of((APP / path).read_text(encoding='utf-8'), symbol)}")
    return sha256_text("\n\x1f\n".join(parts))[:16]


def test_every_semantic_version_has_a_boundary_and_the_boundaries_are_the_versions() -> None:
    assert set(BOUNDARIES) == set(SEMANTIC_VERSIONS), "a version with no code named for it cannot be kept honest"
    assert {"policy_version": POLICY_VERSION, "verifier_version": VERIFIER_VERSION, "retrieval_version": RETRIEVAL_VERSION} == SEMANTIC_VERSIONS
    assert len(set(RECORDED.values())) == len(RECORDED), "two versions with one fingerprint: one of them was bumped for nothing, or copied"


@pytest.mark.parametrize("boundary", sorted(BOUNDARIES))
def test_the_code_behind_a_version_is_the_code_that_version_was_recorded_for(boundary: str) -> None:
    version = SEMANTIC_VERSIONS[boundary]
    now = fingerprint(boundary)
    assert version in RECORDED, f"{boundary} is {version!r}, which has no fingerprint on record. Add to RECORDED in this file:\n    {version!r}: {now!r},"
    assert RECORDED[version] == now, (
        f"The code behind {boundary} changed and the version is still {version!r}.\n"
        f"  If what it decides changed: bump the version where it is declared and add  {'<new version>'!r}: {now!r}  to RECORDED.\n"
        f"  If it did not (a rename, a reworded reason, a refactor): replace the fingerprint of {version!r} with {now!r}.\n"
        "Until one of the two is done by hand, runs made under the old rule would be handed back as answers under the new one."
    )


def test_the_fingerprint_sees_a_changed_rule_and_not_a_changed_comment() -> None:
    rule = 'def meets(a: int, b: int) -> bool:\n    """Whether a meets the floor b."""\n    return a >= b  # a floor\n'
    assert fingerprint_of(rule) == fingerprint_of(rule.replace("# a floor", "# the least that will do"))
    assert fingerprint_of(rule) == fingerprint_of(rule.replace("Whether a meets the floor b.", "Rewritten documentation."))
    assert fingerprint_of(rule) == fingerprint_of(rule.replace("    return a >= b", "    return (\n        a >= b\n    )"))
    assert fingerprint_of(rule) != fingerprint_of(rule.replace("a >= b", "a > b")), "a comparison that changed is a rule that changed"
    assert fingerprint_of(rule) != fingerprint_of(rule + "\n\nLIMIT = 2\n")
    two = rule + "\n\ndef other() -> int:\n    return 1\n"
    assert fingerprint_of(two, "meets") == fingerprint_of(two.replace("return 1", "return 2"), "meets"), "only the named function is read"
    assert fingerprint_of(two, "meets") != fingerprint_of(two.replace("a >= b", "a > b"), "meets")
