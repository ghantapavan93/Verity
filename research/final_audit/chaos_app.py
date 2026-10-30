"""The application for the chaos journey: the real app over an isolated store, with a scripted model.

The model behaves like the hero case (proposes "pass", cites the wrong section, quotes the right words). Markers in the
question change it: "[[slow]]" holds the answer for 10 s, "[[outage]]" fails every call. Every model call is appended
to calls.log in the data directory, so the journey can count calls from outside the process. A file named
fail-memo-once in the data directory makes the next move of a memo's DOCX fail once."""

from __future__ import annotations

import json
import os
import pathlib
import re
import sys
import time
from typing import Any

BACKEND = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BACKEND))
DATA = pathlib.Path(os.environ["WORKBENCH_DATA_DIR"])

from app.main import create_app
from app.providers.admission import AdmissionController, AdmittedProvider
from app.providers.base import Generation, ProviderError

QUOTE = "Either party may terminate this Agreement for convenience upon sixty (60) days' written notice to the other party."


class Scripted:
    name = "fake"
    model = "scripted-1"

    def healthy(self) -> tuple[bool, str]:
        return True, "scripted"

    def generate_json(self, system: str, user: str, schema: dict[str, Any]) -> Generation:
        question = user.splitlines()[0]
        with open(DATA / "calls.log", "a", encoding="utf-8") as log:
            log.write(question + "\n")
        if "[[slow]]" in question:
            time.sleep(10)
        if "[[outage]]" in question:
            raise ProviderError("simulated: the model endpoint refused the connection")
        labels = re.findall(r"\[(sec_\d+)\]", user)
        right = re.search(r"\[(sec_\d+)\] 2 Termination for Convenience", user)
        wrong = next((label for label in labels if right is None or label != right.group(1)), "sec_99")
        payload = {
            "findings": [
                {
                    "topic": "Termination for convenience",
                    "conclusion": "Either party may terminate for convenience with 60 days' written notice.",
                    "status_hint": "pass",
                    "evidence": [{"section_id": wrong, "quote": QUOTE}],
                    "guidance_reference": "We require at least 90 days' written notice for termination for convenience.",
                    "observed": "60 days' written notice",
                    "required": "at least 90 days",
                    "suggested_position": "90 days' written notice",
                }
            ],
            "insufficient_evidence": False,
            "note": None,
        }
        return Generation(text=json.dumps(payload), input_tokens=100, output_tokens=50, latency_ms=12.5, model=self.model)


_real_replace = pathlib.Path.replace


def _replace(self: pathlib.Path, target: Any) -> pathlib.Path:
    flag = DATA / "fail-memo-once"
    if str(target).endswith(".docx") and flag.exists():
        flag.unlink()
        raise OSError("injected: the memo's file could not be put in place")
    return _real_replace(self, target)


pathlib.Path.replace = _replace  # type: ignore[method-assign]

app = create_app(provider=AdmittedProvider(Scripted(), AdmissionController(limit=1), "interactive"))
