from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

import pytest
from typer.testing import Result


def test_list_and_info(
    cli: Callable[..., Result], git_repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(git_repo)
    listed = json.loads(cli("workflow", "list", "--json").output)
    assert {w["id"] for w in listed} == {
        "bugfix",
        "full-cycle",
        "automated",
        "quick",
        "clarity",
        "clarity-validate",
    }

    result = cli("workflow", "info", "full-cycle", "--json")
    assert result.exit_code == 0, result.output
    info = json.loads(result.output)
    assert info["source"] == "builtin"
    names = [h["name"] for h in info["effective_hooks"]]
    assert names == ["compose.track.begin", "compose.track.end"]
    assert info["definition"]["steps"][0]["then"][0]["command"] == "compose-constitution"

    text = cli("workflow", "info", "bugfix")
    assert text.exit_code == 0 and "fix-loop" in text.output and "compose.track.end" in text.output


def test_validate(cli: Callable[..., Result], tmp_path: Path) -> None:
    good = tmp_path / "good.yml"
    good.write_text("workflow: {id: good, name: G}\nsteps:\n  - {id: a, run: ls}\n")
    ok = cli("workflow", "validate", str(good), "--json")
    assert ok.exit_code == 0 and json.loads(ok.output)["valid"] is True

    bad = tmp_path / "bad.yml"
    bad.write_text("workflow: {id: bad, name: B}\nsteps:\n  - {id: a, prompt: '{{ x }}'}\n")
    res = cli("workflow", "validate", str(bad))
    assert res.exit_code == 1 and "unknown name 'x'" in res.output
    res_json = cli("workflow", "validate", str(bad), "--json")
    assert res_json.exit_code == 1 and json.loads(res_json.output)["valid"] is False


def test_add_remove(
    cli: Callable[..., Result], git_repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    src = tmp_path / "flow.yml"
    src.write_text("workflow: {id: flow, name: F}\nsteps:\n  - {id: a, run: ls}\n")
    monkeypatch.chdir(git_repo)
    assert cli("workflow", "add", str(src)).exit_code == 0
    listed = json.loads(cli("workflow", "list", "--json").output)
    assert any(w["id"] == "flow" and w["source"] == "repo" for w in listed)
    assert cli("workflow", "remove", "flow").exit_code == 0


def test_add_outside_repo(
    cli: Callable[..., Result], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    res = cli("workflow", "add", "x.yml")
    assert res.exit_code == 1 and "inside a git repo" in res.output
