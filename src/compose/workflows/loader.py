"""Loading workflow definitions and resolving them by id.

Resolution order for an id: the repo's ``.compose/workflows/<id>/``, then the user's
``$COMPOSE_HOME/workflows/<id>/``, then built-ins.
A path to a ``.yml`` file or a workflow folder is loaded directly.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import httpx
import yaml
from pydantic import ValidationError

from compose.core.home import home_root
from compose.workflows.schema import BUILTIN_TRACKING_HOOKS, Workflow

BUILTIN_DIR = Path(__file__).parent / "builtins"
REPO_WORKFLOWS_DIR = Path(".compose") / "workflows"
DEFINITION_NAMES = ("workflow.yml", "workflow.yaml")
USER_WORKFLOWS_DIRNAME = "workflows"

Source = Literal["builtin", "user", "repo", "file"]
Scope = Literal["repo", "user"]


def user_workflows_dir() -> Path:
    """The user's workflow folder, shared by every repo: ``$COMPOSE_HOME/workflows``."""
    return home_root() / USER_WORKFLOWS_DIRNAME


class WorkflowError(Exception):
    """A workflow cannot be found, loaded or installed."""


@dataclass(frozen=True)
class LoadedWorkflow:
    definition: Workflow
    path: Path  # the YAML file
    source: Source

    @property
    def directory(self) -> Path:
        return self.path.parent

    @property
    def id(self) -> str:
        return self.definition.id


def format_validation_error(err: ValidationError) -> list[str]:
    lines: list[str] = []
    for item in err.errors():
        loc = ".".join(str(p) for p in item["loc"])
        msg = str(item["msg"]).removeprefix("Value error, ")
        for line in msg.splitlines():
            lines.append(f"{loc}: {line}" if loc else line)
    return lines


def parse_workflow(text: str, origin: str) -> Workflow:
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise WorkflowError(f"{origin}: invalid YAML: {exc}") from exc
    if not isinstance(data, dict):
        raise WorkflowError(f"{origin}: a workflow must be a YAML mapping")
    try:
        return Workflow.model_validate(data)
    except ValidationError as exc:
        details = "\n".join(f"  {line}" for line in format_validation_error(exc))
        raise WorkflowError(f"{origin}: invalid workflow:\n{details}") from exc


def definition_file(path: Path) -> Path:
    """The YAML file for a workflow folder or file path."""
    if path.is_dir():
        for name in DEFINITION_NAMES:
            if (path / name).is_file():
                return path / name
        raise WorkflowError(f"{path} has no workflow.yml")
    if path.is_file():
        return path
    raise WorkflowError(f"{path} does not exist")


def load_path(path: Path, source: Source = "file") -> LoadedWorkflow:
    file = definition_file(path.expanduser().resolve())
    definition = parse_workflow(file.read_text(), str(file))
    if source != "builtin" and not file.is_relative_to(BUILTIN_DIR.resolve()):
        _reject_internal_steps(definition, file)
    return LoadedWorkflow(definition, file, source)


def _reject_internal_steps(definition: Workflow, file: Path) -> None:
    """``type: clarity`` steps are compose's own: only built-in workflows may use them."""
    internal = [where for where, step, _ in definition.iter_steps() if step.kind == "clarity"]
    if internal:
        details = "\n".join(
            f"  {where}: type clarity is internal to compose's built-in workflows"
            for where in internal
        )
        raise WorkflowError(f"{file}: invalid workflow:\n{details}")


def _looks_like_path(ref: str) -> bool:
    return "/" in ref or ref.endswith((".yml", ".yaml")) or ref.startswith(".")


def _candidates(repo_root: Path | None) -> list[tuple[Path, Source]]:
    dirs: list[tuple[Path, Source]] = []
    if repo_root is not None:
        dirs.append((repo_root / REPO_WORKFLOWS_DIR, "repo"))
    dirs.append((user_workflows_dir(), "user"))
    dirs.append((BUILTIN_DIR, "builtin"))
    return dirs


