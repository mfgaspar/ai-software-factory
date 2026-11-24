"""The GitHub Copilot engine: ``copilot --output-format=json`` with the prompt on stdin."""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Any

import pytest

from compose.engines.base import (
    EngineOptions,
    EngineTask,
    MessageEvent,
    ThinkingEvent,
    ToolCallEvent,
    ToolResultEvent,
    UsageEvent,
)
from compose.engines.copilot import install as installer
from compose.engines.copilot.adapter import CopilotEngine, build_options, prompt_for, tool_rule
from compose.engines.copilot.cli import CopilotRun, build_command
from compose.engines.copilot.mapping import CopilotMapper, credits_for
from compose.engines.registry import EngineError, default_registry
from compose.tracking import transcripts

DENIED = "Permission denied because no interactive user response was available."

# The shape the Copilot CLI prints (trimmed), including lines compose ignores.
STREAM: list[dict[str, Any]] = [
    {"type": "session.start", "data": {"sessionId": "s-1", "copilotVersion": "1.0.114"}},
    {"type": "session.model_change", "data": {"newModel": "claude-sonnet-5.5"}},
    {"type": "session.skills_loaded", "ephemeral": True, "data": {"skills": []}},
    {"type": "user.message", "data": {"content": "Do it."}},
    {
        "type": "assistant.message",
        "data": {
            "model": "claude-sonnet-5.5",
            "content": "Writing it.",
            "reasoningText": "A file, then a check.",
            "toolRequests": [
                {"toolCallId": "t1", "name": "create", "arguments": {"path": "a.txt"}},
                {"toolCallId": "t2", "name": "bash", "arguments": {"command": "rm a.txt"}},
            ],
        },
    },
    {
        "type": "tool.execution_start",
        "data": {"toolCallId": "t1", "toolName": "create", "arguments": {"path": "a.txt"}},
    },
    {
        "type": "tool.execution_start",
        "data": {"toolCallId": "t2", "toolName": "bash", "arguments": {"command": "rm a.txt"}},
    },
    {
        "type": "tool.execution_complete",
        "data": {"toolCallId": "t1", "success": True, "result": {"content": "Created a.txt"}},
    },
    {
        "type": "tool.execution_complete",
        "data": {
            "toolCallId": "t2",
            "success": False,
            "error": {"message": DENIED, "code": "denied"},
        },
    },
    {"type": "assistant.turn_end", "data": {"turnId": "0"}},
    {"type": "assistant.message", "data": {"content": "Done.", "toolRequests": []}},
    {"type": "assistant.turn_end", "data": {"turnId": "1"}},
    {
        "type": "session.usage_checkpoint",
        "data": {
            "totalNanoAiu": 8_519_140_000,
            "accountingSnapshot": {
                "tokenDetails": {
                    "input": {"tokenCount": 10},
                    "cache_read": {"tokenCount": 59614},
                    "cache_write": {"tokenCount": 30380},
                    "output": {"tokenCount": 326},
                }
            },
        },
    },
    {"type": "assistant.idle", "ephemeral": True, "data": {}},
    {"type": "result", "sessionId": "s-1", "exitCode": 0, "usage": {"sessionDurationMs": 8505}},
]

FAILED: list[dict[str, Any]] = [
    {"type": "session.start", "data": {"sessionId": "s-2"}},
    {"type": "session.error", "data": {"errorType": "query", "message": "Model is gone."}},
    {"type": "result", "sessionId": "s-2", "exitCode": 1, "usage": {"sessionDurationMs": 12}},
]


# ---------------------------------------------------------------- mapping


def test_maps_messages_tools_and_usage() -> None:
    mapper = CopilotMapper()
    events = [event for line in STREAM for event in mapper.map_json(line)]
    assert [type(e) for e in events] == [
        ThinkingEvent,
        MessageEvent,
        ToolCallEvent,
        ToolCallEvent,
        ToolResultEvent,
        ToolResultEvent,
        UsageEvent,
        MessageEvent,
        UsageEvent,
        UsageEvent,
        UsageEvent,
    ]
    assert events[2] == ToolCallEvent("t1", "create", {"path": "a.txt"})
    created, refused = events[4], events[5]
    assert isinstance(created, ToolResultEvent) and isinstance(refused, ToolResultEvent)
    assert created.output == "Created a.txt" and not created.is_error
    assert refused.output == DENIED and refused.is_error
    result = mapper.result
    assert result is not None and result.status == "completed" and result.error is None
    assert result.final_text == "Done." and result.session_id == "s-1"
    assert result.model == "claude-sonnet-5.5" and result.duration_ms == 8505
    usage = result.usage
    assert (usage.input_tokens, usage.output_tokens) == (10, 326)
    assert (usage.cache_read_tokens, usage.cache_write_tokens) == (59614, 30380)
    assert usage.turns == 2
    assert usage.cost_usd == pytest.approx(0.0851914)  # 8.52 AI credits at a cent each


