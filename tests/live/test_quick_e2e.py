"""Live end to end: `compose init` a toy repo, then run the built-in `quick` workflow on
Claude Code, once through the CLI and once through the API.

Run with: uv run pytest -m live tests/live/test_quick_e2e.py -s  (spends a few dollars at
most: each run is capped at MAX_COST_USD on Haiku)
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
import yaml
from fastapi.testclient import TestClient
from typer.testing import Result

from compose.api.app import create_app
from compose.core.home import Home
from compose.engines.claude.install import check
from compose.workflows import loader

pytestmark = pytest.mark.live

MODEL = "claude-haiku-5-5"
MAX_COST_USD = 3.0
TOOLS = "Bash(python3 -m unittest:*),Bash(python -m unittest:*)"
SPEC = (
    "A Python module slug.py with a function slugify(text) that lowercases the text, trims "
    "it and replaces runs of spaces with a single hyphen, plus test_slug.py using unittest."
)


@pytest.fixture(autouse=True)
def _ready() -> None:
    problems = check()
    if problems:
        pytest.skip("; ".join(problems))


@pytest.fixture
def capped_quick(tmp_path: Path) -> Path:
    """The built-in quick workflow on Haiku with a run-wide cost cap."""
    source = loader.resolve("quick", None).path
    data = yaml.safe_load(source.read_text())
    data["workflow"]["model"] = MODEL
    data["workflow"]["limits"] = {"max_cost_usd": MAX_COST_USD}
    path = tmp_path / "quick-capped.yml"
    path.write_text(yaml.safe_dump(data, sort_keys=False))
    return path


def check_run(detail: dict[str, Any]) -> None:
    assert detail["status"] == "completed", detail.get("error")
    engine_steps = [s for s in detail["steps"] if s["type"] in ("command", "prompt")]
    order = [s["step_id"] for s in engine_steps]
    assert order[:5] == ["specify", "plan", "tasks", "implement", "converge"], order
    for step in engine_steps:
        assert step["cost_usd"] > 0, step["step_id"]
        assert step["engine"] == "claude" and step["model"] == MODEL
    steps = {s["step_id"]: s for s in engine_steps}
    assert steps["implement"]["changes"]["files"] >= 2  # slug.py and test_slug.py at least
    open_tasks = [s for s in detail["steps"] if s["step_id"] == "open-tasks"]
    assert open_tasks and open_tasks[-1]["status"] in ("completed", "failed")
    totals = detail["totals"]
    leaves = [s for s in detail["steps"] if s["type"] in ("command", "prompt", "shell")]
    assert totals["cost_usd"] == pytest.approx(sum(s["cost_usd"] for s in leaves))
    assert totals["cost_usd"] <= MAX_COST_USD
    rounds = order.count("converge")
    print(f"\nconverge rounds: {rounds}, implement-gaps: {order.count('implement-gaps')}")
    worktree = Path(detail["worktree"])
    assert (worktree / "slug.py").exists()
    print(f"\n{detail['id']}: ${totals['cost_usd']:.4f}, {totals['changes']}")


def test_quick_through_cli_and_api(
    cli: Callable[..., Result],
    git_repo: Path,
    home: Home,
    monkeypatch: pytest.MonkeyPatch,
    capped_quick: Path,
) -> None:
    monkeypatch.chdir(git_repo)
    init = cli("init", "--engine", "claude", "--json")
    assert init.exit_code == 0, init.output

    started = time.monotonic()
    result = cli(
        "run", str(capped_quick), "-i", f"spec={SPEC}", "-i", f"allowed_tools={TOOLS}", "--json"
    )
    assert result.exit_code == 0, result.output
    detail = json.loads(result.output)
    check_run(detail)
    print(f"CLI run took {time.monotonic() - started:.0f}s")

    trace = json.loads(cli("trace", detail["id"], "--step", "implement", "--json").output)
    tools = {a["tool_name"] for a in trace["steps"][0]["actions"] if a["kind"] == "tool_call"}
    assert tools & {"Write", "Edit", "MultiEdit"}

    started = time.monotonic()
    with TestClient(create_app(home)) as client:
        repo = client.get("/repos").json()[0]["name"]
        created = client.post(
            f"/repos/{repo}/runs",
            json={
                "workflow": str(capped_quick),
                "inputs": {
                    "spec": SPEC.replace("slug", "slug2"),
                    "allowed_tools": TOOLS,
                    "converge": False,  # the CLI run covers converge
                },
            },
        )
        assert created.status_code == 202, created.text
        run_id = created.json()["run_id"]
        while True:
            api_detail = client.get(f"/runs/{run_id}").json()
            if api_detail["status"] not in ("created", "running"):
                break
            assert time.monotonic() - started < 1200, "API run took over 20 minutes"
            time.sleep(2)
    check_run_api(api_detail)
    print(f"API run took {time.monotonic() - started:.0f}s")


def check_run_api(detail: dict[str, Any]) -> None:
    assert detail["status"] == "completed", detail.get("error")
    engine_steps = [s for s in detail["steps"] if s["type"] in ("command", "prompt")]
    assert all(s["cost_usd"] > 0 for s in engine_steps)
    steps = {s["step_id"]: s for s in engine_steps}
    assert steps["implement"]["changes"]["files"] >= 1
    assert detail["totals"]["cost_usd"] <= MAX_COST_USD
    print(f"\n{detail['id']}: ${detail['totals']['cost_usd']:.4f}, {detail['totals']['changes']}")
