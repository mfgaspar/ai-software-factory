"""The compose home directory (``$COMPOSE_HOME``, default ``~/.compose``)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

HOME_ENV = "COMPOSE_HOME"


def home_root() -> Path:
    """Resolve the compose home root without creating it."""
    raw = os.environ.get(HOME_ENV)
    root = Path(raw) if raw else Path.home() / ".compose"
    return root.expanduser().resolve()


@dataclass(frozen=True)
class Home:
    """Well-known locations inside the compose home."""

    root: Path

    @property
    def runs(self) -> Path:
        return self.root / "runs"

    @property
    def repos(self) -> Path:
        return self.root / "repos"

    @property
    def worktrees(self) -> Path:
        return self.root / "worktrees"

    @property
    def db_path(self) -> Path:
        return self.root / "compose.db"

    @property
    def config_path(self) -> Path:
        return self.root / "config.yml"

    def run_dir(self, run_id: str) -> Path:
        return self.runs / run_id


def ensure_home(root: Path | None = None) -> Home:
    """Return the compose home, creating its directories if needed."""
    home = Home(root.expanduser().resolve() if root else home_root())
    for path in (home.root, home.runs, home.repos, home.worktrees):
        path.mkdir(parents=True, exist_ok=True)
    return home
