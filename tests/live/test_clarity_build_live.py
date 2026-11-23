"""Live end to end: `compose clarity` then `compose build` on Claude Code.

Run with: uv run pytest -m live tests/live/test_clarity_build_live.py -s
(real Claude on Sonnet; each clarity run is capped at RUN_CAP_USD, so at most a few tens of
dollars in the worst case, usually much less)

1. `compose clarity docs/ --mode auto` through the CLI: the run completes with FAIL, the
   questions file has setup and gap questions, nothing is confirmed and nothing is merged.
2. A mixed run through the API: every pending question is answered with its recommendation
   (`confirm` for reviews, `approve` from the named approver for approvals) until the run
   completes with PASS. The default branch then has `.clarity/` and a stamped constitution,
   and `POST /repos/{repo}/builds` passes the pre-run check (the build is aborted at once).

The built-in workflows are copied and capped (model and cost) for these tests, so the real
ones stay untouched.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
import yaml
from fastapi.testclient import TestClient
from typer.testing import Result

from compose.api.app import create_app
from compose.clarity import constitution, fingerprint, questions
from compose.core.home import Home
from compose.engines.claude.install import check
from compose.workflows import loader

pytestmark = pytest.mark.live

MODEL = "claude-sonnet-5-5"
RUN_CAP_USD = 12.0  # whole clarity run
DRAFT_CAP_USD = 5.0
APPLY_CAP_USD = 2.5
MAX_RUNS = 3  # mixed: clarity runs started (a later one only to apply approvals)
MAX_PAUSES = 6  # mixed: answer batches in all
RUN_TIMEOUT_S = 45 * 60
ANSWERER = "compose-test"

BRIEF = """\
# wc-lite

Writers want a quick word count for Markdown drafts without opening an editor.

- Users: one person, the author, on their own laptop.
- `wc-lite FILE` prints the number of words in FILE, ignoring Markdown syntax.
- Must count a 10 MB file in under a second. Python 3.11, standard library only.
- Out of scope: PDFs, a GUI, a network service, stored data, accounts.

