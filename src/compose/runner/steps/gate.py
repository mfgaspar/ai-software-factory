"""``gate`` steps: a human decision."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from compose.core.models import ExecStatus, StepExec
from compose.runner.context import Scope
from compose.runner.errors import RunPaused
from compose.runner.steps.base import Outcome
from compose.workflows.schema import REJECT, GateStep

if TYPE_CHECKING:
    from compose.runner.runner import RunContext


def _approving(options: list[str]) -> str | None:
    """The option that says yes: ``approve``, else the first one that isn't ``reject``
    (``install``). None when the gate has no reject option to tell yes from no."""
    if "approve" in options:
        return "approve"
    if REJECT in options:
        return next((o for o in options if o != REJECT), None)
    return None


async def execute(rc: RunContext, step: GateStep, row: StepExec, scope: Scope) -> Outcome:
    key = scope.key(step.id)
    message = rc.render_text(step.message, scope)
    choice = rc.state.gate_choices.pop(key, None)
    if choice is None and step.verdict_input:
        value = rc.run.inputs.get(step.verdict_input)
        if value not in (None, ""):
            choice = str(value)
    interaction = rc.runner.interaction
    if choice is None and interaction.auto_approve:
        choice = _approving(step.options)
        if choice is not None and interaction.on_auto_approve is not None:
            interaction.on_auto_approve(message, choice)
    ask = interaction.ask_gate
    if choice is None and interaction.interactive and ask is not None:
        while choice not in step.options:
            choice = await asyncio.to_thread(ask, message, list(step.options))
    if choice is None:
        rc.emit(
            "gate_waiting", exec_id=row.id, step_id=step.id, message=message, options=step.options
        )
        raise RunPaused(step.id, f"waiting for a decision on gate {step.id!r}: {message}")
    if choice not in step.options:
        rc.clear_input(step.verdict_input)
        allowed = ", ".join(step.options)
        raise RunPaused(step.id, f"invalid choice {choice!r} for gate {step.id!r} (use {allowed})")

    rc.emit("gate_decided", exec_id=row.id, step_id=step.id, choice=choice)
    if choice == REJECT:
        if step.on_reject == "abort":
            return Outcome(
                ExecStatus.COMPLETED, {"choice": choice}, abort_run=f"gate {step.id!r} rejected"
            )
        if step.on_reject == "retry":
            rc.clear_input(step.verdict_input)
            raise RunPaused(step.id, f"gate {step.id!r} rejected; waiting for a new decision")
    return Outcome.ok(choice=choice)
