"""The GitHub Copilot engine.

Runs the Copilot CLI as a process (``copilot --output-format=json``, prompt on stdin) with
the same skills, in the same worktree, as the Claude Code engine. Use it for one step, a
workflow, or every run::

    defaults:
      engine: copilot

Three things differ from Claude Code and are handled here:

- Copilot does not fill in a skill's ``$ARGUMENTS``, so a skill task is sent as the skill's
  own text with the arguments already in place.
- Copilot budgets in AI credits; ``max_cost_usd`` becomes ``--max-ai-credits`` at one cent a
  credit, and costs come back the same way.
- Tool rules are written ``shell(npm test)``, not ``Bash(npm test)``; rules in Claude Code's
  form are translated, so the same workflow runs on either engine.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from compose.engines.base import EngineOptions, EngineRun, EngineTask, Transcript
from compose.engines.copilot import install as installer
from compose.engines.copilot.cli import PERMISSION_FLAGS, CopilotOptions, CopilotRun
from compose.engines.copilot.mapping import credits_for
from compose.engines.registry import EngineError

DEFAULT_PERMISSION_MODE = "allow-all"
# compose's skills locate features through the compose CLI; headless runs can't ask
ALWAYS_ALLOWED = ["shell(compose:*)"]
EFFORTS = ("none", "minimal", "low", "medium", "high", "xhigh", "max")

# engine_options a workflow may set for Copilot (workflow, step or hook level)
ENGINE_OPTIONS = {
    "permission_mode": "permission mode: " + ", ".join(PERMISSION_FLAGS),
    "allowed_tools": "tools allowed without asking (list)",
    "disallowed_tools": "tools never allowed (list)",
    "allowed_urls": "URLs or domains Copilot may fetch without asking (list)",
    "add_dirs": "extra directories Copilot may access (list)",
    "cli_path": "path to a specific copilot executable",
}

# where a skill may live, in the order Copilot looks: the project, then the person
# (compose installs to the first)
SKILL_DIRS = (".github/skills", ".agents/skills", ".claude/skills")
PERSONAL_SKILL_DIRS = (".copilot/skills", ".agents/skills")
ARGUMENTS = "$ARGUMENTS"

# Claude Code tool names and the Copilot permission kind that covers each
_RULE = re.compile(r"(\w+)(?:\((.*)\))?", re.DOTALL)
_KINDS = {
    "Bash": "shell",
    "Write": "write",
    "Edit": "write",
    "MultiEdit": "write",
    "NotebookEdit": "write",
    "Read": "read",
}


def tool_rule(rule: str) -> str:
    """A tool rule in Copilot's form: ``Bash(npm test)`` becomes ``shell(npm test)``.
    Rules already in Copilot's form, and ones with no counterpart, pass through."""
    match = _RULE.fullmatch(rule)
    kind = _KINDS.get(match.group(1)) if match else None
    if match is None or kind is None:
        return rule
    return f"{kind}({match.group(2)})" if match.group(2) else kind


def skill_text(cwd: Path, name: str) -> str | None:
    """The instructions of an installed skill (its SKILL.md without the front matter)."""
    roots = [cwd / d for d in SKILL_DIRS] + [Path.home() / d for d in PERSONAL_SKILL_DIRS]
    for root in roots:
        file = root / name / "SKILL.md"
        if file.is_file():
            text = file.read_text(encoding="utf-8")
            if text.startswith("---"):
                _, _, rest = text[3:].partition("\n---")
                text = rest.partition("\n")[2] if rest else text
            return text.strip()
    return None


def by_name(task: EngineTask) -> str:
    """A skill asked for by name, as a person would type it, with what its arguments are."""
    said = f"`{task.args}`" if task.args else "nothing (it was given no arguments)"
    return f"{task.label}\n\nWhere that skill says `{ARGUMENTS}`, read {said}."


def prompt_for(task: EngineTask, cwd: Path) -> str:
    """A skill task is sent as the skill's own instructions with its arguments filled in.
    A skill compose can't find is asked for by name."""
    if task.kind != "skill":
        return task.text
    args = task.args or ""
    body = skill_text(cwd, task.text)
    if body is None:
        return by_name(task)
    if ARGUMENTS in body:
        body = body.replace(ARGUMENTS, args)
    elif args:
        body += f"\n\nARGUMENTS: {args}"
    return (
        f"Carry out the `{task.text}` skill, whose instructions follow. If they have you run"
        f" another skill, load it with the skill tool; `{ARGUMENTS}` in a skill stands for"
        " the arguments it is called with.\n\n" + body
    )


def _list(value: Any, name: str) -> list[str]:
    """A list of strings; surrounding spaces and empty entries are dropped (so
    ``"{{ inputs.tools | split(',') }}"`` works with an empty or spaced input)."""
    if isinstance(value, str):
        value = [value]
    if isinstance(value, list) and all(isinstance(v, str) for v in value):
        return [v.strip() for v in value if v.strip()]
    raise EngineError(f"engine_options.{name} must be a list of strings")


def _rules(value: Any, name: str) -> list[str]:
    return [tool_rule(rule) for rule in _list(value, name)]


def build_options(cwd: Path, options: EngineOptions) -> CopilotOptions:
    extra = dict(options.engine_options)
    unknown = sorted(set(extra) - set(ENGINE_OPTIONS))
    if unknown:
        known = ", ".join(sorted(ENGINE_OPTIONS))
        raise EngineError(f"unknown Copilot engine_options: {', '.join(unknown)} ({known})")
    mode = extra.get("permission_mode", DEFAULT_PERMISSION_MODE)
    if mode not in PERMISSION_FLAGS:
        raise EngineError(
            f"engine_options.permission_mode: {mode!r} (use {', '.join(PERMISSION_FLAGS)})"
        )
    effort = options.reasoning_effort
    if effort is not None and effort not in EFFORTS:
        raise EngineError(f"reasoning_effort {effort!r} is not one of {', '.join(EFFORTS)}")
    cap = options.max_cost_usd
    allowed = [*ALWAYS_ALLOWED, *_rules(extra.get("allowed_tools", []), "allowed_tools")]
    return CopilotOptions(
        cwd=cwd,
        permission_mode=mode,
        model=options.model,
        reasoning_effort=effort,
        max_ai_credits=None if cap is None else credits_for(cap),
        allowed_tools=list(dict.fromkeys(allowed)),
        disallowed_tools=_rules(extra.get("disallowed_tools", []), "disallowed_tools"),
        allowed_urls=_list(extra.get("allowed_urls", []), "allowed_urls"),
        add_dirs=_list(extra.get("add_dirs", []), "add_dirs"),
        cli_path=extra.get("cli_path"),
        env=dict(options.env),
    )


class CopilotEngine:
    name = "copilot"

    def start(self, task: EngineTask, cwd: Path, options: EngineOptions) -> EngineRun:
        return CopilotRun(
            prompt_for(task, cwd), build_options(cwd, options), Transcript(options.transcript)
        )

    def install(self, path: Path, *, worktree: bool = False) -> list[Path]:
        return installer.install(path, worktree=worktree)

    def check(self) -> list[str]:
        return installer.check()
