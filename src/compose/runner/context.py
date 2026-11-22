"""Expression context and scopes for step execution."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from compose.core.models import ExecStatus, Metrics


@dataclass(frozen=True)
class Scope:
    """Where a step executes: its key prefix (loop iterations, fan-out items), extra
    expression names (``item``, ``fan_in``) and its parent step execution."""

    prefix: str = ""
    extras: dict[str, Any] = field(default_factory=dict)
    parent_exec_id: str | None = None
    iteration: int | None = None
    # inside a fan-out item: the worktree is shared, so changes belong to the fan-out
    shared_worktree: bool = False

    def key(self, step_id: str) -> str:
        return f"{self.prefix}{step_id}"

    def child(
        self,
        *,
        parent_exec_id: str,
        prefix: str | None = None,
        extras: dict[str, Any] | None = None,
        iteration: int | None = None,
        shared_worktree: bool | None = None,
    ) -> Scope:
        return Scope(
            prefix=self.prefix if prefix is None else prefix,
            extras={**self.extras, **(extras or {})},
            parent_exec_id=parent_exec_id,
            iteration=self.iteration if iteration is None else iteration,
            shared_worktree=self.shared_worktree if shared_worktree is None else shared_worktree,
        )


def step_result(
    status: ExecStatus, output: dict[str, Any] | None, metrics: Metrics
) -> dict[str, Any]:
    """What ``steps.<id>`` evaluates to."""
    return {
        "status": status.value,
        "output": output or {},
        "cost_usd": metrics.cost_usd,
        "tokens": {
            "input": metrics.input_tokens,
            "output": metrics.output_tokens,
            "cache_read": metrics.cache_read_tokens,
            "cache_write": metrics.cache_write_tokens,
        },
        "changes": {
            "files": metrics.files_changed,
            "added": metrics.lines_added,
            "removed": metrics.lines_removed,
        },
    }
