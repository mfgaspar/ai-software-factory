from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from compose.core import store
from compose.core.models import FileStatus, HookExec, HookKind, Run, RunStatus, StepExec
from compose.engines.base import EngineOptions, EngineTask, Usage
from compose.engines.fake import Act, Script, edit
from compose.runner.state import RunFiles
from compose.tracking import aggregate, journal
from compose.tracking.journal import FileChange
from tests.unit.runner_helpers import Env


def changes_of(env: Env, exec_id: str) -> list[FileChange]:
    row = store.get(env.db, StepExec, exec_id)
    assert row is not None
    files = RunFiles(env.home.run_dir(row.run_id))
    return sorted(journal.read_changes(files, exec_id), key=lambda c: c.path)


def hooks_of(env: Env, exec_id: str) -> list[HookExec]:
    return store.select(env.db, HookExec, "step_exec_id = ?", (exec_id,), "started_at, id")


WINDOW = """
workflow: {id: window, name: Window}
hooks:
  before_build:
    run: printf 'a\\nb\\n' > setup.txt
    description: setup
  after_build:
    - prompt: write the docs
      description: docs
    - run: printf 'x\\n' >> README.md
      description: touch-readme
outputs:
  files: {value: "{{ steps.build.changes.files }}"}
  added: {value: "{{ steps.build.changes.added }}"}
steps:
  - id: build
    prompt: build it
"""


async def test_step_and_hooks_changes_add_up(env: Env) -> None:
    env.fake.scripts = {
        "build it": Script(edit("src/app.py", "one\ntwo\nthree\n", cost=0.5)),
        "write the docs": Script(edit("docs/guide.md", "g\n", cost=0.25)),
    }
    run = await env.runner().start(env.repo, env.workflow(WINDOW))
    assert run.status is RunStatus.COMPLETED, run.error

    build = env.exec_of(run, "build")[0]
    assert (build.files_changed, build.lines_added, build.lines_removed) == (4, 7, 0)
    assert build.cost_usd == pytest.approx(0.75)
    assert run.outputs == {"files": 4, "added": 7}

    window = [(c.path, c.status, c.added) for c in changes_of(env, build.id) if not c.hook_exec_id]
    assert window == [
        ("README.md", FileStatus.MODIFIED, 1),
        ("docs/guide.md", FileStatus.ADDED, 1),
        ("setup.txt", FileStatus.ADDED, 2),
        ("src/app.py", FileStatus.ADDED, 3),
    ]
    by_hook = {
        h.name: (h.files_changed, h.lines_added, h.cost_usd)
        for h in hooks_of(env, build.id)
        if h.kind is not HookKind.BUILTIN
    }
    assert by_hook == {"setup": (1, 2, 0.0), "docs": (1, 1, 0.25), "touch-readme": (1, 1, 0.0)}
    hook_rows = [c for c in changes_of(env, build.id) if c.hook_exec_id]
    assert sorted(c.path for c in hook_rows) == ["README.md", "docs/guide.md", "setup.txt"]
    hook_lines = sum(added for _, added, _ in by_hook.values())
    assert build.lines_added - hook_lines == 3  # the step itself wrote src/app.py

    record = json.loads((env.files(run).steps_dir / f"{build.id}.json").read_text())
    assert record["files_changed"] == 4
    assert [c["path"] for c in record["changes"]] == [
        "README.md",
        "docs/guide.md",
        "setup.txt",
        "src/app.py",
    ]
    docs = next(h for h in record["hooks"] if h["name"] == "docs")
    assert docs["changes"][0]["path"] == "docs/guide.md"
    assert docs["actions"] == 2  # tool call and tool result
    assert any(a["tool_name"] == "Write" for a in record["actions"])


async def test_changes_are_per_step(env: Env) -> None:
    wf = """
workflow: {id: twosteps, name: Two}
steps:
  - {id: first, run: "printf '1\\n2\\n' > a.txt"}
  - {id: second, run: "printf '1\\n' > a.txt && rm README.md"}
"""
    run = await env.runner().start(env.repo, env.workflow(wf))
    first, second = env.exec_of(run, "first")[0], env.exec_of(run, "second")[0]
    assert [(c.path, c.status, c.added, c.removed) for c in changes_of(env, first.id)] == [
        ("a.txt", FileStatus.ADDED, 2, 0)
    ]
    assert [(c.path, c.status, c.added, c.removed) for c in changes_of(env, second.id)] == [
        ("README.md", FileStatus.DELETED, 0, 1),
        ("a.txt", FileStatus.MODIFIED, 0, 1),
    ]
    run_total = aggregate.totals(env.db, "run", run_id=run.id)[0]
    assert run_total.files_changed == 3  # a.txt counts in each step that changed it
    assert (run_total.lines_added, run_total.lines_removed) == (2, 2)


async def test_failed_step_is_still_recorded(env: Env) -> None:
    wf = """
workflow: {id: failing, name: Failing}
steps:
  - {id: half, run: "echo partial > partial.txt && exit 1"}
"""
    run = await env.runner().start(env.repo, env.workflow(wf))
    assert run.status is RunStatus.FAILED
    half = env.exec_of(run, "half")[0]
    assert [c.path for c in changes_of(env, half.id)] == ["partial.txt"]
    assert half.files_changed == 1


async def test_tracking_off_records_no_changes(env: Env) -> None:
    wf = """
workflow: {id: untracked, name: Untracked, tracking: false}
steps:
  - {id: work, run: "echo x > x.txt"}
"""
    run = await env.runner().start(env.repo, env.workflow(wf))
    work = env.exec_of(run, "work")[0]
    assert changes_of(env, work.id) == [] and work.files_changed == 0
    assert hooks_of(env, work.id) == []


