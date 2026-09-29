"""Run SkillOpt over the workbench's answer prompt, with both roles on the local Ollama.

    data/skillopt/venv/Scripts/python experiments/skillopt/run.py                       # the pre-registered run
    data/skillopt/venv/Scripts/python experiments/skillopt/run.py --set train.num_epochs=1 --set train.train_size=2 --set evaluation.sel_env_num=2

Nothing in the SkillOpt checkout is modified: the environment is registered from here, the analyst
prompts are read from this directory, and the optimizer's calls get `reasoning_effort: "none"`, which
is how Ollama's OpenAI-compatible endpoint switches Qwen's thinking off (SkillOpt's backend drops that
field). The target role never goes through SkillOpt's backend at all: rollout.py calls the workbench's
own Ollama provider, so the answers are produced exactly as in production.
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
BACKEND = HERE.parents[1]
SKILLOPT = BACKEND / "data" / "skillopt" / "SkillOpt"
DATA = BACKEND / "data" / "skillopt" / "data"
RUNS = BACKEND / "data" / "skillopt" / "runs"
SEED_SKILL = BACKEND / "app" / "analysis" / "prompts" / "answer-v2.md"
OLLAMA_V1 = os.environ.get("WORKBENCH_OLLAMA_URL", "http://127.0.0.1:11434").rstrip("/") + "/v1"


def configure_backends(model: str) -> None:
    for role in ("OPTIMIZER", "TARGET"):
        os.environ.setdefault(f"{role}_BACKEND", "openai_compatible")
        os.environ.setdefault(f"{role}_OPENAI_COMPATIBLE_BASE_URL", OLLAMA_V1)
        os.environ.setdefault(f"{role}_OPENAI_COMPATIBLE_API_KEY", "ollama")
        os.environ.setdefault(f"{role}_OPENAI_COMPATIBLE_MODEL", model)
        os.environ.setdefault(f"{role}_OPENAI_COMPATIBLE_MAX_TOKENS", "12000")
    os.environ.setdefault("OPTIMIZER_OPENAI_COMPATIBLE_TEMPERATURE", "0.7")


def switch_thinking_off_for_the_optimizer() -> None:
    """Every chat completion the OpenAI client sends in this process carries reasoning_effort "none"."""
    from openai.resources.chat import completions as chat_completions

    original = chat_completions.Completions.create

    def create(self: object, *args: object, **kwargs: object) -> object:
        extra = dict(kwargs.get("extra_body") or {})  # type: ignore[call-overload]
        extra.setdefault("reasoning_effort", "none")
        kwargs["extra_body"] = extra
        return original(self, *args, **kwargs)

    chat_completions.Completions.create = create  # type: ignore[method-assign]


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--set", action="append", default=[], metavar="SECTION.KEY=VALUE", help="config override, repeatable")
    parser.add_argument("--model", default="qwen3:8b", help="Ollama model for both roles")
    parser.add_argument("--label", default="", help="suffix for the run directory")
    args = parser.parse_args(argv)

    configure_backends(args.model)
    for path in (SKILLOPT / "scripts", SKILLOPT, BACKEND, HERE):
        sys.path.insert(0, str(path))
    switch_thinking_off_for_the_optimizer()

    import train  # SkillOpt's scripts/train.py
    from workbench_env.adapter import WorkbenchAdapter

    train._ENV_REGISTRY["workbench"] = WorkbenchAdapter  # the registry is the documented extension point

    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    out_root = RUNS / (f"{stamp}-{args.label}" if args.label else stamp)
    overrides = [
        f"env.skill_init={SEED_SKILL.as_posix()}",
        f"env.split_dir={DATA.as_posix()}",
        f"env.out_root={out_root.as_posix()}",
        f"model.optimizer={args.model}",
        f"model.target={args.model}",
        *args.set,
    ]
    sys.argv = ["train.py", "--config", str(HERE / "config.yaml"), "--cfg-options", *overrides]
    print(f"SkillOpt run -> {out_root}")
    train.main()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