def test_turns_count_before_any_usage_is_reported() -> None:
    mapper = CopilotMapper()
    events = [event for line in STREAM[:10] for event in mapper.map_json(line)]
    last = events[-1]
    assert isinstance(last, UsageEvent) and last.usage.turns == 1 and last.usage.cost_usd == 0


def test_a_failed_session_reports_what_copilot_said() -> None:
    mapper = CopilotMapper()
    for line in FAILED:
        mapper.map_json(line)
    assert mapper.result is not None
    assert mapper.result.status == "failed" and mapper.result.error == "Model is gone."


def test_a_budget_in_dollars_becomes_ai_credits() -> None:
    assert credits_for(5) == 500
    assert credits_for(0.555) == 56  # rounded up
    assert credits_for(0.05) == 30  # Copilot accepts no smaller cap


# ---------------------------------------------------------------- options


def test_tool_rules_are_translated_from_claude_codes_form() -> None:
    assert tool_rule("Bash(npm test)") == "shell(npm test)"
    assert tool_rule("Bash(git hash-object:*)") == "shell(git hash-object:*)"
    assert tool_rule("Bash") == "shell"
    assert tool_rule("Edit") == "write" and tool_rule("Read(.env)") == "read(.env)"
    assert tool_rule("shell(npm:*)") == "shell(npm:*)"  # already Copilot's
    assert tool_rule("WebFetch(domain:example.com)") == "WebFetch(domain:example.com)"


def test_command_line(tmp_path: Path) -> None:
    options = build_options(
        tmp_path,
        EngineOptions(
            model="gpt-5.5",
            reasoning_effort="high",
            max_cost_usd=2.5,
            engine_options={
                "cli_path": "/opt/copilot",
                "allowed_tools": ["Bash(npm test)", " ", "write"],
                "disallowed_tools": ["Bash(git push)"],
                "allowed_urls": ["example.com"],
                "add_dirs": ["/data"],
            },
        ),
    )
    assert build_command(options) == [
        "/opt/copilot",
        "--output-format=json",
        "--stream=off",
        "--no-color",
        "--no-ask-user",
        "--no-auto-update",
        "--trust-folder",
        "--allow-all-tools",
        "--allow-all-paths",
        "--model=gpt-5.5",
        "--reasoning-effort=high",
        "--max-ai-credits=250",
        "--allow-tool=shell(compose:*)",
        "--allow-tool=shell(npm test)",
        "--allow-tool=write",
        "--deny-tool=shell(git push)",
        "--allow-url=example.com",
        "--add-dir=/data",
    ]


def test_permission_modes(tmp_path: Path) -> None:
    def flags(mode: str) -> list[str]:
        extra = {"permission_mode": mode, "cli_path": "/opt/copilot"}
        return build_command(build_options(tmp_path, EngineOptions(engine_options=extra)))

    assert "--allow-all-tools" in flags("allow-all")
    rules = flags("rules")
    assert "--allow-all-tools" not in rules and "--assisted-approval" not in rules
    with pytest.raises(EngineError, match="permission_mode"):
        flags("auto")


def test_rejects_what_copilot_cannot_take(tmp_path: Path) -> None:
    with pytest.raises(EngineError, match="unknown Copilot engine_options: transport"):
        build_options(tmp_path, EngineOptions(engine_options={"transport": "sdk"}))
    with pytest.raises(EngineError, match="reasoning_effort"):
        build_options(tmp_path, EngineOptions(reasoning_effort="extreme"))
    with pytest.raises(EngineError, match="allowed_tools must be a list"):
        build_options(tmp_path, EngineOptions(engine_options={"allowed_tools": [1]}))