def resolve(ref: str, repo_root: Path | None) -> LoadedWorkflow:
    """Load a workflow by id (repo first, then user, then built-in) or by path."""
    if _looks_like_path(ref):
        return load_path(Path(ref))
    for base, source in _candidates(repo_root):
        folder = base / ref
        if folder.is_dir():
            loaded = load_path(folder, source)
            if loaded.id != ref:
                raise WorkflowError(
                    f"{loaded.path}: workflow.id is {loaded.id!r} but its folder is {ref!r}"
                )
            return loaded
    raise WorkflowError(f"No workflow {ref!r} (see `compose workflow list`)")


@dataclass(frozen=True)
class WorkflowListing:
    workflow: LoadedWorkflow | None
    id: str
    source: Source
    shadowed: bool
    error: str | None = None


def list_workflows(repo_root: Path | None) -> list[WorkflowListing]:
    """All workflows; an earlier source shadows a later one with the same id."""
    seen: set[str] = set()
    out: list[WorkflowListing] = []
    for base, source in _candidates(repo_root):
        if not base.is_dir():
            continue
        for folder in sorted(p for p in base.iterdir() if p.is_dir()):
            if not any((folder / n).is_file() for n in DEFINITION_NAMES):
                continue
            shadowed = folder.name in seen
            seen.add(folder.name)
            try:
                loaded = load_path(folder, source)
                out.append(WorkflowListing(loaded, folder.name, source, shadowed))
            except WorkflowError as exc:
                out.append(WorkflowListing(None, folder.name, source, shadowed, str(exc)))
    return out


def install_dir(scope: Scope, repo_root: Path | None) -> Path:
    """Where ``compose workflow add`` installs for a scope."""
    if scope == "user":
        return user_workflows_dir()
    if repo_root is None:
        raise WorkflowError("Run this inside a git repo, or pass --user")
    return repo_root / REPO_WORKFLOWS_DIR


def add_workflow(
    repo_root: Path | None, source: str, *, force: bool = False, scope: Scope = "repo"
) -> LoadedWorkflow:
    """Install a workflow (folder, file or URL of a YAML file) into the repo or user folder."""
    target_root = install_dir(scope, repo_root)
    if source.startswith(("http://", "https://")):
        try:
            response = httpx.get(source, follow_redirects=True, timeout=30)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise WorkflowError(f"Cannot download {source}: {exc}") from exc
        definition = parse_workflow(response.text, source)
        target = target_root / definition.id
        _prepare_target(target, force)
        target.mkdir(parents=True)
        (target / "workflow.yml").write_text(response.text)
    else:
        loaded = load_path(Path(source))
        target = target_root / loaded.id
        if target.resolve() == loaded.directory.resolve():
            raise WorkflowError(f"{source} is already installed")
        _prepare_target(target, force)
        if loaded.path.name in DEFINITION_NAMES and Path(source).expanduser().is_dir():
            shutil.copytree(loaded.directory, target)
        else:
            target.mkdir(parents=True)
            shutil.copy2(loaded.path, target / "workflow.yml")
    return load_path(target, scope)


def _prepare_target(target: Path, force: bool) -> None:
    if target.exists():
        if not force:
            raise WorkflowError(f"Workflow {target.name!r} is already installed; pass --force")
        shutil.rmtree(target)


def remove_workflow(repo_root: Path | None, workflow_id: str, *, scope: Scope = "repo") -> Path:
    base = install_dir(scope, repo_root)
    target = base / workflow_id
    if not target.is_dir():
        if (BUILTIN_DIR / workflow_id).is_dir():
            raise WorkflowError(f"{workflow_id!r} is built in and cannot be removed")
        raise WorkflowError(f"No installed workflow {workflow_id!r} in {base}")
    shutil.rmtree(target)
    return target


def effective_hooks(definition: Workflow) -> list[dict[str, Any]]:
    """Hooks that run, built-in tracking hooks included, as JSON-ready dicts."""
    hooks: list[dict[str, Any]] = []
    if definition.workflow.tracking:
        for b in BUILTIN_TRACKING_HOOKS:
            hooks.append(
                {
                    "event": b.event,
                    "name": b.name,
                    "builtin": True,
                    "position": b.position,
                    "description": b.description,
                }
            )
    for event, specs in definition.hooks.items():
        for spec in specs:
            hooks.append(
                {
                    "event": event,
                    "name": spec.label,
                    "builtin": False,
                    "kind": spec.kind,
                    "priority": spec.priority,
                    "optional": spec.optional,
                    "condition": spec.condition,
                }
            )
    return hooks
