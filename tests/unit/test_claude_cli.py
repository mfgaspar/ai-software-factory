"""The Claude Code CLI transport: ``claude -p --output-format stream-json``."""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Any

import pytest

from compose.core.config import Config
from compose.engines.base import EngineOptions, EngineTask, ToolCallEvent, ToolResultEvent
from compose.engines.claude.adapter import ClaudeEngine, ClaudeRun, build_options
from compose.engines.claude.cli import ClaudeCliRun, build_command, build_env
from compose.engines.claude.mapping import EventMapper
from compose.engines.registry import EngineError

USAGE = {
    "input_tokens": 4,
    "output_tokens": 50,
    "cache_read_input_tokens": 100,
    "cache_creation_input_tokens": 20,
}

# The shape Claude Code prints (trimmed), including lines compose ignores.
STREAM: list[dict[str, Any]] = [
    {"type": "system", "subtype": "init", "session_id": "s-1", "model": "claude-haiku-5-5"},
    {
        "type": "assistant",
        "session_id": "s-1",
        "parent_tool_use_id": None,
        "message": {
            "id": "msg_1",
            "model": "claude-haiku-5-5",
            "content": [
                {"type": "thinking", "thinking": "..."},
                {"type": "text", "text": "Reading it."},
                {"type": "tool_use", "id": "tu_1", "name": "Read", "input": {"file_path": "a"}},
            ],
            "usage": {"input_tokens": 2, "output_tokens": 30, "cache_read_input_tokens": 50},
        },
    },
    {"type": "rate_limit_event", "rate_limit_info": {}, "session_id": "s-1"},
    {
        "type": "user",
        "session_id": "s-1",
        "message": {
            "role": "user",
            "content": [{"type": "tool_result", "tool_use_id": "tu_1", "content": "hello"}],
        },
        "tool_use_result": {"type": "text"},
    },
    {
        "type": "assistant",
        "session_id": "s-1",
        "message": {
            "id": "msg_2",
            "model": "claude-haiku-5-5",
            "content": [{"type": "text", "text": "It says hello."}],
            "usage": {"input_tokens": 2, "output_tokens": 20, "cache_read_input_tokens": 50},
        },
    },
    {"type": "system", "subtype": "post_turn_summary", "session_id": "s-1"},
    {
        "type": "result",
        "subtype": "success",
        "is_error": False,
        "duration_ms": 2981,
        "num_turns": 2,
        "result": "It says hello.",
        "session_id": "s-1",
        "total_cost_usd": 0.0024,
        "usage": USAGE,
        "modelUsage": {"claude-haiku-5-5": {"costUSD": 0.0024}},
    },
    {"type": "system", "subtype": "task_summary", "session_id": "s-1"},
]


# ------------------------------------------------------------------ mapping


def test_maps_stream_json_lines() -> None:
    ticks = iter([0.0, 0.25])
    mapper = EventMapper(clock=lambda: next(ticks))
    events = [e for line in STREAM for e in mapper.map_json(line)]
    assert [e.kind for e in events] == [
        "message",
        "tool_call",
        "usage_update",
        "tool_result",
        "message",
        "usage_update",
        "usage_update",
    ]
    call = events[1]
    assert (
        isinstance(call, ToolCallEvent) and call.name == "Read" and call.input == {"file_path": "a"}
    )
    result_event = events[3]
    assert isinstance(result_event, ToolResultEvent)
    assert result_event.output == "hello" and result_event.duration_ms == 250
    result = mapper.result
    assert result is not None and result.status == "completed"
    assert result.usage.cost_usd == 0.0024 and result.usage.turns == 2
    assert (result.usage.input_tokens, result.usage.output_tokens) == (4, 50)
    assert (result.usage.cache_read_tokens, result.usage.cache_write_tokens) == (100, 20)
    assert result.model == "claude-haiku-5-5" and result.session_id == "s-1"
    assert result.final_text == "It says hello." and result.duration_ms == 2981


def test_running_usage_before_the_result() -> None:
    mapper = EventMapper()
    for line in STREAM[:5]:
        mapper.map_json(line)
    usage = mapper.usage()
    assert (usage.input_tokens, usage.output_tokens, usage.turns) == (4, 50, 2)


