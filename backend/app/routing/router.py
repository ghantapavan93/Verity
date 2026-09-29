"""Which model answers which task, by measurement.

A run is one of a few tasks. The router picks a model for the task from a policy built from
golden-set results per model (docs/ROUTING.md). Until a smaller model has been measured on a
task and found to pass the goldens the default passes, the policy is the default model for every
task, and the run record says so in its routing reason. Nothing here guesses at "complexity".
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Literal, get_args

TaskName = Literal["clause_lookup", "guidance_comparison"]
TASKS: tuple[TaskName, ...] = get_args(TaskName)


@dataclass(frozen=True)
class ModelDecision:
    model: str
    reason: str


@dataclass(frozen=True)
class ModelRouter:
    default_model: str
    # task → model. Every entry is justified by a golden-set measurement recorded in docs/ROUTING.md.
    policy: Mapping[str, str] = field(default_factory=dict)

    def select(self, task: TaskName, requested: str | None = None) -> ModelDecision:
        if requested:
            return ModelDecision(requested, "requested explicitly")
        chosen = self.policy.get(task)
        if chosen:
            return ModelDecision(chosen, f"policy for {task}: measured on the golden set (docs/ROUTING.md)")
        return ModelDecision(self.default_model, f"no measured alternative for {task}; the default model")


def task_for(guidance_present: bool) -> TaskName:
    """The task a question is: a lookup in the contract, or a comparison of its position with a policy."""
    return "guidance_comparison" if guidance_present else "clause_lookup"
