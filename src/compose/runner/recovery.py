"""Mark runs whose process died as failed, so they can be resumed."""

from __future__ import annotations

from compose.core import locks, store
from compose.core.db import Database, utcnow
from compose.core.home import Home
from compose.core.models import ExecStatus, HookExec, Run, RunStatus, StepExec
from compose.runner.hooks import fold_hook_metrics
from compose.runner.state import RunFiles

DIED = "the process running this run stopped unexpectedly"


def _root(db: Database, run: Run) -> Run:
    while run.parent_run_id:
        parent = store.get(db, Run, run.parent_run_id)
        if parent is None:
            break
        run = parent
    return run


def recover_stale_runs(db: Database, home: Home) -> list[Run]:
    """Fail every ``running`` run that no live process holds the run's lock for (its
    feature's, or its repo's for a repo-scoped run)."""
    recovered: list[Run] = []
    for run in store.select(db, Run, "status = ?", (RunStatus.RUNNING.value,)):
        root = _root(db, run)
        key = (
            locks.feature_lock_key(run.feature_id)
            if run.feature_id
            else locks.repo_lock_key(run.repo_id)
        )
        info = locks.read_lock(db, key)
        alive = info is not None and info.run_id == root.id and not locks.is_stale(info)
        if alive:
            continue
        for row in store.select(
            db, StepExec, "run_id = ? AND status = ?", (run.id, ExecStatus.RUNNING.value)
        ):
            row.status = ExecStatus.FAILED
            row.error = DIED
            row.ended_at = utcnow()
            fold_hook_metrics(db, row)
            store.update(db, row)
        run.status = RunStatus.FAILED
        run.error = DIED
        run.ended_at = utcnow()
        store.update(db, run)
        for hook in store.select(
            db, HookExec, "run_id = ? AND status = ?", (run.id, ExecStatus.RUNNING.value)
        ):
            hook.status = ExecStatus.FAILED
            hook.error = DIED
            hook.ended_at = utcnow()
            store.update(db, hook)
        files = RunFiles(home.run_dir(run.id))
        if files.state.exists():
            state = files.read_state()
            state.status = RunStatus.FAILED.value
            state.error = DIED
            # The step that was running starts over as a new attempt on resume.
            failed_ids = {
                r.id
                for r in store.select(
                    db, StepExec, "run_id = ? AND status = ?", (run.id, ExecStatus.FAILED.value)
                )
            }
            state.execs = {k: v for k, v in state.execs.items() if v not in failed_ids}
            files.write_state(state)
            files.append_event({"type": "run_recovered", "run_id": run.id, "status": "failed"})
        recovered.append(run)
    return recovered
