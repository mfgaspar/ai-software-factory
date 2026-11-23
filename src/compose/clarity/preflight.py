"""The pre-run check for feature runs: is the clarity foundation on the default branch current?

It reads the **local** default branch through git (no checkout, no fetch): that's what a
feature worktree branches from. A repo that hasn't started clarity (no ``.clarity/`` on the
default branch and no clarity branch) only gets a warning. One that has must have a recorded
PASS and a constitution generated from the same fingerprint as the default branch's
``.clarity/``; otherwise the run is refused with a fix.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from compose.clarity import branch, constitution, fingerprint, verdict
from compose.core.models import Repo
from compose.repos import git
from compose.runner.errors import RunError

NOT_STARTED = (
    "No clarity foundation: building on a guessed constitution."
    " Run `compose clarity` for a confirmed foundation."
)


@dataclass(frozen=True)
class Problem:
    message: str
    fix: str


@dataclass(frozen=True)
class Preflight:
    problems: list[Problem] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.problems


class PreflightError(RunError):
    """The pre-run check refused a feature run; ``problems`` says why and how to fix it."""

    def __init__(self, problems: list[Problem]) -> None:
        self.problems = problems
        lines = [f"{p.message} Fix: {p.fix}" for p in problems]
        super().__init__("\n".join(lines))


def check(repo: Repo, *, clarity_branch: str = branch.DEFAULT_BRANCH) -> Preflight:
    root = Path(repo.path)
    base = branch.default_branch(repo)
    on_default = _exists(root, base) and _has_clarity(root, base)
    if not on_default and not git.branch_exists(root, clarity_branch):
        return Preflight(warnings=[NOT_STARTED + _behind(root, base)])

    problems: list[Problem] = []
    if not on_default:
        if _passes(root, clarity_branch):
            problem = Problem(
                f"Clarity passed on branch `{clarity_branch}` but isn't merged into {base} yet.",
                "compose clarity merge",
            )
        else:
            problem = Problem(
                f"Clarity is in progress on branch `{clarity_branch}` and hasn't passed yet.",
                "compose clarity",
            )
        problems.append(problem)
    else:
        fp = fingerprint.of_ref(root, base)
        recorded = verdict.read_ref(root, base)
        if recorded is None or not recorded.verdict.passed or recorded.fingerprint != fp:
            problems.append(
                Problem(
                    "The clarity foundation doesn't pass (or changed since it was validated).",
                    "compose clarity validate",
                )
            )
        if constitution.read_ref(root, base) != fp:
            problems.append(
                Problem("The constitution is out of date with clarity.", "compose clarity validate")
            )
    hint = _behind(root, base)
    if hint:
        problems = [Problem(p.message + hint, p.fix) for p in problems]
    return Preflight(problems=problems)


def _exists(root: Path, ref: str) -> bool:
    proc = git.run_git(root, "rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}", check=False)
    return proc.returncode == 0


def _has_clarity(root: Path, ref: str) -> bool:
    proc = git.run_git(root, "ls-tree", "--name-only", ref, "--", fingerprint.CLARITY_DIR)
    return bool(proc.stdout.strip())


def _passes(root: Path, ref: str) -> bool:
    """``ref`` has a PASS recorded for the ``.clarity/`` it has."""
    recorded = verdict.read_ref(root, ref)
    return (
        recorded is not None
        and recorded.verdict.passed
        and recorded.fingerprint == fingerprint.of_ref(root, ref)
    )


def _behind(root: Path, base: str) -> str:
    """A "pull first" hint when the local ``base`` is behind its upstream (as git knows)."""
    upstream = git.run_git(
        root, "rev-parse", "--abbrev-ref", "--symbolic-full-name", f"{base}@{{u}}", check=False
    )
    if upstream.returncode != 0 or not upstream.stdout.strip():
        return ""
    counted = git.run_git(root, "rev-list", "--count", f"{base}..{base}@{{u}}", check=False)
    behind = int(counted.stdout.strip() or 0) if counted.returncode == 0 else 0
    if behind <= 0:
        return ""
    name = upstream.stdout.strip()
    return (
        f" Your local {base} is {behind} commit(s) behind {name}: pull first"
        " (clarity merged on the remote reaches builds only after a pull)."
    )
