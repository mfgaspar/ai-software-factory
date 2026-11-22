"""Engine adapters by name."""

from __future__ import annotations

import importlib

from compose.engines.base import Engine


class EngineError(Exception):
    """An engine is unknown or unavailable."""


class EngineRegistry:
    def __init__(self, engines: dict[str, Engine] | None = None) -> None:
        self._engines: dict[str, Engine] = dict(engines or {})

    def register(self, engine: Engine) -> None:
        self._engines[engine.name] = engine

    def get(self, name: str) -> Engine:
        engine = self._engines.get(name)
        if engine is None:
            known = ", ".join(sorted(self._engines)) or "none"
            raise EngineError(f"Engine {name!r} is not available (available: {known})")
        return engine

    def names(self) -> list[str]:
        return sorted(self._engines)


def default_registry() -> EngineRegistry:
    """Engines shipped with compose."""
    registry = EngineRegistry()
    try:
        module = importlib.import_module("compose.engines.claude.adapter")
    except ImportError:  # the Claude Code adapter is optional until it is installed
        return registry
    registry.register(module.ClaudeEngine())
    return registry
