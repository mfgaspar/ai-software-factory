"""``command`` and ``prompt`` steps: run the engine and record what it does."""

from __future__ import annotations

from typing import TYPE_CHECKING

from compose.core.models import StepExec
from compose.engines.base import EngineOptions, EngineTask, Usage, UsageEvent
from compose.runner.context import Scope
from compose.runner.errors import LimitExceeded
from compose.runner.steps.base import Outcome
from compose.workflows.schema import CommandStep, PromptStep

if TYPE_CHECKING:
    from compose.runner.runner import RunContext


async def execute(
    rc: RunContext, step: CommandStep | PromptStep, row: StepExec, scope: Scope
) -> Outcome:
    if isinstance(step, CommandStep):
        args = rc.render_text(step.input.args, scope) if step.input.args else None
        task = EngineTask.skill(step.command, args)
    else:
        task = EngineTask.prompt(rc.render_text(step.prompt, scope))
    settings = rc.engine_settings(step)
    engine = rc.runner.engines.get(settings.engine)
    options = EngineOptions(
        model=settings.model,
        reasoning_effort=settings.reasoning_effort,
        max_turns=step.limits.max_turns,
        engine_options=settings.engine_options,
        env=rc.env(),
    )
    row.engine = settings.engine
    row.model = settings.model
    rc.emit("engine_started", exec_id=row.id, step_id=step.id, task=task.label)
    run = engine.start(task, rc.worktree, options)
    usage = Usage()
    limit_error: str | None = None
    try:
        async for event in run.events():
            rc.record_engine_event(row.id, None, event)
            if isinstance(event, UsageEvent):
                usage = event.usage
                apply_usage(row, usage)
                rc.check_limits(step.limits, usage)
    except LimitExceeded as exc:
        limit_error = str(exc)
        await run.stop()
    except BaseException:
        await run.stop()
        raise
    result = run.result
    if result.usage.cost_usd >= usage.cost_usd:
        usage = result.usage
    apply_usage(row, usage)
    row.session_id = result.session_id
    row.model = result.model or row.model
    if limit_error:
        return Outcome.failed(limit_error, session_id=result.session_id)
    if result.status == "completed":
        return Outcome.ok(text=result.final_text, session_id=result.session_id)
    return Outcome.failed(result.error or result.status, session_id=result.session_id)


def apply_usage(row: StepExec, usage: Usage) -> None:
    row.input_tokens = usage.input_tokens
    row.output_tokens = usage.output_tokens
    row.cache_read_tokens = usage.cache_read_tokens
    row.cache_write_tokens = usage.cache_write_tokens
    row.cost_usd = usage.cost_usd
    row.turns = usage.turns
