"""The evidence pack's own checker and the workbench agree on what verifier v8 verified.

verify.py, the dependency-free checker every pack carries, re-checked a span's characters under its tier but never its
edges, and its typed check dropped a number's sign and parentheses and its written precision. So a v8 pack whose
offsets were moved onto "$1,500" inside "$1,500,000", or whose quote dropped the minus of "-5%", passed the pack's
checker while the workbench refuses both (release integration, 2026-10-13). The invariant: for a run verified under v8,
the pack's checker accepts a span exactly when the workbench's verifier would, edges and signed numbers included;
a run verified under an earlier verifier is checked as that verifier recorded it. The pack is not signed, and these
tests claim nothing about tampering with the whole pack: only that its checker and its record agree.

The counter-review of the integrated release found the typed check still read text its own way: its tokens could end
inside a run of letters and digits, as before v7, and it joined neighbouring words, as before v6. So "$10M (in
aggregate) per year", which the workbench verified, failed the pack, while "5)a" passed for a quote "5a", and a quote of
punctuation alone passed as typed, though the workbench refuses both. For a run verified under v7 or later the pack now
reads tokens with the workbench's own pattern, copied in, and compares words whole.
"""

from __future__ import annotations

import json
import subprocess
import sys
import types
from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from app.application.evidence_pack import render_verify_py
from app.hashing import sha256_bytes
from app.verify.spans import _INVISIBLE, bounded, locate
from app.verify.tokens import VERSION, Token, compared, significant, tokenize
from tests.support import FUZZ_SCALE


def _pack(folder: Path, text: str, start: int, end: int, quote: str, method: str, verifier: str, heading: str = "Fees") -> Path:
    folder.mkdir(parents=True)
    sections = [{"id": "s1", "ordinal": 0, "number": "4", "heading": heading, "text": text}]
    sections_json = json.dumps(sections, ensure_ascii=False, indent=1)
    (folder / "sections.json").write_text(sections_json, encoding="utf-8", newline="\n")
    run = {
        "document": {"file": None, "sha256": "x"},
        "sections_sha256": sha256_bytes(sections_json.encode("utf-8")),
        "prompt_version": "answer-v2",
        "prompt_hash": "",
        "options": {"verifier_version": verifier},
        "verifier": {"window_chars": 6000},
    }
    (folder / "run.json").write_text(json.dumps(run), encoding="utf-8")
    span = {"ordinal": 0, "section_id": "s1", "start": start, "end": end, "quote": quote, "verified": True, "method": method}
    (folder / "findings.json").write_text(json.dumps([{"ordinal": 0, "spans": [span]}]), encoding="utf-8")
    (folder / "verify.py").write_text(render_verify_py(), encoding="utf-8")
    return folder


def _verdict(folder: Path) -> bool:
    done = subprocess.run([sys.executable, "verify.py"], cwd=folder, capture_output=True, text=True, check=False)
    assert ("PASS finding 1 span 1" in done.stdout) != ("FAIL finding 1 span 1" in done.stdout), done.stdout
    return done.returncode == 0


# A record changed after the fact: offsets moved inside a number, or a quote that drops a sign, the parentheses or the
# precision of the number it stands for. The workbench refuses each of them under v8.
TAMPERED = [
    ("moved inside $1,500,000", "A fee of $1,500,000 is due.", "$1,500", "exact"),
    ("moved inside $15.50", "A fee of $15.50 is due.", "$15", "exact"),
    ("moved inside Section 5.2", "As set out in Section 5.2 below.", "Section 5", "exact"),
    ("moved inside -5%", "A credit of -5% applies.", "5%", "exact"),
    ("a dropped minus", "A credit of -5% applies.", "A credit of 5% applies", "typed"),
    ("dropped parentheses", "A credit of ($500) applies.", "A credit of $500 applies", "typed"),
    ("a dropped precision", "A fee of $15.00 is due.", "A fee of $15 is due", "typed"),
]


def _span(text: str, quote: str, method: str) -> tuple[int, int]:
    """Where the record points: the quote's own characters for a verbatim tier, the whole sentence for a typed one."""
    if method == "exact":
        start = text.index(quote)
        return start, start + len(quote)
    return 0, len(text) - 1  # the sentence without its full stop


@pytest.mark.parametrize(("case", "text", "quote", "method"), TAMPERED, ids=[case for case, *_ in TAMPERED])
def test_a_v8_pack_fails_where_the_workbench_refuses(tmp_path: Path, case: str, text: str, quote: str, method: str) -> None:
    start, end = _span(text, quote, method)
    assert locate(quote, text) is None, f"{case}: the workbench refuses it"
    assert not _verdict(_pack(tmp_path / "v8", text, start, end, quote, method, "v8")), case


# What v7 itself verified (replayed on 8b7b8fb, 2026-10-13): every tampered record above but the dropped precision,
# since v7 already compared a number's digits as written ("15.00" is not "15"). The pack said otherwise until the
# counter-review: its typed check normalised "15.00" to "15" for every run before v8.
V7_FOUND = {case: case != "a dropped precision" for case, *_ in TAMPERED}


