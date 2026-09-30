"""A prompt file is frozen once a run has used it: its sha256 is recorded in prompts/manifest.json and this test fails
when the file no longer matches. A changed prompt is a new version file, never a rewrite, because a run's identity
carries the prompt hash and its input is rebuilt from the file (application.reconstruct_input). The 57 runs recorded
before the message format settled, and one under an earlier text of answer-v2, remain unreconstructable; that history
is not rewritten to pass."""

from __future__ import annotations

import json

from app.analysis.service import PROMPTS_DIR, load_prompt
from app.hashing import sha256_text

MANIFEST = PROMPTS_DIR / "manifest.json"


def test_every_prompt_file_hashes_to_what_the_manifest_recorded() -> None:
    recorded: dict[str, str] = json.loads(MANIFEST.read_text(encoding="utf-8"))
    files = {path.stem: path for path in PROMPTS_DIR.glob("*.md")}
    assert set(files) == set(recorded), f"prompt files {sorted(files)} and manifest entries {sorted(recorded)} must match one to one"
    for version, path in sorted(files.items()):
        actual = sha256_text(path.read_text(encoding="utf-8"))
        assert actual == recorded[version], (
            f"{path.name} was rewritten in place (sha256 {actual[:12]} now, {recorded[version][:12]} recorded); a changed prompt is a new version file"
        )
        assert load_prompt(version).sha256 == actual, "load_prompt hashes the same bytes the manifest does"


def test_a_rewritten_prompt_would_be_caught() -> None:
    recorded: dict[str, str] = json.loads(MANIFEST.read_text(encoding="utf-8"))
    text = (PROMPTS_DIR / "answer-v2.md").read_text(encoding="utf-8")
    assert sha256_text(text + "\n\nA rule added later.") != recorded["answer-v2"]
