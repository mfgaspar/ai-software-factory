"""compose's read of a repo's clarity documents (front matter only)."""

from __future__ import annotations

from pathlib import Path

from compose.clarity import summary as clarity
from compose.repos import features


def _doc(root: Path, path: str, front: str) -> None:
    target = root / ".clarity" / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(f"---\n{front}---\n\n# Body\n")


def test_no_clarity_folder(tmp_path: Path) -> None:
    assert clarity.summary(tmp_path) is None


def test_summary_lists_documents_with_a_status(tmp_path: Path) -> None:
    _doc(tmp_path, "goal/problem.md", "status: complete\n")
    _doc(tmp_path, "product/ux-standards.md", "status: n/a\nreason: CLI only\n")
    _doc(tmp_path, "decisions/ADR-001-python.md", "status: accepted\n")
    _doc(tmp_path, "failures/brainstorm/security.md", "status: draft\n")  # working file
    (tmp_path / ".clarity/notes.md").write_text("# Notes\n")  # no front matter
    (tmp_path / ".clarity/broken.md").write_text("---\n: [\n---\n")
    data = clarity.summary(tmp_path)
    assert data == {
        "dir": str(tmp_path / ".clarity"),
        "guide": str(tmp_path / ".compose/templates/compose/clarity.md"),
        "documents": {
            "decisions/ADR-001-python.md": "accepted",
            "goal/problem.md": "complete",
            "product/ux-standards.md": "n/a",
        },
    }


def test_feature_paths_json_carries_clarity(tmp_path: Path) -> None:
    assert features.feature_paths(tmp_path, "001-x").to_json()["clarity"] is None
    _doc(tmp_path, "goal/problem.md", "status: draft\n")
    data = features.feature_paths(tmp_path, "001-x").to_json()
    assert data["clarity"]["documents"] == {"goal/problem.md": "draft"}  # type: ignore[index]
    assert data["templates_dir"] == str(tmp_path / ".compose/templates/compose")
