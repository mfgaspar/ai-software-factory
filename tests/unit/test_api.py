"""The HTTP API, over fake-engine runs executing in the server."""

from __future__ import annotations

import json
import time
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from typer.testing import Result

from compose.api import events as run_events
from compose.api.app import create_app
from compose.cli import runs as cli_runs
from compose.core import store
from compose.core.home import Home
from compose.core.models import Repo, Run, RunStatus
from compose.engines.base import Usage
from compose.engines.fake import Act, FakeEngine, Script, edit
from compose.engines.registry import EngineRegistry

DEMO = """
workflow: {id: demo, name: Demo, version: 1.0.0}
inputs:
  spec: {type: string, required: true}
steps:
  - id: build
    prompt: "build {{ inputs.spec }}"
  - id: check
    type: shell
    run: printf 'ok\\n' >> app.py
"""

GATED = """
workflow: {id: gated, name: Gated, version: 1.0.0}
inputs:
  spec: {type: string, required: true}
steps:
  - id: draft
    type: shell
    run: printf 'a\\n' > draft.txt
  - id: review
    type: gate
    message: "Ship it?"
    options: [approve, reject]
  - id: finish
    type: shell
    run: echo done >> draft.txt
"""


@pytest.fixture
def fake(compose_home: Path) -> FakeEngine:
    (compose_home / "config.yml").write_text("defaults: {engine: fake}\n")
    return FakeEngine(
        {
            "build todo": Script(
                [
                    Act(say="Writing it."),
                    *edit("app.py", "print('hi')\n"),
                    Act(usage=Usage(input_tokens=100, output_tokens=40, cost_usd=0.3, turns=1)),
                ]
            ),
            "build slow": Script([Act(say="thinking"), Act(sleep=30), Act(say="never")]),
        }
    )


@pytest.fixture
def client(home: Home, fake: FakeEngine) -> Iterator[TestClient]:
    app = create_app(home, engines=EngineRegistry({"fake": fake}))
    with TestClient(app) as c:
        yield c


@pytest.fixture
def repo(client: TestClient, git_repo: Path) -> str:
    for name, body in (("demo", DEMO), ("gated", GATED)):
        folder = git_repo / ".compose" / "workflows" / name
        folder.mkdir(parents=True)
        (folder / "workflow.yml").write_text(body)
    response = client.post("/repos", json={"path": str(git_repo), "name": "app"})
    assert response.status_code == 201, response.text
    return "app"


def ok(response: Any, status: int = 200) -> Any:
    assert response.status_code == status, response.text
    return response.json()


def wait(client: TestClient, run_id: str, *statuses: str, timeout: float = 20) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    while True:
        detail: dict[str, Any] = ok(client.get(f"/runs/{run_id}"))
        if detail["status"] in statuses:
            return detail
        assert time.monotonic() < deadline, detail
        time.sleep(0.05)


def start(client: TestClient, repo: str, workflow: str, **body: Any) -> str:
    data = ok(client.post(f"/repos/{repo}/runs", json={"workflow": workflow, **body}), 202)
    return str(data["run_id"])


def test_health_and_openapi(client: TestClient) -> None:
    health = ok(client.get("/health"))
    assert health["status"] == "ok" and health["active_runs"] == []
    paths = ok(client.get("/openapi.json"))["paths"]
    for path in (
        "/repos",
        "/repos/{repo}/runs",
        "/runs/{run_id}/events",
        "/runs/{run_id}/gates/{step_id}",
        "/costs",
    ):
        assert path in paths


def test_repos(client: TestClient, git_repo: Path, bare_remote: str) -> None:
    added = ok(client.post("/repos", json={"path": str(git_repo)}), 201)
    assert added["name"] == "repo" and added["default_branch"] == "main"
    assert client.post("/repos", json={"path": str(git_repo)}).status_code == 400
    assert client.post("/repos", json={}).status_code == 422
    both = {"path": str(git_repo), "url": bare_remote}
    assert client.post("/repos", json=both).status_code == 422
    assert client.post("/repos", json={"url": "not a url"}).status_code == 422

    cloned = ok(client.post("/repos", json={"url": bare_remote, "name": "remote"}), 201)
    assert Path(cloned["path"]).is_dir()
    assert [r["name"] for r in ok(client.get("/repos"))] == ["remote", "repo"]
    assert ok(client.get("/repos/remote"))["id"] == cloned["id"]
    assert client.get("/repos/nope").status_code == 404

    assert ok(client.delete("/repos/remote?delete_clone=true")) == {"removed": "remote"}
    assert not Path(cloned["path"]).exists()
    assert client.delete("/repos/remote").status_code == 404


