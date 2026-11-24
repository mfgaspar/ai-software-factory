"""Find the GitHub Copilot CLI and check it can run.

Copilot's own place for project skills is ``.github/skills``, so compose installs its skills
there (the templates go to ``.compose/templates``, as for Claude Code). Copilot also reads
``.claude/skills``, which the Claude engine fills; a checkout that uses both has both.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from compose.engines.claude import install as _claude

__all__ = ["SKILLS_DIR", "check", "cli_path", "install", "version"]

SKILLS_DIR = Path(".github") / "skills"


def install(path: Path, *, worktree: bool = False) -> list[Path]:
    """Put compose's skills in ``.github/skills`` and its templates in ``.compose``."""
    return _claude.install(path, worktree=worktree, skills_dir=SKILLS_DIR)


def cli_path() -> str | None:
    """The copilot executable compose runs: the one on PATH."""
    return shutil.which("copilot")


def check() -> list[str]:
    """Problems that stop compose from running Copilot (empty when ready).

    Copilot has no command that reports whether it is signed in, so that is not checked:
    a step run while signed out fails with Copilot's own message.
    """
    cli = cli_path()
    if cli is None:
        return ["GitHub Copilot CLI is not installed (no `copilot` on PATH)"]
    try:
        proc = subprocess.run(
            [cli, "--version"], capture_output=True, text=True, timeout=30, check=False
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return [f"cannot run {cli}: {exc}"]
    if proc.returncode != 0:
        return [f"`{cli} --version` failed: {proc.stderr.strip()}"]
    return []


def version() -> str | None:
    cli = cli_path()
    if cli is None:
        return None
    proc = subprocess.run([cli, "--version"], capture_output=True, text=True, check=False)
    lines = proc.stdout.strip().splitlines()
    return lines[0].rstrip(".") if lines else None
