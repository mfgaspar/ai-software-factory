"""``compose build``: build a feature on the default workflow, after the pre-run check."""

from __future__ import annotations

from pathlib import Path

import typer

from compose.clarity import service
from compose.cli.common import handle_errors, open_store
from compose.cli.runs import (
    INPUT_HELP,
    JSON_HELP,
    Progress,
    _is_interactive,
    _make_runner,
    follow,
    parse_inputs,
)
from compose.repos import registry
from compose.workflows import loader


@handle_errors
def build(
    description: str = typer.Argument(..., help="What to build: the feature, in a sentence."),
    workflow: str | None = typer.Option(
        None, "--workflow", help="Workflow id or path (default: defaults.workflow, automated)."
    ),
    repo: str | None = typer.Option(None, "--repo", help="Repo name or id (default: here)."),
    feature: str | None = typer.Option(
        None, "--feature", help="Existing feature (NNN-name); default: a new one."
    ),
    inputs: list[str] | None = typer.Option(None, "-i", "--input", help=INPUT_HELP),
    detach: bool = typer.Option(False, "--detach", "-d", help="Run in the background."),
    interactive: bool | None = typer.Option(
        None,
        "--interactive/--no-interactive",
        help="Ask for missing inputs and gate decisions (default: when on a terminal).",
    ),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show each tool call."),
    as_json: bool = typer.Option(False, "--json", help=JSON_HELP),
) -> None:
    """Build a feature: the default workflow with DESCRIPTION as its spec (pre-run check
    first: a repo that started clarity needs a current PASS)."""
    values = parse_inputs(inputs)
    ask = _is_interactive(interactive, as_json) and not detach
    progress = None if as_json or detach else Progress(verbose)
    with open_store() as (home, db):
        target = registry.resolve_repo(db, repo, Path.cwd())
        runner = _make_runner(db, home, interactive=ask, progress=progress)
        loaded = loader.resolve(workflow or runner.config.defaults.workflow, Path(target.path))
        values = service.build_inputs(loaded.definition, description, values)
        created = runner.create_run(target, loaded, values, feature=feature)
        follow(
            db,
            home,
            runner,
            target,
            created,
            detach=detach,
            as_json=as_json,
            progress=progress,
            warnings=runner.last_warnings,
        )
