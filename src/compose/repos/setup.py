"""Making a repository ready for compose (``compose init``) and checking it (``compose check``)."""

from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from pathlib import Path

from compose.core.db import Database
from compose.core.home import Home
from compose.core.models import Repo
from compose.engines.claude.install import ASSETS
from compose.engines.registry import EngineRegistry
from compose.repos import git, registry
from compose.repos.git import GitError
from compose.tracking.snapshot import EXCLUDED

CONSTITUTION = Path(".compose") / "memory" / "constitution.md"
GITIGNORE_HEADER = "# compose: local state"
GITIGNORE_ENTRIES = [f"/{p}/" for p in EXCLUDED]
MARKER_SKILLS = (
    Path(".claude") / "skills" / "compose-specify" / "SKILL.md",
    Path(".github") / "skills" / "compose-specify" / "SKILL.md",
)


@dataclass
class InitReport:
    root: Path
    repo: Repo
    registered: bool  # newly registered by this init
    written: list[Path] = field(default_factory=list)

    def to_commit(self) -> list[str]:
        return sorted(p.relative_to(self.root).as_posix() for p in self.written)


def _ensure_gitignore(root: Path) -> Path | None:
    path = root / ".gitignore"
    lines = path.read_text().splitlines() if path.exists() else []
    missing = [entry for entry in GITIGNORE_ENTRIES if entry not in lines]
    if not missing:
        return None
    if lines and lines[-1].strip():
        lines.append("")
    if GITIGNORE_HEADER not in lines:
        lines.append(GITIGNORE_HEADER)
    lines.extend(missing)
    path.write_text("\n".join(lines) + "\n")
    return path


def init_repo(
    db: Database, home: Home, path: Path, engines: EngineRegistry, engine: str
) -> InitReport:
    """Install the engine's skills and compose's templates, add a starter constitution and
    ``.gitignore`` entries, and register the repo. Commits nothing; safe to repeat."""
    root = git.toplevel(path.expanduser().resolve())
    adapter = engines.get(engine)
    existing = registry.find_repo_for_path(db, root)
    if existing is not None and Path(existing.path) != root:
        raise registry.RepoError(
            f"{root} is a worktree of {existing.path}; run compose init in the main checkout"
        )
    repo = existing or registry.add_repo(db, home, str(root))
    report = InitReport(root=root, repo=repo, registered=existing is None)
    report.written.extend(adapter.install(root))
    constitution = root / CONSTITUTION
    if not constitution.exists():
        constitution.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ASSETS / "templates" / "compose" / "constitution.md", constitution)
        report.written.append(constitution)
    gitignore = _ensure_gitignore(root)
    if gitignore is not None:
        report.written.append(gitignore)
    return report


# ------------------------------------------------------------------------ check


@dataclass(frozen=True)
class CheckItem:
    name: str
    ok: bool
    detail: str
    fix: str | None = None
    required: bool = True

    def to_json(self) -> dict[str, object]:
        return {
            "name": self.name,
            "ok": self.ok,
            "detail": self.detail,
            "fix": self.fix,
            "required": self.required,
        }


def check_all(db: Database, cwd: Path, engines: EngineRegistry, engine: str) -> list[CheckItem]:
    """Everything compose needs, each with how to fix it."""
    items: list[CheckItem] = []
    git_path = shutil.which("git")
    if git_path is None:
        items.append(CheckItem("git", False, "git is not on PATH", "install git"))
    else:
        version = git.run_git(cwd, "--version", check=False).stdout.strip()
        items.append(CheckItem("git", True, version or git_path))

    try:
        adapter = engines.get(engine)
    except Exception as exc:  # unknown engine name
        fix = f"use --engine {' or '.join(engines.names())}"
        items.append(CheckItem(f"engine {engine}", False, str(exc), fix))
    else:
        problems = adapter.check()
        items.append(
            CheckItem(
                f"engine {engine}",
                not problems,
                "; ".join(problems) or "ready",
                None if not problems else "see the message above",
            )
        )

    if not git.is_work_tree(cwd):
        items.append(
            CheckItem(
                "repository",
                False,
                f"{cwd} is not inside a git repository",
                "cd into a repository, or register one with `compose repo add <path|url>`",
                required=False,
            )
        )
        return items
    try:
        root = git.main_worktree(cwd)
    except GitError as exc:
        items.append(CheckItem("repository", False, str(exc), None, required=False))
        return items
    repo = registry.find_repo_for_path(db, root)
    items.append(
        CheckItem(
            "repository registered",
            repo is not None,
            f"{root}" + (f" as {repo.name} ({repo.id})" if repo else " is not registered"),
            None if repo else "run `compose init` here",
        )
    )
    initialized = any((root / m).exists() for m in MARKER_SKILLS) and (root / CONSTITUTION).exists()
    items.append(
        CheckItem(
            "repository initialized",
            initialized,
            "skills and constitution present"
            if initialized
            else "compose skills or the constitution are missing in this checkout",
            None if initialized else "run `compose init` here",
            # runs install the skills into their worktrees anyway
            required=False,
        )
    )
    return items
