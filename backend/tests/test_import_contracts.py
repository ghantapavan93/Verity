"""The verifier's purity, and the import contracts that hold it, are checked whole (stress test, 2026-10-30).

The verifier contract in .importlinter was "independence" over one module, which nothing can break: eleven planted
imports into spans.py (the providers, the models, the store, the settings) each kept all three contracts, and app.trust
and app.serving sat in no contract at all. Now the verifier is forbidden every other module of the app, this file checks
that the forbidden list names every one (a module added later cannot slip past it), that every module sits in the
layers contract or is exempt with its reason, and that the verifier's files import only pure parts of the standard
library and call nothing that reaches outside the process.
"""

from __future__ import annotations

import ast
import configparser
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
APP = BACKEND / "app"

# The standard library the verifier may use: computation on strings and numbers, nothing that reads a file, the clock,
# the environment, the network or another module by name.
PURE = {"__future__", "array", "bisect", "collections.abc", "contextlib", "contextvars", "dataclasses", "decimal", "enum", "re", "typing", "unicodedata"}
IMPURE_CALLS = {"open", "eval", "exec", "compile", "__import__", "input", "breakpoint"}
# Modules outside the layers contract, each with why.
EXEMPT = {
    "main": "the composition root: it builds the application from every layer",
    "serving": "the server launcher's helper: it imports nothing of the app and nothing of the app imports it",
}


def _contracts() -> configparser.ConfigParser:
    parser = configparser.ConfigParser()
    parser.read(BACKEND / ".importlinter", encoding="utf-8")
    return parser


def _top_level() -> set[str]:
    modules = {p.stem for p in APP.glob("*.py") if p.stem != "__init__"}
    return modules | {p.parent.name for p in APP.glob("*/__init__.py")}


def test_the_verifier_imports_only_pure_standard_library_and_itself() -> None:
    for path in sorted((APP / "verify").glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                assert all(alias.name in PURE for alias in node.names), (path.name, [a.name for a in node.names])
            elif isinstance(node, ast.ImportFrom):
                assert node.level > 0 or node.module in PURE, (path.name, node.module)  # relative: the verifier itself
            elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                assert node.func.id not in IMPURE_CALLS, (path.name, node.func.id, node.lineno)


def test_the_verifier_is_forbidden_every_other_module() -> None:
    contract = _contracts()["importlinter:contract:verifier-is-pure"]
    assert contract["type"] == "forbidden" and contract["source_modules"].strip() == "app.verify"
    forbidden = {line.strip().removeprefix("app.") for line in contract["forbidden_modules"].splitlines() if line.strip()}
    assert forbidden == _top_level() - {"verify"}


def test_every_module_sits_in_the_layers_contract_or_says_why_not() -> None:
    layers = _contracts()["importlinter:contract:layers"]["layers"]
    named = {name.strip().removeprefix("app.") for line in layers.splitlines() for name in line.replace("|", ":").split(":") if name.strip()}
    assert _top_level() - named == set(EXEMPT), "a module in no layer must be exempt with its reason, and an exempt one in none"
    assert not named & set(EXEMPT)
