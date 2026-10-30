"""How the readers name a file, and where they take what a reader does not see (stress test, 2026-10-30, second wave).

(1) A file named only with characters that draw nothing (a Hangul filler, a joiner, a direction mark) was stored under
that name instead of "document": base_name asked `visible_text(name).strip()`, which keeps them on purpose. The one test
of whether text shows anything (`has_visible_text`) now lives with the readers that define what is unseen, and names use
it. Control: a name in any script that shows something is kept.

(2) The readers take the characters a reader does not see from app.unseen, the one definition below every layer that
policy and the memo read too, instead of writing their own copy.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from app import unseen
from app.ingest import base_name, invisible

BACKEND = Path(__file__).resolve().parents[1]


# ---------------------------------------------------------------- (1) a name that shows nothing


@pytest.mark.parametrize(
    ("given", "named"),
    [
        ("\u3164", "document"),
        ("\u200d\u200e", "document"),
        ("\u200d\u200e.txt", "document.txt"),
        ("\u3164\u115f.pdf", "document.pdf"),
        ("\ufe0f\u034f.docx", "document.docx"),
        ("   .txt", "document.txt"),
    ],
)
def test_a_name_that_draws_nothing_is_named_document(given: str, named: str) -> None:
    assert base_name(given) == named


@pytest.mark.parametrize("given", ["Lease.pdf", "محمد.docx", "\U0001f469\u200d⚖\ufe0f.txt", "José terms.txt", "readme"])
def test_control_a_name_that_shows_something_is_kept(given: str) -> None:
    assert base_name(given) == given


def test_has_visible_text_is_the_readers_one_definition() -> None:
    from app.application import visible_input

    assert visible_input.has_visible_text is invisible.has_visible_text
    assert not invisible.has_visible_text("\u200d \u3164⠀") and invisible.has_visible_text("Pat")


# ---------------------------------------------------------------- (2) one definition of what is unseen


def test_the_readers_take_what_is_unseen_from_the_one_definition() -> None:
    assert (invisible.JOINERS, invisible.MARKS, invisible.IGNORABLE) == (unseen.JOINERS, unseen.MARKS, unseen.IGNORABLE)
    tree = ast.parse((BACKEND / "app" / "ingest" / "invisible.py").read_text(encoding="utf-8"))
    assigned = {target.id for node in tree.body if isinstance(node, ast.Assign) for target in node.targets if isinstance(target, ast.Name)}
    assert not assigned & {"JOINERS", "MARKS", "IGNORABLE"}, "ingest/invisible.py writes its own copy"
    imported = {alias.name for node in tree.body if isinstance(node, ast.ImportFrom) and node.module == "unseen" for alias in node.names}
    assert {"JOINERS", "MARKS", "IGNORABLE"} <= imported
