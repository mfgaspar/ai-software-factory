from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest
from claude_agent_sdk import (
    AssistantMessage,
    CLIConnectionError,
    ResultMessage,
    SystemMessage,
    TextBlock,
    ToolResultBlock,
    ToolUseBlock,
    UserMessage,
)

from compose.engines.base import (
    EngineOptions,
    EngineTask,
    MessageEvent,
    ToolCallEvent,
    ToolResultEvent,
    Usage,
    UsageEvent,
)
from compose.engines.claude import adapter
from compose.engines.claude.adapter import ClaudeEngine, build_options, prompt_for
from compose.engines.claude.mapping import EventMapper
from compose.engines.registry import EngineError, default_registry


def usage(inp: int, out: int, read: int = 0, write: int = 0) -> dict[str, int]:
    return {
        "input_tokens": inp,
        "output_tokens": out,
        "cache_read_input_tokens": read,
        "cache_creation_input_tokens": write,
    }


def result(**overrides: Any) -> ResultMessage:
    fields: dict[str, Any] = {
        "subtype": "success",
        "duration_ms": 1200,
        "duration_api_ms": 900,
        "is_error": False,
        "num_turns": 2,
        "session_id": "sess-1",
        "total_cost_usd": 0.0123,
        "usage": usage(30, 12, 100, 40),
        "result": "All done.",
        "model_usage": {"claude-haiku-5-5": {}},
    }
    fields.update(overrides)
    return ResultMessage(**fields)


# A recorded-shape conversation: text + tool use, the tool result, a final answer.
CONVERSATION: list[object] = [
    SystemMessage(subtype="init", data={"session_id": "sess-1"}),
    AssistantMessage(
        content=[TextBlock("I'll create the file.")],
        model="claude-haiku-5-5",
        usage=usage(10, 5, 100, 40),
        message_id="m1",
        session_id="sess-1",
    ),
    AssistantMessage(  # same API message, next content block: usage repeated
        content=[ToolUseBlock("tu1", "Write", {"file_path": "hello.txt", "content": "hi"})],
        model="claude-haiku-5-5",
        usage=usage(10, 5, 100, 40),
        message_id="m1",
        session_id="sess-1",
    ),
    UserMessage(
        content=[ToolResultBlock("tu1", [{"type": "text", "text": "File created"}], False)]
    ),
    AssistantMessage(
        content=[TextBlock("All done.")],
        model="claude-haiku-5-5",
        usage=usage(20, 7),
        message_id="m2",
        session_id="sess-1",
    ),
    result(),
]


def test_mapping_a_conversation() -> None:
    ticks = iter([1.0, 1.25])
    mapper = EventMapper(clock=lambda: next(ticks))
    mapped = [e for m in CONVERSATION for e in mapper.map(m)]
    estimates = [e.usage.estimated_cost_usd for e in mapped if isinstance(e, UsageEvent)]
    assert 0 < estimates[0] <= estimates[1] < estimates[2]  # the live estimate grows...
    assert estimates[3] == 0.0  # ...and the result's real cost replaces it
    events = [  # the figures Claude reported, without the estimate
        UsageEvent(replace(e.usage, estimated_cost_usd=0.0)) if isinstance(e, UsageEvent) else e
        for e in mapped
    ]
    assert events[0] == MessageEvent("I'll create the file.")
    assert events[1] == UsageEvent(Usage(10, 5, 100, 40, 0.0, 1))
    assert events[2] == ToolCallEvent("tu1", "Write", {"file_path": "hello.txt", "content": "hi"})
    assert events[3] == UsageEvent(Usage(10, 5, 100, 40, 0.0, 1))  # not double counted
    assert events[4] == ToolResultEvent("tu1", "File created", is_error=False, duration_ms=250)
    assert events[5] == MessageEvent("All done.")
    assert events[6] == UsageEvent(Usage(30, 12, 100, 40, 0.0, 2))
    assert events[7] == UsageEvent(Usage(30, 12, 100, 40, 0.0123, 2))
    assert len(events) == 8

    final = mapper.result
    assert final is not None
    assert final.status == "completed"
    assert (final.session_id, final.final_text, final.duration_ms) == ("sess-1", "All done.", 1200)
    assert final.model == "claude-haiku-5-5"
    assert final.usage.cost_usd == 0.0123 and final.usage.turns == 2


def test_mapping_errors_and_odd_content() -> None:
    mapper = EventMapper(clock=lambda: 0.0)
    assert mapper.map(UserMessage(content="plain text")) == []
    tool_error = UserMessage(content=[ToolResultBlock("x", "denied", True)])
    assert mapper.map(tool_error) == [ToolResultEvent("x", "denied", is_error=True)]
    image = UserMessage(content=[ToolResultBlock("y", [{"type": "image", "data": "..."}])])
    (event,) = mapper.map(image)
    assert isinstance(event, ToolResultEvent) and '"type": "image"' in event.output

    mapper.map(
        result(
            is_error=True,
            subtype="error_max_turns",
            errors=["reached max turns"],
            result=None,
            usage=None,
            total_cost_usd=None,
        )
    )
    assert mapper.result is not None
    assert mapper.result.status == "failed"
    assert mapper.result.error == "error_max_turns: reached max turns"
    assert mapper.result.usage.cost_usd == 0.0

    unfinished = EventMapper().unfinished("stopped", None)
    assert unfinished.status == "stopped" and unfinished.usage == Usage()


