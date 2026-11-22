"""Workflow hooks: which hooks run around a step or the run, and running them."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from compose.core import store
from compose.core.db import Database, utcnow
from compose.core.ids import new_id
from compose.core.models import ExecStatus, HookExec, HookKind, StepExec
from compose.engines.base import EngineTask
from compose.engines.registry import EngineError
from compose.repos.git import GitError
from compose.runner.context import Scope
from compose.runner.errors import LimitExceeded, RunAborted
from compose.runner.steps.base import Outcome
from compose.runner.steps.engine import run_engine
from compose.runner.steps.shell import run_shell
from compose.tracking import records
from compose.workflows import expressions
from compose.workflows.schema import (
    BUILTIN_TRACKING_HOOKS,
    BuiltinHook,
    HookSpec,
    Limits,
    Workflow,
)

if TYPE_CHECKING:
    from compose.runner.runner import RunContext

Phase = Literal["before", "after"]
BUILTIN_INDEX = -1
SUMMARY_LIMIT = 500


@dataclass(frozen=True)
class ResolvedHook:
    """One hook to run for an event: a workflow hook or a compose built-in."""

    event: str
    index: int
    spec: HookSpec | None = None
    builtin: BuiltinHook | None = None

    @property
    def name(self) -> str:
        if self.builtin is not None:
            return self.builtin.name
        assert self.spec is not None
        return self.spec.label

    @property
    def kind(self) -> HookKind:
        if self.builtin is not None:
            return HookKind.BUILTIN
        assert self.spec is not None
        return HookKind(self.spec.kind)

    @property
    def optional(self) -> bool:
        return self.spec.optional if self.spec is not None else False

    @property
    def key(self) -> tuple[str, int, str]:
        return (self.event, self.index, self.name)


@dataclass(frozen=True)
class StepHooks:
    """The hooks around one step, in execution order.

    ``after`` hooks run only when the step succeeds; ``final`` hooks (tracking's end
    hook) run whenever the step finishes, so its record is written even on failure.
    """

    before: list[ResolvedHook]
    after: list[ResolvedHook]
    final: list[ResolvedHook]

    def __bool__(self) -> bool:
        return bool(self.before or self.after or self.final)


def _declared(definition: Workflow, event: str) -> list[ResolvedHook]:
    hooks = [ResolvedHook(event, i, spec=s) for i, s in enumerate(definition.hooks.get(event, []))]
    # sorted() is stable, so equal priorities keep declaration order
    return sorted(hooks, key=lambda h: h.spec.priority if h.spec else 0)


def _builtins(definition: Workflow, position: Literal["first", "last"]) -> list[ResolvedHook]:
    if not definition.workflow.tracking:
        return []
    return [
        ResolvedHook(b.event, BUILTIN_INDEX, builtin=b)
        for b in BUILTIN_TRACKING_HOOKS
        if b.position == position
    ]


def step_hooks(definition: Workflow, step_id: str, *, workflow_hooks: bool = True) -> StepHooks:
    """Hooks around a step: ``before_step``, ``before_<id>``, the step, ``after_<id>``,
    ``after_step`` — tracking first and last. ``workflow_hooks=False`` gives only the
    built-ins (a fan-out is tracked as a whole but has no hooks of its own)."""
    before = _builtins(definition, "first")
    after: list[ResolvedHook] = []
    if workflow_hooks:
        before += _declared(definition, "before_step") + _declared(definition, f"before_{step_id}")
        after = _declared(definition, f"after_{step_id}") + _declared(definition, "after_step")
    return StepHooks(before=before, after=after, final=_builtins(definition, "last"))


def run_hooks(definition: Workflow, phase: Phase) -> list[ResolvedHook]:
    """Hooks around the whole run (``before_run`` / ``after_run``)."""
    return _declared(definition, f"{phase}_run")


# ----------------------------------------------------------------------- built-ins


@dataclass
class BuiltinCall:
    """What a built-in hook gets: the run, the step execution it surrounds, its own row."""

    rc: RunContext
    step_exec: StepExec | None
    hook_exec: HookExec
    scope: Scope


BuiltinImpl = Callable[[BuiltinCall], Awaitable[None]]


async def _track_begin(call: BuiltinCall) -> None:
    await records.track_begin(call.rc, call.step_exec, call.scope)


async def _track_end(call: BuiltinCall) -> None:
    await records.track_end(call.rc, call.step_exec, call.scope)


BUILTIN_IMPLS: dict[str, BuiltinImpl] = {
    "compose.track.begin": _track_begin,
    "compose.track.end": _track_end,
}


def register_builtin(name: str, impl: BuiltinImpl) -> None:
    BUILTIN_IMPLS[name] = impl


# ----------------------------------------------------------------------- execution


def completed_keys(
    db: Database, run_id: str, step_exec_id: str | None
) -> set[tuple[str, int, str]]:
    """Hooks that already ran to the end for this execution (skipped on resume)."""
    if step_exec_id is None:
        rows = store.select(db, HookExec, "run_id = ? AND step_exec_id IS NULL", (run_id,))
    else:
        rows = store.select(db, HookExec, "step_exec_id = ?", (step_exec_id,))
    final = (ExecStatus.COMPLETED, ExecStatus.SKIPPED)
    return {(r.event, r.hook_index, r.name) for r in rows if r.status in final}


def _summary(data: bytes) -> str:
    text = data.decode(errors="replace")
    return text if len(text) <= SUMMARY_LIMIT else text[:SUMMARY_LIMIT] + "…"


async def _ask(rc: RunContext, question: str) -> bool:
    interaction = rc.runner.interaction
    if not (interaction.interactive and interaction.ask_confirm):
        return True  # non-interactive runs execute the hook
    return await asyncio.to_thread(interaction.ask_confirm, question)


async def _perform(
    rc: RunContext, hook: ResolvedHook, row: HookExec, step_exec: StepExec | None, scope: Scope
) -> Outcome:
    step_exec_id = step_exec.id if step_exec else None
    if hook.builtin is not None:
        await BUILTIN_IMPLS[hook.builtin.name](BuiltinCall(rc, step_exec, row, scope))
        return Outcome.ok()
    spec = hook.spec
    assert spec is not None
    env = {key: rc.render_text(value, scope) for key, value in spec.env.items()}
    if spec.run is not None:
        command = rc.render_text(spec.run, scope)
        rc.record_action(
            step_exec_id, row.id, kind="tool_call", tool_name="shell", input_summary=command
        )
        code, out, err = await run_shell(rc, command, env)
        rc.record_action(
            step_exec_id,
            row.id,
            kind="tool_result",
            tool_name="shell",
            result_summary=f"exit {code}\n{_summary(out + err)}",
            is_error=code != 0,
        )
        return Outcome.ok(exit_code=code) if code == 0 else Outcome.failed(f"exit code {code}")

    if spec.command is not None:
        args = rc.render_text(spec.args, scope) if spec.args else None
        task = EngineTask.skill(spec.command, args)
    else:
        task = EngineTask.prompt(rc.render_text(spec.prompt or "", scope))
    result = await run_engine(
        rc, task, spec, Limits(), row, step_exec_id=step_exec_id, hook_exec_id=row.id, env=env
    )
    if result.ok:
        return Outcome.ok(text=result.final_text)
    return Outcome.failed(result.error or "failed")


async def execute_hook(
    rc: RunContext, hook: ResolvedHook, step_exec: StepExec | None, scope: Scope
) -> HookExec:
    """Run one hook and record it; returns its (closed) row.

    Abort propagates as :class:`RunAborted`; every other problem is the hook's failure.
    """
    row = HookExec(
        id=new_id("hook"),
        run_id=rc.run.id,
        step_exec_id=step_exec.id if step_exec else None,
        event=hook.event,
        hook_index=hook.index,
        kind=hook.kind,
        name=hook.name,
        optional=hook.optional,
        status=ExecStatus.RUNNING,
        started_at=utcnow(),
    )
    spec = hook.spec
    skip_reason: str | None = None
    try:
        if spec is not None and spec.condition and not rc.condition(spec.condition, scope):
            skip_reason = "condition is false"
        elif spec is not None and spec.prompt_text:
            question = rc.render_text(spec.prompt_text, scope)
            if not await _ask(rc, question):
                skip_reason = "declined"
    except expressions.ExpressionError as exc:
        row.error = f"expression error: {exc}"
        row.status = ExecStatus.FAILED
    store.insert(rc.db, row)
    if row.status is ExecStatus.FAILED or skip_reason is not None:
        if skip_reason is not None:
            row.status = ExecStatus.SKIPPED
            row.error = skip_reason
        return _close(rc, row)

    rc.emit(
        "hook_started",
        hook_exec_id=row.id,
        exec_id=row.step_exec_id,
        event=hook.event,
        name=hook.name,
        kind=hook.kind.value,
    )
    timeout = spec.timeout if spec is not None else None
    try:
        if hook.builtin is not None:
            outcome = await rc.guard(_perform(rc, hook, row, step_exec, scope), timeout)
        else:
            outcome = await records.measure_hook(
                rc,
                step_exec,
                row,
                scope,
                lambda: rc.guard(_perform(rc, hook, row, step_exec, scope), timeout),
            )
    except RunAborted as aborted:
        row.status = ExecStatus.ABORTED
        row.error = aborted.reason
        _close(rc, row)
        raise
    except TimeoutError:
        outcome = Outcome.failed(f"timeout after {timeout}s")
    except (EngineError, LimitExceeded, GitError) as exc:
        outcome = Outcome.failed(str(exc))
    except expressions.ExpressionError as exc:
        outcome = Outcome.failed(f"expression error: {exc}")
    row.status = outcome.status
    row.error = outcome.error
    return _close(rc, row)


def _close(rc: RunContext, row: HookExec) -> HookExec:
    row.ended_at = utcnow()
    if row.started_at is not None:
        row.duration_ms = int((row.ended_at - row.started_at).total_seconds() * 1000)
    rc.shared.spent_usd += row.cost_usd
    store.update(rc.db, row)
    rc.emit(
        "hook_finished",
        hook_exec_id=row.id,
        exec_id=row.step_exec_id,
        event=row.event,
        name=row.name,
        status=row.status.value,
        optional=row.optional,
        error=row.error,
        cost_usd=row.cost_usd,
    )
    return row


async def run_group(
    rc: RunContext,
    hooks: list[ResolvedHook],
    step_exec: StepExec | None,
    scope: Scope,
    *,
    skip: set[tuple[str, int, str]] | None = None,
) -> str | None:
    """Run hooks in order; stop at the first required failure and return its message."""
    for hook in hooks:
        if skip and hook.key in skip:
            continue
        row = await execute_hook(rc, hook, step_exec, scope)
        if row.status is ExecStatus.FAILED and not row.optional:
            return f"{hook.event} hook {hook.name!r} failed: {row.error}"
    return None


def fold_hook_metrics(db: Database, row: StepExec) -> None:
    """Add the tokens and cost of a step's hooks to the step's own totals."""
    totals = db.conn.execute(
        """
        SELECT COALESCE(SUM(input_tokens), 0), COALESCE(SUM(output_tokens), 0),
               COALESCE(SUM(cache_read_tokens), 0), COALESCE(SUM(cache_write_tokens), 0),
               COALESCE(SUM(cost_usd), 0)
        FROM hook_execs WHERE step_exec_id = ?
        """,
        (row.id,),
    ).fetchone()
    row.input_tokens += int(totals[0])
    row.output_tokens += int(totals[1])
    row.cache_read_tokens += int(totals[2])
    row.cache_write_tokens += int(totals[3])
    row.cost_usd += float(totals[4])
