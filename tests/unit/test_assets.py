"""The skills and templates compose ships."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest
import typer
import yaml

from compose.cli.app import app
from compose.engines.claude.install import ASSETS

SKILLS = sorted(p for p in (ASSETS / "skills").iterdir() if p.is_dir())
WORKFLOW_SKILLS = [
    "compose-analyze",
    "compose-bug-assess",
    "compose-bug-fix",
    "compose-bug-test",
    "compose-checklist",
    "compose-clarify",
    "compose-constitution",
    "compose-converge",
    "compose-implement",
    "compose-plan",
    "compose-specify",
    "compose-tasks",
]
# shipped skills that work outside workflows and don't touch features
OTHER_SKILLS = ["compose-find-skills"]
# the clarity family (see docs/clarity.md); independent of compose workflows
CLARITY_SKILLS = [
    "clarity",
    "clarity-api-contracts",
    "clarity-approve",
    "clarity-architecture",
    "clarity-configure",
    "clarity-data-model",
    "clarity-decision",
    "clarity-discovery-prototype",
    "clarity-discovery-research",
    "clarity-failure-analysis",
    "clarity-failure-brainstorm",
    "clarity-failure-management",
    "clarity-fmea",
    "clarity-message",
    "clarity-prd",
    "clarity-problem",
    "clarity-setup-guide",
    "clarity-solution",
    "clarity-ux-standards",
    "clarity-validate",
]
CLARITY_PENDING: set[str] = set()
PLANNED: set[str] = set()


def frontmatter(path: Path) -> tuple[dict[str, object], str]:
    text = path.read_text()
    match = re.match(r"^---\n(.*?)\n---\n(.*)$", text, re.S)
    assert match, f"{path} has no frontmatter"
    data = yaml.safe_load(match.group(1))
    assert isinstance(data, dict)
    return data, match.group(2)


def cli_commands() -> set[str]:
    """Every command path the CLI knows, e.g. 'feature paths', 'init'."""
    root: Any = typer.main.get_command(app)
    paths: set[str] = set()
    for name, command in root.commands.items():
        paths.add(name)
        paths.update(f"{name} {sub}" for sub in getattr(command, "commands", {}))
    return paths


def referenced(body: str) -> set[str]:
    """'compose <command> [<sub>]' mentioned inside backticks or code blocks."""
    fence = re.compile(r"```[a-z]*\n(.*?)```", re.S)
    blocks = fence.findall(body)
    inline = re.findall(r"`([^`\n]+)`", fence.sub("", body))
    code = "\n".join([*blocks, *inline])
    found: set[str] = set()
    for match in re.finditer(r"\bcompose ([a-z]+)(?: ([a-z]+))?", code):
        command, sub = match.group(1), match.group(2)
        found.add(f"{command} {sub}" if sub else command)
    return found


def test_all_skills_are_shipped() -> None:
    shipped = [*WORKFLOW_SKILLS, *OTHER_SKILLS, "compose", *CLARITY_SKILLS]
    expected = sorted(name for name in shipped if name not in CLARITY_PENDING)
    assert [p.name for p in SKILLS] == expected


@pytest.mark.parametrize("skill", SKILLS, ids=lambda p: p.name)
def test_skill_frontmatter(skill: Path) -> None:
    data, body = frontmatter(skill / "SKILL.md")
    assert data["name"] == skill.name
    description = data["description"]
    assert isinstance(description, str) and 40 < len(description) < 400
    assert "$ARGUMENTS" in body


@pytest.mark.parametrize("skill", SKILLS, ids=lambda p: p.name)
def test_skills_use_only_real_cli_commands(skill: Path) -> None:
    _, body = frontmatter(skill / "SKILL.md")
    known = cli_commands()
    unknown = set()
    for ref in referenced(body):
        if ref in known or ref.split()[0] in known - {"feature", "repo", "workflow"}:
            continue
        unknown.add(ref)
    if skill.name == "compose":
        assert {u.split()[0] for u in unknown} <= PLANNED
    else:
        assert unknown == set()


@pytest.mark.parametrize("skill", WORKFLOW_SKILLS)
def test_workflow_skills_locate_features_through_the_cli(skill: str) -> None:
    _, body = frontmatter(ASSETS / "skills" / skill / "SKILL.md")
    assert "compose feature paths --json" in body or "compose feature new --json" in body


def test_adopted_skill_keeps_its_license() -> None:
    folder = ASSETS / "skills" / "compose-find-skills"
    license_text = (folder / "LICENSE.txt").read_text()
    assert "MIT License" in license_text and "Vercel, Inc." in license_text
    assert "LICENSE.txt" in (folder / "SKILL.md").read_text()


def test_no_references_to_the_old_project() -> None:
    s, k, i = "spec", "kit", "ify"
    pattern = re.compile(rf"{s}[- ]?{k}|\\.{s}{i}/", re.I)
    offenders = [
        str(p.relative_to(ASSETS))
        for p in ASSETS.rglob("*")
        if p.is_file() and pattern.search(p.read_text())
    ]
    assert offenders == []


def test_templates() -> None:
    names = sorted(p.name for p in (ASSETS / "templates" / "compose").iterdir() if p.is_file())
    assert names == [
        "checklist.md",
        "clarity.md",
        "constitution.md",
        "plan.md",
        "spec.md",
        "tasks.md",
    ]
    spec = (ASSETS / "templates" / "compose" / "spec.md").read_text()
    for heading in ("## User scenarios", "## Requirements", "## Success criteria"):
        assert heading in spec
    tasks = (ASSETS / "templates" / "compose" / "tasks.md").read_text()
    assert "- [ ] T001" in tasks


def test_assets_are_packaged() -> None:
    """Hatchling ships everything inside the package folder, including these."""
    assert ASSETS.parent.name == "compose" and (ASSETS.parent / "__init__.py").exists()
