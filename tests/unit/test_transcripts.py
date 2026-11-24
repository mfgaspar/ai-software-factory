"""What a step's transcript file holds and how it reads back."""

from __future__ import annotations

import json
from pathlib import Path

from claude_agent_sdk import (
    AssistantMessage,
    ResultMessage,
    SystemMessage,
    TextBlock,
    ThinkingBlock,
    ToolResultBlock,
    ToolUseBlock,
    UserMessage,
)

from compose.engines.claude.mapping import as_stream_json
from compose.tracking import transcripts


def test_sdk_messages_take_the_stream_json_shape(tmp_path: Path) -> None:
    messages = [
        SystemMessage("init", {"session_id": "s1", "model": "m", "permissionMode": "auto"}),
        AssistantMessage(
            [
                ThinkingBlock("Plan first.", "sig"),
                TextBlock("Reading."),
                ToolUseBlock("t1", "Read", {"file_path": "a.md"}),
            ],
            "m",
            parent_tool_use_id="p1",
        ),
        UserMessage([ToolResultBlock("t1", "the whole file", False)]),
        ResultMessage(
            subtype="success",
            duration_ms=5,
            duration_api_ms=4,
            is_error=False,
            num_turns=2,
            session_id="s1",
            total_cost_usd=0.01,
            permission_denials=[{"tool_name": "Bash", "tool_input": {"command": "rm -rf /"}}],
        ),
    ]
    file = tmp_path / "t.jsonl"
    lines = [json.dumps(as_stream_json(m), default=str) for m in messages]
    file.write_text("\n".join([*lines, "{cut short"]) + "\n")
    found = transcripts.entries(file)
    assert [e["kind"] for e in found] == [
        "session",
        "thinking",
        "message",
        "tool_call",
        "tool_result",
        "result",
        "raw",
    ]
    assert found[0]["permission_mode"] == "auto"
    assert found[1] == {"kind": "thinking", "text": "Plan first.", "parent": "p1"}
    assert found[3]["input"] == {"file_path": "a.md"} and found[3]["parent"] == "p1"
    assert found[4]["output"] == "the whole file"
    assert found[5]["permission_denials"][0]["tool_name"] == "Bash"


def test_no_file_no_entries(tmp_path: Path) -> None:
    assert transcripts.entries(tmp_path / "missing.jsonl") == []
