"""Characters that change what text looks like without being text, removed before anything reads or checks it.

Unicode format characters (category Cf) are invisible: a zero-width space or a soft hyphen between two digits, a word
joiner, a byte-order mark, tag characters, and the direction controls that reorder what is displayed. Left in a reading,
the text a person sees and the text that is checked part ways: "terminate on \u202e09\u202c days" displays as "90 days"
while the model, the verifier and the day parser read "09", and "9\u200b0 days" displays as "90" while the day parser
reads 0 (adversarial review, 2026-10-08). The invariant: the text a person reads is the text that was checked.

Kept, because text needs them: the zero-width joiner and non-joiner (emoji sequences, the shaping of Arabic and Indic
scripts) and the other default-ignorable characters (variation selectors, the combining grapheme joiner, Hangul fillers)
except between two ASCII letters or digits, where nothing is shaped or varied; and the left-to-right, right-to-left and
Arabic letter marks, which order neutral characters and cannot reverse a run, except inside a number written in ASCII
digits (reader v16): "upon 9\u061c0 days" displays "upon 90 days", and there the mark orders nothing and only parts the
number for whatever reads it (stress test, 2026-10-30). Between two ASCII letters a mark is kept, as before.
"""

from __future__ import annotations

import re
import unicodedata
from functools import cache

# The joiners, the direction marks and the default-ignorable characters that are not Cf are defined once, below every
# layer, where policy and the memo read them too (app/unseen.py; the readers wrote their own copy until the second wave
# of the stress test, 2026-10-30, and a test held the two equal).
from ..unseen import IGNORABLE, JOINERS, MARKS

__all__ = ["IGNORABLE", "JOINERS", "MARKS", "has_visible_text", "remove_format_characters", "visible_text"]
_BETWEEN_ASCII = re.compile(rf"(?<=[A-Za-z0-9])[{JOINERS}{IGNORABLE}]+(?=[A-Za-z0-9])")
# Inside a number written in ASCII digits: between two digits, or between a digit and the group or decimal mark beside
# another digit ("1" LRM ",500", "1," LRM "500"). Any of the invisible characters kept elsewhere (reader v16).
INSIDE_NUMBERS = f"{JOINERS}{MARKS}{IGNORABLE}"
_IN_ASCII_NUMBER = re.compile(rf"(?<=[0-9])[{INSIDE_NUMBERS}]+(?=[0-9]|[.,][0-9])|(?<=[0-9][.,])[{INSIDE_NUMBERS}]+(?=[0-9])")
# Whether a text holds any of them at all: most hold none, and the two passes above then cost a 2 MB text 0.8 s.
_ANY_KEPT = re.compile(f"[{INSIDE_NUMBERS}]")


@cache
def _format_characters() -> re.Pattern[str]:
    """Every Cf character this Python's Unicode database knows, except those kept; built once per process."""
    # Format characters live in the Basic and Supplementary Multilingual Planes and in plane 14 (tags); scanning only
    # those keeps the first use near 0.1 s instead of the whole code space's 0.9 s.
    candidates = (*range(0x20000), *range(0xE0000, 0xE1000))
    removed = "".join(chr(c) for c in candidates if unicodedata.category(chr(c)) == "Cf" and chr(c) not in JOINERS + MARKS)
    return re.compile(f"[{re.escape(removed)}]")


def remove_format_characters(text: str) -> tuple[str, int]:
    """The text without invisible format characters, and how many were removed."""
    cleaned = _format_characters().sub("", text)
    if _ANY_KEPT.search(cleaned):
        cleaned = _IN_ASCII_NUMBER.sub("", _BETWEEN_ASCII.sub("", cleaned))
    return cleaned, len(text) - len(cleaned)


def visible_text(text: str) -> str:
    """``remove_format_characters`` for a field where the count is not recorded (a question, guidance, a name)."""
    return remove_format_characters(text)[0]


# Whether text shows anything: the one test of it (moved here from application/visible_input.py in the second wave of
# the stress test, 2026-10-30, so that the readers' own names use it too). visible_text keeps, on purpose, characters
# text needs that render nothing on their own: the joiners, the direction marks, the Hangul fillers and variation
# selectors, a combining mark. A reviewer of "\u200d" was recorded and printed in the memo, a question of only those
# started a run, and a file named only with them was stored under that name instead of "document" (journeys 3). A text
# shows something when one of its characters is drawn: not a space, not a control, format or combining character, not
# one of those kept but undrawn, not the blank braille pattern. A mark on a visible letter keeps it visible ("José"
# written with a combining accent), and so does a joiner inside an emoji sequence.
_UNDRAWN_CATEGORIES = frozenset({"Cc", "Cf", "Mn", "Me", "Zs", "Zl", "Zp"})
_KEPT_BUT_UNDRAWN = re.compile(f"[{JOINERS}{MARKS}{IGNORABLE}\u2800]")


def _drawn(character: str) -> bool:
    return not character.isspace() and unicodedata.category(character) not in _UNDRAWN_CATEGORIES and not _KEPT_BUT_UNDRAWN.fullmatch(character)


def has_visible_text(text: str) -> bool:
    return any(_drawn(character) for character in text)
