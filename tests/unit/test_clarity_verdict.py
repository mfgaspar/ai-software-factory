"""The clarity fingerprint, the validator's verdict and the constitution marker."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest

from compose.clarity import constitution, fingerprint, verdict

Git = Callable[..., str]


def _write(root: Path, path: str, text: str) -> None:
    target = root / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text)


@pytest.fixture
def clarity_repo(git_repo: Path, run_git: Git) -> Path:
    _write(git_repo, ".clarity/goal/problem.md", "---\nstatus: complete\n---\n# Problem\n")
    _write(git_repo, ".clarity/notes.md", "# Notes\n")
    run_git(git_repo, "add", ".clarity")
    run_git(git_repo, "commit", "-q", "-m", "clarity")
    return git_repo


# ------------------------------------------------------------------- fingerprint


def test_branch_and_directory_agree(clarity_repo: Path) -> None:
    value = fingerprint.of_ref(clarity_repo, "main")
    assert len(value) == 64
    assert fingerprint.of_dir(clarity_repo) == value


def test_fingerprint_ignores_excluded_files(clarity_repo: Path, run_git: Git) -> None:
    before = fingerprint.of_ref(clarity_repo, "main")
    for path in (
        ".clarity/verdict.yml",
        ".clarity/questions.yml",
        ".clarity/failures/brainstorm/security.md",
        ".clarity/prototypes/spike/main.py",
    ):
        _write(clarity_repo, path, "anything\n")
    _write(clarity_repo, "README.md", "outside clarity\n")
    assert fingerprint.of_dir(clarity_repo) == before
    run_git(clarity_repo, "add", "-A")
    run_git(clarity_repo, "commit", "-q", "-m", "working files")
    assert fingerprint.of_ref(clarity_repo, "main") == before


def test_fingerprint_changes_on_any_document_edit(clarity_repo: Path, run_git: Git) -> None:
    before = fingerprint.of_dir(clarity_repo)
    _write(clarity_repo, ".clarity/notes.md", "# Notes\n\nmore\n")
    edited = fingerprint.of_dir(clarity_repo)
    assert edited != before
    _write(clarity_repo, ".clarity/failures/failures.md", "# Failures\n")  # new, untracked
    added = fingerprint.of_dir(clarity_repo)
    assert added not in (before, edited)
    (clarity_repo / ".clarity/notes.md").unlink()  # deleted, still in the index
    assert fingerprint.of_dir(clarity_repo) not in (before, edited, added)
    run_git(clarity_repo, "add", "-A")
    run_git(clarity_repo, "commit", "-q", "-m", "edit")
    assert fingerprint.of_ref(clarity_repo, "main") == fingerprint.of_dir(clarity_repo)
    assert fingerprint.of_ref(clarity_repo, "main~1") == before


def test_no_clarity_folder_has_the_empty_fingerprint(git_repo: Path) -> None:
    assert fingerprint.of_ref(git_repo, "main") == fingerprint.of_dir(git_repo)


# ----------------------------------------------------------------------- verdict


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("report\nCLARITY: PASS", verdict.Verdict("PASS", 0)),
        ("report\nCLARITY: FAIL (3 incomplete)\n", verdict.Verdict("FAIL", 3)),
        ("CLARITY: PASS\n\n  \n", verdict.Verdict("PASS", 0)),  # trailing blank lines
        ("CLARITY: PASS\nsomething after", verdict.Verdict("FAIL", None)),
        ("CLARITY: FAIL", verdict.Verdict("FAIL", None)),
        ("clarity: pass", verdict.Verdict("FAIL", None)),
        ("", verdict.Verdict("FAIL", None)),
    ],
)
def test_parse(text: str, expected: verdict.Verdict) -> None:
    assert verdict.parse(text) == expected


def test_write_and_read_ref(clarity_repo: Path, run_git: Git) -> None:
    assert verdict.read_ref(clarity_repo, "main") is None
    value = fingerprint.of_dir(clarity_repo)
    path = verdict.write(clarity_repo, verdict.Verdict("FAIL", 2), value, "run-1")
    assert path == clarity_repo / ".clarity/verdict.yml"
    assert fingerprint.of_dir(clarity_repo) == value  # the verdict isn't part of it
    run_git(clarity_repo, "add", ".clarity")
    run_git(clarity_repo, "commit", "-q", "-m", "verdict")
    recorded = verdict.read_ref(clarity_repo, "main")
    assert recorded is not None
    assert recorded.verdict == verdict.Verdict("FAIL", 2) and not recorded.verdict.passed
    assert recorded.fingerprint == value and recorded.run_id == "run-1"
    assert recorded.at


def test_malformed_verdict_file_reads_as_none() -> None:
    assert verdict.from_text("result: MAYBE\nfingerprint: abc\n") is None
    assert verdict.from_text("result: PASS\n") is None
    assert verdict.from_text(": [\n") is None


# ------------------------------------------------------------------ constitution


def test_marker_round_trip_and_legacy() -> None:
    text = f"{constitution.marker('abc')}\n# Project memory\n"
    assert text.startswith("<!-- memory-index: abc -->\n")
    assert constitution.read_text(text) == "abc" and not constitution.is_legacy(text)
    legacy = "<!-- generated-from-clarity: abc -->\n# Constitution\n"
    assert constitution.read_text(legacy) is None and constitution.is_legacy(legacy)
    assert constitution.read_text("# Constitution\n") is None


def test_constitution_read_ref(git_repo: Path, run_git: Git) -> None:
    assert constitution.read_ref(git_repo, "main") is None
    path = git_repo / constitution.CONSTITUTION_FILE
    _write(git_repo, constitution.CONSTITUTION_FILE, "# Constitution\n")
    run_git(git_repo, "add", "-A")
    run_git(git_repo, "commit", "-q", "-m", "hand-written")
    assert constitution.read_ref(git_repo, "main") is None
    path.write_text(f"{constitution.marker('f' * 64)}\n# Project memory\n")
    run_git(git_repo, "commit", "-q", "-am", "generated")
    assert constitution.read_ref(git_repo, "main") == "f" * 64
