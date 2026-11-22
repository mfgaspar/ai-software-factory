from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError

from compose.workflows.loader import format_validation_error
from compose.workflows.schema import (
    CommandStep,
    DoWhileStep,
    GateStep,
    InputSpec,
    InputType,
    PromptStep,
    ShellStep,
    Workflow,
    coerce_input,
)


def wf(steps: list[dict[str, Any]], **extra: Any) -> dict[str, Any]:
    return {"workflow": {"id": "demo", "name": "Demo"}, "steps": steps, **extra}


def errors(data: dict[str, Any]) -> str:
    with pytest.raises(ValidationError) as err:
        Workflow.model_validate(data)
    return "\n".join(format_validation_error(err.value))


def test_minimal() -> None:
    w = Workflow.model_validate(wf([{"id": "a", "command": "compose-plan"}]))
    assert w.id == "demo"
    assert w.workflow.version == "0.0.0"
    assert w.workflow.tracking is True
    assert isinstance(w.steps[0], CommandStep)


def test_type_inference() -> None:
    w = Workflow.model_validate(
        wf(
            [
                {"id": "a", "command": "x"},
                {"id": "b", "prompt": "hi"},
                {"id": "c", "run": "ls"},
                {"id": "d", "type": "gate", "message": "ok?"},
            ]
        )
    )
    kinds = [type(s) for s in w.steps]
    assert kinds == [CommandStep, PromptStep, ShellStep, GateStep]
    gate = w.steps[3]
    assert isinstance(gate, GateStep) and gate.options == ["approve", "reject"]


def test_nested_steps_and_walk() -> None:
    w = Workflow.model_validate(
        wf(
            [
                {
                    "id": "loop",
                    "type": "do-while",
                    "max_iterations": 2,
                    "condition": "{{ steps.t.output.exit_code != 0 }}",
                    "steps": [{"id": "t", "run": "pytest"}],
                },
                {
                    "id": "br",
                    "type": "if",
                    "condition": "true",
                    "then": [{"id": "x", "prompt": "p"}],
                    "else": [{"id": "y", "prompt": "q"}],
                },
                {
                    "id": "sw",
                    "type": "switch",
                    "expression": "{{ 'a' }}",
                    "cases": {"a": [{"id": "ca", "run": "true"}]},
                    "default": [{"id": "cd", "run": "true"}],
                },
                {
                    "id": "fan",
                    "type": "fan-out",
                    "items": "{{ [1] }}",
                    "step": {"id": "each", "run": "echo {{ item }}"},
                },
                {
                    "id": "join",
                    "type": "fan-in",
                    "wait_for": ["fan"],
                    "output": {"n": "{{ fan_in.results | length }}"},
                },
            ]
        )
    )
    assert isinstance(w.steps[0], DoWhileStep)
    assert w.step_ids() == {"loop", "t", "br", "x", "y", "sw", "ca", "cd", "fan", "each", "join"}
    inside = {s.id: f for _, s, f in w.iter_steps()}
    assert inside["each"] is True and inside["t"] is False


