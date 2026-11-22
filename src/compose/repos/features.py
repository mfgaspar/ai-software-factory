"""Features: one specification each, with a numbered branch and a ``specs/NNN-name/`` folder.

Used both by hand (the skills call ``compose feature new|paths``) and by workflow runs.
Inside a run, ``COMPOSE_FEATURE`` names the run's feature so nothing creates a second one.
"""

from __future__ import annotations

import os
import re
import unicodedata
from dataclasses import asdict, dataclass
from pathlib import Path

from compose.core import store
from compose.core.db import Database
from compose.core.ids import new_id
from compose.core.models import Feature, Repo
from compose.repos import git

FEATURE_ENV = "COMPOSE_FEATURE"
SPECS_DIR = "specs"
NAME_RE = re.compile(r"^(\d{3,})-([a-z0-9]+(?:-[a-z0-9]+)*)$")
MAX_SLUG_WORDS = 4
_STOPWORDS = frozenset(
    {
        "a",
        "an",
        "and",
        "are",
        "as",
        "at",
        "be",
        "by",
        "for",
        "from",
        "i",
        "in",
        "into",
        "is",
        "it",
        "let",
        "me",
        "my",
        "of",
        "on",
        "or",
        "our",
        "please",
        "should",
        "so",
        "that",
        "the",
        "their",
        "this",
        "to",
        "we",
        "want",
        "will",
        "with",
    }
)


class FeatureError(Exception):
    """A feature cannot be created or resolved."""


def slugify(text: str, *, max_words: int = MAX_SLUG_WORDS) -> str:
    """``"Add user authentication with OAuth"`` -> ``"add-user-authentication-oauth"``."""
    ascii_text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    words = re.findall(r"[a-z0-9]+", ascii_text.lower())
    meaningful = [w for w in words if w not in _STOPWORDS] or words
    return "-".join(meaningful[:max_words]) or "feature"


def format_name(number: int, slug: str) -> str:
    return f"{number:03d}-{slug}"


def parse_name(name: str) -> tuple[int, str] | None:
    match = NAME_RE.match(name)
    return (int(match.group(1)), match.group(2)) if match else None


def next_number(root: Path) -> int:
    """One more than the highest feature number in branches or ``specs/`` folders."""
    names = git.local_branches(root) + git.remote_branches(root)
    specs = root / SPECS_DIR
    if specs.is_dir():
        names += [p.name for p in specs.iterdir() if p.is_dir()]
    numbers = [parsed[0] for n in names if (parsed := parse_name(n))]
    return max(numbers, default=0) + 1


def allocate_name(root: Path, text: str, *, short_name: str | None = None) -> str:
    """The name the next feature would get, e.g. ``"004-user-auth"``."""
    return format_name(next_number(root), slugify(short_name or text))


@dataclass(frozen=True)
class FeaturePaths:
    """Where a feature's files live in one checkout."""

    name: str
    number: int
    branch: str
    repo_root: Path
    feature_dir: Path
    spec_file: Path
    plan_file: Path
    tasks_file: Path
    research_file: Path
    checklists_dir: Path
    constitution_file: Path
    templates_dir: Path

    def to_json(self) -> dict[str, object]:
        return {k: str(v) if isinstance(v, Path) else v for k, v in asdict(self).items()}


def feature_paths(root: Path, name: str) -> FeaturePaths:
    parsed = parse_name(name)
    if parsed is None:
        raise FeatureError(f"{name!r} is not a feature name (expected NNN-short-name)")
    feature_dir = root / SPECS_DIR / name
    return FeaturePaths(
        name=name,
        number=parsed[0],
        branch=name,
        repo_root=root,
        feature_dir=feature_dir,
        spec_file=feature_dir / "spec.md",
        plan_file=feature_dir / "plan.md",
        tasks_file=feature_dir / "tasks.md",
        research_file=feature_dir / "research.md",
        checklists_dir=feature_dir / "checklists",
        constitution_file=root / ".compose" / "memory" / "constitution.md",
        templates_dir=root / ".compose" / "templates",
    )


def _root_of(cwd: Path) -> Path:
    if not git.is_work_tree(cwd):
        raise FeatureError(f"{cwd} is not inside a git working tree")
    return git.toplevel(cwd)


def resolve_current(cwd: Path) -> FeaturePaths:
    """The active feature: ``COMPOSE_FEATURE`` if set, else the current branch."""
    root = _root_of(cwd)
    env_name = os.environ.get(FEATURE_ENV)
    if env_name:
        return feature_paths(root, env_name)
    branch = git.current_branch(root)
    if branch is None or parse_name(branch) is None:
        raise FeatureError(
            f"Current branch {branch or '(detached)'} is not a feature branch;"
            " run `compose feature new` or switch to an NNN-name branch"
        )
    return feature_paths(root, branch)


def create_feature(
    cwd: Path, text: str, *, short_name: str | None = None, switch: bool = True
) -> tuple[FeaturePaths, bool]:
    """Create a feature in the current checkout (manual use).

    Returns ``(paths, created)``. Inside a workflow run (``COMPOSE_FEATURE`` set) this
    returns the run's feature with ``created=False`` and changes nothing.
    """
    if os.environ.get(FEATURE_ENV):
        return resolve_current(cwd), False
    root = _root_of(cwd)
    name = allocate_name(root, text, short_name=short_name)
    if switch:
        git.switch_new_branch(root, name)
    else:
        git.create_branch(root, name, "HEAD")
    paths = feature_paths(root, name)
    paths.feature_dir.mkdir(parents=True, exist_ok=True)
    return paths, True


@dataclass(frozen=True)
class FeatureSummary:
    name: str
    number: int
    has_branch: bool
    has_dir: bool


def list_features(root: Path) -> list[FeatureSummary]:
    branches = set(git.local_branches(root)) | set(git.remote_branches(root))
    specs = root / SPECS_DIR
    dirs = {p.name for p in specs.iterdir() if p.is_dir()} if specs.is_dir() else set()
    summaries = []
    for name in branches | dirs:
        parsed = parse_name(name)
        if parsed:
            summaries.append(FeatureSummary(name, parsed[0], name in branches, name in dirs))
    return sorted(summaries, key=lambda s: (s.number, s.name))


def upsert_feature(db: Database, repo: Repo, name: str) -> Feature:
    """The database record for a feature, created on first use."""
    found = store.select(db, Feature, "repo_id = ? AND name = ?", (repo.id, name))
    if found:
        return found[0]
    parsed = parse_name(name)
    if parsed is None:
        raise FeatureError(f"{name!r} is not a feature name (expected NNN-short-name)")
    return store.insert(
        db,
        Feature(
            id=new_id("feat"),
            repo_id=repo.id,
            number=parsed[0],
            slug=parsed[1],
            name=name,
            branch=name,
        ),
    )
