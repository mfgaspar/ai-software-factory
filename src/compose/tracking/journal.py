"""What each step did and which files it changed, kept as files in the run folder.

The database only holds identifiers, status and totals; the detail lives next to the
run's other files (see :class:`compose.runner.state.RunFiles`):

- ``steps/<exec id>.actions.jsonl``  messages, tool calls and results of a step or hook
- ``steps/<exec id>.changes.jsonl``  files a step (and each of its hooks) changed
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from compose.core.db import utcnow
from compose.core.models import FileStatus
from compose.runner.state import RunFiles
from compose.tracking.diff import Change


class Action(BaseModel):
    run_id: str
    step_exec_id: str | None = None
    hook_exec_id: str | None = None
    seq: int
    kind: str  # message | tool_call | tool_result
    tool_name: str | None = None
    input_summary: str | None = None
    result_summary: str | None = None
    is_error: bool = False
    duration_ms: int | None = None
    ts: datetime = Field(default_factory=utcnow)


class FileChange(BaseModel):
    run_id: str
    step_exec_id: str
    hook_exec_id: str | None = None
    path: str
    old_path: str | None = None
    status: FileStatus
    added: int | None = None  # None for binary files
    removed: int | None = None


def _owner(action: Action) -> str:
    return action.hook_exec_id or action.step_exec_id or "run"


def append_action(files: RunFiles, action: Action) -> None:
    files.append_jsonl(files.actions_key(_owner(action)), [action.model_dump(mode="json")])


def append_changes(
    files: RunFiles, run_id: str, step_exec_id: str, hook_exec_id: str | None, changes: list[Change]
) -> None:
    rows = [
        FileChange(
            run_id=run_id,
            step_exec_id=step_exec_id,
            hook_exec_id=hook_exec_id,
            path=c.path,
            old_path=c.old_path,
            status=c.status,
            added=c.added,
            removed=c.removed,
        ).model_dump(mode="json")
        for c in changes
    ]
    files.append_jsonl(files.changes_key(step_exec_id), rows)


def read_actions(files: RunFiles, owner_ids: list[str]) -> list[Action]:
    """Actions of the given step/hook executions, in run order."""
    found: list[Action] = []
    for owner in owner_ids:
        found.extend(Action.model_validate(r) for r in files.read_jsonl(files.actions_key(owner)))
    return sorted(found, key=lambda a: a.seq)


def read_changes(files: RunFiles, step_exec_id: str) -> list[FileChange]:
    return [FileChange.model_validate(r) for r in files.read_jsonl(files.changes_key(step_exec_id))]
