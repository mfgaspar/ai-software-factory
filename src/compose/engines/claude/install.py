"""Put compose's skills and templates where Claude Code finds them, and check readiness."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

from compose.repos.git import git, run_git

ASSETS = Path(__file__).resolve().parents[2] / "assets"
SKILLS_DIR = Path(".claude") / "skills"
TEMPLATES_DIR = Path(".compose") / "templates"
EXCLUDE_BEGIN = "# >>> compose: installed files (managed by compose)"
EXCLUDE_END = "# <<< compose"


SKILL_PREFIXES = ("compose", "clarity")
# Templates that are shipped data rather than starting points, refreshed like skills.
REFRESHED_TEMPLATES = {Path("clarity") / "manifest.yml"}


def _planned(assets: Path, skills_dir: Path = SKILLS_DIR) -> list[tuple[Path, Path, bool]]:
    """(source, target relative to the repo, overwrite) for every installable file.

    Skills (compose's and the clarity family) are refreshed; templates are only added when
    missing, so local edits to them survive. The clarity manifest is the exception: the
    clarity skills read it as their source of truth, so it is refreshed with them.
    """
    planned: list[tuple[Path, Path, bool]] = []
    skills = assets / "skills"
    if skills.is_dir():
        for skill in sorted(p for p in skills.iterdir() if p.name.startswith(SKILL_PREFIXES)):
            for src in sorted(p for p in skill.rglob("*") if p.is_file()):
                planned.append((src, skills_dir / skill.name / src.relative_to(skill), True))
    templates = assets / "templates"
    if templates.is_dir():
        for src in sorted(p for p in templates.rglob("*") if p.is_file()):
            relative = src.relative_to(templates)
            planned.append((src, TEMPLATES_DIR / relative, relative in REFRESHED_TEMPLATES))
    return planned


def _tracked(path: Path, relative: Path) -> bool:
    proc = run_git(path, "ls-files", "--error-unmatch", "--", str(relative), check=False)
    return proc.returncode == 0


def _exclude_patterns(written: list[Path], skills_dir: Path = SKILLS_DIR) -> list[str]:
    patterns: set[str] = set()
    for rel in written:
        if rel.parts[: len(skills_dir.parts)] == skills_dir.parts:
            patterns.add(f"/{skills_dir.as_posix()}/{rel.parts[len(skills_dir.parts)]}/")
        else:
            patterns.add(f"/{rel.as_posix()}")
    return sorted(patterns)


def _update_exclude(path: Path, patterns: list[str]) -> None:
    """Hide compose-installed files from git in this worktree (and so from tracking)."""
    exclude = Path(git(path, "rev-parse", "--git-path", "info/exclude"))
    if not exclude.is_absolute():
        exclude = path / exclude
    lines = exclude.read_text().splitlines() if exclude.exists() else []
    if EXCLUDE_BEGIN in lines and EXCLUDE_END in lines:
        start, end = lines.index(EXCLUDE_BEGIN), lines.index(EXCLUDE_END)
        previous = set(lines[start + 1 : end])
        lines = lines[:start] + lines[end + 1 :]
    else:
        previous = set()
    block = sorted(previous | set(patterns))
    if block:
        lines += [EXCLUDE_BEGIN, *block, EXCLUDE_END]
    exclude.parent.mkdir(parents=True, exist_ok=True)
    exclude.write_text("\n".join(lines) + "\n")


def install(
    path: Path,
    *,
    worktree: bool = False,
    assets: Path = ASSETS,
    skills_dir: Path = SKILLS_DIR,
) -> list[Path]:
    """Install skills into ``<path>/<skills_dir>`` (``.claude/skills`` by default) and
    templates into ``<path>/.compose/templates``; return the files written (absolute)."""
    written: list[Path] = []
    for src, rel, overwrite in _planned(assets, skills_dir):
        target = path / rel
        if worktree and _tracked(path, rel):
            continue  # the repo's committed version wins
        if target.exists() and not overwrite:
            continue
        if target.exists() and target.read_bytes() == src.read_bytes():
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, target)
        written.append(target)
    if worktree:
        untracked = [rel for _, rel, _ in _planned(assets, skills_dir) if not _tracked(path, rel)]
        if untracked:
            _update_exclude(path, _exclude_patterns(untracked, skills_dir))
    return written


# ------------------------------------------------------------------------ check


def bundled_cli() -> str | None:
    """The claude executable shipped inside the Claude Agent SDK, if any."""
    try:
        import claude_agent_sdk
    except ImportError:
        return None
    name = "claude.exe" if os.name == "nt" else "claude"
    bundled = Path(claude_agent_sdk.__file__).parent / "_bundled" / name
    return str(bundled) if bundled.is_file() else None


def cli_path() -> str | None:
    """The claude executable compose runs: the one on PATH, else the SDK's bundled one."""
    return shutil.which("claude") or bundled_cli()


def check() -> list[str]:
    """Problems that stop compose from running Claude Code (empty when ready)."""
    try:
        import claude_agent_sdk  # noqa: F401
    except ImportError:
        return ["the claude-agent-sdk package is not installed"]
    cli = cli_path()
    if cli is None:
        return ["Claude Code is not installed (no bundled CLI and no `claude` on PATH)"]
    try:
        version = subprocess.run(
            [cli, "--version"], capture_output=True, text=True, timeout=30, check=False
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return [f"cannot run {cli}: {exc}"]
    if version.returncode != 0:
        return [f"`{cli} --version` failed: {version.stderr.strip()}"]
    if os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("CLAUDE_CODE_OAUTH_TOKEN"):
        return []
    try:
        status = subprocess.run(
            [cli, "auth", "status"], capture_output=True, text=True, timeout=30, check=False
        )
        logged_in = bool(json.loads(status.stdout or "{}").get("loggedIn"))
    except (OSError, subprocess.TimeoutExpired, json.JSONDecodeError):
        logged_in = False
    if not logged_in:
        return ["Claude Code is not signed in: run `claude auth login` or set ANTHROPIC_API_KEY"]
    return []


def version() -> str | None:
    cli = cli_path()
    if cli is None:
        return None
    proc = subprocess.run([cli, "--version"], capture_output=True, text=True, check=False)
    return proc.stdout.strip() or None
