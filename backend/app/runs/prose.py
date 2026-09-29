"""The model's prose reaches a reader with the model's section handles replaced.

The model cites sections by the handle it was handed ("sec_12"). A handle is an internal address
for one run, not a citation, so before a finding is stored it is rewritten as the section's own
label ("§5.4", or the heading when the section is unnumbered). The raw output keeps the handles.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import overload

HANDLE = re.compile(r"\[\s*sec_(\d+)\s*\]|\bsec_(\d+)\b")
_SPACE_BEFORE_STOP = re.compile(r"\s+([.,;:)\]])")
_EMPTY_BRACKETS = re.compile(r"\(\s*\)|\[\s*\]")
_SPACES = re.compile(r"[ \t]{2,}")


@overload
def label_handles(text: str, labels: Mapping[str, str]) -> str: ...
@overload
def label_handles(text: None, labels: Mapping[str, str]) -> None: ...


def label_handles(text: str | None, labels: Mapping[str, str]) -> str | None:
    """Replace every sec_N handle with that section's label; drop handles that name no section."""
    if text is None:
        return None

    def replace(match: re.Match[str]) -> str:
        ordinal = match.group(1) or match.group(2)
        return labels.get(f"sec_{ordinal}", "")

    cleaned = HANDLE.sub(replace, text)
    cleaned = _EMPTY_BRACKETS.sub("", cleaned)
    cleaned = _SPACE_BEFORE_STOP.sub(r"\1", cleaned)
    return _SPACES.sub(" ", cleaned).strip()
