"""SkillOpt's view of the workbench: a dataset-backed environment whose rollout is the production
answer path (rollout.py) and whose analyst prompts know the failure types this pipeline has."""

from __future__ import annotations

from pathlib import Path

from skillopt.datasets.base import BatchSpec
from skillopt.envs.base import EnvAdapter

from workbench_env.dataloader import WorkbenchDataLoader
from workbench_env.rollout import run_batch

PROMPTS = Path(__file__).with_name("prompts")


class WorkbenchAdapter(EnvAdapter):
    def __init__(
        self,
        split_dir: str = "",
        data_path: str = "",
        split_mode: str = "split_dir",
        split_ratio: str = "2:1:7",
        split_seed: int = 42,
        split_output_dir: str = "",
        workers: int = 1,
        analyst_workers: int = 1,
        failure_only: bool = False,
        minibatch_size: int = 8,
        edit_budget: int = 3,
        seed: int = 42,
        limit: int = 0,
        max_completion_tokens: int = 4096,
    ) -> None:
        self.workers = workers
        self.analyst_workers = analyst_workers
        self.failure_only = failure_only
        self.minibatch_size = minibatch_size
        self.edit_budget = edit_budget
        self.max_completion_tokens = int(max_completion_tokens)
        self.dataloader = WorkbenchDataLoader(
            split_dir=split_dir,
            data_path=data_path,
            split_mode=split_mode,
            split_ratio=split_ratio,
            split_seed=split_seed,
            split_output_dir=split_output_dir,
            seed=seed,
            limit=limit,
        )

    def setup(self, cfg: dict) -> None:
        super().setup(cfg)
        self.dataloader.setup(cfg)

    def get_dataloader(self) -> WorkbenchDataLoader:
        return self.dataloader

    def build_env_from_batch(self, batch: BatchSpec, **kwargs: object) -> list[dict]:
        return list(batch.payload or [])

    def build_train_env(self, batch_size: int, seed: int, **kwargs: object) -> list[dict]:
        return self.build_env_from_batch(self.dataloader.build_train_batch(batch_size=batch_size, seed=seed, **kwargs), **kwargs)

    def build_eval_env(self, env_num: int, split: str, seed: int, **kwargs: object) -> list[dict]:
        return self.build_env_from_batch(self.dataloader.build_eval_batch(env_num=env_num, split=split, seed=seed, **kwargs), **kwargs)

    def rollout(self, env_manager: list[dict], skill_content: str, out_dir: str, **kwargs: object) -> list[dict]:
        return run_batch(
            items=env_manager, skill_content=skill_content, out_root=out_dir, workers=self.workers, max_completion_tokens=self.max_completion_tokens
        )

    def get_task_types(self) -> list[str]:
        seen: list[str] = []
        for item in self.dataloader.train_items + self.dataloader.val_items + self.dataloader.test_items:
            task_type = str(item.get("task_type") or "clause")
            if task_type not in seen:
                seen.append(task_type)
        return seen or ["clause"]

    # The adapter lives outside skillopt.envs, so the env-specific prompt lookup finds nothing; these
    # two are read from this directory, everything else falls back to SkillOpt's generic prompts.
    def get_error_minibatch_prompt(self) -> str | None:
        return (PROMPTS / "analyst_error.md").read_text(encoding="utf-8")

    def get_success_minibatch_prompt(self) -> str | None:
        return (PROMPTS / "analyst_success.md").read_text(encoding="utf-8")
