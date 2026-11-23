"""``compose clarity``: the clarity foundation, as tracked runs on the clarity branch.

``compose clarity [SOURCES…]`` starts a run; a first word that isn't a subcommand
(``status``, ``questions``, ``answer``, ``validate``, ``merge``) is taken as a source, so a
source named like a subcommand needs ``./`` (``compose clarity ./status``).
"""

from __future__ import annotations

import subprocess
import sys
from enum import StrEnum
from pathlib import Path
from typing import Any

import typer
from rich.table import Table
from typer.core import TyperGroup

from compose.clarity import branch as clarity_branch
from compose.clarity import service
from compose.cli.common import console, err_console, handle_errors, open_store, print_json
from compose.cli.runs import (
    JSON_HELP,
    Progress,
    _finish,
    _is_interactive,
    _make_runner,
    follow,
    run_foreground,
    spawn,
    styled,
)
from compose.core import store
from compose.core.config import load_config
from compose.core.db import Database
from compose.core.home import Home
from compose.core.models import Repo, StepExec
from compose.engines.claude import install as installer
from compose.repos import registry
from compose.runner.errors import RunError
from compose.runner.recovery import recover_stale_runs
from compose.runner.steps.questions import answerer

REPO_HELP = "Repo name or id (default: here)."
DETACH_HELP = "Run in the background."


class Mode(StrEnum):
    MIXED = "mixed"
    AUTO = "auto"
    INTERACTIVE = "interactive"


class _SourcesGroup(TyperGroup):
    """A group whose bare form takes sources: an unknown first word routes to ``start``."""

    def parse_args(self, ctx: Any, args: list[str]) -> list[str]:  # typer's own click Context
        if not args or (args[0] not in self.commands and args[0] not in ctx.help_option_names):
            args = ["start", *args]
        return super().parse_args(ctx, args)


app = typer.Typer(
    cls=_SourcesGroup,
    help="The clarity foundation: start a run, answer its questions, validate and merge."
    " compose clarity [SOURCES...] [--mode mixed|auto|interactive] starts a run (options:"
    " compose clarity start --help); a source named like a subcommand needs ./.",
)


def _has_tty() -> bool:
    return sys.stdin.isatty() and sys.stdout.isatty()


def _attached(argv: list[str], cwd: Path) -> int:
    """Run ``argv`` attached to this terminal (tests replace this)."""
    return subprocess.run(argv, cwd=cwd, check=False).returncode


def _branch(home: Home) -> str:
    return load_config(home).clarity.branch


def _verdict(db: Database, run_id: str) -> dict[str, Any]:
    """The outputs of the run's last ``verdict`` and ``merge`` steps."""
    found: dict[str, Any] = {}
    for step in ("verdict", "merge"):
        rows = store.select(
            db, StepExec, "run_id = ? AND step_id = ?", (run_id, step), "started_at DESC"
        )
        if rows and rows[0].output:
            found[step] = rows[0].output
    return found


def _after(db: Database, as_json: bool, *, fail_exit: bool) -> Any:
    """Print the verdict and merge outcome of a finished clarity run; with ``fail_exit``,
    a completed run whose verdict isn't PASS exits 1."""

    def after(detail: dict[str, Any]) -> int | None:
        if detail["status"] != "completed":
            return None
        found = _verdict(db, detail["id"])
        result = (found.get("verdict") or {}).get("result")
        merged = found.get("merge") or {}
        if not as_json and result:
            line = f"CLARITY: {result}"
            if merged.get("merged"):
                line += " — merged into the default branch (push it when ready)"
            elif result == "PASS" and merged.get("pending_reason"):
                line += f" — merge pending: {merged['pending_reason']}"
            console.print(line, highlight=False, soft_wrap=True)
        return 1 if fail_exit and result != "PASS" else None

    return after


def _start_validate(
    db: Database, home: Home, target: Repo, *, detach: bool, as_json: bool, verbose: bool
) -> None:
    progress = None if as_json or detach else Progress(verbose)
    runner = _make_runner(db, home, interactive=False, progress=progress)
    created = runner.create_run(target, "clarity-validate")
    follow(
        db,
        home,
        runner,
        target,
        created,
        detach=detach,
        as_json=as_json,
        progress=progress,
        after=_after(db, as_json, fail_exit=True),
    )


# --------------------------------------------------------------- commands


