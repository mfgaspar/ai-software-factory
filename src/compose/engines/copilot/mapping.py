"""Turn GitHub Copilot CLI output into compose engine events and a final result.

``copilot --output-format json`` prints one JSON object per line: ``{"type": ..., "data":
{...}}``. The ones compose records are ``assistant.message`` (text), ``tool.execution_start``
and ``tool.execution_complete`` (tool calls and their results), ``assistant.turn_end`` (a
turn), ``session.usage_checkpoint`` (tokens and AI credits so far), ``session.error`` and the
closing ``result`` line (exit code, session id, duration).

Copilot bills in AI credits. One credit is one US cent, so costs and budgets convert both
ways. On the legacy premium-request plans Copilot reports no credits and the cost stays 0.
"""

from __future__ import annotations

import json
import math
import re
import time
from dataclasses import dataclass, field
from typing import Any

from compose.engines.base import (
    EngineEvent,
    EngineResult,
    MessageEvent,
    ThinkingEvent,
    ToolCallEvent,
    ToolResultEvent,
    Usage,
    UsageEvent,
)

CREDIT_USD = 0.01  # GitHub's price for one AI credit
NANO = 1_000_000_000  # Copilot counts in billionths of a credit
MIN_SESSION_CREDITS = 30  # the smallest cap --max-ai-credits accepts


def credits_for(usd: float) -> int:
    """A budget in dollars as a session cap in AI credits (never under Copilot's minimum)."""
    return max(math.ceil(usd / CREDIT_USD - 1e-9), MIN_SESSION_CREDITS)


def _dict(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _count(details: dict[str, Any], key: str) -> int:
    value = _dict(details.get(key)).get("tokenCount")
    return int(value) if isinstance(value, int | float) else 0


_PATCHED = re.compile(r"^\*\*\* (Add|Update|Delete) File: (.+?)\s*$", re.MULTILINE)


def patch_calls(call_id: str, patch: str) -> list[ToolCallEvent]:
    """``apply_patch`` sends one patch text for any number of files; report each file as a
    write (``create`` or ``edit``) so progress counts and names them."""
    calls = []
    for n, (action, path) in enumerate(_PATCHED.findall(patch)):
        name = "create" if action == "Add" else "edit"
        calls.append(ToolCallEvent(call_id if n == 0 else f"{call_id}#{n}", name, {"path": path}))
    return calls


def tool_output(data: dict[str, Any]) -> str:
    """What a finished tool call returned: its content, or why it failed."""
    content = _dict(data.get("result")).get("content")
    if content is None:
        content = _dict(data.get("error")).get("message")
    if content is None:
        return ""
    return content if isinstance(content, str) else json.dumps(content, default=str)


@dataclass
class CopilotMapper:
    """Stateful: keeps running usage and tool timings across one Copilot run."""

    clock: Any = time.monotonic
    model: str | None = None
    session_id: str | None = None
    last_text: str = ""
    turns: int = 0
    credits: float = 0.0
    errors: list[str] = field(default_factory=list)
    result: EngineResult | None = None
    _tokens: dict[str, int] = field(default_factory=dict)
    _started: dict[str, float] = field(default_factory=dict)

    def usage(self) -> Usage:
        return Usage(
            input_tokens=self._tokens.get("input", 0),
            output_tokens=self._tokens.get("output", 0),
            cache_read_tokens=self._tokens.get("cache_read", 0),
            cache_write_tokens=self._tokens.get("cache_write", 0),
            cost_usd=self.credits * CREDIT_USD,
            turns=self.turns,
        )

    def map_json(self, line: dict[str, Any]) -> list[EngineEvent]:
        """Map one line of ``copilot --output-format json``."""
        kind = line.get("type")
        data = _dict(line.get("data"))
        if kind == "result":
            return self._result(line)
        if kind == "session.start":
            self.session_id = data.get("sessionId") or self.session_id
        elif kind == "session.model_change":
            self.model = data.get("newModel") or self.model
        elif kind == "session.error":
            self.errors.append(str(data.get("message") or data.get("errorType") or "error"))
        elif kind == "assistant.message":
            self.model = data.get("model") or self.model
            events: list[EngineEvent] = []
            thought = str(data.get("reasoningText") or "")
            if thought.strip():
                events.append(ThinkingEvent(thought))
            text = str(data.get("content") or "")
            if text.strip():
                self.last_text = text
                events.append(MessageEvent(text))
            return events
        elif kind == "assistant.reasoning":
            thought = str(data.get("content") or "")
            if thought.strip():
                return [ThinkingEvent(thought)]
        elif kind == "tool.execution_start":
            call_id = str(data.get("toolCallId", ""))
            self._started[call_id] = self.clock()
            name, arguments = str(data.get("toolName", "")), data.get("arguments")
            if isinstance(arguments, str) and name == "apply_patch":
                calls = patch_calls(call_id, arguments)
                if calls:
                    return list(calls)
            return [ToolCallEvent(call_id, name, _dict(arguments))]
        elif kind == "tool.execution_complete":
            call_id = str(data.get("toolCallId", ""))
            started = self._started.pop(call_id, None)
            return [
                ToolResultEvent(
                    call_id,
                    tool_output(data),
                    is_error=data.get("success") is False,
                    duration_ms=None if started is None else int((self.clock() - started) * 1000),
                )
            ]
        elif kind == "assistant.turn_end":
            self.turns += 1
            return [UsageEvent(self.usage())]
        elif kind == "session.usage_checkpoint":
            return self._checkpoint(data)
        return []  # session bookkeeping carries nothing compose records

    def _checkpoint(self, data: dict[str, Any]) -> list[EngineEvent]:
        """Totals for the session so far, subagents included."""
        snapshot = _dict(data.get("accountingSnapshot"))
        details = _dict(snapshot.get("tokenDetails"))
        if details:
            self._tokens = {
                key: _count(details, key)
                for key in ("input", "output", "cache_read", "cache_write")
            }
        nano = data.get("totalNanoAiu", snapshot.get("totalNanoAiu"))
        if isinstance(nano, int | float):
            self.credits = nano / NANO
        return [UsageEvent(self.usage())]

    def _result(self, line: dict[str, Any]) -> list[EngineEvent]:
        code = line.get("exitCode")
        failed = code != 0
        duration = _dict(line.get("usage")).get("sessionDurationMs")
        self.session_id = line.get("sessionId") or self.session_id
        error: str | None = None
        if failed:
            error = "; ".join(self.errors) or f"copilot exited with code {code}"
        self.result = EngineResult(
            status="failed" if failed else "completed",
            usage=self.usage(),
            session_id=self.session_id,
            final_text=self.last_text,
            duration_ms=int(duration) if isinstance(duration, int | float) else 0,
            error=error,
            model=self.model,
        )
        return [UsageEvent(self.result.usage)]

    def unfinished(self, status: str, error: str | None) -> EngineResult:
        """The result when Copilot stopped or broke before reporting one."""
        return EngineResult(
            status="stopped" if status == "stopped" else "failed",
            usage=self.usage(),
            session_id=self.session_id,
            final_text=self.last_text,
            error=error,
            model=self.model,
        )
