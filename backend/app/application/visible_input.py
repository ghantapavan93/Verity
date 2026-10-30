"""Whether something a person typed shows anything: the one test every use case asks of free text it stores.

visible_text (ingest/invisible.py) removes format characters and keeps, deliberately, the characters text needs that
render nothing on their own: the joiners, the direction marks, the Hangul fillers and variation selectors, a combining
mark. Each use case then tested `visible_text(x).strip()` for emptiness, and a string of only those passed: a reviewer
of "\u200d" was recorded and printed in the memo, a reviewer of zero-width spaces was recorded with an empty name, and
such a question started a run and such guidance was saved (stress test, 2026-10-30, journeys 3). A text has visible
text when at least one of its characters is drawn: not a space, not a control, format or combining character, not one of
those kept-but-invisible ones, and not the blank braille pattern. A mark on a visible letter keeps it visible ("José"
written with a combining accent), and so does a joiner inside an emoji sequence.
"""

from __future__ import annotations

# The test itself lives with the readers that define what is unseen (ingest/invisible.py), which name a file by it too
# (second wave of the stress test, 2026-10-30); the use cases keep importing it from here.
from ..ingest.invisible import has_visible_text

__all__ = ["has_visible_text"]
