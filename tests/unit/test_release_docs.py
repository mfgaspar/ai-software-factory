"""The shipped documentation stays in step with the code."""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

from compose import __version__
from compose.api.app import create_app

ROOT = Path(__file__).parents[2]
DOCS = ["README.md", "docs/cli.md", "docs/api.md", "docs/custom-workflows.md", "docs/clarity.md"]


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


# The old project's name, assembled so this file doesn't contain it.
_S, _K, _I = "spec", "kit", "ify"
OLD_NAME = re.compile(rf"{_S}[-_ ]?{_K}|\\.{_S}{_I}/", re.I)


def _repo_files() -> list[Path]:
    """Tracked and untracked (not ignored) files of this checkout."""
    listed = subprocess.run(
        ["git", "ls-files", "-co", "--exclude-standard", "-z"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    return [ROOT / name for name in listed.split("\0") if name and (ROOT / name).is_file()]


def test_no_references_to_the_old_project_anywhere() -> None:
    """compose neither depends on nor mentions the project it was modeled on."""
    offenders = []
    for path in _repo_files():
        try:
            text = path.read_text()
        except UnicodeDecodeError:
            continue
        if OLD_NAME.search(text) or OLD_NAME.search(path.name):
            offenders.append(str(path.relative_to(ROOT)))
    assert offenders == []


def test_install_scripts() -> None:
    sh = ROOT / "install.sh"
    ps1 = ROOT / "install.ps1"
    assert sh.stat().st_mode & 0o111, "install.sh must be executable"
    subprocess.run(["sh", "-n", str(sh)], check=True)
    help_text = subprocess.run(
        ["sh", str(sh), "--help"], capture_output=True, text=True, check=True
    ).stdout
    assert "--source" in help_text and "set -eu" not in help_text
    for script in (sh, ps1):
        text = script.read_text()
        assert "uv tool install --force --reinstall --python" in text and "compose check" in text
    readme = (ROOT / "README.md").read_text()
    assert "./install.sh" in readme and "install.ps1" in readme
