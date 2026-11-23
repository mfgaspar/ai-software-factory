"""What compose knows about a repo's clarity documents (``.clarity/``).

Clarity holds the application-level why, rules and how; compose specifies and plans each
feature within them. This module only reads front matter, so it's cheap and deterministic:
it reports each document's declared ``status``, not whether the document passes
``/clarity-validate`` (that needs the model).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

CLARITY_DIR = ".clarity"
GUIDE = Path(".compose") / "templates" / "compose" / "clarity.md"
# Working files the clarity skills keep that aren't documents compose should follow.
_SKIPPED = ("failures/brainstorm/", "prototypes/")


def front_matter(path: Path) -> dict[str, Any] | None:
    """The YAML front matter of a Markdown file, or None when it has none (or it's broken)."""
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None
    if not text.startswith("---\n"):
        return None
    end = text.find("\n---", 4)
    if end == -1:
        return None
    try:
        data = yaml.safe_load(text[4:end])
    except yaml.YAMLError:
        return None
    return data if isinstance(data, dict) else None


def summary(root: Path) -> dict[str, Any] | None:
    """``{"dir", "guide", "documents": {path: status}}`` for ``root/.clarity``, or None.

    Paths are relative to ``.clarity/``. Files without a ``status`` in their front matter
    (notes, observations) are left out.
    """
    folder = root / CLARITY_DIR
    if not folder.is_dir():
        return None
    documents: dict[str, str] = {}
    for path in sorted(folder.rglob("*.md")):
        relative = path.relative_to(folder).as_posix()
        if relative.startswith(_SKIPPED):
            continue
        data = front_matter(path)
        if data is None or "status" not in data:
            continue
        documents[relative] = str(data["status"])
    return {"dir": str(folder), "guide": str(root / GUIDE), "documents": documents}
