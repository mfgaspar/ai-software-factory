"""Running workflows: creating runs, executing steps, pausing, resuming and aborting."""

from __future__ import annotations

import asyncio
import getpass
import json
import os
import sys
from collections.abc import Awaitable, Callable
from contextlib import suppress
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from compose import notify, telemetry
from compose.clarity import branch as clarity_branch
from compose.clarity import preflight
from compose.clarity.questions import Question
from compose.core import locks, store
from compose.core.config import Config, load_config
from compose.core.db import Database, utcnow
from compose.core.home import Home
from compose.core.ids import new_id
from compose.core.models import (
    ExecStatus,
    Feature,
    Repo,
    Run,
    RunStatus,
    StepExec,
)
from compose.engines.base import (
    EngineEvent,
    MessageEvent,
    ToolCallEvent,
    ToolResultEvent,
    Usage,
    UsageEvent,
)
from compose.engines.registry import EngineError, EngineRegistry, default_registry
from compose.repos import features, git
from compose.repos.git import GitError
from compose.repos.worktrees import commit_all, ensure_feature_worktree, merge_into_default
from compose.runner import hooks
from compose.runner.context import Scope, step_result
from compose.runner.errors import (
    InputError,
    LimitExceeded,
    RunAborted,
    RunError,
    RunHookFailed,
    RunPaused,
    StepFailed,
)
from compose.runner.state import CompletedStep, RunFiles, RunState, check_transition
from compose.runner.steps import clarity, control, engine, gate, questions, shell, subworkflow
from compose.runner.steps.base import Outcome
from compose.tracking import journal, records
from compose.tracking.aggregate import LEAF
from compose.workflows import expressions, loader
from compose.workflows.schema import (
    BaseStep,
    EngineSettings,
    InputSpec,
    InputType,
    Limits,
    Workflow,
    coerce_input,
)

SUMMARY_LIMIT = 500
ABORT_POLL_SECONDS = 0.25
EventSink = Callable[[dict[str, Any]], None]

LeafExecutor = Callable[["RunContext", Any, StepExec, Scope], Awaitable[Outcome]]

LEAF_EXECUTORS: dict[str, LeafExecutor] = {
    "command": engine.execute,
    "prompt": engine.execute,
    "shell": shell.execute,
    "gate": gate.execute,
    "questions": questions.execute,
    "clarity": clarity.execute,
}
CONTROL_EXECUTORS: dict[str, LeafExecutor] = {
    "if": control.execute_if,
    "switch": control.execute_switch,
    "while": control.execute_loop,
    "do-while": control.execute_loop,
    "fan-out": control.execute_fan_out,
    "fan-in": control.execute_fan_in,
    "workflow": subworkflow.execute,
}


def _starter(path: Path) -> str:
    """Who starts a run on this machine: the git user name, else the OS user."""
    try:
        name = git.user_name(path)
    except OSError:
        name = None
    return name or getpass.getuser()


@dataclass
class Interaction:
    """How a run talks to a person, when one is present."""

    interactive: bool = False
    auto_approve: bool = False  # gates take "approve" and confirmations say yes
    on_auto_approve: Callable[[str, str], None] | None = None  # (gate message, choice taken)
    ask_input: Callable[[str, InputSpec], str] | None = None
    ask_gate: Callable[[str, list[str]], str] | None = None
    ask_confirm: Callable[[str], bool] | None = None
    ask_question: Callable[[Question], str] | None = None


@dataclass
class EngineChoice:
    engine: str
    model: str | None
    reasoning_effort: str | None
    engine_options: dict[str, Any]


@dataclass
class Shared:
    """State shared by a root run and its child runs."""

    root_run_id: str
    run_limits: Limits
    abort_event: asyncio.Event = field(default_factory=asyncio.Event)
    spent_usd: float = 0.0
    call_stack: list[str] = field(default_factory=list)


def _summary(value: Any) -> str:
    text = value if isinstance(value, str) else json.dumps(value, default=str)
    return text if len(text) <= SUMMARY_LIMIT else text[:SUMMARY_LIMIT] + "…"


