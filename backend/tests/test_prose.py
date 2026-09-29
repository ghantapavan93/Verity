"""The model's section handles never reach a reader: they become the section's own label, or nothing."""

from __future__ import annotations

from app.runs.prose import label_handles

LABELS = {"sec_55": "§9.1", "sec_60": "§9.5.1", "sec_3": "Cover Page"}


def test_handles_become_section_labels() -> None:
    assert label_handles("…legal expenses, and other costs. [sec_55]", LABELS) == "…legal expenses, and other costs. §9.1"
    assert label_handles("See sec_60 and [ sec_55 ] together.", LABELS) == "See §9.5.1 and §9.1 together."
    assert label_handles("Defined on the cover (sec_3).", LABELS) == "Defined on the cover (Cover Page)."


def test_unknown_handles_are_dropped_cleanly() -> None:
    assert label_handles("Old versions of the Product. [sec_99]", LABELS) == "Old versions of the Product."
    assert label_handles("As stated (sec_99) above, fees apply.", LABELS) == "As stated above, fees apply."
    assert label_handles("Section sec_99 .", LABELS) == "Section."


def test_prose_without_handles_is_untouched_and_none_stays_none() -> None:
    text = "Customer may terminate on 15 days' written notice; the guidance requires at least 30 days."
    assert label_handles(text, LABELS) == text
    assert label_handles(None, LABELS) is None
    assert label_handles("second_sec_1 is not a handle", LABELS) == "second_sec_1 is not a handle"
