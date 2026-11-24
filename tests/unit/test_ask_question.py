"""How the terminal asks one clarity question."""

from __future__ import annotations

from io import StringIO
from typing import Any

import pytest
from rich.console import Console

from compose.clarity.questions import Question
from compose.cli import runs


def _ask(monkeypatch: pytest.MonkeyPatch, q: Question, *replies: str) -> tuple[str, str, list[str]]:
    buffer = StringIO()
    monkeypatch.setattr(runs, "console", Console(file=buffer, width=100, color_system=None))
    hints: list[str] = []
    answers = iter(replies)

    def prompt(text: str, **_: Any) -> str:
        hints.append(text)
        return next(answers)

    monkeypatch.setattr(runs.typer, "prompt", prompt)
    return runs.ask_question(q), buffer.getvalue(), hints


def _setup(**fields: Any) -> Question:
    data: dict[str, Any] = {
        "id": "Q-001",
        "kind": "setup",
        "question": "Confirm the required documents.",
        "details": ["Required: problem, requirements.", "No approvers."],
        "options": ["confirm", "also require solution/architecture.md"],
        "recommended": "confirm",
    }
    return Question.model_validate({**data, **fields})


def test_shows_details_and_says_own_words_are_welcome(monkeypatch: pytest.MonkeyPatch) -> None:
    answer, out, hints = _ask(monkeypatch, _setup(), "")
    assert answer == "confirm"
    assert "  • Required: problem, requirements." in out and "  • No approvers." in out
    assert "  2. also require solution/architecture.md" in out
    assert hints == ["Answer (number or your own words, Enter = 1)"]


def test_marks_the_recommendation_once(monkeypatch: pytest.MonkeyPatch) -> None:
    # skills often write "(recommended)" into the option itself
    q = _setup(options=["confirm (recommended)", "other"], recommended="confirm (recommended)")
    answer, out, hints = _ask(monkeypatch, q, "")
    assert answer == "confirm (recommended)"
    assert out.count("recommended") == 1 and "   1. confirm  recommended" in out
    assert hints == ["Answer (number or your own words, Enter = 1)"]


def test_long_options_wrap_under_their_text(monkeypatch: pytest.MonkeyPatch) -> None:
    q = _setup(options=["word " * 40, "short"], recommended=None)
    out = _ask(monkeypatch, q, "2")[1]
    wrapped = [line for line in out.splitlines() if line.strip().startswith("word")]
    assert len(wrapped) > 1 and all(line.startswith("      word") for line in wrapped)
    assert "   1. word word" in out


def test_takes_a_number_or_own_words(monkeypatch: pytest.MonkeyPatch) -> None:
    assert _ask(monkeypatch, _setup(), "2")[0] == "also require solution/architecture.md"
    assert _ask(monkeypatch, _setup(), "also require the UX standards")[0] == (
        "also require the UX standards"
    )


def test_approvals_take_only_their_options(monkeypatch: pytest.MonkeyPatch) -> None:
    approval = _setup(
        kind="approval",
        options=["approve", "reject"],
        recommended=None,
        free_text=False,
        details=[],
    )
    answer, out, hints = _ask(monkeypatch, approval, "looks fine", "1")
    assert answer == "approve" and "Choose one of the numbered options." in out
    assert hints[0] == "Answer (number, Enter = later)"


def test_inline_questions_notify_once_per_questions_step(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[str] = []
    monkeypatch.setattr(runs.notify, "notify", lambda message, **_: seen.append(message))
    monkeypatch.setattr(runs, "ask_question", lambda q, out=None: "confirm")
    progress = runs.Progress(False, Console(file=StringIO(), color_system=None))
    ask = runs._interaction(True, progress).ask_question
    assert ask is not None
    progress({"type": "step_started", "exec_id": "s1", "step_id": "questions"})
    ask(_setup(id="Q-001"))
    ask(_setup(id="Q-002"))
    progress({"type": "step_started", "exec_id": "s2", "step_id": "questions"})
    ask(_setup(id="Q-003"))
    assert seen == ["waiting for your answers (Q-001)", "waiting for your answers (Q-003)"]
