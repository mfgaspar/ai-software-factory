"""The ``questions`` step, the internal ``clarity`` step, and clarity commits on pause."""

from __future__ import annotations

import textwrap
from datetime import UTC, datetime

import pytest
import yaml

from compose.clarity import questions
from compose.clarity.questions import Question
from compose.core.models import Run, RunStatus
from compose.engines.fake import Script, edit
from compose.repos import git
from compose.tracking import views
from compose.workflows import loader
from compose.workflows.loader import WorkflowError
from tests.unit.runner_helpers import Env, interaction

QFILE = ".clarity/questions.yml"


def _questions(*items: dict[str, object]) -> str:
    return yaml.safe_dump({"questions": list(items)}, sort_keys=False)


GAP = {
    "id": "Q-001",
    "kind": "gap",
    "question": "Which roles?",
    "options": ["3", "2"],
    "recommended": "3",
}
CONFLICT = {"id": "Q-002", "kind": "conflict", "question": "PRD or code?"}
APPROVAL = {
    "id": "Q-003",
    "kind": "approval",
    "question": "Approve the PRD?",
    "options": ["approve", "reject"],
    "free_text": False,
    "approver": "someone-else",
}


def _workflow(env: Env, step: str = "", *, wf_id: str = "ask-q") -> loader.LoadedWorkflow:
    body = f"""
    workflow: {{id: {wf_id}, name: Ask, scope: repo}}
    steps:
      - {{id: draft, prompt: draft}}
      - {{id: ask, type: questions, file: {QFILE}{step}}}
    """
    return env.workflow(body, name=wf_id)


def _script(env: Env, *items: dict[str, object]) -> None:
    env.fake.scripts = {"draft": Script(edit(QFILE, _questions(*items)))}


def _answer(env: Env, run: Run, answers: dict[str, str], by: str = "pat") -> None:
    questions.record(env.worktree(run) / QFILE, answers, by, datetime.now(UTC))


def _output(env: Env, run: Run, step_id: str = "ask") -> dict[str, object]:
    return env.exec_of(run, step_id)[-1].output


async def test_pauses_with_waiting_questions(env: Env) -> None:
    _script(env, GAP, CONFLICT, APPROVAL)
    run = await env.runner().start(env.repo, _workflow(env))
    assert run.status is RunStatus.PAUSED, run.error
    waiting = views.run_detail(env.db, env.home, run.id)["waiting"]
    assert waiting["step_id"] == "ask"
    assert [q["id"] for q in waiting["questions"]] == ["Q-001", "Q-002", "Q-003"]
    assert waiting["questions"][0]["question"] == "Which roles?"
    event = next(e for e in env.events if e["type"] == "questions_waiting")
    assert event["ids"] == ["Q-001", "Q-002", "Q-003"]


async def test_record_and_resume_completes(env: Env) -> None:
    _script(env, GAP, CONFLICT)
    runner = env.runner()
    run = await runner.start(env.repo, _workflow(env))
    _answer(env, run, {"Q-001": "3", "Q-002": "PRD"})
    run = await runner.resume(run.id)
    assert run.status is RunStatus.COMPLETED, run.error
    assert _output(env, run) == {"answered": 0, "pending": 0, "holding": 0}
    assert views.run_detail(env.db, env.home, run.id)["waiting"] is None


async def test_partial_answer_pauses_again(env: Env) -> None:
    _script(env, GAP, CONFLICT)
    runner = env.runner()
    run = await runner.start(env.repo, _workflow(env))
    _answer(env, run, {"Q-001": "3"})
    run = await runner.resume(run.id)
    assert run.status is RunStatus.PAUSED
    waiting = views.run_detail(env.db, env.home, run.id)["waiting"]
    assert [q["id"] for q in waiting["questions"]] == ["Q-002"]
    kept = {q.id: q.answer for q in questions.load(env.worktree(run) / QFILE)}
    assert kept == {"Q-001": "3", "Q-002": None}


async def test_approvals_alone_dont_pause(env: Env) -> None:
    _script(env, {**GAP, "answer": "3"}, APPROVAL)
    run = await env.runner().start(env.repo, _workflow(env))
    assert run.status is RunStatus.COMPLETED, run.error
    assert _output(env, run) == {"answered": 0, "pending": 1, "holding": 0}


async def test_holding_kinds_can_include_approvals(env: Env) -> None:
    _script(env, APPROVAL)
    wf = _workflow(env, ", holding_kinds: [approval]")
    run = await env.runner().start(env.repo, wf)
    assert run.status is RunStatus.PAUSED


async def test_interactive_answers(env: Env) -> None:
    _script(env, GAP, CONFLICT, APPROVAL)
    asked: list[str] = []

    def ask(q: Question) -> str:
        asked.append(q.id)
        return q.recommended or "the PRD"

    runner = env.runner(interaction=interaction(ask_question=ask))
    run = await runner.start(env.repo, _workflow(env))
    assert run.status is RunStatus.COMPLETED, run.error
    assert asked == ["Q-001", "Q-002"]  # the approval belongs to someone else
    assert _output(env, run) == {"answered": 2, "pending": 1, "holding": 0}
    by_id = {q.id: q for q in questions.load(env.worktree(run) / QFILE)}
    assert (by_id["Q-001"].answer, by_id["Q-001"].answered_by) == ("3", "compose-test")
    assert by_id["Q-002"].answer == "the PRD"
    assert by_id["Q-003"].answer is None


async def test_ask_false_counts(env: Env) -> None:
    _script(env, GAP, CONFLICT, APPROVAL)
    run = await env.runner().start(env.repo, _workflow(env, ", ask: false"))
    assert run.status is RunStatus.COMPLETED, run.error
    assert _output(env, run) == {"answered": 0, "pending": 3, "holding": 2}


