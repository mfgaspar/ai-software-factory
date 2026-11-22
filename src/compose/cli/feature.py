"""``compose feature ...`` (also used by the skills, with ``--json``)."""

from __future__ import annotations

from pathlib import Path

import typer
from rich.table import Table

from compose.cli.common import console, handle_errors, open_store, print_json
from compose.repos import features, git, registry

app = typer.Typer(help="Create and locate features (specifications).", no_args_is_help=True)


def _record(cwd: Path, name: str) -> None:
    """Record the feature in the database when the repo is registered (best effort)."""
    with open_store() as (_, db):
        repo = registry.find_repo_for_path(db, cwd)
        if repo is not None:
            features.upsert_feature(db, repo, name)


@app.command("new")
@handle_errors
def new(
    description: list[str] = typer.Argument(..., help="What the feature is about."),
    short_name: str | None = typer.Option(None, "--name", help="Short name to use."),
    no_switch: bool = typer.Option(False, "--no-switch", help="Create the branch only."),
    as_json: bool = typer.Option(False, "--json", help="Print JSON."),
) -> None:
    """Create a feature branch and specs folder in the current checkout.

    Inside a workflow run this returns the run's feature and creates nothing.
    """
    cwd = Path.cwd()
    paths, created = features.create_feature(
        cwd, " ".join(description), short_name=short_name, switch=not no_switch
    )
    if created:
        _record(cwd, paths.name)
    if as_json:
        print_json({**paths.to_json(), "created": created})
    elif created:
        console.print(f"Created feature [bold]{paths.name}[/bold] in {paths.feature_dir}")
    else:
        console.print(f"Using current feature [bold]{paths.name}[/bold]")


@app.command("paths")
@handle_errors
def paths_(as_json: bool = typer.Option(False, "--json", help="Print JSON.")) -> None:
    """Paths of the current feature (from COMPOSE_FEATURE or the current branch)."""
    paths = features.resolve_current(Path.cwd())
    if as_json:
        print_json(paths.to_json())
        return
    for key, value in paths.to_json().items():
        console.print(f"{key}: {value}", highlight=False)


@app.command("list")
@handle_errors
def list_(as_json: bool = typer.Option(False, "--json", help="Print JSON.")) -> None:
    """List features in the current repo (from branches and specs folders)."""
    root = git.toplevel(Path.cwd())
    items = features.list_features(root)
    if as_json:
        print_json([vars(i) for i in items])
        return
    table = Table("feature", "branch", "specs folder")
    for i in items:
        table.add_row(i.name, "yes" if i.has_branch else "", "yes" if i.has_dir else "")
    console.print(table)


@app.command("show")
@handle_errors
def show(
    name: str = typer.Argument(..., help="Feature name, e.g. 003-user-auth."),
    as_json: bool = typer.Option(False, "--json", help="Print JSON."),
) -> None:
    """Show a feature's paths and which files exist in this checkout."""
    root = git.toplevel(Path.cwd())
    paths = features.feature_paths(root, name)
    files = {
        "spec": paths.spec_file.exists(),
        "plan": paths.plan_file.exists(),
        "tasks": paths.tasks_file.exists(),
    }
    data = {**paths.to_json(), "branch_exists": git.branch_exists(root, name), "files": files}
    if as_json:
        print_json(data)
        return
    for key, value in data.items():
        console.print(f"{key}: {value}", highlight=False)
