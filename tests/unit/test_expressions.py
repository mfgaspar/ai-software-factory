from __future__ import annotations

import re
from typing import Any

import pytest

from compose.workflows.expressions import (
    ExpressionError,
    Undefined,
    compile_template,
    evaluate,
    evaluate_condition,
    references,
    register_filter,
    render,
)

CTX: dict[str, Any] = {
    "inputs": {
        "spec": "Add login",
        "n": 3,
        "ratio": 0.5,
        "flag": True,
        "off": False,
        "empty": "",
        "csv": "a,b,c",
        "people": [{"name": "ana", "age": 30}, {"name": "bo", "age": 20}],
        "raw": '{"k": [1, 2]}',
        "key": "name",
    },
    "steps": {
        "test": {"output": {"exit_code": 1, "stdout": "FAIL"}},
        "review-spec": {"output": {"choice": "approve"}},
    },
    "context": {"run_id": "run_1"},
}


@pytest.mark.parametrize(
    ("template", "expected"),
    [
        # typed lone expressions
        ("{{ inputs.n }}", 3),
        ("  {{ inputs.flag }}  ", True),
        ("{{ inputs.people }}", CTX["inputs"]["people"]),
        ("{{ [1, 'a', true] }}", [1, "a", True]),
        ("{{ -1.5 }}", -1.5),
        ("{{ null }}", None),
        # text rendering
        ("n={{ inputs.n }}", "n=3"),
        ("{{ inputs.flag }}/{{ inputs.off }}", "true/false"),
        ("x{{ null }}y", "xy"),
        ("{{ inputs.spec }} for {{ context.run_id }}", "Add login for run_1"),
        ("list: {{ [1, 2] }}", "list: [1, 2]"),
        ("no expressions", "no expressions"),
        # lookups
        ("{{ steps.review-spec.output.choice }}", "approve"),
        ("{{ inputs.people[0].name }}", "ana"),
        ("{{ inputs.people.1.name }}", "bo"),
        ("{{ inputs.people[-1].name }}", "bo"),
        ("{{ inputs.people[0][inputs.key] }}", "ana"),
        # comparisons and logic
        ("{{ steps.test.output.exit_code != 0 }}", True),
        ("{{ inputs.n >= 3 and inputs.ratio < 1 }}", True),
        ("{{ inputs.off or inputs.spec }}", "Add login"),
        ("{{ not inputs.flag }}", False),
        ("{{ 'log' in inputs.spec }}", True),
        ("{{ 'x' not in inputs.csv }}", True),
        ("{{ 2 in [1, 2] }}", True),
        ("{{ 'spec' in inputs }}", True),
        ("{{ (inputs.n == 3) and (inputs.spec == 'Add login') }}", True),
        ("{{ inputs.missing == null }}", True),
        # filters
        ("{{ inputs.missing | default('d') }}", "d"),
        ("{{ inputs.missing.deeper | default(inputs.n) }}", 3),
        ("{{ inputs.empty | default('d') }}", ""),
        ("{{ inputs.csv | split(',') }}", ["a", "b", "c"]),
        ("{{ inputs.csv | split(',') | join('-') }}", "a-b-c"),
        ("{{ inputs.people | map('name') | join }}", "ana,bo"),
        ("{{ inputs.people | length > 1 }}", True),
        ("{{ inputs.spec | upper }}", "ADD LOGIN"),
        ("{{ inputs.spec | lower | contains('login') }}", True),
        ("{{ inputs.raw | from_json }}", {"k": [1, 2]}),
        ("{{ inputs.people | map('age') | to_json }}", "[30, 20]"),
        ("{{ 'a\\'b' }}", "a'b"),
    ],
)
def test_render(template: str, expected: Any) -> None:
    assert render(template, CTX) == expected


@pytest.mark.parametrize(
    ("condition", "expected"),
    [
        ("{{ inputs.flag }}", True),
        ("inputs.flag and inputs.n > 2", True),
        ("{{ inputs.missing }}", False),  # undefined is falsy in conditions
        ("not inputs.missing", True),
        ("{{ steps.test.output.exit_code == 0 }}", False),
        (True, True),
    ],
)
def test_conditions(condition: str | bool, expected: bool) -> None:
    assert evaluate_condition(condition, CTX) is expected


def test_evaluate_bare() -> None:
    assert evaluate("inputs.people | map('name')", CTX) == ["ana", "bo"]


@pytest.mark.parametrize(
    ("template", "message"),
    [
        ("{{ input.spec }}", "unknown name 'input'"),
        ("{{ inputs.missing }}", "inputs.missing is undefined"),
        ("x {{ inputs.missing }}", "inputs.missing is undefined"),
        ("{{ inputs.n + 1 }}", "unexpected character '+'"),
        ("{{ inputs.n | nope }}", "unknown filter 'nope'"),
        ("{{ inputs.spec > 3 }}", "cannot compare str > int"),
        ("{{ inputs.n | length }}", "int has no length"),
        ("{{ inputs.n | join }}", "expected a list"),
        ("{{ inputs.spec | from_json }}", "invalid JSON"),
        ("{{ inputs.people | map('zip') }}", "no key 'zip'"),
        ("{{ }}", "empty expression"),
        ("{{ inputs.n ", "unbalanced"),
        ("{{ (inputs.n }}", "expected ')'"),
        ("{{ inputs.n inputs.n }}", "unexpected 'inputs' at 9"),
        ("{{ 3 in inputs.n }}", "'in' needs a list"),
    ],
)
def test_errors(template: str, message: str) -> None:
    with pytest.raises(ExpressionError, match=re.escape(message)):
        render(template, CTX)


def test_undefined_is_falsy() -> None:
    assert not Undefined("x")


def test_references() -> None:
    refs = references("{{ steps.test.output[inputs.key] | default(context.run_id) }} {{ 1 }}")
    assert refs == [("steps", "test", "output"), ("inputs", "key"), ("context", "run_id")]
    assert references("inputs.flag and item.x", bare=True) == [("inputs", "flag"), ("item", "x")]


def test_compile_flags() -> None:
    assert compile_template("{{ a }}").is_lone
    assert not compile_template("a {{ b }}").is_lone
    assert not compile_template("plain").has_expressions


def test_register_filter() -> None:
    register_filter("double_text", lambda v: v + v)
    assert render("{{ inputs.spec | double_text }}", CTX) == "Add loginAdd login"
