"""Run folder (``$COMPOSE_HOME/runs/<run_id>/``) and resumable run state.

Files:
  definition.yml   the exact workflow definition the run started with
  inputs.json      resolved inputs
  state.json       status, progress and outputs needed to resume
  log.jsonl        append-only event log (also tailed by the API)
  steps/<id>.json  one record per step execution
"""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from compose.core.db import utcnow
from compose.core.models import RunStatus

ALLOWED_TRANSITIONS: dict[RunStatus, frozenset[RunStatus]] = {
    RunStatus.CREATED: frozenset({RunStatus.RUNNING, RunStatus.FAILED, RunStatus.ABORTED}),
    RunStatus.RUNNING: frozenset(
        {RunStatus.COMPLETED, RunStatus.PAUSED, RunStatus.FAILED, RunStatus.ABORTED}
    ),
    RunStatus.PAUSED: frozenset({RunStatus.RUNNING, RunStatus.ABORTED}),
    RunStatus.FAILED: frozenset({RunStatus.RUNNING, RunStatus.ABORTED}),
    RunStatus.COMPLETED: frozenset(),
    RunStatus.ABORTED: frozenset(),
}


class TransitionError(Exception):
    pass


def check_transition(current: RunStatus, new: RunStatus) -> None:
    if new not in ALLOWED_TRANSITIONS[current]:
        raise TransitionError(f"a {current.value} run cannot become {new.value}")


def atomic_write(path: Path, text: str) -> None:
    """Write via a temp file + rename so readers never see a partial file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


@dataclass
class CompletedStep:
    exec_id: str
    step_id: str
    status: str
    result: dict[str, Any]  # what `steps.<id>` evaluates to


@dataclass
class RunState:
    """What a run needs to resume. Keys identify step executions (see ``Scope.key``)."""

    status: str = RunStatus.CREATED.value
    current_step_id: str | None = None
    completed: dict[str, CompletedStep] = field(default_factory=dict)
    execs: dict[str, str] = field(default_factory=dict)  # key -> exec id (reused on resume)
    attempts: dict[str, int] = field(default_factory=dict)
    retry_gates: list[str] = field(default_factory=list)
    children: dict[str, str] = field(default_factory=dict)  # key -> child run id
    gate_choices: dict[str, str] = field(default_factory=dict)  # key -> decision given on resume
    snapshots: dict[str, str] = field(default_factory=dict)  # exec id -> tree at step start
    workflow_dir: str | None = None
    workflow_source: str | None = None
    workdir: str | None = None  # where the run works (a repo-scoped run has no feature)
    paused_at: str | None = None
    error: str | None = None
    updated_at: str = ""

    def to_json(self) -> dict[str, Any]:
        data = asdict(self)
        return data

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> RunState:
        completed = {k: CompletedStep(**v) for k, v in data.get("completed", {}).items()}
        return cls(**{**data, "completed": completed})


class RunFiles:
    def __init__(self, directory: Path) -> None:
        self.dir = directory

    @property
    def definition(self) -> Path:
        return self.dir / "definition.yml"

    @property
    def inputs(self) -> Path:
        return self.dir / "inputs.json"

    @property
    def state(self) -> Path:
        return self.dir / "state.json"

    @property
    def log(self) -> Path:
        return self.dir / "log.jsonl"

    @property
    def steps_dir(self) -> Path:
        return self.dir / "steps"

    def create(self, definition_text: str, inputs: dict[str, Any]) -> None:
        self.dir.mkdir(parents=True, exist_ok=False)
        self.steps_dir.mkdir()
        atomic_write(self.definition, definition_text)
        self.write_inputs(inputs)
        self.write_state(RunState())
        self.log.touch()

    def write_inputs(self, inputs: dict[str, Any]) -> None:
        atomic_write(self.inputs, json.dumps(inputs, indent=2, default=str))

    def read_inputs(self) -> dict[str, Any]:
        data: dict[str, Any] = json.loads(self.inputs.read_text())
        return data

    def write_state(self, state: RunState) -> None:
        state.updated_at = utcnow().isoformat()
        atomic_write(self.state, json.dumps(state.to_json(), indent=2, default=str))

    def read_state(self) -> RunState:
        return RunState.from_json(json.loads(self.state.read_text()))

    def append_event(self, event: dict[str, Any]) -> None:
        line = json.dumps({"ts": utcnow().isoformat(), **event}, default=str)
        with self.log.open("a") as handle:
            handle.write(line + "\n")

    def read_events(self) -> list[dict[str, Any]]:
        if not self.log.exists():
            return []
        return [json.loads(line) for line in self.log.read_text().splitlines() if line]

    def write_step_record(self, exec_id: str, record: dict[str, Any]) -> None:
        atomic_write(self.steps_dir / f"{exec_id}.json", json.dumps(record, indent=2, default=str))