@app.command("start", hidden=True)
@handle_errors
def start(
    sources: list[str] | None = typer.Argument(
        None, help="Paths or URLs to draft from, passed to /clarity as given."
    ),
    mode: Mode = typer.Option(Mode.MIXED, "--mode", help="mixed, auto or interactive."),
    repo: str | None = typer.Option(None, "--repo", help=REPO_HELP),
    detach: bool = typer.Option(False, "--detach", "-d", help=DETACH_HELP),
    interactive: bool | None = typer.Option(
        None,
        "--interactive/--no-interactive",
        help="Ask the questions here (default: when on a terminal); otherwise the run pauses.",
    ),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show each tool call."),
    as_json: bool = typer.Option(False, "--json", help=JSON_HELP),
) -> None:
    """Start a clarity run (mixed by default)."""
    words = list(sources or [])
    if mode is Mode.INTERACTIVE:
        _interactive(words, repo, detach=detach, as_json=as_json, verbose=verbose)
        return
    ask = _is_interactive(interactive, as_json) and not detach
    progress = None if as_json or detach else Progress(verbose)
    with open_store() as (home, db):
        target = registry.resolve_repo(db, repo, Path.cwd())
        runner = _make_runner(db, home, interactive=ask, progress=progress)
        inputs = {"sources": " ".join(words), "mode": mode.value}
        created = runner.create_run(target, "clarity", inputs)
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
            after=_after(db, as_json, fail_exit=False),
        )


def _interactive(
    sources: list[str], repo: str | None, *, detach: bool, as_json: bool, verbose: bool
) -> None:
    """``/clarity … interactive`` in Claude Code in the clarity worktree, then validate."""
    if detach:
        raise RunError("--mode interactive is a conversation; it can't run with --detach")
    if not _has_tty():
        raise RunError(
            "--mode interactive needs a terminal (it starts a Claude Code conversation);"
            " use --mode mixed or --mode auto here"
        )
    claude = installer.cli_path()
    if claude is None:
        raise RunError("Claude Code (claude) is not installed; see compose check")
    with open_store() as (home, db):
        target = registry.resolve_repo(db, repo, Path.cwd())
        recover_stale_runs(db, home)
        active = service.active_run(db, target)
        if active is not None:
            raise RunError(
                f"Repo {target.name} already has an active clarity run ({active.id});"
                f" answer it, or compose abort {active.id}"
            )
        worktree = clarity_branch.ensure_worktree(home, target, branch=_branch(home))
        installer.install(worktree, worktree=True)
        prompt = " ".join(["/clarity", *sources, "interactive"])
        if not as_json:
            console.print(f"Starting Claude Code in {worktree}", highlight=False)
        _attached([claude, prompt], worktree)
        _start_validate(db, home, target, detach=False, as_json=as_json, verbose=verbose)


@app.command("status")
@handle_errors
def status(
    repo: str | None = typer.Option(None, "--repo", help=REPO_HELP),
    as_json: bool = typer.Option(False, "--json", help=JSON_HELP),
) -> None:
    """Documents, verdict, open questions and constitution currency (no model call)."""
    with open_store() as (home, db):
        target = registry.resolve_repo(db, repo, Path.cwd())
        recover_stale_runs(db, home)
        data = service.status(db, home, target, _branch(home))
    if as_json:
        print_json(data)
        return
    if not data["started"]:
        console.print("Clarity hasn't started here. Start it with: compose clarity <sources>")
    else:
        table = Table("document", "status")
        for path, state in data["documents"].items():
            table.add_row(path, state)
        console.print(table)
        found = data["verdict"]
        if found is None:
            console.print("Verdict: none recorded yet")
        else:
            current = "current" if found["current"] else "stale (documents changed since)"
            console.print(f"Verdict: {found['result']}, {current}", highlight=False)
        q = data["questions"]
        console.print(f"Questions: {q['pending']} pending", highlight=False)
        stamp = "current" if data["constitution"]["current"] else "out of date"
        console.print(f"Constitution: {stamp}", highlight=False)
    if data["active_run"]:
        run = data["active_run"]
        console.print(f"Active run {run['id']}: ", styled(run["status"]), highlight=False)
    build = data["build"]
    if build["ok"]:
        console.print("compose build: ready", style="green")
    for problem in build["problems"]:
        console.print(
            f"compose build: refused — {problem['message']} Fix: {problem['fix']}",
            style="red",
            highlight=False,
            soft_wrap=True,
        )


