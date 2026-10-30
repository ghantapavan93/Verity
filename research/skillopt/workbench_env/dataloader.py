"""Items for SkillOpt: one per contract and question, with the experts' spans as the label.

The split directory is built by experiments/skillopt/build_data.py: train/, val/ and test/, each with
an items.json. A missing split is empty rather than an error, because the reserve split is never read.
"""

from __future__ import annotations

import json
from pathlib import Path

from skillopt.datasets.base import SplitDataLoader


class WorkbenchDataLoader(SplitDataLoader):
    def load_split_items(self, split_path: str) -> list[dict]:
        path = Path(split_path) / "items.json"
        if not path.exists():
            return []
        items: list[dict] = json.loads(path.read_text(encoding="utf-8"))
        return items
