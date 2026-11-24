"""Read-only views of runs for the CLI and the API: status, trace, changes and cost.

Every view returns plain JSON-ready data. A run's view covers its child runs
(``type: workflow`` steps) too; each step carries the ``run_id`` it belongs to.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from compose.clarity import questions
from compose.core import store
from compose.core.db import Database
from compose.core.home import Home
from compose.core.models import (
    Feature,
    HookExec,
    Repo,
    Run,
    RunStatus,
    StepExec,
)
from compose.runner.errors import InputError
from compose.runner.state import RunFiles
from compose.tracking import aggregate, journal
from compose.tracking.journal import Action, FileChange


class ViewError(Exception):
    """The run, feature or filter asked for does not exist."""


def get_run(db: Database, run_id: str) -> Run:
    run = store.get(db, Run, run_id)
    if run is None:
        raise ViewError(f"No run {run_id!r} (see `compose status`)")
    return run


def run_tree(db: Database, run_id: str) -> list[str]:
    """The run and all of its child runs, parents first."""
    rows = db.execute(
        """
        WITH RECURSIVE tree(id, depth) AS (
            SELECT id, 0 FROM runs WHERE id = ?
            UNION ALL
            SELECT r.id, t.depth + 1 FROM runs r JOIN tree t ON r.parent_run_id = t.id
        )
        SELECT id FROM tree ORDER BY depth, id
        """,
        (run_id,),
    ).fetchall()
    return [r[0] for r in rows]


def _in(ids: list[str]) -> str:
    return ", ".join("?" for _ in ids)


def step_execs(db: Database, run_id: str, step_id: str | None = None) -> list[StepExec]:
    ids = run_tree(db, run_id)
    where = f"run_id IN ({_in(ids)})"
    params: list[Any] = list(ids)
    if step_id is not None:
        where += " AND step_id = ?"
        params.append(step_id)
    return store.select(db, StepExec, where, tuple(params), "started_at, id")


def _names(db: Database, run: Run) -> tuple[str | None, str | None]:
    repo = store.get(db, Repo, run.repo_id)
    feature = store.get(db, Feature, run.feature_id) if run.feature_id else None
    return (repo.name if repo else None), (feature.name if feature else None)


def _metrics(row: StepExec | HookExec) -> dict[str, Any]:
    return {
        "engine": row.engine,
        "model": row.model,
        "turns": row.turns,
        "cost_usd": row.cost_usd,
        "tokens": {
            "input": row.input_tokens,
            "output": row.output_tokens,
            "cache_read": row.cache_read_tokens,
            "cache_write": row.cache_write_tokens,
        },
        "changes": {
            "files": row.files_changed,
            "added": row.lines_added,
            "removed": row.lines_removed,
        },
    }


def step_summary(row: StepExec) -> dict[str, Any]:
    return {
        "exec_id": row.id,
        "run_id": row.run_id,
        "step_id": row.step_id,
        "type": row.step_type,
        "parent_exec_id": row.parent_exec_id,
        "iteration": row.iteration,
        "attempt": row.attempt,
        "status": row.status.value,
        "started_at": row.started_at,
        "ended_at": row.ended_at,
        "duration_ms": row.duration_ms,
        **_metrics(row),
        "error": row.error,
    }


def _paused_target(home: Home, run: Run) -> tuple[RunFiles, str | None, str] | None:
    """Where a paused run waits: the run files (its own or a child's), the step key, the
    owning run id."""
    if run.status is not RunStatus.PAUSED:
        return None
    files = RunFiles(home.run_dir(run.id))
    if not files.state.exists():
        return None
    state = files.read_state()
    key, owner = state.paused_at, run.id
    while key and key in state.children:  # the gate may sit in a child run
        child_id = state.children[key]
        child = RunFiles(home.run_dir(child_id))
        child_state = child.read_state()
        if not child_state.paused_at:
            break
        files, state, key, owner = child, child_state, child_state.paused_at, child_id
    return files, key, owner


def _questions_event(files: RunFiles, key: str | None) -> dict[str, Any] | None:
    """The ``questions_waiting`` event of the step paused at ``key``, if it's a questions
    step."""
    for event in reversed(files.read_events()):
        if event.get("type") == "questions_waiting":
            return event if key and event.get("key") == key else None
        if event.get("type") == "run_started":
            return None
    return None


def waiting_gate(home: Home, run: Run) -> dict[str, Any] | None:
    """The gate (or questions step) a paused run waits at: its step, message and options."""
    target = _paused_target(home, run)
    if target is None:
        return None
    files, key, owner = target
    asked = _questions_event(files, key)
    waiting = (
        None
        if asked is not None
        else next(
            (e for e in reversed(files.read_events()) if e.get("type") == "gate_waiting"), None
        )
    )
    return {
        "run_id": owner,
        "key": key,
        "step_id": (asked or waiting or {}).get("step_id", key),
        "message": waiting.get("message") if waiting else None,
        "options": waiting.get("options") if waiting else None,
        "reason": run.error,
    }


def waiting_questions(home: Home, run: Run) -> list[dict[str, Any]] | None:
    """The pending questions a run paused at a ``questions`` step waits for, or None."""
    target = _paused_target(home, run)
    if target is None:
        return None
    files, key, _ = target
    asked = _questions_event(files, key)
    if asked is None:
        return None
    ids = list(asked.get("ids") or [])
    try:
        found = {q.id: q for q in questions.load(Path(str(asked.get("file"))))}
    except (InputError, OSError):
        return [{"id": qid} for qid in ids]
    return [
        found[qid].model_dump(mode="json") for qid in ids if qid in found and found[qid].is_pending
    ]


def run_brief(db: Database, run: Run) -> dict[str, Any]:
    repo, feature = _names(db, run)
    return {
        "id": run.id,
        "workflow_id": run.workflow_id,
        "workflow_version": run.workflow_version,
        "status": run.status.value,
        "repo": repo,
        "feature": feature,
        "current_step_id": run.current_step_id,
        "parent_run_id": run.parent_run_id,
        "created_at": run.created_at,
        "started_at": run.started_at,
        "ended_at": run.ended_at,
        "error": run.error,
    }


def run_detail(db: Database, home: Home, run_id: str) -> dict[str, Any]:
    """Status of one run: its steps (child runs included), the gate it waits at, totals."""
    run = get_run(db, run_id)
    children = [i for i in run_tree(db, run.id) if i != run.id]
    feature = store.get(db, Feature, run.feature_id) if run.feature_id else None
    return {
        **run_brief(db, run),
        "worktree": feature.worktree_path if feature else _workdir(home, run),
        "inputs": run.inputs,
        "outputs": run.outputs,
        "waiting": _waiting(home, run),
        "children": children,
        "steps": [step_summary(r) for r in step_execs(db, run.id)],
        "totals": aggregate.grand_total(db, run_id=run.id).to_json(),
        "run_dir": str(home.run_dir(run.id)),
    }


def _waiting(home: Home, run: Run) -> dict[str, Any] | None:
    waiting = waiting_gate(home, run)
    if waiting is not None:
        waiting["questions"] = waiting_questions(home, run)
    return waiting


def _workdir(home: Home, run: Run) -> str | None:
    """Where a run with no feature (a repo-scoped run) works, from its state."""
    files = RunFiles(home.run_dir(run.id))
    return files.read_state().workdir if files.state.exists() else None


def find_feature(db: Database, repo: Repo, name: str) -> Feature:
    found = store.select(db, Feature, "repo_id = ? AND name = ?", (repo.id, name))
    if not found:
        raise ViewError(f"No feature {name!r} in repo {repo.name!r}")
    return found[0]


def list_runs(
    db: Database,
    *,
    repo: Repo | None = None,
    feature: Feature | None = None,
    status: RunStatus | None = None,
    since: datetime | None = None,
    limit: int | None = 20,
) -> list[dict[str, Any]]:
    """Root runs, newest first, with their cost."""
    where = ["parent_run_id IS NULL"]
    params: list[Any] = []
    if repo is not None:
        where.append("repo_id = ?")
        params.append(repo.id)
    if feature is not None:
        where.append("feature_id = ?")
        params.append(feature.id)
    if status is not None:
        where.append("status = ?")
        params.append(status.value)
    if since is not None:
        where.append("created_at >= ?")
        params.append(aggregate.utc(since))
    order = "created_at DESC, id DESC" + (f" LIMIT {int(limit)}" if limit else "")
    runs = store.select(db, Run, " AND ".join(where), tuple(params), order)
    costs = {t.key: t for t in aggregate.totals(db, "run", repo_id=repo.id if repo else None)}
    out = []
    for run in runs:
        total = costs.get(run.id) or aggregate.Totals(key=run.id)
        out.append({**run_brief(db, run), "cost_usd": total.cost_usd})
    return out


# ------------------------------------------------------------------ trace


def _action(a: Action) -> dict[str, Any]:
    return {
        "seq": a.seq,
        "kind": a.kind,
        "tool_name": a.tool_name,
        "input": a.input_summary,
        "result": a.result_summary,
        "is_error": a.is_error,
        "duration_ms": a.duration_ms,
        "ts": a.ts,
    }


def _hook(hook: HookExec, actions: list[Action], changes: list[FileChange]) -> dict[str, Any]:
    return {
        "hook_exec_id": hook.id,
        "event": hook.event,
        "name": hook.name,
        "kind": hook.kind.value,
        "optional": hook.optional,
        "status": hook.status.value,
        "duration_ms": hook.duration_ms,
        **_metrics(hook),
        "error": hook.error,
        "actions": [_action(a) for a in actions if a.hook_exec_id == hook.id],
        "files": [_change(c) for c in changes if c.hook_exec_id == hook.id],
    }


def _change(c: FileChange) -> dict[str, Any]:
    return {
        "path": c.path,
        "old_path": c.old_path,
        "status": c.status.value,
        "added": c.added,
        "removed": c.removed,
    }


def trace(db: Database, home: Home, run_id: str, step_id: str | None = None) -> dict[str, Any]:
    """Every action per step execution, with each hook's own actions nested under it.

    Run-level hooks (``before_run``/``after_run``) are listed under ``run_hooks``.
    """
    run = get_run(db, run_id)
    ids = run_tree(db, run.id)
    rows = step_execs(db, run.id, step_id)
    if step_id is not None and not rows:
        raise ViewError(f"Run {run.id} has no step {step_id!r}")
    hooks = store.select(db, HookExec, f"run_id IN ({_in(ids)})", tuple(ids), "started_at, id")
    actions: list[Action] = []
    changes: list[FileChange] = []
    for rid in ids:
        files = RunFiles(home.run_dir(rid))
        owners = ["run", *(r.id for r in rows if r.run_id == rid)]
        owners += [h.id for h in hooks if h.run_id == rid]
        actions += journal.read_actions(files, owners)
        for r in rows:
            if r.run_id == rid:
                changes += journal.read_changes(files, r.id)
    steps = []
    for row in rows:
        own = [h for h in hooks if h.step_exec_id == row.id]
        steps.append(
            {
                **step_summary(row),
                "actions": [
                    _action(a)
                    for a in actions
                    if a.step_exec_id == row.id and a.hook_exec_id is None
                ],
                "hooks": [_hook(h, actions, changes) for h in own],
            }
        )
    run_hooks = (
        [_hook(h, actions, changes) for h in hooks if h.step_exec_id is None]
        if step_id is None
        else []
    )
    return {"run_id": run.id, "status": run.status.value, "steps": steps, "run_hooks": run_hooks}


# ---------------------------------------------------------------- changes


def changes(db: Database, home: Home, run_id: str, step_id: str | None = None) -> dict[str, Any]:
    """Files and lines changed per step execution (only steps that changed something).

    Each step lists the files of its whole window, hooks included; ``hooks`` breaks out
    what each hook changed by itself. Totals count a file changed twice once.
    """
    run = get_run(db, run_id)
    ids = run_tree(db, run.id)
    rows = step_execs(db, run.id, step_id)
    if step_id is not None and not rows:
        raise ViewError(f"Run {run.id} has no step {step_id!r}")
    all_changes = [
        c for r in rows for c in journal.read_changes(RunFiles(home.run_dir(r.run_id)), r.id)
    ]
    hooks = {
        h.id: h for h in store.select(db, HookExec, f"run_id IN ({_in(ids)})", tuple(ids), "id")
    }
    steps: list[dict[str, Any]] = []
    for row in rows:
        mine = [c for c in all_changes if c.step_exec_id == row.id]
        if not mine:
            continue
        window = [c for c in mine if c.hook_exec_id is None]
        by_hook: dict[str, list[FileChange]] = {}
        for c in mine:
            if c.hook_exec_id is not None:
                by_hook.setdefault(c.hook_exec_id, []).append(c)
        steps.append(
            {
                "exec_id": row.id,
                "run_id": row.run_id,
                "step_id": row.step_id,
                "iteration": row.iteration,
                "attempt": row.attempt,
                "status": row.status.value,
                "files": [_change(c) for c in window],
                "summary": {
                    "files": len(window),
                    "added": sum(c.added or 0 for c in window),
                    "removed": sum(c.removed or 0 for c in window),
                },
                "hooks": [
                    {
                        "hook_exec_id": hid,
                        "event": hooks[hid].event if hid in hooks else None,
                        "name": hooks[hid].name if hid in hooks else None,
                        "files": [_change(c) for c in items],
                    }
                    for hid, items in by_hook.items()
                ],
            }
        )
    if step_id is None:
        total: dict[str, int] = aggregate.grand_total(db, run_id=run.id).to_json()["changes"]
    else:
        paths = {f["path"] for s in steps for f in s["files"]}
        total = {
            "files": len(paths),
            "added": sum(s["summary"]["added"] for s in steps),
            "removed": sum(s["summary"]["removed"] for s in steps),
        }
    return {"run_id": run.id, "steps": steps, "totals": total}


# ------------------------------------------------------------------- cost


def cost(
    db: Database,
    by: aggregate.GroupBy,
    *,
    repo: Repo | None = None,
    feature: Feature | None = None,
    run_id: str | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
) -> dict[str, Any]:
    """Cost, tokens and changes grouped by step, run, feature, repo, day or user."""
    if run_id is not None:
        get_run(db, run_id)
    filters: dict[str, Any] = {
        "run_id": run_id,
        "feature_id": feature.id if feature else None,
        "repo_id": repo.id if repo else None,
        "since": since,
        "until": until,
    }
    groups = aggregate.totals(db, by, **filters)
    labels = _labels(db, by, [g.key for g in groups])
    return {
        "by": by,
        "filters": {
            "repo": repo.name if repo else None,
            "feature": feature.name if feature else None,
            "run": run_id,
            "since": since,
            "until": until,
        },
        "groups": [{**g.to_json(), "label": labels.get(g.key or "", g.key)} for g in groups],
        "total": aggregate.grand_total(db, **filters).to_json(),
    }


def _labels(db: Database, by: str, keys: list[str | None]) -> dict[str, str]:
    present = [k for k in keys if k]
    if not present:
        return {}
    if by == "feature":
        rows = db.execute(
            f"SELECT id, name FROM features WHERE id IN ({_in(present)})", present
        ).fetchall()
        return {r[0]: r[1] for r in rows}
    if by == "repo":
        rows = db.execute(
            f"SELECT id, name FROM repos WHERE id IN ({_in(present)})", present
        ).fetchall()
        return {r[0]: r[1] for r in rows}
    if by == "run":
        rows = db.execute(
            f"SELECT id, workflow_id FROM runs WHERE id IN ({_in(present)})", present
        ).fetchall()
        return {r[0]: f"{r[0]} ({r[1]})" for r in rows}
    return {}
