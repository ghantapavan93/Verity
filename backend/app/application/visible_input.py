"""Whether something a person typed shows anything: the one test every use case asks of free text it stores.

visible_text (ingest/invisible.py) removes format characters and keeps, deliberately, the characters text needs that
render nothing on their own: the joiners, the direction marks, the Hangul fillers and variation selectors, a combining
mark. Each use case then tested `visible_text(x).strip()` for emptiness, and a string of only those passed: a reviewer
of "‍" was recorded and printed in the memo, a reviewer of zero-width spaces was recorded with an empty name, and
such a question started a run and such guidance was saved (stress test, 2026-10-30, journeys 3). A text has visible
text when at least one of its characters is drawn: not a space, not a control, format or combining character, not one of
those kept-but-invisible ones, and not the blank braille pattern. A mark on a visible letter keeps it visible ("José"
written with a combining accent), and so does a joiner inside an emoji sequence.
"""

from __future__ import annotations

import re
import unicodedata

from ..ingest.invisible import IGNORABLE, JOINERS, MARKS

_UNDRAWN_CATEGORIES = frozenset({"Cc", "Cf", "Mn", "Me", "Zs", "Zl", "Zp"})
_KEPT_BUT_UNDRAWN = re.compile(f"[{JOINERS}{MARKS}{IGNORABLE}⠀]")


def _drawn(character: str) -> bool:
    return not character.isspace() and unicodedata.category(character) not in _UNDRAWN_CATEGORIES and not _KEPT_BUT_UNDRAWN.fullmatch(character)


def has_visible_text(text: str) -> bool:
    return any(_drawn(character) for character in text)