def test_workflows(client: TestClient, repo: str) -> None:
    listed = {w["id"]: w for w in ok(client.get(f"/repos/{repo}/workflows"))}
    assert listed["demo"]["source"] == "repo" and listed["demo"]["name"] == "Demo"
    info = ok(client.get(f"/repos/{repo}/workflows/gated"))
    assert [s["id"] for s in info["definition"]["steps"]] == ["draft", "review", "finish"]
    assert {h["name"] for h in info["effective_hooks"]} >= {"compose.track.begin"}
    assert client.get(f"/repos/{repo}/workflows/nope").status_code == 404


def test_run_lifecycle_and_reports(client: TestClient, repo: str, git_repo: Path) -> None:
    run_id = start(client, repo, "demo", inputs={"spec": "todo"})
    detail = wait(client, run_id, "completed")
    assert detail["feature"] == "001-todo"
    assert [s["step_id"] for s in detail["steps"]] == ["build", "check"]
    assert detail["totals"]["cost_usd"] == pytest.approx(0.3)
    assert detail["totals"]["changes"] == {
        "files": 2,
        "added": 2,
        "removed": 0,
    }  # app.py counts once per step

    build = detail["steps"][0]
    record = ok(client.get(f"/runs/{run_id}/steps/{build['exec_id']}"))
    assert record["cost_usd"] == pytest.approx(0.3)
    assert [c["path"] for c in record["changes"]] == ["app.py"]
    assert {h["name"] for h in record["hooks"]} == {"compose.track.begin", "compose.track.end"}
    assert client.get(f"/runs/{run_id}/steps/step_nope").status_code == 404

    trace = ok(client.get(f"/runs/{run_id}/trace?step=build"))
    assert [a["kind"] for a in trace["steps"][0]["actions"]] == [
        "message",
        "tool_call",
        "tool_result",
    ]
    changes = ok(client.get(f"/runs/{run_id}/changes"))
    assert [s["step_id"] for s in changes["steps"]] == ["build", "check"]

    costs = ok(client.get(f"/costs?run={run_id}&group_by=step"))
    assert {g["key"]: g["cost_usd"] for g in costs["groups"]} == {
        "build": pytest.approx(0.3),
        "check": 0.0,
    }
    by_feature = ok(client.get(f"/costs?repo={repo}&group_by=feature"))
    assert by_feature["groups"][0]["label"] == "001-todo"
    assert ok(client.get("/costs?from=2999-01-01"))["groups"] == []
    assert client.get("/costs?group_by=week").status_code == 422
    assert client.get("/costs?feature=001-todo").status_code == 422
    assert client.get(f"/costs?repo={repo}&feature=999-x").status_code == 404

    listed = ok(client.get(f"/runs?repo={repo}&status=completed"))
    assert [r["id"] for r in listed] == [run_id]
    assert ok(client.get("/runs?status=paused")) == []
    assert ok(client.get(f"/runs?repo={repo}&feature=001-todo"))[0]["id"] == run_id
    assert client.get("/runs?status=bogus").status_code == 422
    assert client.get("/runs/run_nope").status_code == 404

    features = ok(client.get(f"/repos/{repo}/features"))
    assert features == [
        {"name": "001-todo", "has_branch": True, "has_specs_folder": False, "runs": 1}
    ]
    feature = ok(client.get(f"/repos/{repo}/features/001-todo"))
    assert feature["worktree"] and Path(feature["worktree"], "app.py").exists()
    assert [r["id"] for r in feature["runs"]] == [run_id]
    assert feature["totals"]["cost_usd"] == pytest.approx(0.3)
    assert client.get(f"/repos/{repo}/features/002-nope").status_code == 404
    assert client.get(f"/repos/{repo}/features/bad").status_code == 400


