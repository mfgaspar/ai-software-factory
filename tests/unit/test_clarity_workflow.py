"""The built-in ``clarity`` and ``clarity-validate`` workflows, end to end on the fake engine.

The scripts stand in for the skills: ``/clarity draft`` writes a PRD and a gap question,
``/clarity apply`` raises a review question until one is answered, ``compose-constitution``
writes the constitution and ``clarity-validate`` passes when nothing is pending.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

import pytest
import yaml

from compose.clarity import constitution, fingerprint, questions, verdict
from compose.clarity.questions import Question
from compose.core.models import Run, RunStatus
from compose.engines.base import EngineOptions, EngineTask
from compose.engines.fake import Script, edit
from compose.repos import git
from compose.runner.errors import InputError
from compose.workflows import loader
from tests.unit.runner_helpers import Env, interaction

QFILE = ".clarity/questions.yml"
GAP = {"id": "Q-001", "kind": "gap", "question": "Which roles?", "recommended": "3"}
APPROVAL = {
    "id": "Q-009",
    "kind": "approval",
    "question": "Approve the PRD?",
    "options": ["approve", "reject"],
    "free_text": False,
    "approver": "someone-else",
}
ScriptFor = Callable[[EngineTask, Path, EngineOptions], Script]


def _load(cwd: Path) -> list[dict[str, object]]:
    path = cwd / QFILE
    if not path.is_file():
        return []
    return list((yaml.safe_load(path.read_text()) or {}).get("questions") or [])


def _dump(items: list[dict[str, object]]) -> str:
    return yaml.safe_dump({"questions": items}, sort_keys=False)


def skills(
    *, drafted: list[dict[str, object]] | None = None, always_ask: bool = False
) -> ScriptFor:
    """Plausible clarity skills. ``always_ask``: apply raises a new gap every round."""
    first = [GAP] if drafted is None else drafted

    def script(task: EngineTask, cwd: Path, options: EngineOptions) -> Script:
        args = task.args or ""
        if task.text == "clarity" and args.endswith("draft"):
            acts = edit(".clarity/product/prd.md", f"# PRD\nFrom: {args}\n")
            return Script([*acts, *edit(QFILE, _dump(_load(cwd) or list(first)))])
        if task.text == "clarity" and args == "apply":
            items = _load(cwd)
            if always_ask:
                n = len(items) + 1
                items.append({"id": f"Q-{n:03}", "kind": "gap", "question": f"More {n}?"})
            elif not any(q["kind"] == "review" for q in items):
                items.append({"id": "Q-002", "kind": "review", "question": "Confirm?"})
            notes = "".join(f"- {q['id']}: {q.get('answer')}\n" for q in items)
            acts = edit(".clarity/product/prd.md", f"# PRD\n{notes}")
            return Script([*acts, *edit(QFILE, _dump(items))])
        if task.text == "compose-constitution":
            return Script(edit(constitution.CONSTITUTION_FILE, "# Constitution\n"))
        if task.text == "clarity-validate":
            pending = [q for q in _load(cwd) if q.get("answer") is None]
            last = f"CLARITY: FAIL ({len(pending)} incomplete)" if pending else "CLARITY: PASS"
            return Script(final_text=f"Checked.\n{last}")
        return Script()

    return script


def _workflow(name: str = "clarity") -> loader.LoadedWorkflow:
    return loader.resolve(name, None)


def _answer(env: Env, run: Run, answers: dict[str, str]) -> None:
    questions.record(env.worktree(run) / QFILE, answers, "pat", datetime.now(UTC))


def _called(env: Env) -> list[str]:
    return [f"{task.text} {task.args or ''}".strip() for task, _, _ in env.fake.calls]


def _output(env: Env, run: Run, step_id: str) -> dict[str, object]:
    return env.exec_of(run, step_id)[-1].output


async def test_mixed_pauses_then_passes_and_merges(env: Env) -> None:
    env.fake.scripts = skills()
    runner = env.runner()
    run = await runner.start(env.repo, _workflow(), {"sources": "docs/prd.md"})
    assert run.status is RunStatus.PAUSED, run.error
    assert env.fake.calls[0][0].args == "docs/prd.md draft"

    _answer(env, run, {"Q-001": "3"})
    run = await runner.resume(run.id)
    assert run.status is RunStatus.PAUSED, run.error  # apply raised the review question
    _answer(env, run, {"Q-002": "confirm"})
    run = await runner.resume(run.id)
    assert run.status is RunStatus.COMPLETED, run.error

    assert _called(env) == [
        "clarity docs/prd.md draft",
        "clarity apply",
        "clarity apply",
        "compose-constitution from-clarity",
        "clarity-validate",
    ]
    workdir = env.worktree(run)
    fp = fingerprint.of_dir(workdir)
    assert _output(env, run, "verdict")["result"] == "PASS"
    stamped = constitution.read_text((workdir / constitution.CONSTITUTION_FILE).read_text())
    assert stamped == fp
    sha = _output(env, run, "commit")["sha"]
    assert sha == git.rev_parse(env.repo_path, "clarity")
    assert git.git(workdir, "log", "-1", "--format=%s") == f"clarity: mixed run {run.id}"
    assert _output(env, run, "merge") == {"merged": True, "pending_reason": None}
    assert git.rev_parse(env.repo_path, "main") == sha
    recorded = verdict.read_ref(env.repo_path, "main")
    assert recorded is not None and recorded.verdict.passed and recorded.fingerprint == fp


async def test_auto_never_pauses_and_fails_without_merging(env: Env) -> None:
    env.fake.scripts = skills()
    main = git.rev_parse(env.repo_path, "main")
    run = await env.runner().start(env.repo, _workflow(), {"mode": "auto"})
    assert run.status is RunStatus.COMPLETED, run.error
    assert _called(env) == [
        "clarity draft",
        "compose-constitution from-clarity",
        "clarity-validate",
    ]
    assert _output(env, run, "verdict")["result"] == "FAIL"
    assert _output(env, run, "verdict")["incomplete"] == 1
    assert _output(env, run, "merge")["merged"] is False
    assert git.rev_parse(env.repo_path, "main") == main
    assert git.git(env.worktree(run), "log", "-1", "--format=%s") == f"clarity: auto run {run.id}"


def test_mode_must_be_mixed_or_auto(env: Env) -> None:
    with pytest.raises(InputError, match="not one of: mixed, auto"):
        env.runner().create_run(env.repo, _workflow(), {"mode": "interactive"})


async def test_only_approvals_pending_completes_with_fail(env: Env) -> None:
    drafted = [{**GAP, "answer": "3"}, {"id": "Q-002", "kind": "review", "question": "Ok?"}]
    drafted[1]["answer"] = "confirm"
    env.fake.scripts = skills(drafted=[*drafted, APPROVAL])
    run = await env.runner().start(env.repo, _workflow())
    assert run.status is RunStatus.COMPLETED, run.error
    assert len(env.exec_of(run, "apply")) == 1
    assert _output(env, run, "count") == {"answered": 0, "pending": 1, "holding": 0}
    assert _output(env, run, "verdict") == {
        **_output(env, run, "verdict"),
        "result": "FAIL",
        "incomplete": 1,
    }
    assert _output(env, run, "merge")["merged"] is False


async def test_loop_stops_after_four_rounds(env: Env) -> None:
    env.fake.scripts = skills(always_ask=True)

    def ask(q: Question) -> str:
        return "yes"

    run = await env.runner(interaction=interaction(ask_question=ask)).start(env.repo, _workflow())
    assert run.status is RunStatus.COMPLETED, run.error
    assert len(env.exec_of(run, "apply")) == 4
    assert _output(env, run, "rounds") == {"iterations": 4, "exhausted": True}
    assert _output(env, run, "count")["holding"] == 1  # still pending, left in the file
    assert _output(env, run, "verdict")["result"] == "FAIL"


# ------------------------------------------------------------------ clarity-validate


def _commit_foundation(env: Env, marker: str | None) -> None:
    """Commit a clarity foundation on main, with a constitution stamped with ``marker``."""
    root = env.repo_path
    (root / ".clarity/product").mkdir(parents=True)
    (root / ".clarity/product/prd.md").write_text("# PRD\n")
    (root / ".compose/memory").mkdir(parents=True)
    body = "# Hand-made constitution\n"
    head = f"{constitution.marker(marker)}\n" if marker else ""
    (root / constitution.CONSTITUTION_FILE).write_text(head + body)
    git.git(root, "add", ".clarity", ".compose")
    git.git(root, "commit", "-q", "-m", "foundation")


def _validate_only(result: str) -> ScriptFor:
    def script(task: EngineTask, cwd: Path, options: EngineOptions) -> Script:
        if task.text == "clarity-validate":
            return Script(final_text=f"Checked.\n{result}")
        if task.text == "compose-constitution":
            return Script(edit(constitution.CONSTITUTION_FILE, "# Generated\n"))
        return Script()

    return script


async def test_validate_regenerates_a_stale_constitution_on_pass(env: Env) -> None:
    _commit_foundation(env, "stale")
    env.fake.scripts = _validate_only("CLARITY: PASS")
    run = await env.runner().start(env.repo, _workflow("clarity-validate"))
    assert run.status is RunStatus.COMPLETED, run.error
    assert _called(env) == ["clarity-validate", "compose-constitution from-clarity"]
    workdir = env.worktree(run)
    fp = fingerprint.of_dir(workdir)
    assert _output(env, run, "verdict")["constitution_current"] is False
    assert constitution.read_ref(env.repo_path, "main") == fp
    assert git.git(workdir, "log", "-1", "--format=%s") == f"clarity: validate run {run.id}"
    assert _output(env, run, "merge")["merged"] is True


async def test_validate_keeps_a_current_constitution(env: Env) -> None:
    _commit_foundation(env, None)
    fp = fingerprint.of_ref(env.repo_path, "main")
    path = env.repo_path / constitution.CONSTITUTION_FILE
    constitution.stamp(path, fp)
    git.git(env.repo_path, "commit", "-q", "-am", "stamp")
    env.fake.scripts = _validate_only("CLARITY: PASS")
    run = await env.runner().start(env.repo, _workflow("clarity-validate"))
    assert run.status is RunStatus.COMPLETED, run.error
    assert _called(env) == ["clarity-validate"]
    assert _output(env, run, "verdict")["constitution_current"] is True


async def test_validate_leaves_the_constitution_alone_on_fail(env: Env) -> None:
    _commit_foundation(env, "stale")
    main = git.rev_parse(env.repo_path, "main")
    env.fake.scripts = _validate_only("CLARITY: FAIL (2 incomplete)")
    run = await env.runner().start(env.repo, _workflow("clarity-validate"))
    assert run.status is RunStatus.COMPLETED, run.error
    assert _called(env) == ["clarity-validate"]
    assert constitution.read_text((env.worktree(run) / constitution.CONSTITUTION_FILE).read_text())
    assert _output(env, run, "merge")["merged"] is False
    assert git.rev_parse(env.repo_path, "main") == main