class RunContext:
    """Everything one run (root or child) needs while it executes."""

    def __init__(
        self,
        runner: Runner,
        run: Run,
        definition: Workflow,
        files: RunFiles,
        state: RunState,
        repo: Repo,
        feature: Feature | None,
        worktree: Path,
        shared: Shared,
    ) -> None:
        self.runner = runner
        self.run = run
        self.definition = definition
        self.files = files
        self.state = state
        self.repo = repo
        self.feature = feature
        self.worktree = worktree
        self.shared = shared
        self.results: dict[str, dict[str, Any]] = {}
        self.fan_results: dict[str, list[Any]] = {}
        self._seq = files.action_count()

    # ------------------------------------------------------------------ helpers

    @property
    def db(self) -> Database:
        return self.runner.db

    @property
    def workflow_dir(self) -> str:
        return self.state.workflow_dir or str(self.files.dir)

    @property
    def scope(self) -> str:
        """``feature``, or ``repo`` for a run with no feature (e.g. clarity)."""
        return "feature" if self.feature is not None else "repo"

    def env(self) -> dict[str, str]:
        env = {
            "COMPOSE_RUN_ID": self.run.id,
            "COMPOSE_REPO": self.repo.name,
            "COMPOSE_SCOPE": self.scope,
            "COMPOSE_WORKFLOW_DIR": self.workflow_dir,
        }
        if self.feature is not None:
            env["COMPOSE_FEATURE"] = self.feature.name
        # skills call the compose CLI: make sure the one running this run is found first
        bin_dir = Path(sys.executable).parent
        if (bin_dir / "compose").exists():
            env["PATH"] = f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}"
        return env

    def expression_context(self, scope: Scope) -> dict[str, Any]:
        constitution = self.worktree / ".compose" / "memory" / "constitution.md"
        return {
            "inputs": self.run.inputs,
            "steps": self.results,
            "context": {
                "run_id": self.run.id,
                "workflow_dir": self.workflow_dir,
                "worktree": str(self.worktree),
                "repo": {"id": self.repo.id, "name": self.repo.name, "dir": str(self.worktree)},
                "feature": self._feature_context(),
                "constitution_exists": constitution.exists(),
                "engine": self.definition.workflow.engine or self.runner.config.defaults.engine,
            },
            **scope.extras,
        }

    def _feature_context(self) -> dict[str, Any] | None:
        if self.feature is None:
            return None
        return {
            "id": self.feature.id,
            "name": self.feature.name,
            "branch": self.feature.branch,
            "dir": f"{features.SPECS_DIR}/{self.feature.name}",
        }

    def render(self, text: str, scope: Scope) -> Any:
        return expressions.render(text, self.expression_context(scope))

    def render_text(self, text: str, scope: Scope) -> str:
        return expressions.to_text(self.render(text, scope))

    def condition(self, text: str, scope: Scope) -> bool:
        return expressions.evaluate_condition(text, self.expression_context(scope))

    def engine_settings(self, step: EngineSettings, scope: Scope | None = None) -> EngineChoice:
        meta = self.definition.workflow
        config = self.runner.config
        defaults = config.defaults
        engine = step.engine or meta.engine or defaults.engine
        options = {**config.engines.get(engine, {}), **meta.engine_options, **step.engine_options}
        scope = scope or Scope()
        return EngineChoice(
            engine=engine,
            model=self._render_setting(step.model, scope)
            or self._render_setting(meta.model, scope)
            or defaults.model,
            reasoning_effort=self._render_setting(step.reasoning_effort, scope)
            or self._render_setting(meta.reasoning_effort, scope),
            engine_options={k: self._render_option(v, scope) for k, v in options.items()},
        )

    def _render_setting(self, value: str | None, scope: Scope) -> str | None:
        """A model or reasoning effort; one that renders empty falls back to the next level."""
        if value is None or "{{" not in value:
            return value
        return self.render_text(value, scope).strip() or None

    def _render_option(self, value: Any, scope: Scope) -> Any:
        """Expressions in engine_options; a list item that renders to a list is spliced in."""
        if isinstance(value, str):
            return self.render(value, scope) if "{{" in value else value
        if isinstance(value, list):
            out: list[Any] = []
            for item in value:
                rendered = self._render_option(item, scope)
                if isinstance(item, str) and isinstance(rendered, list):
                    out.extend(rendered)
                else:
                    out.append(rendered)
            return out
        if isinstance(value, dict):
            return {k: self._render_option(v, scope) for k, v in value.items()}
        return value

    def check_limits(self, limits: Limits, usage: Usage) -> None:
        if limits.max_cost_usd is not None and usage.cost_usd > limits.max_cost_usd:
            raise LimitExceeded(
                f"step cost ${usage.cost_usd:.4f} exceeds max_cost_usd ${limits.max_cost_usd}"
            )
        if limits.max_turns is not None and usage.turns > limits.max_turns:
            raise LimitExceeded(f"{usage.turns} turns exceeds max_turns {limits.max_turns}")
        run_cap = self.shared.run_limits.max_cost_usd
        if run_cap is not None and self.shared.spent_usd + usage.cost_usd > run_cap:
            total = self.shared.spent_usd + usage.cost_usd
            raise LimitExceeded(f"run cost ${total:.4f} exceeds max_cost_usd ${run_cap}")

    def clear_input(self, name: str | None) -> None:
        if name and self.run.inputs.get(name) not in (None, ""):
            self.run.inputs = {**self.run.inputs, name: ""}
            store.update(self.db, self.run)
            self.files.write_inputs(self.run.inputs)

    def save_state(self) -> None:
        self.files.write_state(self.state)

    def emit(self, type_: str, **data: Any) -> None:
        event = {"type": type_, "run_id": self.run.id, **data}
        self.files.append_event(event)
        if self.runner.on_event is not None:
            self.runner.on_event(event)
        if self.runner.telemetry is not None:
            self.runner.telemetry.handle(event)

    # ---------------------------------------------------------------- recording

    def record_action(
        self,
        step_exec_id: str | None,
        hook_exec_id: str | None,
        *,
        kind: str,
        tool_name: str | None = None,
        input_summary: str | None = None,
        result_summary: str | None = None,
        is_error: bool = False,
        duration_ms: int | None = None,
    ) -> int:
        self._seq += 1
        journal.append_action(
            self.files,
            journal.Action(
                run_id=self.run.id,
                step_exec_id=step_exec_id,
                hook_exec_id=hook_exec_id,
                seq=self._seq,
                kind=kind,
                tool_name=tool_name,
                input_summary=input_summary,
                result_summary=result_summary,
                is_error=is_error,
                duration_ms=duration_ms,
            ),
        )
        return self._seq

    def record_engine_event(
        self, step_exec_id: str | None, hook_exec_id: str | None, event: EngineEvent
    ) -> None:
        self.emit(
            "engine_event",
            exec_id=step_exec_id,
            hook_exec_id=hook_exec_id,
            event=asdict(event),
        )
        if isinstance(event, MessageEvent):
            self.record_action(
                step_exec_id, hook_exec_id, kind="message", input_summary=_summary(event.text)
            )
        elif isinstance(event, ToolCallEvent):
            self.record_action(
                step_exec_id,
                hook_exec_id,
                kind="tool_call",
                tool_name=event.name,
                input_summary=_summary(event.input),
            )
        elif isinstance(event, ToolResultEvent):
            self.record_action(
                step_exec_id,
                hook_exec_id,
                kind="tool_result",
                result_summary=_summary(event.output),
                is_error=event.is_error,
                duration_ms=event.duration_ms,
            )
        elif isinstance(event, UsageEvent):
            pass  # kept in the event log; totals go on the execution row

    # ---------------------------------------------------------------- execution

    async def guard(self, coro: Awaitable[Outcome], timeout: float | None) -> Outcome:
        """Run ``coro``, cancelling it on abort (RunAborted) or timeout (TimeoutError)."""
        task = asyncio.ensure_future(coro)
        abort = asyncio.ensure_future(self.shared.abort_event.wait())
        try:
            done, _ = await asyncio.wait(
                {task, abort}, timeout=timeout, return_when=asyncio.FIRST_COMPLETED
            )
            if task in done:
                return task.result()
            task.cancel()
            with suppress(asyncio.CancelledError, Exception):
                await task
            if abort in done:
                raise RunAborted("aborted by request")
            raise TimeoutError
        finally:
            abort.cancel()

    async def run_steps(self, steps: list[Any], scope: Scope) -> None:
        for step in steps:
            await self.run_step(step, scope)

    async def run_step(self, step: BaseStep, scope: Scope) -> dict[str, Any]:
        """Execute one step (or replay it on resume); return what ``steps.<id>`` is."""
        if self.shared.abort_event.is_set():
            raise RunAborted("aborted by request")
        key = scope.key(step.id)
        done = self.state.completed.get(key)
        if done is not None:
            self.results[step.id] = done.result
            if step.kind == "fan-out":
                self.fan_results[step.id] = list(done.result["output"].get("results", []))
            return done.result
        kind = step.kind
        if kind in LEAF_EXECUTORS:
            return await self._execute(step, scope, LEAF_EXECUTORS[kind], leaf=True)
        return await self._execute(step, scope, CONTROL_EXECUTORS[kind], leaf=False)

    def _open_exec(self, step: BaseStep, scope: Scope, key: str) -> StepExec:
        existing_id = self.state.execs.get(key)
        if existing_id is not None:
            row = store.get(self.db, StepExec, existing_id)
            if row is not None and row.status in (ExecStatus.PAUSED, ExecStatus.RUNNING):
                row.status = ExecStatus.RUNNING
                row.error = None
                store.update(self.db, row)
                return row
        attempt = self.state.attempts.get(key, 0) + 1
        row = StepExec(
            id=new_id("exec"),
            run_id=self.run.id,
            step_id=step.id,
            step_type=step.kind,
            parent_exec_id=scope.parent_exec_id,
            iteration=scope.iteration,
            attempt=attempt,
            status=ExecStatus.RUNNING,
            started_at=utcnow(),
        )
        store.insert(self.db, row)
        self.state.execs[key] = row.id
        self.state.attempts[key] = attempt
        return row

    async def _execute(
        self, step: BaseStep, scope: Scope, executor: LeafExecutor, *, leaf: bool
    ) -> dict[str, Any]:
        key = scope.key(step.id)
        row = self._open_exec(step, scope, key)
        self.state.current_step_id = step.id
        self.run.current_step_id = step.id
        store.update(self.db, self.run)
        self.save_state()
        self.emit(
            "step_started",
            exec_id=row.id,
            step_id=step.id,
            key=key,
            step_type=row.step_type,
            parent_exec_id=scope.parent_exec_id,
            name=step.name,
            quiet=step.quiet,
        )

        plan = (
            hooks.step_hooks(self.definition, step.id, workflow_hooks=leaf)
            if leaf or step.kind == "fan-out"
            else None
        )
        try:
            if plan:
                outcome = await self._with_hooks(step, scope, row, plan, executor, leaf=leaf)
            else:
                outcome = await self._body(step, scope, row, executor, leaf=leaf)
        except RunPaused as paused:
            self._close(row, ExecStatus.PAUSED, error=paused.reason, leaf=leaf)
            # the innermost step (the gate itself) is where a resume choice belongs,
            # not the if / loop around it
            if self.state.paused_at is None:
                self.state.paused_at = key
            self.save_state()
            raise
        except RunAborted as aborted:
            self._close(row, ExecStatus.ABORTED, error=aborted.reason, leaf=leaf)
            raise
        except StepFailed as failed:
            self._close(row, ExecStatus.FAILED, error=str(failed), leaf=leaf)
            self._forget(key)
            raise
        except Exception as exc:  # unexpected: always stops the run
            self._close(row, ExecStatus.FAILED, error=f"internal error: {exc!r}", leaf=leaf)
            self._forget(key)
            raise StepFailed(step.id, f"internal error: {exc!r}") from exc

        self._close(row, outcome.status, error=outcome.error, output=outcome.output, leaf=leaf)
        result = step_result(outcome.status, outcome.output, row)
        self.results[step.id] = result
        is_failure = outcome.status is ExecStatus.FAILED
        if not is_failure or step.continue_on_error:
            self.state.completed[key] = CompletedStep(row.id, step.id, row.status.value, result)
            self.state.execs.pop(key, None)
        else:
            self._forget(key)
        self.save_state()
        if outcome.abort_run:
            raise RunAborted(outcome.abort_run)
        if is_failure and not step.continue_on_error:
            raise StepFailed(step.id, outcome.error or "failed")
        return result

    async def _body(
        self, step: BaseStep, scope: Scope, row: StepExec, executor: LeafExecutor, *, leaf: bool
    ) -> Outcome:
        """Run the step itself; expected problems become a failed outcome."""
        try:
            if leaf:
                return await self.guard(executor(self, step, row, scope), step.timeout)
            return await executor(self, step, row, scope)
        except EngineError as exc:
            return Outcome.failed(str(exc))
        except LimitExceeded as exc:
            return Outcome.failed(str(exc))
        except TimeoutError:
            return Outcome.failed(f"timeout after {step.timeout}s")
        except expressions.ExpressionError as exc:
            return Outcome.failed(f"expression error: {exc}")

    async def _with_hooks(
        self,
        step: BaseStep,
        scope: Scope,
        row: StepExec,
        plan: hooks.StepHooks,
        executor: LeafExecutor,
        *,
        leaf: bool,
    ) -> Outcome:
        """before hooks, the step, after hooks (on success), then the final hooks."""
        # A gate resumed after a pause keeps its row; hooks that already ran are not repeated.
        done = hooks.completed_keys(self.db, self.run.id, row.id)
        error = await hooks.run_group(self, plan.before, row, scope, skip=done)
        if error is not None:
            outcome = Outcome.failed(error)
        else:
            try:
                outcome = await self._body(step, scope, row, executor, leaf=leaf)
            except StepFailed:
                await hooks.run_group(self, plan.final, row, scope, skip=done)
                raise
            # after hooks can read the step's own result as steps.<id>
            self.results[step.id] = step_result(outcome.status, outcome.output, row)
            if outcome.status is ExecStatus.COMPLETED:
                error = await hooks.run_group(self, plan.after, row, scope, skip=done)
                if error is not None:
                    outcome = Outcome(ExecStatus.FAILED, outcome.output, error, outcome.abort_run)
        error = await hooks.run_group(self, plan.final, row, scope, skip=done)
        if error is not None and outcome.status is not ExecStatus.FAILED:
            outcome = Outcome(ExecStatus.FAILED, outcome.output, error, outcome.abort_run)
        return outcome

    def _forget(self, key: str) -> None:
        """A failed execution: the next resume starts a new attempt."""
        self.state.execs.pop(key, None)

    def _close(
        self,
        row: StepExec,
        status: ExecStatus,
        *,
        error: str | None,
        output: dict[str, Any] | None = None,
        leaf: bool,
    ) -> None:
        row.status = status
        row.error = error
        if output is not None:
            row.output = output
        if status is not ExecStatus.PAUSED:
            row.ended_at = utcnow()
            if row.started_at is not None:
                row.duration_ms = int((row.ended_at - row.started_at).total_seconds() * 1000)
        if leaf:
            self.shared.spent_usd += row.cost_usd  # hooks were counted as they finished
        elif status is not ExecStatus.PAUSED:
            self._roll_up(row)
        if status is not ExecStatus.PAUSED:
            # Kept apart while paused so a resumed gate doesn't count its hooks twice.
            hooks.fold_hook_metrics(self.db, row)
        store.update(self.db, row)
        self.files.write_step_record(row.id, records.step_record(self.db, self.files, row))
        self.emit(
            "step_finished",
            exec_id=row.id,
            step_id=row.step_id,
            status=status.value,
            error=error,
            cost_usd=row.cost_usd,
        )

    def _roll_up(self, row: StepExec) -> None:
        """Totals of a control step = sum of the executions beneath it.

        Usage comes from leaf steps; file changes from leaf steps and fan-outs (whose
        items share the worktree and are tracked as a whole). A fan-out keeps the
        changes its own tracking recorded.
        """
        own_changes = (row.files_changed, row.lines_added, row.lines_removed)
        totals = self.db.execute(
            f"""
            WITH RECURSIVE tree(id) AS (
                SELECT id FROM step_execs WHERE parent_exec_id = ?
                UNION ALL
                SELECT s.id FROM step_execs s JOIN tree t ON s.parent_exec_id = t.id
            )
            SELECT COALESCE(SUM(input_tokens), 0), COALESCE(SUM(output_tokens), 0),
                   COALESCE(SUM(cache_read_tokens), 0), COALESCE(SUM(cache_write_tokens), 0),
                   COALESCE(SUM(cost_usd), 0)
            FROM step_execs WHERE id IN (SELECT id FROM tree)
              AND step_type IN {LEAF}
            """,
            (row.id,),
        ).fetchone()
        (
            row.input_tokens,
            row.output_tokens,
            row.cache_read_tokens,
            row.cache_write_tokens,
            row.cost_usd,
        ) = totals
        if row.step_type == "fan-out":
            row.files_changed, row.lines_added, row.lines_removed = own_changes
            return
        changes = self.db.execute(
            f"""
            WITH RECURSIVE tree(id) AS (
                SELECT id FROM step_execs WHERE parent_exec_id = ?
                UNION ALL
                SELECT s.id FROM step_execs s JOIN tree t ON s.parent_exec_id = t.id
            )
            SELECT COALESCE(SUM(files_changed), 0), COALESCE(SUM(lines_added), 0),
                   COALESCE(SUM(lines_removed), 0)
            FROM step_execs WHERE id IN (SELECT id FROM tree)
              AND (step_type IN {LEAF} OR step_type = 'fan-out')
            """,
            (row.id,),
        ).fetchone()
        row.files_changed, row.lines_added, row.lines_removed = changes


