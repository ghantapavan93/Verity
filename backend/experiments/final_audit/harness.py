"""Shared by the audit probes: an isolated store (temp dir, its own SQLite file), the app bound to it, a scriptable
provider, and a results recorder. Nothing here touches the production store."""

from __future__ import annotations

import json
import re
import sys
import tempfile
import threading
import time
from pathlib import Path
from typing import Any

BACKEND = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BACKEND))

from fastapi.testclient import TestClient

from app import config
from app import db as db_module
from app.main import create_app
from app.providers.base import Generation, ProviderError

CONTRACT = """SERVICES AGREEMENT

1. Term

This Agreement commences on the Effective Date and continues for twelve (12) months.

2. Termination for Convenience

Either party may terminate this Agreement for convenience upon sixty (60) days' written notice to the other party. On termination, Customer pays all Fees accrued.

3. Governing Law

This Agreement is governed by the laws of the State of Delaware.

4. Notices

Notices under this Agreement are sent in writing to the address on the Order Form.
"""
GUIDANCE = "We require at least 90 days' written notice for termination for convenience. Anything shorter needs review."
QUOTE = "Either party may terminate this Agreement for convenience upon sixty (60) days' written notice to the other party."


class ScriptedProvider:
    """A model that behaves like the hero case unless told otherwise: it proposes "pass", cites the WRONG section, and
    quotes the right words. Knobs: delay_s (hold every answer), fail_next (raise ProviderError n times), garbage."""

    name = "fake"
    model = "scripted-1"

    def __init__(self) -> None:
        self.calls: list[str] = []
        self.delay_s = 0.0
        self.fail_next = 0
        self.garbage = False
        self.payload: dict[str, Any] | None = None
        self._lock = threading.Lock()

    def healthy(self) -> tuple[bool, str]:
        return True, "scripted"

    def generate_json(self, system: str, user: str, schema: dict[str, Any]) -> Generation:
        with self._lock:
            self.calls.append(user)
            fail = self.fail_next > 0
            if fail:
                self.fail_next -= 1
        if self.delay_s:
            time.sleep(self.delay_s)
        if fail:
            raise ProviderError("simulated: the model endpoint timed out")
        if self.garbage:
            return Generation(text="not json", input_tokens=1, output_tokens=1, latency_ms=1.0, model=self.model)
        if self.payload is not None:
            return Generation(text=json.dumps(self.payload), input_tokens=10, output_tokens=10, latency_ms=2.0, model=self.model)
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


class Store:
    def __init__(self, provider: Any | None = None, prefix: str = "verity-audit-") -> None:
        self.dir = Path(tempfile.mkdtemp(prefix=prefix))
        self.db_path = self.dir / "audit.db"
        self.engine = db_module.make_engine(f"sqlite:///{self.db_path.as_posix()}")
        db_module.engine = self.engine
        db_module.SessionLocal.configure(bind=self.engine)
        config.settings.data_dir = self.dir
        self.provider = provider or ScriptedProvider()
        self.app = create_app(provider=self.provider)
        self.client = TestClient(self.app, raise_server_exceptions=False).__enter__()

    def upload(self, text: str = CONTRACT, name: str = "agreement.txt") -> dict[str, Any]:
        r = self.client.post("/api/documents", files={"file": (name, text.encode("utf-8"), "text/plain")})
        assert r.status_code in (200, 201), r.text
        return r.json()

    def guidance(self, text: str = GUIDANCE) -> str:
        r = self.client.post("/api/guidance", json={"text": text})
        assert r.status_code in (200, 201), r.text
        return r.json()["id"]

    def ask(self, document_id: str, question: str, guidance_id: str | None = None) -> Any:
        return self.client.post("/api/runs", json={"documentId": document_id, "guidanceId": guidance_id, "question": question})

    def wait(self, run_id: str, timeout_s: float = 60.0) -> dict[str, Any]:
        deadline = time.time() + timeout_s
        while time.time() < deadline:
            run = self.client.get(f"/api/runs/{run_id}").json()
            if run["stage"] in ("complete", "failed", "unresolved"):
                return run
            time.sleep(0.02)
        raise TimeoutError(run_id)

    def complete_run(self, question: str = "May either party terminate for convenience, and on what notice?") -> dict[str, Any]:
        doc = self.upload()
        gid = self.guidance()
        started = self.ask(doc["id"], question, gid)
        assert started.status_code in (200, 202), started.text
        return self.wait(started.json()["id"])


class Report:
    def __init__(self, title: str) -> None:
        self.title = title
        self.rows: list[tuple[str, str, str]] = []
        print(f"##### {title}")

    def note(self, name: str, outcome: str, detail: str = "") -> None:
        """outcome: PASS, FAIL, or INFO (a measurement, not a verdict)."""
        self.rows.append((name, outcome, detail))
        print(f"{outcome:4}  {name}" + (f"  - {detail}" if detail else ""))

    def check(self, name: str, ok: bool, detail: str = "") -> bool:
        self.note(name, "PASS" if ok else "FAIL", detail)
        return ok

    def done(self) -> None:
        fails = [r for r in self.rows if r[1] == "FAIL"]
        print(
            f"----- {self.title}: {len([r for r in self.rows if r[1] == 'PASS'])} pass, {len(fails)} fail, {len([r for r in self.rows if r[1] == 'INFO'])} info"
        )
