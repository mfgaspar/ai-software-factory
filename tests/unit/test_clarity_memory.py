from __future__ import annotations

from pathlib import Path

import pytest

from compose.clarity import constitution, memory

FP = "f" * 64


def doc(status: str, body: str, **extra: str) -> str:
    fields = "".join(f'{key}: "{value}"\n' for key, value in extra.items())
    return f'---\nstatus: {status}\n{fields}reviewed:\n  hash: ""\n---\n{body}'


def write(root: Path, relative: str, text: str) -> None:
    path = root / ".clarity" / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def published(root: Path, relative: str) -> str:
    return (root / memory.MEMORY_DIR / relative).read_text()


def rows(root: Path) -> dict[str, list[str]]:
    """The index table: file path -> [holds, read, standing]."""
    out = {}
    for line in published(root, memory.INDEX_NAME).splitlines():
        if line.startswith("| ["):
            cells = [c.strip() for c in line.strip("|").split(" | ")]
            out[cells[0].split("]")[0][1:]] = cells[1:]
    return out


REQUIREMENTS = "\n# Requirements\n\n- **NFR-001** fast\n- **NFR-014** safe\n- **CON-002** cheap\n"


@pytest.fixture
def root(tmp_path: Path) -> Path:
    write(tmp_path, "goal/requirements.md", doc("complete", REQUIREMENTS))
    write(tmp_path, "goal/problem.md", doc("draft", "\n# Problem\n\nToo slow.\n"))
    return tmp_path


def test_copies_bodies_unchanged_and_stamps_the_index(root: Path) -> None:
    result = memory.publish(root, FP)
    copy = published(root, "goal/requirements.md")
    header, body = copy.split("\n", 1)
    assert header == (
        "<!-- generated from .clarity/goal/requirements.md (complete) by compose; do not edit -->"
    )
    assert body == REQUIREMENTS  # the hashed body, byte for byte
    index = published(root, memory.INDEX_NAME)
    assert constitution.read_text(index) == FP
    assert "# Project memory" in index and "always at" in index
    assert result.written == ["constitution.md", "goal/problem.md", "goal/requirements.md"]
    assert published(root, memory.PUBLISHED_NAME).splitlines() == result.written


def test_rows_carry_summary_ids_read_and_standing(root: Path) -> None:
    memory.publish(root, FP)
    table = rows(root)
    assert list(table) == ["goal/problem.md", "goal/requirements.md"]  # manifest walk order
    holds, read, standing = table["goal/requirements.md"]
    assert holds.startswith("The rules every feature must meet")
    assert holds.endswith("IDs: NFR-001…NFR-014, CON-002.")
    assert read == "always at: specify, clarify, plan, tasks, implement, analyze"
    assert standing == "binding"
    assert table["goal/problem.md"][2] == "draft"


def test_conditional_documents_say_when(root: Path) -> None:
    write(root, "product/ux-standards.md", doc("complete", "\n# UX\n"))
    memory.publish(root, FP)
    read = rows(root)["product/ux-standards.md"][1]
    assert read == "always at: analyze; when: the feature has a user interface"


def test_not_applicable_is_listed_not_copied(root: Path) -> None:
    write(root, "data/data-model.md", doc("n/a", "\n# Data\n", reason="Stateless service"))
    write(root, "config.yml", 'not_applicable:\n  contracts/api.md: "No API"\n')
    result = memory.publish(root, FP)
    assert not (root / memory.MEMORY_DIR / "data/data-model.md").exists()
    assert result.not_applicable == {
        "data/data-model.md": "Stateless service",
        "contracts/api.md": "No API",
    }
    index = published(root, memory.INDEX_NAME)
    assert "## Not applicable" in index
    assert "- `contracts/api.md`: No API" in index
    assert "- `data/data-model.md`: Stateless service" in index


def test_front_matter_status_wins_over_config_not_applicable(root: Path) -> None:
    write(root, "config.yml", 'not_applicable:\n  goal/problem.md: "ignored"\n')
    result = memory.publish(root, FP)
    assert "goal/problem.md" in result.written and result.not_applicable == {}


def test_only_accepted_adrs_are_published(root: Path) -> None:
    write(root, "decisions/index.md", doc("complete", "\n# Decisions\n"))
    write(root, "decisions/ADR-002-store.md", doc("accepted", "\n# ADR-002: Use SQLite\n"))
    write(root, "decisions/ADR-001-lang.md", doc("accepted", "\n# ADR-001: Python\n"))
    write(root, "decisions/ADR-003-queue.md", doc("proposed", "\n# ADR-003: A queue\n"))
    memory.publish(root, FP)
    table = rows(root)
    assert "decisions/ADR-003-queue.md" not in table
    assert list(table)[-2:] == ["decisions/ADR-001-lang.md", "decisions/ADR-002-store.md"]
    holds, read, standing = table["decisions/ADR-002-store.md"]
    assert holds == "ADR-002: Use SQLite"
    assert read == "always at: analyze; when: the feature touches this decision"
    assert standing == "binding"


