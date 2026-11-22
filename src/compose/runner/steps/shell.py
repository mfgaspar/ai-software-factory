"""``shell`` steps: run a command in the feature worktree."""

from __future__ import annotations

import asyncio
import json
import os
import signal
from contextlib import suppress
from typing import TYPE_CHECKING

from compose.core.models import StepExec
from compose.runner.context import Scope
from compose.runner.steps.base import Outcome
from compose.workflows.schema import ShellStep

if TYPE_CHECKING:
    from compose.runner.runner import RunContext


def _truncate(data: bytes, limit: int) -> str:
    text = data[:limit].decode(errors="replace")
    return text + ("\n[truncated]" if len(data) > limit else "")


async def run_shell(rc: RunContext, command: str, env: dict[str, str]) -> tuple[int, bytes, bytes]:
    """Run ``command`` in the worktree; kill its process group if cancelled."""
    proc = await asyncio.create_subprocess_shell(
        command,
        cwd=rc.worktree,
        env={**os.environ, **rc.env(), **env},
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        start_new_session=True,
    )
    try:
        out, err = await proc.communicate()
    except BaseException:
        with suppress(ProcessLookupError):
            os.killpg(proc.pid, signal.SIGKILL)
        with suppress(Exception):
            await proc.wait()
        raise
    return proc.returncode or 0, out, err


async def execute(rc: RunContext, step: ShellStep, row: StepExec, scope: Scope) -> Outcome:
    command = step.run if step.strict else rc.render_text(step.run, scope)
    env = {key: rc.render_text(value, scope) for key, value in step.env.items()}
    rc.record_action(row.id, None, kind="tool_call", tool_name="shell", input_summary=command)
    code, out, err = await run_shell(rc, command, env)
    output: dict[str, object] = {"exit_code": code}
    if step.capture:
        output["stdout"] = _truncate(out, step.capture_max_bytes)
        output["stderr"] = _truncate(err, step.capture_max_bytes)
    rc.record_action(
        row.id,
        None,
        kind="tool_result",
        tool_name="shell",
        result_summary=f"exit {code}\n{_truncate(out + err, 500)}",
        is_error=code != 0,
    )
    if step.output_format == "json" and code == 0:
        try:
            output["data"] = json.loads(out.decode() or "null")
        except json.JSONDecodeError as exc:
            return Outcome.failed(f"output is not valid JSON: {exc}", **output)
    if code != 0:
        return Outcome.failed(f"exit code {code}", **output)
    return Outcome.ok(**output)
