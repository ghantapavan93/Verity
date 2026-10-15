"""The amended sample the first screen offers (src/components/workbench/samples.ts) shows what it is offered for.

It is synthetic, written for the first-visitor tests: Amendment No. 1 deletes clause 7.2 and replaces it. Its three
questions ask the same point as the agreement stands, as first signed, and at a time before the amendment took effect,
so a reviewer sees code's three readings: a replaced quote set to needs review, the original noted as context, and a
concern naming the time. If the file or the questions change, this says whether the sample still shows that.
"""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path
from types import SimpleNamespace

from app.ingest import ingest
from app.runs.relations import locate_relations, perspective

REPO = Path(__file__).resolve().parents[2]
SAMPLES = (REPO / "src" / "components" / "workbench" / "samples.ts").read_text(encoding="utf-8")


def _amended() -> tuple[str, list[str]]:
    block = SAMPLES[SAMPLES.index("amended: {") :]
    path = re.search(r'path: "([^"]+)"', block)
    questions = re.search(r"questions: \[(.*?)\]", block, re.S)
    assert path and questions
    return path.group(1), re.findall(r'"([^"]+)"', questions.group(1))


def test_the_amended_sample_replaces_a_clause_in_full_and_its_questions_ask_three_ways() -> None:
    path, questions = _amended()
    data = (REPO / "public" / path.lstrip("/")).read_bytes()
    sections = [
        SimpleNamespace(id=f"s{i}", number=s.number, heading=s.heading, text=s.text) for i, s in enumerate(ingest(path.rsplit("/", 1)[-1], data).sections)
    ]
    replaces = {r.target: r for r in locate_relations(sections, date(2026, 10, 15)) if r.kind == "replaces"}
    # 7.2, which the questions ask about, is replaced in full; 4.3 is changed only for one site and one year, a limit.
    assert replaces.keys() == {"7.2", "4.3"} and replaces["7.2"].scope is None and replaces["4.3"].scope is not None
    assert replaces["7.2"].replaced is not None and replaces["7.2"].replacement is not None
    assert [perspective(q) for q in questions] == ["current", "historical", "dated"]