def test_custom_document_metadata_comes_from_config(root: Path) -> None:
    write(root, "ops/runbook.md", doc("complete", "\n# Runbook\n\nAlerts.\n"))
    write(root, "ops/checklist.md", doc("draft", "\n# Release checklist\n"))
    write(
        root,
        "config.yml",
        "documents:\n  ops/runbook.md:\n    memory:\n"
        '      summary: "Alerts and rollback."\n      read_at: [tasks]\n'
        '      read_when: "the feature changes how it is operated"\n',
    )
    memory.publish(root, FP)
    table = rows(root)
    assert table["ops/runbook.md"] == [
        "Alerts and rollback.",
        "always at: tasks; when: the feature changes how it is operated",
        "binding",
    ]
    assert table["ops/checklist.md"] == ["Release checklist", "when: relevant", "draft"]


def test_spec_outside_clarity_is_cited_and_inside_is_copied(root: Path) -> None:
    write(root, "contracts/api.md", doc("complete", "\n# API\n", spec="openapi.yaml"))
    memory.publish(root, FP)
    assert rows(root)["contracts/api.md"][0].endswith("Published spec: `openapi.yaml`.")

    write(root, "contracts/api.md", doc("complete", "\n# API\n", spec="contracts/openapi.yaml"))
    write(root, "contracts/openapi.yaml", "openapi: 3.1.0\n")
    result = memory.publish(root, FP)
    assert "contracts/openapi.yaml" in result.written
    assert published(root, "contracts/openapi.yaml") == "openapi: 3.1.0\n"
    assert rows(root)["contracts/api.md"][0].endswith(
        "Published spec: `.compose/memory/contracts/openapi.yaml`."
    )


def test_feature_ideas_come_from_notes(root: Path) -> None:
    write(root, "notes.md", "# Notes\n\n## Feature ideas\n\n## Progress\n\nDone.\n")
    assert memory.FEATURE_IDEAS not in memory.publish(root, FP).written
    write(root, "notes.md", "# Notes\n\n## Feature ideas\n\n- Export to CSV\n\n## Progress\n\nx\n")
    memory.publish(root, FP)
    ideas = published(root, memory.FEATURE_IDEAS)
    assert "- Export to CSV" in ideas and "Progress" not in ideas
    assert rows(root)[memory.FEATURE_IDEAS][1:] == ["always at: specify", "ideas"]


def test_stale_copies_are_removed_and_other_files_kept(root: Path) -> None:
    write(root, "product/prd.md", doc("complete", "\n# PRD\n"))
    memory.publish(root, FP)
    own = root / memory.MEMORY_DIR / "own.md"
    own.write_text("mine\n")
    write(root, "product/prd.md", doc("n/a", "\n# PRD\n", reason="No product"))
    result = memory.publish(root, FP)
    assert result.removed == ["product/prd.md"]
    assert not (root / memory.MEMORY_DIR / "product").exists()
    assert own.read_text() == "mine\n"
    assert "product/prd.md" not in published(root, memory.PUBLISHED_NAME)


def test_published_list_cannot_delete_outside_memory(root: Path) -> None:
    memory.publish(root, FP)
    outside = root / "keep.txt"
    outside.write_text("keep\n")
    (root / memory.MEMORY_DIR / memory.PUBLISHED_NAME).write_text("../../keep.txt\n")
    memory.publish(root, FP)
    assert outside.read_text() == "keep\n"


def test_publishing_twice_changes_nothing(root: Path) -> None:
    memory.publish(root, FP)
    folder = root / memory.MEMORY_DIR
    before = {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in folder.rglob("*") if p.is_file()}
    memory.publish(root, FP)
    after = {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in folder.rglob("*") if p.is_file()}
    assert after == before


def test_files_without_a_status_and_working_folders_are_skipped(root: Path) -> None:
    write(root, "observations.md", "# Observations\n")
    write(root, "failures/brainstorm/skeptic.md", doc("draft", "\n# Skeptic\n"))
    write(root, "templates/runbook.md", doc("draft", "\n# Runbook\n"))
    assert memory.publish(root, FP).written == [
        "constitution.md",
        "goal/problem.md",
        "goal/requirements.md",
    ]


def test_errors(root: Path, tmp_path: Path) -> None:
    write(root, "config.yml", "documents: [\n")
    with pytest.raises(memory.PublishError, match="config.yml is not valid YAML"):
        memory.publish(root, FP)
    write(
        root,
        "config.yml",
        "documents:\n  goal/problem.md:\n    memory:\n      read_at: [review]\n",
    )
    with pytest.raises(memory.PublishError, match="unknown step.*review"):
        memory.publish(root, FP)
    empty = tmp_path / "empty"
    empty.mkdir()
    with pytest.raises(memory.PublishError, match="no .clarity/ folder"):
        memory.publish(empty, FP)
