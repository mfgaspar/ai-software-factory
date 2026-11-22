"""Loading workflow definitions and resolving them by id.

Resolution order for an id: the repo's ``.compose/workflows/<id>/``, then built-ins.
A path to a ``.yml`` file or a workflow folder is loaded directly.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import httpx
import yaml
from pydantic import ValidationError

from compose.workflows.schema import Workflow

BUILTIN_DIR = Path(__file__).parent / "builtins"
REPO_WORKFLOWS_DIR = Path(".compose") / "workflows"
DEFINITION_NAMES = ("workflow.yml", "workflow.yaml")

Source = Literal["builtin", "repo", "file"]


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
    return LoadedWorkflow(parse_workflow(file.read_text(), str(file)), file, source)


def _looks_like_path(ref: str) -> bool:
    return "/" in ref or ref.endswith((".yml", ".yaml")) or ref.startswith(".")


def _candidates(repo_root: Path | None) -> list[tuple[Path, Source]]:
    dirs: list[tuple[Path, Source]] = []
    if repo_root is not None:
        dirs.append((repo_root / REPO_WORKFLOWS_DIR, "repo"))
    dirs.append((BUILTIN_DIR, "builtin"))
    return dirs


def resolve(ref: str, repo_root: Path | None) -> LoadedWorkflow:
    """Load a workflow by id (repo first, then built-in) or by path."""
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
    """All workflows; a repo workflow shadows a built-in with the same id."""
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


def add_workflow(repo_root: Path, source: str, *, force: bool = False) -> LoadedWorkflow:
    """Install a workflow (folder, file or URL of a YAML file) into the repo."""
    target_root = repo_root / REPO_WORKFLOWS_DIR
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
    return load_path(target, "repo")


def _prepare_target(target: Path, force: bool) -> None:
    if target.exists():
        if not force:
            raise WorkflowError(f"Workflow {target.name!r} is already installed; pass --force")
        shutil.rmtree(target)


def remove_workflow(repo_root: Path, workflow_id: str) -> Path:
    target = repo_root / REPO_WORKFLOWS_DIR / workflow_id
    if not target.is_dir():
        if (BUILTIN_DIR / workflow_id).is_dir():
            raise WorkflowError(f"{workflow_id!r} is built in and cannot be removed")
        raise WorkflowError(f"No installed workflow {workflow_id!r} in {repo_root}")
    shutil.rmtree(target)
    return target
