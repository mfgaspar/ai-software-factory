"""A scripted engine for tests: replays events and edits files deterministically."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from compose.engines.base import (
    EngineEvent,
    EngineOptions,
    EngineResult,
    EngineTask,
    MessageEvent,
    ToolCallEvent,
    ToolResultEvent,
    Usage,
    UsageEvent,
)


@dataclass
class Act:
    """One scripted action. Exactly one of the fields describes it."""

    say: str | None = None
    tool: str | None = None
    tool_input: dict[str, Any] = field(default_factory=dict)
    tool_output: str = "ok"
    tool_error: bool = False
    write: dict[str, str] = field(default_factory=dict)  # path -> content (relative to cwd)
    delete: list[str] = field(default_factory=list)
    usage: Usage | None = None
    sleep: float = 0.0


@dataclass
class Script:
    actions: list[Act] = field(default_factory=list)
    final_text: str = "done"
    fail: str | None = None  # finish with status failed and this error
    session_id: str = "fake-session"


def edit(path: str, content: str, *, cost: float = 0.0) -> list[Act]:
    """Helper: a Write tool call that creates/overwrites ``path``."""
    acts = [Act(tool="Write", tool_input={"file_path": path}, write={path: content})]
    if cost:
        acts.append(Act(usage=Usage(input_tokens=100, output_tokens=50, cost_usd=cost, turns=1)))
    return acts


ScriptFor = Callable[[EngineTask, Path, EngineOptions], Script]


class FakeRun:
    def __init__(self, script: Script, cwd: Path) -> None:
        self.script = script
        self.cwd = cwd
        self._stopped = asyncio.Event()
        self._result: EngineResult | None = None
        self._usage = Usage()

    async def events(self) -> AsyncIterator[EngineEvent]:
        for i, act in enumerate(self.script.actions):
            if self._stopped.is_set():
                break
            if act.sleep:
                try:
                    await asyncio.wait_for(self._stopped.wait(), timeout=act.sleep)
                    break
                except TimeoutError:
                    pass
            if act.say is not None:
                yield MessageEvent(act.say)
            if act.tool is not None:
                call_id = f"call-{i}"
                yield ToolCallEvent(call_id, act.tool, dict(act.tool_input))
                for rel, content in act.write.items():
                    target = self.cwd / rel
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_text(content)
                for rel in act.delete:
                    (self.cwd / rel).unlink(missing_ok=True)
                yield ToolResultEvent(call_id, act.tool_output, act.tool_error, duration_ms=1)
            if act.usage is not None:
                u = act.usage
                self._usage = Usage(
                    input_tokens=self._usage.input_tokens + u.input_tokens,
                    output_tokens=self._usage.output_tokens + u.output_tokens,
                    cache_read_tokens=self._usage.cache_read_tokens + u.cache_read_tokens,
                    cache_write_tokens=self._usage.cache_write_tokens + u.cache_write_tokens,
                    cost_usd=round(self._usage.cost_usd + u.cost_usd, 10),
                    turns=self._usage.turns + u.turns,
                )
                yield UsageEvent(self._usage)
        if self._stopped.is_set():
            self._result = EngineResult(
                "stopped", self._usage, self.script.session_id, "", error="stopped"
            )
        elif self.script.fail:
            self._result = EngineResult(
                "failed", self._usage, self.script.session_id, "", error=self.script.fail
            )
        else:
            self._result = EngineResult(
                "completed", self._usage, self.script.session_id, self.script.final_text
            )

    @property
    def result(self) -> EngineResult:
        if self._result is None:
            return EngineResult("stopped", self._usage, self.script.session_id, error="stopped")
        return self._result

    async def stop(self) -> None:
        self._stopped.set()


class FakeEngine:
    """Engine whose behavior per task is given by ``scripts``.

    ``scripts`` maps a skill name or exact prompt text to a :class:`Script`; ``default``
    is used otherwise. Every started task is recorded in :attr:`calls`.
    """

    def __init__(
        self,
        scripts: dict[str, Script] | ScriptFor | None = None,
        *,
        default: Script | None = None,
        name: str = "fake",
    ) -> None:
        self.name = name
        self.scripts = scripts if scripts is not None else {}
        self.default = default or Script()
        self.calls: list[tuple[EngineTask, Path, EngineOptions]] = []

    def start(self, task: EngineTask, cwd: Path, options: EngineOptions) -> FakeRun:
        self.calls.append((task, cwd, options))
        if callable(self.scripts):
            script = self.scripts(task, cwd, options)
        else:
            script = self.scripts.get(task.text, self.default)
        return FakeRun(script, cwd)

    def install(self, path: Path) -> list[Path]:
        return []

    def check(self) -> list[str]:
        return []
