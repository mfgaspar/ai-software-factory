"""User configuration, loaded from ``$COMPOSE_HOME/config.yml``."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from compose.core.home import Home

TOKEN_ENV = "COMPOSE_API_TOKEN"


class ConfigError(Exception):
    """The config file exists but cannot be used."""


class _Section(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ServerConfig(_Section):
    host: str = "127.0.0.1"
    port: int = Field(default=8765, ge=1, le=65535)
    token: str | None = None


class DefaultsConfig(_Section):
    engine: str = "claude"
    model: str | None = None
    workflow: str = "automated"  # what compose run starts when no workflow is named


class ClarityConfig(_Section):
    branch: str = Field(default="clarity", min_length=1)  # where clarity runs work


class Config(_Section):
    server: ServerConfig = Field(default_factory=ServerConfig)
    defaults: DefaultsConfig = Field(default_factory=DefaultsConfig)
    clarity: ClarityConfig = Field(default_factory=ClarityConfig)
    # default engine_options per engine, under the workflow's and step's own
    engines: dict[str, dict[str, Any]] = Field(default_factory=dict)


def _format_validation_error(path: Path, err: ValidationError) -> str:
    lines = [f"Invalid compose config in {path}:"]
    for item in err.errors():
        where = ".".join(str(p) for p in item["loc"]) or "(root)"
        lines.append(f"  {where}: {item['msg']}")
    return "\n".join(lines)


def load_config(home: Home) -> Config:
    """Load the config file; a missing file means all defaults.

    ``COMPOSE_API_TOKEN`` overrides ``server.token``.
    """
    path = home.config_path
    data: object = {}
    if path.exists():
        try:
            data = yaml.safe_load(path.read_text()) or {}
        except yaml.YAMLError as exc:
            raise ConfigError(f"Cannot parse compose config {path}: {exc}") from exc
        if not isinstance(data, dict):
            raise ConfigError(f"Invalid compose config in {path}: top level must be a mapping")
    try:
        config = Config.model_validate(data)
    except ValidationError as exc:
        raise ConfigError(_format_validation_error(path, exc)) from exc
    token = os.environ.get(TOKEN_ENV)
    if token:
        config.server.token = token
    return config
