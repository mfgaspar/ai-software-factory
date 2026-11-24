"""The clarity branch: its worktree, updates from the default branch, commits and merges."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest

from compose.clarity import branch
from compose.core.db import Database
from compose.core.home import Home
from compose.core.models import Repo
from compose.repos import git, registry
from compose.runner.errors import RunError

Git = Callable[..., str]


@pytest.fixture
def repo(db: Database, home: Home, git_repo: Path) -> Repo:
    return registry.add_repo(db, home, str(git_repo))


def _commit(run_git: Git, cwd: Path, path: str, text: str, message: str = "change") -> str:
    target = cwd / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text)
    run_git(cwd, "add", path)
    run_git(cwd, "commit", "-q", "-m", message)
    return run_git(cwd, "rev-parse", "HEAD")


def test_creates_branch_and_worktree(home: Home, repo: Repo, git_repo: Path) -> None:
    workdir = branch.ensure_worktree(home, repo)
    assert workdir == (home.worktrees / repo.name / "clarity").resolve()
    assert git.current_branch(workdir) == "clarity"
    assert git.rev_parse(git_repo, "clarity") == git.rev_parse(git_repo, "main")
    assert branch.ensure_worktree(home, repo) == workdir  # idempotent


def test_branch_name_is_configurable(home: Home, repo: Repo) -> None:
    workdir = branch.ensure_worktree(home, repo, branch="docs-clarity")
    assert git.current_branch(workdir) == "docs-clarity"


def test_updates_from_moved_default(home: Home, repo: Repo, git_repo: Path, run_git: Git) -> None:
    workdir = branch.ensure_worktree(home, repo)
    _commit(run_git, workdir, ".clarity/product/prd.md", "prd\n")
    moved = _commit(run_git, git_repo, "src/app.py", "print()\n")
    branch.ensure_worktree(home, repo)
    assert git.is_ancestor(git_repo, moved, "clarity")
    assert (workdir / "src/app.py").exists() and (workdir / ".clarity/product/prd.md").exists()
    assert git.rev_parse(git_repo, "main") == moved


def test_conflict_refuses_and_leaves_branches(
    home: Home, repo: Repo, git_repo: Path, run_git: Git
) -> None:
    workdir = branch.ensure_worktree(home, repo)
    ours = _commit(run_git, workdir, "README.md", "clarity side\n")
    theirs = _commit(run_git, git_repo, "README.md", "main side\n")
    with pytest.raises(RunError, match="conflicts in: README.md"):
        branch.ensure_worktree(home, repo)
    assert git.rev_parse(git_repo, "clarity") == ours
    assert git.rev_parse(git_repo, "main") == theirs
    assert git.changed_paths(workdir) == []
    assert not (Path(run_git(workdir, "rev-parse", "--git-dir")) / "MERGE_HEAD").exists()


def test_commit_paths_only_commits_clarity_files(home: Home, repo: Repo, run_git: Git) -> None:
    workdir = branch.ensure_worktree(home, repo)
    assert branch.commit_paths(workdir, "clarity: nothing") is None
    (workdir / ".clarity").mkdir()
    (workdir / ".clarity" / "questions.yml").write_text("[]\n")
    (workdir / ".compose" / "memory").mkdir(parents=True)
    (workdir / ".compose" / "memory" / "constitution.md").write_text("# Constitution\n")
    (workdir / ".compose" / "memory" / "goal").mkdir()
    (workdir / ".compose" / "memory" / "goal" / "problem.md").write_text("# Problem\n")
    (workdir / ".compose" / "templates").mkdir()
    (workdir / ".compose" / "templates" / "spec.md").write_text("not mine\n")
    (workdir / "README.md").write_text("edited\n")
    (workdir / "other.txt").write_text("untracked\n")
    run_git(workdir, "add", "other.txt")  # staged by someone else: still not committed
    sha = branch.commit_paths(workdir, "clarity: draft run run_1")
    assert sha == git.rev_parse(workdir, "HEAD")
    committed = run_git(workdir, "show", "--name-only", "--format=%s", "HEAD").splitlines()
    assert committed[0] == "clarity: draft run run_1"
    assert sorted(filter(None, committed[1:])) == [
        ".clarity/questions.yml",
        ".compose/memory/constitution.md",
        ".compose/memory/goal/problem.md",
    ]
    assert set(git.changed_paths(workdir)) >= {"README.md", "other.txt"}
    assert branch.commit_paths(workdir, "again") is None


def test_fast_forwards_checked_out_clean_default(
    home: Home, repo: Repo, git_repo: Path, run_git: Git
) -> None:
    workdir = branch.ensure_worktree(home, repo)
    tip = _commit(run_git, workdir, ".clarity/product/prd.md", "prd\n")
    (git_repo / "scratch.txt").write_text("user's own work elsewhere\n")
    outcome = branch.merge_into_default(repo, workdir)
    assert outcome == branch.MergeOutcome(merged=True)
    assert git.rev_parse(git_repo, "main") == tip
    assert (git_repo / ".clarity/product/prd.md").read_text() == "prd\n"


def test_updates_ref_when_default_not_checked_out(
    home: Home, repo: Repo, git_repo: Path, run_git: Git
) -> None:
    run_git(git_repo, "switch", "-q", "-c", "elsewhere")
    workdir = branch.ensure_worktree(home, repo)
    tip = _commit(run_git, workdir, ".clarity/product/prd.md", "prd\n")
    assert branch.merge_into_default(repo, workdir).merged
    assert git.rev_parse(git_repo, "main") == tip
    assert git.current_branch(git_repo) == "elsewhere"


def test_pending_when_checkout_has_dirty_clarity(
    home: Home, repo: Repo, git_repo: Path, run_git: Git
) -> None:
    workdir = branch.ensure_worktree(home, repo)
    _commit(run_git, workdir, ".clarity/product/prd.md", "prd\n")
    before = git.rev_parse(git_repo, "main")
    (git_repo / ".clarity").mkdir()
    (git_repo / ".clarity" / "draft.md").write_text("mine\n")
    outcome = branch.merge_into_default(repo, workdir)
    assert not outcome.merged
    assert "uncommitted changes" in (outcome.pending_reason or "")
    assert git.rev_parse(git_repo, "main") == before


def test_pending_when_default_diverged(
    home: Home, repo: Repo, git_repo: Path, run_git: Git
) -> None:
    workdir = branch.ensure_worktree(home, repo)
    _commit(run_git, workdir, ".clarity/product/prd.md", "prd\n")
    moved = _commit(run_git, git_repo, "src/app.py", "print()\n")
    outcome = branch.merge_into_default(repo, workdir)
    assert outcome == branch.MergeOutcome(False, "default branch moved; re-validate")
    assert git.rev_parse(git_repo, "main") == moved
    assert git.is_ancestor(git_repo, moved, "clarity")  # merged into clarity for re-checking
    assert branch.merge_into_default(repo, workdir).merged  # next time it fast-forwards


def test_commit_paths_commits_a_removed_memory_file(home: Home, repo: Repo, run_git: Git) -> None:
    workdir = branch.ensure_worktree(home, repo)
    folder = workdir / ".compose" / "memory" / "product"
    folder.mkdir(parents=True)
    (folder / "prd.md").write_text("# PRD\n")
    (workdir / ".compose" / "memory" / "constitution.md").write_text("# Index\n")
    assert branch.commit_paths(workdir, "clarity: one") is not None
    (folder / "prd.md").unlink()
    assert branch.commit_paths(workdir, "clarity: two") is not None
    tracked = run_git(workdir, "ls-files", "--", ".compose/memory").splitlines()
    assert tracked == [".compose/memory/constitution.md"]
    assert git.changed_paths(workdir) == []
