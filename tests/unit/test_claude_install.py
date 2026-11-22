from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from compose.engines.claude import install as installer
from compose.tracking.diff import diff_trees
from compose.tracking.snapshot import snapshot


def git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=repo, check=True, capture_output=True, text=True
    ).stdout


@pytest.fixture
def assets(tmp_path: Path) -> Path:
    root = tmp_path / "assets"
    for name in ("compose-specify", "compose-plan"):
        skill = root / "skills" / name
        skill.mkdir(parents=True)
        (skill / "SKILL.md").write_text(f"---\nname: {name}\n---\n{name} v1\n")
    (root / "skills" / "compose-plan" / "reference.md").write_text("ref\n")
    (root / "skills" / "other-skill").mkdir()
    (root / "skills" / "other-skill" / "SKILL.md").write_text("not ours\n")
    (root / "templates").mkdir()
    (root / "templates" / "spec.md").write_text("# Spec template\n")
    return root


def rel(paths: list[Path], base: Path) -> list[str]:
    return sorted(p.relative_to(base).as_posix() for p in paths)


def test_install_into_a_repo(git_repo: Path, assets: Path) -> None:
    written = installer.install(git_repo, assets=assets)
    assert rel(written, git_repo) == [
        ".claude/skills/compose-plan/SKILL.md",
        ".claude/skills/compose-plan/reference.md",
        ".claude/skills/compose-specify/SKILL.md",
        ".compose/templates/spec.md",
    ]
    assert installer.install(git_repo, assets=assets) == []  # nothing changed

    (git_repo / ".compose/templates/spec.md").write_text("# My own template\n")
    (assets / "skills/compose-plan/SKILL.md").write_text("compose-plan v2\n")
    again = installer.install(git_repo, assets=assets)
    assert rel(again, git_repo) == [".claude/skills/compose-plan/SKILL.md"]
    assert (git_repo / ".compose/templates/spec.md").read_text() == "# My own template\n"
    exclude = git_repo / ".git" / "info" / "exclude"
    assert installer.EXCLUDE_BEGIN not in (exclude.read_text() if exclude.exists() else "")


def test_install_into_a_run_worktree(git_repo: Path, assets: Path, tmp_path: Path) -> None:
    # the repo commits its own copy of one skill
    committed = git_repo / ".claude/skills/compose-specify/SKILL.md"
    committed.parent.mkdir(parents=True)
    committed.write_text("team version\n")
    git(git_repo, "add", ".")
    git(git_repo, "commit", "-qm", "own specify")
    worktree = tmp_path / "wt"
    git(git_repo, "worktree", "add", "-q", "-b", "001-x", str(worktree))

    before = snapshot(worktree)
    written = installer.install(worktree, worktree=True, assets=assets)
    assert rel(written, worktree) == [
        ".claude/skills/compose-plan/SKILL.md",
        ".claude/skills/compose-plan/reference.md",
        ".compose/templates/spec.md",
    ]
    assert (worktree / ".claude/skills/compose-specify/SKILL.md").read_text() == "team version\n"
    assert git(worktree, "status", "--porcelain") == ""  # installed files are hidden
    assert diff_trees(worktree, before, snapshot(worktree)) == []  # and never tracked

    installer.install(worktree, worktree=True, assets=assets)
    exclude = Path(git(worktree, "rev-parse", "--git-path", "info/exclude").strip())
    exclude = exclude if exclude.is_absolute() else worktree / exclude
    text = exclude.read_text()
    assert text.count(installer.EXCLUDE_BEGIN) == 1
    assert "/.claude/skills/compose-plan/" in text
    assert "/.compose/templates/spec.md" in text
    assert "compose-specify" not in text


def test_check_reports_problems(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(installer, "cli_path", lambda: None)
    assert installer.check() == [
        "Claude Code is not installed (no bundled CLI and no `claude` on PATH)"
    ]

    cli = tmp_path / "claude"
    cli.write_text(
        "#!/bin/sh\n"
        'if [ "$1" = "--version" ]; then echo "9.9.9 (Claude Code)"; exit 0; fi\n'
        "echo '{\"loggedIn\": false}'\n"
    )
    cli.chmod(0o755)
    monkeypatch.setattr(installer, "cli_path", lambda: str(cli))
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("CLAUDE_CODE_OAUTH_TOKEN", raising=False)
    assert installer.check() == [
        "Claude Code is not signed in: run `claude auth login` or set ANTHROPIC_API_KEY"
    ]
    assert installer.version() == "9.9.9 (Claude Code)"
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key-not-real")
    assert installer.check() == []
