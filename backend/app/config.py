"""Runtime settings. Everything has a default that works on a laptop with Ollama running."""

from __future__ import annotations

import json
import os
from pathlib import Path

from pydantic import BaseModel

BACKEND_DIR = Path(__file__).resolve().parents[1]


class Settings(BaseModel):
    data_dir: Path = Path(os.environ.get("WORKBENCH_DATA_DIR", BACKEND_DIR / "data"))
    database_url: str = os.environ.get("WORKBENCH_DATABASE_URL", "")
    provider: str = os.environ.get("WORKBENCH_PROVIDER", "ollama")
    model: str = os.environ.get("WORKBENCH_MODEL", "qwen3:8b")
    ollama_url: str = os.environ.get("WORKBENCH_OLLAMA_URL", "http://localhost:11434")
    # The same decoding settings that produced schema-valid output across 250 calls in A1-lite.
    temperature: float = 0.0
    seed: int = 42
    num_ctx: int = 16384
    model_timeout_s: float = 600.0
    # Model calls in flight per process (providers.admission). One GPU serialises them anyway; the bound makes the queue visible.
    model_concurrency: int = int(os.environ.get("WORKBENCH_MODEL_CONCURRENCY", "1"))
    # Sections handed to the model per run. Six covers a clause, its neighbours and one or two
    # cross-referenced sections without crowding an 8B model's context.
    retrieval_k: int = int(os.environ.get("WORKBENCH_RETRIEVAL_K", "6"))  # part of a run's identity; ten is the measured candidate (docs/RETRIEVAL.md)
    # Characters of each handed section the prompt carries: the reader's split, so a part is handed whole (before 2026-10-01 it was
    # 5,000 and 6 of 111 CUAD-30 expert spans lay beyond it in their section). Part of a run's identity.
    # 6,000 since 2026-10-01: measured on the 44 goldens (37 of 44, no change) and the six beyond-window CUAD cases (4 correct
    # against 2), see docs/RETRIEVAL.md. Recorded on every run; a run recorded before the option was made at 5,000.
    section_window: int = int(os.environ.get("WORKBENCH_SECTION_WINDOW", "6000"))
    retrieval: str = os.environ.get("WORKBENCH_RETRIEVAL", "bm25")  # bm25 | hybrid (docs/RETRIEVAL.md)
    # The legal alias table joins the retrieval query (retrieval/aliases.py); part of a run's identity when on. On since
    # 2026-10-01: Recall@6 on CUAD 0.85 to 0.97 with no model, 37 of 44 goldens with no regression (docs/RETRIEVAL.md).
    retrieval_aliases: bool = os.environ.get("WORKBENCH_RETRIEVAL_ALIASES", "1").lower() in ("1", "true", "yes")
    embed_model: str = os.environ.get("WORKBENCH_EMBED_MODEL", "nomic-embed-text")
    prompt_version: str = os.environ.get("WORKBENCH_PROMPT_VERSION", "answer-v2")
    # task → model overrides, each justified by a measurement in docs/ROUTING.md; empty means the default model for every task.
    routing_policy: dict[str, str] = json.loads(os.environ.get("WORKBENCH_ROUTING_POLICY", "{}"))
    replay_file: Path = Path(os.environ.get("WORKBENCH_REPLAY_FILE", BACKEND_DIR.parent / "e2e" / "replay.json"))
    cors_origins: list[str] = [
        o.strip() for o in os.environ.get("WORKBENCH_CORS_ORIGINS", "http://localhost:3900,http://127.0.0.1:3900").split(",") if o.strip()
    ]
    # Where the interface runs, for links that lead from a memo or an evidence pack back to a run.
    app_url: str = os.environ.get("WORKBENCH_APP_URL", "http://localhost:3900").rstrip("/")
    # Optional: the results.json of the ivo-experiments repository, for the Runs surface, and the
    # published page it was built for (links become "Open experiment" → <url>#<id>).
    experiments_results: Path | None = Path(os.environ["WORKBENCH_EXPERIMENTS_RESULTS"]) if os.environ.get("WORKBENCH_EXPERIMENTS_RESULTS") else None
    experiments_url: str | None = os.environ.get("WORKBENCH_EXPERIMENTS_URL") or None

    @property
    def sqlite_url(self) -> str:
        if self.database_url:
            return self.database_url
        self.data_dir.mkdir(parents=True, exist_ok=True)
        return f"sqlite:///{(self.data_dir / 'workbench.db').as_posix()}"


settings = Settings()
