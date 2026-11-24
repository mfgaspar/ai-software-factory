"""Run events become spans and counters, with ids derived from the run and step ids."""

from __future__ import annotations

from typing import Any

from compose import telemetry
from compose.core.config import Config
from compose.core.models import RunStatus
from compose.engines.fake import Script, edit
from compose.telemetry import Telemetry
from tests.unit.runner_helpers import Env

WF = """
workflow: {id: tel, name: Tel}
steps:
  - id: build
    prompt: build it
"""


class FakeSpan:
    def __init__(self, name: str, context: Any, start: int | None, attrs: dict[str, Any]) -> None:
        self.name, self.context, self.start, self.attrs = name, context, start, attrs
        self.end_time: int | None = None
        self.error = False

    def set_status(self, status: Any) -> None:
        self.error = True

    def end(self, end_time: int | None = None) -> None:
        self.end_time = end_time


class FakeTracer:
    def __init__(self) -> None:
        self.spans: list[FakeSpan] = []

    def start_span(self, name: str, context: Any, start_time: int | None, attributes: Any):
        span = FakeSpan(name, context, start_time, attributes)
        self.spans.append(span)
        return span


class FakeCounter:
    def __init__(self) -> None:
        self.added: list[tuple[float, dict[str, Any]]] = []

    def add(self, value: float, attrs: dict[str, Any]) -> None:
        self.added.append((value, attrs))


class FakeMeter:
    def __init__(self) -> None:
        self.counters: dict[str, FakeCounter] = {}

    def create_counter(self, name: str, unit: str = "") -> FakeCounter:
        return self.counters.setdefault(name, FakeCounter())


def parent_span_id(span: FakeSpan) -> int | None:
    from opentelemetry import trace

    return trace.get_current_span(span.context).get_span_context().span_id if span.context else None


async def test_run_exports_run_and_step_spans_and_counters(env: Env) -> None:
    env.fake.scripts = {"build it": Script(edit("a.txt", "x\n", cost=0.5))}
    tracer, meter = FakeTracer(), FakeMeter()
    runner = env.runner()
    runner.telemetry = Telemetry(env.db, tracer, meter)
    run = await runner.start(env.repo, env.workflow(WF))
    assert run.status is RunStatus.COMPLETED, run.error

    spans = {s.name: s for s in tracer.spans}
    assert set(spans) == {"run tel", "prompt build"}
    step, root = spans["prompt build"], spans["run tel"]
    assert parent_span_id(step) == telemetry.run_span_id(run.id)
    assert root.context is None
    assert step.attrs["compose.step_id"] == "build"
    assert step.attrs["gen_ai.system"] == "fake"
    assert step.attrs["compose.cost_usd"] == 0.5
    assert step.start is not None and step.end_time is not None
    assert step.end_time >= step.start
    assert root.attrs["compose.status"] == "completed"
    assert [v for v, _ in meter.counters["compose.cost"].added] == [0.5]
    assert [v for v, _ in meter.counters["compose.runs"].added] == [1]


async def test_failed_step_marks_the_span_as_an_error(env: Env) -> None:
    env.fake.scripts = {"build it": Script(fail="boom")}
    tracer = FakeTracer()
    runner = env.runner()
    runner.telemetry = Telemetry(env.db, tracer)
    run = await runner.start(env.repo, env.workflow(WF))
    assert run.status is RunStatus.FAILED
    assert any(s.error for s in tracer.spans)


def test_ids_are_stable_and_nonzero() -> None:
    assert telemetry.trace_id_for("run_1") == telemetry.trace_id_for("run_1")
    assert telemetry.step_span_id("exec_1") != telemetry.run_span_id("exec_1")
    assert 0 < telemetry.step_span_id("exec_1") < 2**64


def test_off_by_default_and_without_the_sdk(db) -> None:
    assert telemetry.create(db, Config()) is None
    on = Config.model_validate({"telemetry": {"enabled": True}})
    try:
        import opentelemetry.sdk  # noqa: F401
    except ImportError:
        assert telemetry.create(db, on) is None


async def test_real_sdk_keeps_derived_ids_and_parents(env: Env) -> None:
    import pytest

    pytest.importorskip("opentelemetry.sdk")
    from opentelemetry.sdk.metrics.export import InMemoryMetricReader
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

    exporter, reader = InMemorySpanExporter(), InMemoryMetricReader()
    env.fake.scripts = {"build it": Script(edit("a.txt", "x\n", cost=0.5))}
    runner = env.runner()
    runner.telemetry = telemetry.build(env.db, "compose", SimpleSpanProcessor(exporter), reader)
    run = await runner.start(env.repo, env.workflow(WF))
    assert run.status is RunStatus.COMPLETED, run.error

    spans = {s.name: s for s in exporter.get_finished_spans()}
    root, step = spans["run tel"], spans["prompt build"]
    assert root.context.trace_id == step.context.trace_id == telemetry.trace_id_for(run.id)
    assert root.context.span_id == telemetry.run_span_id(run.id)
    assert step.parent is not None and step.parent.span_id == root.context.span_id
    assert root.parent is None
    assert step.start_time is not None and step.end_time is not None
    assert step.end_time >= step.start_time
    assert step.attributes["gen_ai.system"] == "fake"
    assert root.resource.attributes["service.name"] == "compose"

    names = {
        m.name
        for rm in (reader.get_metrics_data().resource_metrics)
        for sm in rm.scope_metrics
        for m in sm.metrics
    }
    assert {"compose.cost", "compose.steps", "compose.runs"} <= names
