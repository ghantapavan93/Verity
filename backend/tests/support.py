"""Shared by every API test: a small contract, a fake provider that answers like a well-behaved model
and can be told to misbehave, and the upload-and-ask helper. The client fixture is in conftest.py."""

from __future__ import annotations

import json
import os
import re
from typing import Any

from fastapi.testclient import TestClient

from app.providers.base import Generation, ProviderError

CONTRACT = """SERVICES AGREEMENT

1. Term

This Agreement commences on the Effective Date and continues for twelve (12) months.

2. Termination for Convenience

Customer may terminate this Agreement for convenience upon fifteen (15) days’ written notice to Provider. On termination, Customer pays all Fees accrued.

3. Governing Law

This Agreement is governed by the laws of the State of Delaware.
"""

GUIDANCE = "We can accept termination for convenience at 30 days' notice or more. Anything below 30 days requires review."


class FakeProvider:
    """Answers like a well-behaved model: quotes verbatim from the section it was handed."""

    name = "fake"
    model = "fake-1"

    def __init__(self, paraphrase: bool = False) -> None:
        self.paraphrase = paraphrase
        self.calls: list[str] = []

    def healthy(self) -> tuple[bool, str]:
        return True, "fake"

    def generate_json(self, system: str, user: str, schema: dict[str, Any]) -> Generation:
        self.calls.append(user)
        if getattr(self, "fail_always", False):
            raise ProviderError("Ollama not reachable at http://localhost:11434: connection refused")
        if getattr(self, "fail_once", False):
            self.fail_once = False
            raise ProviderError("Ollama request failed: timed out")
        if getattr(self, "garbage", False):
            return Generation(text="not json at all", input_tokens=10, output_tokens=3, latency_ms=5.0, model=self.model)
        if getattr(self, "no_evidence", False):
            payload = {
                "findings": [
                    {
                        "topic": "Termination",
                        "conclusion": "Nothing was found.",
                        "status_hint": "missing",
                        "evidence": [],
                        "guidance_reference": None,
                        "observed": None,
                        "required": None,
                        "suggested_position": None,
                    }
                ],
                "insufficient_evidence": False,
                "note": None,
            }
            return Generation(text=json.dumps(payload), input_tokens=10, output_tokens=3, latency_ms=5.0, model=self.model)
        match = re.search(r"\[(sec_\d+)\] 2 Termination for Convenience\n(.+?)(?:\n\n\[|\Z)", user, re.S)
        assert match, "the termination section was not handed to the model"
        label, body = match.group(1), match.group(2)
        quote = "Customer may terminate this Agreement for convenience upon fifteen (15) days’ written notice to Provider."
        assert quote in body
        if self.paraphrase:
            quote = "The customer can walk away with about two weeks of notice."
        conclusion = f"Customer may terminate for convenience on 15 days' written notice; the guidance requires at least 30 days. [{label}]"
        if getattr(self, "invented_reference", False):
            conclusion = f"Section 14.2 grants the Customer most favoured nation pricing. [{label}]"  # a real quote under an invented reference
        cited = label
        if getattr(self, "cite_wrong_section", False):
            cited = "sec_0" if label != "sec_0" else "sec_9"  # a real quote attributed to another section, as an 8B model sometimes does
        payload = {
            "findings": [
                {
                    "topic": "Termination for convenience",
                    "conclusion": conclusion,
                    "status_hint": "pass",
                    "evidence": [{"section_id": cited, "quote": quote}],
                    "guidance_reference": "at 30 days' notice or more",
                    "observed": "15 days' written notice",
                    "required": "at least 30 days",
                    "suggested_position": "Change fifteen (15) days to thirty (30) days.",
                }
            ],
            "insufficient_evidence": False,
            "note": None,
        }
        return Generation(text=json.dumps(payload), input_tokens=100, output_tokens=50, latency_ms=12.5, model=self.model)


# Multiplies every Hypothesis and Schemathesis budget. WORKBENCH_FUZZ_SCALE=20 is the deep pass recorded in
# docs/VALIDATION.md; the default keeps the suite under half a minute.
FUZZ_SCALE = int(os.environ.get("WORKBENCH_FUZZ_SCALE", "1"))


def upload_and_ask(client: TestClient, question: str, with_guidance: bool = True) -> dict[str, Any]:
    uploaded = client.post("/api/documents", files={"file": ("agreement.txt", CONTRACT.encode("utf-8"), "text/plain")})
    assert uploaded.status_code in (200, 201), uploaded.text  # 200: the same bytes were stored earlier in this test
    document = uploaded.json()
    guidance_id = None
    if with_guidance:
        created = client.post("/api/guidance", json={"text": GUIDANCE})
        assert created.status_code in (200, 201)  # 200: the same guidance words were saved earlier in this test
        guidance_id = created.json()["id"]
    started = client.post("/api/runs", json={"documentId": document["id"], "guidanceId": guidance_id, "question": question})
    assert started.status_code == 202, started.text
    run_id = started.json()["id"]
    return {"document": document, "run": client.get(f"/api/runs/{run_id}").json(), "run_id": run_id}