def test_error_result() -> None:
    mapper = EventMapper()
    mapper.map_json(
        {
            "type": "result",
            "subtype": "error_max_budget_usd",
            "is_error": True,
            "total_cost_usd": 0.31,
            "num_turns": 7,
            "errors": ["Reached maximum budget ($0.3)"],
        }
    )
    assert mapper.result is not None
    assert mapper.result.status == "failed" and mapper.result.usage.cost_usd == 0.31
    assert mapper.result.error == "error_max_budget_usd: Reached maximum budget ($0.3)"


def test_tool_result_content_blocks() -> None:
    mapper = EventMapper()
    [event] = mapper.map_json(
        {
            "type": "user",
            "message": {
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": "x",
                        "is_error": True,
                        "content": [{"type": "text", "text": "boom"}, {"type": "image"}],
                    }
                ]
            },
        }
    )
    assert isinstance(event, ToolResultEvent) and event.is_error
    assert event.output == 'boom\n{"type": "image"}'


# ------------------------------------------------------------------ command


def test_command_line(tmp_path: Path) -> None:
    options = build_options(
        tmp_path,
        EngineOptions(
            model="claude-haiku-5-5",
            max_turns=5,
            max_cost_usd=1.5,
            reasoning_effort="high",
            engine_options={
                "cli_path": "/opt/claude",
                "allowed_tools": ["Bash(npm test)"],
                "disallowed_tools": ["WebFetch"],
                "add_dirs": ["/data"],
            },
        ),
    )
    assert build_command(options) == [
        "/opt/claude",
        "-p",
        "--output-format=stream-json",
        "--verbose",
        "--permission-mode=auto",
        "--setting-sources=project",
        "--model=claude-haiku-5-5",
        "--max-turns=5",
        "--max-budget-usd=1.5",
        "--effort=high",
        "--allowedTools=Bash(compose:*),Bash(npm test)",
        "--disallowedTools=WebFetch",
        "--add-dir=/data",
    ]


def test_command_needs_an_executable(tmp_path: Path) -> None:
    with pytest.raises(EngineError, match="not installed"):
        build_command(build_options(tmp_path, EngineOptions()))