def test_start_errors(client: TestClient, repo: str) -> None:
    missing = client.post(f"/repos/{repo}/runs", json={"workflow": "demo"})
    assert missing.status_code == 422 and "Missing required input" in missing.json()["detail"]
    assert client.post(f"/repos/{repo}/runs", json={"workflow": "nope"}).status_code == 404
    assert client.post("/repos/nope/runs", json={"workflow": "demo"}).status_code == 404
    bad_feature = {"workflow": "demo", "inputs": {"spec": "x"}, "feature": "bad"}
    assert client.post(f"/repos/{repo}/runs", json=bad_feature).status_code == 409


def test_gates(client: TestClient, repo: str) -> None:
    run_id = start(client, repo, "gated", inputs={"spec": "gate"})
    paused = wait(client, run_id, "paused")
    assert paused["waiting"]["step_id"] == "review"
    assert paused["waiting"]["options"] == ["approve", "reject"]

    gate = f"/runs/{run_id}/gates"
    assert client.post(f"{gate}/draft", json={"choice": "approve"}).status_code == 409
    assert client.post(f"{gate}/review", json={"choice": "maybe"}).status_code == 422
    ok(client.post(f"{gate}/review", json={"choice": "approve"}), 202)
    done = wait(client, run_id, "completed")
    assert [s["status"] for s in done["steps"]] == ["completed"] * 3
    assert client.post(f"{gate}/review", json={"choice": "approve"}).status_code == 409
    resumed = client.post(f"/runs/{run_id}/resume", json={})
    assert resumed.status_code == 409 and "only paused or failed" in resumed.json()["detail"]

    second = start(client, repo, "gated", inputs={"spec": "again"})
    wait(client, second, "paused")
    ok(client.post(f"/runs/{second}/resume", json={"choice": "approve"}), 202)
    wait(client, second, "completed")


def test_busy_feature_and_abort(client: TestClient, repo: str) -> None:
    run_id = start(client, repo, "demo", inputs={"spec": "slow"})
    running = wait(client, run_id, "running")
    assert ok(client.get("/health"))["active_runs"] == [run_id]
    busy = client.post(
        f"/repos/{repo}/runs",
        json={"workflow": "demo", "inputs": {"spec": "x"}, "feature": running["feature"]},
    )
    assert busy.status_code == 409 and "already has an active run" in busy.json()["detail"]

    assert ok(client.post(f"/runs/{run_id}/abort"))["status"] == "running"  # requested
    aborted = wait(client, run_id, "aborted")
    assert aborted["steps"][0]["status"] in ("failed", "aborted")
    assert client.post(f"/runs/{run_id}/abort").status_code == 409


def test_events_pages_and_stream(client: TestClient, repo: str) -> None:
    run_id = start(client, repo, "gated", inputs={"spec": "events"})
    wait(client, run_id, "paused")
    page = ok(client.get(f"/runs/{run_id}/events"))
    kinds = [e["type"] for e in page["events"]]
    assert kinds[0] == "run_created" and kinds[-1] == "run_paused"
    assert [e["seq"] for e in page["events"]] == list(range(1, len(kinds) + 1))
    assert page["next"] == len(kinds)
    later = ok(client.get(f"/runs/{run_id}/events?after=2&limit=2"))
    assert [e["seq"] for e in later["events"]] == [3, 4]

    streamed = sse(client, f"/runs/{run_id}/events?stream=true")
    assert [e["event"] for e in streamed][-2:] == ["run_paused", "end"]
    assert json.loads(streamed[-1]["data"])["status"] == "paused"
    resumed = sse(client, f"/runs/{run_id}/events?stream=true", {"Last-Event-ID": "3"})
    assert resumed[0]["id"] == "4"

    # live: decide the gate, then follow the run to the end
    ok(client.post(f"/runs/{run_id}/gates/review", json={"choice": "approve"}), 202)
    live = sse(client, f"/runs/{run_id}/events?stream=true&after={page['next']}")
    kinds = [e["event"] for e in live]
    assert "gate_decided" in kinds and kinds[-2:] == ["run_finished", "end"]
    assert client.get("/runs/run_nope/events").status_code == 404


def sse(
    client: TestClient, url: str, headers: dict[str, str] | None = None
) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    with client.stream("GET", url, headers=headers or {}) as response:
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        current: dict[str, str] = {}
        for line in response.iter_lines():
            if not line:
                if current:
                    out.append(current)
                current = {}
            elif not line.startswith(":"):
                key, _, value = line.partition(": ")
                current[key] = value
    return out


