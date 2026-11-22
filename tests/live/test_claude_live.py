"""Live tests against real Claude Code. Run with: uv run pytest -m live tests/live

They spend a few cents on a small model and need Claude Code signed in.
"""

from __future__ import annotations

import pytest

from compose.core import store
from compose.core.config import Config, DefaultsConfig
from compose.core.models import Action, FileChange, RunStatus
from compose.engines.claude.install import check
from compose.engines.registry import default_registry
from compose.runner.runner import Runner
from tests.unit.runner_helpers import Env

pytestmark = pytest.mark.live

MODEL = "claude-haiku-5-5"

WORKFLOW = f"""
workflow: {{id: live, name: Live, model: {MODEL}}}
steps:
  - id: write
    prompt: >-
      Create a file named hello.txt in the current directory containing exactly the
      text "hi" followed by a newline. Do nothing else and do not ask questions.
    limits: {{max_turns: 6, max_cost_usd: 0.5}}
"""


@pytest.fixture(autouse=True)
def _ready() -> None:
    problems = check()
    if problems:
        pytest.skip("; ".join(problems))


async def test_prompt_step_on_claude_code(env: Env) -> None:
    runner = Runner(
        env.db,
        env.home,
        engines=default_registry(),
        config=Config(defaults=DefaultsConfig(engine="claude")),
        on_event=env.events.append,
    )
    run = await runner.start(env.repo, env.workflow(WORKFLOW), feature="001-live")
    assert run.status is RunStatus.COMPLETED, run.error

    step = env.exec_of(run, "write")[0]
    assert step.engine == "claude" and step.session_id
    assert step.cost_usd > 0 and step.output_tokens > 0 and (step.turns or 0) >= 1
    assert (env.worktree(run) / "hello.txt").read_text().strip() == "hi"

    changes = store.select(env.db, FileChange, "step_exec_id = ?", (step.id,))
    assert [(c.path, c.added) for c in changes] == [("hello.txt", 1)]
    actions = store.select(env.db, Action, "step_exec_id = ?", (step.id,), "seq")
    assert any(a.kind == "tool_call" and a.tool_name in ("Write", "Bash") for a in actions)
    assert any(a.kind == "tool_result" for a in actions)
