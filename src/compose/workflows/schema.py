"""Workflow definition schema (``workflow.yml``).

See ``docs/workflow-reference.md`` for the semantics of every field.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from enum import StrEnum
from typing import Annotated, Any, ClassVar, Literal

from pydantic import (
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

from compose.workflows import expressions

SCHEMA_VERSION: Literal["1.0"] = "1.0"
ID_RE = r"^[a-z0-9](?:[a-z0-9-]*[a-z0-9])?$"
STEP_ID_RE = r"^[A-Za-z0-9_][A-Za-z0-9_-]*$"
INPUT_NAME_RE = r"^[A-Za-z_][A-Za-z0-9_-]*$"
VERSION_RE = r"^\d+\.\d+\.\d+$"
RESERVED_STEP_IDS = frozenset({"run", "step"})  # would clash with before_run / before_step
EXPRESSION_ROOTS = frozenset({"inputs", "steps", "context", "item", "fan_in"})
REJECT = "reject"


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


# --------------------------------------------------------------------------- common


class Limits(_Model):
    """Spending caps. On a step they apply to that step; on the workflow, to the run."""

    max_cost_usd: float | None = Field(default=None, gt=0)
    max_turns: int | None = Field(default=None, ge=1)


class InputType(StrEnum):
    STRING = "string"
    NUMBER = "number"
    BOOLEAN = "boolean"


class InputSpec(_Model):
    type: InputType = InputType.STRING
    required: bool = False
    default: str | int | float | bool | None = None
    prompt: str | None = None
    description: str | None = None
    enum: list[str | int | float | bool] | None = None

    @model_validator(mode="after")
    def _check_default(self) -> InputSpec:
        if self.default is not None:
            coerce_input(self, self.default)
        if self.enum is not None:
            self.enum = [coerce_input(self, v, check_enum=False) for v in self.enum]
        return self


_TRUE = {"true", "1", "yes", "y", "on"}
_FALSE = {"false", "0", "no", "n", "off"}


def coerce_input(
    spec: InputSpec, value: Any, *, check_enum: bool = True
) -> str | int | float | bool:
    """Coerce a raw value (often a CLI string) to the input's type."""
    result: str | int | float | bool
    if spec.type is InputType.BOOLEAN:
        if isinstance(value, bool):
            result = value
        elif str(value).strip().lower() in _TRUE:
            result = True
        elif str(value).strip().lower() in _FALSE:
            result = False
        else:
            raise ValueError(f"{value!r} is not a boolean (use true/false)")
    elif spec.type is InputType.NUMBER:
        if isinstance(value, bool):
            raise ValueError(f"{value!r} is not a number")
        if isinstance(value, int | float):
            result = value
        else:
            text = str(value).strip()
            try:
                result = int(text)
            except ValueError:
                try:
                    result = float(text)
                except ValueError:
                    raise ValueError(f"{value!r} is not a number") from None
    else:
        result = value if isinstance(value, str) else str(value)
    if check_enum and spec.enum is not None and result not in spec.enum:
        allowed = ", ".join(str(v) for v in spec.enum)
        raise ValueError(f"{result!r} is not one of: {allowed}")
    return result


class OutputSpec(_Model):
    value: str
    description: str | None = None


class EngineSettings(_Model):
    """Engine choice for engine steps and hooks; unset fields inherit from the workflow."""

    engine: str | None = None
    model: str | None = None
    reasoning_effort: str | None = None
    engine_options: dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------- steps


class BaseStep(_Model):
    TEMPLATE_FIELDS: ClassVar[tuple[str, ...]] = ()
    CONDITION_FIELDS: ClassVar[tuple[str, ...]] = ()

    id: str = Field(pattern=STEP_ID_RE)
    name: str | None = None
    description: str | None = None
    continue_on_error: bool = False
    timeout: float | None = Field(default=None, gt=0, description="Seconds.")

    @field_validator("id")
    @classmethod
    def _not_reserved(cls, value: str) -> str:
        if value in RESERVED_STEP_IDS:
            raise ValueError(f"step id {value!r} is reserved")
        return value

    @property
    def kind(self) -> str:
        """The step type (``command``, ``gate``, ``fan-out``, ...)."""
        return str(getattr(self, "type"))  # noqa: B009 - declared on each subclass

    def children(self) -> Iterator[tuple[str, list[Step]]]:
        """Nested step lists, labelled (e.g. ``"then"``)."""
        return iter(())

    def template_strings(self) -> Iterator[tuple[str, str, bool]]:
        """(field label, text, is_bare_condition) for every expression-bearing field."""
        for name in self.TEMPLATE_FIELDS:
            value = getattr(self, name)
            if isinstance(value, str):
                yield name, value, False
            elif isinstance(value, dict):
                for key, item in value.items():
                    if isinstance(item, str):
                        yield f"{name}.{key}", item, False
        for name in self.CONDITION_FIELDS:
            value = getattr(self, name)
            if isinstance(value, str):
                yield name, value, True


