"""A semantic version cannot be forgotten.

A run's identity carries four versions (runs.versions): what a status means, when a quote counts as found, which
sections are handed to the model, and what the model is handed of them. A document's reading carries a fifth, the
reader's. They only protect a reader of the record if the code behind each cannot change while its version stays the
same: then a fixed rule would hand back the answers the broken rule made, which is the defect the versions exist to end.

The code behind a version is the closure of its entry points (tests/code_closure.py): every function, class and
assignment their code reaches inside the app, found by following it. Until 2026-10-30 it was a list of files and
functions written by hand, and five edits outside it (a sub-reference pattern, a clause opening, the condition check
gated in the executor, a section's label, the prompt's window) changed statuses with every fingerprint green; 117 of 503
reached definitions sat in no boundary (stress test, architecture 2). What status a run's execution decides is the
policy's: the executor and everything it reaches but the other versions' entry points and what is named below as
recording rather than deciding.

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

import pytest

from app.analysis.service import INPUT_VERSION
from app.hashing import sha256_text
from app.ingest import PARSER_VERSION
from app.retrieval.lexical import RETRIEVAL_VERSION
from app.runs.status import POLICY_VERSION
from app.runs.versions import SEMANTIC_VERSIONS
from app.verify.spans import VERIFIER_VERSION
from tests.code_closure import Symbol, canonical, closure

# Where the code each version names begins. The alias table is versioned by its own hash, on every run; the prompt's
# text by its own; the model's build by its digest.
ENTRY_POINTS: dict[str, tuple[Symbol, ...]] = {
    "verifier_version": (("runs/service.py", "verify_evidence"),),
    "retrieval_version": (("runs/service.py", "_retrieve"),),
    "input_version": (
        ("analysis/service.py", "build_user_message"),
        ("analysis/service.py", "analyze"),  # the note a rejected answer is sent back with
        ("analysis/schema.py", "ANALYSIS_SCHEMA"),
        ("analysis/service.py", "load_prompt"),
        ("document_names.py", "run_prompt_name"),  # the contract's name as the model reads it
        ("providers/ollama.py", "OllamaProvider.chat_request"),  # the request: the schema as its format, thinking, no cut
    ),
    "policy_version": (("runs/service.py", "execute_run"),),
    "parser_version": (("ingest/__init__.py", "ingest"),),
}

# Reached from the executor, and recording, reporting or configuring rather than deciding a status. Each must be reached
# (a test says so); one that comes to decide leaves this list.
NON_DECIDING: dict[Symbol, str] = {
    ("runs/service.py", "_set_stage"): "records a stage",
    ("runs/service.py", "_note_stage"): "records a stage's note",
    ("runs/service.py", "_finish"): "records the end the executor chose",
    ("runs/service.py", "_fail"): "records a failure",
    ("runs/service.py", "finished_record"): "hashes the record decided",
    ("runs/service.py", "_retrieval_record"): "records what retrieval chose",
    ("runs/service.py", "_counted"): "words a count",
    ("runs/service.py", "fired_alias_groups"): "reports which alias groups fired",
    ("runs/service.py", "bound_to"): "binds the provider to the recorded model and decoding (the options' identity)",
    ("runs/service.py", "log"): "logs",
    ("runs/events.py", "bus"): "tells the page a stage moved",
    ("runs/owner.py", "this_process"): "names the process that holds a run",
    ("runs/transitions.py", "assert_transition"): "which stage may follow which",
    ("runs/versions.py", "stale_versions"): "whether this build may execute a run at all (test_version_order)",
    ("runs/versions.py", "SEMANTIC_VERSIONS"): "names the versions; it decides nothing",
    ("models.py", "Run"): "a row",
    ("models.py", "Finding"): "a row; the statuses it may hold are vocabularies status.py reaches itself",
    ("models.py", "EvidenceSpan"): "a row",
    ("models.py", "RunStage"): "a row",
    ("models.py", "DocumentAccess"): "a row",
    ("models.py", "new_id"): "an id",
    ("models.py", "utcnow"): "a time",
    ("config.py", "settings"): "configuration; what a run uses of it is recorded in its options (FrozenOptions)",
    ("hashing.py", "sha256_text"): "hashes",
    ("providers/base.py", "ProviderError"): "an error's type",
}

VERSIONS: dict[str, str] = {**SEMANTIC_VERSIONS, "parser_version": PARSER_VERSION}


def recorded_as(boundary: str, version: str) -> str:
    """A version's key in RECORDED: the reader's versions ("v17") are named apart from the verifier's ("v11")."""
    return f"reader {version}" if boundary == "parser_version" else version


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
    # policy-v17, 2026-10-30 (the adversarial stress test): a period is read as the text writes it or not at all (ranges,
    # lists, number words, invisible characters, negations, ambiguous periods anywhere in the quotes); a range compares in
    # one unit. v16 is released, so this is a bump. Re-recorded before release as each class of the stress test is closed,
    # and when the boundaries became closures of their entry points (the executor's, for the policy).
    "policy-v17": "e139fb7d79be932c",
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
    # punctuation alone is never found, a clause's letter keeps its case ("2(A)" is not "2(a)"), and the typed tier tries
    # every place its tokens occur, not only the first; and, from the fresh review, a word is read whole through its marks and
    # compared caseless, a sign of relation may stand against a letter, a currency may precede a decimal point, and a
    # sentence may end with no space; and, from the stress test, every default-ignorable character is read as absent, typeset
    # joints and mixed numbers make one number, a unit sign belongs to its number, a window's end and a fold's middle are no
    # boundaries, and a label is stripped only whole. v11 is not committed to main, so its fingerprint was replaced, not
    # bumped. Replayed over 17,603 recorded spans in 94 stores: none lost or gained; six typed spans now end on their own
    # quote's closing semicolon.
    "v11": "e0c252050f95ddaa",
    "retrieval-v1": "28dbb5a6d6459640",  # 2026-10-09: credentials on the embed call, then its failure said in plain words; what retrieval decides is unchanged
    # retrieval-v2, 2026-10-14: after the ranking, the sections the top three depend on where the contract says which
    # (runs.links: a definition, an amendment, a cited clause), at most two, within k full windows.
    # Re-recorded 2026-10-16 (blind contract stress test): the embedding call's failure sentence no longer carries the
    # exception's class, which goes to the log; which sections are handed over is unchanged.
    # Re-recorded 2026-10-19 (backend audit): a run's defined terms are read once for its seeds and no longer cached
    # between runs; old and new gave the same links on 580 cases over 150 EDGAR contracts.
    "retrieval-v2": "4829c7d19f9a7ba3",
    # retrieval-v3, 2026-10-30 (the stress test's retrieval corner): text read as the verifier reads it (quotation marks
    # folded, casefolded, a possessive its word); every section sharing a word with the query ranked while places remain;
    # an alias group fires only on a phrase that names its concept, never on its clause wording (aliases.WORDING); a
    # definition read in every pair of quotation marks, words of construction not terms, a term used in capitals; the
    # amendments of every handed section handed with it, a linked section's included (runs.links).
    # retrieval-v3 is not committed to main, so its fingerprint is replaced, not bumped, as the branch adds to it.
    "retrieval-v3": "272c76e0c6991632",
    # input-v1, 2026-10-30: the first version of what the model is handed. Recorded with the boundaries' move to closures,
    # which changed every fingerprint's definition; the versions above it are kept as they were recorded.
    "input-v1": "9579eac90fa902fa",
    # reader v17, 2026-10-30: the first reader version held to its code (columns, fields, branches, cells, checkboxes and
    # text boxes read as Word displays them; the PDF page read by position).
    "reader v17": "3a4543713ac44436",
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
    return repr(canonical(_without_docstrings(tree)))


