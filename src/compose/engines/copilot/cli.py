"""GitHub Copilot driven as a command: ``copilot --output-format=json``.

The prompt goes in on stdin (so its size and content never touch argv) and every line of
output is a JSON event, mapped by :class:`CopilotMapper`. The closing ``result`` line
carries the exit code; tokens and AI credits come from the usage checkpoint before it.
"""

from __future__ import annotations

import asyncio
import json
import os
from collections import deque
from collections.abc import AsyncIterator
from contextlib import suppress
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from compose.core import procs
from compose.engines.base import EngineEvent, EngineResult, Transcript
from compose.engines.copilot import install as installer
from compose.engines.copilot.mapping import CopilotMapper
from compose.engines.registry import EngineError

STOP_TIMEOUT_SECONDS = 10.0
LINE_LIMIT_BYTES = 64 * 1024 * 1024  # one JSON line can hold a large tool result
STDERR_LINES = 20

# how each permission mode is asked for on the command line
PERMISSION_FLAGS: dict[str, list[str]] = {
    "assisted": ["--assisted-approval"],
    # tools and paths: a headless run cannot answer "may I work outside the worktree?"
    "allow-all": ["--allow-all-tools", "--allow-all-paths"],
    "rules": [],
}


@dataclass(frozen=True)
class CopilotOptions:
    """Everything one ``copilot`` process is started with."""

    cwd: Path
    permission_mode: str = "allow-all"
    model: str | None = None
    reasoning_effort: str | None = None
    max_ai_credits: int | None = None
    allowed_tools: list[str] = field(default_factory=list)
    disallowed_tools: list[str] = field(default_factory=list)
    allowed_urls: list[str] = field(default_factory=list)
    add_dirs: list[str] = field(default_factory=list)
    cli_path: str | None = None
    env: dict[str, str] = field(default_factory=dict)


def build_command(options: CopilotOptions) -> list[str]:
    """The argv for one task. Values use ``--flag=value`` so none can pose as a flag."""
    cli = options.cli_path or installer.cli_path()
    if cli is None:
        raise EngineError("GitHub Copilot CLI is not installed (no `copilot` on PATH)")
    argv = [
        str(cli),
        "--output-format=json",
        "--stream=off",  # whole messages; no partial-text lines
        "--no-color",
        "--no-ask-user",  # nobody is there to answer a question form
        "--no-auto-update",
        "--trust-folder",  # load the worktree's skills and instructions, for this run only
        *PERMISSION_FLAGS[options.permission_mode],
    ]

    def add(flag: str, value: object) -> None:
        argv.append(f"--{flag}={value}")

    if options.model:
        add("model", options.model)
    if options.reasoning_effort:
        add("reasoning-effort", options.reasoning_effort)
    if options.max_ai_credits is not None:
        add("max-ai-credits", options.max_ai_credits)
    for rule in options.allowed_tools:
        add("allow-tool", rule)
    for rule in options.disallowed_tools:
        add("deny-tool", rule)
    for url in options.allowed_urls:
        add("allow-url", url)
    for directory in options.add_dirs:
        add("add-dir", directory)
    return argv


def task_entry(prompt: str, options: CopilotOptions, argv: list[str]) -> dict[str, Any]:
    """The transcript's first line: what compose asked, where and how."""
    return {
        "type": "compose_task",
        "transport": "copilot",
        "prompt": prompt,
        "cwd": str(options.cwd),
        "permission_mode": options.permission_mode,
        "model": options.model,
        "allowed_tools": list(options.allowed_tools),
        "disallowed_tools": list(options.disallowed_tools),
        "argv": argv,
    }


def result_entry(result: EngineResult) -> dict[str, Any]:
    """The transcript's last line: how the run ended, in compose's terms. Copilot's own
    ``result`` line has no turns, cost or error text."""
    return {
        "type": "compose_result",
        "status": result.status,
        "turns": result.usage.turns,
        "cost_usd": result.usage.cost_usd,
        "duration_ms": result.duration_ms,
        "error": result.error,
        "session_id": result.session_id,
    }


def build_env(options: CopilotOptions) -> dict[str, str]:
    return {**os.environ, **{k: str(v) for k, v in options.env.items()}}


class CopilotRun:
    """One ``copilot`` process for one task."""

    def __init__(
        self, prompt: str, options: CopilotOptions, transcript: Transcript | None = None
    ) -> None:
        self.prompt = prompt
        self.options = options
        self.transcript = transcript or Transcript(None)
        self.argv = build_command(options)
        self.mapper = CopilotMapper()
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
                limit=LINE_LIMIT_BYTES,
                **procs.group_kwargs(),  # stop() signals the whole process group
            )
        except OSError as exc:
            self._result = self.mapper.unfinished("failed", f"cannot start {self.argv[0]}: {exc}")
            return
        self._proc = proc
        self.transcript.write(task_entry(self.prompt, self.options, self.argv))
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
                self.transcript.write_raw(line.decode(errors="replace"))  # exactly as printed
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
                said = [*self.mapper.errors, *self._stderr]
                detail = "\n".join(said).strip() or "no result reported"
                self._result = self.mapper.unfinished(
                    "failed", f"copilot exited with code {code}: {detail}"
                )
        finally:
            await self._terminate()
            stderr.cancel()
            if self._stderr:
                self.transcript.write({"type": "compose_stderr", "lines": list(self._stderr)})
            self.transcript.write(result_entry(self.result))

    async def stop(self) -> None:
        self._stopped = True
        await self._terminate()

    async def _terminate(self) -> None:
        proc = self._proc
        if proc is not None:
            await procs.stop_tree(proc, STOP_TIMEOUT_SECONDS)

    async def _drain(self, stream: asyncio.StreamReader) -> None:
        async for raw in stream:
            text = raw.decode(errors="replace").rstrip()
            if text:
                self._stderr.append(text)
