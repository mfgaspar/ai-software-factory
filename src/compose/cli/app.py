"""Top-level `compose` command."""

from __future__ import annotations

import typer

from compose import __version__
from compose.cli import feature, repo, workflow

app = typer.Typer(
    name="compose",
    help="Spec-driven development workflows with traceability and cost tracking.",
    no_args_is_help=True,
    add_completion=False,
)
app.add_typer(repo.app, name="repo")
app.add_typer(feature.app, name="feature")
app.add_typer(workflow.app, name="workflow")


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"compose {__version__}")
        raise typer.Exit()


@app.callback()
def root(
    version: bool = typer.Option(
        False,
        "--version",
        callback=_version_callback,
        is_eager=True,
        help="Show the compose version and exit.",
    ),
) -> None:
    """Spec-driven development workflows with traceability and cost tracking."""


def main() -> None:
    app()


if __name__ == "__main__":
    main()
