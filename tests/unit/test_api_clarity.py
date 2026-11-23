"""The clarity and build routes, over fake-engine runs executing in the server."""

from __future__ import annotations

import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from compose.api.app import create_app
from compose.core.home import Home
from compose.engines.fake import FakeEngine
from compose.engines.registry import EngineRegistry
from compose.repos import git
from tests.unit.clarity_helpers import foundation, skills

FEATURE = """
workflow: {id: feat, name: Feat, version: 1.0.0}
inputs:
  spec: {type: string, required: true}
steps:
  - {id: build, type: shell, run: echo built}
"""


@pytest.fixture
def fake(compose_home: Path) -> FakeEngine:
    (compose_home / "config.yml").write_text("defaults: {engine: fake, workflow: feat}\n")
    return FakeEngine(skills())


@pytest.fixture
def client(home: Home, fake: FakeEngine) -> Iterator[TestClient]:
    app = create_app(home, engines=EngineRegistry({"fake": fake}))
    with TestClient(app) as c:
        yield c


@pytest.fixture
def repo(client: TestClient, git_repo: Path) -> str:
    folder = git_repo / ".compose" / "workflows" / "feat"
    folder.mkdir(parents=True)
    (folder / "workflow.yml").write_text(FEATURE)
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


def wait_asked(client: TestClient, run_id: str, qid: str, timeout: float = 20) -> dict[str, Any]:
    """Wait until the run is paused asking ``qid``."""
    deadline = time.monotonic() + timeout
    while True:
        detail = wait(client, run_id, "paused", timeout=timeout)
        asked = [q["id"] for q in (detail["waiting"] or {}).get("questions") or []]
        if qid in asked:
            return detail
        assert time.monotonic() < deadline, detail
        time.sleep(0.05)


def test_a_full_mixed_run(client: TestClient, repo: str, git_repo: Path) -> None:
    main = git.rev_parse(git_repo, "main")
    brief = ok(client.post(f"/repos/{repo}/clarity", json={"sources": ["docs/prd.md"]}), 202)
    assert brief["workflow_id"] == "clarity" and brief["warnings"] == []
    run_id = brief["run_id"]

    detail = wait(client, run_id, "paused")
    assert [q["id"] for q in detail["waiting"]["questions"]] == ["Q-001"]
    assert detail["inputs"] == {"sources": "docs/prd.md", "mode": "mixed"}
    assert [q["id"] for q in ok(client.get(f"/repos/{repo}/clarity/questions"))] == ["Q-001"]

    answered = ok(
        client.post(f"/repos/{repo}/clarity/answers", json={"answers": {"Q-001": "3"}, "by": "pat"})
    )
    assert answered == {"recorded": ["Q-001"], "resumed_run": run_id}
    detail = wait_asked(client, run_id, "Q-002")  # apply raised the review question
    assert detail["status"] == "paused"
    answered = ok(
        client.post(
            f"/repos/{repo}/clarity/answers",
            json={"answers": {"Q-002": "confirm"}, "by": "pat"},
        )
    )
    assert answered["resumed_run"] == run_id
    wait(client, run_id, "completed")

    status = ok(client.get(f"/repos/{repo}/clarity"))
    assert status["verdict"]["result"] == "PASS" and status["verdict"]["current"] is True
    assert status["questions"]["pending"] == 0
    assert status["build"]["ok"] is True
    assert git.rev_parse(git_repo, "main") != main
    assert git.rev_parse(git_repo, "main") == git.rev_parse(git_repo, "clarity")
    assert ok(client.post(f"/repos/{repo}/clarity/merge")) == {"merged": True}


def test_the_answers_endpoint_validates(client: TestClient, repo: str) -> None:
    run_id = ok(client.post(f"/repos/{repo}/clarity", json={}), 202)["run_id"]
    wait(client, run_id, "paused")
    bad = client.post(
        f"/repos/{repo}/clarity/answers",
        json={"answers": {"Q-001": "3", "Q-404": "x"}, "by": "pat"},
    )
    assert bad.status_code == 422, bad.text
    assert "Q-404: no such question" in bad.json()["detail"]
    assert [q["id"] for q in ok(client.get(f"/repos/{repo}/clarity/questions"))] == ["Q-001"]
    empty = client.post(f"/repos/{repo}/clarity/answers", json={"answers": {}, "by": "pat"})
    assert empty.status_code == 422
    kept = ok(
        client.post(
            f"/repos/{repo}/clarity/answers",
            json={"answers": {"Q-001": "3"}, "by": "pat", "resume": False},
        )
    )
    assert kept == {"recorded": ["Q-001"], "resumed_run": None}
    assert ok(client.get(f"/runs/{run_id}"))["status"] == "paused"


def test_interactive_gives_422(client: TestClient, repo: str) -> None:
    response = client.post(f"/repos/{repo}/clarity", json={"mode": "interactive"})
    assert response.status_code == 422
    assert "Claude Code session" in response.text


def test_one_active_clarity_run(client: TestClient, repo: str) -> None:
    run_id = ok(client.post(f"/repos/{repo}/clarity", json={}), 202)["run_id"]
    wait(client, run_id, "paused")
    again = client.post(f"/repos/{repo}/clarity/validate")
    assert again.status_code == 409 and run_id in again.json()["detail"]


def test_builds_refused_with_problems(client: TestClient, repo: str, git_repo: Path) -> None:
    git.git(git_repo, "branch", "clarity")
    response = client.post(f"/repos/{repo}/builds", json={"spec": "a todo app"})
    assert response.status_code == 409, response.text
    body = response.json()
    assert body["problems"] == [
        {
            "message": "Clarity is in progress on branch `clarity` and hasn't passed yet.",
            "fix": "compose clarity",
        }
    ]
    assert ok(client.get("/runs")) == []
    merge = client.post(f"/repos/{repo}/clarity/merge")
    assert merge.status_code == 409
    assert merge.json()["pending_reason"] == "no PASS verdict is recorded"


def test_builds_start_with_warnings(client: TestClient, repo: str) -> None:
    brief = ok(client.post(f"/repos/{repo}/builds", json={"spec": "a todo app"}), 202)
    assert brief["workflow_id"] == "feat" and brief["feature"] == "001-todo-app"
    assert "No clarity foundation" in brief["warnings"][0]
    detail = wait(client, brief["run_id"], "completed")
    assert detail["inputs"] == {"spec": "a todo app"}
    runs = ok(client.post(f"/repos/{repo}/runs", json={"inputs": {"spec": "more"}}), 202)
    assert "No clarity foundation" in runs["warnings"][0]


def test_builds_on_a_current_pass(client: TestClient, repo: str, git_repo: Path) -> None:
    foundation(git_repo)
    brief = ok(client.post(f"/repos/{repo}/builds", json={"spec": "a todo app"}), 202)
    assert brief["warnings"] == []
    wait(client, brief["run_id"], "completed")
