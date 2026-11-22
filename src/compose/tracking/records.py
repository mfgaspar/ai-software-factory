"""The built-in tracking hooks and the step records they produce.

``compose.track.begin`` snapshots the worktree before a step's other hooks run;
``compose.track.end`` snapshots it again after them and records every file the step and
its hooks changed. Each workflow hook is also measured on its own, so a step's record can
show which hook changed what. Inside a fan-out the items share the worktree, so their
changes are recorded once, on the fan-out.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any, TypeVar

from compose.core import store
from compose.core.db import Database
from compose.core.models import Action, FileChange, HookExec, Metrics, StepExec
from compose.tracking.diff import Change, ChangeSummary, diff_trees
from compose.tracking.snapshot import snapshot

if TYPE_CHECKING:
    from compose.runner.context import Scope
    from compose.runner.runner import RunContext

T = TypeVar("T")


def tracked(rc: RunContext, step_exec: StepExec | None, scope: Scope) -> bool:
    return rc.definition.workflow.tracking and step_exec is not None and not scope.shared_worktree


async def take_snapshot(rc: RunContext) -> str:
    return await asyncio.to_thread(snapshot, rc.worktree)


async def changes_since(rc: RunContext, before: str) -> list[Change]:
    after = await take_snapshot(rc)
    return await asyncio.to_thread(diff_trees, rc.worktree, before, after)


def record_changes(
    db: Database,
    run_id: str,
    step_exec_id: str,
    hook_exec_id: str | None,
    changes: list[Change],
    target: Metrics,
) -> None:
    with db.transaction():
        for change in changes:
            store.insert(
                db,
                FileChange(
                    run_id=run_id,
                    step_exec_id=step_exec_id,
                    hook_exec_id=hook_exec_id,
                    path=change.path,
                    old_path=change.old_path,
                    status=change.status,
                    added=change.added,
                    removed=change.removed,
                ),
            )
    summary = ChangeSummary.of(changes)
    target.files_changed = summary.files
    target.lines_added = summary.added
    target.lines_removed = summary.removed


async def track_begin(rc: RunContext, step_exec: StepExec | None, scope: Scope) -> None:
    if not tracked(rc, step_exec, scope):
        return
    assert step_exec is not None
    rc.state.snapshots[step_exec.id] = await take_snapshot(rc)
    rc.save_state()


async def track_end(rc: RunContext, step_exec: StepExec | None, scope: Scope) -> None:
    if not tracked(rc, step_exec, scope):
        return
    assert step_exec is not None
    before = rc.state.snapshots.get(step_exec.id)
    if before is None:
        return
    changes = await changes_since(rc, before)
    record_changes(rc.db, rc.run.id, step_exec.id, None, changes, step_exec)
    rc.state.snapshots.pop(step_exec.id, None)
    rc.save_state()
    rc.emit(
        "changes_recorded",
        exec_id=step_exec.id,
        files=step_exec.files_changed,
        added=step_exec.lines_added,
        removed=step_exec.lines_removed,
    )


async def measure_hook(
    rc: RunContext,
    step_exec: StepExec | None,
    hook_exec: HookExec,
    scope: Scope,
    work: Callable[[], Awaitable[T]],
) -> T:
    """Run a workflow hook, recording the files it changed on its own row."""
    if not tracked(rc, step_exec, scope):
        return await work()
    assert step_exec is not None
    before = await take_snapshot(rc)
    try:
        return await work()
    finally:
        changes = await changes_since(rc, before)
        record_changes(rc.db, rc.run.id, step_exec.id, hook_exec.id, changes, hook_exec)


# ------------------------------------------------------------------------ records


def _change_json(change: FileChange) -> dict[str, Any]:
    return {
        "path": change.path,
        "old_path": change.old_path,
        "status": change.status.value,
        "added": change.added,
        "removed": change.removed,
    }


def step_record(db: Database, row: StepExec) -> dict[str, Any]:
    """Everything recorded for one step execution: totals, hooks, files, actions."""
    changes = store.select(db, FileChange, "step_exec_id = ?", (row.id,), "id")
    hooks = store.select(db, HookExec, "step_exec_id = ?", (row.id,), "started_at, id")
    actions = store.select(db, Action, "step_exec_id = ?", (row.id,), "seq")
    by_hook: dict[str | None, list[dict[str, Any]]] = {}
    for change in changes:
        by_hook.setdefault(change.hook_exec_id, []).append(_change_json(change))
    return {
        **row.model_dump(mode="json"),
        "changes": by_hook.get(None, []),
        "hooks": [
            {
                **hook.model_dump(mode="json"),
                "changes": by_hook.get(hook.id, []),
                "actions": sum(1 for a in actions if a.hook_exec_id == hook.id),
            }
            for hook in hooks
        ],
        "actions": [a.model_dump(mode="json") for a in actions],
    }
