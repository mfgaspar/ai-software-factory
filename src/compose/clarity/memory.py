"""Publishing the clarity documents to ``.compose/memory/``.

``.clarity/`` is where the foundation is drafted and approved; ``.compose/memory/`` is the
published result, and the only place the ``compose-*`` skills read. :func:`publish` copies
each clarity document there with its body unchanged, and writes
``.compose/memory/constitution.md`` as an index: one row per file, saying what it holds, when
a feature step reads it, and whether it is binding. No model is involved, so publishing is
free and the same input always gives the same files.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from compose.clarity import constitution
from compose.clarity.summary import CLARITY_DIR, front_matter
from compose.engines.claude.install import ASSETS
from compose.runner.state import atomic_write

MEMORY_DIR = ".compose/memory"
INDEX_NAME = "constitution.md"
PUBLISHED_NAME = ".published"
FEATURE_IDEAS = "feature-ideas.md"
STEPS = ("specify", "clarify", "plan", "tasks", "implement", "analyze")

_MANIFEST = ASSETS / "templates" / "clarity" / "manifest.yml"
_CONFIG = "config.yml"
# Working files the clarity skills keep that aren't documents (as in summary.py).
_SKIPPED = ("failures/brainstorm/", "prototypes/", "templates/")
_ADR = re.compile(r"^decisions/ADR-(\d+)[^/]*\.md$")
_RULE_ID = re.compile(r"\b([A-Z]{1,5})-(\d{3})\b")
_IGNORED_PREFIXES = frozenset({"Q", "ADR"})
_IDEAS_HEADING = re.compile(r"^## Feature ideas[ \t]*$", re.MULTILINE)
_NEXT_HEADING = re.compile(r"^#{1,2} ", re.MULTILINE)

_HOW_TO_USE = """\
This folder is the project's foundation, published by compose from the clarity documents
in `.clarity/`. Do not edit it: change the clarity documents with `/clarity`, and compose
publishes them again.

Read this file at every step, and open only what the step needs:

- **always at** names the steps that must open the file. Open it when your step is listed.
- **when** is a condition. Open the file when it is true of the feature you are working on.
- `binding` files are rules: follow them and cite their IDs. `draft` files aren't confirmed
  yet: mark anything you take from one as an assumption. `ideas` are suggestions.
"""


class PublishError(Exception):
    """The clarity documents can't be published as they are."""


@dataclass(frozen=True)
class PublishResult:
    written: list[str] = field(default_factory=list)  # relative to .compose/memory
    removed: list[str] = field(default_factory=list)
    not_applicable: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class _Row:
    path: str
    holds: str
    read: str
    standing: str


def _load_yaml(path: Path, what: str) -> dict[str, Any]:
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise PublishError(f"{what} is not valid YAML: {exc}") from exc
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise PublishError(f"{what} must be a YAML mapping")
    return data


def _body(text: str) -> str:
    """Everything after the front matter's closing ``---`` line (the hashed body)."""
    end = text.find("\n---", 4)
    after = text.find("\n", end + 1)
    return "" if after == -1 else text[after + 1 :]


def _header(source: str, status: str) -> str:
    return f"<!-- generated from {CLARITY_DIR}/{source} ({status}) by compose; do not edit -->\n"


def _first_heading(body: str) -> str:
    for line in body.splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return ""


def _rule_ids(body: str) -> str:
    """``NFR-001…NFR-014, CON-001`` for the rule IDs a body defines or cites."""
    found: dict[str, list[int]] = {}
    for prefix, number in _RULE_ID.findall(body):
        if prefix not in _IGNORED_PREFIXES:
            found.setdefault(prefix, []).append(int(number))
    parts = []
    for prefix, numbers in found.items():
        low, high = min(numbers), max(numbers)
        first = f"{prefix}-{low:03}"
        parts.append(first if low == high else f"{first}…{prefix}-{high:03}")
    return ", ".join(parts)


