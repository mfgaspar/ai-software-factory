"""Mark runs whose process died as failed, so they can be resumed."""

from __future__ import annotations

from compose.core import locks, store
from compose.core.db import Database, utcnow
from compose.core.home import Home
from compose.core.models import ExecStatus, Run, RunStatus, StepExec
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
    """Fail every ``running`` run that no live process holds the feature lock for."""
    recovered: list[Run] = []
    for run in store.select(db, Run, "status = ?", (RunStatus.RUNNING.value,)):
        root = _root(db, run)
        info = locks.read_lock(db, locks.feature_lock_key(run.feature_id or ""))
        alive = info is not None and info.run_id == root.id and not locks.is_stale(info)
        if alive:
            continue
        for row in store.select(
            db, StepExec, "run_id = ? AND status = ?", (run.id, ExecStatus.RUNNING.value)
        ):
            row.status = ExecStatus.FAILED
            row.error = DIED
            row.ended_at = utcnow()
            store.update(db, row)
        run.status = RunStatus.FAILED
        run.error = DIED
        run.ended_at = utcnow()
        store.update(db, run)
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