@app.command("questions")
@handle_errors
def questions_(
    repo: str | None = typer.Option(None, "--repo", help=REPO_HELP),
    as_json: bool = typer.Option(False, "--json", help=JSON_HELP),
) -> None:
    """The repo's pending questions, in the order they're asked."""
    with open_store() as (home, db):
        target = registry.resolve_repo(db, repo, Path.cwd())
        found = service.pending(home, target, _branch(home))
    if as_json:
        print_json([q.model_dump(mode="json") for q in found])
        return
    if not found:
        console.print("No pending questions.")
        return
    table = Table("id", "kind", "document", "question", "options", "recommended")
    for q in found:
        options = " | ".join(q.options)
        if q.approver:
            options += f" (approver: {q.approver})"
        text = "\n".join([q.question, *(f"• {d}" for d in q.details)])
        table.add_row(q.id, q.kind, q.document or "", text, options, q.recommended or "")
    console.print(table)
    console.print(
        'Answer with: compose clarity answer <ID> "<answer>" (an option or your own words)',
        highlight=False,
    )


@app.command("answer")
@handle_errors
def answer(
    question_id: str = typer.Argument(..., metavar="ID", help="Question id (e.g. Q-007)."),
    text: str = typer.Argument(..., metavar="ANSWER", help="The answer."),
    by: str | None = typer.Option(None, "--by", help="Who answers (default: git user name)."),
    resume: bool = typer.Option(
        True, "--resume/--no-resume", help="Resume the paused clarity run when it can go on."
    ),
    repo: str | None = typer.Option(None, "--repo", help=REPO_HELP),
    detach: bool = typer.Option(False, "--detach", "-d", help="Resume in the background."),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show each tool call."),
    as_json: bool = typer.Option(False, "--json", help=JSON_HELP),
) -> None:
    """Record an answer; resume the paused clarity run once nothing it asked is pending."""
    with open_store() as (home, db):
        target = registry.resolve_repo(db, repo, Path.cwd())
        recover_stale_runs(db, home)
        who = by or answerer(Path(target.path))
        done = service.answer(db, home, target, _branch(home), {question_id: text}, who)
        recorded = [q.id for q in done.recorded]
        run = done.resumable if resume else None
        if run is None:
            left = len(service.pending(home, target, _branch(home)))
            if as_json:
                print_json({"recorded": recorded, "resumed_run": None, "pending": left})
            else:
                console.print(f"Recorded {question_id} ({who}); {left} pending.", highlight=False)
            return
        progress = None if as_json or detach else Progress(verbose)
        runner = _make_runner(db, home, interactive=False, progress=progress)
        runner.prepare_resume(run.id)
        if detach:
            pid = spawn(home, run.id, Path(target.path))
            if as_json:
                print_json({"recorded": recorded, "resumed_run": run.id, "pid": pid})
            else:
                console.print(
                    f"Recorded {question_id}; resumed run [bold]{run.id}[/bold] in the"
                    f" background.\nFollow it with: compose status {run.id}",
                    highlight=False,
                )
            return
        if not as_json:
            console.print(f"Recorded {question_id}; resuming run {run.id}", highlight=False)
        run_foreground(runner, run.id, progress)
        _finish(db, home, run.id, as_json, after=_after(db, as_json, fail_exit=False))


@app.command("validate")
@handle_errors
def validate(
    repo: str | None = typer.Option(None, "--repo", help=REPO_HELP),
    detach: bool = typer.Option(False, "--detach", "-d", help=DETACH_HELP),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show each tool call."),
    as_json: bool = typer.Option(False, "--json", help=JSON_HELP),
) -> None:
    """Run /clarity-validate as a tracked run; on PASS, refresh the constitution and merge.
    Exits 1 on FAIL."""
    with open_store() as (home, db):
        target = registry.resolve_repo(db, repo, Path.cwd())
        _start_validate(db, home, target, detach=detach, as_json=as_json, verbose=verbose)


@app.command("merge")
@handle_errors
def merge(
    repo: str | None = typer.Option(None, "--repo", help=REPO_HELP),
    as_json: bool = typer.Option(False, "--json", help=JSON_HELP),
) -> None:
    """Retry merging a passing clarity branch into the default branch. Exits 1 if pending."""
    with open_store() as (home, db):
        target = registry.resolve_repo(db, repo, Path.cwd())
        recover_stale_runs(db, home)
        outcome = service.merge(db, home, target, _branch(home))
        base = clarity_branch.default_branch(target)
    if as_json:
        print_json({"merged": outcome.merged, "pending_reason": outcome.pending_reason})
    elif outcome.merged:
        console.print(f"Merged into {base}. Push it when ready.", highlight=False)
    else:
        err_console.print(
            f"[yellow]merge pending:[/yellow] {outcome.pending_reason}",
            highlight=False,
            soft_wrap=True,
        )
    if not outcome.merged:
        raise typer.Exit(1)
