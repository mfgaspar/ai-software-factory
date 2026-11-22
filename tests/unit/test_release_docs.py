"""The shipped documentation stays in step with the code."""

from __future__ import annotations

import json
import re
from pathlib import Path

from compose import __version__
from compose.api.app import create_app

ROOT = Path(__file__).parents[2]
DOCS = ["README.md", "docs/cli.md", "docs/api.md", "docs/custom-workflows.md"]


def test_openapi_copy_is_current() -> None:
    """Regenerate with: python -c "import json; from compose.api.app import create_app;
    print(json.dumps(create_app().openapi(), indent=2, sort_keys=True))" > docs/openapi.json"""
    committed = json.loads((ROOT / "docs" / "openapi.json").read_text())
    assert committed == json.loads(json.dumps(create_app().openapi(), sort_keys=True))
    assert committed["info"]["version"] == __version__


def test_relative_links_resolve() -> None:
    broken = []
    for name in DOCS:
        page = ROOT / name
        for target in re.findall(r"\]\(([^)#\s]+)(?:#[^)]*)?\)", page.read_text()):
            if "://" in target:
                continue
            if not (page.parent / target).exists():
                broken.append(f"{name}: {target}")
    assert broken == []


def test_cli_reference_covers_every_command() -> None:
    import typer

    from compose.cli.app import app

    text = (ROOT / "docs" / "cli.md").read_text()
    root = typer.main.get_command(app)
    missing = [
        name
        for name, command in root.commands.items()  # type: ignore[attr-defined]
        if not command.hidden and f"compose {name}" not in text
    ]
    assert missing == []


def test_no_references_to_the_old_project_in_user_docs() -> None:
    pattern = re.compile(r"spec[- ]?kit|speckit", re.I)
    assert [
        n for n in DOCS + ["docs/workflow-reference.md"] if pattern.search((ROOT / n).read_text())
    ] == []
