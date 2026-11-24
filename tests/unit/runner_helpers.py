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
from compose.core.models import Run, StepExec
from compose.engines.fake import FakeEngine
from compose.engines.registry import EngineRegistry
from compose.runner.runner import Interaction, Runner
from compose.runner.state import RunFiles
from compose.tracking import journal
from compose.tracking.journal import Action
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
        files = self.files(run)
        owners = ["run", *files.action_owners()]
        return journal.read_actions(files, owners)

    def files(self, run: Run) -> RunFiles:
        return RunFiles(self.home.run_dir(run.id))

    def worktree(self, run: Run) -> Path:
        """The run's feature worktree, or its working directory for a repo-scoped run."""
        if run.feature_id is None:
            workdir = self.files(run).read_state().workdir
            assert workdir is not None, f"{run.id} has no working directory yet"
            return Path(workdir)
        feature = self.db.execute(
            "SELECT worktree_path FROM features WHERE id = ?", (run.feature_id,)
        ).fetchone()
        return Path(feature[0])


def interaction(**answers: Any) -> Interaction:
    return Interaction(interactive=True, **answers)
