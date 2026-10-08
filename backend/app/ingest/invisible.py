"""Characters that change what text looks like without being text, removed before anything reads or checks it.

Unicode format characters (category Cf) are invisible: a zero-width space or a soft hyphen between two digits, a word
joiner, a byte-order mark, tag characters, and the direction controls that reorder what is displayed. Left in a reading,
the text a person sees and the text that is checked part ways: "terminate on \u202e09\u202c days" displays as "90 days"
while the model, the verifier and the day parser read "09", and "9\u200b0 days" displays as "90" while the day parser
reads 0 (adversarial review, 2026-10-08). The invariant: the text a person reads is the text that was checked.

Kept, because text needs them: the zero-width joiner and non-joiner (emoji sequences, the shaping of Arabic and Indic
scripts) and the other default-ignorable characters (variation selectors, the combining grapheme joiner, Hangul fillers)
except between two ASCII letters or digits, where nothing is shaped or varied; and the left-to-right, right-to-left and
Arabic letter marks, which order neutral characters and cannot reverse a run.
"""

from __future__ import annotations

import re
import unicodedata
from functools import cache

JOINERS = "\u200c\u200d"  # zero-width non-joiner and joiner
MARKS = "\u200e\u200f\u061c"  # left-to-right, right-to-left and Arabic letter marks
# Default-ignorable code points that are not format characters (Unicode's Default_Ignorable_Code_Point less Cf):
# invisible, yet the Cf pass keeps them. Between two ASCII letters or digits they join or vary nothing, and there
# "9\ufe0f0 days" displayed "90 days" while the day parser read 0 (triage review, 2026-10-08). Elsewhere they are
# kept: a variation selector chooses an emoji's or a CJK character's form, and a keycap is a digit, U+FE0F and U+20E3.
IGNORABLE = "\u034f\u115f\u1160\u17b4\u17b5\u180b-\u180d\u180f\u3164\ufe00-\ufe0f\uffa0\U000e0100-\U000e01ef"
_BETWEEN_ASCII = re.compile(rf"(?<=[A-Za-z0-9])[{JOINERS}{IGNORABLE}]+(?=[A-Za-z0-9])")


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
    cleaned = _BETWEEN_ASCII.sub("", _format_characters().sub("", text))
    return cleaned, len(text) - len(cleaned)


def visible_text(text: str) -> str:
    """``remove_format_characters`` for a field where the count is not recorded (a question, guidance, a name)."""
    return remove_format_characters(text)[0]
