"""Build the SkillOpt training data from CUAD v1, disjoint from CUAD-30, before any run.

    .venv/Scripts/python experiments/skillopt/build_data.py

Same eligibility and stride as scripts/cuad_corpus.py (contracts of 10,000 to 150,000 characters, sorted by
title, every 13th), starting six positions later, so no contract is shared with CUAD-30. Thirty contracts:
the first three are the training split (SkillOpt trains on the whole split, so the split is the budget),
the next three the validation set that gates every edit, the rest a reserve that no run reads.
One item per contract and question of the cuad-clauses task, with the experts'
spans as its label. Texts go under data/skillopt/data/contracts (ignored); the manifest that names them
goes under app/batch/corpora/cuad-skillopt.json (committed).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

BACKEND = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BACKEND / "scripts"))
sys.path.insert(0, str(BACKEND))

from cuad_corpus import ARCHIVE, CATEGORIES, MAX_CHARS, MIN_CHARS, SIZE, expert_spans, load_contracts, slug, text_of  # noqa: E402

DATA = BACKEND / "data" / "skillopt" / "data"
MANIFEST = BACKEND / "app" / "batch" / "corpora" / "cuad-skillopt.json"
CUAD_30 = BACKEND / "app" / "batch" / "corpora" / "cuad-30.json"
TASK = BACKEND / "app" / "batch" / "tasks" / "cuad-clauses.json"
OFFSET = 6
TRAIN_CONTRACTS = 3  # SkillOpt trains on the whole split, so the split is the budget: 3 x 7 = 21 items
VAL_CONTRACTS = 3  # 21 items gate every edit


def splits(train: int, val: int) -> dict[str, range]:
    return {"train": range(train), "val": range(train, train + val), "test": range(train + val, SIZE)}


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--train", type=int, default=TRAIN_CONTRACTS, help="contracts in the training split")
    parser.add_argument("--val", type=int, default=VAL_CONTRACTS, help="contracts in the validation split")
    args = parser.parse_args(argv)
    split_ranges = splits(args.train, args.val)
    contracts = load_contracts(ARCHIVE)
    eligible = sorted((c for c in contracts if MIN_CHARS <= len(text_of(c)) <= MAX_CHARS), key=lambda c: str(c["title"]))
    step = len(eligible) // SIZE
    chosen = eligible[OFFSET::step][:SIZE]
    taken = {c["title"] for c in json.loads(CUAD_30.read_text(encoding="utf-8"))["contracts"]}
    overlap = [str(c["title"]) for c in chosen if str(c["title"]) in taken]
    if overlap:
        print(f"refusing: {len(overlap)} contracts overlap CUAD-30: {overlap[:3]}")
        return 2
    fields: list[dict[str, Any]] = json.loads(TASK.read_text(encoding="utf-8"))["fields"]

    contracts_dir = DATA / "contracts"
    contracts_dir.mkdir(parents=True, exist_ok=True)
    entries: list[dict[str, Any]] = []
    items: dict[str, list[dict[str, Any]]] = {split: [] for split in split_ranges}
    for index, contract in enumerate(chosen):
        title = str(contract["title"])
        text = text_of(contract)
        name = f"{index + 1:02d}-{slug(title)}.txt"
        path = contracts_dir / name
        path.write_text(text, encoding="utf-8", newline="\n")
        split = next(s for s, positions in split_ranges.items() if index in positions)
        entries.append({"file": name, "title": title, "chars": len(text), "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(), "split": split})
        spans = expert_spans(contract)
        for field in fields:
            category = str(field["cuad_category"])
            items[split].append(
                {
                    "id": f"c{index + 1:02d}__{field['key']}",  # short: SkillOpt makes a directory per id and Windows caps paths at 260 chars
                    "task_type": str(field["key"]),
                    "field": str(field["key"]),
                    "question": str(field["question"]),
                    "category": category,
                    "contract_file": str(path),
                    "contract_name": name,
                    "title": title,
                    "expert_spans": spans.get(category, []),
                }
            )
    for split, split_items in items.items():
        (DATA / split).mkdir(parents=True, exist_ok=True)
        (DATA / split / "items.json").write_text(json.dumps(split_items, indent=1, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    manifest = {
        "source": "data/cuad/data.zip, see data/cuad/SOURCE.txt (CUAD v1, CC BY 4.0, The Atticus Project)",
        "selection": {
            "rule": f"same eligibility and stride as cuad-30 ({MIN_CHARS:,} to {MAX_CHARS:,} characters, sorted by title, step {step}), offset {OFFSET}",
            "eligible": len(eligible),
            "step": step,
            "offset": OFFSET,
            "disjoint_from": "cuad-30.json",
        },
        "splits": {split: [entries[i]["file"] for i in positions] for split, positions in split_ranges.items()},
        "categories": list(CATEGORIES),
        "contracts": entries,
    }
    MANIFEST.write_text(json.dumps(manifest, indent=1, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    for split, split_items in items.items():
        with_span = sum(1 for item in split_items if item["expert_spans"])
        print(f"{split:5} {len(split_items):3} items, {with_span:3} with an expert span")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
