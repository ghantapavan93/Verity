"""What a reader does not see: the one definition the readers (ingest.invisible) and the value readers (policy.durations,
runs.values) share.

It sits below every layer, so the status rules can read it without importing the readers: policy.durations imported it
from ingest.invisible, and the layers contract forbids one sibling importing another (merge of the stress test's fixes,
2026-10-30). The verifier keeps its own copy, written out (verify.spans.IGNORABLE_RANGES), because it imports nothing
of the app; backend/tests/test_import_contracts.py holds the two to the same set.
"""

from __future__ import annotations

JOINERS = "\u200c\u200d"  # zero-width non-joiner and joiner
MARKS = "\u200e\u200f\u061c"  # left-to-right, right-to-left and Arabic letter marks
# Default-ignorable code points that are not format characters (Unicode's Default_Ignorable_Code_Point less Cf):
# invisible, yet a pass over category Cf keeps them. Between two ASCII letters or digits they join or vary nothing, and
# there "9\ufe0f0 days" displayed "90 days" while the day parser read 0 (triage review, 2026-10-08). Elsewhere a reading
# keeps them: a variation selector chooses an emoji's or a CJK character's form, and a keycap is a digit, U+FE0F and
# U+20E3. Written as a regular-expression class body.
IGNORABLE = "\u034f\u115f\u1160\u17b4\u17b5\u180b-\u180d\u180f\u3164\ufe00-\ufe0f\uffa0\U000e0100-\U000e01ef"
