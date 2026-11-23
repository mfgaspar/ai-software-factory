"""``questions`` steps: the pending questions in a questions file.

On a terminal, each pending question is asked and the answers are recorded with
``answered_by`` set to the git user name. Otherwise the run pauses while a question of a
holding kind is pending (approvals don't hold a run by default); answers written into the
file meanwhile are picked up on resume.
"""

from __future__ import annotations

import asyncio
import getpass
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from compose.clarity import questions
from compose.core.models import StepExec
from compose.repos import git
from compose.runner.context import Scope
from compose.runner.errors import InputError, RunPaused
from compose.runner.steps.base import Outcome
from compose.workflows.schema import QuestionsStep

if TYPE_CHECKING:
    from compose.runner.runner import RunContext


def answerer(workdir: Path) -> str:
    """Who answers on this machine: the git user name, else the OS user."""
    try:
        name = git.user_name(workdir)
    except OSError:
        name = None
    return name or getpass.getuser()


def _counts(path: Path, holding: set[str]) -> tuple[list[questions.Question], int]:
    pending = questions.pending(questions.load(path))
    return pending, sum(1 for q in pending if q.kind in holding)


async def execute(rc: RunContext, step: QuestionsStep, row: StepExec, scope: Scope) -> Outcome:
    file = rc.render_text(step.file, scope)
    path = rc.worktree / file
    try:
        pending, holding = _counts(path, step.holding)
    except InputError as exc:
        return Outcome.failed(str(exc))
    if not step.ask or not pending:
        return Outcome.ok(answered=0, pending=len(pending), holding=holding)

    interaction = rc.runner.interaction
    ask = interaction.ask_question
    if interaction.interactive and ask is not None:
        by = answerer(rc.worktree)
        answers: dict[str, str] = {}
        for q in pending:
            if q.kind == "approval" and q.approver != by:
                continue  # an absent approver doesn't hold the run
            answer = (await asyncio.to_thread(ask, q)).strip()
            if not answer:
                continue  # left for later
            problems = questions.validate_answer(q, answer, by)
            if problems:
                rc.emit("question_skipped", exec_id=row.id, id=q.id, problems=problems)
                continue
            answers[q.id] = answer
        try:
            if answers:
                questions.record(path, answers, by, datetime.now(UTC))
            pending, holding = _counts(path, step.holding)
        except InputError as exc:
            return Outcome.failed(str(exc))
        rc.emit("questions_answered", exec_id=row.id, step_id=step.id, ids=list(answers))
        return Outcome.ok(answered=len(answers), pending=len(pending), holding=holding)

    if holding:
        rc.emit(
            "questions_waiting",
            exec_id=row.id,
            step_id=step.id,
            key=scope.key(step.id),
            ids=[q.id for q in pending],
            file=str(path),
        )
        raise RunPaused(
            step.id, f"waiting for answers to {holding} question(s) in {file} ({step.id!r})"
        )
    return Outcome.ok(answered=0, pending=len(pending), holding=0)