@pytest.mark.parametrize(("case", "text", "quote", "method"), TAMPERED, ids=[case for case, *_ in TAMPERED])
def test_control_a_v7_pack_is_checked_as_v7_recorded_it(tmp_path: Path, case: str, text: str, quote: str, method: str) -> None:
    """Historical packs keep their verdict: v7 found "$1,500" in "$1,500,000", and its pack still says what v7 did."""
    start, end = _span(text, quote, method)
    assert _verdict(_pack(tmp_path / "v7", text, start, end, quote, method, "v7")) == V7_FOUND[case], case


@pytest.mark.parametrize(
    ("text", "quote"),
    [
        ("A fee of $1,500,000 is due.", "$1,500,000"),
        ("A credit of -5% applies.", "-5%"),
        ("A credit of ($500) applies.", "($500)"),
        ("As set out in Section 5.2 below.", "Section 5.2"),
        ("Fees: “$1,500” per user.", 'Fees: "$1,500" per user.'),
        ("A credit of -5 % applies.", "a credit of -5% applies"),
    ],
)
def test_control_a_span_the_workbench_verified_passes(tmp_path: Path, text: str, quote: str) -> None:
    located = locate(quote, text)
    assert located is not None
    folder = _pack(tmp_path / "ok", text, located.start, located.end, quote, located.method, "v8")
    assert _verdict(folder), (text, quote, located.method)


def _checker(tmp_path: Path) -> types.ModuleType:
    module = types.ModuleType("pack_verify")
    module.__dict__["__file__"] = str(tmp_path / "verify.py")
    exec(compile(render_verify_py(), "verify.py", "exec"), module.__dict__)
    return module


def _compared(text: str, version: int) -> list[Token]:
    """What the typed tier of ``version`` compares, as the workbench calls it (tokens.locate_tokens): from v8 with what is
    written against each number, from v9 with invisible marks read as absent."""
    if version < 8:
        return significant(tokenize(text))
    return compared(text, version, _INVISIBLE if version >= 9 else frozenset())


NUMBERISH = st.text(alphabet="0123456789,.%$()-− Sa", min_size=1, max_size=24)
NUMBERS_ONLY = st.text(alphabet="0123456789,.%$()-− ", min_size=1, max_size=24)


@settings(max_examples=400 * FUZZ_SCALE, deadline=None)
@given(text=NUMBERISH, data=st.data())
def test_the_pack_reads_every_edge_as_the_workbench_does(tmp_path_factory: pytest.TempPathFactory, text: str, data: st.DataObject) -> None:
    checker = _checker(tmp_path_factory.mktemp("edges"))
    start = data.draw(st.integers(0, len(text)))
    end = data.draw(st.integers(start, len(text)))
    assert checker.edges_hold(text, start, end, VERSION) == bounded(text, start, end), (text, start, end)  # the runtime reads at its own version


@settings(max_examples=400 * FUZZ_SCALE, deadline=None)
@given(a=NUMBERS_ONLY, b=NUMBERS_ONLY)
def test_the_pack_compares_numbers_as_the_workbench_does(tmp_path_factory: pytest.TempPathFactory, a: str, b: str) -> None:
    checker = _checker(tmp_path_factory.mktemp("typed"))

    for version in (8, 9, 10, 11):

        def runtime(text: str) -> list[str]:
            return [t.canonical for t in _compared(text, version)]  # noqa: B023 - read at once

        assert (checker.typed(a, version) == checker.typed(b, version)) == (runtime(a) == runtime(b)), (a, b, version)


# Found by the counter-review (2026-10-13): a letter against the digits of an amount, and a quote of punctuation alone.
TAMPERED_TYPED = [
    ("a bracket between a number and a letter", "Rate 5)a applies.", "Rate 5a applies", "Rate 5)a applies"),
    ("a dash before a currency sign", "Fee 1-€1, due.", "Fee 1€1, due", "Fee 1-€1, due"),
    ("a quote of punctuation alone", "A fee of $15 (-) is due.", "( - )", "(-)"),
    # Read out of place, "$01" is an amount; in place, after "4.3", its "$" is punctuation and "01" a plain number.
    ("a currency sign after a digit", "Rate (4.3$01.)935 due.", "$01)935", "$01.)935"),
    # A span that begins on a minus sign the reader sees joined to its number, across a zero-width space.
    ("a span that begins on a sign", "Due )$-​1€,8 now.", "​1€", "-​1€"),
]


@pytest.mark.parametrize("verifier", ["v7", "v8"])
@pytest.mark.parametrize(("case", "text", "quote", "found"), TAMPERED_TYPED, ids=[case for case, *_ in TAMPERED_TYPED])
def test_a_typed_span_the_workbench_refuses_fails_the_pack(tmp_path: Path, verifier: str, case: str, text: str, quote: str, found: str) -> None:
    assert locate(quote, text) is None, f"{case}: the workbench refuses it"
    start = text.index(found)
    assert not _verdict(_pack(tmp_path / verifier, text, start, start + len(found), quote, "typed", verifier)), case