async def test_stream_waits_for_new_events(tmp_path: Path, db: Any) -> None:
    log = tmp_path / "log.jsonl"
    store.insert(db, Repo(id="r", name="r", path="/x"))
    store.insert(
        db,
        Run(
            id="run_1",
            repo_id="r",
            workflow_id="w",
            workflow_version="1.0.0",
            status=RunStatus.RUNNING,
        ),
    )
    log.write_text('{"type": "a"}\n{"type": "b"')  # the second line is still being written
    gen = run_events.stream(db, "run_1", log, poll=0.01)
    first = await gen.__anext__()
    assert first.startswith("id: 1\nevent: a\n")
    with log.open("a") as fh:
        fh.write("}\n")
    assert (await gen.__anext__()).startswith("id: 2\nevent: b\n")
    db.execute("UPDATE runs SET status = 'completed' WHERE id = 'run_1'")
    assert (await gen.__anext__()).startswith("event: end")


def test_bearer_token(home: Home, fake: FakeEngine, compose_home: Path) -> None:
    (compose_home / "config.yml").write_text(
        "defaults: {engine: fake}\nserver: {token: s3cret-test}\n"
    )
    with TestClient(create_app(home, engines=EngineRegistry({"fake": fake}))) as client:
        assert client.get("/health").status_code == 200
        assert client.get("/repos").status_code == 401
        wrong = {"Authorization": "Bearer nope"}
        assert client.get("/repos", headers=wrong).status_code == 401
        right = {"Authorization": "Bearer s3cret-test"}
        assert client.get("/repos", headers=right).status_code == 200


def test_cli_and_api_share_runs(
    client: TestClient,
    repo: str,
    cli: Callable[..., Result],
    fake: FakeEngine,
    git_repo: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(cli_runs, "engine_registry", lambda: EngineRegistry({"fake": fake}))
    monkeypatch.chdir(git_repo)
    paused = cli("run", "gated", "-i", "spec=from cli", "--json")
    assert paused.exit_code == cli_runs.EXIT_PAUSED, paused.output
    run_id = json.loads(paused.output)["id"]

    seen = ok(client.get(f"/runs/{run_id}"))
    assert seen["status"] == "paused" and seen["waiting"]["step_id"] == "review"
    ok(client.post(f"/runs/{run_id}/gates/review", json={"choice": "approve"}), 202)
    wait(client, run_id, "completed")
    assert json.loads(cli("status", run_id, "--json").output)["status"] == "completed"


def test_shutdown_leaves_runs_resumable(
    home: Home, fake: FakeEngine, git_repo: Path, db: Any
) -> None:
    app = create_app(home, engines=EngineRegistry({"fake": fake}))
    with TestClient(app) as client:
        folder = git_repo / ".compose" / "workflows" / "demo"
        folder.mkdir(parents=True)
        (folder / "workflow.yml").write_text(DEMO)
        ok(client.post("/repos", json={"path": str(git_repo)}), 201)
        run_id = start(client, "repo", "demo", inputs={"spec": "slow"})
        wait(client, run_id, "running")
    row = db.execute("SELECT status, error FROM runs WHERE id = ?", (run_id,)).fetchone()
    assert row[0] == "failed" and "stopped unexpectedly" in row[1]

    fake.scripts = {"build slow": Script([Act(say="quick this time")])}
    with TestClient(create_app(home, engines=EngineRegistry({"fake": fake}))) as client:
        ok(client.post(f"/runs/{run_id}/resume", json={}), 202)
        steps = wait(client, run_id, "completed")["steps"]
        builds = [(s["attempt"], s["status"]) for s in steps if s["step_id"] == "build"]
        assert builds == [(1, "failed"), (2, "completed")]


def test_serve_command(
    cli: Callable[..., Result], monkeypatch: pytest.MonkeyPatch, compose_home: Path
) -> None:
    import uvicorn

    calls: list[dict[str, Any]] = []
    monkeypatch.setattr(uvicorn, "run", lambda app, **kw: calls.append({"app": app, **kw}))
    assert cli("serve").exit_code == 0
    assert (calls[0]["host"], calls[0]["port"]) == ("127.0.0.1", 8765)

    open_bind = cli("serve", "--host", "0.0.0.0", "--port", "9000")
    assert open_bind.exit_code == 0 and "without a token" in open_bind.output
    assert (calls[1]["host"], calls[1]["port"]) == ("0.0.0.0", 9000)
