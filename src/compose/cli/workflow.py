"""``compose workflow ...``"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import typer
from rich.table import Table
from rich.tree import Tree

from compose.cli.common import console, handle_errors, print_json
from compose.repos import git
from compose.workflows import loader
from compose.workflows.schema import (
    BaseStep,
    CommandStep,
    GateStep,
    PromptStep,
    ShellStep,
    WorkflowCallStep,
)

app = typer.Typer(help="List, inspect, install and validate workflows.", no_args_is_help=True)


def _repo_root() -> Path | None:
    cwd = Path.cwd()
    return git.toplevel(cwd) if git.is_work_tree(cwd) else None


def _require_repo_root() -> Path:
    root = _repo_root()
    if root is None:
        raise loader.WorkflowError("Run this inside a git repo")
    return root


@app.command("list")
@handle_errors
def list_(as_json: bool = typer.Option(False, "--json", help="Print JSON.")) -> None:
    """List built-in workflows and those installed in this repo."""
    items = loader.list_workflows(_repo_root())
    if as_json:
        print_json(
            [
                {
                    "id": i.id,
                    "source": i.source,
                    "shadowed": i.shadowed,
                    "name": i.workflow.definition.workflow.name if i.workflow else None,
                    "version": i.workflow.definition.workflow.version if i.workflow else None,
                    "path": str(i.workflow.path) if i.workflow else None,
                    "error": i.error,
                }
                for i in items
            ]
        )
        return
    table = Table("id", "name", "version", "source")
    for i in items:
        if i.workflow:
            meta = i.workflow.definition.workflow
            source = i.source + (" (shadowed)" if i.shadowed else "")
            table.add_row(i.id, meta.name, meta.version, source)
        else:
            table.add_row(i.id, "[red]invalid[/red]", "", i.source)
    console.print(table)


def _step_label(step: BaseStep) -> str:
    detail = ""
    if isinstance(step, CommandStep):
        detail = f" -> {step.command}"
    elif isinstance(step, PromptStep):
        detail = " -> prompt"
    elif isinstance(step, ShellStep):
        detail = f" -> {step.run.splitlines()[0][:50]}"
    elif isinstance(step, GateStep):
        detail = f" ({'/'.join(step.options)}, on_reject={step.on_reject})"
    elif isinstance(step, WorkflowCallStep):
        detail = f" -> {step.workflow}"
    kind = getattr(step, "type", "command")
    return f"[bold]{step.id}[/bold] [dim]{kind}[/dim]{detail}"


def _add_steps(tree: Tree, steps: list[Any]) -> None:
    for step in steps:
        node = tree.add(_step_label(step))
        for label, children in step.children():
            branch = node.add(f"[dim]{label}[/dim]")
            _add_steps(branch, children)


@app.command("info")
@handle_errors
def info(
    ref: str = typer.Argument(..., help="Workflow id, or path to a workflow file/folder."),
    as_json: bool = typer.Option(False, "--json", help="Print JSON."),
) -> None:
    """Show a workflow's inputs, steps and hooks (including built-in tracking hooks)."""
    loaded = loader.resolve(ref, _repo_root())
    definition = loaded.definition
    if as_json:
        print_json(
            {
                "source": loaded.source,
                "path": str(loaded.path),
                "definition": definition.model_dump(mode="json", by_alias=True),
                "effective_hooks": loader.effective_hooks(definition),
            }
        )
        return
    meta = definition.workflow
    console.print(f"[bold]{meta.name}[/bold] ({meta.id} {meta.version}, {loaded.source})")
    if meta.description:
        console.print(meta.description.strip(), highlight=False)
    console.print(f"[dim]{loaded.path}[/dim]")
    if definition.inputs:
        table = Table("input", "type", "required", "default", title="Inputs", title_justify="left")
        for name, spec in definition.inputs.items():
            default = "" if spec.default is None else repr(spec.default)
            table.add_row(name, spec.type.value, "yes" if spec.required else "", default)
        console.print(table)
    tree = Tree("[bold]Steps[/bold]")
    _add_steps(tree, definition.steps)
    console.print(tree)
    table = Table("event", "hook", "notes", title="Hooks", title_justify="left")
    for hook in loader.effective_hooks(definition):
        if hook["builtin"]:
            notes = f"built-in, runs {hook['position']}"
        else:
            parts = [hook["kind"], f"priority {hook['priority']}"]
            if hook["optional"]:
                parts.append("optional")
            if hook["condition"]:
                parts.append(f"if {hook['condition']}")
            notes = ", ".join(parts)
        table.add_row(hook["event"], str(hook["name"]), notes)
    console.print(table)


@app.command("validate")
@handle_errors
def validate(
    path: Path = typer.Argument(..., help="Workflow file or folder."),
    as_json: bool = typer.Option(False, "--json", help="Print JSON."),
) -> None:
    """Check a workflow definition without running it."""
    try:
        loaded = loader.load_path(path)
    except loader.WorkflowError as exc:
        if as_json:
            print_json({"valid": False, "error": str(exc)})
            raise typer.Exit(1) from exc
        raise
    if as_json:
        print_json({"valid": True, "id": loaded.id, "path": str(loaded.path)})
    else:
        console.print(f"[green]valid[/green] {loaded.id} ({loaded.path})", highlight=False)


@app.command("add")
@handle_errors
def add(
    source: str = typer.Argument(..., help="Workflow folder, YAML file, or URL of a YAML file."),
    force: bool = typer.Option(False, "--force", help="Replace an installed workflow."),
) -> None:
    """Install a workflow into this repo's .compose/workflows/."""
    loaded = loader.add_workflow(_require_repo_root(), source, force=force)
    console.print(f"Installed {loaded.id} at {loaded.directory}", highlight=False)


@app.command("remove")
@handle_errors
def remove(workflow_id: str = typer.Argument(..., help="Installed workflow id.")) -> None:
    """Remove a workflow installed in this repo."""
    target = loader.remove_workflow(_require_repo_root(), workflow_id)
    console.print(f"Removed {target}", highlight=False)
