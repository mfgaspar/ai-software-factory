"""What ``compose clarity`` and the clarity API routes share: status, questions, answers,
merge, and the input name ``compose build`` fills.

Answers are repo-level: they're written into the questions file in the clarity worktree,
whether or not a run is paused on them. A repo-scoped run paused at a ``questions`` step
is resumable once none of the questions it asked is pending any more (approvals excepted:
they never hold a run).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from compose.clarity import branch, constitution, fingerprint, preflight, questions, summary
from compose.clarity import verdict as verdicts
from compose.core import store
from compose.core.db import Database
from compose.core.home import Home
from compose.core.models import Repo, Run, RunStatus
from compose.repos import git
from compose.runner.errors import InputError, RunError
from compose.tracking import views
from compose.workflows.schema import InputType, Workflow

QUESTIONS_PATH = f"{fingerprint.CLARITY_DIR}/{questions.QUESTIONS_FILE}"
NOT_HOLDING = frozenset({"approval"})


@dataclass(frozen=True)
class Answered:
    recorded: list[questions.Question]
    resumable: Run | None  # the paused clarity run these answers unblock


def started(repo: Repo, clarity_branch: str) -> bool:
    """The repo has a clarity branch, or ``.clarity/`` on its default branch."""
    root = Path(repo.path)
    if git.branch_exists(root, clarity_branch):
        return True
    base = branch.default_branch(repo)
    proc = git.run_git(root, "ls-tree", "--name-only", base, "--", fingerprint.CLARITY_DIR)
    return proc.returncode == 0 and bool(proc.stdout.strip())


def workdir(home: Home, repo: Repo, clarity_branch: str, *, create: bool = False) -> Path | None:
    """Where the repo's clarity documents are worked on: the clarity worktree.

    Without a clarity branch that's None, unless ``create`` (the branch is made from the
    default branch). The worktree is never brought up to date here: only runs do that.
    """
    if not create and not git.branch_exists(Path(repo.path), clarity_branch):
        return None
    return branch.ensure_worktree(home, repo, branch=clarity_branch, update=False)


def active_run(db: Database, repo: Repo) -> Run | None:
    """The repo's running or paused repo-scoped root run, if any."""
    rows = store.select(
        db,
        Run,
        "repo_id = ? AND feature_id IS NULL AND parent_run_id IS NULL AND status IN (?, ?)",
        (repo.id, RunStatus.RUNNING.value, RunStatus.PAUSED.value),
        "created_at DESC",
    )
    return rows[0] if rows else None


def pending(home: Home, repo: Repo, clarity_branch: str) -> list[questions.Question]:
    """The repo's pending questions, in the order they're asked."""
    where = workdir(home, repo, clarity_branch)
    if where is None:
        return []
    return questions.pending(questions.load(where / QUESTIONS_PATH))


def answer(
    db: Database,
    home: Home,
    repo: Repo,
    clarity_branch: str,
    answers: Mapping[str, str],
    by: str,
) -> Answered:
    """Record ``answers`` (all or nothing) and say which paused run they unblock."""
    if not answers:
        raise InputError("no answers given")
    where = workdir(home, repo, clarity_branch)
    if where is None or not (where / QUESTIONS_PATH).is_file():
        raise InputError(f"Repo {repo.name} has no clarity questions; start with compose clarity")
    recorded = questions.record(where / QUESTIONS_PATH, answers, by, datetime.now(UTC))
    return Answered(recorded, resumable(db, home, repo))


def resumable(db: Database, home: Home, repo: Repo) -> Run | None:
    """The paused clarity run whose asked questions are all answered (approvals aside)."""
    run = active_run(db, repo)
    if run is None or run.status is not RunStatus.PAUSED:
        return None
    waiting = views.waiting_questions(home, run)
    if waiting is None:
        return None
    holding = [q for q in waiting if q.get("kind") not in NOT_HOLDING]
    return None if holding else run


