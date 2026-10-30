"""Text a model or a file wrote, as the memo and the evidence pack's README show it.

The invariant of ingest/invisible.py, on the way out: the text a person reads is the text that was checked. Ingest holds
the contract, its name, guidance and questions to it; nothing holds the strings the model writes, and the record keeps
them as the model wrote them, which is right: they are its evidence. A direction override in a quote the verifier
located printed "fifteen (51) days" in the memo under "found in the document text", where the contract says fifteen
(15); html.escape leaves format characters alone, and the DOCX's xml_safe removed only control characters
(hostile-model review, 2026-10-30).

So every such string is shown through this module, the memo's one display primitive (the interface's is
src/lib/text.ts revealInvisible, the same rule): each character the reader would remove on its own is named in place
("[U+202E]", or a marked span in HTML) instead of acting on the page. Kept as text, as the reader keeps them: the
joiners and the direction marks, and a variation selector or other default-ignorable character except between two ASCII
letters or digits, where it shapes and varies nothing. The record is never changed here.
"""

from __future__ import annotations

import re
import unicodedata
from html import escape

from ..ingest.invisible import IGNORABLE, JOINERS, MARKS

_SHAPING = re.compile(f"[{JOINERS}{IGNORABLE}]")
_ASCII_WORD = re.compile(r"[A-Za-z0-9]")


def _hidden(text: str) -> list[bool]:
    """Which characters the screen names instead of showing: as the reader removes them, format characters first, then a
    run of shaping characters between two ASCII letters or digits."""
    hidden = [unicodedata.category(ch) == "Cf" and ch not in JOINERS + MARKS for ch in text]

    def neighbour(start: int, step: int) -> str:
        i = start
        while 0 <= i < len(text) and (hidden[i] or _SHAPING.match(text[i])):
            i += step
        return text[i] if 0 <= i < len(text) else ""

    for i, ch in enumerate(text):
        if _SHAPING.match(ch) and _ASCII_WORD.match(neighbour(i - 1, -1)) and _ASCII_WORD.match(neighbour(i + 1, 1)):
            hidden[i] = True
    return hidden


def _pieces(text: str) -> list[tuple[str, str | None]]:
    """The text in pieces: (text, None) for ordinary text, (character, "U+XXXX") for each one named."""
    pieces: list[tuple[str, str | None]] = []
    run: list[str] = []
    for ch, hidden in zip(text, _hidden(text), strict=True):
        if not hidden:
            run.append(ch)
            continue
        if run:
            pieces.append(("".join(run), None))
            run = []
        pieces.append((ch, f"U+{ord(ch):04X}"))
    if run:
        pieces.append(("".join(run), None))
    return pieces


def shown(text: str) -> str:
    """The text as plain text shows it: each named character written as its name in brackets (the DOCX, the README)."""
    return "".join(f"[{name}]" if name else piece for piece, name in _pieces(text))


def shown_html(text: str) -> str:
    """The text as HTML, escaped, each named character a marked span that says what it is (the HTML memo)."""
    return "".join(
        f"<span class='invisible' title='An invisible character ({name}) in the recorded text'>{name}</span>" if name else escape(piece)
        for piece, name in _pieces(text)
    )
