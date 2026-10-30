"""Runtime settings. Everything has a default that works on a laptop with Ollama running."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from urllib.parse import urlsplit

from pydantic import BaseModel, Field, model_validator

BACKEND_DIR = Path(__file__).resolve().parents[1]
# A compose service name, as WORKBENCH_MODEL_ON_SERVER admits one (Settings._one_place_for_the_model).
SERVICE_NAME = re.compile(r"[a-z][a-z0-9_-]{0,62}")
# Ollama's own default bind, as an address: "localhost" can resolve to ::1 first, and where the server listens on IPv4
# only every request waits for the IPv6 attempt to fail (about two seconds on Windows, measured 2026-10-11).
DEFAULT_OLLAMA_URL = "http://127.0.0.1:11434"


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
    ollama_url: str = os.environ.get("WORKBENCH_OLLAMA_URL", DEFAULT_OLLAMA_URL)
    # Credentials for a model endpoint behind an authenticating proxy; never printed (repr) or logged.
    ollama_headers: dict[str, str] = Field(default_factory=lambda: json_headers(os.environ.get("WORKBENCH_OLLAMA_HEADERS", "")), repr=False)
    # The model build the deployment names (an Ollama digest prefix, e.g. 500a1f067a9f for qwen3:8b Q4_K_M). Set, every
    # answer is preceded by a check that the endpoint's tag is that build; a run against another build fails with the reason.
    model_digest: str = os.environ.get("WORKBENCH_MODEL_DIGEST", "").strip().lower()
    # Where a model on another machine runs, in words a reader can weigh ("a GPU service in the US"); shown wherever the
    # interface says where a contract's text goes. Empty for a model on the server itself.
    model_host: str = os.environ.get("WORKBENCH_MODEL_HOST", "").strip()
    # Set where the model endpoint is another container on this same machine (deploy/cloud: http://ollama:11434), an
    # address that is not this process's loopback: the interface then says a contract's text stays on this server, and
    # never that a hosted model sleeps. Unset, any address but loopback counts as elsewhere, the safe reading for a claim
    # about where a contract's words go.
    model_on_server: bool = os.environ.get("WORKBENCH_MODEL_ON_SERVER", "").strip().lower() in ("1", "true", "yes")
    # A ceiling on the readers' new runs per UTC day, all workspaces together: the model's daily spend has a bound. It is
    # shared, so one reader can still reach it; the per-reader bound is 20 starts in 10 minutes (api/access.py). 0 is no
    # ceiling. Curated runs (scripts) are not counted (application.start_run).
    max_runs_per_day: int = int(os.environ.get("WORKBENCH_MAX_RUNS_PER_DAY", "0") or "0")
    # Whether /api/health asks the model endpoint. Off where the endpoint bills by the second and starts cold: every
    # answer still checks the model first (providers.ollama._check_build), and health reports the store and the gate.
    health_probes_model: bool = os.environ.get("WORKBENCH_HEALTH_PROBES_MODEL", "1").strip().lower() not in ("0", "false", "no")
    # Whether adding a contract or starting a question wakes the model ahead of it (application/wake_model.py): for an endpoint that
    # sleeps when idle and takes minutes to wake (Modal, measured 2026-10-13: 168 s to the first token). Off where the
    # model runs on the server itself and never sleeps.
    model_wakeup: bool = os.environ.get("WORKBENCH_MODEL_WAKEUP", "").strip().lower() in ("1", "true", "yes")
    # Wake-ups per UTC day, all readers together: each one costs a cold start and the endpoint's idle minutes, whether or
    # not a question follows.
    model_wakeups_per_day: int = int(os.environ.get("WORKBENCH_MODEL_WAKEUPS_PER_DAY", "10") or "0")
    # Seconds after the model last answered or woke during which it is taken to be awake still. Below the endpoint's own
    # idle window (300 s on the serverless host staged on 2026-10-13), so a model that has gone is never taken for awake.
    model_awake_s: int = int(os.environ.get("WORKBENCH_MODEL_AWAKE_S", "240") or "0")
    # The same decoding settings that produced schema-valid output across 250 calls in A1-lite.
    temperature: float = 0.0
    seed: int = 42
    num_ctx: int = 16384
    model_timeout_s: float = 600.0
    # Model calls in flight per process (providers.admission). One GPU serialises them anyway; the bound makes the queue visible.
    model_concurrency: int = int(os.environ.get("WORKBENCH_MODEL_CONCURRENCY", "1"))
    # Runs one reader may start in ten minutes (api/access.py). Production leaves it at 20. The browser flows raise it for
    # their own API: every flow comes from one address, and at 20 the suite had reached the limit (m9, 2026-10-11).
    run_start_limit: int = int(os.environ.get("WORKBENCH_RUN_START_LIMIT", "20"))
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
    access_secret: str = Field(default=os.environ.get("WORKBENCH_ACCESS_SECRET", "").strip(), repr=False)
    access_session_days: int = int(os.environ.get("WORKBENCH_ACCESS_SESSION_DAYS", "7"))
    # Set in a deployment that must never run open: the application refuses to start if the secret is missing.
    access_required: bool = os.environ.get("WORKBENCH_ACCESS_REQUIRED", "").lower() in ("1", "true", "yes")
    # Readers whose invites and sessions no longer open anything, by the name their invite was made for.
    access_revoked: list[str] = [s.strip() for s in os.environ.get("WORKBENCH_ACCESS_REVOKED", "").split(",") if s.strip()]
    # Public use without an invite (api/access.py visit): a browser with no session is handed one of its own, an
    # unpredictable subject in a workspace no one else can read. The gate stays required; anonymous never means shared.
    anonymous_sessions: bool = os.environ.get("WORKBENCH_ANONYMOUS_SESSIONS", "").lower() in ("1", "true", "yes")
    # A visitor's session and workspace last this long; then the workspace and what it holds are deleted
    # (application/retention.py).
    anonymous_retention_days: int = int(os.environ.get("WORKBENCH_ANONYMOUS_RETENTION_DAYS", "7"))
    # Bounds on what one anonymous workspace may hold and start, and on everyone together; each refusal is a 429 that
    # says which bound and when it lifts. Per-address bounds are in api/access.py.
    anonymous_max_documents: int = int(os.environ.get("WORKBENCH_ANONYMOUS_MAX_DOCUMENTS", "10"))
    anonymous_max_runs_per_day: int = int(os.environ.get("WORKBENCH_ANONYMOUS_MAX_RUNS_PER_DAY", "30"))
    # Questions one anonymous workspace may have being answered at once: the model's queue is shared (quotas.run_quotas).
    anonymous_max_runs_in_flight: int = int(os.environ.get("WORKBENCH_ANONYMOUS_MAX_RUNS_IN_FLIGHT", "2"))
    # Questions every anonymous workspace together may have being answered at once: the model's queue, bounded. At about
    # half a minute an answer, eight is a wait of four minutes; the ninth visitor is told at once rather than queued.
    public_max_runs_in_flight: int = int(os.environ.get("WORKBENCH_PUBLIC_MAX_RUNS_IN_FLIGHT", "8"))
    anonymous_max_uploads_per_day: int = int(os.environ.get("WORKBENCH_ANONYMOUS_MAX_UPLOADS_PER_DAY", "300"))
    # Bytes of new contracts the public store takes in a UTC day, every visitor together (application/quotas.py): by count
    # alone, 300 uploads of 25 MB could bring the store to its 2 GiB floor in days. 1 GiB is a thousand ordinary contracts
    # and forty of the largest; a document already held costs none. 0 is no bound.
    anonymous_max_upload_bytes_per_day: int = int(os.environ.get("WORKBENCH_ANONYMOUS_MAX_UPLOAD_BYTES_PER_DAY", str(1024**3)))
    # Requests one network may have in flight at once in the public store (api/in_flight.py): a fifth of the forty request
    # threads, so no one network holds them. A page's own burst at load is a handful, and one past the bound waits two
    # seconds for a turn before it is refused.
    public_requests_per_network: int = int(os.environ.get("WORKBENCH_PUBLIC_REQUESTS_PER_NETWORK", "8"))
    # Live event streams open at once, per workspace and per network (api/in_flight.py): a workspace has at most two
    # questions being answered, so four covers two tabs. A stream refused is followed by polling the run instead.
    public_streams_per_workspace: int = int(os.environ.get("WORKBENCH_PUBLIC_STREAMS_PER_WORKSPACE", "4"))
    public_streams_per_network: int = int(os.environ.get("WORKBENCH_PUBLIC_STREAMS_PER_NETWORK", "16"))
    # Free space the public store keeps: below it new uploads and writes are paused, reading still works (2 GiB).
    public_min_free_bytes: int = int(os.environ.get("WORKBENCH_PUBLIC_MIN_FREE_BYTES", str(2 * 1024**3)))
    # Where the API writes its log (app/log_sink.py): segments in this folder, the oldest deleted past log_keep_bytes in
    # all. Unset, the log goes to standard error (tests, a laptop, a container whose log driver bounds it). The supervisor
    # sets it (deploy/supervise.ps1): its redirect of standard error to one file per start had no bound at all.
    log_dir: Path | None = Path(os.environ["WORKBENCH_LOG_DIR"]) if os.environ.get("WORKBENCH_LOG_DIR") else None
    log_segment_bytes: int = int(os.environ.get("WORKBENCH_LOG_SEGMENT_BYTES", str(10 * 1024**2)))
    log_keep_bytes: int = int(os.environ.get("WORKBENCH_LOG_KEEP_BYTES", str(200 * 1024**2)))
    # Optional: the results.json of the ivo-experiments repository, for the Runs surface, and the
    # published page it was built for (links become "Open experiment" → <url>#<id>).
    experiments_results: Path | None = Path(os.environ["WORKBENCH_EXPERIMENTS_RESULTS"]) if os.environ.get("WORKBENCH_EXPERIMENTS_RESULTS") else None
    experiments_url: str | None = os.environ.get("WORKBENCH_EXPERIMENTS_URL") or None
    # Optional: the contract-state.json the contract-state experiment exports (a recording of measured arrivals), for
    # the Runs surface. Read as a file; nothing of the experiment's code runs here.
    contract_state: Path | None = Path(os.environ["WORKBENCH_CONTRACT_STATE"]) if os.environ.get("WORKBENCH_CONTRACT_STATE") else None

    @model_validator(mode="after")
    def _one_place_for_the_model(self) -> Settings:
        if self.model_on_server and self.model_host:
            raise ValueError("WORKBENCH_MODEL_ON_SERVER and WORKBENCH_MODEL_HOST name two places for the model; set one")
        # "On this server" means loopback, or another container here reached by its service name: one ASCII name that
        # starts with a letter (SERVICE_NAME). Anything else, a domain, an IP in any spelling (dotted, IPv6, decimal, hex),
        # a name with non-ASCII letters or host.docker.internal, may be a machine elsewhere, and the interface would say
        # otherwise. A bare name that is a machine on the network passes: the flag is the deployment's word for that.
        host = (urlsplit(self.ollama_url).hostname or "").lower()
        local = host in ("localhost", "127.0.0.1", "::1") or SERVICE_NAME.fullmatch(host) is not None
        if self.model_on_server and not local:
            raise ValueError(
                f"WORKBENCH_MODEL_ON_SERVER is for a container on this machine, reached by its service name; {host or 'no host'} is an address elsewhere"
            )
        return self

    @property
    def sqlite_url(self) -> str:
        if self.database_url:
            return self.database_url
        self.data_dir.mkdir(parents=True, exist_ok=True)
        return f"sqlite:///{(self.data_dir / 'workbench.db').as_posix()}"


settings = Settings()
