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
    "policy_version": ("runs/status.py", "policy/durations.py", "policy/proof.py", "runs/values.py", "runs/relations.py"),  # values: policy-v6; relations: v11
    "verifier_version": ("verify/spans.py", "verify/tokens.py", ("runs/service.py", "verify_evidence")),
    "retrieval_version": (
        "retrieval/lexical.py",
        "retrieval/hybrid.py",
        ("retrieval/aliases.py", "expand_query"),  # the table itself is versioned by its own hash, on every run
        ("retrieval/aliases.py", "_phrase_in"),
        ("runs/service.py", "_retrieve"),  # the opening-sections fallback
        "runs/links.py",  # retrieval-v2: the sections the ranked ones depend on
    ),
}

# version -> fingerprint of the code it names. One line per version that ever recorded a run.
RECORDED: dict[str, str] = {
    "policy-v2": "f680f205d5dca0c0",
    "policy-v3": "157d0c3d7711b18b",
    "policy-v4": "b88a4017c8ebfd98",
    "policy-v5": "85ac4239ce9ffd27",
    "policy-v6": "f10ef3734b729ff5",  # 2026-10-10: a pass stating a value its evidence does not show is lowered (runs.values joins the boundary)
    "policy-v7": "10f56e2f09548f97",  # 2026-10-10: the party check, not adopted (57e4dae); its runs (the /break headline) keep the name, never reused
    # policy-v8, 2026-10-13: a pass names the sections its sentence points at that the model was not handed, compared or
    # not; re-recorded the same day for runs.status.basis, which reads a decision and makes none.
    "policy-v8": "5c39eda6f3101a65",
    # policy-v9, 2026-10-14: periods code cannot compare (calendar against Business Days, months against days) send a
    # pass the model proposed to review with that reason (the legal pilot's H4-Q5).
    "policy-v9": "97bab10c1b008ab3",
    # policy-v10, 2026-10-14: periods in units that do not convert compared as calendar-day ranges; Business Days and bare
    # "days" as the contract's own words define them (policy.durations.calendar_days, business_week, day_convention).
    # Amended before any release (first-visitor acceptance test, 2026-10-14): a definition that lists its weekdays is
    # read, and code says what it could not read rather than that the contract has no definition. policy-v10 was never
    # committed or deployed (the released line is policy-v6), so no stored run was decided under the earlier text.
    "policy-v10": "8c22b18b5f0310e8",
    # policy-v11, 2026-10-14 (the intent-first mission): the contract's replacement and precedence statements are located
    # and recorded with the run (runs.relations); an answer to a question about the agreement as it stands, quoting text
    # the contract replaced in full and not the replacement, is needs review set by code. A limit or a ranking is a concern
    # only. Amended before release (owner-note review, 2026-10-14): a question naming a time is a concern, not read at the
    # run's date; quoting the replacement with only the replaced values is a concern; a month start is read, not raised on.
    # policy-v11 was never committed, so its fingerprint was replaced rather than bumped.
    "policy-v11": "b3728ef49122b641",
    # policy-v12, 2026-10-15: the time a question asks at ("in June 2026") counts as stated when the answer repeats it, so
    # the status no longer depends on whether the answer says it (values.frame_times). v11 is committed, so this is a bump.
    "policy-v12": "995405407aa14b15",
    # policy-v13, 2026-10-15: the model's stated value is its stance between a replaced clause and its replacement; a
    # section handle the model was not given is marked and lowers a pass. v12 is committed, so this is a bump.
    "policy-v13": "9e5f78fbbf5ead56",
    # policy-v14, 2026-10-16 (the blind contract stress test): one value given to every party where the passages give
    # several, and a quote whose own sentence carries a condition the answer leaves out, are needs review set by code.
    # v13 is committed, so this is a bump. Re-recorded the same day for a reworded reason (the answer's party phrase
    # quoted, not lowercased).
    "policy-v14": "51c5b04897ada0cf",
    # policy-v15, 2026-10-17 (the amendment challenge): the number of an instrument named with a mark ("Amendment No.
    # 1") is not a value the answer states, in the value check and in runs.relations. v14 is committed, so this is a bump.
    # Re-recorded the same day, before any release: five fresh reviews rejected broader readings; this one marks names only
    # and keeps v14's section pointers (DECISIONS.md).
    "policy-v15": "fdbe664659bd28b0",
    # policy-v16, 2026-10-17 (the owner's decision on the amendment challenge): an answer quoting the replacement with only
    # the replaced values (relations' old_value) is needs review set by code. v15 is committed and pushed, so this is a bump.
    "policy-v16": "c185473f506d484f",
    "v6": "d73590a20b16ec34",
    "v7": "e9127a10c244afaa",
    # v8, 2026-10-13: no span begins or ends inside a number; a number's sign is part of its value (F-03). Re-recorded the
    # same day for the verification pass, which only scopes the memo (18,717 recorded spans replayed, none changed).
    "v8": "e72813eba0872169",
    # v9, 2026-10-14: an amount with a magnitude letter ("$5M", "USD 10K") or a currency in letters against "$" ("US$")
    # is a number, with its sign; inside a signed number no edge falls at a space (legal evaluation B1).
    "v9": "6753ff2523e274dc",
    # v10, 2026-10-14: a short label after a minus sign or inside an opening parenthesis ("-Ksh 5M", "(RM5M)") is part of
    # the number, so its sign is kept whatever currency it names (the pilot's B1 residual).
    "v10": "d895b935b9c94210",
    # v11, 2026-10-30 (the break audit): a comparator, a plus sign and a leading decimal point belong to a number, "/" and
    # ":" join its digits, the typed tier compares the end of a sentence, a combining mark or a joiner belongs to its word,
    # and punctuation alone is never found. Replayed over 17,603 recorded spans in 94 stores: none lost or gained; six
    # typed spans now end on their own quote's closing semicolon.
    "v11": "46b0058accc6124d",
    "retrieval-v1": "28dbb5a6d6459640",  # 2026-10-09: credentials on the embed call, then its failure said in plain words; what retrieval decides is unchanged
    # retrieval-v2, 2026-10-14: after the ranking, the sections the top three depend on where the contract says which
    # (runs.links: a definition, an amendment, a cited clause), at most two, within k full windows.
    # Re-recorded 2026-10-16 (blind contract stress test): the embedding call's failure sentence no longer carries the
    # exception's class, which goes to the log; which sections are handed over is unchanged.
    # Re-recorded 2026-10-19 (backend audit): a run's defined terms are read once for its seeds and no longer cached
    # between runs; old and new gave the same links on 580 cases over 150 EDGAR contracts.
    "retrieval-v2": "4829c7d19f9a7ba3",
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
