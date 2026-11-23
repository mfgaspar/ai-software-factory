"""Desktop notifications: the OS command, the switches, and that nothing breaks a run."""

from __future__ import annotations

import subprocess
from typing import Any

import pytest

from compose import notify
from compose.core.models import RunStatus
from tests.unit.runner_helpers import Env


@pytest.fixture
def sent(monkeypatch: pytest.MonkeyPatch) -> list[list[str]]:
    monkeypatch.delenv("COMPOSE_NOTIFY", raising=False)
    calls: list[list[str]] = []

    def run(argv: list[str], **_: Any) -> subprocess.CompletedProcess[str]:
        calls.append(argv)
        return subprocess.CompletedProcess(argv, 0)

    monkeypatch.setattr(notify.subprocess, "run", run)
    return calls


def test_macos_uses_osascript_with_escaped_strings() -> None:
    argv = notify.command('say "hi"', 'a \\ "b"', platform="darwin")
    assert argv == [
        "osascript",
        "-e",
        'display notification "a \\\\ \\"b\\"" with title "say \\"hi\\""',
    ]


def test_linux_uses_notify_send_when_there(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(notify.shutil, "which", lambda name: "/usr/bin/notify-send")
    assert notify.command("compose", "done", platform="linux") == [
        "notify-send",
        "--app-name=compose",
        "compose",
        "done",
    ]
    monkeypatch.setattr(notify.shutil, "which", lambda name: None)
    assert notify.command("compose", "done", platform="linux") is None


def test_windows_uses_a_powershell_toast_with_escaped_text() -> None:
    argv = notify.command("compose", "it's <done> & ok", platform="win32")
    assert argv is not None and argv[:2] == ["powershell", "-NoProfile"]
    assert "it''s &lt;done&gt; &amp; ok" in argv[-1]


def test_sends_when_on(sent: list[list[str]], monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(notify, "command", lambda title, message: ["echo", title, message])
    notify.notify("clarity on wc-lite completed")
    assert sent == [["echo", "compose", "clarity on wc-lite completed"]]


@pytest.mark.parametrize("value", ["0", "false", "no", "OFF"])
def test_env_switch_turns_it_off(
    sent: list[list[str]], monkeypatch: pytest.MonkeyPatch, value: str
) -> None:
    monkeypatch.setenv("COMPOSE_NOTIFY", value)
    notify.notify("x")
    assert sent == []


def test_config_switch_turns_it_off(sent: list[list[str]]) -> None:
    notify.notify("x", configured=False)
    assert sent == []


@pytest.mark.parametrize(
    "error", [subprocess.TimeoutExpired("osascript", 5), OSError("no such file"), RuntimeError()]
)
def test_failures_never_raise(monkeypatch: pytest.MonkeyPatch, error: Exception) -> None:
    monkeypatch.delenv("COMPOSE_NOTIFY", raising=False)
    monkeypatch.setattr(notify, "command", lambda title, message: ["osascript"])

    def boom(*_: Any, **__: Any) -> None:
        raise error

    monkeypatch.setattr(notify.subprocess, "run", boom)
    notify.notify("x")  # no exception


@pytest.fixture
def notices(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    seen: list[str] = []
    monkeypatch.setattr(notify, "notify", lambda message, **_: seen.append(message))
    return seen


async def test_a_completed_run_notifies_once(env: Env, notices: list[str]) -> None:
    wf = env.workflow("workflow: {id: hi, name: Hi}\nsteps: [{id: say, run: 'echo hi'}]\n")
    run = await env.runner().start(env.repo, wf)
    assert run.status is RunStatus.COMPLETED, run.error
    assert (
        len(notices) == 1 and notices[0].startswith("hi on ") and notices[0].endswith(" completed")
    )


async def test_a_gate_pause_says_what_it_waits_for(env: Env, notices: list[str]) -> None:
    wf = env.workflow(
        "workflow: {id: g, name: G}\nsteps: [{id: review, type: gate, message: 'Read the plan'}]\n"
    )
    run = await env.runner().start(env.repo, wf)
    assert run.status is RunStatus.PAUSED
    assert notices == [notices[0]] and "is waiting at gate review: Read the plan" in notices[0]


async def test_a_failure_names_the_step(env: Env, notices: list[str]) -> None:
    wf = env.workflow("workflow: {id: f, name: F}\nsteps: [{id: boom, run: 'exit 3'}]\n")
    run = await env.runner().start(env.repo, wf)
    assert run.status is RunStatus.FAILED
    assert notices[-1].endswith("failed at boom")


async def test_a_called_workflow_does_not_notify(env: Env, notices: list[str]) -> None:
    child_dir = env.repo_path / ".compose" / "workflows" / "child"
    child_dir.mkdir(parents=True)
    (child_dir / "workflow.yml").write_text(
        "workflow: {id: child, name: Child}\nsteps: [{id: ok, type: gate, message: 'child gate'}]\n"
    )
    wf = env.workflow(
        "workflow: {id: parent, name: Parent}\n"
        "steps: [{id: call, type: workflow, workflow: child}]\n"
    )
    runner = env.runner()
    run = await runner.start(env.repo, wf)
    assert run.status is RunStatus.PAUSED, run.error
    assert len(notices) == 1 and notices[0].startswith("parent on ")
    run = await runner.resume(run.id, choice="approve")
    assert run.status is RunStatus.COMPLETED, run.error
    assert len(notices) == 2 and notices[1].endswith(" completed")
