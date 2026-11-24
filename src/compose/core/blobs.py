"""Where a run's detail files (actions, file changes, ...) are kept.

The database holds identifiers and metrics only; everything detailed goes through a
:class:`BlobStore`, addressed by a key relative to the run (``steps/<exec id>.actions.jsonl``).
:class:`LocalBlobStore` keeps them in the run folder. An object store (S3, Azure Blob, ...)
only has to implement the same four methods and be returned by :func:`RunFiles.blobs`.
"""

from __future__ import annotations

from pathlib import Path
from typing import Protocol


class BlobStore(Protocol):
    def append_lines(self, key: str, lines: list[str]) -> None: ...

    def read_lines(self, key: str) -> list[str]: ...

    def list_keys(self, prefix: str) -> list[str]: ...

    def exists(self, key: str) -> bool: ...


class LocalBlobStore:
    def __init__(self, root: Path) -> None:
        self.root = root

    def append_lines(self, key: str, lines: list[str]) -> None:
        path = self.root / key
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a") as handle:
            for line in lines:
                handle.write(line + "\n")

    def read_lines(self, key: str) -> list[str]:
        path = self.root / key
        if not path.is_file():
            return []
        return [ln for ln in path.read_text(errors="replace").splitlines() if ln]

    def list_keys(self, prefix: str) -> list[str]:
        base = self.root / prefix
        folder = base if base.is_dir() else base.parent
        if not folder.is_dir():
            return []
        return sorted(
            p.relative_to(self.root).as_posix()
            for p in folder.rglob("*")
            if p.is_file() and p.relative_to(self.root).as_posix().startswith(prefix)
        )

    def exists(self, key: str) -> bool:
        return (self.root / key).is_file()