def merge_if_passing(repo: Repo, where: Path) -> branch.MergeOutcome:
    """Merge the clarity branch only on a recorded PASS that still describes the documents."""
    path = where / verdicts.VERDICT_FILE
    recorded = verdicts.from_text(path.read_text(encoding="utf-8")) if path.is_file() else None
    try:
        if recorded is None or not recorded.verdict.passed:
            return branch.MergeOutcome(False, "no PASS verdict is recorded")
        if recorded.fingerprint != fingerprint.of_dir(where):
            return branch.MergeOutcome(
                False, "the clarity documents changed since the verdict; validate again"
            )
        return branch.merge_into_default(repo, where)
    except (git.GitError, RunError, OSError) as exc:
        return branch.MergeOutcome(False, f"could not merge: {exc}")


def merge(db: Database, home: Home, repo: Repo, clarity_branch: str) -> branch.MergeOutcome:
    """``compose clarity merge``: retry merging a passing clarity branch."""
    where = workdir(home, repo, clarity_branch)
    if where is None:
        raise RunError(f"Repo {repo.name} has no {clarity_branch} branch; run compose clarity")
    running = active_run(db, repo)
    if running is not None and running.status is RunStatus.RUNNING:
        raise RunError(f"Clarity run {running.id} is running; merge after it stops")
    return merge_if_passing(repo, where)


def status(db: Database, home: Home, repo: Repo, clarity_branch: str) -> dict[str, Any]:
    """Free, no model call: documents, verdict, questions, constitution and build readiness."""
    is_started = started(repo, clarity_branch)
    where = workdir(home, repo, clarity_branch) if is_started else None
    root = where or Path(repo.path)  # clarity done in the user's own checkout
    run = active_run(db, repo)
    checked = preflight.check(repo, clarity_branch=clarity_branch)
    data: dict[str, Any] = {
        "repo": repo.name,
        "started": is_started,
        "branch": clarity_branch,
        "worktree": str(where) if where else None,
        "documents": {},
        "fingerprint": None,
        "verdict": None,
        "questions": {"pending": 0, "holding": 0, "ids": []},
        "constitution": {"fingerprint": None, "current": False},
        "active_run": views.run_brief(db, run) if run else None,
        "build": {
            "ok": checked.ok,
            "problems": [{"message": p.message, "fix": p.fix} for p in checked.problems],
            "warnings": checked.warnings,
        },
    }
    if not is_started:
        return data
    found = summary.summary(root)
    data["documents"] = found["documents"] if found else {}
    fp = fingerprint.of_dir(root)
    data["fingerprint"] = fp
    path = root / verdicts.VERDICT_FILE
    recorded = verdicts.from_text(path.read_text(encoding="utf-8")) if path.is_file() else None
    if recorded is not None:
        data["verdict"] = {
            "result": recorded.verdict.result,
            "incomplete": recorded.verdict.incomplete,
            "fingerprint": recorded.fingerprint,
            "run_id": recorded.run_id,
            "at": recorded.at,
            "current": recorded.fingerprint == fp,
        }
    try:
        waiting = questions.pending(questions.load(root / QUESTIONS_PATH))
    except InputError as exc:
        data["questions"]["error"] = str(exc)
        waiting = []
    data["questions"].update(
        pending=len(waiting),
        holding=sum(1 for q in waiting if q.kind not in NOT_HOLDING),
        ids=[q.id for q in waiting],
    )
    file = root / constitution.CONSTITUTION_FILE
    stamped = constitution.read_text(file.read_text(encoding="utf-8")) if file.is_file() else None
    data["constitution"] = {"fingerprint": stamped, "current": stamped == fp}
    return data


def spec_input(definition: Workflow) -> str:
    """The input ``compose build`` puts the description in: the first required string."""
    for name, spec in definition.inputs.items():
        if spec.required and spec.type is InputType.STRING:
            return name
    raise InputError(
        f"Workflow {definition.id} has no required string input to take the description;"
        " use compose run with -i instead"
    )


def build_inputs(
    definition: Workflow, description: str, inputs: Mapping[str, Any] | None
) -> dict[str, Any]:
    name = spec_input(definition)
    given = dict(inputs or {})
    if name in given:
        raise InputError(f"Input {name!r} is the build description; don't also give it as input")
    return {**given, name: description}
