"""Control flow: ``if``, ``switch``, ``while``, ``do-while``, ``fan-out``, ``fan-in``."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

from compose.core.models import StepExec
from compose.runner.context import Scope
from compose.runner.errors import StepFailed
from compose.runner.steps.base import Outcome
from compose.workflows import expressions
from compose.workflows.schema import (
    DoWhileStep,
    FanInStep,
    FanOutStep,
    IfStep,
    SwitchStep,
    WhileStep,
)

if TYPE_CHECKING:
    from compose.runner.runner import RunContext


async def execute_if(rc: RunContext, step: IfStep, row: StepExec, scope: Scope) -> Outcome:
    child = scope.child(parent_exec_id=row.id)
    if rc.condition(step.condition, scope):
        await rc.run_steps(step.then, child)
        return Outcome.ok(branch="then")
    if step.else_:
        await rc.run_steps(step.else_, child)
        return Outcome.ok(branch="else")
    return Outcome.ok(branch=None)


async def execute_switch(rc: RunContext, step: SwitchStep, row: StepExec, scope: Scope) -> Outcome:
    value = expressions.to_text(rc.render(step.expression, scope))
    child = scope.child(parent_exec_id=row.id)
    if value in step.cases:
        await rc.run_steps(step.cases[value], child)
        return Outcome.ok(case=value, value=value)
    if step.default:
        await rc.run_steps(step.default, child)
        return Outcome.ok(case="default", value=value)
    return Outcome.ok(case=None, value=value)


async def execute_loop(
    rc: RunContext, step: WhileStep | DoWhileStep, row: StepExec, scope: Scope
) -> Outcome:
    check_first = not isinstance(step, DoWhileStep)
    iterations = 0
    while True:
        if check_first and not rc.condition(step.condition, scope):
            return Outcome.ok(iterations=iterations, exhausted=False)
        if iterations >= step.max_iterations:
            return Outcome.ok(iterations=iterations, exhausted=True)
        iterations += 1
        child = scope.child(
            parent_exec_id=row.id,
            prefix=f"{scope.prefix}{step.id}#{iterations}/",
            iteration=iterations,
        )
        await rc.run_steps(step.steps, child)
        if not check_first and not rc.condition(step.condition, scope):
            return Outcome.ok(iterations=iterations, exhausted=False)
        if not check_first and iterations >= step.max_iterations:
            return Outcome.ok(iterations=iterations, exhausted=True)


async def execute_fan_out(rc: RunContext, step: FanOutStep, row: StepExec, scope: Scope) -> Outcome:
    items = rc.render(step.items, scope)
    if not isinstance(items, list):
        return Outcome.failed(f"items must evaluate to a list, got {type(items).__name__}")
    semaphore = asyncio.Semaphore(step.max_concurrency)

    async def one(index: int, item: Any) -> dict[str, Any]:
        async with semaphore:
            child = scope.child(
                parent_exec_id=row.id,
                prefix=f"{scope.prefix}{step.id}[{index}]/",
                extras={"item": item},
                iteration=index,
                shared_worktree=True,
            )
            return await rc.run_step(step.step, child)

    outcomes = await asyncio.gather(
        *(one(i, item) for i, item in enumerate(items)), return_exceptions=True
    )
    for result in outcomes:
        if isinstance(result, BaseException):
            raise result
    results = [r["output"] for r in outcomes if isinstance(r, dict)]
    rc.fan_results[step.id] = results
    failed = [r for r in outcomes if isinstance(r, dict) and r["status"] == "failed"]
    if failed and not step.step.continue_on_error:  # pragma: no cover - run_step raises
        raise StepFailed(step.id, f"{len(failed)} item(s) failed")
    return Outcome.ok(results=results, count=len(results))


async def execute_fan_in(rc: RunContext, step: FanInStep, row: StepExec, scope: Scope) -> Outcome:
    fan_in: dict[str, Any] = {}
    combined: list[Any] = []
    for target in step.wait_for:
        results = rc.fan_results.get(target)
        if results is None:
            prior = rc.results.get(target, {}).get("output", {})
            results = list(prior.get("results", []))
        fan_in[target] = results
        combined.extend(results)
    fan_in["results"] = combined
    inner = Scope(scope.prefix, {**scope.extras, "fan_in": fan_in}, scope.parent_exec_id)
    output = {key: rc.render(text, inner) for key, text in step.output.items()}
    return Outcome.ok(**output)