def _meta(raw: object, where: str) -> tuple[str, list[str], str]:
    """A ``memory`` block as ``(summary, read_at, read_when)``, validated."""
    if raw is None:
        return "", [], ""
    if not isinstance(raw, dict):
        raise PublishError(f"{where}: memory must be a mapping")
    read_at = raw.get("read_at") or []
    if not isinstance(read_at, list):
        raise PublishError(f"{where}: memory.read_at must be a list of steps")
    steps = [str(step) for step in read_at]
    unknown = [step for step in steps if step not in STEPS]
    if unknown:
        raise PublishError(
            f"{where}: memory.read_at has unknown step(s) {', '.join(unknown)}"
            f" (use {', '.join(STEPS)})"
        )
    return str(raw.get("summary") or "").strip(), steps, str(raw.get("read_when") or "").strip()


def _read(read_at: list[str], read_when: str) -> str:
    parts = []
    if read_at:
        ordered = [step for step in STEPS if step in read_at]
        parts.append(f"always at: {', '.join(ordered)}")
    if read_when:
        parts.append(f"when: {read_when}")
    return "; ".join(parts) or "when: relevant"


def _cell(text: str) -> str:
    return " ".join(text.split()).replace("|", "\\|")


def _feature_ideas(notes: str) -> str:
    """The ``## Feature ideas`` section of ``notes.md``, or "" when there is none."""
    match = _IDEAS_HEADING.search(notes)
    if not match:
        return ""
    rest = notes[match.end() :]
    stop = _NEXT_HEADING.search(rest)
    content = (rest[: stop.start()] if stop else rest).strip()
    return f"# Feature ideas\n\n{content}\n" if content else ""


def _order(paths: list[str], walk_order: list[str]) -> list[str]:
    """Manifest walk order, then other documents by name, then ADRs by number."""
    rank = {path: index for index, path in enumerate(walk_order)}

    def key(path: str) -> tuple[int, int, str]:
        adr = _ADR.match(path)
        if adr:
            return (2, int(adr.group(1)), path)
        if path in rank:
            return (0, rank[path], path)
        return (1, 0, path)

    return sorted(paths, key=key)


def _index(fingerprint: str, rows: list[_Row], not_applicable: dict[str, str]) -> str:
    lines = [constitution.marker(fingerprint), "# Project memory", "", _HOW_TO_USE]
    lines += ["| File | Holds | Read | Standing |", "|---|---|---|---|"]
    for row in rows:
        link = f"[{row.path}]({row.path})"
        lines.append(f"| {link} | {_cell(row.holds)} | {_cell(row.read)} | {row.standing} |")
    if not_applicable:
        lines += ["", "## Not applicable", ""]
        lines += [f"- `{path}`: {reason}" for path, reason in sorted(not_applicable.items())]
    return "\n".join(lines) + "\n"


def _old_published(memory: Path) -> list[str]:
    listing = memory / PUBLISHED_NAME
    if not listing.is_file():
        return []
    return [line.strip() for line in listing.read_text(encoding="utf-8").splitlines() if line]


def _remove_stale(memory: Path, old: list[str], kept: set[str]) -> list[str]:
    removed = []
    root = memory.resolve()
    for relative in old:
        target = (memory / relative).resolve()
        if relative in kept or not target.is_relative_to(root) or not target.is_file():
            continue
        target.unlink()
        removed.append(relative)
        parent = target.parent
        while parent != root and not any(parent.iterdir()):
            parent.rmdir()
            parent = parent.parent
    return removed


