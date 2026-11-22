"""Repos registered with compose (local clones, or cloned by compose from a URL)."""

from __future__ import annotations

import re
import shutil
from pathlib import Path

from compose.core import store
from compose.core.db import Database
from compose.core.home import Home
from compose.core.ids import new_id
from compose.core.models import Repo
from compose.repos import git

_URL_RE = re.compile(r"^(?:[a-z][a-z0-9+.-]*://|[\w.-]+@[\w.-]+:)", re.IGNORECASE)
_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9._-]*$")


class RepoError(Exception):
    """A repo cannot be added, found or removed."""


def is_url(source: str) -> bool:
    return bool(_URL_RE.match(source))


def name_from_source(source: str) -> str:
    base = source.rstrip("/").rsplit("/", 1)[-1].rsplit(":", 1)[-1]
    base = base.removesuffix(".git")
    name = re.sub(r"[^a-z0-9._-]+", "-", base.lower()).strip("-._")
    return name or "repo"


def _check_name(db: Database, name: str) -> None:
    if not _NAME_RE.match(name):
        raise RepoError(
            f"Invalid repo name {name!r}: use lowercase letters, digits, '.', '_' or '-'"
        )
    if store.select(db, Repo, "name = ?", (name,)):
        raise RepoError(f"A repo named {name!r} is already registered; pass --name")


def add_repo(db: Database, home: Home, source: str, *, name: str | None = None) -> Repo:
    """Register a local git checkout, or clone ``source`` (a URL) into the compose home."""
    if is_url(source):
        repo_name = name or name_from_source(source)
        _check_name(db, repo_name)
        dest = home.repos / repo_name
        if dest.exists():
            raise RepoError(f"{dest} already exists; remove it or pass a different --name")
        try:
            git.clone(source, dest)
        except git.GitError as exc:
            shutil.rmtree(dest, ignore_errors=True)
            raise RepoError(f"Cannot clone {source}: {exc.stderr.strip()}") from exc
        path = dest.resolve()
    else:
        candidate = Path(source).expanduser().resolve()
        if not git.is_work_tree(candidate):
            raise RepoError(f"{candidate} is not a git working tree")
        path = git.main_worktree(candidate)
        repo_name = name or name_from_source(path.name)
        existing = store.select(db, Repo, "path = ?", (str(path),))
        if existing:
            raise RepoError(f"{path} is already registered as {existing[0].name!r}")
        _check_name(db, repo_name)

    repo = Repo(
        id=new_id("repo"),
        name=repo_name,
        path=str(path),
        origin_url=git.origin_url(path),
        default_branch=git.default_branch(path),
    )
    return store.insert(db, repo)


def list_repos(db: Database) -> list[Repo]:
    return store.select(db, Repo, order_by="name")


def get_repo(db: Database, ref: str) -> Repo:
    """Find a repo by id or name."""
    found = store.select(db, Repo, "id = ? OR name = ?", (ref, ref))
    if not found:
        raise RepoError(f"No registered repo {ref!r} (see `compose repo list`)")
    return found[0]


def find_repo_for_path(db: Database, path: Path) -> Repo | None:
    """The registered repo whose checkout (or one of its worktrees) contains ``path``."""
    path = path.expanduser().resolve()
    if not git.is_work_tree(path):
        return None
    root = git.main_worktree(path)
    found = store.select(db, Repo, "path = ?", (str(root),))
    return found[0] if found else None


def resolve_repo(db: Database, ref: str | None, cwd: Path) -> Repo:
    """``--repo`` if given, else the registered repo containing ``cwd``."""
    if ref:
        return get_repo(db, ref)
    repo = find_repo_for_path(db, cwd)
    if repo is None:
        raise RepoError(
            "Not inside a registered repo; pass --repo or run `compose repo add <path>`"
        )
    return repo


def remove_repo(
    db: Database, home: Home, ref: str, *, delete_clone: bool = False, force: bool = False
) -> Repo:
    """Unregister a repo. Refuses when it has run history, unless ``force``."""
    repo = get_repo(db, ref)
    runs = db.conn.execute("SELECT COUNT(*) FROM runs WHERE repo_id = ?", (repo.id,)).fetchone()
    if runs[0] and not force:
        raise RepoError(
            f"{repo.name!r} has {runs[0]} run(s); removing it deletes their history."
            " Pass --force to remove anyway"
        )
    path = Path(repo.path)
    if delete_clone and not path.is_relative_to(home.repos):
        raise RepoError(f"{path} was not cloned by compose; refusing to delete it")
    with db.transaction() as conn:
        conn.execute("DELETE FROM repos WHERE id = ?", (repo.id,))
    if delete_clone:
        shutil.rmtree(path, ignore_errors=True)
    return repo
