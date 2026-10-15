"""No contract text is kept in memory past the work that needed it.

A visitor's contract is deleted with their workspace (application/retention.py), so a copy kept in the API's memory
outlives the promise. Two did (release integration, 2026-10-13): the verifier's process-wide caches were keyed by the
texts and quotes they had seen (16 section texts, 1,024 quotes), and a document read again for a revision check kept its
reading, by path, until 32 newer ones displaced it. The invariant: what is worked out about a text lives for one
verification pass; a reading kept for reuse lives minutes, and never past a retention pass.
"""

from __future__ import annotations

import asyncio
import sys
import time
import uuid
from pathlib import Path

import pytest

from app.application import trust_run
from app.ingest import ingest
from app.verify import spans
from app.verify.spans import locate, verification_pass
from tests.support import CONTRACT


def _fresh(text: str) -> str:
    """A new string object, never one the interpreter shares with another literal."""
    return "".join([text, " ", uuid.uuid4().hex])


@pytest.mark.parametrize("inside_a_pass", [False, True])
def test_locate_keeps_no_reference_to_a_contract_or_a_quote_once_it_is_done(inside_a_pass: bool) -> None:
    # Edges next to a sign, a currency sign and a section number, so every memo is asked for: numbers, words, letters.
    text = _fresh("The credit is -5% of the fees. Under Section 5.2 the fees of $1,500,000 are due within 30 days.")
    quote = "".join(["fees of $1,500,000 ", "are due"])  # built at run time, so not a shared constant
    label = "".join(["5 ", "Fees"])
    before = sys.getrefcount(text), sys.getrefcount(quote), sys.getrefcount(label)
    if inside_a_pass:
        with verification_pass():
            assert locate(quote, text, label) is not None
            assert locate("".join(["-5", "%"]), text, label) is not None
    else:
        assert locate(quote, text, label) is not None
        assert locate("".join(["-5", "%"]), text, label) is not None
    assert (sys.getrefcount(text), sys.getrefcount(quote), sys.getrefcount(label)) == before


def test_within_a_pass_a_text_s_numbers_are_read_once(monkeypatch: pytest.MonkeyPatch) -> None:
    """Control: the memo still does its work while the pass lasts, across quotes and across occurrences."""
    reads: list[int] = []
    real = spans._read_numbers

    def counted(text: str) -> object:
        reads.append(len(text))
        return real(text)

    monkeypatch.setattr(spans, "_read_numbers", counted)
    text = _fresh(" ".join(f"Fee {n}: -{n}% of $1,{n:03d},000." for n in range(200)))
    with verification_pass():
        for n in (5, 50, 150):
            assert locate(f"-{n}% of $1,{n:03d},000", text) is not None
    assert len(reads) == 1, reads
    reads.clear()
    assert locate("-5% of $1,005,000", text) is not None  # a single locate opens its own pass
    assert len(reads) == 1


def test_a_quote_repeated_through_a_long_section_is_still_quick() -> None:
    """Hostile control: thousands of occurrences, each with a numeric edge, in a 330 KB section; numbers read once."""
    text = _fresh(" ".join(["-5% of the fee is due."] * 15_000))
    began = time.perf_counter()
    found = locate("5% of the fee is due", text)
    took = time.perf_counter() - began
    assert found is None, "every occurrence sits after a minus sign, so none is bounded"
    assert took < 3.0, took


def test_a_document_read_again_is_kept_for_minutes_not_for_good(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    stored = tmp_path / "stored.txt"
    stored.write_bytes(CONTRACT.encode())
    reads: list[int] = []

    def counted(name: str, data: bytes, **_kwargs: object) -> object:
        reads.append(1)
        return ingest(name, data)

    monkeypatch.setattr(trust_run, "read_file", counted)
    monkeypatch.setattr(trust_run, "READING_KEPT_SECONDS", 0.2)
    trust_run.forget_readings()
    assert trust_run._read_again(stored, "stored.txt", "test-reader") is not None
    assert trust_run._read_again(stored, "stored.txt", "test-reader") is not None
    assert len(reads) == 1, "control: kept while it is fresh"
    time.sleep(0.3)
    assert trust_run._read_again(stored, "stored.txt", "test-reader") is not None
    assert len(reads) == 2, "read again once its minutes are over: the old reading is gone"


def test_a_retention_pass_drops_every_document_read_again(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from app import main

    stored = tmp_path / "stored.txt"
    stored.write_bytes(CONTRACT.encode())
    trust_run.forget_readings()
    assert trust_run._read_again(stored, "stored.txt", "test-reader") is not None
    assert trust_run._readings, "control: the reading is kept"

    async def one_pass(_seconds: float) -> None:
        raise asyncio.CancelledError  # stop after the first pass

    monkeypatch.setattr(main, "purge_expired_workspaces", lambda _engine: None)
    monkeypatch.setattr(main, "sweep_orphaned_files", lambda _engine: 0)
    monkeypatch.setattr(asyncio, "sleep", one_pass)  # the module main awaits it from
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(main._retain_hourly())
    assert not trust_run._readings


def test_a_retention_pass_that_fails_midway_still_drops_every_document_read_again(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """A purge that raises after deleting some workspaces must not leave their readings for another hour (counter-review N2)."""
    from app import main

    stored = tmp_path / "stored.txt"
    stored.write_bytes(CONTRACT.encode())
    trust_run.forget_readings()
    assert trust_run._read_again(stored, "stored.txt", "test-reader") is not None
    assert trust_run._readings, "control: the reading is kept"

    def purge_fails(_engine: object) -> None:
        raise RuntimeError("the store went away midway")

    async def one_pass(_seconds: float) -> None:
        raise asyncio.CancelledError

    monkeypatch.setattr(main, "purge_expired_workspaces", purge_fails)
    monkeypatch.setattr(main, "sweep_orphaned_files", lambda _engine: 0)
    monkeypatch.setattr(asyncio, "sleep", one_pass)
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(main._retain_hourly())
    assert not trust_run._readings
