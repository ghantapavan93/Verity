"""The reference model on a serverless GPU: Ollama 0.40.1 serving qwen3:8b (digest 500a1f067a9f, Q4_K_M), the build the
workstation runs, behind Modal's proxy authentication. NOT VERIFIED: written against Modal's documented API; it has not
been deployed, because an account and its spend are the owner's to create (README.md, model endpoint).

    modal deploy deploy/cloud/modal_ollama.py      # prints the endpoint URL for WORKBENCH_OLLAMA_URL

Spend is bounded three ways: one container at most, released a minute after the last request, and the workspace budget
set in Modal's dashboard (a hard cap). Requests need a proxy-auth token (Modal-Key, Modal-Secret headers), which the API
sends from WORKBENCH_OLLAMA_HEADERS.
"""

from __future__ import annotations

import subprocess

import modal

OLLAMA_VERSION = "0.40.1"
MODEL = "qwen3:8b"
DIGEST = "500a1f067a9f"  # the Ollama library's qwen3:8b Q4_K_M; the API checks it again before every answer
PORT = 11434

image = (
    modal.Image.debian_slim(python_version="3.12")
    .apt_install("curl", "ca-certificates", "zstd")
    .run_commands(f"curl -fsSL https://ollama.com/install.sh | OLLAMA_VERSION={OLLAMA_VERSION} sh")
    .env({"OLLAMA_HOST": f"0.0.0.0:{PORT}", "OLLAMA_MODELS": "/models", "OLLAMA_KEEP_ALIVE": "-1"})
    # The weights are baked into the image, so a cold start loads them from local disk, and the build stops if the tag
    # does not name the pinned build.
    .run_commands(
        f"ollama serve > /tmp/ollama-build.log 2>&1 & sleep 10 && ollama pull {MODEL} && ollama list | grep -q '{DIGEST}' "
        f"|| (echo '{MODEL} is not the pinned build {DIGEST}' >&2 && exit 1)"
    )
)

app = modal.App("verity-ollama", image=image)


@app.function(gpu="L4", max_containers=1, scaledown_window=60, timeout=900)
@modal.concurrent(max_inputs=8)  # a health check is not queued behind a long answer
@modal.web_server(port=PORT, startup_timeout=180, requires_proxy_auth=True)
def ollama() -> None:
    subprocess.Popen(["ollama", "serve"])
