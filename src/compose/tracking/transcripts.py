"""The engine's whole session for each step, kept as files in the run folder.

Each engine execution (a step or a hook) appends its session to
``runs/<run>/steps/<exec id>.transcript.jsonl``: a first ``compose_task`` line (the prompt,
the working folder, the permission mode, the allowed tools), then every line the engine
printed, exactly as printed: Claude Code's stream-json lines (with the SDK transport, its
messages in the same shape) or the Copilot CLI's JSON lines, which end with a
``compose_result`` line. It is the complete record: thinking, messages, every tool call
with its whole input and result, permission refusals and the final result. The database
keeps only summaries.

:func:`entries` reads one back as a flat list a person (or ``compose trace --full``) can
follow.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from compose.core.home import Home
from compose.engines.copilot.mapping import tool_output
from compose.runner.state import RunFiles


def path(home: Home, run_id: str, exec_id: str) -> Path:
    return RunFiles(home.run_dir(run_id)).transcript(exec_id)


def _text(content: object) -> str:
    """A tool result's content as text (a string, or a list of text and other parts)."""
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(
            str(part.get("text", ""))
            if isinstance(part, dict) and part.get("type") == "text"
            else json.dumps(part, default=str)
            for part in content
        )
    return json.dumps(content, default=str)


def _is_copilot(line: dict[str, Any]) -> bool:
    """Copilot's event names are dotted (``assistant.message``); its last line is a
    ``result`` with an exit code."""
    kind = line.get("type")
    return isinstance(kind, str) and ("." in kind or (kind == "result" and "exitCode" in line))


def _from_copilot(line: dict[str, Any]) -> list[dict[str, Any]]:
    kind = line.get("type")
    data = line.get("data")
    data = data if isinstance(data, dict) else {}
    if kind == "session.start":
        context = data.get("context")
        return [
            {
                "kind": "session",
                "session_id": data.get("sessionId"),
                "model": None,  # chosen after the session starts
                "permission_mode": None,
                "cwd": context.get("cwd") if isinstance(context, dict) else None,
                "tools": [],
                "copilot_version": data.get("copilotVersion"),
            }
        ]
    if kind == "user.message":
        return [{"kind": "message", "role": "user", "text": data.get("content")}]
    if kind == "assistant.message":
        found: list[dict[str, Any]] = []
        if data.get("reasoningText"):
            found.append({"kind": "thinking", "text": data.get("reasoningText")})
        if str(data.get("content") or "").strip():
            found.append({"kind": "message", "role": "assistant", "text": data.get("content")})
        for request in data.get("toolRequests") or []:
            if isinstance(request, dict):
                found.append(
                    {
                        "kind": "tool_call",
                        "id": request.get("toolCallId"),
                        "name": request.get("name"),
                        "input": request.get("arguments"),
                    }
                )
        return found
    if kind == "tool.execution_complete":
        return [
            {
                "kind": "tool_result",
                "id": data.get("toolCallId"),
                "output": tool_output(data),
                "is_error": data.get("success") is False,
            }
        ]
    if kind == "session.error":
        return [{"kind": "error", "text": data.get("message") or data.get("errorType")}]
    # the rest is bookkeeping; compose's own closing line reports the result
    return [{"kind": "system", "subtype": kind, "data": line}]


def _from_line(line: dict[str, Any]) -> list[dict[str, Any]]:
    kind = line.get("type")
    parent = line.get("parent_tool_use_id")
    extra = {"parent": parent} if parent else {}
    if kind == "compose_task":
        return [{"kind": "task", **{k: v for k, v in line.items() if k != "type"}}]
    if kind == "compose_stderr":
        return [{"kind": "stderr", "text": "\n".join(line.get("lines") or [])}]
    if kind == "compose_result":
        return [
            {
                "kind": "result",
                "subtype": line.get("status"),
                "is_error": line.get("status") != "completed",
                "turns": line.get("turns"),
                "cost_usd": line.get("cost_usd"),
                "duration_ms": line.get("duration_ms"),
                "text": None,
                "permission_denials": [],
                "errors": [line["error"]] if line.get("error") else [],
                "session_id": line.get("session_id"),
            }
        ]
    if _is_copilot(line):
        return _from_copilot(line)
    if kind == "system":
        if line.get("subtype") == "init":
            return [
                {
                    "kind": "session",
                    "session_id": line.get("session_id"),
                    "model": line.get("model"),
                    "permission_mode": line.get("permissionMode"),
                    "cwd": line.get("cwd"),
                    "tools": line.get("tools") or [],
                    "claude_code_version": line.get("claude_code_version"),
                }
            ]
        return [{"kind": "system", "subtype": line.get("subtype"), "data": line}]
    if kind in ("assistant", "user"):
        message = line.get("message") or {}
        content = message.get("content")
        if isinstance(content, str):
            return [{"kind": "message", "role": kind, "text": content, **extra}]
        found: list[dict[str, Any]] = []
        for block in content or []:
            if not isinstance(block, dict):
                continue
            btype = block.get("type")
            if btype == "text":
                found.append({"kind": "message", "role": kind, "text": block.get("text"), **extra})
            elif btype == "thinking":
                found.append({"kind": "thinking", "text": block.get("thinking"), **extra})
            elif btype == "tool_use":
                found.append(
                    {
                        "kind": "tool_call",
                        "id": block.get("id"),
                        "name": block.get("name"),
                        "input": block.get("input"),
                        **extra,
                    }
                )
            elif btype == "tool_result":
                found.append(
                    {
                        "kind": "tool_result",
                        "id": block.get("tool_use_id"),
                        "output": _text(block.get("content")),
                        "is_error": bool(block.get("is_error")),
                        **extra,
                    }
                )
        return found
    if kind == "result":
        return [
            {
                "kind": "result",
                "subtype": line.get("subtype"),
                "is_error": bool(line.get("is_error")),
                "turns": line.get("num_turns"),
                "cost_usd": line.get("total_cost_usd"),
                "duration_ms": line.get("duration_ms"),
                "text": line.get("result"),
                "permission_denials": line.get("permission_denials") or [],
                "errors": line.get("errors") or [],
                "session_id": line.get("session_id"),
            }
        ]
    return [{"kind": str(kind or "unknown"), "data": line}]


def entries(file: Path) -> list[dict[str, Any]]:
    """Everything in one transcript, in order; [] when there is none. A line that isn't
    JSON (a write cut short by a kill) comes back as a ``raw`` entry."""
    if not file.is_file():
        return []
    found: list[dict[str, Any]] = []
    for raw in file.read_text(encoding="utf-8", errors="replace").splitlines():
        if not raw.strip():
            continue
        try:
            line = json.loads(raw)
        except json.JSONDecodeError:
            found.append({"kind": "raw", "text": raw})
            continue
        if isinstance(line, dict):
            found.extend(_from_line(line))
    return found
