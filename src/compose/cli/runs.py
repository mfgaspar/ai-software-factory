"""Running workflows and reporting on runs: ``compose run``, ``status``, ``resume``,
``abort``, ``trace``, ``changes`` and ``cost``.

Exit codes of ``run`` and ``resume``: 0 completed (or detached), 1 failed or aborted,
3 paused at a gate.
"""

from __future__ import annotations

import asyncio
import os
import subprocess
import sys
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any

import typer
from rich.table import Table
from rich.text import Text
from rich.tree import Tree

from compose.clarity.questions import Question
from compose.cli.common import console, err_console, handle_errors, open_store, print_json
from compose.core import procs
from compose.core.db import Database
from compose.core.home import Home
from compose.core.models import Repo, Run, RunStatus
from compose.engines.registry import EngineRegistry, default_registry
from compose.repos import registry
from compose.runner.recovery import recover_stale_runs
from compose.runner.runner import Interaction, Runner
from compose.tracking import views
from compose.tracking.aggregate import GroupBy
from compose.workflows.schema import InputSpec

EXIT_PAUSED = 3
EXIT_CODES = {
    RunStatus.COMPLETED: 0,
    RunStatus.PAUSED: EXIT_PAUSED,
    RunStatus.FAILED: 1,
    RunStatus.ABORTED: 1,
}
STATUS_STYLE = {
    "completed": "green",
    "running": "cyan",
    "paused": "yellow",
    "failed": "red",
    "aborted": "red",
    "skipped": "dim",
    "pending": "dim",
    "created": "dim",
}
SYMBOL = {"completed": "✓", "failed": "✗", "paused": "⏸", "skipped": "-", "aborted": "✗"}

INPUT_HELP = "Workflow input as key=value; repeat for more. Use key=@file to read a file."
JSON_HELP = "Print JSON."


def engine_registry() -> EngineRegistry:
    """The engines runs use (tests replace this)."""
    return default_registry()


# ----------------------------------------------------------------- helpers


def parse_inputs(pairs: list[str] | None) -> dict[str, Any]:
    values: dict[str, Any] = {}
    for pair in pairs or []:
        key, sep, value = pair.partition("=")
        if not sep or not key.strip():
            raise typer.BadParameter(f"{pair!r} is not key=value", param_hint="-i/--input")
        if value.startswith("@"):
            path = Path(value[1:]).expanduser()
            try:
                value = path.read_text()
            except OSError as exc:
                raise typer.BadParameter(f"cannot read {path}: {exc}") from exc
        values[key.strip()] = value
    return values


def parse_time(value: str | None, option: str) -> datetime | None:
    if value is None:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError as exc:
        raise typer.BadParameter(
            f"{value!r} is not a date or time (e.g. 2026-11-01 or 2026-11-01T09:00)",
            param_hint=option,
        ) from exc


def money(value: float) -> str:
    return f"${value:.4f}" if value < 1 else f"${value:.2f}"


def duration(ms: int | None) -> str:
    if ms is None:
        return ""
    seconds = ms / 1000
    if seconds < 60:
        return f"{seconds:.1f}s"
    minutes, secs = divmod(int(seconds), 60)
    return f"{minutes}m{secs:02d}s"


def styled(status: str) -> Text:
    return Text(status, style=STATUS_STYLE.get(status, ""))


def _interaction(interactive: bool) -> Interaction:
    if not interactive:
        return Interaction()

    def ask_input(name: str, spec: InputSpec) -> str:
        label = f"{name} ({spec.description})" if spec.description else name
        return str(typer.prompt(label))

    def ask_gate(message: str, options: list[str]) -> str:
        console.print(f"[yellow]?[/yellow] {message}", highlight=False)
        return str(typer.prompt(f"Choose {'/'.join(options)}"))

    def ask_confirm(message: str) -> bool:
        return bool(typer.confirm(message, default=True))

    return Interaction(
        interactive=True,
        ask_input=ask_input,
        ask_gate=ask_gate,
        ask_confirm=ask_confirm,
        ask_question=ask_question,
    )


