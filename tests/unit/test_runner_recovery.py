from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from pathlib import Path

from compose.core import store
from compose.core.models import ExecStatus, Run, RunStatus
from compose.runner.recovery import DIED, recover_stale_runs
from tests.unit.runner_helpers import Env

DRIVER = """
import asyncio, sys
from pathlib import Path
from compose.core.config import Config, DefaultsConfig
from compose.core.db import open_database
from compose.core.home import ensure_home
from compose.engines.registry import EngineRegistry
from compose.repos import registry
from compose.runner.runner import Runner
from compose.workflows import loader

home = ensure_home()
db = open_database(home)
repo = registry.get_repo(db, sys.argv[1])
config = Config(defaults=DefaultsConfig(engine="fake"))
runner = Runner(db, home, engines=EngineRegistry(), config=config)
asyncio.run(runner.start(repo, loader.load_path(Path(sys.argv[2]))))
"""

WORKFLOW = """
workflow: {id: crash, name: Crash}
steps:
  - {id: first, run: "echo first"}
  - {id: slow, run: "test -f marker || sleep 60"}
  - {id: last, run: "echo last"}
"""


def test_recovery_after_killed_process(env: Env, tmp_path: Path) -> None:
    driver = tmp_path / "driver.py"
    driver.write_text(DRIVER)
    wf = tmp_path / "crash.yml"
    wf.write_text(WORKFLOW)
    proc = subprocess.Popen(
        [sys.executable, str(driver), env.repo.name, str(wf)], start_new_session=True
    )
    try:
        deadline = time.time() + 30
        run: Run | None = None
        while time.time() < deadline:
            rows = store.select(env.db, Run)
            if rows and env.exec_of(rows[0], "slow"):
                run = rows[0]
                break
            time.sleep(0.05)
        assert run is not None, "the run never reached the slow step"
    finally:
        os.killpg(proc.pid, signal.SIGKILL)  # kills the driver and its `sleep`
        proc.wait()

    assert store.get(env.db, Run, run.id).status is RunStatus.RUNNING  # type: ignore[union-attr]
    recovered = recover_stale_runs(env.db, env.home)
    assert [r.id for r in recovered] == [run.id]
    failed = store.get(env.db, Run, run.id)
    assert failed is not None and failed.status is RunStatus.FAILED and failed.error == DIED
    assert env.exec_of(run, "slow")[0].status is ExecStatus.FAILED
    assert recover_stale_runs(env.db, env.home) == []  # idempotent

    (env.worktree(run) / "marker").write_text("go")
    import asyncio

    resumed = asyncio.run(env.runner().resume(run.id))
    assert resumed.status is RunStatus.COMPLETED
    assert len(env.exec_of(run, "first")) == 1
    assert [e.attempt for e in env.exec_of(run, "slow")] == [1, 2]


def test_recovery_leaves_live_runs_alone(env: Env) -> None:
    from compose.core import locks

    wf = env.workflow("workflow: {id: live, name: L}\nsteps: [{id: a, run: 'true'}]\n")
    run = env.runner().create_run(env.repo, wf)
    run.status = RunStatus.RUNNING
    store.update(env.db, run)
    with locks.acquire(env.db, locks.feature_lock_key(run.feature_id or ""), run_id=run.id):
        assert recover_stale_runs(env.db, env.home) == []
    assert [r.id for r in recover_stale_runs(env.db, env.home)] == [run.id]
