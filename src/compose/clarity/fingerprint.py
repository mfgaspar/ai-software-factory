"""The clarity fingerprint: one hash over the documents under ``.clarity/``.

It covers every file there except compose's own bookkeeping (``verdict.yml``,
``questions.yml``) and the skills' working files (``failures/brainstorm/``,
``prototypes/``). It's the sha256 of the sorted ``path\\0blobsha\\n`` lines, so a committed
tree (:func:`of_ref`) and a checked-out directory (:func:`of_dir`) with the same content give
the same value.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from compose.repos import git

CLARITY_DIR = ".clarity"
_EXCLUDED_FILES = (f"{CLARITY_DIR}/verdict.yml", f"{CLARITY_DIR}/questions.yml")
_EXCLUDED_DIRS = (f"{CLARITY_DIR}/failures/brainstorm/", f"{CLARITY_DIR}/prototypes/")


def _included(path: str) -> bool:
    return path not in _EXCLUDED_FILES and not path.startswith(_EXCLUDED_DIRS)


def _digest(entries: dict[str, str]) -> str:
    lines = "".join(f"{path}\0{blob}\n" for path, blob in sorted(entries.items()))
    return hashlib.sha256(lines.encode()).hexdigest()


def of_ref(root: Path, ref: str) -> str:
    """The fingerprint of ``.clarity/`` in the committed tree of ``ref``."""
    out = git.run_git(root, "ls-tree", "-r", "-z", ref, "--", CLARITY_DIR).stdout
    entries = {}
    for record in filter(None, out.split("\0")):
        meta, path = record.split("\t", 1)
        if _included(path):
            entries[path] = meta.split()[2]
    return _digest(entries)


def of_dir(root: Path) -> str:
    """The fingerprint of ``root/.clarity`` as it is on disk (ignored files left out)."""
    out = git.run_git(
        root, "ls-files", "-z", "--cached", "--others", "--exclude-standard", "--", CLARITY_DIR
    ).stdout
    paths = sorted({p for p in out.split("\0") if p and _included(p) and (root / p).is_file()})
    if not paths:
        return _digest({})
    blobs = git.run_git(root, "hash-object", "--stdin-paths", input_="\n".join(paths)).stdout
    return _digest(dict(zip(paths, blobs.split(), strict=True)))