def ask_question(q: Question) -> str:
    """Show a question with its numbered options and recommendation; Enter takes the
    recommendation (or leaves the question for later when there's none)."""
    where = f" {q.document}" if q.document else ""
    console.print(f"[yellow]?[/yellow] [bold]{q.id}[/bold] [dim]{q.kind}{where}[/dim]")
    console.print(q.question, highlight=False, soft_wrap=True)
    for number, option in enumerate(q.options, 1):
        mark = " [green](recommended)[/green]" if option == q.recommended else ""
        console.print(f"  {number}. {option}{mark}", highlight=False)
    if q.recommended and q.recommended not in q.options:
        console.print(f"  Recommended: {q.recommended}", highlight=False)
    hint = f"Enter takes {q.recommended!r}" if q.recommended else "Enter skips it"
    while True:
        text = str(typer.prompt(f"Answer ({hint})", default="", show_default=False)).strip()
        if not text:
            return q.recommended or ""
        if text.isdigit() and 1 <= int(text) <= len(q.options):
            return q.options[int(text) - 1]
        if q.free_text and q.kind != "approval" or text in q.options:
            return text
        console.print("[red]Choose one of the numbered options.[/red]")


class Progress:
    """Prints a line per step as a foreground run goes."""

    def __init__(self, verbose: bool) -> None:
        self.verbose = verbose
        self.depth: dict[str, int] = {}

    def __call__(self, event: dict[str, Any]) -> None:
        kind = event.get("type")
        if kind == "step_started":
            parent = event.get("parent_exec_id")
            depth = self.depth[parent] + 1 if parent in self.depth else 0
            self.depth[event.get("exec_id", "")] = depth
            console.print(
                f"{'  ' * depth}[cyan]▸[/cyan] {event.get('key') or event.get('step_id')}"
                f" [dim]{event.get('step_type') or ''}[/dim]",
                highlight=False,
            )
        elif kind == "step_finished":
            status = str(event.get("status"))
            pad = "  " * self.depth.get(event.get("exec_id", ""), 0)
            cost = event.get("cost_usd") or 0
            extra = f" [dim]{money(cost)}[/dim]" if cost else ""
            shown = event.get("error") and status != "paused"
            error = f" [red]{event['error']}[/red]" if shown else ""
            style = STATUS_STYLE.get(status, "")
            console.print(
                f"{pad}[{style}]{SYMBOL.get(status, '·')}[/{style}] {event.get('step_id')}"
                f" [{style}]{status}[/{style}]{extra}{error}",
                highlight=False,
            )
        elif kind == "engine_event" and self.verbose:
            inner = event.get("event") or {}
            if inner.get("kind") == "tool_call":
                console.print(f"    [dim]· {inner.get('name')}[/dim]", highlight=False)
        elif kind == "gate_waiting":
            console.print(
                f"[yellow]⏸ waiting at gate {event.get('step_id')}:[/yellow]"
                f" {event.get('message')} ({'/'.join(event.get('options') or [])})",
                highlight=False,
            )
        elif kind == "questions_waiting":
            console.print(
                f"[yellow]⏸ waiting for answers at {event.get('step_id')}:[/yellow]"
                f" {', '.join(event.get('ids') or [])}",
                highlight=False,
            )


def _make_runner(
    db: Database, home: Home, *, interactive: bool, progress: Progress | None
) -> Runner:
    recover_stale_runs(db, home)
    return Runner(
        db,
        home,
        engines=engine_registry(),
        interaction=_interaction(interactive),
        on_event=progress,
    )


def _is_interactive(flag: bool | None, as_json: bool) -> bool:
    if flag is not None:
        return flag
    return not as_json and sys.stdin.isatty()


def spawn(home: Home, run_id: str, cwd: Path) -> int:
    """Execute a run in a background process that outlives this command."""
    log = home.run_dir(run_id) / "process.log"
    log.parent.mkdir(parents=True, exist_ok=True)
    with log.open("ab") as out:
        process = subprocess.Popen(
            [sys.executable, "-m", "compose.cli.app", "_execute", run_id],
            cwd=cwd,
            stdin=subprocess.DEVNULL,
            stdout=out,
            stderr=subprocess.STDOUT,
            env=os.environ.copy(),
            **procs.detached_kwargs(),
        )
    return process.pid


