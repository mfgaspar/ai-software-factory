"""``compose run / status / resume / abort / trace / changes / cost`` over fake-engine runs."""

from __future__ import annotations

import json
import subprocess
import time
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner, Result

from compose.cli import runs
from compose.cli.app import app
from compose.core.db import open_database
from compose.core.home import Home, ensure_home
from compose.engines.base import Usage
from compose.engines.fake import Act, FakeEngine, Script, edit
from compose.engines.registry import EngineRegistry

WORKFLOW = """
workflow: {id: demo, name: Demo, version: 1.0.0}
inputs:
  spec: {type: string, required: true}
hooks:
  before_run:
    run: echo starting
    description: announce
  after_build:
    run: printf 'note\\n' > NOTES.md
    description: notes
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
    run: printf 'a\\nb\\n' > draft.txt
  - id: review
    type: gate
    message: "Ship it?"
    options: [approve, reject]
  - id: finish
    type: shell
    run: echo done >> draft.txt
"""


@pytest.fixture
def fake(monkeypatch: pytest.MonkeyPatch, compose_home: Path) -> FakeEngine:
    engine = FakeEngine(
        {
            "build a todo app": Script(
                [
                    Act(say="Writing the app."),
                    *edit("app.py", "print('hi')\nprint('bye')\n"),
                    Act(usage=Usage(input_tokens=1200, output_tokens=300, cost_usd=0.42, turns=2)),
                ]
            )
        }
    )
    monkeypatch.setattr(runs, "engine_registry", lambda: EngineRegistry({"fake": engine}))
    (compose_home / "config.yml").write_text("defaults: {engine: fake}\n")
    return engine