@pytest.mark.parametrize(
    ("data", "message"),
    [
        (wf([]), "at least 1 item"),
        (wf([{"id": "a", "command": "x"}, {"id": "a", "command": "y"}]), "duplicate step id 'a'"),
        (wf([{"id": "run", "command": "x"}]), "reserved"),
        (wf([{"id": "a:b", "command": "x"}]), "should match pattern"),
        (wf([{"id": "a", "command": "x", "bogus": 1}]), "Extra inputs are not permitted"),
        (wf([{"id": "a", "type": "nope"}]), "does not match any of the expected tags"),
        (
            wf(
                [
                    {
                        "id": "w",
                        "type": "while",
                        "condition": "true",
                        "steps": [{"id": "x", "run": "a"}],
                    }
                ]
            ),
            "max_iterations",
        ),
        (wf([{"id": "s", "run": "echo {{ x }}", "strict": True}]), "strict shell steps"),
        (
            wf([{"id": "g", "type": "gate", "message": "m", "verdict_input": "v"}]),
            "'v' is not a declared input",
        ),
        (
            wf([{"id": "g", "type": "gate", "message": "m", "options": ["a", "a"]}]),
            "unique",
        ),
        (wf([{"id": "f", "type": "fan-in", "wait_for": ["ghost"]}]), "unknown step 'ghost'"),
        (wf([{"id": "c", "type": "workflow", "workflow": "demo"}]), "cannot call itself"),
        (wf([{"id": "a", "prompt": "{{ inputs.nope }}"}]), "unknown input 'nope'"),
        (wf([{"id": "a", "prompt": "{{ steps.ghost.output }}"}]), "unknown step 'ghost'"),
        (wf([{"id": "a", "prompt": "{{ input.spec }}"}]), "unknown name 'input'"),
        (wf([{"id": "a", "prompt": "{{ item }}"}]), "only available inside a fan-out"),
        (wf([{"id": "a", "prompt": "{{ fan_in.results }}"}]), "only available in a fan-in"),
        (wf([{"id": "a", "prompt": "{{ 1 + 1 }}"}]), "unexpected character"),
        (
            wf([{"id": "a", "command": "x"}], hooks={"after_ghost": {"run": "x"}}),
            "no step with id 'ghost'",
        ),
        (
            wf([{"id": "a", "command": "x"}], hooks={"during_a": {"run": "x"}}),
            "event must be before_<step-id>",
        ),
        (
            wf([{"id": "a", "command": "x"}], hooks={"after_a": {"run": "x", "prompt": "y"}}),
            "exactly one of",
        ),
        (
            wf([{"id": "a", "command": "x"}], hooks={"after_a": {"run": "x", "args": "y"}}),
            "'args' is only valid with 'command'",
        ),
        (
            wf([{"id": "a", "command": "x"}], hooks={"after_a": {"run": "{{ inputs.q }}"}}),
            "unknown input 'q'",
        ),
        (wf([{"id": "a", "command": "x"}], outputs={"o": {"value": "{{ steps.z }}"}}), "'z'"),
        (wf([{"id": "a", "command": "x"}], inputs={"bad name": {}}), "invalid input name"),
        (
            wf([{"id": "a", "command": "x"}], inputs={"n": {"type": "number", "default": "x"}}),
            "is not a number",
        ),
        (
            wf([{"id": "a", "command": "x", "limits": {"max_cost_usd": 0}}]),
            "greater than 0",
        ),
        ({"workflow": {"id": "Bad_Id", "name": "x"}, "steps": [{"id": "a", "run": "x"}]}, "id"),
        ({**wf([{"id": "a", "run": "x"}]), "schema_version": "2.0"}, "schema_version"),
    ],
)
def test_invalid(data: dict[str, Any], message: str) -> None:
    assert message in errors(data)


def test_hooks_normalized_to_lists() -> None:
    w = Workflow.model_validate(
        wf(
            [{"id": "impl", "command": "x"}],
            hooks={
                "after_impl": {"run": "npm test"},
                "before_step": [{"command": "compose-checklist", "args": "a"}, {"prompt": "p"}],
                "after_run": {"run": "echo done"},
            },
        )
    )
    assert [h.kind for h in w.hooks["before_step"]] == ["command", "prompt"]
    assert w.hooks["after_impl"][0].priority == 10
    assert w.hooks["after_impl"][0].label == "npm test"


def test_numeric_schema_version_accepted() -> None:
    data = {**wf([{"id": "a", "run": "x"}]), "schema_version": 1.0}
    assert Workflow.model_validate(data).schema_version == "1.0"


@pytest.mark.parametrize(
    ("spec", "raw", "expected"),
    [
        (InputSpec(type=InputType.BOOLEAN), "yes", True),
        (InputSpec(type=InputType.BOOLEAN), "0", False),
        (InputSpec(type=InputType.BOOLEAN), False, False),
        (InputSpec(type=InputType.NUMBER), "42", 42),
        (InputSpec(type=InputType.NUMBER), "2.5", 2.5),
        (InputSpec(type=InputType.STRING), 7, "7"),
        (InputSpec(enum=["a", "b"]), "a", "a"),
    ],
)
def test_coerce_input(spec: InputSpec, raw: Any, expected: Any) -> None:
    assert coerce_input(spec, raw) == expected


@pytest.mark.parametrize(
    ("spec", "raw", "message"),
    [
        (InputSpec(type=InputType.BOOLEAN), "maybe", "not a boolean"),
        (InputSpec(type=InputType.NUMBER), "x", "not a number"),
        (InputSpec(type=InputType.NUMBER), True, "not a number"),
        (InputSpec(enum=["a", "b"]), "c", "not one of: a, b"),
    ],
)
def test_coerce_input_errors(spec: InputSpec, raw: Any, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        coerce_input(spec, raw)
