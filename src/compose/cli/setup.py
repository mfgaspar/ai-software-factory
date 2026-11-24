"""``compose init`` and ``compose check``."""

from __future__ import annotations

from pathlib import Path

import typer
from rich.table import Table

from compose import notify
from compose.cli.common import console, handle_errors, open_store, print_json
from compose.core.config import load_config
from compose.engines.registry import default_registry
from compose.repos.setup import check_all, init_repo


@handle_errors
def init(
    engine: str | None = typer.Option(
        None, "--engine", help="Coding engine to set up (default: the configured one)."
    ),
    path: Path = typer.Option(Path("."), "--path", help="Repository to initialize."),
    as_json: bool = typer.Option(False, "--json", help="Print JSON."),
) -> None:
    """Make a repository ready for compose: skills, templates, constitution, registration.

    Nothing is committed; commit the listed files if you want them shared.
    """
    with open_store() as (home, db):
        name = engine or load_config(home).defaults.engine
        report = init_repo(db, home, path, default_registry(), name)
    files = report.to_commit()
    if as_json:
        print_json(
            {
                "repo": report.repo.model_dump(mode="json"),
                "registered": report.registered,
                "written": files,
            }
        )
        return
    action = "Registered" if report.registered else "Already registered:"
    console.print(f"{action} [bold]{report.repo.name}[/bold] ({report.repo.id}) at {report.root}")
    if files:
        console.print(f"Wrote {len(files)} file(s). To share them with your team, commit:")
        for name in files:
            console.print(f"  {name}", highlight=False)
    else:
        console.print("Everything was already in place.")
    if notify.enabled(load_config(home).notifications.enabled):
        console.print(notify.setup_hint(), highlight=False)
    console.print("Next: [bold]compose check[/bold], then try [bold]/compose-specify[/bold].")


@handle_errors
def check(
    engine: str | None = typer.Option(None, "--engine", help="Engine to check."),
    as_json: bool = typer.Option(False, "--json", help="Print JSON."),
) -> None:
    """Check prerequisites: git, the engine, and the current repository."""
    with open_store() as (home, db):
        name = engine or load_config(home).defaults.engine
        items = check_all(db, Path.cwd(), default_registry(), name)
    failed = [i for i in items if not i.ok and i.required]
    if as_json:
        print_json({"ok": not failed, "checks": [i.to_json() for i in items]})
    else:
        table = Table("check", "status", "detail", "fix")
        for item in items:
            status = (
                "[green]ok[/green]"
                if item.ok
                else ("[red]fail[/red]" if item.required else "[yellow]warn[/yellow]")
            )
            table.add_row(item.name, status, item.detail, item.fix or "")
        console.print(table)
    if failed:
        raise typer.Exit(1)
