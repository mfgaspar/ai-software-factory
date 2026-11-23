"""Live end-to-end tests of the clarity skills on Claude Code.

Run with: uv run pytest -m live tests/live/test_clarity_live.py  (spends about a dollar)

Each test builds a project in a throwaway git repo, installs the shipped skills and templates,
and runs `claude -p` on it directly: clarity is independent of compose workflows, so these
tests don't go through the runner. Hashes in the fixtures are computed here with the
manifest's own command, so they can't drift from the templates.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path
from typing import Any

import pytest
import yaml

from compose.engines.claude.install import check, cli_path, install
from tests.unit.test_clarity_assets import DOCUMENTS, MANIFEST, TEMPLATES, body_hash, split

pytestmark = pytest.mark.live

MODEL = "claude-sonnet-5-5"  # the validator's rules need a capable model to apply exactly
BUDGET_USD = 1.5


@pytest.fixture(autouse=True)
def _ready() -> None:
    problems = check()
    if problems:
        pytest.skip("; ".join(problems))


def claude(repo: Path, prompt: str) -> str:
    cli = cli_path()
    assert cli
    env = {k: v for k, v in os.environ.items() if k != "CLAUDECODE"}
    proc = subprocess.run(
        [
            cli, "-p", prompt, "--output-format=json", f"--model={MODEL}",
            f"--max-budget-usd={BUDGET_USD}", "--permission-mode=bypassPermissions",
            "--setting-sources=project",
        ],
        cwd=repo, env=env, capture_output=True, text=True, timeout=1200, check=False,
    )
    assert proc.returncode == 0, proc.stderr[-2000:]
    result = json.loads(proc.stdout)
    text = result.get("result", "")
    assert isinstance(text, str)
    return text


def last_line(text: str) -> str:
    return [line for line in text.strip().splitlines() if line.strip()][-1].strip()


# ---------------------------------------------------------------- fixture project


def filled_body(path: str, entry: dict[str, Any]) -> str:
    """A finished document: every required section has real text, no placeholders."""
    title = path.rsplit("/", 1)[-1].removesuffix(".md").replace("-", " ").title()
    parts = [f"# {title}\n", "A word-count command-line tool for writers.\n"]
    for section in entry["required_sections"]:
        text = f"Written content for {section.lower()} of the word-count tool."
        if path == "goal/requirements.md" and section == "Functional requirements":
            text = "- **FR-001 — count words:** print the word count of a file."
        if path == "goal/open-questions.md":
            text = "No fundamental unknowns were identified; the problem is clear."
        if path == "decisions/index.md":
            text = "| ADR | Title | Status | Date |\n|---|---|---|---|\n" \
                   "| [ADR-001](ADR-001-language.md) | Use Python | accepted | 2026-11-22 |"
        parts.append(f"## {section}\n\n{text}\n")
    return "\n".join(parts)


def write_doc(root: Path, path: str, front: dict[str, Any], body: str) -> None:
    target = root / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("---\n" + yaml.safe_dump(front, sort_keys=False) + "---\n\n" + body)


def confirm(root: Path, path: str) -> None:
    """Do what a user's confirmation does: complete + reviewed hashes."""
    target = root / path
    front, body = split(target.read_text())
    front["status"] = "complete"
    front["reviewed"] = {
        "hash": body_hash(target),
        "deps": {dep: body_hash(root / dep) for dep in front.get("depends_on", [])},
    }
    target.write_text("---\n" + yaml.safe_dump(front, sort_keys=False) + "---\n" + body)


def build_complete_project(git_repo: Path) -> Path:
    """Install the clarity skills and write every mandatory document, complete."""
    install(git_repo)
    root = git_repo / ".clarity"
    for path, entry in DOCUMENTS.items():
        front, _ = split((TEMPLATES / entry["template"]).read_text())
        write_doc(root, path, front, filled_body(path, entry))
    (root / "contracts/openapi.yaml").write_text(
        "openapi: 3.1.0\ninfo: {title: Word count, version: 1.0.0}\npaths: {}\n"
    )
    adr_front, _ = split((TEMPLATES / "decisions/adr.md").read_text())
    adr_front.update(status="accepted", date="2026-11-22", depends_on=["goal/requirements.md"])
    write_doc(root, "decisions/ADR-001-language.md", adr_front,
              "# ADR-001: Use Python\n\n## Decision\n\nPython, for its standard library.\n")
    # confirm in walk order so every recorded dependency hash is current
    for path in MANIFEST["walk_order"]:
        confirm(root, path)
    confirm(root, "decisions/ADR-001-language.md")
    return git_repo


