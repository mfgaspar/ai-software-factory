"""``compose repo ...``"""

from __future__ import annotations

import typer
from rich.table import Table

from compose.cli.common import console, handle_errors, open_store, print_json
from compose.repos import registry

app = typer.Typer(help="Register and manage repos.", no_args_is_help=True)


@app.command("add")
@handle_errors
def add(
    source: str = typer.Argument(..., help="Local path to a git checkout, or a git URL."),
    name: str | None = typer.Option(None, "--name", help="Short name (default: from source)."),
    as_json: bool = typer.Option(False, "--json", help="Print JSON."),
) -> None:
    """Register a local repo, or clone a git URL into the compose home."""
    with open_store() as (home, db):
        repo = registry.add_repo(db, home, source, name=name)
    if as_json:
        print_json(repo.model_dump(mode="json"))
    else:
        console.print(f"Added [bold]{repo.name}[/bold] ({repo.path})", highlight=False)


@app.command("list")
@handle_errors
def list_(as_json: bool = typer.Option(False, "--json", help="Print JSON.")) -> None:
    """List registered repos."""
    with open_store() as (_, db):
        repos = registry.list_repos(db)
    if as_json:
        print_json([r.model_dump(mode="json") for r in repos])
        return
    if not repos:
        console.print("No repos registered. Add one with `compose repo add <path|url>`.")
        return
    table = Table("name", "path", "default branch", "origin")
    for r in repos:
        table.add_row(r.name, r.path, r.default_branch or "", r.origin_url or "")
    console.print(table)


@app.command("remove")
@handle_errors
def remove(
    ref: str = typer.Argument(..., help="Repo name or id."),
    delete_clone: bool = typer.Option(
        False, "--delete-clone", help="Also delete the folder (only for repos compose cloned)."
    ),
    force: bool = typer.Option(False, "--force", help="Remove even if it has run history."),
) -> None:
    """Unregister a repo."""
    with open_store() as (home, db):
        repo = registry.remove_repo(db, home, ref, delete_clone=delete_clone, force=force)
    console.print(f"Removed {repo.name}", highlight=False)
