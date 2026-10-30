"""A replay searches the window its run was verified over (stress test, 2026-10-30, architecture 3).

reverify_run called verify_evidence without a window, so it searched the legacy 5,000 characters of each section while
every run since 2026-10-01 was verified over its recorded 6,000: a quote the run verified between the two replayed as
"lost", and a gain there could not be seen. A replay of an unchanged verifier must reproduce the run.
"""

from __future__ import annotations

import ast
from pathlib import Path

from fastapi.testclient import TestClient

from app.application.reverify_run import reverify_run
from app.db import SessionLocal
from tests.support import CONTRACT

FILLER = "The parties shall cooperate in good faith on every operational matter under this Agreement. " * 58
QUESTION = "What notice period applies to termination for convenience?"


def test_a_quote_past_the_old_window_and_inside_the_recorded_one_replays_as_it_was_verified(client: TestClient) -> None:
    contract = CONTRACT.replace("Customer may terminate this Agreement", FILLER + "Customer may terminate this Agreement")
    uploaded = client.post("/api/documents", files={"file": ("long.txt", contract.encode("utf-8"), "text/plain")}).json()
    run = client.post("/api/runs", json={"documentId": uploaded["id"], "guidanceId": None, "question": QUESTION}).json()
    spans = client.get(f"/api/runs/{run['id']}").json()["findings"][0]["spans"]
    assert spans[0]["verified"] and 5000 < spans[0]["start"] < spans[0]["end"] <= 6000, spans  # verified past 5,000
    with SessionLocal() as session:
        replay = reverify_run(session, run["id"])
    assert [s.change for s in replay.spans] == ["same"], [(s.change, s.method) for s in replay.spans]


WINDOWED = {"verify_evidence", "context_slice", "build_user_message"}


def test_every_call_that_reads_a_window_says_which_one() -> None:
    # The default is the legacy 5,000, which no run since 2026-10-01 was made at: a caller that leaves it out reads
    # another slice of each section than its run did.
    app = Path(__file__).resolve().parents[1] / "app"
    missing = []
    for path in app.rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Call):
                name = node.func.attr if isinstance(node.func, ast.Attribute) else getattr(node.func, "id", "")
                if name in WINDOWED and not any(keyword.arg == "window" for keyword in node.keywords):
                    missing.append(f"{path.relative_to(app)}:{node.lineno} {name}")
    assert missing == []