@pytest.mark.parametrize("verifier", ["v7", "v8", "v9"])
@pytest.mark.parametrize(
    ("text", "quote", "v8_start"),
    [
        ("The fee is capped at $10M (in aggregate) per year.", "$10M in aggregate per year", "10M"),
        ("Liability: $5K, per claim.", "$5K per claim", "5K"),
        ("Pay 30days, after the 2nd invoice.", "Pay 30days after the 2nd invoice", "Pay"),
    ],
)
def test_control_a_typed_span_with_letters_against_digits_passes(tmp_path: Path, verifier: str, text: str, quote: str, v8_start: str) -> None:
    """Each version's pack accepts the span that version located: v7 and v8 read "$10M" as "$" and the word "10m", so
    their span began at the digits; v9 reads "$10M" as one amount and its span begins at the dollar sign."""
    located = locate(quote, text)
    assert located is not None and located.method == "typed", located
    start = located.start if verifier == "v9" else text.index(v8_start)
    assert _verdict(_pack(tmp_path / verifier, text, start, located.end, quote, "typed", verifier)), (text, quote)


WORDS_AND_NUMBERS = st.text(alphabet="0123456789,.%$€()-− aMKxUSDb", min_size=1, max_size=24)


@settings(max_examples=400 * FUZZ_SCALE, deadline=None)
@given(a=WORDS_AND_NUMBERS, b=WORDS_AND_NUMBERS, version=st.sampled_from([7, 8, 9, 10, 11]))
def test_the_pack_compares_typed_tokens_as_the_workbench_does(tmp_path_factory: pytest.TempPathFactory, a: str, b: str, version: int) -> None:
    """For v7 to v11 runs, with letters against digits: the pack's typed check and the workbench's (as that version
    read) agree, both ways."""
    checker = _checker(tmp_path_factory.mktemp("typed-words"))

    def runtime(text: str) -> list[tuple[str, str]]:
        return [(str(t.kind), t.canonical) for t in _compared(text, version)]

    expected = bool(runtime(a)) and runtime(a) == runtime(b)
    assert checker.same(a, b, "typed", version) == expected, (a, b, version)


PLACED = st.text(alphabet="0123456789,.%$€()-− aMKUSD​", min_size=1, max_size=24)


@settings(max_examples=400 * FUZZ_SCALE, deadline=None)
@given(text=PLACED, quote=PLACED, version=st.sampled_from([7, 8, 9, 10, 11]), data=st.data())
def test_the_pack_reads_a_typed_span_in_place_as_the_workbench_does(
    tmp_path_factory: pytest.TempPathFactory, text: str, quote: str, version: int, data: st.DataObject
) -> None:
    """For v7 to v11 runs: the pack accepts a typed span at its offsets exactly when that version's typed tier reports
    the quote's tokens there, read from the whole text the workbench searched."""
    checker = _checker(tmp_path_factory.mktemp("typed-placed"))
    start = data.draw(st.integers(0, len(text)))
    end = data.draw(st.integers(start, len(text)))
    needle = [(t.kind, t.canonical) for t in _compared(quote, version)]
    hay = _compared(text, version)
    n = len(needle)
    expected = bool(needle) and any(
        hay[i].start == start and hay[i + n - 1].end == end and [(t.kind, t.canonical) for t in hay[i : i + n]] == needle for i in range(len(hay) - n + 1)
    )
    assert checker.same(text[start:end], quote, "typed", version, (text, start, end)) == expected, (text, start, end, quote, version)


@pytest.mark.parametrize("heading", ["Fees", "Fees ≥ 30 days"])
def test_the_pack_prints_where_a_span_is_and_survives_a_console_that_cannot_print_the_contract(tmp_path: Path, heading: str) -> None:
    """A PASS line names the span's section and offsets, never its text, and a character the console cannot encode
    never crashes the checker: piped on Windows, Python writes cp1252, and a genuine pack whose section held "≥"
    exited 1 with UnicodeEncodeError (counter-review of 708e511)."""
    import os

    text = "Notice of not less than ≥ 30 days: a fee of $1,500 is due."
    located = locate("a fee of $1,500 is due", text)
    assert located is not None
    folder = _pack(tmp_path / "console", text, located.start, located.end, "a fee of $1,500 is due", located.method, "v8", heading)
    env = {**os.environ, "PYTHONIOENCODING": "cp1252"}
    env.pop("PYTHONUTF8", None)
    done = subprocess.run([sys.executable, "verify.py"], cwd=folder, capture_output=True, check=False, env=env)
    out = done.stdout.decode("cp1252", errors="replace")
    assert done.returncode == 0, (out, done.stderr.decode("cp1252", errors="replace"))
    line = next(row for row in out.splitlines() if row.startswith("PASS finding 1 span 1"))
    assert line.startswith(f"PASS finding 1 span 1: section 4 characters {located.start}-{located.end} ({located.method})"), line
    assert "Notice of not less" not in out
