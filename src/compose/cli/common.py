"""Shared CLI helpers: opening the store, printing, error handling."""

from __future__ import annotations

import json
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import datetime
from functools import wraps
from typing import Any, ParamSpec, TypeVar

import typer
from rich.console import Console

from compose.core.config import ConfigError
from compose.core.db import Database, open_database
from compose.core.home import Home, ensure_home
from compose.core.locks import LockHeld
from compose.engines.registry import EngineError
from compose.repos.features import FeatureError
from compose.repos.git import GitError
from compose.repos.registry import RepoError
from compose.repos.worktrees import WorktreeError
from compose.runner.errors import RunError
from compose.runner.state import TransitionError
from compose.tracking.views import ViewError
from compose.workflows.loader import WorkflowError

console = Console()
err_console = Console(stderr=True)

USER_ERRORS: tuple[type[Exception], ...] = (
    ConfigError,
    EngineError,
    FeatureError,
    GitError,
    LockHeld,
    RepoError,
    RunError,
    TransitionError,
    ViewError,
    WorktreeError,
    WorkflowError,
)

P = ParamSpec("P")
T = TypeVar("T")


def handle_errors(func: Callable[P, T]) -> Callable[P, T]:
    """Turn expected errors into a one-line message and exit code 1."""

    @wraps(func)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
        try:
            return func(*args, **kwargs)
        except USER_ERRORS as exc:
            err_console.print(f"[red]error:[/red] {exc}", highlight=False, soft_wrap=True)
            raise typer.Exit(1) from exc

    return wrapper


@contextmanager
def open_store() -> Iterator[tuple[Home, Database]]:
    home = ensure_home()
    db = open_database(home)
    try:
        yield home, db
    finally:
        db.close()


def _json_default(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def print_json(data: Any) -> None:
    typer.echo(json.dumps(data, indent=2, default=_json_default))