class CommandInput(_Model):
    args: str | None = None


class CommandStep(BaseStep, EngineSettings):
    """Run a skill on the engine."""

    TEMPLATE_FIELDS: ClassVar[tuple[str, ...]] = ("args",)

    type: Literal["command"] = "command"
    command: str = Field(min_length=1)
    input: CommandInput = Field(default_factory=CommandInput)
    limits: Limits = Field(default_factory=Limits)

    @property
    def args(self) -> str | None:
        return self.input.args


class PromptStep(BaseStep, EngineSettings):
    """Send an inline prompt to the engine."""

    TEMPLATE_FIELDS: ClassVar[tuple[str, ...]] = ("prompt",)

    type: Literal["prompt"] = "prompt"
    prompt: str = Field(min_length=1)
    limits: Limits = Field(default_factory=Limits)


class ShellStep(BaseStep):
    """Run a shell command in the feature worktree."""

    TEMPLATE_FIELDS: ClassVar[tuple[str, ...]] = ("run", "env")

    type: Literal["shell"] = "shell"
    run: str = Field(min_length=1)
    env: dict[str, str] = Field(default_factory=dict)
    strict: bool = False
    output_format: Literal["text", "json"] = "text"
    capture: bool = True
    capture_max_bytes: int = Field(default=1_000_000, ge=1)

    @model_validator(mode="after")
    def _strict(self) -> ShellStep:
        if self.strict and ("{{" in self.run or "}}" in self.run):
            raise ValueError("strict shell steps may not use {{ }} in 'run'; pass values via env")
        return self


class GateStep(BaseStep):
    """Ask a human to choose. Choosing ``reject`` triggers ``on_reject``."""

    TEMPLATE_FIELDS: ClassVar[tuple[str, ...]] = ("message",)

    type: Literal["gate"] = "gate"
    message: str = Field(min_length=1)
    options: list[str] = Field(default_factory=lambda: ["approve", REJECT], min_length=2)
    verdict_input: str | None = None
    on_reject: Literal["abort", "skip", "retry"] = "abort"

    @field_validator("options")
    @classmethod
    def _unique(cls, value: list[str]) -> list[str]:
        if len(set(value)) != len(value):
            raise ValueError("gate options must be unique")
        return value


class IfStep(BaseStep):
    CONDITION_FIELDS: ClassVar[tuple[str, ...]] = ("condition",)

    type: Literal["if"] = "if"
    condition: str
    then: list[Step] = Field(min_length=1)
    else_: list[Step] = Field(default_factory=list, alias="else")

    def children(self) -> Iterator[tuple[str, list[Step]]]:
        yield "then", self.then
        if self.else_:
            yield "else", self.else_


class SwitchStep(BaseStep):
    TEMPLATE_FIELDS: ClassVar[tuple[str, ...]] = ("expression",)

    type: Literal["switch"] = "switch"
    expression: str
    cases: dict[str, list[Step]] = Field(min_length=1)
    default: list[Step] = Field(default_factory=list)

    def children(self) -> Iterator[tuple[str, list[Step]]]:
        for key, steps in self.cases.items():
            yield f"cases.{key}", steps
        if self.default:
            yield "default", self.default


class WhileStep(BaseStep):
    CONDITION_FIELDS: ClassVar[tuple[str, ...]] = ("condition",)

    type: Literal["while"] = "while"
    condition: str
    steps: list[Step] = Field(min_length=1)
    max_iterations: int = Field(ge=1)

    def children(self) -> Iterator[tuple[str, list[Step]]]:
        yield "steps", self.steps


class DoWhileStep(WhileStep):
    type: Literal["do-while"] = "do-while"  # type: ignore[assignment]


class FanOutStep(BaseStep):
    TEMPLATE_FIELDS: ClassVar[tuple[str, ...]] = ("items",)

    type: Literal["fan-out"] = "fan-out"
    items: str
    max_concurrency: int = Field(default=1, ge=1)
    step: Step

    def children(self) -> Iterator[tuple[str, list[Step]]]:
        yield "step", [self.step]


class FanInStep(BaseStep):
    TEMPLATE_FIELDS: ClassVar[tuple[str, ...]] = ("output",)

    type: Literal["fan-in"] = "fan-in"
    wait_for: list[str] = Field(min_length=1)
    output: dict[str, str] = Field(default_factory=dict)