@pytest.fixture
def project(git_repo: Path) -> Path:
    return build_complete_project(git_repo)


# ------------------------------------------------------------------------ tests


def test_validate_passes_a_complete_project(project: Path) -> None:
    assert last_line(claude(project, "/clarity-validate")) == "CLARITY: PASS"


def test_validate_fails_an_edited_document(project: Path) -> None:
    prd = project / ".clarity/product/prd.md"
    prd.write_text(prd.read_text() + "\nA sentence added after confirmation.\n")
    text = claude(project, "/clarity-validate")
    assert re.fullmatch(r"CLARITY: FAIL \(\d+ incomplete\)", last_line(text))
    assert "prd.md" in text and "edited" in text.lower()


def test_stale_is_a_warning_unless_configured(project: Path) -> None:
    problem = project / ".clarity/goal/problem.md"
    front, body = split(problem.read_text())
    problem.write_text(problem.read_text().replace(body, body + "\nOne more line.\n"))
    confirm(project / ".clarity", "goal/problem.md")  # problem itself re-confirmed
    text = claude(project, "/clarity-validate")
    assert last_line(text) == "CLARITY: PASS"
    assert "stale" in text.lower()

    (project / ".clarity/config.yml").write_text("stale_fails: true\n")
    assert last_line(claude(project, "/clarity-validate")).startswith("CLARITY: FAIL")


def test_na_and_approvals(project: Path) -> None:
    root = project / ".clarity"
    (root / "config.yml").write_text(
        "not_applicable:\n  product/ux-flows.md: \"Command-line tool, no screens\"\n"
        "approvals:\n  product/prd.md: [Ana Silva]\n"
    )
    text = claude(project, "/clarity-validate")
    assert last_line(text).startswith("CLARITY: FAIL")
    assert "Ana Silva" in text

    prd = root / "product/prd.md"
    front, body = split(prd.read_text())
    front["approvals"] = [{"by": "Ana Silva", "at": "2026-11-22", "hash": body_hash(prd)}]
    prd.write_text("---\n" + yaml.safe_dump(front, sort_keys=False) + "---\n" + body)
    assert last_line(claude(project, "/clarity-validate")) == "CLARITY: PASS"


def test_orchestrator_auto_drafts_from_sources(git_repo: Path) -> None:
    install(git_repo)
    docs = git_repo / "docs"
    docs.mkdir()
    (docs / "prd.md").write_text(
        "# Word count v1\n\nWriters need a quick word count for Markdown drafts without opening "
        "an editor. Users: novelists and bloggers. Must count words in a file in under a "
        "second for files up to 10 MB, and ignore Markdown syntax. Out of scope: PDFs.\n"
    )
    api = git_repo / "api"
    api.mkdir()
    (api / "openapi.yaml").write_text(
        "openapi: 3.1.0\ninfo: {title: Word count, version: 1.0.0}\n"
        "paths:\n  /count:\n    post:\n      summary: Count the words in a document\n"
        "      responses: {'200': {description: The count}}\n"
    )
    text = claude(git_repo, "/clarity docs/prd.md api/openapi.yaml auto")
    root = git_repo / ".clarity"
    assert (root / "config.yml").is_file()
    for path in ("goal/problem.md", "goal/requirements.md", "product/prd.md"):
        front, _ = split((root / path).read_text())
        assert front["status"] == "draft", path  # auto never confirms
        assert any("prd.md" in str(s) for s in front["sources"]), path
    api_front, _ = split((root / "contracts/api.md").read_text())
    assert "openapi.yaml" in str(api_front["spec"])
    for path in DOCUMENTS:
        if (root / path).exists():
            assert split((root / path).read_text())[0]["status"] != "complete", path
    assert last_line(text).startswith("CLARITY: FAIL")