def test_prompt_for_tasks() -> None:
    assert prompt_for(EngineTask.skill("compose-plan", "use postgres")) == (
        "/compose-plan use postgres"
    )
    assert prompt_for(EngineTask.skill("compose-tasks")) == "/compose-tasks"
    assert prompt_for(EngineTask.prompt("Summarize")) == "Summarize"


def test_build_options(tmp_path: Path) -> None:
    opts = build_options(
        tmp_path,
        EngineOptions(
            model="claude-sonnet-5-5",
            reasoning_effort="high",
            max_turns=7,
            max_cost_usd=2.5,
            env={"COMPOSE_RUN_ID": "run_1"},
        ),
    )
    assert opts.cwd == str(tmp_path)
    assert (opts.model, opts.effort, opts.max_turns, opts.max_budget_usd) == (
        "claude-sonnet-5-5",
        "high",
        7,
        2.5,
    )
    assert opts.permission_mode == "auto"
    assert opts.setting_sources == ["project"]
    assert opts.env == {"COMPOSE_RUN_ID": "run_1"}

    custom = build_options(
        tmp_path,
        EngineOptions(
            engine_options={
                "permission_mode": "bypassPermissions",
                "allowed_tools": ["Bash(npm test)", "Read"],
                "disallowed_tools": "WebFetch",
                "setting_sources": ["user", "project"],
            }
        ),
    )
    assert custom.permission_mode == "bypassPermissions"
    assert custom.allowed_tools == ["Bash(compose:*)", "Bash(npm test)", "Read"]
    assert custom.disallowed_tools == ["WebFetch"]
    assert custom.setting_sources == ["user", "project"]


@pytest.mark.parametrize(
    ("options", "message"),
    [
        (EngineOptions(engine_options={"colour": "red"}), "unknown Claude Code engine_options"),
        (EngineOptions(engine_options={"permission_mode": "yolo"}), "not a permission mode"),
        (EngineOptions(engine_options={"allowed_tools": 3}), "must be a list of strings"),
        (EngineOptions(engine_options={"setting_sources": ["team"]}), "setting_sources"),
        (EngineOptions(reasoning_effort="extreme"), "reasoning_effort 'extreme'"),
    ],
)
def test_build_options_rejects(tmp_path: Path, options: EngineOptions, message: str) -> None:
    with pytest.raises(EngineError, match=message):
        build_options(tmp_path, options)


def test_default_registry_has_claude() -> None:
    assert default_registry().names() == ["claude", "copilot"]


# ------------------------------------------------------------ run lifecycle


class FakeClient:
    """Stands in for ClaudeSDKClient: replays messages, records calls."""

    instances: list[FakeClient] = []
    messages: list[object] = CONVERSATION
    fail_on_connect: Exception | None = None
    hang: bool = False

    def __init__(self, options: Any) -> None:
        self.options = options
        self.calls: list[str] = []
        FakeClient.instances.append(self)

    async def connect(self) -> None:
        self.calls.append("connect")
        if self.fail_on_connect is not None:
            raise self.fail_on_connect

    async def query(self, prompt: str) -> None:
        self.calls.append(f"query:{prompt}")

    async def receive_response(self) -> AsyncIterator[object]:
        for message in self.messages:
            yield message
            if self.hang and isinstance(message, AssistantMessage):
                await asyncio.sleep(3600)

    async def interrupt(self) -> None:
        self.calls.append("interrupt")

    async def disconnect(self) -> None:
        self.calls.append("disconnect")


@pytest.fixture
def fake_client(monkeypatch: pytest.MonkeyPatch) -> type[FakeClient]:
    FakeClient.instances = []
    FakeClient.messages = CONVERSATION
    FakeClient.fail_on_connect = None
    FakeClient.hang = False
    monkeypatch.setattr(adapter, "ClaudeSDKClient", FakeClient)
    return FakeClient


async def test_run_streams_and_disconnects(tmp_path: Path, fake_client: type[FakeClient]) -> None:
    run = ClaudeEngine("sdk").start(
        EngineTask.skill("compose-plan", "x"), tmp_path, EngineOptions()
    )
    kinds = [e.kind async for e in run.events()]
    assert kinds.count("tool_call") == 1 and kinds[-1] == "usage_update"
    assert run.result.status == "completed" and run.result.usage.cost_usd == 0.0123
    assert fake_client.instances[0].calls == ["connect", "query:/compose-plan x", "disconnect"]


async def test_run_reports_sdk_errors(tmp_path: Path, fake_client: type[FakeClient]) -> None:
    fake_client.fail_on_connect = CLIConnectionError("no CLI")
    run = ClaudeEngine("sdk").start(EngineTask.prompt("hi"), tmp_path, EngineOptions())
    assert [e async for e in run.events()] == []
    assert run.result.status == "failed"
    assert run.result.error == "CLIConnectionError: no CLI"


async def test_stop_interrupts(tmp_path: Path, fake_client: type[FakeClient]) -> None:
    fake_client.hang = True
    run = ClaudeEngine("sdk").start(EngineTask.prompt("hi"), tmp_path, EngineOptions())
    events = run.events()
    first = await events.__anext__()
    assert first.kind == "message"
    await run.stop()
    assert run.result.status == "stopped"
    assert fake_client.instances[0].calls[-2:] == ["interrupt", "disconnect"]
    await events.aclose()  # closing afterwards doesn't disconnect twice
    assert fake_client.instances[0].calls.count("disconnect") == 1