def publish(root: Path, fingerprint: str) -> PublishResult:
    """Write ``root/.compose/memory`` from ``root/.clarity``; stamp the index."""
    clarity = root / CLARITY_DIR
    if not clarity.is_dir():
        raise PublishError(f"no {CLARITY_DIR}/ folder to publish")
    manifest = _load_yaml(_MANIFEST, "the clarity manifest")
    config_file = clarity / _CONFIG
    config = _load_yaml(config_file, f"{CLARITY_DIR}/{_CONFIG}") if config_file.is_file() else {}
    shipped: dict[str, Any] = manifest.get("documents") or {}
    custom = config.get("documents") or {}
    if not isinstance(custom, dict):
        raise PublishError(f"{CLARITY_DIR}/{_CONFIG}: documents must be a mapping")
    extras: dict[str, Any] = manifest.get("memory") or {}

    files: dict[str, str] = {}  # memory-relative path -> text
    rows: dict[str, _Row] = {}
    not_applicable: dict[str, str] = {}

    for path in sorted(clarity.rglob("*.md")):
        relative = path.relative_to(clarity).as_posix()
        if relative.startswith(_SKIPPED):
            continue
        data = front_matter(path)
        if data is None or "status" not in data:
            continue
        status = str(data["status"])
        is_adr = _ADR.match(relative) is not None
        if is_adr:
            if status != "accepted":
                continue
        elif status == "n/a":
            not_applicable[relative] = str(data.get("reason") or "").strip() or "no reason given"
            continue
        elif status not in ("complete", "draft"):
            continue
        body = _body(path.read_text(encoding="utf-8"))
        files[relative] = _header(relative, status) + body

        where = f"{CLARITY_DIR}/{_CONFIG} documents.{relative}"
        if is_adr:
            summary, read_at, read_when = _meta(extras.get("adr"), "manifest memory.adr")
        else:
            entry = custom.get(relative) if relative in custom else shipped.get(relative)
            raw = entry.get("memory") if isinstance(entry, dict) else None
            summary, read_at, read_when = _meta(raw, where)
        holds = summary or _first_heading(body) or relative
        ids = "" if is_adr else _rule_ids(body)
        if is_adr:
            holds = _first_heading(body) or relative
        elif ids:
            holds = f"{holds} IDs: {ids}."
        spec = str(data.get("spec") or "").strip()
        if spec:
            spec = _publish_spec(root, clarity, spec, files)
            holds = f"{holds} Published spec: `{spec}`."
        standing = "binding" if status in ("complete", "accepted") else "draft"
        rows[relative] = _Row(relative, holds, _read(read_at, read_when), standing)

    declared = config.get("not_applicable") or {}
    if not isinstance(declared, dict):
        raise PublishError(f"{CLARITY_DIR}/{_CONFIG}: not_applicable must be a mapping")
    for name, reason in declared.items():
        if str(name) not in rows and str(name) not in not_applicable:
            not_applicable[str(name)] = str(reason or "").strip() or "no reason given"

    ordered = [rows[p] for p in _order(list(rows), list(manifest.get("walk_order") or []))]
    notes = clarity / "notes.md"
    ideas = _feature_ideas(notes.read_text(encoding="utf-8")) if notes.is_file() else ""
    if ideas:
        summary, read_at, read_when = _meta(extras.get("feature_ideas"), "manifest memory")
        files[FEATURE_IDEAS] = _header("notes.md", "ideas") + "\n" + ideas
        ordered.append(
            _Row(FEATURE_IDEAS, summary or "Feature ideas.", _read(read_at, read_when), "ideas")
        )
    files[INDEX_NAME] = _index(fingerprint, ordered, not_applicable)

    memory = root / MEMORY_DIR
    removed = _remove_stale(memory, _old_published(memory), set(files))
    for relative, text in files.items():
        target = memory / relative
        if not target.is_file() or target.read_text(encoding="utf-8") != text:
            atomic_write(target, text)
    listing = "".join(f"{relative}\n" for relative in sorted(files))
    if not (memory / PUBLISHED_NAME).is_file() or (memory / PUBLISHED_NAME).read_text() != listing:
        atomic_write(memory / PUBLISHED_NAME, listing)
    return PublishResult(sorted(files), sorted(removed), not_applicable)


def _publish_spec(root: Path, clarity: Path, spec: str, files: dict[str, str]) -> str:
    """Copy a spec that lives under ``.clarity/`` into memory; return the path to cite.

    ``spec`` is as the API document wrote it: relative to ``.clarity/`` or to the repo root.
    A spec outside ``.clarity/`` stays where it is and is cited as written.
    """
    base = clarity.resolve()
    for candidate in (clarity / spec, root / spec):
        resolved = candidate.resolve()
        if resolved.is_file() and resolved.is_relative_to(base):
            relative = resolved.relative_to(base).as_posix()
            try:
                files[relative] = resolved.read_text(encoding="utf-8")
            except UnicodeDecodeError as exc:
                raise PublishError(f"{CLARITY_DIR}/{relative}: the spec isn't text") from exc
            return f"{MEMORY_DIR}/{relative}"
    return spec
