"""What does the local model server do when the prompt is larger than the context window it was given?

Two direct calls to Ollama with the product's own options (num_ctx 16384, temperature 0, seed 42): one prompt that
fits, one that cannot. A fact is planted at the START of the oversized prompt and the question asks for it; if the
server drops the beginning to make room, the model cannot answer and nothing in the response says why."""

from __future__ import annotations

import json
import sys
import time

import httpx

URL = "http://localhost:11434/api/chat"
OPTIONS = {"temperature": 0.0, "seed": 42, "num_ctx": 16384}
SCHEMA = {"type": "object", "properties": {"notice_days": {"type": ["integer", "null"]}, "found": {"type": "boolean"}}, "required": ["notice_days", "found"]}
FACT = "[sec_1] 1 Termination\nEither party may terminate this Agreement upon forty-seven (47) days' written notice.\n\n"
FILLER = (
    "[sec_{n}] {n} General\nThe parties shall cooperate in good faith and perform their obligations under this Agreement in accordance with applicable law. "
)


def ask(sections: int) -> dict:
    body = FACT + "".join(FILLER.format(n=i) * 6 + "\n\n" for i in range(2, sections + 2))
    user = f"QUESTION: How many days' written notice does termination require? Answer from the sections only.\n\nSECTIONS:\n\n{body}"
    payload = {
        "model": "qwen3:8b",
        "messages": [
            {"role": "system", "content": "Answer ONLY from the supplied sections. If the answer is not in them, set found to false."},
            {"role": "user", "content": user},
        ],
        "format": SCHEMA,
        "stream": False,
        "think": False,
        "options": OPTIONS,
    }
    started = time.perf_counter()
    response = httpx.post(URL, json=payload, timeout=600).json()
    return {
        "chars_sent": len(user),
        "prompt_eval_count": response.get("prompt_eval_count"),
        "eval_count": response.get("eval_count"),
        "answer": response.get("message", {}).get("content", "")[:120],
        "seconds": round(time.perf_counter() - started, 1),
        "other_keys": sorted(k for k in response if k not in ("message", "model", "created_at")),
    }


for label, n in (("fits", 20), ("cannot fit", int(sys.argv[1]) if len(sys.argv) > 1 else 110)):
    print(label, json.dumps(ask(n)))