class WorkflowCallStep(BaseStep):
    TEMPLATE_FIELDS: ClassVar[tuple[str, ...]] = ("workflow", "input")

    type: Literal["workflow"] = "workflow"
    workflow: str = Field(min_length=1)
    input: dict[str, Any] = Field(default_factory=dict)


def _default_step_type(value: Any) -> Any:
    """``type`` defaults to command; ``prompt:`` or ``run:`` without a type imply those."""
    if isinstance(value, dict) and "type" not in value:
        if "command" in value:
            kind = "command"
        elif "prompt" in value:
            kind = "prompt"
        elif "run" in value:
            kind = "shell"
        else:
            kind = "command"
        return {**value, "type": kind}
    return value


Step = Annotated[
    Annotated[
        CommandStep
        | PromptStep
        | ShellStep
        | GateStep
        | IfStep
        | SwitchStep
        | WhileStep
        | DoWhileStep
        | FanOutStep
        | FanInStep
        | WorkflowCallStep,
        Field(discriminator="type"),
    ],
    BeforeValidator(_default_step_type),
]

ENGINE_STEP_TYPES = (CommandStep, PromptStep)

for _model in (IfStep, SwitchStep, WhileStep, DoWhileStep, FanOutStep):
    _model.model_rebuild()


# ---------------------------------------------------------------------------- hooks


class HookSpec(EngineSettings):
    """Something to run before/after a step or the run. Exactly one of
    ``command`` / ``prompt`` / ``run``."""

    command: str | None = None
    args: str | None = None
    prompt: str | None = None
    run: str | None = None
    env: dict[str, str] = Field(default_factory=dict)
    optional: bool = False
    prompt_text: str | None = None
    description: str | None = None
    condition: str | None = None
    priority: int = Field(default=10, ge=1)
    timeout: float | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def _one_action(self) -> HookSpec:
        actions = [n for n in ("command", "prompt", "run") if getattr(self, n)]
        if len(actions) != 1:
            raise ValueError("a hook needs exactly one of 'command', 'prompt' or 'run'")
        if self.args is not None and self.command is None:
            raise ValueError("'args' is only valid with 'command'")
        return self

    @property
    def kind(self) -> Literal["command", "prompt", "run"]:
        if self.command:
            return "command"
        return "prompt" if self.prompt else "run"

    @property
    def label(self) -> str:
        return self.description or self.command or self.run or (self.prompt or "")[:60]

    def template_strings(self) -> Iterator[tuple[str, str, bool]]:
        for name in ("args", "prompt", "run", "prompt_text"):
            value = getattr(self, name)
            if value:
                yield name, value, False
        for key, value in self.env.items():
            yield f"env.{key}", value, False
        if self.condition:
            yield "condition", self.condition, True


def _as_list(value: Any) -> Any:
    return [value] if isinstance(value, dict) else value


HookList = Annotated[list[HookSpec], BeforeValidator(_as_list)]

RUN_EVENTS = ("before_run", "after_run")
HOOKED_STEP_KINDS = ("command", "prompt", "shell", "gate")
STEP_EVENTS = ("before_step", "after_step")
_EVENT_RE = re.compile(r"^(before|after)_(.+)$")


