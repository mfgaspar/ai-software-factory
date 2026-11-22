"""Turn Claude Code output into compose engine events and a final result.

Two sources share one mapping: Claude Agent SDK messages and the JSON lines of
``claude -p --output-format stream-json``, which carry the same fields.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any

from claude_agent_sdk import (
    AssistantMessage,
    ResultMessage,
    TextBlock,
    ToolResultBlock,
    ToolUseBlock,
    UserMessage,
)

from compose.engines.base import (
    EngineEvent,
    EngineResult,
    MessageEvent,
    ToolCallEvent,
    ToolResultEvent,
    Usage,
    UsageEvent,
)


def _int(data: dict[str, Any] | None, key: str) -> int:
    value = (data or {}).get(key)
    return int(value) if isinstance(value, int | float) else 0


def _tool_output(content: object) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return json.dumps(content, default=str)
    parts: list[str] = []
    for item in content:
        if isinstance(item, dict) and item.get("type") == "text":
            parts.append(str(item.get("text", "")))
        else:
            parts.append(json.dumps(item, default=str))
    return "\n".join(parts)


@dataclass
class _MessageUsage:
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0


@dataclass
class EventMapper:
    """Stateful: keeps running usage and tool timings across one engine run.

    The SDK repeats an assistant message's usage on every content block of that message,
    so usage is kept per message id and summed.
    """

    clock: Any = time.monotonic
    _usage: dict[str, _MessageUsage] = field(default_factory=dict)
    _started: dict[str, float] = field(default_factory=dict)
    model: str | None = None
    session_id: str | None = None
    last_text: str = ""
    result: EngineResult | None = None

    def usage(self, cost_usd: float = 0.0, turns: int | None = None) -> Usage:
        values = list(self._usage.values())
        return Usage(
            input_tokens=sum(u.input_tokens for u in values),
            output_tokens=sum(u.output_tokens for u in values),
            cache_read_tokens=sum(u.cache_read_tokens for u in values),
            cache_write_tokens=sum(u.cache_write_tokens for u in values),
            cost_usd=cost_usd,
            turns=len(values) if turns is None else turns,
        )

    def map(self, message: object) -> list[EngineEvent]:
        """Map a Claude Agent SDK message."""
        if isinstance(message, AssistantMessage):
            blocks: list[dict[str, Any]] = []
            for block in message.content:
                if isinstance(block, TextBlock):
                    blocks.append({"type": "text", "text": block.text})
                elif isinstance(block, ToolUseBlock):
                    blocks.append(
                        {
                            "type": "tool_use",
                            "id": block.id,
                            "name": block.name,
                            "input": block.input,
                        }
                    )
            return self._assistant(
                blocks, message.usage, message.message_id, message.model, message.session_id
            )
        if isinstance(message, UserMessage):
            if isinstance(message.content, str):
                return []
            return self._tool_results(
                [
                    {"tool_use_id": b.tool_use_id, "content": b.content, "is_error": b.is_error}
                    for b in message.content
                    if isinstance(b, ToolResultBlock)
                ]
            )
        if isinstance(message, ResultMessage):
            return self._result(
                {
                    "subtype": message.subtype,
                    "is_error": message.is_error,
                    "duration_ms": message.duration_ms,
                    "num_turns": message.num_turns,
                    "session_id": message.session_id,
                    "total_cost_usd": message.total_cost_usd,
                    "usage": message.usage,
                    "result": message.result,
                    "modelUsage": message.model_usage,
                    "errors": message.errors,
                }
            )
        return []  # system and stream messages carry nothing compose records

    def map_json(self, line: dict[str, Any]) -> list[EngineEvent]:
        """Map one line of ``claude -p --output-format stream-json --verbose``."""
        kind = line.get("type")
        if kind == "system" and line.get("subtype") == "init":
            self.model = line.get("model") or self.model
            self.session_id = line.get("session_id") or self.session_id
            return []
        message = line.get("message")
        if not isinstance(message, dict):
            return self._result(line) if kind == "result" else []
        content = message.get("content")
        if kind == "assistant" and isinstance(content, list):
            return self._assistant(
                [b for b in content if isinstance(b, dict)],
                message.get("usage"),
                message.get("id"),
                message.get("model"),
                line.get("session_id"),
            )
        if kind == "user" and isinstance(content, list):
            return self._tool_results(
                [b for b in content if isinstance(b, dict) and b.get("type") == "tool_result"]
            )
        return []

    def _assistant(
        self,
        blocks: list[dict[str, Any]],
        usage: dict[str, Any] | None,
        message_id: str | None,
        model: str | None,
        session_id: str | None,
    ) -> list[EngineEvent]:
        events: list[EngineEvent] = []
        self.model = model or self.model
        self.session_id = session_id or self.session_id
        for block in blocks:
            if block.get("type") == "text":
                text = str(block.get("text") or "")
                if text.strip():
                    self.last_text = text
                    events.append(MessageEvent(text))
            elif block.get("type") == "tool_use":
                call_id = str(block.get("id", ""))
                tool_input = block.get("input")
                self._started[call_id] = self.clock()
                events.append(
                    ToolCallEvent(
                        call_id,
                        str(block.get("name", "")),
                        dict(tool_input) if isinstance(tool_input, dict) else {},
                    )
                )
        if usage is not None:
            key = message_id or f"anon-{len(self._usage)}"
            self._usage[key] = _MessageUsage(
                input_tokens=_int(usage, "input_tokens"),
                output_tokens=_int(usage, "output_tokens"),
                cache_read_tokens=_int(usage, "cache_read_input_tokens"),
                cache_write_tokens=_int(usage, "cache_creation_input_tokens"),
            )
            events.append(UsageEvent(self.usage()))
        return events

    def _tool_results(self, blocks: list[dict[str, Any]]) -> list[EngineEvent]:
        events: list[EngineEvent] = []
        for block in blocks:
            call_id = str(block.get("tool_use_id", ""))
            started = self._started.pop(call_id, None)
            duration = None if started is None else int((self.clock() - started) * 1000)
            events.append(
                ToolResultEvent(
                    call_id,
                    _tool_output(block.get("content")),
                    is_error=bool(block.get("is_error")),
                    duration_ms=duration,
                )
            )
        return events

    def _result(self, data: dict[str, Any]) -> list[EngineEvent]:
        """The result's figures are authoritative (they include subagents and retries)."""
        raw = data.get("usage")
        totals = self.usage()
        if isinstance(raw, dict) and raw:
            totals = Usage(
                input_tokens=_int(raw, "input_tokens"),
                output_tokens=_int(raw, "output_tokens"),
                cache_read_tokens=_int(raw, "cache_read_input_tokens"),
                cache_write_tokens=_int(raw, "cache_creation_input_tokens"),
            )
        turns = data.get("num_turns")
        usage = Usage(
            input_tokens=totals.input_tokens,
            output_tokens=totals.output_tokens,
            cache_read_tokens=totals.cache_read_tokens,
            cache_write_tokens=totals.cache_write_tokens,
            cost_usd=float(data.get("total_cost_usd") or 0.0),
            turns=int(turns) if isinstance(turns, int) else totals.turns,
        )
        model_usage = data.get("modelUsage")
        model = next(iter(model_usage), None) if isinstance(model_usage, dict) else None
        subtype = str(data.get("subtype") or "error")
        is_error = bool(data.get("is_error"))
        error: str | None = None
        if is_error:
            errors = [str(e) for e in data.get("errors") or []]
            details = "; ".join(errors) or str(data.get("result") or "")
            error = f"{subtype}: {details}" if details else subtype
        result = data.get("result")
        duration = data.get("duration_ms")
        self.result = EngineResult(
            status="failed" if is_error else "completed",
            usage=usage,
            session_id=data.get("session_id") or self.session_id,
            final_text=str(result) if result is not None else self.last_text,
            duration_ms=int(duration) if isinstance(duration, int | float) else 0,
            error=error,
            model=model or self.model,
        )
        return [UsageEvent(usage)]

    def unfinished(self, status: str, error: str | None) -> EngineResult:
        """The result when the engine stopped or broke before reporting one."""
        return EngineResult(
            status="stopped" if status == "stopped" else "failed",
            usage=self.usage(),
            session_id=self.session_id,
            final_text=self.last_text,
            error=error,
            model=self.model,
        )