Clarity scope for this sample: keep the foundation minimal. Only the problem and the
requirements are mandatory; every other document can be left out of the mandatory set.
There are no approvers and no sign-offs are needed.
"""


@pytest.fixture(autouse=True)
def _ready() -> None:
    problems = check()
    if problems:
        pytest.skip("; ".join(problems))


@pytest.fixture
def capped_builtins(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """The built-in workflows, with the clarity ones on Sonnet and cost-capped."""
    target = tmp_path / "builtins"
    shutil.copytree(loader.BUILTIN_DIR, target)
    for workflow_id in ("clarity", "clarity-validate"):
        path = target / workflow_id / "workflow.yml"
        data = yaml.safe_load(path.read_text())
        data["workflow"]["model"] = MODEL
        data["workflow"]["limits"] = {"max_cost_usd": RUN_CAP_USD}
        caps = {"draft": DRAFT_CAP_USD, "apply": APPLY_CAP_USD}
        for step in _walk(data["steps"]):
            if step.get("id") in caps:
                step["limits"] = {"max_cost_usd": caps[step["id"]]}
        path.write_text(yaml.safe_dump(data, sort_keys=False))
    monkeypatch.setattr(loader, "BUILTIN_DIR", target)
    return target


def _walk(steps: list[dict[str, Any]]) -> list[dict[str, Any]]:
    found = []
    for step in steps:
        found.append(step)
        for key in ("steps", "then", "else"):
            found.extend(_walk(step.get(key) or []))
    return found


@pytest.fixture
def project(
    cli: Callable[..., Result],
    git_repo: Path,
    home: Home,
    monkeypatch: pytest.MonkeyPatch,
    capped_builtins: Path,
) -> Path:
    """A tiny repo with `compose init` done and committed, and a one-page brief in docs/."""
    home.config_path.write_text(yaml.safe_dump({"defaults": {"model": MODEL}}))
    monkeypatch.chdir(git_repo)
    init = cli("init", "--engine", "claude", "--json")
    assert init.exit_code == 0, init.output
    (git_repo / "docs").mkdir()
    (git_repo / "docs" / "brief.md").write_text(BRIEF)
    git(git_repo, "add", "-A")
    git(git_repo, "commit", "-q", "-m", "compose init and a brief")
    return git_repo


def git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=repo, check=True, capture_output=True, text=True
    ).stdout.strip()


def on_main(repo: Path, path: str) -> bool:
    return bool(git(repo, "ls-tree", "--name-only", "main", "--", path))


def questions_file(status: dict[str, Any]) -> Path:
    assert status["worktree"], status
    return Path(status["worktree"]) / ".clarity" / questions.QUESTIONS_FILE


# ------------------------------------------------------------------ 1. auto, CLI


def test_auto_drafts_and_merges_nothing(cli: Callable[..., Result], project: Path) -> None:
    head = git(project, "rev-parse", "main")
    started = time.monotonic()
    result = cli("clarity", "docs/", "--mode", "auto", "--json")
    assert result.exit_code == 0, result.output
    detail = json.loads(result.output)
    assert detail["status"] == "completed", detail.get("error")
    print(
        f"\nauto run {detail['id']}: ${detail['totals']['cost_usd']:.2f},"
        f" {time.monotonic() - started:.0f}s"
    )
    ran = [s["step_id"] for s in detail["steps"]]
    assert "draft" in ran and "apply" not in ran and "questions" not in ran, ran

    status = json.loads(cli("clarity", "status", "--json").output)
    assert status["started"] and status["verdict"]["result"] == "FAIL", status["verdict"]
    documents = status["documents"]
    assert documents, status
    for path in ("goal/problem.md", "goal/requirements.md"):
        assert documents.get(path) == "draft", (path, documents)
    confirmed = {p: s for p, s in documents.items() if s in ("complete", "n/a")}
    assert confirmed == {}, confirmed  # auto never confirms nor marks N/A

    kinds = {q.kind for q in questions.load(questions_file(status)) if q.is_pending}
    assert {"setup", "gap"} <= kinds, kinds

    assert git(project, "rev-parse", "main") == head  # nothing merged
    assert not on_main(project, ".clarity")
    assert git(project, "rev-parse", "clarity") != head  # but committed on the clarity branch
    assert not status["build"]["ok"]  # clarity started and hasn't passed: builds refused


# ------------------------------------------------------------------ 2. mixed, API


def answer_for(q: dict[str, Any]) -> str:
    options = q.get("options") or []
    if q["kind"] == "approval":
        return "approve"
    if q["kind"] == "review" and ("confirm" in options or q.get("free_text", True)):
        return "confirm"
    if q.get("recommended"):
        return str(q["recommended"])
    if options:
        return str(options[0])
    return "Take the simplest choice consistent with the brief; nothing more is required."


def answer_all(client: TestClient, repo: str, *, resume: bool) -> dict[str, Any] | None:
    """Answer every pending question; approvals first, each by its approver. Returns the
    last response (the one that may resume the run), or None when nothing was pending."""
    pending = client.get(f"/repos/{repo}/clarity/questions").json()
    batches: dict[str, dict[str, str]] = {}
    for q in pending:
        by = q.get("approver") if q["kind"] == "approval" else ANSWERER
        assert by, q
        batches.setdefault(by, {})[q["id"]] = answer_for(q)
    print(f"answering {[(q['id'], q['kind'], answer_for(q)) for q in pending]}")
    ordered = sorted(batches.items(), key=lambda item: item[0] == ANSWERER)
    last = None
    for index, (by, answers) in enumerate(ordered):
        final = index == len(ordered) - 1
        response = client.post(
            f"/repos/{repo}/clarity/answers",
            json={"answers": answers, "by": by, "resume": resume and final},
        )
        assert response.status_code == 200, response.text
        last = response.json()
    return last


def wait(client: TestClient, run_id: str) -> dict[str, Any]:
    started = time.monotonic()
    while True:
        detail = client.get(f"/runs/{run_id}").json()
        if detail["status"] not in ("created", "running"):
            return detail
        assert time.monotonic() - started < RUN_TIMEOUT_S, f"{run_id} is still running"
        time.sleep(3)


def test_mixed_through_api_passes_and_unlocks_builds(home: Home, project: Path) -> None:
    total = 0.0
    with TestClient(create_app(home)) as client:
        repo = client.get("/repos").json()[0]["name"]
        status: dict[str, Any] = {}
        pauses = 0
        for _ in range(MAX_RUNS):
            created = client.post(f"/repos/{repo}/clarity", json={"sources": ["docs/"]})
            assert created.status_code == 202, created.text
            run_id = created.json()["run_id"]
            assert created.json()["warnings"] == []
            detail = wait(client, run_id)
            while detail["status"] == "paused":
                pauses += 1
                assert pauses <= MAX_PAUSES, "too many question rounds"
                waiting = detail["waiting"]
                assert waiting and waiting["questions"], waiting
                answered = answer_all(client, repo, resume=True)
                assert answered and answered["resumed_run"] == run_id, answered
                detail = wait(client, run_id)
            assert detail["status"] == "completed", detail.get("error")
            total += detail["totals"]["cost_usd"]
            print(f"\nmixed run {run_id}: ${detail['totals']['cost_usd']:.2f}")
            status = client.get(f"/repos/{repo}/clarity").json()
            if status["verdict"]["result"] == "PASS":
                break
            # only approvals of absent approvers may be left: answer them, then run again
            left = client.get(f"/repos/{repo}/clarity/questions").json()
            assert left and all(q["kind"] == "approval" for q in left), (status, left)
            answer_all(client, repo, resume=False)
        print(f"clarity total: ${total:.2f}")

        assert status["verdict"]["result"] == "PASS", status
        assert status["verdict"]["current"] and status["constitution"]["current"], status
        assert on_main(project, ".clarity")
        fp = fingerprint.of_ref(project, "main")
        assert constitution.read_ref(project, "main") == fp  # stamped and merged
        assert status["build"] == {"ok": True, "problems": [], "warnings": []}

        build = client.post(
            f"/repos/{repo}/builds", json={"spec": "Print the word count of a file."}
        )
        assert build.status_code == 202, build.text  # the pre-run check let it through
        assert build.json()["warnings"] == []
        build_id = build.json()["run_id"]
        aborted = client.post(f"/runs/{build_id}/abort")
        assert aborted.status_code == 200, aborted.text
        assert wait(client, build_id)["status"] in ("aborted", "failed")
