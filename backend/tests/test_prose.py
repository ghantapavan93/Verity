"""The model's section handles never reach a reader: they become the section's own label, or a visible mark that the
model named a section it was not given. An unknown handle is never dropped: dropping left "found in.3." and hid the
reference from the check that lowers such a pass (status.check_references)."""

from __future__ import annotations

import pytest

from app.runs.prose import UNRESOLVED, label_handles, unresolved_handles

LABELS = {"sec_55": "§9.1", "sec_60": "§9.5.1", "sec_3": "Cover Page"}


def test_handles_become_section_labels() -> None:
    assert label_handles("…legal expenses, and other costs. [sec_55]", LABELS) == "…legal expenses, and other costs. §9.1"
    assert label_handles("See sec_60 and [ sec_55 ] together.", LABELS) == "See §9.5.1 and §9.1 together."
    assert label_handles("Defined on the cover (sec_3).", LABELS) == "Defined on the cover (Cover Page)."


def test_an_unknown_handle_is_marked_and_reported_never_dropped() -> None:
    assert label_handles("Old versions of the Product. [sec_99]", LABELS) == f"Old versions of the Product. {UNRESOLVED}"
    assert label_handles("As stated (sec_99) above, fees apply.", LABELS) == f"As stated ({UNRESOLVED}) above, fees apply."
    assert label_handles("Section sec_99 .", LABELS) == f"Section {UNRESOLVED}."
    assert unresolved_handles("See sec_55, [sec_99] and sec_7.", LABELS) == ["[sec_99]", "sec_7"]


def test_a_handle_with_sub_numbering_is_no_handle_and_never_joins_a_label() -> None:
    # "sec_55.2(b)" read as sec_55 + ".2(b)" would print "§9.1.2(b)", a clause number the model never wrote.
    for text in ("This is found in sec_55.2(b).", "found in sec_12.3."):
        labelled = label_handles(text, LABELS)
        assert "§9.1." not in labelled and ".3." not in labelled and UNRESOLVED in labelled
        assert unresolved_handles(text, LABELS) == [text.split("in ")[1].rstrip(".")]
    # Control: a known handle beside a full stop is still that section.
    assert label_handles("See sec_55.", LABELS) == "See §9.1." and unresolved_handles("See sec_55.", LABELS) == []


def test_prose_without_handles_is_untouched_and_none_stays_none() -> None:
    text = "Customer may terminate on 15 days' written notice; the guidance requires at least 30 days."
    assert label_handles(text, LABELS) == text
    assert label_handles(None, LABELS) is None
    assert label_handles("second_sec_1 is not a handle", LABELS) == "second_sec_1 is not a handle"


@pytest.mark.parametrize(
    "written",
    ["sec_7(b)", "sec_7(iv)", "sec_7(B)", "sec_7,2", "[sec_7.1]", "[ sec_7(b) ]", "sec_7.1(a)(ii)", "sec_7 (b)", "sec_7(a", "sec_7-9", "sec_7 ,2", "sec_7 .2"],
)
def test_every_sub_reference_after_a_given_handle_is_no_address_and_never_joins_its_label(written: str) -> None:
    # sec_7 is a handle the run gave; what follows it names a part code cannot place, so it is never written as "§3(b)",
    # "§3,2" or "[§3.1]": a clause number the model did not write.
    labels = {"sec_7": "§3"}
    text = label_handles(f"See {written} for the rule.", labels)
    assert text == f"See {UNRESOLVED} for the rule." and "§3" not in text
    assert unresolved_handles(f"See {written}.", labels) == [written]


@pytest.mark.parametrize(
    ("written", "shown"),
    [
        ("sec_7 and sec_8", "§3 and §4"),
        ("sec_7, sec_8", "§3, §4"),
        ("[sec_7]", "§3"),
        ("sec_7 (fees)", "§3 (fees)"),
        ("sec_7(Payment)", "§3(Payment)"),
        ("sec_7, 30 days", "§3, 30 days"),
        ("sec_7. 30 days", "§3. 30 days"),
    ],
)
def test_control_a_handle_followed_by_a_space_or_another_handle_is_labelled(written: str, shown: str) -> None:
    labels = {"sec_7": "§3", "sec_8": "§4"}
    assert label_handles(f"See {written}.", labels) == f"See {shown}." and unresolved_handles(f"See {written}.", labels) == []
