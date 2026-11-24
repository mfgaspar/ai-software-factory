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
    progress(
        {
            "type": "step_started",
            "exec_id": "e1",
            "step_id": "draft",
            "name": "Draft the documents",
            "step_type": "command",
        }
    )


def _finish(progress: Progress, exec_id: str = "e1", **data: Any) -> None:
    event = {"type": "step_finished", "exec_id": exec_id, "status": "completed", **data}
    progress(event)


def test_a_step_is_one_line_with_its_files_and_cost(tmp_path: Path) -> None:
    progress, out = _progress()
    _start(progress, tmp_path)
    target = tmp_path / ".clarity" / "goal" / "problem.md"
    for _ in range(3):  # the same file edited three times counts once
        progress(_engine("tool_call", name="Edit", input={"file_path": str(target)}))
    progress(_engine("tool_call", name="Write", input={"file_path": "/elsewhere/x.md"}))
    progress(_engine("tool_call", name="Read", input={"file_path": str(target)}))
    progress(_engine("message", text="Drafting the problem statement."))
    _finish(progress, step_id="draft", cost_usd=0.0307)
    lines = [line for line in out.getvalue().splitlines() if line.strip()]
    assert lines[-1].startswith("✓ Draft the documents ")
    assert lines[-1].endswith(" · $0.03") and " 2 files · " in lines[-1]
    text = out.getvalue()
    assert "✎" not in text and "»" not in text and "Read" not in text and "completed" not in text


def test_verbose_shows_files_once_commentary_and_tool_calls(tmp_path: Path) -> None:
    progress, out = _progress(verbose=True)
    _start(progress, tmp_path)
    for _ in range(2):
        progress(_engine("tool_call", name="Edit", input={"file_path": str(tmp_path / "a.md")}))
    progress(_engine("tool_call", name="Read", input={"file_path": str(tmp_path / "a.md")}))
    progress(_engine("tool_call", name="Bash", input={"command": "git status\nmore"}))
    progress(_engine("message", text="Writing the app."))
    text = out.getvalue()
    assert "▸ Draft the documents command" in text
    assert text.count("✎ a.md") == 1
    assert "· Read a.md" in text and "· Bash git status" in text and "more" not in text
    assert "» Writing the app." in text


def test_commentary_is_the_first_line_clipped(tmp_path: Path) -> None:
    progress, out = _progress(verbose=True, width=40)
    _start(progress, tmp_path)
    progress(_engine("message", text="\n  No code exists yet, so I draft from the brief only.\n2"))
    progress(_engine("message", text="   "))
    lines = [line for line in out.getvalue().splitlines() if "»" in line]
    assert len(lines) == 1
    assert lines[0].startswith("  » No code exists") and lines[0].endswith("…")
    assert len(lines[0]) <= 40


def test_control_and_quiet_steps_stay_out(tmp_path: Path) -> None:
    progress, out = _progress()
    progress({"type": "step_started", "exec_id": "p", "step_id": "rounds", "step_type": "do-while"})
    progress(
        {
            "type": "step_started",
            "exec_id": "e1",
            "parent_exec_id": "p",
            "step_id": "apply",
            "key": "rounds#2/apply",
            "name": "Apply your answers",
            "step_type": "command",
        }
    )
    _finish(progress)
    progress({"type": "step_started", "exec_id": "q", "step_id": "count", "quiet": True})
    _finish(progress, "q")
    progress({"type": "step_started", "exec_id": "s", "step_id": "stamp", "quiet": True})
    progress({"type": "step_finished", "exec_id": "s", "status": "failed", "error": "no file"})
    _finish(progress, "p")
    lines = [line for line in out.getvalue().splitlines() if line.strip() and "▸" not in line]
    assert lines[0].startswith("✓ Apply your answers (round 2)")  # no indent, no parent
    assert lines[1].startswith("✗ stamp") and "failed" in lines[1] and "no file" in lines[1]
    assert len(lines) == 2


def test_a_questions_step_counts_its_answers(tmp_path: Path) -> None:
    progress, out = _progress()
    event = {"type": "step_started", "exec_id": "q", "step_type": "questions"}
    progress({**event, "step_id": "questions", "name": "Your answers"})
    progress.asked += 3
    _finish(progress, "q")
    progress({**event, "exec_id": "q2", "step_id": "questions", "name": "Your answers"})
    _finish(progress, "q2")  # nothing to ask: no line
    lines = [line for line in out.getvalue().splitlines() if line.strip()]
    assert len(lines) == 1 and lines[0].startswith("✓ Your answers") and "3 answered" in lines[0]


def test_header_names_the_workflow(tmp_path: Path) -> None:
    progress, out = _progress()
    progress(
        {
            "type": "run_started",
            "run_id": "run_1",
            "workflow": "Clarity foundation",
            "worktree": str(tmp_path),
        }
    )
    assert out.getvalue().startswith("Clarity foundation  run_1")


def test_no_live_line_when_not_a_terminal(tmp_path: Path) -> None:
    progress, out = _progress()
    _start(progress, tmp_path)
    progress(_engine("usage_update", usage={"cost_usd": 0.5, "input_tokens": 10}))
    assert progress.live is None
    assert "▸ Draft the documents" in out.getvalue()  # a log still says what is running
    _finish(progress, step_id="draft", cost_usd=0.5)
    assert "$0.50" in out.getvalue()


def test_live_line_in_a_terminal_stops_at_the_step_end(tmp_path: Path) -> None:
    buffer = StringIO()
    progress = Progress(False, Console(file=buffer, width=80, force_terminal=True))
    _start(progress, tmp_path)
    assert progress.live is not None
    usage = {"cost_usd": 0, "turns": 13, "estimated_cost_usd": 0.1234}
    progress(_engine("usage_update", usage=usage))
    progress(_engine("message", text="**Reading the brief** first."))
    line = str(progress.status.__rich__())
    first, _, note = line.partition("\n")
    assert " Draft the documents · " in first and " · turn 14 · ~$0.12" in first
    assert "Reading the brief" in note
    progress(_engine("usage_update", usage={**usage, "estimated_cost_usd": 0.004}))
    assert " · ~<$0.01" in str(progress.status.__rich__())
    progress(_engine("usage_update", usage={**usage, "cost_usd": 0.41}))  # the real cost wins
    line = str(progress.status.__rich__())
    assert " · $0.41" in line and "~" not in line
    _finish(progress, step_id="draft")
    assert progress.live is None
