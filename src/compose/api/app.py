"""The compose HTTP API (``compose serve``). (No postponed annotations: FastAPI reads them.)

Runs started here execute as background tasks in the server process, on the same runner
and store as the CLI: a run started by either is visible and resumable from the other.
Gates never block: a run without a decision pauses and waits for
``POST /runs/{id}/gates/{step}`` or ``POST /runs/{id}/resume``.
"""

import asyncio
import logging
import secrets
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager, suppress
from datetime import datetime
from pathlib import Path
from typing import Annotated, Any, Literal

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from compose import __version__
from compose.api import events as run_events
from compose.core import store
from compose.core.config import Config, ConfigError, load_config
from compose.core.db import Database, open_database, utcnow
from compose.core.home import Home, ensure_home
from compose.core.locks import LockHeld
from compose.core.models import Feature, Run, RunStatus, StepExec
from compose.engines.registry import EngineError, EngineRegistry, default_registry
from compose.repos import features, git, registry
from compose.repos.features import FeatureError
from compose.repos.git import GitError
from compose.repos.registry import RepoError
from compose.repos.worktrees import WorktreeError
from compose.runner.errors import InputError, RunError
from compose.runner.recovery import recover_stale_runs
from compose.runner.runner import Runner
from compose.runner.state import TransitionError
from compose.tracking import records, views
from compose.workflows import loader
from compose.workflows.loader import WorkflowError

log = logging.getLogger("compose.api")
RunStatusName = Literal["created", "running", "paused", "completed", "failed", "aborted"]
GroupByName = Literal["step", "run", "feature", "repo", "day"]


# ------------------------------------------------------------------ bodies


class AddRepo(BaseModel):
    path: str | None = Field(None, description="Local path of a git checkout.")
    url: str | None = Field(None, description="Git URL to clone into the compose home.")
    name: str | None = Field(None, description="Short name (default: from the path or URL).")


class StartRun(BaseModel):
    workflow: str | None = Field(
        None,
        description="Workflow id (repo or built-in), or a file path; default: the configured "
        "default workflow (automated).",
    )
    feature: str | None = Field(None, description="Existing feature (NNN-name); default new.")
    inputs: dict[str, Any] = Field(default_factory=dict)


class ResumeRun(BaseModel):
    inputs: dict[str, Any] = Field(default_factory=dict)
    choice: str | None = Field(None, description="Decision for the gate the run waits at.")


class GateDecision(BaseModel):
    choice: str


# ----------------------------------------------------------------- errors


def _status_for(exc: Exception) -> int:
    message = str(exc)
    if isinstance(exc, views.ViewError) or message.startswith("No "):
        return 404
    if isinstance(exc, LockHeld) or "already has an active run" in message:
        return 409
    if isinstance(exc, InputError | WorkflowError | EngineError):
        return 422
    if isinstance(exc, RunError | TransitionError):
        return 409
    return 400


EXPECTED: tuple[type[Exception], ...] = (
    views.ViewError,
    RunError,
    TransitionError,
    LockHeld,
    RepoError,
    FeatureError,
    GitError,
    WorktreeError,
    WorkflowError,
    EngineError,
    ConfigError,
)


# ------------------------------------------------------------------ state


class Server:
    """What the routes share: the store, the engines and the runs executing here."""

    def __init__(self, home: Home, db: Database, engines: EngineRegistry, config: Config):
        self.home = home
        self.db = db
        self.engines = engines
        self.config = config
        self.tasks: dict[str, asyncio.Task[None]] = {}

    def runner(self) -> Runner:
        return Runner(self.db, self.home, engines=self.engines, config=self.config)

    async def launch(self, runner: Runner, run_id: str) -> None:
        """Execute a run in the background. Returns once it holds its feature lock."""
        task = asyncio.create_task(self._execute(runner, run_id), name=f"run {run_id}")
        self.tasks[run_id] = task
        task.add_done_callback(lambda _: self.tasks.pop(run_id, None))
        await asyncio.sleep(0)  # let it take the feature lock before we answer

    async def _execute(self, runner: Runner, run_id: str) -> None:
        try:
            await runner.execute(run_id)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # the run could not start; record why
            log.exception("run %s did not start", run_id)
            run = store.get(self.db, Run, run_id)
            if run is not None and run.status is RunStatus.CREATED:
                run.status = RunStatus.FAILED
                run.error = f"could not start: {exc}"
                run.ended_at = utcnow()
                store.update(self.db, run)

    async def shutdown(self) -> None:
        """Stop runs executing here; they are marked failed and can be resumed."""
        tasks = list(self.tasks.values())
        for task in tasks:
            task.cancel()
        for task in tasks:
            with suppress(asyncio.CancelledError, Exception):
                await task
        recover_stale_runs(self.db, self.home)


