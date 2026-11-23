from __future__ import annotations

from pathlib import Path

import pytest

from compose.core.config import ConfigError, load_config
from compose.core.home import Home, ensure_home, home_root


def test_home_from_env(compose_home: Path) -> None:
    assert home_root() == compose_home.resolve()


def test_home_default(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.delenv("COMPOSE_HOME")
    monkeypatch.setenv("HOME", str(tmp_path))
    assert home_root() == (tmp_path / ".compose").resolve()


def test_ensure_home_creates_dirs(tmp_path: Path) -> None:
    home = ensure_home(tmp_path / "h")
    for path in (home.root, home.runs, home.repos, home.worktrees):
        assert path.is_dir()
    assert home.db_path == home.root / "compose.db"
    assert home.run_dir("run_1") == home.runs / "run_1"


def test_config_defaults(home: Home) -> None:
    config = load_config(home)
    assert config.server.host == "127.0.0.1"
    assert config.server.port == 8765
    assert config.server.token is None
    assert config.defaults.engine == "claude"
    assert config.notifications.enabled is True


def test_config_file_values(home: Home) -> None:
    home.config_path.write_text("server:\n  port: 9000\ndefaults:\n  model: m1\n")
    config = load_config(home)
    assert config.server.port == 9000
    assert config.defaults.model == "m1"


def test_config_turns_notifications_off(home: Home) -> None:
    home.config_path.write_text("notifications: {enabled: false}\n")
    assert load_config(home).notifications.enabled is False


def test_config_token_env_override(home: Home, monkeypatch: pytest.MonkeyPatch) -> None:
    home.config_path.write_text("server:\n  token: from-file\n")
    monkeypatch.setenv("COMPOSE_API_TOKEN", "from-env")
    assert load_config(home).server.token == "from-env"


def test_config_empty_file(home: Home) -> None:
    home.config_path.write_text("")
    assert load_config(home).server.port == 8765


@pytest.mark.parametrize(
    ("content", "expected"),
    [
        ("server: [unclosed", "Cannot parse"),
        ("- a\n- b\n", "top level must be a mapping"),
        ("server:\n  prot: 1\n", "server.prot"),
        ("server:\n  port: 70000\n", "server.port"),
        ("notifications:\n  sound: true\n", "notifications.sound"),
    ],
)
def test_config_errors(home: Home, content: str, expected: str) -> None:
    home.config_path.write_text(content)
    with pytest.raises(ConfigError) as err:
        load_config(home)
    assert expected in str(err.value)
    assert str(home.config_path) in str(err.value)
