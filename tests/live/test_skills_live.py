"""Live smoke test of the compose skills on Claude Code: specify, then plan.

Run with: uv run pytest -m live tests/live/test_skills_live.py  (spends some cents)
"""

from __future__ import annotations

import pytest

from compose.core.config import Config, DefaultsConfig
from compose.core.models import RunStatus
from compose.engines.claude.install import check
from compose.engines.registry import default_registry
from compose.runner.runner import Runner
from compose.tracking import journal
from tests.unit.runner_helpers import Env

pytestmark = pytest.mark.live

WORKFLOW = """
workflow: {id: spec-plan, name: Spec and plan, model: claude-haiku-5-5}
inputs:
  spec: {type: string, required: true}
steps:
  - id: specify
    command: compose-specify
    input: {args: "{{ inputs.spec }}"}
    limits: {max_cost_usd: 1.5}
  - id: plan
    command: compose-plan
    input: {args: "Python 3.12 command-line tool, standard library only, pytest for tests"}
    limits: {max_cost_usd: 1.5}
"""


@pytest.fixture(autouse=True)
def _ready() -> None:
    problems = check()
    if problems:
        pytest.skip("; ".join(problems))


async def test_specify_then_plan(env: Env) -> None:
    runner = Runner(
        env.db,
        env.home,
        engines=default_registry(),
        config=Config(defaults=DefaultsConfig(engine="claude")),
    )
    run = await runner.start(
        env.repo,
        env.workflow(WORKFLOW),
        {"spec": "A command-line tool that counts the words in a text file"},
    )
    assert run.status is RunStatus.COMPLETED, run.error

    worktree = env.worktree(run)
    feature_dirs = sorted((worktree / "specs").iterdir())
    assert len(feature_dirs) == 1  # the skill reused the run's feature, no second one
    feature = feature_dirs[0]
    assert feature.name.startswith("001-")
    spec = (feature / "spec.md").read_text()
    plan = (feature / "plan.md").read_text()
    assert "## Requirements" in spec and "FR-001" in spec
    assert "[FEATURE TITLE]" not in spec and "[FEATURE TITLE]" not in plan
    assert "## Technical context" in plan
    assert (feature / "checklists" / "requirements.md").exists()

    specify, plan_step = env.exec_of(run, "specify")[0], env.exec_of(run, "plan")[0]
    assert specify.cost_usd > 0 and plan_step.cost_usd > 0
    assert specify.files_changed >= 2 and plan_step.files_changed >= 1
    # compose's installed skills are not counted as changes
    paths = [
        c.path for s in (specify, plan_step) for c in journal.read_changes(env.files(run), s.id)
    ]
    assert paths and not any(p.startswith((".claude/", ".compose/templates/")) for p in paths)