@pytest.fixture
def repo(cli: Callable[..., Result], git_repo: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    assert cli("repo", "add", str(git_repo)).exit_code == 0
    monkeypatch.chdir(git_repo)
    return git_repo


@pytest.fixture
def workflows(tmp_path: Path) -> Iterator[dict[str, Path]]:
    paths = {}
    for name, body in (("demo", WORKFLOW), ("gated", GATED)):
        path = tmp_path / f"{name}.yml"
        path.write_text(body)
        paths[name] = path
    yield paths


def as_json(result: Result) -> Any:
    assert result.output.strip(), result.output
    return json.loads(result.output)


def test_run_reports_steps_cost_and_changes(
    cli: Callable[..., Result], fake: FakeEngine, repo: Path, workflows: dict[str, Path]
) -> None:
    result = cli("run", str(workflows["demo"]), "-i", "spec=a todo app", "--json")
    assert result.exit_code == 0, result.output
    data = as_json(result)
    assert data["status"] == "completed"
    assert data["feature"] == "001-todo-app"
    assert data["waiting"] is None
    steps = {s["step_id"]: s for s in data["steps"]}
    assert list(steps) == ["build", "check"]
    build = steps["build"]
    assert build["cost_usd"] == pytest.approx(0.42)
    assert build["tokens"] == {"input": 1200, "output": 300, "cache_read": 0, "cache_write": 0}
    # the step wrote app.py; its after hook wrote NOTES.md; both count for the step
    assert build["changes"] == {"files": 2, "added": 3, "removed": 0}
    assert steps["check"]["changes"] == {"files": 1, "added": 1, "removed": 0}
    totals = data["totals"]
    assert totals["cost_usd"] == pytest.approx(0.42)
    assert totals["changes"] == {"files": 3, "added": 4, "removed": 0}
    assert data["started_at"].endswith("+00:00") and "T" in data["started_at"]

    text = cli("status", data["id"])
    assert text.exit_code == 0
    assert "build" in text.output and "$0.4200" in text.output and "+3 -0" in text.output

    events = Path(data["run_dir"], "log.jsonl").read_text().splitlines()
    started = [json.loads(e) for e in events if '"step_started"' in e]
    assert [(e["type"], e["step_type"]) for e in started] == [
        ("step_started", "prompt"),
        ("step_started", "shell"),
    ]


def test_foreground_progress(
    cli: Callable[..., Result], fake: FakeEngine, repo: Path, workflows: dict[str, Path]
) -> None:
    result = cli("run", str(workflows["demo"]), "-i", "spec=a todo app", "-v")
    assert result.exit_code == 0, result.output
    out = result.output
    assert "▸ build prompt" in out and "✓ build" in out and "$0.42" in out
    assert "» Writing the app." in out  # the model's commentary
    assert "✎ app.py" in out  # the files it writes, relative to the worktree
    assert "✓ Run completed" in out and "$0.42 · 3 files changed (+4 -0)" in out


def test_a_feature_run_commits_its_work_and_says_where(
    cli: Callable[..., Result], fake: FakeEngine, repo: Path, workflows: dict[str, Path]
) -> None:
    result = cli("run", str(workflows["demo"]), "-i", "spec=a todo app")
    assert result.exit_code == 0, result.output
    branch = "001-todo-app"
    log = subprocess.run(
        ["git", "log", "-1", "--format=%s", branch],
        cwd=repo,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.splitlines()
    assert log == [f"{branch}: Demo"]
    shown = subprocess.run(
        ["git", "show", "--name-only", "--format=", branch],
        cwd=repo,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.split()
    assert sorted(shown) == ["NOTES.md", "app.py"]  # the engine's own files stay out
    # the default branch is fast-forwarded, so the work is in the repo's own folder
    assert (repo / "app.py").is_file() and (repo / "NOTES.md").is_file()
    out = " ".join(result.output.split())
    assert f"The work is merged into main, in . (branch {branch})." in out


def test_a_feature_run_that_cannot_fast_forward_says_why(
    cli: Callable[..., Result], fake: FakeEngine, repo: Path, workflows: dict[str, Path]
) -> None:
    (repo / "app.py").write_text("mine\n")  # an untracked file the merge would overwrite
    result = cli("run", str(workflows["demo"]), "-i", "spec=a todo app")
    assert result.exit_code == 0, result.output
    branch = "001-todo-app"
    assert (repo / "app.py").read_text() == "mine\n"
    out = " ".join(result.output.split())
    assert f"The work is on branch {branch} (1 commit ahead of main)." in out
    assert f"git -C . diff main...{branch}" in out and f"git -C . merge {branch}" in out
    assert "Not merged into main:" in out


def test_features_merge_can_be_turned_off(
    cli: Callable[..., Result], fake: FakeEngine, repo: Path, workflows: dict[str, Path], home: Home
) -> None:
    with home.config_path.open("a") as handle:
        handle.write("\nfeatures:\n  merge: false\n")
    result = cli("run", str(workflows["demo"]), "-i", "spec=a todo app")
    assert result.exit_code == 0, result.output
    assert not (repo / "app.py").exists()
    out = " ".join(result.output.split())
    assert "The work is on branch 001-todo-app (1 commit ahead of main)." in out
    assert "Not merged" not in out


def test_a_paused_feature_run_commits_too_but_offers_no_merge(
    cli: Callable[..., Result], repo: Path, workflows: dict[str, Path]
) -> None:
    result = cli("run", str(workflows["gated"]), "-i", "spec=x", "--no-interactive")
    assert result.exit_code == runs.EXIT_PAUSED, result.output
    assert "1 commit ahead of main" in result.output and "merge" not in result.output


def test_trace_full_reads_each_steps_transcript_file(
    cli: Callable[..., Result], fake: FakeEngine, repo: Path, workflows: dict[str, Path]
) -> None:
    data = as_json(cli("run", str(workflows["demo"]), "-i", "spec=a todo app", "--json"))
    build = next(s for s in data["steps"] if s["step_id"] == "build")
    file = Path(data["run_dir"], "steps", f"{build['exec_id']}.transcript.jsonl")
    assert file.is_file()

    short = cli("trace", data["id"])
    assert short.exit_code == 0, short.output
    assert "transcript:" in short.output and ".transcript.j" in short.output

    full = as_json(cli("trace", data["id"], "--full", "--json"))
    step = next(s for s in full["steps"] if s["step_id"] == "build")
    kinds = [e["kind"] for e in step["transcript_entries"]]
    assert kinds[0] == "task" and kinds[-1] == "result"
    assert step["transcript_entries"][0]["prompt"] == "build a todo app"
    call = next(e for e in step["transcript_entries"] if e["kind"] == "tool_call")
    assert call["name"] == "Write" and call["input"] == {"file_path": "app.py"}
    shell = next(s for s in full["steps"] if s["step_id"] == "check")
    assert shell["transcript"] is None  # no engine, no transcript

    text = cli("trace", data["id"], "--full")
    assert "build a todo app" in text.output and "Writing the app." in text.output
    assert '"file_path": "app.py"' in text.output  # whole tool inputs


def test_gate_pause_and_resume(
    cli: Callable[..., Result], fake: FakeEngine, repo: Path, workflows: dict[str, Path]
) -> None:
    paused = cli("run", str(workflows["gated"]), "-i", "spec=gate me", "--json")
    assert paused.exit_code == runs.EXIT_PAUSED, paused.output
    data = as_json(paused)
    run_id = data["id"]
    assert data["status"] == "paused"
    assert data["waiting"]["step_id"] == "review"
    assert data["waiting"]["message"] == "Ship it?"
    assert data["waiting"]["options"] == ["approve", "reject"]
    assert (Path(data["worktree"]) / "draft.txt").read_text() == "a\nb\n"

    text = cli("status", run_id)
    assert f"compose resume {run_id} --choice <approve|reject>" in text.output

    listed = as_json(cli("status", "--json"))
    assert [(r["id"], r["status"], r["current_step_id"]) for r in listed] == [
        (run_id, "paused", "review")
    ]
    assert as_json(cli("status", "--status", "completed", "--json")) == []
    assert cli("status", "--status", "nope").exit_code == 2

    wrong = cli("resume", run_id, "--choice", "maybe", "--json")
    assert wrong.exit_code == runs.EXIT_PAUSED
    assert "invalid choice 'maybe'" in as_json(wrong)["error"]

    done = cli("resume", run_id, "--choice", "approve", "--json")
    assert done.exit_code == 0, done.output
    assert as_json(done)["status"] == "completed"

    again = cli("resume", run_id)
    assert again.exit_code == 1 and "only paused or failed runs" in again.output


def test_interactive_gate_and_inputs(
    cli: Callable[..., Result], fake: FakeEngine, repo: Path, workflows: dict[str, Path]
) -> None:
    runner = CliRunner()
    result = runner.invoke(
        app,
        ["run", str(workflows["gated"]), "--interactive"],
        input="asked spec\nmaybe\napprove\n",
    )
    assert result.exit_code == 0, result.output
    assert "Ship it?" in result.output
    assert result.output.count("Choose approve/reject") == 2  # asked again after 'maybe'
    assert "002" not in result.output and "001-asked-spec" in result.output


def test_input_errors(
    cli: Callable[..., Result],
    fake: FakeEngine,
    repo: Path,
    workflows: dict[str, Path],
    tmp_path: Path,
) -> None:
    missing = cli("run", str(workflows["gated"]), "--no-interactive")
    assert missing.exit_code == 1 and "Missing required input 'spec'" in missing.output
    unknown = cli("run", str(workflows["gated"]), "-i", "spec=x", "-i", "colour=red")
    assert unknown.exit_code == 1 and "Unknown input(s): colour" in unknown.output
    bad = cli("run", str(workflows["gated"]), "-i", "spec")
    assert bad.exit_code == 2 and "is not key=value" in bad.output
    nofile = cli("run", str(workflows["gated"]), "-i", "spec=@nowhere.md")
    assert nofile.exit_code == 2 and "cannot read" in nofile.output

    spec = tmp_path / "spec.md"
    spec.write_text("From a file\n")
    from_file = cli("run", str(workflows["gated"]), "-i", f"spec=@{spec}", "--json")
    assert as_json(from_file)["inputs"] == {"spec": "From a file\n"}
    assert as_json(from_file)["feature"] == "001-file"


def test_run_outside_a_registered_repo(
    cli: Callable[..., Result],
    fake: FakeEngine,
    tmp_path: Path,
    workflows: dict[str, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    result = cli("run", str(workflows["gated"]), "-i", "spec=x")
    assert result.exit_code == 1 and "Not inside a registered repo" in result.output
    assert cli("status", "run_nope").exit_code == 1


def test_trace(
    cli: Callable[..., Result], fake: FakeEngine, repo: Path, workflows: dict[str, Path]
) -> None:
    run_id = as_json(cli("run", str(workflows["demo"]), "-i", "spec=a todo app", "--json"))["id"]
    data = as_json(cli("trace", run_id, "--json"))
    assert [h["name"] for h in data["run_hooks"]] == ["announce"]
    assert data["run_hooks"][0]["actions"][0]["tool_name"] == "shell"
    build = data["steps"][0]
    assert [(a["kind"], a["tool_name"]) for a in build["actions"]] == [
        ("message", None),
        ("tool_call", "Write"),
        ("tool_result", None),
    ]
    hooks = {h["name"]: h for h in build["hooks"]}
    assert set(hooks) == {"compose.track.begin", "notes", "compose.track.end"}
    assert hooks["notes"]["files"] == [
        {"path": "NOTES.md", "old_path": None, "status": "A", "added": 1, "removed": 0}
    ]
    assert hooks["notes"]["actions"][0]["input"].startswith("printf")

    only = as_json(cli("trace", run_id, "--step", "check", "--json"))
    assert [s["step_id"] for s in only["steps"]] == ["check"] and only["run_hooks"] == []
    assert cli("trace", run_id, "--step", "nope").exit_code == 1

    text = cli("trace", run_id).output
    assert "→ Write" in text and "hook after_build notes completed" in text
    assert "hook before_run announce" in text
    assert "compose.track" not in text  # tracking itself only shows in --json


def test_changes(
    cli: Callable[..., Result], fake: FakeEngine, repo: Path, workflows: dict[str, Path]
) -> None:
    run_id = as_json(cli("run", str(workflows["demo"]), "-i", "spec=a todo app", "--json"))["id"]
    data = as_json(cli("changes", run_id, "--json"))
    steps = {s["step_id"]: s for s in data["steps"]}
    assert [f["path"] for f in steps["build"]["files"]] == ["NOTES.md", "app.py"]
    assert steps["build"]["summary"] == {"files": 2, "added": 3, "removed": 0}
    assert [h["name"] for h in steps["build"]["hooks"]] == ["notes"]
    assert steps["check"]["files"][0]["status"] == "M"
    assert data["totals"] == {"files": 3, "added": 4, "removed": 0}

    one = as_json(cli("changes", run_id, "--step", "check", "--json"))
    assert one["totals"] == {"files": 1, "added": 1, "removed": 0}

    text = cli("changes", run_id).output
    assert "app.py" in text and "3 files, +4 -0" in text


def test_cost(
    cli: Callable[..., Result],
    fake: FakeEngine,
    repo: Path,
    workflows: dict[str, Path],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first = as_json(cli("run", str(workflows["demo"]), "-i", "spec=a todo app", "--json"))
    second = as_json(cli("run", str(workflows["gated"]), "-i", "spec=other", "--json"))

    by_run = as_json(cli("cost", "--json"))
    assert by_run["by"] == "run" and by_run["filters"]["repo"] == repo.name
    labels = {g["key"]: g["label"] for g in by_run["groups"]}
    assert labels == {first["id"]: f"{first['id']} (demo)", second["id"]: f"{second['id']} (gated)"}
    assert by_run["total"]["cost_usd"] == pytest.approx(0.42)
    assert by_run["total"]["runs"] == 2

    by_step = as_json(cli("cost", "--run", first["id"], "--json"))
    assert by_step["by"] == "step"
    assert {g["key"]: g["cost_usd"] for g in by_step["groups"]} == {
        "before_run": 0.0,
        "build": pytest.approx(0.42),
        "check": 0.0,
    }

    by_feature = as_json(cli("cost", "--by", "feature", "--json"))
    assert sorted(g["label"] for g in by_feature["groups"]) == ["001-todo-app", "002-other"]
    one = as_json(cli("cost", "--feature", "002-other", "--by", "day", "--json"))
    assert one["total"]["cost_usd"] == 0 and one["total"]["changes"]["files"] == 1
    assert len(one["groups"]) == 1

    future = as_json(cli("cost", "--since", "2999-01-01", "--json"))
    assert future["groups"] == [] and future["total"]["runs"] == 0
    assert cli("cost", "--by", "week").exit_code == 2
    assert cli("cost", "--since", "yesterday").exit_code == 2
    assert cli("cost", "--feature", "999-none").exit_code == 1

    text = cli("cost").output
    assert "total" in text and "$0.4200" in text

    monkeypatch.chdir(tmp_path)  # outside any repo: everything
    assert as_json(cli("cost", "--by", "repo", "--json"))["groups"][0]["label"] == repo.name
    assert cli("cost", "--feature", "001-todo-app").exit_code == 1


def test_abort(
    cli: Callable[..., Result], fake: FakeEngine, repo: Path, workflows: dict[str, Path]
) -> None:
    paused = as_json(cli("run", str(workflows["gated"]), "-i", "spec=x", "--json"))
    result = cli("abort", paused["id"], "--json")
    assert result.exit_code == 0 and as_json(result)["status"] == "aborted"
    assert cli("resume", paused["id"]).exit_code == 1
    again = cli("abort", paused["id"])
    assert again.exit_code == 1 and "nothing to abort" in again.output

    fake.scripts = {"build boom": Script(fail="model refused")}
    failed = cli("run", str(workflows["demo"]), "-i", "spec=boom", "--json")
    assert failed.exit_code == 1 and as_json(failed)["status"] == "failed"
    assert "Retry with" in cli("status", as_json(failed)["id"]).output
    assert as_json(cli("abort", as_json(failed)["id"], "--json"))["status"] == "aborted"


def _wait_for(run_id: str, status: str, timeout: float = 30.0) -> dict[str, Any]:
    home = ensure_home()
    deadline = time.monotonic() + timeout
    while True:
        db = open_database(home)
        try:
            row = db.execute("SELECT status, error FROM runs WHERE id = ?", (run_id,))
            current = dict(row.fetchone())
        finally:
            db.close()
        if current["status"] == status:
            return current
        if time.monotonic() > deadline:
            log = home.run_dir(run_id) / "process.log"
            raise AssertionError(f"{run_id} is {current}; process log:\n{log.read_text()}")
        time.sleep(0.2)


def test_detached_run_and_resume(
    cli: Callable[..., Result], repo: Path, workflows: dict[str, Path], compose_home: Path
) -> None:
    # A real background process: only shell steps, so no engine is needed.
    (compose_home / "config.yml").write_text("defaults: {engine: fake}\n")
    started = cli("run", str(workflows["gated"]), "-i", "spec=background", "--detach", "--json")
    assert started.exit_code == 0, started.output
    data = as_json(started)
    assert data["status"] == "created" and data["pid"] > 0
    _wait_for(data["id"], "paused")

    resumed = cli("resume", data["id"], "--choice", "approve", "--detach")
    assert resumed.exit_code == 0 and "in the background" in resumed.output
    _wait_for(data["id"], "completed")
    detail = as_json(cli("status", data["id"], "--json"))
    assert [s["status"] for s in detail["steps"]] == ["completed"] * 3
    assert detail["totals"]["changes"] == {"files": 2, "added": 3, "removed": 0}