async def test_no_file_completes(env: Env) -> None:
    env.fake.scripts = {}
    run = await env.runner().start(env.repo, _workflow(env))
    assert run.status is RunStatus.COMPLETED, run.error
    assert _output(env, run) == {"answered": 0, "pending": 0, "holding": 0}


# ------------------------------------------------------------------ clarity step

CLARITY_STEPS = """
workflow: {id: clarity, name: Clarity, scope: repo}
steps:
  - {id: write, prompt: write-docs}
  - {id: constitution, prompt: constitution}
  - {id: stamp, type: clarity, action: stamp-constitution}
  - {id: validate, prompt: validate}
  - {id: verdict, type: clarity, action: record-verdict, from_step: validate}
  - {id: commit, type: clarity, action: commit}
  - {id: merge, type: clarity, action: merge}
"""


def _builtin(env: Env, body: str) -> loader.LoadedWorkflow:
    path = env.tmp / "builtin.yml"
    path.write_text(textwrap.dedent(body))
    return loader.load_path(path, "builtin")


def test_user_workflow_with_clarity_step_is_rejected(env: Env) -> None:
    with pytest.raises(WorkflowError, match="type clarity is internal"):
        env.workflow(CLARITY_STEPS)
    assert _builtin(env, CLARITY_STEPS).id == "clarity"


def _clarity_scripts(env: Env, last_line: str) -> None:
    env.fake.scripts = {
        "write-docs": Script(edit(".clarity/product/prd.md", "# PRD\n")),
        "constitution": Script(edit(".compose/memory/constitution.md", "# Constitution\n")),
        "validate": Script(final_text=f"All checked.\n{last_line}"),
    }


async def test_clarity_step_records_commits_and_merges_on_pass(env: Env) -> None:
    from compose.clarity import constitution, fingerprint, verdict

    _clarity_scripts(env, "CLARITY: PASS")
    run = await env.runner().start(env.repo, _builtin(env, CLARITY_STEPS))
    assert run.status is RunStatus.COMPLETED, run.error
    workdir = env.worktree(run)
    fp = fingerprint.of_dir(workdir)
    assert _output(env, run, "verdict") == {
        "result": "PASS",
        "incomplete": 0,
        "fingerprint": fp,
        "constitution_current": True,
    }
    text = (workdir / constitution.CONSTITUTION_FILE).read_text()
    assert constitution.read_text(text) == fp
    sha = _output(env, run, "commit")["sha"]
    assert sha == git.rev_parse(workdir, "HEAD")
    assert git.git(workdir, "log", "-1", "--format=%s") == f"clarity: mixed run {run.id}"
    assert _output(env, run, "merge") == {"merged": True, "pending_reason": None}
    assert git.rev_parse(env.repo_path, "main") == sha
    recorded = verdict.read_ref(env.repo_path, "main")
    assert recorded is not None and recorded.verdict.passed and recorded.fingerprint == fp


async def test_clarity_merge_pending_on_fail(env: Env) -> None:
    _clarity_scripts(env, "CLARITY: FAIL (2 incomplete)")
    main = git.rev_parse(env.repo_path, "main")
    run = await env.runner().start(env.repo, _builtin(env, CLARITY_STEPS))
    assert run.status is RunStatus.COMPLETED, run.error
    assert _output(env, run, "verdict")["incomplete"] == 2
    merge = _output(env, run, "merge")
    assert merge["merged"] is False and "no PASS" in str(merge["pending_reason"])
    assert any(e["type"] == "clarity_merge_pending" for e in env.events)
    assert git.rev_parse(env.repo_path, "main") == main


# ------------------------------------------------------- commit on pause, fail, abort


async def test_clarity_run_commits_when_it_pauses(env: Env) -> None:
    _script(env, GAP)
    run = await env.runner().start(env.repo, _workflow(env, wf_id="clarity"))
    assert run.status is RunStatus.PAUSED
    workdir = env.worktree(run)
    subject = git.git(workdir, "log", "-1", "--format=%s")
    assert subject == f"clarity: mixed run {run.id} (paused)"
    assert git.changed_paths(workdir, ".clarity") == []
    assert any(e["type"] == "clarity_committed" for e in env.events)


async def test_clarity_run_commits_when_it_fails(env: Env) -> None:
    body = """
    workflow: {id: clarity-validate, name: Validate, scope: repo}
    steps:
      - {id: draft, prompt: draft}
      - {id: boom, run: "exit 1"}
    """
    _script(env, GAP)
    run = await env.runner().start(env.repo, env.workflow(body, name="cv"))
    assert run.status is RunStatus.FAILED
    subject = git.git(env.worktree(run), "log", "-1", "--format=%s")
    assert subject == f"clarity: validate run {run.id} (failed)"


async def test_other_repo_runs_dont_commit(env: Env) -> None:
    _script(env, GAP)
    run = await env.runner().start(env.repo, _workflow(env))
    assert run.status is RunStatus.PAUSED
    assert git.changed_paths(env.worktree(run), ".clarity") != []


async def test_clarity_run_commits_when_it_aborts(env: Env) -> None:
    body = """
    workflow: {id: clarity, name: Clarity, scope: repo}
    inputs: {verdict: {type: string, default: reject}}
    steps:
      - {id: draft, prompt: draft}
      - {id: review, type: gate, message: "ok?", verdict_input: verdict}
    """
    _script(env, GAP)
    run = await env.runner().start(env.repo, env.workflow(body, name="clarity"))
    assert run.status is RunStatus.ABORTED
    subject = git.git(env.worktree(run), "log", "-1", "--format=%s")
    assert subject == f"clarity: mixed run {run.id} (aborted)"