def _finish(
    db: Database,
    home: Home,
    run_id: str,
    as_json: bool,
    *,
    warnings: list[str] | None = None,
    after: Callable[[dict[str, Any]], int | None] | None = None,
) -> None:
    """Print the run's outcome and exit with its code. ``after`` runs once the outcome is
    printed and may return another exit code."""
    detail = views.run_detail(db, home, run_id)
    status = RunStatus(detail["status"])
    if warnings is not None:
        detail["warnings"] = warnings
    if as_json:
        print_json(detail)
    else:
        _print_outcome(detail)
    override = after(detail) if after else None
    raise typer.Exit(override if override is not None else EXIT_CODES.get(status, 0))


def follow(
    db: Database,
    home: Home,
    runner: Runner,
    target: Repo,
    created: Run,
    *,
    detach: bool,
    as_json: bool,
    progress: Progress | None,
    warnings: list[str] | None = None,
    after: Callable[[dict[str, Any]], int | None] | None = None,
) -> None:
    """Run a created run in the foreground (then exit with its code) or in the background.
    Warnings go to stderr, and in the JSON under ``warnings``."""
    for warning in [] if as_json else warnings or []:
        err_console.print(f"[yellow]warning:[/yellow] {warning}", highlight=False)
    if detach:
        pid = spawn(home, created.id, Path(target.path))
        if as_json:
            extra = {} if warnings is None else {"warnings": warnings}
            print_json({**views.run_brief(db, created), "pid": pid, **extra})
        else:
            console.print(
                f"Started run [bold]{created.id}[/bold] in the background.\n"
                f"Follow it with: compose status {created.id}",
                highlight=False,
            )
        return
    if progress is not None:
        on = views.run_brief(db, created)["feature"] or "clarity"
        console.print(
            f"Run [bold]{created.id}[/bold]: {created.workflow_id} on {on}",
            highlight=False,
        )
    asyncio.run(runner.execute(created.id))
    _finish(db, home, created.id, as_json, warnings=warnings, after=after)


def _print_outcome(detail: dict[str, Any]) -> None:
    status = detail["status"]
    totals = detail["totals"]
    changes = totals["changes"]
    console.print(
        Text.assemble(
            "Run ",
            (detail["id"], "bold"),
            " ",
            styled(status),
            f"  {money(totals['cost_usd'])}, {changes['files']} files"
            f" +{changes['added']} -{changes['removed']}",
        )
    )
    if detail.get("waiting") and detail["waiting"].get("questions") is not None:
        _print_questions(detail["waiting"]["questions"])
    elif detail.get("waiting"):
        gate = detail["waiting"]
        options = "|".join(gate.get("options") or [])
        console.print(
            f"Waiting at gate [bold]{gate['step_id']}[/bold]: {gate.get('message') or ''}\n"
            f"Continue with: compose resume {detail['id']} --choice <{options}>",
            highlight=False,
            soft_wrap=True,
        )
    elif status == "failed":
        console.print(
            f"[red]{detail.get('error')}[/red]\nRetry with: compose resume {detail['id']}",
            highlight=False,
            soft_wrap=True,
        )


def _print_questions(pending: list[dict[str, Any]]) -> None:
    console.print(f"Waiting for answers to {len(pending)} question(s):")
    for q in pending:
        options = " | ".join(q.get("options") or [])
        extras = [f"options: {options}"] if options else []
        if q.get("recommended"):
            extras.append(f"recommended: {q['recommended']}")
        if q.get("approver"):
            extras.append(f"approver: {q['approver']}")
        tail = f" [dim]({'; '.join(extras)})[/dim]" if extras else ""
        kind = f" [dim]{q['kind']}[/dim]" if q.get("kind") else ""
        console.print(
            f"  [bold]{q['id']}[/bold]{kind} {q.get('question') or ''}{tail}",
            highlight=False,
            soft_wrap=True,
        )
    console.print('Answer with: compose clarity answer <ID> "<answer>"', highlight=False)


def _repo_or_none(db: Database, ref: str | None) -> Repo | None:
    if ref:
        return registry.get_repo(db, ref)
    return registry.find_repo_for_path(db, Path.cwd())


# --------------------------------------------------------------- commands


