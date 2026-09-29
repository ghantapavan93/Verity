"""Select the CUAD-30 corpus and its expert labels from CUAD v1, by a rule fixed before any run.

    .venv/Scripts/python scripts/cuad_corpus.py

Reads data/cuad/data.zip (CUAD v1, CC BY 4.0, The Atticus Project; provenance in data/cuad/SOURCE.txt),
writes the thirty contracts as text under data/cuad/corpus-30/, the manifest that names them under
app/batch/corpora/cuad-30.json, and the experts' spans for the seven categories we ask about under
app/batch/corpora/cuad-30-labels.json. The scoring rule is pre-registered in docs/CUAD.md.
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
import zipfile
from pathlib import Path
from typing import Any

BACKEND = Path(__file__).resolve().parents[1]
ARCHIVE = BACKEND / "data" / "cuad" / "data.zip"
CORPUS_DIR = BACKEND / "data" / "cuad" / "corpus-30"
MANIFEST = BACKEND / "app" / "batch" / "corpora" / "cuad-30.json"
LABELS = BACKEND / "app" / "batch" / "corpora" / "cuad-30-labels.json"

CATEGORIES = (
    "Governing Law",
    "Termination For Convenience",
    "Cap On Liability",
    "Uncapped Liability",
    "Non-Compete",
    "Change Of Control",
    "Most Favored Nation",
)
MIN_CHARS = 10_000
MAX_CHARS = 150_000
SIZE = 30
SELECTION_RULE = (
    f"contracts whose text has between {MIN_CHARS:,} and {MAX_CHARS:,} characters, sorted by title, "
    f"every k-th one taken from the first with k = floor(eligible / {SIZE}), the first {SIZE} kept"
)


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def slug(title: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "-", title).strip("-")[:60].lower()


def load_contracts(archive: Path) -> list[dict[str, Any]]:
    with zipfile.ZipFile(archive) as bundle, bundle.open("CUADv1.json") as handle:
        data: dict[str, Any] = json.load(handle)
    contracts: list[dict[str, Any]] = data["data"]
    return contracts


def text_of(contract: dict[str, Any]) -> str:
    context: str = contract["paragraphs"][0]["context"]
    return context


def expert_spans(contract: dict[str, Any]) -> dict[str, list[str]]:
    """The experts' answer spans per category, in the order CUAD lists them, duplicates dropped."""
    spans: dict[str, list[str]] = {category: [] for category in CATEGORIES}
    for qa in contract["paragraphs"][0]["qas"]:
        category = str(qa["id"]).rsplit("__", 1)[-1]
        if category not in spans or qa.get("is_impossible", False):
            continue
        for answer in qa["answers"]:
            text = str(answer["text"]).strip()
            if text and text not in spans[category]:
                spans[category].append(text)
    return spans


def select(contracts: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], int, int]:
    eligible = sorted((c for c in contracts if MIN_CHARS <= len(text_of(c)) <= MAX_CHARS), key=lambda c: str(c["title"]))
    step = len(eligible) // SIZE
    return eligible[::step][:SIZE], len(eligible), step


def main() -> int:
    if not ARCHIVE.exists():
        print(f"missing {ARCHIVE}; see data/cuad/SOURCE.txt for where it comes from")
        return 2
    contracts = load_contracts(ARCHIVE)
    chosen, eligible, step = select(contracts)
    CORPUS_DIR.mkdir(parents=True, exist_ok=True)
    for stale in CORPUS_DIR.glob("*.txt"):
        stale.unlink()
    entries: list[dict[str, Any]] = []
    labels: dict[str, dict[str, list[str]]] = {}
    for index, contract in enumerate(chosen, start=1):
        title = str(contract["title"])
        text = text_of(contract)
        name = f"{index:02d}-{slug(title)}.txt"
        (CORPUS_DIR / name).write_text(text, encoding="utf-8", newline="\n")
        entries.append({"file": name, "title": title, "chars": len(text), "sha256": sha256_text(text)})
        labels[title] = expert_spans(contract)
    manifest = {
        "source": {
            "file": "data/cuad/data.zip",
            "sha256": hashlib.sha256(ARCHIVE.read_bytes()).hexdigest(),
            "licence": "CC BY 4.0, The Atticus Project, CUAD v1",
            "url": "https://github.com/TheAtticusProject/cuad/raw/main/data.zip",
        },
        "selection": {"rule": SELECTION_RULE, "eligible": eligible, "step": step, "size": len(chosen), "of": len(contracts)},
        "categories": list(CATEGORIES),
        "contracts": entries,
    }
    MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST.write_text(json.dumps(manifest, indent=1, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    LABELS.write_text(json.dumps(labels, indent=1, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    print(f"{len(chosen)} contracts of {eligible} eligible (of {len(contracts)}), step {step}, written to {CORPUS_DIR}")
    for category in CATEGORIES:
        with_span = sum(1 for title in labels if labels[title][category])
        print(f"  {category:28} experts found a span in {with_span:2} of {len(chosen)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
