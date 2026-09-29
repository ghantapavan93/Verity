"""verify_evidence: the one place a proposed quote is located, first in the section the model cited,
then in the other candidates.

Added after the hand mutation run of 2026-09-28: disabling relocation ("for candidate in chosen"
→ "for candidate in []") left all 87 tests green although ten spans in the recorded runs carry a
relocated method. A behaviour that reaches the record needs a test that fails when it goes.
"""

from app.models import Section
from app.runs.service import verify_evidence

TERM = Section(ordinal=0, number="5", heading="Term", text="This Agreement begins on the Effective Date and continues for two (2) years.")
CURE = Section(
    ordinal=1, number="6", heading="Termination", text="Either party may terminate for a material breach not cured within thirty (30) days of notice."
)
BY_LABEL = {"sec_1": TERM, "sec_2": CURE}
CHOSEN = [TERM, CURE]


def test_a_quote_in_the_cited_section_is_found_there() -> None:
    section, located, method = verify_evidence("continues for two (2) years", "sec_1", BY_LABEL, CHOSEN)
    assert section is TERM
    assert located is not None
    assert method == "exact"


def test_a_real_quote_cited_to_the_wrong_section_is_kept_and_marked_relocated() -> None:
    section, located, method = verify_evidence("not cured within thirty (30) days", "sec_1", BY_LABEL, CHOSEN)
    assert section is CURE
    assert located is not None
    assert CURE.text[located.start : located.end] == "not cured within thirty (30) days"
    assert method == "relocated:exact"


def test_a_real_quote_under_an_unknown_label_is_still_relocated() -> None:
    section, located, method = verify_evidence("material breach", "sec_9", BY_LABEL, CHOSEN)
    assert section is CURE
    assert located is not None
    assert method == "relocated:exact"


def test_a_quote_found_nowhere_is_not_located_and_keeps_the_cited_section() -> None:
    section, located, method = verify_evidence("not cured within sixty (60) days", "sec_1", BY_LABEL, CHOSEN)
    assert section is TERM
    assert located is None
    assert method == "none"