@handle_errors
def run(
    workflow: str | None = typer.Argument(
        None,
        help="Workflow id, or path to a workflow file/folder (default: defaults.workflow "
        "in config, automated).",
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
    """Start a workflow run on a feature (a new one unless --feature)."""
    values = parse_inputs(inputs)
    ask = _is_interactive(interactive, as_json) and not detach
    progress = None if as_json or detach else Progress(verbose)
    with open_store() as (home, db):
        target = registry.resolve_repo(db, repo, Path.cwd())
        runner = _make_runner(db, home, interactive=ask, progress=progress)
        created = runner.create_run(target, workflow, values, feature=feature)
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


@handle_errors
def resume(
    run_id: str = typer.Argument(..., help="Run id."),
    inputs: list[str] | None = typer.Option(None, "-i", "--input", help=INPUT_HELP),
    choice: str | None = typer.Option(None, "--choice", help="Decision for the waiting gate."),
    detach: bool = typer.Option(False, "--detach", "-d", help="Continue in the background."),
    interactive: bool | None = typer.Option(
        None, "--interactive/--no-interactive", help="Ask for gate decisions."
    ),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show each tool call."),
    as_json: bool = typer.Option(False, "--json", help=JSON_HELP),
) -> None:
    """Continue a paused or failed run, optionally with new inputs or a gate decision."""
    values = parse_inputs(inputs)
    ask = _is_interactive(interactive, as_json) and not detach
    progress = None if as_json or detach else Progress(verbose)
    with open_store() as (home, db):
        runner = _make_runner(db, home, interactive=ask, progress=progress)
        run_ = runner.prepare_resume(run_id, values, choice=choice)
        if detach:
            target = registry.get_repo(db, run_.repo_id)
            pid = spawn(home, run_.id, Path(target.path))
            if as_json:
                print_json({**views.run_brief(db, run_), "pid": pid})
            else:
                console.print(f"Resumed run [bold]{run_.id}[/bold] in the background.")
            return
        asyncio.run(runner.execute(run_.id))
        _finish(db, home, run_.id, as_json)


@handle_errors
def execute(run_id: str = typer.Argument(...)) -> None:
    """Execute a created, paused or failed run (used by --detach)."""
    with open_store() as (home, db):
        runner = Runner(db, home, engines=engine_registry())
        finished = asyncio.run(runner.execute(run_id))
        raise typer.Exit(EXIT_CODES.get(finished.status, 0))


@handle_errors
def abort(
    run_id: str = typer.Argument(..., help="Run id."),
    as_json: bool = typer.Option(False, "--json", help=JSON_HELP),
) -> None:
    """Abort a run. A running one stops at its next engine event; it cannot be resumed."""
    with open_store() as (home, db):
        recover_stale_runs(db, home)
        run_ = Runner(db, home, engines=engine_registry()).request_abort(run_id)
        if as_json:
            print_json(views.run_brief(db, run_))
        elif run_.status is RunStatus.RUNNING:
            console.print(f"Abort requested; run {run_.id} stops at its next step event.")
        else:
            console.print(f"Run {run_.id} aborted.", highlight=False)


@handle_errors
def status(
    run_id: str | None = typer.Argument(None, help="Run id (omit to list runs)."),
    repo: str | None = typer.Option(None, "--repo", help="Only this repo (default: here)."),
    feature: str | None = typer.Option(None, "--feature", help="Only this feature."),
    state: str | None = typer.Option(None, "--status", help="Only runs with this status."),
    limit: int = typer.Option(20, "--limit", "-n", help="How many runs to list (0: all)."),
    as_json: bool = typer.Option(False, "--json", help=JSON_HELP),
) -> None:
    """List runs, or show one run with the status, cost and changes of each step."""
    with open_store() as (home, db):
        recover_stale_runs(db, home)
        if run_id is not None:
            detail = views.run_detail(db, home, run_id)
            if as_json:
                print_json(detail)
            else:
                _print_detail(detail)
            return
        target = _repo_or_none(db, repo)
        feat = None
        if feature is not None:
            if target is None:
                raise views.ViewError("--feature needs --repo outside a registered repo")
            feat = views.find_feature(db, target, feature)
        try:
            wanted = RunStatus(state) if state else None
        except ValueError as exc:
            allowed = ", ".join(s.value for s in RunStatus)
            raise typer.BadParameter(f"use one of {allowed}", param_hint="--status") from exc
        runs = views.list_runs(db, repo=target, feature=feat, status=wanted, limit=limit or None)
        if as_json:
            print_json(runs)
            return
        if not runs:
            console.print("No runs yet. Start one with: compose run <workflow> -i spec=...")
            return
        table = Table("workflow", "feature", "status", "step", "cost", "created")
        table.add_column("run", no_wrap=True)
        for r in runs:
            table.add_row(
                r["workflow_id"],
                r["feature"] or "clarity",
                styled(r["status"]),
                r["current_step_id"] or "",
                money(r["cost_usd"]),
                str(r["created_at"])[:16].replace("T", " "),
                r["id"],
            )
        console.print(table)


def _step_name(step: dict[str, Any]) -> str:
    name = str(step["step_id"])
    if step.get("iteration") is not None:
        name += f"[{step['iteration']}]"
    if step.get("attempt", 1) > 1:
        name += f" (attempt {step['attempt']})"
    return name


def _print_detail(detail: dict[str, Any]) -> None:
    console.print(
        Text.assemble(
            ("Run ", ""),
            (detail["id"], "bold"),
            f"  {detail['workflow_id']} {detail['workflow_version']}  ",
            styled(detail["status"]),
        )
    )
    where = f"feature {detail['feature']}" if detail["feature"] else "scope repo"
    console.print(
        f"repo {detail['repo']}, {where}\n"
        f"worktree {detail['worktree']}\nrun files {detail['run_dir']}",
        style="dim",
        highlight=False,
    )
    by_parent: dict[str | None, list[dict[str, Any]]] = {}
    exec_ids = {s["exec_id"] for s in detail["steps"]}
    for step in detail["steps"]:
        parent = step["parent_exec_id"] if step["parent_exec_id"] in exec_ids else None
        by_parent.setdefault(parent, []).append(step)
    table = Table("step", "type", "status", "time", "cost", "tokens in/out", "files", "+/-")

    def add(parent: str | None, depth: int) -> None:
        for step in by_parent.get(parent, []):
            tokens = step["tokens"]
            changes = step["changes"]
            table.add_row(
                "  " * depth + _step_name(step),
                step["type"],
                styled(step["status"]),
                duration(step["duration_ms"]),
                money(step["cost_usd"]) if step["cost_usd"] else "",
                f"{tokens['input']}/{tokens['output']}" if tokens["input"] else "",
                str(changes["files"]) if changes["files"] else "",
                f"+{changes['added']} -{changes['removed']}" if changes["files"] else "",
            )
            add(step["exec_id"], depth + 1)

    add(None, 0)
    console.print(table)
    _print_outcome(detail)


@handle_errors
def trace(
    run_id: str = typer.Argument(..., help="Run id."),
    step: str | None = typer.Option(None, "--step", help="Only this step id."),
    full: bool = typer.Option(False, "--full", help="Show whole tool inputs and results."),
    as_json: bool = typer.Option(False, "--json", help=JSON_HELP),
) -> None:
    """Every action of each step (messages, tool calls, results), hooks nested."""
    with open_store() as (_, db):
        data = views.trace(db, run_id, step)
    if as_json:
        print_json(data)
        return
    width = None if full else 100
    root = Tree(f"[bold]{data['run_id']}[/bold] {data['status']}")
    for hook in data["run_hooks"]:
        _hook_node(root, hook, width)
    for s in data["steps"]:
        label = Text.assemble((_step_name(s), "bold"), f" {s['type']} ", styled(s["status"]))
        if s["cost_usd"]:
            label.append(f" {money(s['cost_usd'])}", style="dim")
        node = root.add(label)
        before = [h for h in s["hooks"] if h["event"].startswith("before")]
        for hook in before:
            _hook_node(node, hook, width)
        for action in s["actions"]:
            node.add(_action_text(action, width))
        for hook in s["hooks"]:
            if hook not in before:
                _hook_node(node, hook, width)
    console.print(root)


def _clip(text: str | None, width: int | None) -> str:
    text = (text or "").replace("\n", " ")
    return text if width is None or len(text) <= width else text[: width - 1] + "…"


def _action_text(action: dict[str, Any], width: int | None) -> Text:
    kind = action["kind"]
    if kind == "message":
        return Text(_clip(action["input"], width), style="")
    if kind == "tool_call":
        return Text.assemble(
            ("→ ", "cyan"),
            (action["tool_name"] or "", "bold"),
            " ",
            (_clip(action["input"], width), "dim"),
        )
    if kind == "tool_result":
        style = "red" if action["is_error"] else "dim"
        return Text.assemble(("← ", style), (_clip(action["result"], width), style))
    return Text(f"{kind} {_clip(action['input'] or action['result'], width)}")


def _hook_node(parent: Tree, hook: dict[str, Any], width: int | None) -> None:
    if hook["kind"] == "builtin" and hook["status"] != "failed":
        return  # tracking itself; shown in --json
    label = Text.assemble(
        ("hook ", "magenta"), f"{hook['event']} {hook['name']} ", styled(hook["status"])
    )
    if hook["cost_usd"]:
        label.append(f" {money(hook['cost_usd'])}", style="dim")
    if hook["error"]:
        label.append(f" {hook['error']}", style="red")
    node = parent.add(label)
    for action in hook["actions"]:
        node.add(_action_text(action, width))


@handle_errors
def changes(
    run_id: str = typer.Argument(..., help="Run id."),
    step: str | None = typer.Option(None, "--step", help="Only this step id."),
    as_json: bool = typer.Option(False, "--json", help=JSON_HELP),
) -> None:
    """Files and lines each step changed."""
    with open_store() as (_, db):
        data = views.changes(db, run_id, step)
    if as_json:
        print_json(data)
        return
    if not data["steps"]:
        console.print("No file changes recorded.")
        return
    table = Table("step", "file", "status", "+", "-")
    for s in data["steps"]:
        for i, f in enumerate(s["files"]):
            path = f["path"] if not f["old_path"] else f"{f['old_path']} → {f['path']}"
            table.add_row(
                _step_name(s) if i == 0 else "",
                path,
                f["status"],
                "" if f["added"] is None else str(f["added"]),
                "" if f["removed"] is None else str(f["removed"]),
            )
    console.print(table)
    t = data["totals"]
    console.print(f"{t['files']} files, +{t['added']} -{t['removed']}")


@handle_errors
def cost(
    repo: str | None = typer.Option(None, "--repo", help="Only this repo (default: here)."),
    feature: str | None = typer.Option(None, "--feature", help="Only this feature."),
    run_id: str | None = typer.Option(None, "--run", help="Only this run (with child runs)."),
    by: str = typer.Option(
        "", "--by", help="Group by step, run, feature, repo or day (default: run, or step)."
    ),
    since: str | None = typer.Option(None, "--since", help="From this date/time (UTC)."),
    until: str | None = typer.Option(None, "--until", help="Before this date/time (UTC)."),
    every_repo: bool = typer.Option(False, "--all", help="All repos, wherever you are."),
    as_json: bool = typer.Option(False, "--json", help=JSON_HELP),
) -> None:
    """Cost, tokens and changes, grouped and filtered."""
    group = by or ("step" if run_id else "run")
    if group not in ("step", "run", "feature", "repo", "day"):
        raise typer.BadParameter("use step, run, feature, repo or day", param_hint="--by")
    start, end = parse_time(since, "--since"), parse_time(until, "--until")
    with open_store() as (_, db):
        target = None
        if not every_repo and run_id is None:
            target = _repo_or_none(db, repo)
        elif repo:
            target = registry.get_repo(db, repo)
        feat = None
        if feature is not None:
            if target is None:
                raise views.ViewError("--feature needs --repo outside a registered repo")
            feat = views.find_feature(db, target, feature)
        group_by: GroupBy = group  # type: ignore[assignment]
        data = views.cost(
            db, group_by, repo=target, feature=feat, run_id=run_id, since=start, until=end
        )
    if as_json:
        print_json(data)
        return
    table = Table(group, "cost", "input", "output", "cache read", "cache write", "files", "+/-")
    rows = [*data["groups"], {**data["total"], "label": "total"}]
    for i, g in enumerate(rows):
        tokens, ch = g["tokens"], g["changes"]
        table.add_row(
            Text(str(g["label"]), style="bold" if i == len(rows) - 1 else ""),
            money(g["cost_usd"]),
            str(tokens["input"]),
            str(tokens["output"]),
            str(tokens["cache_read"]),
            str(tokens["cache_write"]),
            str(ch["files"]),
            f"+{ch['added']} -{ch['removed']}",
            end_section=i == len(rows) - 2,
        )
    console.print(table)