async def test_fan_out_changes_belong_to_the_fan_out(env: Env) -> None:
    def script(task: EngineTask, cwd: Path, options: EngineOptions) -> Script:
        name = task.text.split()[-1]
        return Script(edit(f"{name}.txt", f"{name}\n", cost=0.1 if name == "a" else 0.2))

    env.fake.scripts = script
    wf = """
workflow: {id: fan, name: Fan}
steps:
  - id: spread
    type: fan-out
    items: "{{ ['a', 'b'] }}"
    max_concurrency: 2
    step: {id: each, prompt: "write {{ item }}"}
"""
    run = await env.runner().start(env.repo, env.workflow(wf))
    assert run.status is RunStatus.COMPLETED, run.error
    spread = env.exec_of(run, "spread")[0]
    items = env.exec_of(run, "each")
    assert sorted(i.cost_usd for i in items) == pytest.approx([0.1, 0.2])
    assert all(changes_of(env, i.id) == [] and i.files_changed == 0 for i in items)
    assert [c.path for c in changes_of(env, spread.id)] == ["a.txt", "b.txt"]
    assert spread.files_changed == 2 and spread.cost_usd == pytest.approx(0.3)

    total = aggregate.grand_total(env.db, run_id=run.id)
    assert total.cost_usd == pytest.approx(0.3)
    assert total.files_changed == 2
    by_step = {t.key: t for t in aggregate.totals(env.db, "step", run_id=run.id)}
    assert by_step["each"].cost_usd == pytest.approx(0.3) and by_step["each"].files_changed == 0
    assert by_step["spread"].files_changed == 2 and by_step["spread"].cost_usd == 0


async def test_gate_window_spans_the_pause(env: Env) -> None:
    wf = """
workflow: {id: gated, name: Gated}
hooks:
  before_review: {run: "echo before > before.txt"}
steps:
  - {id: review, type: gate, message: "OK?"}
"""
    runner = env.runner()
    run = await runner.start(env.repo, env.workflow(wf))
    assert run.status is RunStatus.PAUSED
    (env.worktree(run) / "manual.txt").write_text("edited by hand\n")
    run = await runner.resume(run.id, choice="approve")
    review = env.exec_of(run, "review")[0]
    window = [c.path for c in changes_of(env, review.id) if not c.hook_exec_id]
    assert window == ["before.txt", "manual.txt"]
    assert env.files(run).read_state().snapshots == {}


# ------------------------------------------------------------------- aggregates


async def _two_runs(env: Env) -> tuple[Run, Run]:
    env.fake.default = Script([Act(usage=Usage(100, 10, 5, 2, cost_usd=0.4, turns=1))])
    child = env.workflow(
        """
        workflow: {id: child, name: Child}
        steps:
          - {id: inner, prompt: inner work}
        """,
        name="child",
    )
    env.repo_path.joinpath(".compose", "workflows", "child").mkdir(parents=True)
    env.repo_path.joinpath(".compose", "workflows", "child", "workflow.yml").write_text(
        child.path.read_text()
    )
    wf = env.workflow(
        """
        workflow: {id: parent, name: Parent}
        hooks:
          before_run: {prompt: warm up}
        steps:
          - {id: outer, prompt: outer work}
          - {id: call, type: workflow, workflow: child}
          - {id: write, run: "echo hi > hi.txt"}
        """
    )
    runner = env.runner()
    first = await runner.start(env.repo, wf, feature="001-first")
    second = await runner.start(env.repo, wf, feature="002-second")
    return first, second


async def test_aggregates(env: Env) -> None:
    first, second = await _two_runs(env)
    assert first.status is RunStatus.COMPLETED, first.error

    run_total = aggregate.totals(env.db, "run", run_id=first.id)
    assert len(run_total) == 1
    t = run_total[0]
    assert t.key == first.id
    assert t.cost_usd == pytest.approx(1.2)  # warm up + outer + inner (child run)
    assert (t.input_tokens, t.output_tokens, t.cache_read_tokens, t.cache_write_tokens) == (
        300,
        30,
        15,
        6,
    )
    assert (t.files_changed, t.lines_added, t.runs) == (1, 1, 1)

    steps = {s.key: s.cost_usd for s in aggregate.totals(env.db, "step", run_id=first.id)}
    assert steps == pytest.approx({"before_run": 0.4, "outer": 0.4, "inner": 0.4, "write": 0})

    features = aggregate.totals(env.db, "feature", repo_id=env.repo.id)
    assert [f.cost_usd for f in features] == pytest.approx([1.2, 1.2])
    assert {f.key for f in features} == {first.feature_id, second.feature_id}

    repo = aggregate.totals(env.db, "repo")
    assert len(repo) == 1 and repo[0].runs == 2 and repo[0].cost_usd == pytest.approx(2.4)
    # hi.txt once: the second feature starts from the merged first one, and rewrites it unchanged
    assert repo[0].files_changed == 1
    today = datetime.now(UTC).date().isoformat()
    assert [(d.key, d.runs) for d in aggregate.totals(env.db, "day")] == [(today, 2)]


async def test_aggregate_time_filters(env: Env) -> None:
    await _two_runs(env)
    now = datetime.now(UTC)
    assert aggregate.grand_total(env.db, since=now + timedelta(minutes=1)).runs == 0
    assert aggregate.grand_total(env.db, until=now - timedelta(hours=1)).cost_usd == 0
    window = aggregate.grand_total(
        env.db, since=now - timedelta(hours=1), until=now + timedelta(minutes=1)
    )
    assert window.cost_usd == pytest.approx(2.4)
    naive_local = datetime.now() - timedelta(hours=30)
    assert aggregate.grand_total(env.db, since=naive_local).runs == 2
    assert aggregate.grand_total(env.db, feature_id="nope").to_json()["cost_usd"] == 0