# ============================================================================ runner


class Runner:
    """Creates and executes runs. One instance can drive many runs."""

    def __init__(
        self,
        db: Database,
        home: Home,
        *,
        engines: EngineRegistry | None = None,
        config: Config | None = None,
        interaction: Interaction | None = None,
        on_event: EventSink | None = None,
    ) -> None:
        self.db = db
        self.home = home
        self.engines = engines or default_registry()
        self.config = config or load_config(home)
        self.interaction = interaction or Interaction()
        self.on_event = on_event
        self.telemetry = telemetry.create(db, self.config)
        self.last_warnings: list[str] = []  # the pre-run check's, from the last create_run

    # ---------------------------------------------------------------- creating

    def resolve_inputs(
        self, definition: Workflow, raw: dict[str, Any], *, ask_missing: bool
    ) -> dict[str, Any]:
        unknown = sorted(set(raw) - set(definition.inputs))
        if unknown:
            raise InputError(f"Unknown input(s): {', '.join(unknown)}")
        resolved: dict[str, Any] = {}
        for name, spec in definition.inputs.items():
            if name in raw and raw[name] is not None:
                value: Any = raw[name]
            elif spec.default is not None:
                value = spec.default
            elif spec.required:
                ask = self.interaction.ask_input
                if not (ask_missing and self.interaction.interactive and ask):
                    raise InputError(f"Missing required input {name!r}")
                value = ask(name, spec)
            else:
                continue
            try:
                resolved[name] = coerce_input(spec, value)
            except ValueError as exc:
                raise InputError(f"Input {name!r}: {exc}") from exc
        return resolved

    def _feature_for(
        self, repo: Repo, definition: Workflow, inputs: dict[str, Any], feature_name: str | None
    ) -> Feature:
        if feature_name:
            if features.parse_name(feature_name) is None:
                raise RunError(f"{feature_name!r} is not a feature name (NNN-short-name)")
            return features.upsert_feature(self.db, repo, feature_name)
        short = inputs.get("feature_name") if "feature_name" in definition.inputs else None
        text = next(
            (
                str(inputs[name])
                for name, spec in definition.inputs.items()
                if spec.required and spec.type is InputType.STRING and inputs.get(name)
            ),
            definition.workflow.name,
        )
        name = features.allocate_name(Path(repo.path), text, short_name=short or None)
        return features.upsert_feature(self.db, repo, name)

    def create_run(
        self,
        repo: Repo,
        workflow: loader.LoadedWorkflow | str | None,
        inputs: dict[str, Any] | None = None,
        *,
        feature: str | None = None,
    ) -> Run:
        """Validate inputs, pick the feature and write the run (status ``created``).

        No workflow means the configured default (``defaults.workflow``). A feature run
        passes the pre-run check first (:mod:`compose.clarity.preflight`): problems raise
        :class:`~compose.clarity.preflight.PreflightError` before anything is written;
        warnings go on the ``run_created`` event and in :attr:`last_warnings`.
        """
        self.last_warnings = []
        workflow = workflow or self.config.defaults.workflow
        loaded = (
            loader.resolve(workflow, Path(repo.path)) if isinstance(workflow, str) else workflow
        )
        definition = loaded.definition
        resolved = self.resolve_inputs(definition, inputs or {}, ask_missing=True)
        repo_scope = definition.workflow.scope == "repo"
        if repo_scope:
            if feature:
                raise RunError(f"{definition.id} is a repo-scoped workflow; it takes no feature")
            self._check_no_repo_run(repo)
            feat = None
            warnings: list[str] = []
        else:
            checked = preflight.check(repo, clarity_branch=self.config.clarity.branch)
            if checked.problems:
                raise preflight.PreflightError(checked.problems)
            warnings = checked.warnings
            feat = self._feature_for(repo, definition, resolved, feature)
            held = locks.read_lock(self.db, locks.feature_lock_key(feat.id))
            if held is not None and not locks.is_stale(held):
                raise RunError(f"Feature {feat.name} already has an active run ({held.run_id})")
        run = Run(
            id=new_id("run"),
            repo_id=repo.id,
            feature_id=feat.id if feat else None,
            workflow_id=definition.id,
            workflow_version=definition.workflow.version,
            inputs=resolved,
            started_by=_starter(Path(repo.path)),
        )
        files = RunFiles(self.home.run_dir(run.id))
        files.create(loaded.path.read_text(), resolved)
        state = RunState(workflow_dir=str(loaded.directory), workflow_source=loaded.source)
        files.write_state(state)
        store.insert(self.db, run)
        if feat is None:
            files.append_event(
                {"type": "run_created", "run_id": run.id, "feature": None, "scope": "repo"}
            )
        else:
            files.append_event(
                {
                    "type": "run_created",
                    "run_id": run.id,
                    "feature": feat.name,
                    "warnings": warnings,
                }
            )
        self.last_warnings = warnings
        return run

    def _check_no_repo_run(self, repo: Repo) -> None:
        """One active repo-scoped run per repo, paused ones included."""
        row = self.db.execute(
            "SELECT id, status FROM runs WHERE repo_id = ? AND feature_id IS NULL"
            " AND parent_run_id IS NULL AND status IN (?, ?) ORDER BY created_at LIMIT 1",
            (repo.id, RunStatus.RUNNING.value, RunStatus.PAUSED.value),
        ).fetchone()
        held = locks.read_lock(self.db, locks.repo_lock_key(repo.id))
        active = row[0] if row is not None else None
        if active is None and held is not None and not locks.is_stale(held):
            active = held.run_id
        if active is not None:
            raise RunError(
                f"Repo {repo.name} already has an active clarity run ({active}); answer it,"
                f" or compose abort {active}"
            )

    def create_child_run(
        self,
        parent: RunContext,
        loaded: loader.LoadedWorkflow,
        inputs: dict[str, Any],
        *,
        parent_exec_id: str,
    ) -> Run:
        resolved = self.resolve_inputs(loaded.definition, inputs, ask_missing=False)
        run = Run(
            id=new_id("run"),
            repo_id=parent.repo.id,
            feature_id=parent.feature.id if parent.feature else None,
            workflow_id=loaded.id,
            workflow_version=loaded.definition.workflow.version,
            inputs=resolved,
            parent_run_id=parent.run.id,
            parent_exec_id=parent_exec_id,
        )
        files = RunFiles(self.home.run_dir(run.id))
        files.create(loaded.path.read_text(), resolved)
        files.write_state(
            RunState(workflow_dir=str(loaded.directory), workflow_source=loaded.source)
        )
        store.insert(self.db, run)
        return run

    # --------------------------------------------------------------- executing

    def _load(self, run_id: str) -> tuple[Run, RunFiles, RunState, Workflow]:
        run = store.get(self.db, Run, run_id)
        if run is None:
            raise RunError(f"No run {run_id!r}")
        files = RunFiles(self.home.run_dir(run.id))
        state = files.read_state()
        definition = loader.parse_workflow(files.definition.read_text(), str(files.definition))
        return run, files, state, definition

    def _set_status(self, run: Run, state: RunState, files: RunFiles, status: RunStatus) -> None:
        check_transition(run.status, status)
        run.status = status
        state.status = status.value
        if status is RunStatus.RUNNING and run.started_at is None:
            run.started_at = utcnow()
        if status in (RunStatus.COMPLETED, RunStatus.FAILED, RunStatus.ABORTED, RunStatus.PAUSED):
            run.ended_at = utcnow()
        store.update(self.db, run)
        files.write_state(state)

    def engines_used(self, definition: Workflow) -> list[str]:
        """Engines a workflow's engine steps and hooks run on (called workflows use the
        default engine unless they say otherwise)."""
        meta = definition.workflow
        default = meta.engine or self.config.defaults.engine
        names = {default}
        for _, step, _ in definition.iter_steps():
            if step.kind in ("command", "prompt"):
                names.add(getattr(step, "engine", None) or default)
        for hooks_list in definition.hooks.values():
            for hook in hooks_list:
                if hook.kind != "run":
                    names.add(hook.engine or default)
        return sorted(names)

    def _install_engines(self, definition: Workflow, worktree: Path) -> None:
        """Make each engine's skills available in the run worktree, hidden from git."""
        for name in self.engines_used(definition):
            try:
                engine = self.engines.get(name)
            except EngineError:
                continue  # reported by the step that needs it
            try:
                engine.install(worktree, worktree=True)
            except GitError as exc:
                raise RunError(f"Could not install {name} files in {worktree}: {exc}") from exc

    def _spent(self, root_run_id: str) -> float:
        row = self.db.execute(
            f"""
            WITH RECURSIVE tree(id) AS (
                SELECT id FROM runs WHERE id = ?
                UNION ALL SELECT r.id FROM runs r JOIN tree t ON r.parent_run_id = t.id
            )
            SELECT
              (SELECT COALESCE(SUM(cost_usd), 0) FROM step_execs
               WHERE run_id IN (SELECT id FROM tree)
                 AND step_type IN {LEAF}),
              (SELECT COALESCE(SUM(h.cost_usd), 0)
               FROM hook_execs h LEFT JOIN step_execs s ON s.id = h.step_exec_id
               WHERE h.run_id IN (SELECT id FROM tree)
                 AND (s.id IS NULL OR s.status IN ('paused', 'running')
                      OR s.step_type NOT IN {LEAF}))
            """,
            (root_run_id,),
        ).fetchone()
        # Leaf rows already include their hooks once closed; count the rest separately.
        return float(row[0]) + float(row[1])

    async def execute(self, run_id: str) -> Run:
        """Execute (or continue) a root run until it completes, pauses, fails or aborts."""
        run, files, state, definition = self._load(run_id)
        if run.parent_run_id is not None:
            raise RunError(f"{run_id} is a child run; resume its parent {run.parent_run_id}")
        if run.status not in (RunStatus.CREATED, RunStatus.PAUSED, RunStatus.FAILED):
            raise RunError(
                f"Run {run_id} is {run.status.value}; only created, paused or failed runs can run"
            )
        repo = store.get(self.db, Repo, run.repo_id)
        feature = store.get(self.db, Feature, run.feature_id) if run.feature_id else None
        repo_scope = definition.workflow.scope == "repo"
        if repo is None or (feature is None and not repo_scope):
            raise RunError(f"Run {run_id} has no repo or feature record")
        lock = self._lock(run, repo, feature)
        lock.keep_alive()
        try:
            if feature is not None:
                worktree = ensure_feature_worktree(self.db, self.home, repo, feature)
            else:
                worktree = clarity_branch.ensure_worktree(
                    self.home,
                    repo,
                    branch=self.config.clarity.branch,
                    update=run.status is RunStatus.CREATED,
                )
            state.workdir = str(worktree)
            self._install_engines(definition, worktree)
            run.abort_requested = False
            state.error = None
            state.paused_at = None
            self._set_status(run, state, files, RunStatus.RUNNING)
            shared = Shared(
                root_run_id=run.id,
                run_limits=definition.workflow.limits,
                spent_usd=self._spent(run.id),
                call_stack=[definition.id],
            )
            rc = RunContext(self, run, definition, files, state, repo, feature, worktree, shared)
            if feature is not None:
                rc.emit(
                    "run_started",
                    workflow=definition.workflow.name,
                    feature=feature.name,
                    worktree=str(worktree),
                )
            else:
                rc.emit(
                    "run_started",
                    workflow=definition.workflow.name,
                    feature=None,
                    scope="repo",
                    worktree=str(worktree),
                )
            watcher = asyncio.create_task(self._watch_abort(run.id, shared))
            try:
                await self._drive(rc)
            finally:
                watcher.cancel()
                with suppress(asyncio.CancelledError):
                    await watcher
        finally:
            lock.release()
        return rc.run

    def _lock(self, run: Run, repo: Repo, feature: Feature | None) -> locks.Lock:
        """Take the run's feature lock, or its repo's lock for a repo-scoped run."""
        if feature is not None:
            key, busy = locks.feature_lock_key(feature.id), f"Feature {feature.name}"
        else:
            key, busy = locks.repo_lock_key(repo.id), f"Repo {repo.name}"
        try:
            return locks.acquire(self.db, key, run_id=run.id)
        except locks.LockHeld as exc:
            raise RunError(f"{busy} already has an active run ({exc.info.run_id})") from exc

    async def execute_child(self, parent: RunContext, child_id: str) -> Run:
        run, files, state, definition = self._load(child_id)
        if run.status is RunStatus.COMPLETED:
            return run
        if run.status is RunStatus.ABORTED:
            raise RunAborted(run.error or "child run aborted")
        state.error = None
        state.paused_at = None
        self._set_status(run, state, files, RunStatus.RUNNING)
        parent.shared.call_stack.append(definition.id)
        try:
            rc = RunContext(
                self,
                run,
                definition,
                files,
                state,
                parent.repo,
                parent.feature,
                parent.worktree,
                parent.shared,
            )
            rc.emit("run_started", parent_run_id=parent.run.id)
            await self._drive(rc, raise_on_stop=True)
        finally:
            parent.shared.call_stack.pop()
        return rc.run

    async def _drive(self, rc: RunContext, *, raise_on_stop: bool = False) -> None:
        run, state, files = rc.run, rc.state, rc.files
        try:
            done = hooks.completed_keys(self.db, run.id, None)
            before = hooks.run_hooks(rc.definition, "before")
            error = await hooks.run_group(rc, before, None, Scope(), skip=done)
            if error is not None:
                raise RunHookFailed(error)
            await rc.run_steps(rc.definition.steps, Scope())
            after = hooks.run_hooks(rc.definition, "after")
            error = await hooks.run_group(rc, after, None, Scope(), skip=done)
            if error is not None:
                raise RunHookFailed(error)
            outputs = {
                name: rc.render(spec.value, Scope()) for name, spec in rc.definition.outputs.items()
            }
            run.outputs = outputs
            run.current_step_id = None
            state.current_step_id = None
            if self._commit_feature(rc, RunStatus.COMPLETED):
                self._merge_feature(rc)
            self._set_status(run, state, files, RunStatus.COMPLETED)
            rc.emit("run_finished", status="completed", outputs=outputs)
            self._notify(rc, "completed")
        except RunPaused as paused:
            run.error = paused.reason
            state.error = paused.reason
            self._commit_clarity(rc, RunStatus.PAUSED)
            self._commit_feature(rc, RunStatus.PAUSED)
            self._set_status(run, state, files, RunStatus.PAUSED)
            rc.emit("run_paused", step_id=paused.step_id, reason=paused.reason)
            self._notify(rc, self._waiting_for(rc, paused))
            if raise_on_stop:
                raise
        except RunAborted as aborted:
            run.error = aborted.reason
            state.error = aborted.reason
            self._commit_clarity(rc, RunStatus.ABORTED)
            self._commit_feature(rc, RunStatus.ABORTED)
            self._set_status(run, state, files, RunStatus.ABORTED)
            rc.emit("run_finished", status="aborted", reason=aborted.reason)
            if raise_on_stop:
                raise
        except (StepFailed, expressions.ExpressionError) as failed:
            run.error = str(failed)
            state.error = str(failed)
            self._commit_clarity(rc, RunStatus.FAILED)
            self._commit_feature(rc, RunStatus.FAILED)
            self._set_status(run, state, files, RunStatus.FAILED)
            rc.emit("run_finished", status="failed", error=str(failed))
            self._notify(rc, f"failed at {run.current_step_id or 'a step'}")

    def _notify(self, rc: RunContext, what: str) -> None:
        """A desktop notification for a root run that waits for a person or ends."""
        if rc.run.parent_run_id is not None:
            return  # the root run notifies for its called workflows
        notify.notify(f"{self.run_label(rc)} {what}", configured=self.config.notifications.enabled)

    @staticmethod
    def run_label(rc: RunContext) -> str:
        """``clarity on wc-lite`` or ``automated on wc-lite (001-word-count)``."""
        feature = f" ({rc.feature.name})" if rc.feature is not None else ""
        return f"{rc.run.workflow_id} on {rc.repo.name}{feature}"

    def _waiting_for(self, rc: RunContext, paused: RunPaused) -> str:
        from compose.tracking import views  # tracking reads the runner's files

        try:
            asked = views.waiting_questions(self.home, rc.run)
            if asked:
                return f"is waiting for your answers ({', '.join(q['id'] for q in asked)})"
            gate = views.waiting_gate(self.home, rc.run)
        except Exception:  # the notification falls back on the pause reason
            gate = None
        if gate and gate.get("message"):
            return f"is waiting at gate {gate['step_id']}: {gate['message']}"
        return f"is paused: {paused.reason}"

    def _commit_clarity(self, rc: RunContext, status: RunStatus) -> None:
        """A clarity run that stops keeps what it wrote: commit the clarity paths on its
        branch. A failure is recorded as an event and never changes the run's outcome."""
        if (
            rc.feature is not None
            or rc.run.parent_run_id is not None
            or rc.definition.id not in clarity.CLARITY_WORKFLOWS
        ):
            return
        message = clarity.commit_message(rc, status.value)
        try:
            sha = clarity_branch.commit_paths(rc.worktree, message)
        except Exception as exc:  # never mask the run's own outcome
            rc.emit("clarity_commit_failed", error=str(exc))
            return
        if sha is not None:
            rc.emit("clarity_committed", sha=sha, message=message)

    def _commit_feature(self, rc: RunContext, status: RunStatus) -> bool:
        """A feature run that stops commits its worktree on the feature branch, so the work
        shows in the repo (``git diff main...<branch>``) and can be merged from there. A
        failure is recorded as an event and never changes the run's outcome. Returns
        whether the branch now holds the run's work."""
        if rc.feature is None or rc.run.parent_run_id is not None:
            return False
        state = "" if status is RunStatus.COMPLETED else f" ({status.value})"
        message = (
            f"{rc.feature.name}: {rc.definition.workflow.name}{state}\n\n"
            f"Run {rc.run.id} ({rc.definition.id})."
        )
        try:
            sha = commit_all(rc.worktree, message)
        except Exception as exc:  # never mask the run's own outcome
            rc.emit("feature_commit_failed", error=str(exc))
            return False
        if sha is not None:
            rc.emit("feature_committed", sha=sha, branch=rc.feature.branch)
        return True

    def _merge_feature(self, rc: RunContext) -> None:
        """A completed feature run fast-forwards the default branch to the feature branch
        (config ``features.merge``), so the work shows in the repo's own folder. When it
        can't, the reason is recorded and the run's outcome stays as it was."""
        if rc.feature is None or not self.config.features.merge:
            return
        try:
            reason = merge_into_default(rc.repo, rc.feature.branch)
        except Exception as exc:  # never mask the run's own outcome
            reason = str(exc)
        if reason is None:
            rc.emit("feature_merged", branch=rc.feature.branch)
        else:
            rc.emit("feature_merge_pending", branch=rc.feature.branch, reason=reason)

    async def _watch_abort(self, run_id: str, shared: Shared) -> None:
        while not shared.abort_event.is_set():
            row = self.db.execute(
                "SELECT abort_requested FROM runs WHERE id = ?", (run_id,)
            ).fetchone()
            if row is not None and row[0]:
                shared.abort_event.set()
                return
            await asyncio.sleep(ABORT_POLL_SECONDS)

    # ------------------------------------------------------------ public verbs

    async def start(
        self,
        repo: Repo,
        workflow: loader.LoadedWorkflow | str,
        inputs: dict[str, Any] | None = None,
        *,
        feature: str | None = None,
    ) -> Run:
        run = self.create_run(repo, workflow, inputs, feature=feature)
        return await self.execute(run.id)

    async def resume(
        self, run_id: str, inputs: dict[str, Any] | None = None, *, choice: str | None = None
    ) -> Run:
        """Continue a paused or failed run, optionally with new inputs or a gate choice."""
        self.prepare_resume(run_id, inputs, choice=choice)
        return await self.execute(run_id)

    def prepare_resume(
        self, run_id: str, inputs: dict[str, Any] | None = None, *, choice: str | None = None
    ) -> Run:
        """Check a run can be resumed and record new inputs or a gate choice (no execution)."""
        run, files, state, definition = self._load(run_id)
        if run.parent_run_id is not None:
            raise RunError(f"{run_id} is a child run; resume its parent {run.parent_run_id}")
        if run.status not in (RunStatus.PAUSED, RunStatus.FAILED):
            raise RunError(
                f"Run {run_id} is {run.status.value}; only paused or failed runs can be resumed"
            )
        if inputs:
            merged = {**run.inputs, **inputs}
            run.inputs = self.resolve_inputs(definition, merged, ask_missing=False)
            store.update(self.db, run)
            files.write_inputs(run.inputs)
        if choice is not None:
            if not state.paused_at:
                raise RunError(f"Run {run_id} is not waiting at a gate")
            target_files, target_state = self._deepest_paused(run_id, state)
            target_state.gate_choices[target_state.paused_at or ""] = choice
            target_files.write_state(target_state)
        return run

    def _deepest_paused(self, run_id: str, state: RunState) -> tuple[RunFiles, RunState]:
        """The run (this one or a child) whose gate is waiting."""
        files = RunFiles(self.home.run_dir(run_id))
        key = state.paused_at
        while key and key in state.children:
            child_files = RunFiles(self.home.run_dir(state.children[key]))
            child_state = child_files.read_state()
            if not child_state.paused_at:
                break
            files, state, key = child_files, child_state, child_state.paused_at
        return files, state

    def request_abort(self, run_id: str) -> Run:
        """Abort a run: a running one stops between engine events; a paused or failed one
        at once (it can no longer be resumed)."""
        run, files, state, _ = self._load(run_id)
        if run.status is RunStatus.RUNNING:
            run.abort_requested = True
            store.update(self.db, run)
            files.append_event({"type": "abort_requested", "run_id": run.id})
            return run
        if run.status in (RunStatus.PAUSED, RunStatus.CREATED, RunStatus.FAILED):
            run.error = "aborted by request"
            state.error = run.error
            self._set_status(run, state, files, RunStatus.ABORTED)
            files.append_event({"type": "run_finished", "run_id": run.id, "status": "aborted"})
            return run
        raise RunError(f"Run {run_id} is {run.status.value}; nothing to abort")
