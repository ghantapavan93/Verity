"""The reference model on a serverless GPU: Ollama 0.40.3 serving qwen3:8b (digest 500a1f067a9f, Q4_K_M), the version
and build the workstation runs, behind Modal's proxy authentication. NOT VERIFIED: checked against Modal's documented
API and SDK 1.6.1 (2026-10-12); it has not been deployed, because an account's spend is the owner's to approve
(CLOUD-READINESS.md). The same weights on another GPU can still decode differently: the acceptance gate S0 in
CLOUD-READINESS.md measures that before anyone is told the cloud answers like the workstation.

    modal deploy deploy/cloud/modal_ollama.py      # prints the endpoint URL for WORKBENCH_OLLAMA_URL

Spend is bounded three ways: one container at most, released a minute after the last request, and the workspace budget
set in Modal's dashboard (a hard cap). Requests need a proxy-auth token (Modal-Key, Modal-Secret headers), which the API
sends from WORKBENCH_OLLAMA_HEADERS. Decoding (temperature 0, seed 42, a 16,384-token window, no thinking, the JSON
schema) is sent by the API with every request, as it is to the workstation's Ollama.

Modal answers a request still running after 150 s with a 303 to a URL that waits for the result, and a request after
scale-to-zero waits for a container to start; the API follows the redirect and gives its build check the answer's own
timeout (app/providers/ollama.py).
"""

from __future__ import annotations

import subprocess

import modal

OLLAMA_IMAGE = "ollama/ollama:0.40.3@sha256:adca95a12c2b386a8f9a995e7fa0600e187e3323b5e5522f5a6c3b1ec73eff99"
MODEL = "qwen3:8b"
DIGEST = "500a1f067a9f"  # the Ollama library's qwen3:8b Q4_K_M; the API checks it again before every answer
PORT = 11434

image = (
    # Ollama's own image of the workstation's version, pinned by digest: no install script fetched at build time.
    modal.Image.from_registry(OLLAMA_IMAGE, add_python="3.12")
    .entrypoint([])  # the image's entrypoint is `ollama`; Modal starts the function below instead
    .env(
        {
            "OLLAMA_HOST": f"0.0.0.0:{PORT}",
            "OLLAMA_MODELS": "/models",
            "OLLAMA_KEEP_ALIVE": "-1",
            # One answer at a time, as the workstation's 6 GB GPU runs it: the API sends one model call at a time
            # (WORKBENCH_MODEL_CONCURRENCY=1), and a fixed batch of one removes one source of decoding drift.
            "OLLAMA_NUM_PARALLEL": "1",
        }
    )
    # The weights are baked into the image, so a cold start loads them from the image, never pulls them, and the
    # build stops if the tag does not name the pinned build.
    .run_commands(
        f"ollama serve > /tmp/ollama-build.log 2>&1 & sleep 10 && ollama pull {MODEL} && ollama list | grep -q '{DIGEST}' "
        f"|| (echo '{MODEL} is not the pinned build {DIGEST}' >&2 && exit 1)"
    )
)

app = modal.App("verity-ollama", image=image)


# One L4 (24 GB) at most, scaled to zero a minute after the last request. `timeout` is per request and equals the API's
# 600 s per model call: once Modal redirects a long call, each hop restarts the client's own timeout, so this is the
# bound that holds. Two cores and 8 GiB hold the server and the 5.2 GB of weights it maps.
@app.function(gpu="L4", cpu=2.0, memory=8192, max_containers=1, scaledown_window=60, timeout=600)
@modal.concurrent(max_inputs=8)  # the build check before an answer is not queued behind a long answer
@modal.web_server(port=PORT, startup_timeout=180, requires_proxy_auth=True)
def ollama() -> None:
    subprocess.Popen(["ollama", "serve"])
