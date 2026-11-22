"""Unit tests never start a real Claude Code: the CLI transport finds no executable
unless a test passes ``cli_path`` (a fake script) itself."""

from __future__ import annotations

import pytest

from compose.engines.claude import install as installer


@pytest.fixture(autouse=True)
def no_real_claude(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(installer, "cli_path", lambda: None)
