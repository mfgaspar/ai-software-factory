"""Running workflows and reporting on runs: ``compose run``, ``status``, ``resume``,
``abort``, ``trace``, ``changes`` and ``cost``.

Exit codes of ``run`` and ``resume``: 0 completed (or detached), 1 failed or aborted,
3 paused at a gate.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import subprocess
import sys
import textwrap
import time
from collections import deque
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any

import typer
from rich.console import Console
from rich.live import Live
from rich.markup import escape
from rich.table import Table
from rich.text import Text
from rich.tree import Tree

from compose import notify
from compose.clarity.questions import Question
from compose.cli.common import console, err_console, handle_errors, open_store, print_json
from compose.core import procs, store
from compose.core.config import load_config
from compose.core.db import Database
from compose.core.home import Home
from compose.core.models import Feature, Repo, Run, RunStatus
from compose.engines.registry import EngineRegistry, default_registry
from compose.repos import git, registry
from compose.runner.recovery import recover_stale_runs
from compose.runner.runner import Interaction, Runner
from compose.runner.state import RunFiles
from compose.tracking import transcripts, views
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


def _interaction(
    interactive: bool,
    progress: Progress | None = None,
    *,
    notifications: bool = True,
    auto_approve: bool = False,
) -> Interaction:
    def announce(message: str, choice: str) -> None:
        if progress is None:  # --json and detached runs print nothing
            return
        line = f"[green]✓[/green] auto-approved: {_first_line(message)} → {choice}"
        progress.console.print(line, highlight=False)

    on_auto = announce if auto_approve else None
    if not interactive:
        return Interaction(auto_approve=auto_approve, on_auto_approve=on_auto)
    asked_at: list[str | None] = [None]  # the questions step last notified about

    def ask_with_notice(q: Question) -> str:
        step = progress.current_step if progress is not None else None
        if step is None or step != asked_at[0]:
            asked_at[0] = step
            notify.notify(f"waiting for your answers ({q.id})", configured=notifications)
        if progress is not None:
            progress.asked += 1
        return ask_question(q, progress.console if progress is not None else None)

    def paused(ask: Callable[..., Any]) -> Callable[..., Any]:
        def call(*args: Any) -> Any:
            if progress is not None:
                progress.pause()
            return ask(*args)

        return call

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
        auto_approve=auto_approve,
        on_auto_approve=on_auto,
        ask_input=paused(ask_input),
        ask_gate=paused(ask_gate),
        ask_confirm=paused(ask_confirm),
        ask_question=paused(ask_with_notice),
    )


_RECOMMENDED_MARK = re.compile(r"\s*\(recommended\)\s*$", re.IGNORECASE)


def _option_text(option: str) -> str:
    """An option as shown: without the "(recommended)" a skill may already have written
    into it, since the list marks the recommendation itself."""
    return _RECOMMENDED_MARK.sub("", option)


def _answer_hint(q: Question) -> str:
    own = q.free_text and q.kind != "approval"
    choices = "number or your own words" if own else "number"
    if q.recommended in q.options:
        default = str(q.options.index(q.recommended) + 1)
    elif q.recommended:
        default = "the recommendation"
    else:
        default = "later"
    return f"Answer ({choices}, Enter = {default})"


def _hanging(
    out: Console, marker: str, text: str, style: str = "", tail: Text | None = None
) -> None:
    """``marker text``, a long text wrapping under its own start, not under the marker."""
    indent = " " * (len(marker) + 1)
    width = max(out.width - len(indent), 20)
    lines = textwrap.wrap(text, width) or [""]
    body = Text(f"{marker} ")
    for i, line in enumerate(lines):
        body.append(("" if i == 0 else f"\n{indent}") + line, style=style)
    if tail is not None:
        body.append_text(tail)
    out.print(body, highlight=False, soft_wrap=True)


def ask_question(q: Question, out: Console | None = None) -> str:
    """Show a question: its headline, supporting details, numbered options and
    recommendation. Enter takes the recommendation (or leaves the question for later when
    there's none); free-text questions take the person's own words too."""
    out = out or console
    where = [q.kind, q.document] if q.document else [q.kind]
    out.print()
    out.print(Text.assemble(("? ", "yellow"), (q.id, "bold"), (f"  {' · '.join(where)}", "dim")))
    _hanging(out, " ", q.question, "bold")
    for detail in q.details:
        _hanging(out, "   •", detail, "dim")
    for number, option in enumerate(q.options, 1):
        mark = Text("  recommended", style="green") if option == q.recommended else None
        _hanging(out, f"  {number:>2}.", _option_text(option), tail=mark)
    if q.recommended and q.recommended not in q.options:
        _hanging(out, "    ", f"Recommended: {q.recommended}", "green")
    while True:
        text = str(typer.prompt(_answer_hint(q), default="", show_default=False)).strip()
        if not text:
            return q.recommended or ""
        if text.isdigit() and 1 <= int(text) <= len(q.options):
            return q.options[int(text) - 1]
        if q.free_text and q.kind != "approval" or text in q.options:
            return text
        out.print("[red]Choose one of the numbered options.[/red]")


# tools that write a file: Claude Code's, then Copilot's
WRITE_TOOLS = frozenset({"Write", "Edit", "MultiEdit", "NotebookEdit", "create", "edit"})
PATH_KEYS = ("file_path", "notebook_path", "path")
ENGINE_STEPS = frozenset({"command", "prompt"})
HINT_KEYS = (
    "file_path",
    "notebook_path",
    "path",
    "pattern",
    "command",
    "url",
    "query",
    "description",
)


def _first_line(text: str) -> str:
    return next((line.strip() for line in text.splitlines() if line.strip()), "")


def _clip_to(text: str, width: int) -> str:
    return text if len(text) <= width else text[: max(width - 1, 1)] + "…"


def short_money(value: float) -> str:
    """A cost as people read it while a run goes: ``$0.03``, ``<$0.01``."""
    return f"${value:.2f}" if value >= 0.01 else "<$0.01"


# Steps that only arrange other steps: their children are what a person follows.
CONTROL_STEPS = frozenset({"if", "switch", "while", "do-while", "fan-out", "workflow"})
LONG_STEPS = ENGINE_STEPS | {"shell"}
RECENT_LINES = 5  # how many of the latest actions the live area shows
SPINNER = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
_ROUND = re.compile(r"#(\d+)/[^/]*$")
LABEL_WIDTH = 34


def step_label(event: dict[str, Any]) -> str:
    """The step's ``name`` (its id when it has none), with the loop round it runs in:
    ``Apply your answers (round 2)``."""
    label = str(event.get("name") or event.get("step_id") or "")
    found = _ROUND.search(str(event.get("key") or ""))
    return f"{label} (round {found.group(1)})" if found else label


class _Step:
    def __init__(self, event: dict[str, Any], depth: int, shown: bool) -> None:
        self.label = step_label(event)
        self.kind = str(event.get("step_type") or "")
        self.depth = depth
        self.shown = shown
        self.started = time.monotonic()
        self.files: set[str] = set()
        self.asked = 0


ACTION_WORD = re.compile(r"^([A-Za-z][\w-]*)(:?)(?=\s|$)")


def _action_note(note: str) -> Text:
    """One line of what the agent is doing, with its action word highlighted: ``Writing``,
    ``Read``, ``Bash``, ``thinking:``, ``Subagent:``. A failure stays red, and a message
    keeps its plain italic."""
    if note.startswith("✗"):
        return Text(note, style="red")
    match = ACTION_WORD.match(note)
    if match is None or note.startswith("»"):
        return Text(note, style="dim italic")
    word = match.group(1).lower()
    action = Text(match.group(0), style="bold")
    return Text.assemble(action, (note[match.end():], "dim italic"))


class _StatusLine:
    """The transient line under a running step: a spinner, the step, its time, the turn,
    the files written and its cost, then the last few things the agent did, one per line:
    ``⠹ Draft the documents · 2m14s · turn 9 · 3 files · ~$0.12``. Claude reports the cost
    only when a step ends, so until then it's an estimate from the tokens at list price,
    marked ``~``."""

    def __init__(self, label: str = "", width: int = 80) -> None:
        self.step = label
        self.width = width
        self.started = time.monotonic()
        self.cost = 0.0
        self.estimate = 0.0
        self.files = 0
        self.turns = 0
        self.recent: deque[str] = deque(maxlen=RECENT_LINES)

    @property
    def note(self) -> str:
        return self.recent[-1] if self.recent else ""

    @note.setter
    def note(self, text: str) -> None:
        """Add what the agent just did; the live area keeps the last few."""
        if text and text != self.note:
            self.recent.append(text)

    def __rich__(self) -> Text:
        elapsed = time.monotonic() - self.started
        frame = SPINNER[int(elapsed * 8) % len(SPINNER)]
        parts = [duration(int(elapsed * 1000))]
        if self.turns:
            parts.append(f"turn {self.turns + 1}")
        if self.files:
            parts.append(f"{self.files} file{'' if self.files == 1 else 's'}")
        if self.cost:
            parts.append(short_money(self.cost))
        elif self.estimate:
            parts.append("~" + short_money(self.estimate))
        line = Text.assemble((frame, "cyan"), " ", self.step, (f" · {' · '.join(parts)}", "dim"))
        for note in self.recent:
            line.append("\n  ")
            line.append_text(_action_note(_clip_to(note, max(self.width - 4, 12))))
        return line


class Progress:
    """What a foreground run prints as it goes.

    By default, one line per step a person cares about, written when the step ends
    (``✓ Draft the documents   7 files · 1m12s · $0.03``); steps that only arrange others
    (``if``, ``do-while``…) and steps marked ``quiet`` stay out of it unless they fail. On a
    terminal a live line shows the running step and the model's latest commentary. With
    ``verbose``, every step, the files written, the commentary and every other tool call.
    """

    def __init__(self, verbose: bool, out: Console | None = None) -> None:
        self.verbose = verbose
        self.out = out
        self.steps: dict[str, _Step] = {}
        self.workdir: Path | None = None
        self.status = _StatusLine()
        self.live: Live | None = None
        self.calls: dict[str, str] = {}  # tool call id -> tool name, to name a failure
        self.current_step: str | None = None  # exec id of the step started last
        self._engine_shown: str | None = None
        self.asked = 0  # questions asked inline; the questions step's summary counts them

    @property
    def console(self) -> Console:
        return self.out or console

    # ------------------------------------------------------------------ status line

    def _start_status(self, step: _Step) -> None:
        if not self.console.is_terminal:
            return
        self.pause()
        self.status = _StatusLine(step.label, self.console.width)
        self.live = Live(self.status, console=self.console, transient=True, refresh_per_second=8)
        self.live.start()

    def pause(self) -> None:
        """Stop the live line (before a prompt, at a step's end, when the run ends)."""
        if self.live is not None:
            self.live.stop()
            self.live = None

    close = pause

    # ------------------------------------------------------------------ helpers

    def _print(self, text: str | Text) -> None:
        self.console.print(text, highlight=False)

    def _relative(self, path: str) -> str:
        if self.workdir is not None:
            try:
                return str(Path(path).resolve().relative_to(self.workdir))
            except (ValueError, OSError):
                pass
        return path

    def _pad(self, step: _Step | None, extra: int = 0) -> str:
        return "  " * ((step.depth if step and self.verbose else 0) + extra)

    def _summary(self, step: _Step, event: dict[str, Any]) -> str:
        parts: list[str] = []
        if step.kind == "questions" and step.asked:
            parts.append(f"{step.asked} answered")
        if step.files:
            parts.append(f"{len(step.files)} file{'' if len(step.files) == 1 else 's'}")
        elapsed = time.monotonic() - step.started
        if step.kind in LONG_STEPS or elapsed >= 1:
            parts.append(duration(int(elapsed * 1000)))
        if event.get("cost_usd"):
            parts.append(short_money(float(event["cost_usd"])))
        return " · ".join(parts)

    # ------------------------------------------------------------------ events

    def _engine_event(self, event: dict[str, Any]) -> None:
        inner = event.get("event") or {}
        step = self.steps.get(event.get("exec_id") or "")
        pad = self._pad(step, 1)
        kind = inner.get("kind")
        width = max(self.console.width - len(pad) - 2, 20)
        if kind == "tool_call":
            name = str(inner.get("name") or "")
            self.calls[str(inner.get("call_id") or "")] = name
            args = inner.get("input") or {}
            if name in WRITE_TOOLS:
                path = self._relative(next((str(args[k]) for k in PATH_KEYS if args.get(k)), ""))
                new = step is None or path not in step.files
                if step is not None:
                    step.files.add(path)
                    self.status.files = len(step.files)
                self.status.note = f"Writing {path}"
                if self.verbose and new:
                    self._print(f"{pad}[green]✎[/green] {escape(path)}")
            else:
                hint = next((str(args[k]) for k in HINT_KEYS if args.get(k)), "")
                if hint and any(k in args for k in PATH_KEYS):
                    hint = self._relative(hint)
                if name == "task":  # a subagent started
                    shown = _clip_to(f"Subagent: {_first_line(hint) or 'working'}", width)
                else:
                    shown = _clip_to(f"{name} {_first_line(hint)}".strip(), width)
                self.status.note = shown  # what the agent is doing now, never a stale line
                if self.verbose:
                    self._print(f"{pad}[dim]· {escape(shown)}[/dim]")
        elif kind == "message":
            line = _first_line(str(inner.get("text") or ""))
            if line and not line.startswith("|"):  # a table row says nothing on its own
                self.status.note = line.strip("*_` ")
                if self.verbose:
                    self._print(f"{pad}[dim]» {escape(_clip_to(line, width))}[/dim]")
        elif kind == "thinking":
            line = _first_line(str(inner.get("text") or "")).strip("*_` ")
            if line:
                self.status.note = f"thinking: {line}"
                if self.verbose:
                    self._print(f"{pad}[dim italic]~ {escape(_clip_to(line, width))}[/dim italic]")
        elif kind == "tool_result" and inner.get("is_error"):
            name = self.calls.get(str(inner.get("call_id") or ""), "tool")
            why = _clip_to(_first_line(str(inner.get("output") or "")) or "failed", width - 12)
            self.status.note = f"✗ {name}: {why}"
            if self.live is not None:  # print above the live line
                self.live.console.print(
                    f"{pad}[red]✗[/red] [dim]{escape(name)}: {escape(why)}[/dim]"
                )
            else:
                self._print(f"{pad}[red]✗[/red] [dim]{escape(name)}: {escape(why)}[/dim]")
        elif kind == "usage_update":
            usage = inner.get("usage") or {}
            self.status.turns = int(usage.get("turns") or 0)
            self.status.cost = float(usage.get("cost_usd") or 0)
            self.status.estimate = float(usage.get("estimated_cost_usd") or 0)

    def _step_started(self, event: dict[str, Any]) -> None:
        parent = self.steps.get(event.get("parent_exec_id") or "")
        depth = parent.depth + 1 if parent is not None else 0
        kind = str(event.get("step_type") or "")
        shown = self.verbose or not (kind in CONTROL_STEPS or event.get("quiet"))
        step = _Step(event, depth, shown)
        self.steps[str(event.get("exec_id") or "")] = step
        self.current_step = event.get("exec_id")
        if self.verbose:
            self._print(f"{self._pad(step)}[cyan]▸[/cyan] {escape(step.label)} [dim]{kind}[/dim]")
        elif shown and kind in LONG_STEPS and not self.console.is_terminal:
            self._print(f"[cyan]▸[/cyan] {escape(step.label)}")  # a log shows what's running
        if shown and kind not in CONTROL_STEPS | {"gate", "questions"}:
            self._start_status(step)
        self.asked = 0

    def _step_finished(self, event: dict[str, Any]) -> None:
        self.pause()
        step = self.steps.get(str(event.get("exec_id") or "")) or _Step(event, 0, True)
        if step.kind == "questions":
            step.asked = self.asked
        status = str(event.get("status"))
        failed = status in ("failed", "aborted")
        if not (step.shown or failed) or (status == "skipped" and not self.verbose):
            return
        asked_none = step.kind == "questions" and status == "completed" and not step.asked
        if asked_none and not self.verbose:
            return  # nothing was asked: nothing to report
        if step.asked:
            self._print("")  # after the questions, before the run goes on
        style = STATUS_STYLE.get(status, "")
        line = Text(self._pad(step))
        line.append(SYMBOL.get(status, "·"), style=style)
        line.append(f" {step.label}")
        summary = self._summary(step, event)
        if summary:
            line.append(" " * max(LABEL_WIDTH - len(step.label), 1) + summary, style="dim")
        if status not in ("completed", "paused") or self.verbose:
            line.append(f"  {status}", style=style)
        if event.get("error") and status != "paused":
            line.append(f"  {event['error']}", style="red")
        self._print(line)

    def _engine_started(self, event: dict[str, Any]) -> None:
        """Say which coding engine (and model) works, whenever it changes."""
        engine = event.get("engine")
        if not engine:
            return
        model = event.get("model")
        label = f"{engine} ({model})" if model else str(engine)
        if label == self._engine_shown:
            return
        self._engine_shown = label
        self._print(Text.assemble(("⚙ Engine: ", "dim"), (label, "bold")))

    def __call__(self, event: dict[str, Any]) -> None:
        kind = event.get("type")
        if kind == "run_started" and not event.get("parent_run_id"):
            if event.get("worktree") and self.workdir is None:
                self.workdir = Path(str(event["worktree"])).resolve()
            title = str(event.get("workflow") or "Run")
            target = event.get("feature")
            self._print(
                Text.assemble(
                    (title, "bold"),
                    (f" · {target}" if target else "", ""),
                    (f"  {event.get('run_id') or ''}", "dim"),
                )
            )
            self._print("")
        elif kind == "step_started":
            self._step_started(event)
        elif kind == "step_finished":
            self._step_finished(event)
        elif kind == "engine_event":
            self._engine_event(event)
        elif kind == "engine_started":
            self._engine_started(event)
        elif kind == "gate_waiting":
            self.pause()
            options = "/".join(event.get("options") or [])
            self._print(
                f"[yellow]⏸[/yellow] Waiting for your decision at {event.get('step_id')}:"
                f" {escape(str(event.get('message')))} [dim]({options})[/dim]"
            )
        elif kind in ("feature_commit_failed", "clarity_commit_failed"):
            self.pause()
            self._print(
                f"[yellow]warning:[/yellow] could not commit the work:"
                f" {escape(str(event.get('error')))}"
            )
        elif kind == "questions_waiting":
            self.pause()
            ids = event.get("ids") or []
            self._print(
                f"[yellow]⏸[/yellow] {len(ids)} question{'' if len(ids) == 1 else 's'}"
                f" waiting for your answers [dim]({', '.join(ids)})[/dim]"
            )


def _make_runner(
    db: Database,
    home: Home,
    *,
    interactive: bool,
    progress: Progress | None,
    auto_approve: bool = False,
) -> Runner:
    recover_stale_runs(db, home)
    config = load_config(home)
    return Runner(
        db,
        home,
        engines=engine_registry(),
        interaction=_interaction(
            interactive,
            progress,
            notifications=config.notifications.enabled,
            auto_approve=auto_approve,
        ),
        on_event=progress,
        config=config,
    )


def run_foreground(runner: Runner, run_id: str, progress: Progress | None) -> None:
    """Execute a run in this process, then clear the live status line."""
    try:
        asyncio.run(runner.execute(run_id))
    finally:
        if progress is not None:
            progress.close()


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
        _print_where(db, home, run_id)
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
    run_foreground(runner, created.id, progress)
    _finish(db, home, created.id, as_json, warnings=warnings, after=after)


def _shown_path(path: Path) -> str:
    """A path as short as it can be: relative to here, or from ``~``."""
    for base, prefix in ((Path.cwd(), ""), (Path.home(), "~/")):
        try:
            return prefix + str(path.resolve().relative_to(base.resolve())) or "."
        except ValueError:
            continue
    return str(path)


def _print_where(db: Database, home: Home, run_id: str) -> None:
    """Where a feature run left its work: merged into the default branch, or on its branch
    with the git commands to review and merge it."""
    run = views.get_run(db, run_id)
    if run.feature_id is None or run.parent_run_id is not None:
        return
    feature = store.get(db, Feature, run.feature_id)
    repo = store.get(db, Repo, run.repo_id)
    if feature is None or repo is None or not feature.worktree_path:
        return
    repo_dir, worktree = Path(repo.path), Path(feature.worktree_path)
    try:
        base = repo.default_branch or git.default_branch(repo_dir)
        ahead = int(git.git(repo_dir, "rev-list", "--count", f"{base}..{feature.branch}"))
        loose = git.changed_paths(worktree) if worktree.is_dir() else []
    except (git.GitError, ValueError):
        return
    events = {e.get("type"): e for e in RunFiles(home.run_dir(run_id)).read_events()}
    if "feature_merged" in events and not ahead and not loose:
        console.print(
            f"The work is merged into [bold]{base}[/bold], in {escape(_shown_path(repo_dir))}"
            f" (branch {feature.branch}).",
            highlight=False,
        )
        return
    if not ahead and not loose:
        console.print(f"No changes on branch [bold]{feature.branch}[/bold].", highlight=False)
        return
    state = f"{ahead} commit{'' if ahead == 1 else 's'} ahead of {base}"
    if loose:
        state += f", {len(loose)} uncommitted file{'' if len(loose) == 1 else 's'}"
    rows = [("Files", _shown_path(worktree))]
    if ahead:
        target = _shown_path(repo_dir)
        rows.append(("Review", f"git -C {target} diff {base}...{feature.branch}"))
        if run.status is RunStatus.COMPLETED:
            rows.append(("Merge", f"git -C {target} merge {feature.branch}"))
    console.print(
        f"The work is on branch [bold]{feature.branch}[/bold] ({state}).", highlight=False
    )
    for label, value in rows:
        console.print(f"  [dim]{label + ':':<8}[/dim] {escape(value)}", highlight=False)
    pending = events.get("feature_merge_pending")
    if pending and ahead:
        console.print(
            f"  Not merged into {base}: {escape(str(pending.get('reason')))}.", highlight=False
        )


def _print_outcome(detail: dict[str, Any]) -> None:
    status = detail["status"]
    totals = detail["totals"]
    changes = totals["changes"]
    parts = []
    started, ended = detail.get("started_at"), detail.get("ended_at")
    if isinstance(started, datetime) and isinstance(ended, datetime):
        parts.append(f"in {duration(int((ended - started).total_seconds() * 1000))}")
    parts.append(short_money(totals["cost_usd"]))
    if changes["files"]:
        files = f"{changes['files']} file{'' if changes['files'] == 1 else 's'} changed"
        parts.append(f"{files} (+{changes['added']} -{changes['removed']})")
    style = STATUS_STYLE.get(status, "")
    console.print()
    console.print(
        Text.assemble(
            (f"{SYMBOL.get(status, '·')} Run {status}", f"bold {style}"),
            f"  {' · '.join(parts)}",
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
        for detail in q.get("details") or []:
            console.print(f"      • {detail}", highlight=False, soft_wrap=True)
    console.print(
        'Answer with: compose clarity answer <ID> "<answer>" (an option or your own words)',
        highlight=False,
    )


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
        run_foreground(runner, run_.id, progress)
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
    full: bool = typer.Option(
        False,
        "--full",
        help="Everything the engine did, from each step's transcript file: the prompt,"
        " thinking, messages, whole tool inputs and results, refusals and the result.",
    ),
    as_json: bool = typer.Option(False, "--json", help=JSON_HELP),
) -> None:
    """Every action of each step (messages, tool calls, results), hooks nested. Each engine
    step's whole session is kept in runs/<run>/steps/<exec id>.transcript.jsonl."""
    with open_store() as (home, db):
        data = views.trace(db, home, run_id, step)
    _attach_transcripts(home, data, full)
    if as_json:
        print_json(data)
        return
    width = None if full else 100
    root = Tree(f"[bold]{data['run_id']}[/bold] {data['status']}")
    for hook in data["run_hooks"]:
        _hook_node(root, hook, width, full)
    for s in data["steps"]:
        label = Text.assemble((_step_name(s), "bold"), f" {s['type']} ", styled(s["status"]))
        if s["cost_usd"]:
            label.append(f" {money(s['cost_usd'])}", style="dim")
        node = root.add(label)
        before = [h for h in s["hooks"] if h["event"].startswith("before")]
        for hook in before:
            _hook_node(node, hook, width, full)
        _actions(node, s, width, full)
        for hook in s["hooks"]:
            if hook not in before:
                _hook_node(node, hook, width, full)
    console.print(root)


def _attach_transcripts(home: Home, data: dict[str, Any], full: bool) -> None:
    """Add each execution's transcript file (when it has one) and, with ``full``, what's
    in it, to the trace."""

    def attach(item: dict[str, Any], run: str, exec_id: str) -> None:
        file = transcripts.path(home, run, exec_id)
        item["transcript"] = str(file) if file.is_file() else None
        if full and item["transcript"]:
            item["transcript_entries"] = transcripts.entries(file)

    for s in data["steps"]:
        attach(s, s["run_id"], s["exec_id"])
        for hook in s["hooks"]:
            attach(hook, s["run_id"], hook["hook_exec_id"])
    for hook in data["run_hooks"]:
        attach(hook, data["run_id"], hook["hook_exec_id"])


def _actions(node: Tree, item: dict[str, Any], width: int | None, full: bool) -> None:
    if full and item.get("transcript_entries"):
        for entry in item["transcript_entries"]:
            shown = _entry_text(entry)
            if shown is not None:
                node.add(shown)
    else:
        for action in item["actions"]:
            node.add(_action_text(action, width))
    if item.get("transcript"):
        node.add(Text(f"transcript: {_shown_path(Path(item['transcript']))}", style="dim"))


def _block(text: object) -> str:
    return text if isinstance(text, str) else json.dumps(text, indent=2, default=str)


def _entry_text(entry: dict[str, Any]) -> Text | None:
    """One transcript entry, whole. Claude Code's hook bookkeeping is left to --json."""
    kind = entry["kind"]
    sub = "↳ " if entry.get("parent") else ""  # inside a subagent
    if kind == "task":
        tools = ", ".join(entry.get("allowed_tools") or []) or "none"
        return Text.assemble(
            ("task ", "magenta"),
            f"{entry.get('transport')} · permission {entry.get('permission_mode')}"
            f" · allowed {tools} · {entry.get('cwd')}\n",
            (_block(entry.get("prompt")), "bold"),
        )
    if kind == "session":
        parts = [f"session {entry.get('session_id')}"]
        if entry.get("model"):
            parts.append(str(entry["model"]))
        if entry.get("permission_mode"):
            parts.append(f"permission {entry['permission_mode']}")
        if entry.get("copilot_version"):
            parts.append(f"Copilot {entry['copilot_version']}")
        else:
            parts.append(f"Claude Code {entry.get('claude_code_version')}")
        return Text(" · ".join(parts), style="magenta")
    if kind == "thinking":
        return Text(f"{sub}thinking: {entry.get('text') or ''}", style="dim italic")
    if kind == "message":
        style = "" if entry.get("role") == "assistant" else "cyan"
        return Text(f"{sub}{entry.get('text') or ''}", style=style)
    if kind == "tool_call":
        return Text.assemble(
            (f"{sub}→ ", "cyan"),
            (str(entry.get("name")), "bold"),
            " ",
            (_block(entry.get("input")), "dim"),
        )
    if kind == "tool_result":
        style = "red" if entry.get("is_error") else "dim"
        return Text.assemble((f"{sub}← ", style), (_block(entry.get("output")), style))
    if kind == "result":
        line = Text.assemble(
            ("result ", "red" if entry.get("is_error") else "green"),
            f"{entry.get('subtype')} · {entry.get('turns')} turns",
            f" · {money(float(entry['cost_usd']))}" if entry.get("cost_usd") else "",
        )
        for denial in entry.get("permission_denials") or []:
            line.append(f"\nrefused: {_block(denial)}", style="yellow")
        for error in entry.get("errors") or []:
            line.append(f"\nerror: {_block(error)}", style="red")
        return line
    if kind in ("stderr", "raw", "error"):
        return Text(f"{kind}: {entry.get('text')}", style="red")
    return None  # system bookkeeping (hooks, status); kept in the file and in --json


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


def _hook_node(parent: Tree, hook: dict[str, Any], width: int | None, full: bool) -> None:
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
    _actions(node, hook, width, full)


@handle_errors
def changes(
    run_id: str = typer.Argument(..., help="Run id."),
    step: str | None = typer.Option(None, "--step", help="Only this step id."),
    as_json: bool = typer.Option(False, "--json", help=JSON_HELP),
) -> None:
    """Files and lines each step changed."""
    with open_store() as (home, db):
        data = views.changes(db, home, run_id, step)
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
        "",
        "--by",
        help="Group by step, run, feature, repo, day or user (default: run, or step).",
    ),
    since: str | None = typer.Option(None, "--since", help="From this date/time (UTC)."),
    until: str | None = typer.Option(None, "--until", help="Before this date/time (UTC)."),
    every_repo: bool = typer.Option(False, "--all", help="All repos, wherever you are."),
    as_json: bool = typer.Option(False, "--json", help=JSON_HELP),
) -> None:
    """Cost, tokens and changes, grouped and filtered."""
    group = by or ("step" if run_id else "run")
    if group not in ("step", "run", "feature", "repo", "day", "user"):
        raise typer.BadParameter("use step, run, feature, repo, day or user", param_hint="--by")
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
