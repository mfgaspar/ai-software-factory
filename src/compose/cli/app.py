"""Top-level `compose` command."""

from __future__ import annotations

import typer

from compose import __version__
from compose.cli import build, clarity, feature, repo, runs, serve, setup, workflow

app = typer.Typer(
    name="compose",
    help="Spec-driven development workflows with traceability and cost tracking.",
    no_args_is_help=True,
    add_completion=False,
)
app.add_typer(repo.app, name="repo")
app.add_typer(feature.app, name="feature")
app.add_typer(workflow.app, name="workflow")
app.add_typer(clarity.app, name="clarity")
app.command("init")(setup.init)
app.command("check")(setup.check)
app.command("run")(runs.run)
app.command("build")(build.build)
app.command("status")(runs.status)
app.command("resume")(runs.resume)
app.command("abort")(runs.abort)
app.command("trace")(runs.trace)
app.command("changes")(runs.changes)
app.command("cost")(runs.cost)
app.command("serve")(serve.serve)
app.command("_execute", hidden=True)(runs.execute)


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
