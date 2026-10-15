"""The model's prose reaches a reader with the model's section handles replaced.

The model cites sections by the handle it was handed ("sec_12"). A handle is an internal address
for one run, not a citation, so before a finding is stored it is rewritten as the section's own
label ("§5.4", or the heading when the section is unnumbered). The raw output keeps the handles.

A handle that names no section of the run, or one the model followed with a sub-reference ("sec_12.3", "sec_1.2(b)",
"sec_4 (b)", "sec_1,2", "sec_1-3", "[sec_3.1]"), is no address of this run: it is shown as UNRESOLVED, never dropped
(dropping left "found in.3." and hid the reference from the check), and never joined to a label (reading "sec_1.2" as
"§7" + ".2" wrote a clause number the model did not).
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import overload

# A paragraph marker: a letter, a roman numeral or a short number in brackets, the closing bracket optional ("(b)",
# "(iv)", "(B)", "(2)", "(a"). A word in brackets is not one: "(fees)", "(term)", "(Payment)".
PARAGRAPH = r"\(\s*(?:[ivxlc]{1,5}|[a-z]|[A-Z]|\d{1,2})(?![A-Za-z0-9])(?:\s*\))?"
# What can follow a handle and make it a sub-reference, so that labelling it would write a clause number the model
# did not: sub-numbering (".2", " .2", ".2(b)"), paragraphs (with or without a space), a comma and digits written
# against it ("sec_1,2", "sec_1 ,2"), or a range ("sec_1-3"). The cleanup below closes "§7 ,2" into "§7,2", so the
# spaced forms count too. "sec_5, 30 days" is ordinary prose and is labelled.
SUB_REFERENCE = rf"\s*\.\d+(?:\.\d+)*(?:\s*{PARAGRAPH})*|(?:\s*{PARAGRAPH})+|\s*,\d+|\s*[-\u2013]\s*\d+"
HANDLE = re.compile(
    rf"\[\s*sec_(?P<bracketed>\d+)(?P<bracketed_sub>{SUB_REFERENCE})?\s*\]"
    rf"|\bsec_(?P<bare>\d+)(?:(?P<bare_sub>{SUB_REFERENCE})|\b)"
)
UNRESOLVED = "[unidentified section]"
_SPACE_BEFORE_STOP = re.compile(r"\s+([.,;:)\]])")
_EMPTY_BRACKETS = re.compile(r"\(\s*\)|\[\s*\]")
_SPACES = re.compile(r"[ \t]{2,}")


def _label(match: re.Match[str], labels: Mapping[str, str]) -> str | None:
    if match.group("bracketed_sub") or match.group("bare_sub"):  # a sub-reference after the handle: not an address of this run
        return None
    return labels.get(f"sec_{match.group('bracketed') or match.group('bare')}")


def unresolved_handles(text: str | None, labels: Mapping[str, str]) -> list[str]:
    """The handles in ``text`` that name no section the run handed the model, as the model wrote them."""
    return [match.group(0) for match in HANDLE.finditer(text or "") if _label(match, labels) is None]


@overload
def label_handles(text: str, labels: Mapping[str, str]) -> str: ...
@overload
def label_handles(text: None, labels: Mapping[str, str]) -> None: ...


def label_handles(text: str | None, labels: Mapping[str, str]) -> str | None:
    """Replace every sec_N handle with that section's label, and one that names no section with UNRESOLVED."""
    if text is None:
        return None
    cleaned = HANDLE.sub(lambda match: _label(match, labels) or UNRESOLVED, text)
    cleaned = _EMPTY_BRACKETS.sub("", cleaned)
    cleaned = _SPACE_BEFORE_STOP.sub(r"\1", cleaned)
    return _SPACES.sub(" ", cleaned).strip()
