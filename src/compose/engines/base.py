"""The boundary between compose and a coding engine.

The core never talks to Claude Code (or any other engine) directly: it starts an
:class:`EngineRun` through an :class:`Engine` adapter, consumes its events, and reads the
final :class:`EngineResult`.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, Protocol, runtime_checkable


@dataclass(frozen=True)
class EngineTask:
    """Run a skill (``/name args``) or send an inline prompt."""

    kind: Literal["skill", "prompt"]
    text: str  # skill name, or the prompt
    args: str | None = None

    @classmethod
    def skill(cls, name: str, args: str | None = None) -> EngineTask:
        return cls("skill", name, args)

    @classmethod
    def prompt(cls, text: str) -> EngineTask:
        return cls("prompt", text)

    @property
    def label(self) -> str:
        if self.kind == "skill":
            return f"/{self.text}" + (f" {self.args}" if self.args else "")
        return self.text


@dataclass(frozen=True)
class EngineOptions:
    model: str | None = None
    reasoning_effort: str | None = None
    max_turns: int | None = None
    max_cost_usd: float | None = None  # budget for this task (step limit or what the run has left)
    engine_options: dict[str, Any] = field(default_factory=dict)
    env: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class Usage:
    """Cumulative usage so far in one engine run."""

    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    cost_usd: float = 0.0
    turns: int = 0


@dataclass(frozen=True)
class MessageEvent:
    text: str
    kind: Literal["message"] = "message"


@dataclass(frozen=True)
class ToolCallEvent:
    call_id: str
    name: str
    input: dict[str, Any]
    kind: Literal["tool_call"] = "tool_call"


@dataclass(frozen=True)
class ToolResultEvent:
    call_id: str
    output: str
    is_error: bool = False
    duration_ms: int | None = None
    kind: Literal["tool_result"] = "tool_result"


@dataclass(frozen=True)
class UsageEvent:
    usage: Usage
    kind: Literal["usage_update"] = "usage_update"


EngineEvent = MessageEvent | ToolCallEvent | ToolResultEvent | UsageEvent


@dataclass(frozen=True)
class EngineResult:
    status: Literal["completed", "failed", "stopped"]
    usage: Usage = field(default_factory=Usage)
    session_id: str | None = None
    final_text: str = ""
    duration_ms: int = 0
    error: str | None = None
    model: str | None = None


class EngineRun(Protocol):
    """One engine invocation in progress."""

    def events(self) -> AsyncIterator[EngineEvent]:
        """Events as they happen. Iteration ends when the engine finishes."""
        ...

    @property
    def result(self) -> EngineResult:
        """Available once :meth:`events` is exhausted (or after :meth:`stop`)."""
        ...

    async def stop(self) -> None:
        """Ask the engine to stop as soon as possible (limits, abort, timeout)."""
        ...


@runtime_checkable
class Engine(Protocol):
    name: str

    def start(self, task: EngineTask, cwd: Path, options: EngineOptions) -> EngineRun: ...

    def install(self, path: Path, *, worktree: bool = False) -> list[Path]:
        """Put this engine's skills in place under ``path``; return files written.

        ``worktree=True`` is a run worktree: files the repo already commits are left as
        they are, and the ones compose adds are hidden from git.
        """
        ...

    def check(self) -> list[str]:
        """Problems that prevent using this engine (empty when ready)."""
        ...
