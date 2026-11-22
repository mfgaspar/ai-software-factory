from __future__ import annotations

import subprocess
from pathlib import Path

from compose.core.models import FileStatus
from compose.tracking.diff import Change, ChangeSummary, diff_trees
from compose.tracking.snapshot import snapshot


def git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=repo, check=True, capture_output=True, text=True
    ).stdout


def changes(repo: Path, edit: object) -> list[Change]:
    before = snapshot(repo)
    assert callable(edit)
    edit()
    return diff_trees(repo, before, snapshot(repo))


def test_tracked_edit_new_file_and_deletion(git_repo: Path) -> None:
    (git_repo / "gone.txt").write_text("a\nb\n")
    git(git_repo, "add", "gone.txt")
    git(git_repo, "commit", "-qm", "add gone")

    def edit() -> None:
        (git_repo / "README.md").write_text("# test repo\nmore\nlines\n")
        (git_repo / "new.txt").write_text("one\ntwo\nthree\n")
        (git_repo / "gone.txt").unlink()

    assert changes(git_repo, edit) == [
        Change("README.md", FileStatus.MODIFIED, None, 2, 0),
        Change("gone.txt", FileStatus.DELETED, None, 0, 2),
        Change("new.txt", FileStatus.ADDED, None, 3, 0),
    ]


def test_rename_and_names_with_spaces(git_repo: Path) -> None:
    body = "".join(f"line {i}\n" for i in range(20))
    (git_repo / "old name.txt").write_text(body)
    git(git_repo, "add", ".")
    git(git_repo, "commit", "-qm", "add")

    def edit() -> None:
        (git_repo / "old name.txt").rename(git_repo / "new name.txt")
        with (git_repo / "new name.txt").open("a") as fh:
            fh.write("extra\n")

    assert changes(git_repo, edit) == [
        Change("new name.txt", FileStatus.RENAMED, "old name.txt", 1, 0)
    ]


def test_ignored_and_compose_scratch_files_are_excluded(git_repo: Path) -> None:
    (git_repo / ".gitignore").write_text("build/\n")
    (git_repo / ".git" / "info" / "exclude").write_text("local.cfg\n")
    git(git_repo, "add", ".gitignore")
    git(git_repo, "commit", "-qm", "ignore")

    def edit() -> None:
        (git_repo / "build").mkdir()
        (git_repo / "build" / "out.bin").write_text("x")
        (git_repo / "local.cfg").write_text("x")
        (git_repo / ".compose" / "runs").mkdir(parents=True)
        (git_repo / ".compose" / "runs" / "log").write_text("x")
        (git_repo / "kept.txt").write_text("x\n")

    assert [c.path for c in changes(git_repo, edit)] == ["kept.txt"]


def test_binary_files_have_no_line_counts(git_repo: Path) -> None:
    def edit() -> None:
        (git_repo / "image.png").write_bytes(b"\x89PNG\x00\x01\x02" * 50)

    result = changes(git_repo, edit)
    assert result == [Change("image.png", FileStatus.ADDED, None, None, None)]
    assert ChangeSummary.of(result) == ChangeSummary(files=1, added=0, removed=0)


def test_real_index_and_history_untouched(git_repo: Path) -> None:
    (git_repo / "staged.txt").write_text("s\n")
    git(git_repo, "add", "staged.txt")
    (git_repo / "untracked.txt").write_text("u\n")
    status = git(git_repo, "status", "--porcelain")
    head = git(git_repo, "rev-parse", "HEAD")
    tree = snapshot(git_repo)
    assert git(git_repo, "status", "--porcelain") == status
    assert git(git_repo, "rev-parse", "HEAD") == head
    listed = git(git_repo, "ls-tree", "-r", "--name-only", tree).split()
    assert listed == ["README.md", "staged.txt", "untracked.txt"]


def test_unchanged_worktree_gives_same_tree(git_repo: Path) -> None:
    assert snapshot(git_repo) == snapshot(git_repo)
    assert diff_trees(git_repo, snapshot(git_repo), snapshot(git_repo)) == []


def test_snapshot_in_linked_worktree(git_repo: Path, tmp_path: Path) -> None:
    linked = tmp_path / "linked"
    git(git_repo, "worktree", "add", "-q", "-b", "feat", str(linked))
    before = snapshot(linked)
    (linked / "README.md").write_text("changed\n")
    assert diff_trees(linked, before, snapshot(linked)) == [
        Change("README.md", FileStatus.MODIFIED, None, 1, 1)
    ]
