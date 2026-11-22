"""Turn Claude Agent SDK messages into compose engine events and a final result."""

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


def _tool_output(content: str | list[dict[str, Any]] | None) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    parts: list[str] = []
    for item in content:
        if item.get("type") == "text":
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
        if isinstance(message, AssistantMessage):
            return self._assistant(message)
        if isinstance(message, UserMessage):
            return self._user(message)
        if isinstance(message, ResultMessage):
            return self._result(message)
        return []  # system and stream messages carry nothing compose records

    def _assistant(self, message: AssistantMessage) -> list[EngineEvent]:
        events: list[EngineEvent] = []
        self.model = message.model or self.model
        self.session_id = message.session_id or self.session_id
        for block in message.content:
            if isinstance(block, TextBlock) and block.text.strip():
                self.last_text = block.text
                events.append(MessageEvent(block.text))
            elif isinstance(block, ToolUseBlock):
                self._started[block.id] = self.clock()
                events.append(ToolCallEvent(block.id, block.name, dict(block.input)))
        if message.usage is not None:
            key = message.message_id or f"anon-{len(self._usage)}"
            self._usage[key] = _MessageUsage(
                input_tokens=_int(message.usage, "input_tokens"),
                output_tokens=_int(message.usage, "output_tokens"),
                cache_read_tokens=_int(message.usage, "cache_read_input_tokens"),
                cache_write_tokens=_int(message.usage, "cache_creation_input_tokens"),
            )
            events.append(UsageEvent(self.usage()))
        return events

    def _user(self, message: UserMessage) -> list[EngineEvent]:
        if isinstance(message.content, str):
            return []
        events: list[EngineEvent] = []
        for block in message.content:
            if isinstance(block, ToolResultBlock):
                started = self._started.pop(block.tool_use_id, None)
                duration = None if started is None else int((self.clock() - started) * 1000)
                events.append(
                    ToolResultEvent(
                        block.tool_use_id,
                        _tool_output(block.content),
                        is_error=bool(block.is_error),
                        duration_ms=duration,
                    )
                )
        return events

    def _result(self, message: ResultMessage) -> list[EngineEvent]:
        """The result's figures are authoritative (they include subagents and retries)."""
        data = message.usage or {}
        totals = self.usage()
        if data:
            totals = Usage(
                input_tokens=_int(data, "input_tokens"),
                output_tokens=_int(data, "output_tokens"),
                cache_read_tokens=_int(data, "cache_read_input_tokens"),
                cache_write_tokens=_int(data, "cache_creation_input_tokens"),
            )
        usage = Usage(
            input_tokens=totals.input_tokens,
            output_tokens=totals.output_tokens,
            cache_read_tokens=totals.cache_read_tokens,
            cache_write_tokens=totals.cache_write_tokens,
            cost_usd=float(message.total_cost_usd or 0.0),
            turns=message.num_turns,
        )
        model = next(iter(message.model_usage or {}), None) or self.model
        error: str | None = None
        if message.is_error:
            details = "; ".join(message.errors or []) or message.result or ""
            error = f"{message.subtype}: {details}" if details else message.subtype
        self.result = EngineResult(
            status="failed" if message.is_error else "completed",
            usage=usage,
            session_id=message.session_id,
            final_text=message.result if message.result is not None else self.last_text,
            duration_ms=message.duration_ms,
            error=error,
            model=model,
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
