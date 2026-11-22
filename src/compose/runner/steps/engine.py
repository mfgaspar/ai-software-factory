"""``command`` and ``prompt`` steps: run the engine and record what it does."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from compose.core.models import Metrics, StepExec
from compose.engines.base import EngineOptions, EngineTask, Usage, UsageEvent
from compose.runner.context import Scope
from compose.runner.errors import LimitExceeded
from compose.runner.steps.base import Outcome
from compose.workflows.schema import CommandStep, EngineSettings, Limits, PromptStep

if TYPE_CHECKING:
    from compose.runner.runner import RunContext


@dataclass
class EngineOutcome:
    ok: bool
    error: str | None
    final_text: str | None
    session_id: str | None


async def run_engine(
    rc: RunContext,
    task: EngineTask,
    settings_from: EngineSettings,
    limits: Limits,
    record: Metrics,
    *,
    step_exec_id: str | None,
    hook_exec_id: str | None = None,
    env: dict[str, str] | None = None,
    scope: Scope | None = None,
) -> EngineOutcome:
    """Run one engine task, streaming its events into the trace and usage into ``record``."""
    settings = rc.engine_settings(settings_from, scope)
    engine = rc.runner.engines.get(settings.engine)
    budgets = [limits.max_cost_usd]
    run_cap = rc.shared.run_limits.max_cost_usd
    if run_cap is not None:
        budgets.append(max(run_cap - rc.shared.spent_usd, 0.0))
    caps = [b for b in budgets if b is not None]
    options = EngineOptions(
        model=settings.model,
        reasoning_effort=settings.reasoning_effort,
        max_turns=limits.max_turns,
        max_cost_usd=min(caps) if caps else None,
        engine_options=settings.engine_options,
        env={**rc.env(), **(env or {})},
    )
    record.engine = settings.engine
    record.model = settings.model
    rc.emit("engine_started", exec_id=step_exec_id, hook_exec_id=hook_exec_id, task=task.label)
    run = engine.start(task, rc.worktree, options)
    usage = Usage()
    limit_error: str | None = None
    try:
        async for event in run.events():
            rc.record_engine_event(step_exec_id, hook_exec_id, event)
            if isinstance(event, UsageEvent):
                usage = event.usage
                apply_usage(record, usage)
                rc.check_limits(limits, usage)
    except LimitExceeded as exc:
        limit_error = str(exc)
        await run.stop()
    except BaseException:
        await run.stop()
        raise
    result = run.result
    if result.usage.cost_usd >= usage.cost_usd:
        usage = result.usage
    apply_usage(record, usage)
    record.session_id = result.session_id
    record.model = result.model or record.model
    if limit_error:
        return EngineOutcome(False, limit_error, None, result.session_id)
    if result.status == "completed":
        return EngineOutcome(True, None, result.final_text, result.session_id)
    return EngineOutcome(False, result.error or result.status, None, result.session_id)


async def execute(
    rc: RunContext, step: CommandStep | PromptStep, row: StepExec, scope: Scope
) -> Outcome:
    if isinstance(step, CommandStep):
        args = rc.render_text(step.input.args, scope) if step.input.args else None
        task = EngineTask.skill(step.command, args)
    else:
        task = EngineTask.prompt(rc.render_text(step.prompt, scope))
    result = await run_engine(rc, task, step, step.limits, row, step_exec_id=row.id, scope=scope)
    if result.ok:
        return Outcome.ok(text=result.final_text, session_id=result.session_id)
    return Outcome.failed(result.error or "failed", session_id=result.session_id)


def apply_usage(record: Metrics, usage: Usage) -> None:
    record.input_tokens = usage.input_tokens
    record.output_tokens = usage.output_tokens
    record.cache_read_tokens = usage.cache_read_tokens
    record.cache_write_tokens = usage.cache_write_tokens
    record.cost_usd = usage.cost_usd
    record.turns = usage.turns
