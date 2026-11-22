"""Every YAML example in the workflow reference must be valid."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest
import yaml

from compose.workflows.schema import Workflow

DOC = Path(__file__).parents[2] / "docs" / "workflow-reference.md"
BLOCKS = re.findall(r"```yaml\n(.*?)```", DOC.read_text(), re.DOTALL)

# Inputs and steps that snippet examples refer to.
WRAPPER_INPUTS = {
    name: {"type": "string"}
    for name in ("spec", "clarify", "size", "services", "report", "release", "spec_verdict")
}


def _wrap(snippet: Any, kind: str) -> dict[str, Any]:
    base: dict[str, Any] = {
        "workflow": {"id": "doc-example", "name": "Doc example"},
        "inputs": WRAPPER_INPUTS,
        "steps": [{"id": "implement", "command": "compose-implement"}],
    }
    if kind == "steps":
        base["steps"] = base["steps"] + snippet
    else:
        base.update(snippet)
    return base


def _cases() -> list[tuple[str, dict[str, Any]]]:
    cases = []
    for i, block in enumerate(BLOCKS):
        data = yaml.safe_load(block)
        if isinstance(data, dict) and "schema_version" in data:
            cases.append((f"block{i}-full", data))
        elif isinstance(data, list):
            cases.append((f"block{i}-steps", _wrap(data, "steps")))
        elif isinstance(data, dict) and set(data) == {"hooks"}:
            cases.append((f"block{i}-hooks", _wrap(data, "hooks")))
        elif isinstance(data, dict) and set(data) <= {"workflow", "steps"}:
            merged = {"workflow": {"id": "doc-example", "name": "Doc", **data.get("workflow", {})}}
            cases.append((f"block{i}-partial", {**merged, "steps": data["steps"]}))
    return cases


CASES = _cases()


def test_doc_has_examples() -> None:
    assert len(CASES) >= 12


@pytest.mark.parametrize(("label", "data"), CASES, ids=[c[0] for c in CASES])
def test_doc_example_is_valid(label: str, data: dict[str, Any]) -> None:
    Workflow.model_validate(data)