def test_env_drops_nesting_marker(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CLAUDECODE", "1")
    env = build_env(build_options(tmp_path, EngineOptions(env={"COMPOSE_RUN_ID": "r1"})))
    assert "CLAUDECODE" not in env and env["COMPOSE_RUN_ID"] == "r1"


# ---------------------------------------------------------------- transport


def test_cli_is_the_default_transport(tmp_path: Path) -> None:
    opts = EngineOptions(engine_options={"cli_path": "/opt/claude"})
    assert isinstance(ClaudeEngine().start(EngineTask.prompt("hi"), tmp_path, opts), ClaudeCliRun)
    sdk = EngineOptions(engine_options={"transport": "sdk"})
    assert isinstance(ClaudeEngine().start(EngineTask.prompt("hi"), tmp_path, sdk), ClaudeRun)
    assert isinstance(
        ClaudeEngine("sdk").start(EngineTask.prompt("hi"), tmp_path, EngineOptions()), ClaudeRun
    )


def test_unknown_transport(tmp_path: Path) -> None:
    with pytest.raises(EngineError, match="transport"):
        ClaudeEngine().start(
            EngineTask.prompt("hi"), tmp_path, EngineOptions(engine_options={"transport": "rpc"})
        )


def test_config_sets_engine_defaults() -> None:
    config = Config.model_validate({"engines": {"claude": {"transport": "sdk"}}})
    assert config.engines == {"claude": {"transport": "sdk"}}


# ------------------------------------------------------------ the process


FAKE = """\
import json, os, sys, time
record = {"argv": sys.argv[1:], "stdin": sys.stdin.read(), "cwd": os.getcwd(),
          "env": {k: os.environ.get(k) for k in ("COMPOSE_RUN_ID", "CLAUDECODE")}}
with open(os.environ["FAKE_RECORD"], "w") as f:
    json.dump(record, f)
mode = os.environ.get("FAKE_MODE", "ok")
lines = json.load(open(os.environ["FAKE_LINES"]))
if mode == "crash":
    print("not json", flush=True)
    print("Error: invalid API key", file=sys.stderr, flush=True)
    sys.exit(2)
for i, line in enumerate(lines):
    print(json.dumps(line), flush=True)
    if mode == "hang" and i == 1:
        time.sleep(3600)
"""


@pytest.fixture
def fake_cli(tmp_path: Path) -> dict[str, Any]:
    script = tmp_path / "claude"
    script.write_text(f"#!{sys.executable}\n{FAKE}")
    script.chmod(0o755)
    lines = tmp_path / "lines.json"
    lines.write_text(json.dumps(STREAM))
    record = tmp_path / "record.json"
    work = tmp_path / "work"
    work.mkdir()
    env = {"FAKE_LINES": str(lines), "FAKE_RECORD": str(record), "COMPOSE_RUN_ID": "r1"}
    return {"script": str(script), "record": record, "work": work, "env": env}


def _start(fake: dict[str, Any], mode: str = "ok", transcript: Path | None = None) -> ClaudeCliRun:
    run = ClaudeEngine().start(
        EngineTask.skill("compose-plan", "use -- flags"),
        fake["work"],
        EngineOptions(
            env={**fake["env"], "FAKE_MODE": mode},
            engine_options={"cli_path": fake["script"]},
            transcript=transcript,
        ),
    )
    assert isinstance(run, ClaudeCliRun)
    return run


async def test_runs_the_command(fake_cli: dict[str, Any], monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CLAUDECODE", "1")
    run = _start(fake_cli)
    kinds = [e.kind async for e in run.events()]
    assert kinds.count("tool_call") == 1 and kinds[-1] == "usage_update"
    assert run.result.status == "completed" and run.result.usage.cost_usd == 0.0024
    record = json.loads(fake_cli["record"].read_text())
    assert record["stdin"] == "/compose-plan use -- flags"  # the prompt never touches argv
    assert record["argv"][:3] == ["-p", "--output-format=stream-json", "--verbose"]
    assert Path(record["cwd"]).resolve() == fake_cli["work"].resolve()
    assert record["env"] == {"COMPOSE_RUN_ID": "r1", "CLAUDECODE": None}


async def test_exit_without_result_fails_with_stderr(fake_cli: dict[str, Any]) -> None:
    run = _start(fake_cli, "crash")
    assert [e async for e in run.events()] == []
    assert run.result.status == "failed"
    assert run.result.error is not None
    assert "exited with code 2" in run.result.error and "invalid API key" in run.result.error


async def test_missing_executable(fake_cli: dict[str, Any]) -> None:
    run = ClaudeEngine().start(
        EngineTask.prompt("hi"),
        fake_cli["work"],
        EngineOptions(engine_options={"cli_path": str(fake_cli["work"] / "nope")}),
    )
    assert [e async for e in run.events()] == []
    assert run.result.status == "failed" and "cannot start" in (run.result.error or "")


async def test_stop_kills_the_process(fake_cli: dict[str, Any]) -> None:
    run = _start(fake_cli, "hang")
    events = run.events()
    first = await events.__anext__()
    assert first.kind == "message"
    started = time.monotonic()
    await run.stop()
    assert time.monotonic() - started < 5
    assert run.result.status == "stopped"
    assert run.result.usage.output_tokens == 30  # what was seen before the stop
    await events.aclose()


async def test_keeps_every_line_as_printed(fake_cli: dict[str, Any], tmp_path: Path) -> None:
    transcript = tmp_path / "steps" / "x.transcript.jsonl"
    run = _start(fake_cli, transcript=transcript)
    _ = [e async for e in run.events()]
    lines = [json.loads(line) for line in transcript.read_text().splitlines()]
    task, rest = lines[0], lines[1:]
    assert task["type"] == "compose_task" and task["prompt"] == "/compose-plan use -- flags"
    assert task["permission_mode"] == "auto" and task["argv"][0] == fake_cli["script"]
    assert rest == STREAM  # Claude Code's own output, unchanged


async def test_a_crash_keeps_what_was_printed_and_stderr(
    fake_cli: dict[str, Any], tmp_path: Path
) -> None:
    transcript = tmp_path / "t.jsonl"
    run = _start(fake_cli, "crash", transcript)
    _ = [e async for e in run.events()]
    text = transcript.read_text().splitlines()
    assert text[1] == "not json"  # kept even though it isn't JSON
    assert json.loads(text[-1]) == {
        "type": "compose_stderr",
        "lines": ["not json", "Error: invalid API key"],
    }
