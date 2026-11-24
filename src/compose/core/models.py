"""Records stored in the compose database, as pydantic models."""

from __future__ import annotations

import json
from datetime import datetime
from enum import StrEnum
from typing import Any, ClassVar, Self

from pydantic import BaseModel, ConfigDict, Field

from compose.core.db import format_ts, utcnow


class RunStatus(StrEnum):
    CREATED = "created"
    RUNNING = "running"
    COMPLETED = "completed"
    PAUSED = "paused"
    FAILED = "failed"
    ABORTED = "aborted"


class ExecStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"
    PAUSED = "paused"
    ABORTED = "aborted"


class HookKind(StrEnum):
    COMMAND = "command"
    PROMPT = "prompt"
    RUN = "run"
    BUILTIN = "builtin"


class FileStatus(StrEnum):
    ADDED = "A"
    MODIFIED = "M"
    DELETED = "D"
    RENAMED = "R"
    COPIED = "C"
    TYPE_CHANGED = "T"


class Record(BaseModel):
    """A row in one table. Fields map 1:1 to columns, except JSON fields
    (``foo`` <-> ``foo_json``)."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    TABLE: ClassVar[str]
    PK: ClassVar[str] = "id"
    JSON_FIELDS: ClassVar[frozenset[str]] = frozenset()

    def to_row(self) -> dict[str, Any]:
        row: dict[str, Any] = {}
        for key, value in self.model_dump(mode="json").items():
            raw = getattr(self, key, None)
            if isinstance(raw, datetime):
                row[key] = format_ts(raw)
            elif key in self.JSON_FIELDS:
                row[f"{key}_json"] = None if value is None else json.dumps(value)
            else:
                row[key] = value
        return row

    @classmethod
    def from_row(cls, row: Any) -> Self:
        data: dict[str, Any] = {}
        for key in row.keys():  # noqa: SIM118 - Row only supports .keys()
            value = row[key]
            if key.endswith("_json") and key[:-5] in cls.JSON_FIELDS:
                data[key[:-5]] = None if value is None else json.loads(value)
            else:
                data[key] = value
        return cls.model_validate(data)


class Metrics(BaseModel):
    """Usage, cost and change totals shared by step and hook executions."""

    engine: str | None = None
    model: str | None = None
    session_id: str | None = None
    turns: int | None = None
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    cost_usd: float = 0.0
    files_changed: int = 0
    lines_added: int = 0
    lines_removed: int = 0


class Repo(Record):
    TABLE: ClassVar[str] = "repos"

    id: str
    name: str
    path: str
    origin_url: str | None = None
    default_branch: str | None = None
    created_at: datetime = Field(default_factory=utcnow)


class Feature(Record):
    TABLE: ClassVar[str] = "features"

    id: str
    repo_id: str
    number: int
    slug: str
    name: str
    branch: str
    worktree_path: str | None = None
    created_at: datetime = Field(default_factory=utcnow)


class Run(Record):
    TABLE: ClassVar[str] = "runs"
    JSON_FIELDS: ClassVar[frozenset[str]] = frozenset({"inputs", "outputs"})

    id: str
    repo_id: str
    feature_id: str | None = None
    workflow_id: str
    workflow_version: str
    status: RunStatus = RunStatus.CREATED
    parent_run_id: str | None = None
    parent_exec_id: str | None = None
    started_by: str | None = None
    current_step_id: str | None = None
    inputs: dict[str, Any] = Field(default_factory=dict)
    outputs: dict[str, Any] | None = None
    abort_requested: bool = False
    error: str | None = None
    created_at: datetime = Field(default_factory=utcnow)
    started_at: datetime | None = None
    ended_at: datetime | None = None


class StepExec(Record, Metrics):
    TABLE: ClassVar[str] = "step_execs"
    JSON_FIELDS: ClassVar[frozenset[str]] = frozenset({"output"})

    id: str
    run_id: str
    step_id: str
    step_type: str
    parent_exec_id: str | None = None
    iteration: int | None = None
    attempt: int = 1
    status: ExecStatus = ExecStatus.PENDING
    started_at: datetime | None = None
    ended_at: datetime | None = None
    duration_ms: int | None = None
    output: dict[str, Any] | None = None
    error: str | None = None


class HookExec(Record, Metrics):
    TABLE: ClassVar[str] = "hook_execs"

    id: str
    run_id: str
    step_exec_id: str | None = None
    event: str
    hook_index: int
    kind: HookKind
    name: str
    optional: bool = False
    status: ExecStatus = ExecStatus.PENDING
    started_at: datetime | None = None
    ended_at: datetime | None = None
    duration_ms: int | None = None
    error: str | None = None
