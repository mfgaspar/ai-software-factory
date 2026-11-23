"""What a foreground run prints while it goes."""

from __future__ import annotations

from io import StringIO
from pathlib import Path
from typing import Any

from rich.console import Console

from compose.cli.runs import Progress


def _progress(verbose: bool = False, width: int = 60) -> tuple[Progress, StringIO]:
    buffer = StringIO()
    return Progress(verbose, Console(file=buffer, width=width, color_system=None)), buffer


def _engine(kind: str, **data: Any) -> dict[str, Any]:
    return {"type": "engine_event", "exec_id": "e1", "event": {"kind": kind, **data}}


def _start(progress: Progress, tmp_path: Path) -> None:
    progress({"type": "run_started", "worktree": str(tmp_path)})
    progress({"type": "step_started", "exec_id": "e1", "step_id": "draft", "step_type": "command"})


def test_writes_show_relative_paths_without_verbose(tmp_path: Path) -> None:
    progress, out = _progress()
    _start(progress, tmp_path)
    target = tmp_path / ".clarity" / "goal" / "problem.md"
    progress(_engine("tool_call", name="Write", input={"file_path": str(target)}))
    progress(_engine("tool_call", name="Edit", input={"file_path": "/elsewhere/x.md"}))
    progress(_engine("tool_call", name="Read", input={"file_path": str(target)}))
    text = out.getvalue()
    assert "  ✎ .clarity/goal/problem.md" in text
    assert "✎ /elsewhere/x.md" in text
    assert "Read" not in text


def test_verbose_shows_other_tool_calls_with_a_hint(tmp_path: Path) -> None:
    progress, out = _progress(verbose=True)
    _start(progress, tmp_path)
    progress(_engine("tool_call", name="Read", input={"file_path": str(tmp_path / "a.md")}))
    progress(_engine("tool_call", name="Bash", input={"command": "git status\nmore"}))
    text = out.getvalue()
    assert "· Read a.md" in text and "· Bash git status" in text and "more" not in text


def test_commentary_is_the_first_line_clipped(tmp_path: Path) -> None:
    progress, out = _progress(width=40)
    _start(progress, tmp_path)
    progress(_engine("message", text="\n  No code exists yet, so I draft from the brief only.\n2"))
    progress(_engine("message", text="   "))
    lines = [line for line in out.getvalue().splitlines() if "»" in line]
    assert len(lines) == 1
    assert lines[0].startswith("  » No code exists") and lines[0].endswith("…")
    assert len(lines[0]) <= 40


def test_no_live_line_when_not_a_terminal(tmp_path: Path) -> None:
    progress, out = _progress()
    _start(progress, tmp_path)
    progress(_engine("usage_update", usage={"cost_usd": 0.5, "input_tokens": 10}))
    assert progress.live is None
    progress(
        {
            "type": "step_finished",
            "exec_id": "e1",
            "step_id": "draft",
            "status": "completed",
            "cost_usd": 0.5,
        }
    )
    assert "✓ draft completed $0.5000" in out.getvalue()


def test_live_line_in_a_terminal_stops_at_the_step_end(tmp_path: Path) -> None:
    buffer = StringIO()
    progress = Progress(False, Console(file=buffer, width=60, force_terminal=True))
    _start(progress, tmp_path)
    assert progress.live is not None
    progress(
        _engine("usage_update", usage={"cost_usd": 0, "input_tokens": 1500, "output_tokens": 0})
    )
    assert "draft" in str(progress.status.__rich__()) and "1.5k tokens" in str(
        progress.status.__rich__()
    )
    progress({"type": "step_finished", "exec_id": "e1", "step_id": "draft", "status": "completed"})
    assert progress.live is None


def test_nested_steps_keep_their_indent(tmp_path: Path) -> None:
    progress, out = _progress()
    progress({"type": "step_started", "exec_id": "p", "step_id": "rounds", "step_type": "do-while"})
    progress(
        {
            "type": "step_started",
            "exec_id": "e1",
            "parent_exec_id": "p",
            "step_id": "apply",
            "step_type": "command",
        }
    )
    progress(_engine("message", text="Applying answers."))
    assert "  ▸ apply command" in out.getvalue()
    assert "    » Applying answers." in out.getvalue()