def boundary(name: str) -> dict[Symbol, tuple[ast.stmt, ...]]:
    """The code a version names: its entry points' closure, short of the other versions' entry points and NON_DECIDING."""
    others = [entry for other, entries in ENTRY_POINTS.items() if other != name for entry in entries]
    return closure(ENTRY_POINTS[name], stop=[*others, *NON_DECIDING])


def fingerprint(name: str) -> str:
    parts = [f"{path}:{symbol}\n{canonical(list(nodes))!r}" for (path, symbol), nodes in sorted(boundary(name).items())]
    return sha256_text("\n\x1f\n".join(parts))[:16]


def test_every_version_has_entry_points_and_the_entry_points_are_the_versions() -> None:
    assert set(ENTRY_POINTS) == set(VERSIONS), "a version with no code named for it cannot be kept honest"
    assert {
        "policy_version": POLICY_VERSION,
        "verifier_version": VERIFIER_VERSION,
        "retrieval_version": RETRIEVAL_VERSION,
        "input_version": INPUT_VERSION,
    } == SEMANTIC_VERSIONS
    assert len(set(RECORDED.values())) == len(RECORDED), "two versions with one fingerprint: one of them was bumped for nothing, or copied"


def test_every_symbol_named_non_deciding_exists_and_is_reached_by_the_executor() -> None:
    """A stale entry would excuse nothing, and a missing one would hide a symbol that decides."""
    reached = closure(ENTRY_POINTS["policy_version"])
    assert sorted(set(NON_DECIDING) - set(reached)) == []


@pytest.mark.parametrize(
    "planted",
    [
        ("runs/prose.py", "SUB_REFERENCE"),  # a range after a handle read as a sub-reference
        ("ingest/sections.py", "clause_openings"),  # a whole number opening a clause without a title
        ("runs/service.py", "execute_run"),  # the condition check gated on guidance
        ("runs/service.py", "_label"),  # the label the verifier forgives before a quote
        ("analysis/service.py", "MAX_SECTION_CHARS_IN_PROMPT"),  # the window of a run that recorded none
        ("runs/status.py", "check_conditions"),
        ("verify/tokens.py", "tokenize"),
        ("retrieval/lexical.py", "tokenize"),
        # From the fresh review (2026-10-30): a field of the answer's schema, named only as a type, and the request the
        # provider sends, reached only through a method of the provider.
        ("analysis/schema.py", "FindingOut"),
        ("analysis/schema.py", "EvidenceOut"),
        ("providers/ollama.py", "OllamaProvider.chat_request"),
        ("providers/ollama.py", "NEVER_CUT"),
    ],
)
def test_the_stress_tests_planted_rule_changes_each_move_a_fingerprint(planted: Symbol) -> None:
    """Each of the five edits the stress test planted outside the hand-made boundaries, and three controls, is inside the
    code some version names, so editing it moves that version's fingerprint."""
    assert any(planted in boundary(name) for name in ENTRY_POINTS), f"{planted} decides and no version names it"


@pytest.mark.parametrize("name", sorted(ENTRY_POINTS))
def test_the_code_behind_a_version_is_the_code_that_version_was_recorded_for(name: str) -> None:
    version = recorded_as(name, VERSIONS[name])
    now = fingerprint(name)
    assert version in RECORDED, f"{name} is {version!r}, which has no fingerprint on record. Add to RECORDED in this file:\n    {version!r}: {now!r},"
    assert RECORDED[version] == now, (
        f"The code behind {name} changed and the version is still {version!r}.\n"
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
