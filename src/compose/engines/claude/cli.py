"""Claude Code driven as a command: ``claude -p --output-format stream-json --verbose``.

The prompt goes in on stdin and every line of output is a JSON event (system, assistant,
user, result). Lines are mapped by the same :class:`EventMapper` as the SDK transport,
so traces and costs come out identical; the final ``result`` line carries the
authoritative cost, tokens, turns and errors.
"""

from __future__ import annotations

import asyncio
import json
import os
import signal
from collections import deque
from collections.abc import AsyncIterator
from contextlib import suppress

from claude_agent_sdk import ClaudeAgentOptions

from compose.engines.base import EngineEvent, EngineResult
from compose.engines.claude import install as installer
from compose.engines.claude.mapping import EventMapper
from compose.engines.registry import EngineError

STOP_TIMEOUT_SECONDS = 10.0
LINE_LIMIT_BYTES = 64 * 1024 * 1024  # one JSON line can hold a large tool result
STDERR_LINES = 20
# set inside a Claude Code session; a nested claude would refuse to start
DROPPED_ENV = ("CLAUDECODE",)


def build_command(options: ClaudeAgentOptions) -> list[str]:
    """The argv for one task. Values use ``--flag=value`` so none can pose as a flag."""
    cli = options.cli_path or installer.cli_path()
    if cli is None:
        raise EngineError("Claude Code is not installed (no `claude` on PATH, no bundled CLI)")
    argv = [str(cli), "-p", "--output-format=stream-json", "--verbose"]

    def add(flag: str, value: object) -> None:
        argv.append(f"--{flag}={value}")

    if options.permission_mode:
        add("permission-mode", options.permission_mode)
    add("setting-sources", ",".join(options.setting_sources or []))
    if options.model:
        add("model", options.model)
    if options.max_turns:
        add("max-turns", options.max_turns)
    if options.max_budget_usd is not None:
        add("max-budget-usd", options.max_budget_usd)
    if options.effort:
        add("effort", options.effort)
    if options.allowed_tools:
        add("allowedTools", ",".join(options.allowed_tools))
    if options.disallowed_tools:
        add("disallowedTools", ",".join(options.disallowed_tools))
    for directory in options.add_dirs:
        add("add-dir", directory)
    return argv


def build_env(options: ClaudeAgentOptions) -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if k not in DROPPED_ENV}
    env.update({k: str(v) for k, v in dict(options.env).items()})
    return env


class ClaudeCliRun:
    """One ``claude -p`` process for one task."""

    def __init__(self, prompt: str, options: ClaudeAgentOptions) -> None:
        self.prompt = prompt
        self.options = options
        self.argv = build_command(options)
        self.mapper = EventMapper()
        self._proc: asyncio.subprocess.Process | None = None
        self._stderr: deque[str] = deque(maxlen=STDERR_LINES)
        self._result: EngineResult | None = None
        self._stopped = False

    @property
    def result(self) -> EngineResult:
        if self._result is not None:
            return self._result
        if self.mapper.result is not None:
            return self.mapper.result
        status = "stopped" if self._stopped else "failed"
        return self.mapper.unfinished(status, None if self._stopped else "no result reported")

    async def events(self) -> AsyncIterator[EngineEvent]:
        try:
            proc = await asyncio.create_subprocess_exec(
                *self.argv,
                cwd=str(self.options.cwd),
                env=build_env(self.options),
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                start_new_session=True,  # stop() signals the whole process group
                limit=LINE_LIMIT_BYTES,
            )
        except OSError as exc:
            self._result = self.mapper.unfinished("failed", f"cannot start {self.argv[0]}: {exc}")
            return
        self._proc = proc
        assert proc.stdin and proc.stdout and proc.stderr
        stderr = asyncio.create_task(self._drain(proc.stderr))
        try:
            with suppress(BrokenPipeError, ConnectionResetError):
                proc.stdin.write(self.prompt.encode())
                await proc.stdin.drain()
                proc.stdin.close()
            async for raw in proc.stdout:
                line = raw.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                except json.JSONDecodeError:
                    self._stderr.append(line.decode(errors="replace"))
                    continue
                if isinstance(data, dict):
                    for event in self.mapper.map_json(data):
                        yield event
            code = await proc.wait()
            await stderr
            if self.mapper.result is None and not self._stopped:
                detail = "\n".join(self._stderr).strip() or "no result reported"
                self._result = self.mapper.unfinished(
                    "failed", f"claude exited with code {code}: {detail}"
                )
        finally:
            await self._terminate()
            stderr.cancel()

    async def stop(self) -> None:
        self._stopped = True
        await self._terminate()

    async def _terminate(self) -> None:
        proc = self._proc
        if proc is None or proc.returncode is not None:
            return
        for sig in (signal.SIGTERM, signal.SIGKILL):
            with suppress(ProcessLookupError, PermissionError):
                os.killpg(proc.pid, sig)
            try:
                await asyncio.wait_for(proc.wait(), STOP_TIMEOUT_SECONDS)
                return
            except TimeoutError:
                continue

    async def _drain(self, stream: asyncio.StreamReader) -> None:
        async for raw in stream:
            text = raw.decode(errors="replace").rstrip()
            if text:
                self._stderr.append(text)
