"""The clarity-* skills' shipped data: manifest, templates, starter config, skills, thinkers.

Skills are prose, so these tests check structure: the manifest is consistent, templates
carry the right front matter, the body-hash command behaves, and no skill inlines a template.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Any

import pytest
import yaml

from compose.engines.claude.install import ASSETS
from tests.unit.test_assets import CLARITY_PENDING, CLARITY_SKILLS, frontmatter

TEMPLATES = ASSETS / "templates" / "clarity"
SKILLS = ASSETS / "skills"
SHIPPED_CLARITY = [name for name in CLARITY_SKILLS if name not in CLARITY_PENDING]


def load_manifest() -> dict[str, Any]:
    data = yaml.safe_load((TEMPLATES / "manifest.yml").read_text())
    assert isinstance(data, dict)
    return data


MANIFEST = load_manifest()
DOCUMENTS: dict[str, dict[str, Any]] = MANIFEST["documents"]


def split(text: str) -> tuple[dict[str, Any], str]:
    match = re.match(r"^---\n(.*?)\n---\n(.*)$", text, re.S)
    assert match, "no front matter"
    data = yaml.safe_load(match.group(1))
    assert isinstance(data, dict)
    return data, match.group(2)


def body_hash(path: Path) -> str:
    command = MANIFEST["hash_command"].replace("FILE", f"'{path}'")
    proc = subprocess.run(["sh", "-c", command], check=True, capture_output=True, text=True)
    return proc.stdout.strip()


# ---------------------------------------------------------------------- manifest


def test_manifest_documents_and_order_agree() -> None:
    assert MANIFEST["walk_order"] == list(DOCUMENTS)  # same set, written in walk order
    staged = [path for stage in MANIFEST["stages"] for path in stage["documents"]]
    assert sorted(staged) == sorted(DOCUMENTS)
    assert len(staged) == len(set(staged))
    # stages follow walk order
    order = MANIFEST["walk_order"]
    assert staged == sorted(staged, key=order.index)


def test_manifest_references_resolve() -> None:
    for path, entry in DOCUMENTS.items():
        assert (TEMPLATES / entry["template"]).is_file(), path
        for dep in entry["depends_on"]:
            assert dep in DOCUMENTS, f"{path} depends on unknown {dep}"
        assert entry["produced_by"] in CLARITY_SKILLS, path
        for skill in entry.get("stage_skills", []):
            assert skill in CLARITY_SKILLS
        for key in ("adr_template", "spec_template"):
            if key in entry:
                assert (TEMPLATES / entry[key]).is_file()
    for template in [*MANIFEST["companions"].values(), *MANIFEST["helpers"].values()]:
        assert (TEMPLATES / template).is_file(), template
    assert (TEMPLATES / MANIFEST["config_template"]).is_file()
    assert set(MANIFEST["question_strategies"].values()) <= set(CLARITY_SKILLS)


def test_never_na_documents_cannot_be_na() -> None:
    for path in MANIFEST["never_na"]:
        assert DOCUMENTS[path]["allow_na"] is False
        assert DOCUMENTS[path]["mandatory"] is True
    others = set(DOCUMENTS) - set(MANIFEST["never_na"])
    assert all(DOCUMENTS[p]["allow_na"] for p in others)


# --------------------------------------------------------------------- templates


@pytest.mark.parametrize("path", list(DOCUMENTS))
def test_document_template(path: str) -> None:
    entry = DOCUMENTS[path]
    front, body = split((TEMPLATES / entry["template"]).read_text())
    assert front["status"] == "draft"
    assert front["reason"] == ""
    assert front["depends_on"] == entry["depends_on"]
    assert front["reviewed"] == {"hash": "", "deps": {}}
    assert front["sources"] == [] and front["approvals"] == []
    assert any(marker in body for marker in MANIFEST["placeholder_markers"])
    headings = set(re.findall(r"^## (.+)$", body, re.M))
    for section in entry["required_sections"]:
        assert section in headings, f"{path} lacks '## {section}'"


def test_contract_and_adr_templates() -> None:
    front, _ = split((TEMPLATES / "contracts/api.md").read_text())
    assert front["spec"] == "contracts/openapi.yaml"
    spec = yaml.safe_load((TEMPLATES / "contracts/openapi.yaml").read_text())
    assert spec["openapi"].startswith("3.")
    adr, body = split((TEMPLATES / "decisions/adr.md").read_text())
    assert adr["status"] == "proposed"
    assert "## Decision" in body
    questions = (TEMPLATES / "goal/open-questions.md").read_text()
    for field in ("**Status:**", "**Strategy:**", "**Blocking:**"):
        assert field in questions


def test_starter_config_is_valid_and_names_real_documents() -> None:
    text = (TEMPLATES / "config.yml").read_text()
    assert yaml.safe_load(text) is None  # everything commented out
    example = "\n".join(line[2:] for line in text.splitlines() if line.startswith("# "))
    known = set(DOCUMENTS) | {"ops/runbook.md"}  # the example custom document
    for path in re.findall(r"(?<![\w./-])[a-z-]+/[a-z-]+\.md\b", example):
        assert path in known, path
    for key in ("mandatory", "not_applicable", "documents", "approvals", "stale_fails"):
        assert f"# {key}:" in text


# --------------------------------------------------------------------- body hash


def test_body_hash_ignores_front_matter_only(tmp_path: Path) -> None:
    source = (TEMPLATES / "goal/problem.md").read_text()
    doc = tmp_path / "problem.md"
    doc.write_text(source)
    original = body_hash(doc)
    assert re.fullmatch(r"[0-9a-f]{40}", original)

    doc.write_text(source.replace("status: draft", "status: complete", 1))
    assert body_hash(doc) == original  # confirming doesn't change the fingerprint

    doc.write_text(source.replace("## Scope", "## Scope!", 1))
    assert body_hash(doc) != original

    doc.write_text(source + "\n---\n\nafter a horizontal rule\n")
    assert body_hash(doc) != original  # a `---` in the body is content


def test_body_hash_handles_spaces_in_paths(tmp_path: Path) -> None:
    doc = tmp_path / "a folder" / "doc.md"
    doc.parent.mkdir()
    doc.write_text("---\nstatus: draft\n---\nbody\n")
    assert len(body_hash(doc)) == 40


# ------------------------------------------------------------------------ skills


def template_blocks() -> list[str]:
    """Distinctive multi-line chunks of every template, which no SKILL.md may contain."""
    blocks: list[str] = []
    for path in TEMPLATES.rglob("*"):
        if not path.is_file() or path.suffix not in {".md", ".yml", ".yaml"}:
            continue
        lines = [line for line in path.read_text().splitlines() if line.strip()]
        for i in range(len(lines) - 2):
            chunk = "\n".join(lines[i : i + 3])
            if len(chunk) > 60:
                blocks.append(chunk)
    return blocks


BLOCKS = template_blocks()


@pytest.mark.parametrize("skill", SHIPPED_CLARITY)
def test_skill_inlines_no_template(skill: str) -> None:
    text = "\n".join(
        line for line in (SKILLS / skill / "SKILL.md").read_text().splitlines() if line.strip()
    )
    leaked = [block for block in BLOCKS if block in text]
    assert leaked == []


@pytest.mark.parametrize("skill", SHIPPED_CLARITY)
def test_skill_reads_the_manifest(skill: str) -> None:
    _, body = frontmatter(SKILLS / skill / "SKILL.md")
    assert ".compose/templates/clarity/manifest.yml" in body
    assert ".clarity/" in body


def skill_body(skill: str) -> str:
    return frontmatter(SKILLS / skill / "SKILL.md")[1]


def test_validate_skill_covers_every_rule() -> None:
    body = skill_body("clarity-validate")
    assert "hash_command" in body and ".clarity/config.yml" in body
    assert "CLARITY: PASS" in body and "CLARITY: FAIL (<n> incomplete)" in body
    for state in ("missing", "invalid-n/a", "draft", "edited", "blocked", "unapproved",
                  "complete", "stale", "outdated"):
        assert f"**{state}**" in body, state
    for key in ("placeholder_markers", "required_sections", "never_na", "stale_fails",
                "not_applicable", "approvals", "**Blocking:** yes", "reconsider"):
        assert key in body, key
    assert "never writes" in body


def test_configure_and_approve_skills() -> None:
    configure = skill_body("clarity-configure")
    for key in (".clarity/config.yml", "config.yml", "never_na", "`auto` mode", "commented out"):
        assert key in configure, key
    approve = skill_body("clarity-approve")
    for key in ("hash_command", "**draft**", "**edited**", "**stale**", "on someone else's behalf"):
        assert key in approve, key
    assert "`auto` mode" in approve and "never records approvals" in approve


PORTED = [
    "clarity",
    "clarity-problem",
    "clarity-discovery-prototype",
    "clarity-discovery-research",
    "clarity-solution",
    "clarity-architecture",
    "clarity-decision",
    "clarity-message",
    "clarity-failure-brainstorm",
    "clarity-failure-analysis",
    "clarity-failure-management",
]
THINKERS = [
    "adversarial-analysis-thinker",
    "codebase-scanner-thinker",
    "general-thinker",
    "human-factors-thinker",
    "security-catalog-thinker",
    "security-thinker",
]


@pytest.mark.parametrize("skill", [s for s in PORTED if s in SHIPPED_CLARITY])
def test_ported_skill_keeps_its_license(skill: str) -> None:
    folder = SKILLS / skill
    license_text = (folder / "LICENSE.txt").read_text()
    assert "MIT License" in license_text and "Microsoft Corporation" in license_text
    body = (folder / "SKILL.md").read_text()
    assert "LICENSE.txt" in body and "microsoft/clarity-agent" in body


@pytest.mark.parametrize("skill", SHIPPED_CLARITY)
def test_skill_writes_only_known_documents(skill: str) -> None:
    """Every `.clarity/<path>.md` a skill names is a manifest document, companion, or a
    documented family of files (ADRs, failure modes, brainstorm output, prototypes)."""
    body = skill_body(skill)
    known = set(DOCUMENTS) | set(MANIFEST["companions"]) | {"messaging.md"}
    families = ("decisions/ADR-", "failures/failure-", "failures/brainstorm/", "prototypes/",
                "goal/discovery/",
                "templates/", "contracts/")
    for path in re.findall(r"\.clarity/([\w./<>-]+\.md)", body):
        assert path in known or path.startswith(families), f"{skill}: .clarity/{path}"


def test_produced_by_skills_are_all_shipped() -> None:
    for entry in DOCUMENTS.values():
        for skill in [entry["produced_by"], *entry.get("stage_skills", [])]:
            assert (SKILLS / skill / "SKILL.md").is_file(), skill


def test_orchestrator_runs_the_whole_flow() -> None:
    body = skill_body("clarity")
    for step in ("### 0. Assess", "### 1. Inputs", "### 2. Configure", "### 3. Scaffold",
                 "### 4. Infer", "### 5. Stages", "### 6. Recheck", "### 7. Approve",
                 "### 8. Validate"):
        assert step in body, step
    # the skills it calls by name; producing skills are reached through `produced_by`
    for skill in ("clarity-configure", "clarity-validate", "clarity-approve", "clarity-decision",
                  "clarity-failure-brainstorm", "clarity-failure-analysis",
                  "clarity-failure-management"):
        assert f"`{skill}`" in body, skill
    assert "question_strategies" in body and "produced_by" in body
    assert "`auto` **never**" in body
    assert "Never overwrite confirmed work" in body


def test_thinkers_ship_with_their_prerequisites() -> None:
    folder = SKILLS / "clarity-failure-brainstorm" / "thinkers"
    assert sorted(p.stem for p in folder.glob("*.md")) == THINKERS
    brainstorm = skill_body("clarity-failure-brainstorm")
    for name in THINKERS:
        front, body = split((folder / f"{name}.md").read_text())
        assert front["name"] == name
        prerequisites = front["prerequisites"]
        for path in [*prerequisites.get("required", []), *prerequisites.get("recommended", [])]:
            assert path in DOCUMENTS, f"{name}: {path}"
        assert "failures/brainstorm/" in body
        assert ".clarity-protocol" not in body
        assert name in brainstorm


def test_software_document_skills() -> None:
    assert "spec:" in skill_body("clarity-api-contracts")
    assert "erDiagram" in skill_body("clarity-data-model")
    assert "stateDiagram" in skill_body("clarity-ux-flows")
    assert "FR-" in skill_body("clarity-prd")
    setup = skill_body("clarity-setup-guide")
    assert "secret" in setup.lower() and "never" in setup.lower()


def test_no_clarity_skill_mentions_the_original_folder() -> None:
    for skill in SHIPPED_CLARITY:
        assert ".clarity-protocol" not in (SKILLS / skill / "SKILL.md").read_text(), skill
