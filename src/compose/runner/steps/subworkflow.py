"""``workflow`` steps: run another workflow as a linked child run."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

from compose.core.models import RunStatus, StepExec
from compose.runner.context import Scope
from compose.runner.steps.base import Outcome
from compose.workflows import loader
from compose.workflows.schema import WorkflowCallStep

if TYPE_CHECKING:
    from compose.runner.runner import RunContext

MAX_DEPTH = 16


async def execute(rc: RunContext, step: WorkflowCallStep, row: StepExec, scope: Scope) -> Outcome:
    key = scope.key(step.id)
    ref = str(rc.render(step.workflow, scope))
    child_id = rc.state.children.get(key)
    if child_id is None:
        if len(rc.shared.call_stack) >= MAX_DEPTH:
            return Outcome.failed(f"workflow calls nest deeper than {MAX_DEPTH}")
        try:
            loaded = loader.resolve(ref, Path(rc.repo.path))
        except loader.WorkflowError as exc:
            return Outcome.failed(str(exc))
        if loaded.id in rc.shared.call_stack:
            chain = " -> ".join([*rc.shared.call_stack, loaded.id])
            return Outcome.failed(f"workflow call cycle: {chain}")
        inputs: dict[str, Any] = {
            name: rc.render(value, scope) if isinstance(value, str) else value
            for name, value in step.input.items()
        }
        child = rc.runner.create_child_run(rc, loaded, inputs, parent_exec_id=row.id)
        rc.state.children[key] = child.id
        rc.save_state()
        child_id = child.id
    child_run = await rc.runner.execute_child(rc, child_id)
    if child_run.status is RunStatus.COMPLETED:
        return Outcome.ok(**(child_run.outputs or {}), run_id=child_run.id)
    return Outcome.failed(child_run.error or child_run.status.value, run_id=child_run.id)
