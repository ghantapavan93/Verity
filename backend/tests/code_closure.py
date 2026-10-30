"""The code a version names, found by following it rather than listed by hand (tests only; nothing here runs in the app).

A closure starts from entry points, top-level definitions of app modules or a method of a top-level class
("Class.method"), and takes in every top-level function, class and assignment their code names, followed through imports
inside the app, until nothing new is reached. A field's type is followed (a Pydantic model's field types are the schema
it reads), a parameter's or a return's annotation is not. A name that cannot be resolved inside the app (the standard
library, a third-party package, a method called on an object) ends there: code reached only that way must be named as
an entry point, as the provider's request is.
"""

from __future__ import annotations

import ast
from collections.abc import Iterable, Iterator, Mapping
from functools import cache
from pathlib import Path, PurePosixPath

APP = Path(__file__).resolve().parents[1] / "app"

Symbol = tuple[str, str]  # (module path under app/, top-level name)


@cache
def module(path: str) -> ast.Module:
    tree = ast.parse((APP / path).read_text(encoding="utf-8"))
    for node in ast.walk(tree):  # docstrings say what code does; they decide nothing
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)) and node.body:
            first = node.body[0]
            if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant) and isinstance(first.value.value, str):
                node.body = node.body[1:] or [ast.Pass()]
    return tree


def _top_level(statements: Iterable[ast.stmt]) -> Iterator[ast.stmt]:
    """A module's statements, those inside a top-level if, try or with included (an import fallback, a guarded def)."""
    for statement in statements:
        if isinstance(statement, (ast.If, ast.Try, ast.With)):
            yield from _top_level(statement.body)
            yield from _top_level(getattr(statement, "orelse", []))
            yield from _top_level(getattr(statement, "finalbody", []))
            for handler in getattr(statement, "handlers", []):
                yield from _top_level(handler.body)
        else:
            yield statement


@cache
def definitions(path: str) -> Mapping[str, tuple[ast.stmt, ...]]:
    found: dict[str, list[ast.stmt]] = {}
    for statement in _top_level(module(path).body):
        names: list[str] = []
        if isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names = [statement.name]
        elif isinstance(statement, ast.Assign):
            names = [n.id for target in statement.targets for n in ast.walk(target) if isinstance(n, ast.Name)]
        elif isinstance(statement, (ast.AnnAssign, ast.AugAssign)) and isinstance(statement.target, ast.Name):
            names = [statement.target.id]
        for name in names:
            found.setdefault(name, []).append(statement)
    return {name: tuple(nodes) for name, nodes in found.items()}


def _file(parts: Iterable[str]) -> str | None:
    base = PurePosixPath(*parts) if parts else PurePosixPath()
    for candidate in (f"{base}.py" if str(base) != "." else "", str(base / "__init__.py") if str(base) != "." else "__init__.py"):
        if candidate and (APP / candidate).is_file():
            return candidate
    return None


@cache
def imports(path: str) -> Mapping[str, tuple[str, str | None]]:
    """Each name a module imports from the app: (module path, the symbol, or None when the name is a module)."""
    found: dict[str, tuple[str, str | None]] = {}
    here = PurePosixPath(path).parent.parts
    for node in ast.walk(module(path)):  # imports inside functions too: a name resolves the same way wherever it is imported
        if isinstance(node, ast.ImportFrom):
            if node.level == 0:
                if not (node.module or "").startswith("app"):
                    continue
                base = (node.module or "").split(".")[1:]
            else:
                base = [*here[: len(here) - (node.level - 1)], *((node.module or "").split(".") if node.module else [])]
            for alias in node.names:
                as_module = _file([*base, alias.name])
                source = _file(base)
                if as_module is not None:
                    found[alias.asname or alias.name] = (as_module, None)
                elif source is not None:
                    found[alias.asname or alias.name] = (source, alias.name)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.startswith("app.") and (target := _file(alias.name.split(".")[1:])) is not None and alias.asname:
                    found[alias.asname] = (target, None)
    return found


def references(node: ast.AST) -> set[tuple[str, ...]]:
    """The names a definition uses, and `module.attribute` pairs; never a parameter or an annotation."""
    found: set[tuple[str, ...]] = set()

    def visit(current: ast.AST) -> None:
        if isinstance(current, ast.arg):
            return
        if isinstance(current, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for part in [*current.decorator_list, *current.args.defaults, *(d for d in current.args.kw_defaults if d is not None), *current.body]:
                visit(part)
            return
        if isinstance(current, ast.AnnAssign):  # a field: its type, and its default
            visit(current.annotation)
            if current.value is not None:
                visit(current.value)
            return
        if isinstance(current, ast.Attribute) and isinstance(current.value, ast.Name):
            found.add((current.value.id, current.attr))
        if isinstance(current, ast.Name) and isinstance(current.ctx, ast.Load):
            found.add((current.id,))
        for child in ast.iter_child_nodes(current):
            visit(child)

    visit(node)
    return found


def _symbol(path: str, name: str, seen: frozenset[Symbol] = frozenset()) -> Symbol | None:
    """Where a module's name is defined, through re-exports."""
    if (path, name) in seen:
        return None
    if name in definitions(path):
        return (path, name)
    imported = imports(path).get(name)
    if imported is None:
        return None
    source, symbol = imported
    return _symbol(source, symbol, seen | {(path, name)}) if symbol is not None else None


def resolve(path: str, reference: tuple[str, ...]) -> Symbol | None:
    name = reference[0]
    imported = imports(path).get(name)
    if len(reference) == 2 and imported is not None and imported[1] is None:
        return _symbol(imported[0], reference[1])  # module.attribute
    return _symbol(path, name)


def nodes_of(path: str, name: str) -> tuple[ast.stmt, ...]:
    """A top-level definition, or "Class.method": the method's own definition."""
    owner, _, method = name.partition(".")
    nodes = definitions(path).get(owner, ())
    if method:
        nodes = tuple(node for owner_node in nodes if isinstance(owner_node, ast.ClassDef) for node in owner_node.body
                      if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == method)  # fmt: skip
    return nodes


def closure(entries: Iterable[Symbol], stop: Iterable[Symbol] = ()) -> dict[Symbol, tuple[ast.stmt, ...]]:
    """Every definition the entries reach, the entries included; a symbol in ``stop`` is neither taken nor followed."""
    stopped, reached = set(stop), {}
    pending = list(entries)
    for path, name in pending:
        assert nodes_of(path, name), f"{path}:{name} is not a top-level definition or method; the entry point moved"
    while pending:
        symbol = pending.pop()
        if symbol in reached or symbol in stopped:
            continue
        nodes = nodes_of(*symbol)
        reached[symbol] = nodes
        for node in nodes:
            for reference in references(node):
                if (target := resolve(symbol[0], reference)) is not None:
                    pending.append(target)
    return reached


def canonical(node: object) -> object:
    """The tree as nested tuples of node names and the fields that carry something. Positions are not fields, and an
    empty or absent field is left out, so a Python that adds an optional field to a node does not change the result."""
    if isinstance(node, ast.AST):
        return (type(node).__name__, tuple((name, canonical(value)) for name, value in ast.iter_fields(node) if value not in (None, [], ())))
    if isinstance(node, list):
        return tuple(canonical(item) for item in node)
    return repr(node)