def test_missing_cli(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(installer, "cli_path", lambda: None)
    with pytest.raises(EngineError, match="not installed"):
        build_command(build_options(tmp_path, EngineOptions()))
    assert installer.check() == ["GitHub Copilot CLI is not installed (no `copilot` on PATH)"]


def test_default_registry_has_copilot() -> None:
    assert isinstance(default_registry().get("copilot"), CopilotEngine)


# ---------------------------------------------------------------- prompts


def _skill(root: Path, name: str, body: str) -> None:
    folder = root / ".claude" / "skills" / name
    folder.mkdir(parents=True)
    front = f"---\nname: {name}\ndescription: A test skill.\n---\n\n"
    (folder / "SKILL.md").write_text(front + body)


def test_a_skill_is_sent_with_its_arguments_filled_in(tmp_path: Path) -> None:
    _skill(tmp_path, "compose-plan", "# Plan\n\nThe request:\n\n$ARGUMENTS\n")
    prompt = prompt_for(EngineTask.skill("compose-plan", "use -- flags"), tmp_path)
    assert prompt.startswith("Carry out the `compose-plan` skill")
    assert prompt.endswith("# Plan\n\nThe request:\n\nuse -- flags")
    assert "description: A test skill" not in prompt  # the front matter stays out


def test_arguments_follow_a_skill_that_names_no_place_for_them(tmp_path: Path) -> None:
    _skill(tmp_path, "tidy", "Tidy the folder.\n")
    assert prompt_for(EngineTask.skill("tidy", "src"), tmp_path).endswith(
        "Tidy the folder.\n\nARGUMENTS: src"
    )
    assert prompt_for(EngineTask.skill("tidy"), tmp_path).endswith("Tidy the folder.")


def test_an_unknown_skill_is_asked_for_by_name(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(Path, "home", lambda: tmp_path / "home")
    prompt = prompt_for(EngineTask.skill("their-skill", "now"), tmp_path)
    assert prompt.startswith("/their-skill now\n") and "read `now`" in prompt
    assert prompt_for(EngineTask.prompt("Just this."), tmp_path) == "Just this."


# ------------------------------------------------------------ the process


FAKE = """\
import json, os, sys, time
record = {"argv": sys.argv[1:], "stdin": sys.stdin.read(), "cwd": os.getcwd(),
          "env": {k: os.environ.get(k) for k in ("COMPOSE_RUN_ID",)}}
with open(os.environ["FAKE_RECORD"], "w") as f:
    json.dump(record, f)
mode = os.environ.get("FAKE_MODE", "ok")
lines = json.load(open(os.environ["FAKE_LINES"]))
if mode == "crash":
    print("not json", flush=True)
    print("Error: not signed in", file=sys.stderr, flush=True)
    sys.exit(2)
for i, line in enumerate(lines):
    print(json.dumps(line), flush=True)
    if mode == "hang" and i == 4:
        time.sleep(3600)
"""


@pytest.fixture
def fake_cli(tmp_path: Path) -> dict[str, Any]:
    script = tmp_path / "copilot"
    script.write_text(f"#!{sys.executable}\n{FAKE}")
    script.chmod(0o755)
    lines = tmp_path / "lines.json"
    lines.write_text(json.dumps(STREAM))
    record = tmp_path / "record.json"
    work = tmp_path / "work"
    work.mkdir()
    env = {"FAKE_LINES": str(lines), "FAKE_RECORD": str(record), "COMPOSE_RUN_ID": "r1"}
    return {"script": str(script), "record": record, "work": work, "env": env, "lines": lines}


def _start(fake: dict[str, Any], mode: str = "ok", transcript: Path | None = None) -> CopilotRun:
    run = CopilotEngine().start(
        EngineTask.prompt("Do it."),
        fake["work"],
        EngineOptions(
            env={**fake["env"], "FAKE_MODE": mode},
            engine_options={"cli_path": fake["script"]},
            transcript=transcript,
        ),
    )
    assert isinstance(run, CopilotRun)
    return run


async def test_runs_the_command(fake_cli: dict[str, Any]) -> None:
    run = _start(fake_cli)
    kinds = [e.kind async for e in run.events()]
    assert kinds.count("tool_call") == 2 and kinds[-1] == "usage_update"
    assert run.result.status == "completed" and run.result.usage.turns == 2
    record = json.loads(fake_cli["record"].read_text())
    assert record["stdin"] == "Do it."  # the prompt never touches argv
    assert record["argv"][0] == "--output-format=json" and "Do it." not in record["argv"]
    assert Path(record["cwd"]).resolve() == fake_cli["work"].resolve()
    assert record["env"] == {"COMPOSE_RUN_ID": "r1"}


async def test_a_failed_session_fails_the_run(fake_cli: dict[str, Any]) -> None:
    fake_cli["lines"].write_text(json.dumps(FAILED))
    run = _start(fake_cli)
    _ = [e async for e in run.events()]
    assert run.result.status == "failed" and run.result.error == "Model is gone."


async def test_exit_without_result_fails_with_stderr(fake_cli: dict[str, Any]) -> None:
    run = _start(fake_cli, "crash")
    assert [e async for e in run.events()] == []
    assert run.result.status == "failed"
    assert run.result.error is not None
    assert "exited with code 2" in run.result.error and "not signed in" in run.result.error


async def test_missing_executable(fake_cli: dict[str, Any]) -> None:
    run = CopilotEngine().start(
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
    assert first.kind == "thinking"  # the reasoning comes before the message
    started = time.monotonic()
    await run.stop()
    assert time.monotonic() - started < 5
    assert run.result.status == "stopped" and run.result.session_id == "s-1"
    await events.aclose()


# ------------------------------------------------------------ the transcript


async def test_transcript_reads_back(fake_cli: dict[str, Any], tmp_path: Path) -> None:
    transcript = tmp_path / "steps" / "x.transcript.jsonl"
    run = _start(fake_cli, transcript=transcript)
    _ = [e async for e in run.events()]
    lines = [json.loads(line) for line in transcript.read_text().splitlines()]
    assert lines[0]["type"] == "compose_task" and lines[0]["prompt"] == "Do it."
    assert lines[1:-1] == STREAM  # exactly as printed
    assert lines[-1]["type"] == "compose_result" and lines[-1]["status"] == "completed"
    found = [e for e in transcripts.entries(transcript) if e["kind"] != "system"]
    assert [e["kind"] for e in found] == [
        "task",
        "session",
        "message",
        "thinking",
        "message",
        "tool_call",
        "tool_call",
        "tool_result",
        "tool_result",
        "message",
        "result",
    ]
    assert found[1]["copilot_version"] == "1.0.114" and found[2]["role"] == "user"
    assert found[5]["name"] == "create" and found[5]["input"] == {"path": "a.txt"}
    assert found[8]["is_error"] and found[8]["output"] == DENIED
    result = found[-1]
    assert not result["is_error"] and result["turns"] == 2
    assert result["cost_usd"] == pytest.approx(0.0851914)


async def test_transcript_keeps_the_error(fake_cli: dict[str, Any], tmp_path: Path) -> None:
    fake_cli["lines"].write_text(json.dumps(FAILED))
    transcript = tmp_path / "x.transcript.jsonl"
    _ = [e async for e in _start(fake_cli, transcript=transcript).events()]
    found = transcripts.entries(transcript)
    assert {"kind": "error", "text": "Model is gone."} in found
    assert found[-1]["is_error"] and found[-1]["errors"] == ["Model is gone."]


def test_apply_patch_is_reported_as_one_write_per_file() -> None:
    patch = (
        "*** Begin Patch\n*** Add File: a/new.md\n+x\n*** Update File: b/old.md\n@@\n-x\n+y\n"
        "*** End Patch"
    )
    events = CopilotMapper().map_json(
        {
            "type": "tool.execution_start",
            "data": {"toolCallId": "c1", "toolName": "apply_patch", "arguments": patch},
        }
    )
    assert [(e.name, e.input["path"]) for e in events] == [
        ("create", "a/new.md"),
        ("edit", "b/old.md"),
    ]


def test_reasoning_is_passed_on_when_readable() -> None:
    mapper = CopilotMapper()
    events = mapper.map_json(
        {"type": "assistant.reasoning", "data": {"reasoningId": "r", "content": "Check the brief."}}
    )
    assert [e.kind for e in events] == ["thinking"]
    assert mapper.map_json({"type": "assistant.reasoning", "data": {"content": ""}}) == []
    both = mapper.map_json(
        {"type": "assistant.message", "data": {"content": "Hi", "reasoningText": "Plan."}}
    )
    assert [e.kind for e in both] == ["thinking", "message"]


def test_copilot_installs_skills_in_github_skills(tmp_path: Path) -> None:
    written = CopilotEngine().install(tmp_path)
    rel = {str(p.relative_to(tmp_path)) for p in written}
    assert ".github/skills/clarity/SKILL.md" in rel
    assert not (tmp_path / ".claude").exists()
