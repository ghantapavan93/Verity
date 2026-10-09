"""Runtime settings. Everything has a default that works on a laptop with Ollama running."""

from __future__ import annotations

import json
import os
from pathlib import Path

from pydantic import BaseModel, Field

BACKEND_DIR = Path(__file__).resolve().parents[1]


def json_headers(raw: str) -> dict[str, str]:
    """WORKBENCH_OLLAMA_HEADERS: the headers a model endpoint behind an authenticating proxy needs (a JSON object of
    names to values, from the secret store). Anything else stops the start: a model call without its credentials would
    fail on every run instead."""
    if not raw.strip():
        return {}
    try:
        value = json.loads(raw)
    except ValueError as error:
        raise RuntimeError("WORKBENCH_OLLAMA_HEADERS must be a JSON object of header names to string values") from error
    if not isinstance(value, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in value.items()):
        raise RuntimeError("WORKBENCH_OLLAMA_HEADERS must be a JSON object of header names to string values")
    return value


class Settings(BaseModel):
    data_dir: Path = Path(os.environ.get("WORKBENCH_DATA_DIR", BACKEND_DIR / "data"))
    database_url: str = os.environ.get("WORKBENCH_DATABASE_URL", "")
    provider: str = os.environ.get("WORKBENCH_PROVIDER", "ollama")
    model: str = os.environ.get("WORKBENCH_MODEL", "qwen3:8b")
    ollama_url: str = os.environ.get("WORKBENCH_OLLAMA_URL", "http://localhost:11434")
    # Credentials for a model endpoint behind an authenticating proxy; never printed (repr) or logged.
    ollama_headers: dict[str, str] = Field(default_factory=lambda: json_headers(os.environ.get("WORKBENCH_OLLAMA_HEADERS", "")), repr=False)
    # The model build the deployment names (an Ollama digest prefix, e.g. 500a1f067a9f for qwen3:8b Q4_K_M). Set, every
    # answer is preceded by a check that the endpoint's tag is that build; a run against another build fails with the reason.
    model_digest: str = os.environ.get("WORKBENCH_MODEL_DIGEST", "").strip().lower()
    # Where a model on another machine runs, in words a reader can weigh ("a Modal GPU in the US"); shown wherever the
    # interface says where a contract's text goes. Empty for a model on the server itself.
    model_host: str = os.environ.get("WORKBENCH_MODEL_HOST", "").strip()
    # A ceiling on the readers' new runs per UTC day, all workspaces together: the model's spend has a bound that one
    # reader cannot exhaust for everyone (application.start_run). 0 is no ceiling. Curated runs (scripts) are not counted.
    max_runs_per_day: int = int(os.environ.get("WORKBENCH_MAX_RUNS_PER_DAY", "0") or "0")
    # Whether /api/health asks the model endpoint. Off where the endpoint bills by the second and starts cold: every
    # answer still checks the model first (providers.ollama._check_build), and health reports the store and the gate.
    health_probes_model: bool = os.environ.get("WORKBENCH_HEALTH_PROBES_MODEL", "1").strip().lower() not in ("0", "false", "no")
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
    # The gate (api/access.py). With a secret, every route but health and the gate itself needs a session that an
    # invite signed under this secret was exchanged for; without one the gate is off, as on a laptop and in the tests.
    # The deployment reads it from a file outside the repository (deploy/supervise.ps1); it is never a default.
    access_secret: str = os.environ.get("WORKBENCH_ACCESS_SECRET", "").strip()
    access_session_days: int = int(os.environ.get("WORKBENCH_ACCESS_SESSION_DAYS", "7"))
    # Set in a deployment that must never run open: the application refuses to start if the secret is missing.
    access_required: bool = os.environ.get("WORKBENCH_ACCESS_REQUIRED", "").lower() in ("1", "true", "yes")
    # Readers whose invites and sessions no longer open anything, by the name their invite was made for.
    access_revoked: list[str] = [s.strip() for s in os.environ.get("WORKBENCH_ACCESS_REVOKED", "").split(",") if s.strip()]
    # Optional: the results.json of the ivo-experiments repository, for the Runs surface, and the
    # published page it was built for (links become "Open experiment" → <url>#<id>).
    experiments_results: Path | None = Path(os.environ["WORKBENCH_EXPERIMENTS_RESULTS"]) if os.environ.get("WORKBENCH_EXPERIMENTS_RESULTS") else None
    experiments_url: str | None = os.environ.get("WORKBENCH_EXPERIMENTS_URL") or None
    # Optional: the contract-state.json the contract-state experiment exports (a recording of measured arrivals), for
    # the Runs surface. Read as a file; nothing of the experiment's code runs here.
    contract_state: Path | None = Path(os.environ["WORKBENCH_CONTRACT_STATE"]) if os.environ.get("WORKBENCH_CONTRACT_STATE") else None

    @property
    def sqlite_url(self) -> str:
        if self.database_url:
            return self.database_url
        self.data_dir.mkdir(parents=True, exist_ok=True)
        return f"sqlite:///{(self.data_dir / 'workbench.db').as_posix()}"


settings = Settings()
