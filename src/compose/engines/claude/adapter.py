"""The Claude Code engine.

Two transports run the same skills with the same options and produce the same events:
``cli`` (the default) runs ``claude -p --output-format stream-json`` as a process;
``sdk`` drives Claude Code through the Claude Agent SDK. Pick one with
``engine_options.transport``, or for every run in ``~/.compose/config.yml``::

    engines:
      claude:
        transport: sdk
"""

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

from compose.engines.base import EngineEvent, EngineOptions, EngineResult, EngineRun, EngineTask
from compose.engines.claude import install as installer
from compose.engines.claude.cli import ClaudeCliRun
from compose.engines.claude.mapping import EventMapper
from compose.engines.registry import EngineError

DEFAULT_PERMISSION_MODE: PermissionMode = "acceptEdits"
DEFAULT_SETTING_SOURCES: list[SettingSource] = ["project"]
STOP_TIMEOUT_SECONDS = 10.0
# compose's skills locate features through the compose CLI; headless runs can't ask
ALWAYS_ALLOWED = ["Bash(compose:*)"]

# engine_options a workflow may set for Claude Code (workflow, step or hook level)
TRANSPORTS = ("cli", "sdk")
DEFAULT_TRANSPORT = "cli"
ENGINE_OPTIONS = {
    "transport": "how compose runs Claude Code: cli (claude -p, default) or sdk",
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
    """A list of strings; surrounding spaces and empty entries are dropped (so
    ``"{{ inputs.tools | split(',') }}"`` works with an empty or spaced input)."""
    if isinstance(value, str):
        value = [value]
    if isinstance(value, list) and all(isinstance(v, str) for v in value):
        return [v.strip() for v in value if v.strip()]
    raise EngineError(f"engine_options.{name} must be a list of strings")


def _merge(first: list[str], second: list[str]) -> list[str]:
    return list(dict.fromkeys([*first, *second]))


def transport(options: EngineOptions, default: str = DEFAULT_TRANSPORT) -> str:
    value = options.engine_options.get("transport", default)
    if value not in TRANSPORTS:
        raise EngineError(f"engine_options.transport: {value!r} (use {' or '.join(TRANSPORTS)})")
    return str(value)


def build_options(cwd: Path, options: EngineOptions) -> ClaudeAgentOptions:
    extra = dict(options.engine_options)
    unknown = sorted(set(extra) - set(ENGINE_OPTIONS))
    if unknown:
        known = ", ".join(sorted(ENGINE_OPTIONS))
        raise EngineError(f"unknown Claude Code engine_options: {', '.join(unknown)} ({known})")
    transport(options)
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
        allowed_tools=_merge(
            ALWAYS_ALLOWED, _list(extra.get("allowed_tools", []), "allowed_tools")
        ),
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

    def __init__(self, default_transport: str = DEFAULT_TRANSPORT) -> None:
        self.default_transport = default_transport

    def start(self, task: EngineTask, cwd: Path, options: EngineOptions) -> EngineRun:
        sdk_options = build_options(cwd, options)
        if transport(options, self.default_transport) == "sdk":
            return ClaudeRun(prompt_for(task), sdk_options)
        return ClaudeCliRun(prompt_for(task), sdk_options)

    def install(self, path: Path, *, worktree: bool = False) -> list[Path]:
        return installer.install(path, worktree=worktree)

    def check(self) -> list[str]:
        return installer.check()
