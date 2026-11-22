"""Helpers for runner tests: a registered repo, the fake engine and inline workflows."""

from __future__ import annotations

import textwrap
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from compose.core import store
from compose.core.config import Config, DefaultsConfig
from compose.core.db import Database
from compose.core.home import Home
from compose.core.models import Action, Run, StepExec
from compose.engines.fake import FakeEngine
from compose.engines.registry import EngineRegistry
from compose.runner.runner import Interaction, Runner
from compose.runner.state import RunFiles
from compose.workflows import loader


@dataclass
class Env:
    db: Database
    home: Home
    repo_path: Path
    tmp: Path
    fake: FakeEngine
    events: list[dict[str, Any]]
    repo: Any

    def runner(self, **kwargs: Any) -> Runner:
        return Runner(
            self.db,
            self.home,
            engines=EngineRegistry({"fake": self.fake}),
            config=Config(defaults=DefaultsConfig(engine="fake", model="default-model")),
            on_event=self.events.append,
            **kwargs,
        )

    def workflow(self, body: str, name: str = "wf") -> loader.LoadedWorkflow:
        path = self.tmp / f"{name}.yml"
        path.write_text(textwrap.dedent(body))
        return loader.load_path(path)

    def execs(self, run: Run) -> list[StepExec]:
        return store.select(self.db, StepExec, "run_id = ?", (run.id,), "started_at, id")

    def exec_of(self, run: Run, step_id: str) -> list[StepExec]:
        return [e for e in self.execs(run) if e.step_id == step_id]

    def actions(self, run: Run) -> list[Action]:
        return store.select(self.db, Action, "run_id = ?", (run.id,), "seq")

    def files(self, run: Run) -> RunFiles:
        return RunFiles(self.home.run_dir(run.id))

    def worktree(self, run: Run) -> Path:
        feature = self.db.conn.execute(
            "SELECT worktree_path FROM features WHERE id = ?", (run.feature_id,)
        ).fetchone()
        return Path(feature[0])


def interaction(**answers: Any) -> Interaction:
    return Interaction(interactive=True, **answers)