class BuiltinHook(_Model):
    """A hook compose adds to every workflow (shown by ``compose workflow info``)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str
    event: str
    position: Literal["first", "last"]
    description: str


BUILTIN_TRACKING_HOOKS = (
    BuiltinHook(
        name="compose.track.begin",
        event="before_step",
        position="first",
        description="Snapshot the worktree and open the step's trace.",
    ),
    BuiltinHook(
        name="compose.track.end",
        event="after_step",
        position="last",
        description="Record files and lines changed, engine actions, tokens and cost.",
    ),
)


# ------------------------------------------------------------------------- workflow


class WorkflowMeta(EngineSettings):
    id: str = Field(pattern=ID_RE)
    name: str = Field(min_length=1)
    version: str = Field(default="0.0.0", pattern=VERSION_RE)
    author: str | None = None
    description: str | None = None
    limits: Limits = Field(default_factory=Limits)
    tracking: bool = True


class Requires(_Model):
    compose_version: str | None = None
    engines: list[str] = Field(default_factory=list)


class Workflow(_Model):
    schema_version: Literal["1.0"] = SCHEMA_VERSION
    workflow: WorkflowMeta
    requires: Requires = Field(default_factory=Requires)
    inputs: dict[str, InputSpec] = Field(default_factory=dict)
    hooks: dict[str, HookList] = Field(default_factory=dict)
    outputs: dict[str, OutputSpec] = Field(default_factory=dict)
    steps: list[Step] = Field(min_length=1)

    @field_validator("schema_version", mode="before")
    @classmethod
    def _version_str(cls, value: Any) -> Any:
        return str(value) if isinstance(value, int | float) else value

    @property
    def id(self) -> str:
        return self.workflow.id

    def iter_steps(self) -> Iterator[tuple[str, BaseStep, bool]]:
        """Every step, nested ones included: (location, step, inside_fan_out)."""
        yield from _walk(self.steps, "steps", False)

    def step_ids(self) -> set[str]:
        return {step.id for _, step, _ in self.iter_steps()}

    def hook_events(self) -> list[str]:
        return list(self.hooks)

    @model_validator(mode="after")
    def _validate(self) -> Workflow:
        errors: list[str] = []
        seen: dict[str, str] = {}
        for where, step, _ in self.iter_steps():
            if step.id in seen:
                errors.append(f"{where}: duplicate step id {step.id!r} (first at {seen[step.id]})")
            else:
                seen[step.id] = where
        for name in self.inputs:
            if not re.match(INPUT_NAME_RE, name):
                errors.append(f"inputs.{name}: invalid input name")
        ids = set(seen)
        kinds = {step.id: step.kind for _, step, _ in self.iter_steps()}
        for where, step, _ in self.iter_steps():
            gate_input = step.verdict_input if isinstance(step, GateStep) else None
            if gate_input and gate_input not in self.inputs:
                errors.append(f"{where}.verdict_input: {gate_input!r} is not a declared input")
            if isinstance(step, FanInStep):
                for target in step.wait_for:
                    if target not in ids:
                        errors.append(f"{where}.wait_for: unknown step {target!r}")
            if isinstance(step, WorkflowCallStep) and step.workflow == self.workflow.id:
                errors.append(f"{where}.workflow: a workflow cannot call itself")
        for event in self.hooks:
            if event in RUN_EVENTS or event in STEP_EVENTS:
                continue
            match = _EVENT_RE.match(event)
            if not match:
                errors.append(f"hooks.{event}: event must be before_<step-id> or after_<step-id>")
            elif match.group(2) not in ids:
                errors.append(f"hooks.{event}: no step with id {match.group(2)!r}")
            elif (kind := kinds[match.group(2)]) not in HOOKED_STEP_KINDS:
                errors.append(
                    f"hooks.{event}: {match.group(2)!r} is a step of type {kind!r}; hooks run only "
                    "around command, prompt, shell and gate steps"
                )
        errors.extend(self._check_expressions(ids))
        if errors:
            raise ValueError("\n".join(errors))
        return self

    def _check_expressions(self, step_ids: set[str]) -> list[str]:
        errors: list[str] = []

        def check(where: str, text: str, bare: bool, in_fan_out: bool, fan_in: bool) -> None:
            try:
                refs = expressions.references(text, bare=bare)
            except expressions.ExpressionError as exc:
                errors.append(f"{where}: {exc}")
                return
            for ref in refs:
                root = ref[0]
                if root not in EXPRESSION_ROOTS:
                    errors.append(f"{where}: unknown name {root!r} in {text!r}")
                elif root == "inputs" and len(ref) > 1 and ref[1] not in self.inputs:
                    errors.append(f"{where}: unknown input {ref[1]!r}")
                elif root == "steps" and len(ref) > 1 and ref[1] not in step_ids:
                    errors.append(f"{where}: unknown step {ref[1]!r}")
                elif root == "item" and not in_fan_out:
                    errors.append(f"{where}: 'item' is only available inside a fan-out step")
                elif root == "fan_in" and not fan_in:
                    errors.append(f"{where}: 'fan_in' is only available in a fan-in step")

        for where, step, in_fan_out in self.iter_steps():
            for label, text, bare in step.template_strings():
                check(f"{where}.{label}", text, bare, in_fan_out, isinstance(step, FanInStep))
        in_fan_out_ids = {step.id for _, step, inside in self.iter_steps() if inside}
        for event, hooks in self.hooks.items():
            match = _EVENT_RE.match(event)
            per_item = bool(match) and match.group(2) in in_fan_out_ids  # type: ignore[union-attr]
            for i, hook in enumerate(hooks):
                for label, text, bare in hook.template_strings():
                    check(f"hooks.{event}[{i}].{label}", text, bare, per_item, False)
        for name, out in self.outputs.items():
            check(f"outputs.{name}.value", out.value, False, False, False)
        return errors


def _walk(steps: list[Any], where: str, in_fan_out: bool) -> Iterator[tuple[str, BaseStep, bool]]:
    for i, step in enumerate(steps):
        here = f"{where}[{i}]({step.id})"
        yield here, step, in_fan_out
        for label, children in step.children():
            yield from _walk(
                children, f"{here}.{label}", in_fan_out or isinstance(step, FanOutStep)
            )
