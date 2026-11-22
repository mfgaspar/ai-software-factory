"""The Claude Code engine, driven through the Claude Agent SDK."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import suppress
from pathlib import Path
from typing import Any, cast, get_args

from claude_agent_sdk import (
    ClaudeAgentOptions,
    ClaudeSDKClient,
    ClaudeSDKError,
    ResultMessage,
)
from claude_agent_sdk.types import EffortLevel, PermissionMode, SettingSource

from compose.engines.base import EngineEvent, EngineOptions, EngineResult, EngineTask
from compose.engines.claude import install as installer
from compose.engines.claude.mapping import EventMapper
from compose.engines.registry import EngineError

DEFAULT_PERMISSION_MODE: PermissionMode = "acceptEdits"
DEFAULT_SETTING_SOURCES: list[SettingSource] = ["project"]
STOP_TIMEOUT_SECONDS = 10.0

# engine_options a workflow may set for Claude Code (workflow, step or hook level)
ENGINE_OPTIONS = {
    "permission_mode": "permission mode: " + ", ".join(get_args(PermissionMode)),
    "allowed_tools": "tools allowed without asking (list)",
    "disallowed_tools": "tools never allowed (list)",
    "setting_sources": "Claude Code settings to load (default: project)",
    "add_dirs": "extra directories Claude Code may access (list)",
    "cli_path": "path to a specific claude executable",
}


def prompt_for(task: EngineTask) -> str:
    """A skill task runs as its slash command, exactly as a person would type it."""
    if task.kind == "skill":
        return f"/{task.text}" + (f" {task.args}" if task.args else "")
    return task.text


def _list(value: Any, name: str) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, list) and all(isinstance(v, str) for v in value):
        return list(value)
    raise EngineError(f"engine_options.{name} must be a list of strings")


def build_options(cwd: Path, options: EngineOptions) -> ClaudeAgentOptions:
    extra = dict(options.engine_options)
    unknown = sorted(set(extra) - set(ENGINE_OPTIONS))
    if unknown:
        known = ", ".join(sorted(ENGINE_OPTIONS))
        raise EngineError(f"unknown Claude Code engine_options: {', '.join(unknown)} ({known})")
    mode = extra.get("permission_mode", DEFAULT_PERMISSION_MODE)
    if mode not in get_args(PermissionMode):
        raise EngineError(f"engine_options.permission_mode: {mode!r} is not a permission mode")
    sources = _list(extra.get("setting_sources", DEFAULT_SETTING_SOURCES), "setting_sources")
    if not set(sources) <= set(get_args(SettingSource)):
        raise EngineError(f"engine_options.setting_sources: {sources} (use user, project, local)")
    effort = options.reasoning_effort
    if effort is not None and effort not in get_args(EffortLevel):
        raise EngineError(
            f"reasoning_effort {effort!r} is not one of {', '.join(get_args(EffortLevel))}"
        )
    return ClaudeAgentOptions(
        cwd=str(cwd),
        model=options.model,
        max_turns=options.max_turns,
        max_budget_usd=options.max_cost_usd,
        permission_mode=cast(PermissionMode, mode),
        allowed_tools=_list(extra.get("allowed_tools", []), "allowed_tools"),
        disallowed_tools=_list(extra.get("disallowed_tools", []), "disallowed_tools"),
        setting_sources=cast(list[SettingSource], sources),
        add_dirs=list(_list(extra.get("add_dirs", []), "add_dirs")),
        cli_path=extra.get("cli_path"),
        effort=cast(EffortLevel | None, effort),
        env=dict(options.env),
    )


class ClaudeRun:
    """One Claude Code session for one task."""

    def __init__(self, prompt: str, options: ClaudeAgentOptions) -> None:
        self.prompt = prompt
        self.options = options
        self.mapper = EventMapper()
        self._client: ClaudeSDKClient | None = None
        self._result: EngineResult | None = None
        self._stopped = False
        self._closed = False

    @property
    def result(self) -> EngineResult:
        if self._result is not None:
            return self._result
        if self.mapper.result is not None:
            return self.mapper.result
        status = "stopped" if self._stopped else "failed"
        return self.mapper.unfinished(status, None if self._stopped else "no result reported")

    async def events(self) -> AsyncIterator[EngineEvent]:
        client = ClaudeSDKClient(self.options)
        self._client = client
        try:
            await client.connect()
            await client.query(self.prompt)
            async for message in client.receive_response():
                for event in self.mapper.map(message):
                    yield event
                if isinstance(message, ResultMessage):
                    break
        except ClaudeSDKError as exc:
            if not self._stopped:
                self._result = self.mapper.unfinished("failed", f"{type(exc).__name__}: {exc}")
        finally:
            await self._close()

    async def stop(self) -> None:
        self._stopped = True
        client = self._client
        if client is not None and not self._closed:
            with suppress(Exception):
                await asyncio.wait_for(client.interrupt(), STOP_TIMEOUT_SECONDS)
        await self._close()

    async def _close(self) -> None:
        if self._closed or self._client is None:
            return
        self._closed = True
        with suppress(Exception):
            await asyncio.wait_for(self._client.disconnect(), STOP_TIMEOUT_SECONDS)


class ClaudeEngine:
    name = "claude"

    def start(self, task: EngineTask, cwd: Path, options: EngineOptions) -> ClaudeRun:
        return ClaudeRun(prompt_for(task), build_options(cwd, options))

    def install(self, path: Path, *, worktree: bool = False) -> list[Path]:
        return installer.install(path, worktree=worktree)

    def check(self) -> list[str]:
        return installer.check()