def create_app(
    home: Home | None = None,
    *,
    engines: Callable[[], EngineRegistry] | EngineRegistry | None = None,
) -> FastAPI:
    """Build the API. ``engines`` replaces the default engine registry (tests)."""

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        resolved_home = home or ensure_home()
        db = open_database(resolved_home)
        registry_ = engines() if callable(engines) else engines or default_registry()
        server = Server(resolved_home, db, registry_, load_config(resolved_home))
        recovered = recover_stale_runs(db, resolved_home)
        if recovered:
            log.warning("marked %d interrupted run(s) failed", len(recovered))
        app.state.server = server
        try:
            yield
        finally:
            await server.shutdown()
            db.close()

    app = FastAPI(
        title="compose",
        version=__version__,
        description="Spec-driven development workflows with traceability and cost tracking.",
        lifespan=lifespan,
    )

    async def expected_errors(request: Request, exc: Exception) -> JSONResponse:
        return JSONResponse({"detail": str(exc)}, status_code=_status_for(exc))

    for error in EXPECTED:
        app.add_exception_handler(error, expected_errors)

    def get_server(request: Request) -> Server:
        server: Server = request.app.state.server
        return server

    def authorize(request: Request, authorization: Annotated[str | None, Header()] = None) -> None:
        token = get_server(request).config.server.token
        if not token:
            return
        scheme, _, given = (authorization or "").partition(" ")
        if scheme.lower() != "bearer" or not secrets.compare_digest(given, token):
            raise HTTPException(401, "missing or wrong bearer token")

    S = Annotated[Server, Depends(get_server)]
    auth = [Depends(authorize)]

    # ------------------------------------------------------------ health

    @app.get("/health", tags=["server"])
    def health(server: S) -> dict[str, Any]:
        """Liveness, version and how many runs execute in this server."""
        return {"status": "ok", "version": __version__, "active_runs": sorted(server.tasks)}

    # ------------------------------------------------------------- repos

    def repo_json(repo: Any) -> dict[str, Any]:
        data: dict[str, Any] = repo.model_dump(mode="json")
        return data

    @app.get("/repos", tags=["repos"], dependencies=auth)
    def list_repos(server: S) -> list[dict[str, Any]]:
        return [repo_json(r) for r in registry.list_repos(server.db)]

    @app.post("/repos", tags=["repos"], dependencies=auth, status_code=201)
    def add_repo(body: AddRepo, server: S) -> dict[str, Any]:
        """Register a local checkout (``path``) or clone a git ``url``."""
        if bool(body.path) == bool(body.url):
            raise HTTPException(422, "give exactly one of path or url")
        source = body.url if body.url else str(body.path)
        if body.url and not registry.is_url(body.url):
            raise HTTPException(422, f"{body.url!r} is not a git URL")
        return repo_json(registry.add_repo(server.db, server.home, source, name=body.name))

    @app.get("/repos/{repo}", tags=["repos"], dependencies=auth)
    def get_repo(repo: str, server: S) -> dict[str, Any]:
        return repo_json(registry.get_repo(server.db, repo))

    @app.delete("/repos/{repo}", tags=["repos"], dependencies=auth)
    def remove_repo(
        repo: str, server: S, force: bool = False, delete_clone: bool = False
    ) -> dict[str, Any]:
        """Unregister a repo (``force`` when it has run history)."""
        removed = registry.remove_repo(
            server.db, server.home, repo, force=force, delete_clone=delete_clone
        )
        return {"removed": removed.name}

    # --------------------------------------------------------- workflows

    @app.get("/repos/{repo}/workflows", tags=["workflows"], dependencies=auth)
    def list_workflows(repo: str, server: S) -> list[dict[str, Any]]:
        root = Path(registry.get_repo(server.db, repo).path)
        out = []
        for item in loader.list_workflows(root):
            meta = item.workflow.definition.workflow if item.workflow else None
            out.append(
                {
                    "id": item.id,
                    "source": item.source,
                    "shadowed": item.shadowed,
                    "name": meta.name if meta else None,
                    "version": meta.version if meta else None,
                    "description": meta.description if meta else None,
                    "error": item.error,
                }
            )
        return out

    @app.get("/repos/{repo}/workflows/{workflow_id}", tags=["workflows"], dependencies=auth)
    def get_workflow(repo: str, workflow_id: str, server: S) -> dict[str, Any]:
        """A workflow's definition, with the hooks that will run (built-ins included)."""
        root = Path(registry.get_repo(server.db, repo).path)
        if "/" in workflow_id or workflow_id.startswith("."):
            raise HTTPException(422, "use a workflow id")
        loaded = loader.resolve(workflow_id, root)
        return {
            "id": loaded.id,
            "source": loaded.source,
            "definition": loaded.definition.model_dump(mode="json", by_alias=True),
            "effective_hooks": loader.effective_hooks(loaded.definition),
        }

    # ---------------------------------------------------------- features

    @app.get("/repos/{repo}/features", tags=["features"], dependencies=auth)
    def list_features(repo: str, server: S) -> list[dict[str, Any]]:
        """Features from the repo's branches and specs folders, with their run counts."""
        found = registry.get_repo(server.db, repo)
        counts = dict(
            server.db.conn.execute(
                "SELECT f.name, COUNT(r.id) FROM features f"
                " LEFT JOIN runs r ON r.feature_id = f.id AND r.parent_run_id IS NULL"
                " WHERE f.repo_id = ? GROUP BY f.name",
                (found.id,),
            ).fetchall()
        )
        names = {f.name: f for f in features.list_features(Path(found.path))}
        out = []
        for name in sorted(set(names) | set(counts)):
            summary = names.get(name)
            out.append(
                {
                    "name": name,
                    "has_branch": bool(summary and summary.has_branch),
                    "has_specs_folder": bool(summary and summary.has_dir),
                    "runs": counts.get(name, 0),
                }
            )
        return out

    @app.get("/repos/{repo}/features/{feature}", tags=["features"], dependencies=auth)
    def get_feature(repo: str, feature: str, server: S) -> dict[str, Any]:
        """A feature's paths, which spec files exist, its worktree, runs and totals."""
        found = registry.get_repo(server.db, repo)
        root = Path(found.path)
        paths = features.feature_paths(root, feature)
        rows = store.select(server.db, Feature, "repo_id = ? AND name = ?", (found.id, feature))
        record = rows[0] if rows else None
        if record is None and not git.branch_exists(root, feature):
            raise views.ViewError(f"No feature {feature!r} in repo {found.name!r}")
        worktree = Path(record.worktree_path) if record and record.worktree_path else None
        base = worktree if worktree and worktree.exists() else root
        files_dir = base / paths.feature_dir.relative_to(root)
        return {
            **paths.to_json(),
            "branch_exists": git.branch_exists(root, feature),
            "worktree": str(worktree) if worktree else None,
            "files": {
                name: (files_dir / f"{name}.md").exists() for name in ("spec", "plan", "tasks")
            },
            "runs": (
                views.list_runs(server.db, repo=found, feature=record, limit=None) if record else []
            ),
            "totals": (
                views.cost(server.db, "feature", repo=found, feature=record)["total"]
                if record
                else None
            ),
        }

    # -------------------------------------------------------------- runs

    @app.post("/repos/{repo}/runs", tags=["runs"], dependencies=auth, status_code=202)
    async def start_run(repo: str, body: StartRun, server: S) -> dict[str, Any]:
        """Create a run and start it in the background. 409 when the feature is busy."""
        found = registry.get_repo(server.db, repo)
        runner = server.runner()
        run = runner.create_run(found, body.workflow, body.inputs, feature=body.feature)
        await server.launch(runner, run.id)
        current = views.get_run(server.db, run.id)
        return {**views.run_brief(server.db, current), "run_id": run.id}

    @app.get("/runs", tags=["runs"], dependencies=auth)
    def list_runs(
        server: S,
        repo: str | None = None,
        feature: str | None = None,
        status: RunStatusName | None = None,
        since: datetime | None = None,
        limit: Annotated[int, Query(ge=0, le=1000)] = 50,
    ) -> list[dict[str, Any]]:
        """Root runs, newest first. ``feature`` needs ``repo``."""
        found = registry.get_repo(server.db, repo) if repo else None
        feat = None
        if feature is not None:
            if found is None:
                raise HTTPException(422, "feature needs repo")
            feat = views.find_feature(server.db, found, feature)
        return views.list_runs(
            server.db,
            repo=found,
            feature=feat,
            status=RunStatus(status) if status else None,
            since=since,
            limit=limit or None,
        )

    @app.get("/runs/{run_id}", tags=["runs"], dependencies=auth)
    def get_run(run_id: str, server: S) -> dict[str, Any]:
        """Status, current step, the gate it waits at, every step and totals."""
        return views.run_detail(server.db, server.home, run_id)

    @app.get("/runs/{run_id}/steps/{exec_id}", tags=["runs"], dependencies=auth)
    def get_step(run_id: str, exec_id: str, server: S) -> dict[str, Any]:
        """One step execution: totals, hooks (with their own cost and files), files,
        actions."""
        row = store.get(server.db, StepExec, exec_id)
        if row is None or row.run_id not in views.run_tree(server.db, run_id):
            raise views.ViewError(f"No step execution {exec_id!r} in run {run_id}")
        return records.step_record(server.db, row)

    @app.get("/runs/{run_id}/trace", tags=["runs"], dependencies=auth)
    def get_trace(run_id: str, server: S, step: str | None = None) -> dict[str, Any]:
        """Every action per step, hooks nested."""
        return views.trace(server.db, run_id, step)

    @app.get("/runs/{run_id}/changes", tags=["runs"], dependencies=auth)
    def get_changes(run_id: str, server: S, step: str | None = None) -> dict[str, Any]:
        """Files and lines changed per step."""
        return views.changes(server.db, run_id, step)

    @app.get("/runs/{run_id}/events", tags=["runs"], dependencies=auth, response_model=None)
    def get_events(
        run_id: str,
        server: S,
        after: Annotated[int, Query(ge=0)] = 0,
        limit: Annotated[int, Query(ge=1, le=5000)] = 500,
        stream: bool = False,
        last_event_id: Annotated[str | None, Header()] = None,
    ) -> dict[str, Any] | StreamingResponse:
        """The run's event log. Paged by ``after`` (the last ``seq`` seen); with
        ``stream=true`` a Server-Sent Events stream that ends when the run stops."""
        views.get_run(server.db, run_id)
        log_path = server.home.run_dir(run_id) / "log.jsonl"
        if stream:
            start = int(last_event_id) if last_event_id and last_event_id.isdigit() else after
            return StreamingResponse(
                run_events.stream(server.db, run_id, log_path, start),
                media_type="text/event-stream",
                headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
            )
        page = run_events.read(log_path, after, limit)
        return {"run_id": run_id, "events": page, "next": page[-1]["seq"] if page else after}

    @app.post("/runs/{run_id}/resume", tags=["runs"], dependencies=auth, status_code=202)
    async def resume_run(run_id: str, body: ResumeRun, server: S) -> dict[str, Any]:
        """Continue a paused or failed run, with new inputs or a gate decision."""
        runner = server.runner()
        runner.prepare_resume(run_id, body.inputs, choice=body.choice)
        await server.launch(runner, run_id)
        return views.run_brief(server.db, views.get_run(server.db, run_id))

    @app.post("/runs/{run_id}/gates/{step_id}", tags=["runs"], dependencies=auth, status_code=202)
    async def decide_gate(
        run_id: str, step_id: str, body: GateDecision, server: S
    ) -> dict[str, Any]:
        """Answer the gate the run waits at and resume it."""
        run = views.get_run(server.db, run_id)
        waiting = views.waiting_gate(server.home, run)
        if waiting is None:
            raise HTTPException(409, f"Run {run_id} is not waiting at a gate")
        if waiting["step_id"] != step_id:
            raise HTTPException(409, f"Run {run_id} waits at gate {waiting['step_id']!r}")
        options = waiting.get("options")
        if options and body.choice not in options:
            raise HTTPException(422, f"choice must be one of {', '.join(options)}")
        runner = server.runner()
        runner.prepare_resume(run_id, choice=body.choice)
        await server.launch(runner, run_id)
        return views.run_brief(server.db, views.get_run(server.db, run_id))

    @app.post("/runs/{run_id}/abort", tags=["runs"], dependencies=auth)
    def abort_run(run_id: str, server: S) -> dict[str, Any]:
        """Abort a run; a running one stops at its next engine event."""
        run = server.runner().request_abort(run_id)
        return views.run_brief(server.db, run)

    # ------------------------------------------------------------- costs

    @app.get("/costs", tags=["costs"], dependencies=auth)
    def get_costs(
        server: S,
        repo: str | None = None,
        feature: str | None = None,
        run: str | None = None,
        group_by: GroupByName = "run",
        from_: Annotated[datetime | None, Query(alias="from")] = None,
        to: datetime | None = None,
    ) -> dict[str, Any]:
        """Cost, tokens and changes grouped by step, run, feature, repo or day."""
        found = registry.get_repo(server.db, repo) if repo else None
        feat = None
        if feature is not None:
            if found is None:
                raise HTTPException(422, "feature needs repo")
            feat = views.find_feature(server.db, found, feature)
        return views.cost(
            server.db, group_by, repo=found, feature=feat, run_id=run, since=from_, until=to
        )

    return app
