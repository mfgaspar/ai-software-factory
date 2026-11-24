"""OpenTelemetry export of runs: one trace per root run, spans for runs and steps, counters
for cost and tokens.

It listens to the events a run already emits and reads the stored records, so the runner
holds no OpenTelemetry code and nothing runs unless ``telemetry.enabled`` is set. A span is
written when its run or step *ends*, with its recorded start and end times, so a run that
paused and resumed in another process still lands in one trace: ids are derived from the run
and step ids, not generated. A step that paused at a gate is exported when it finally
finishes, one span covering the wait (``compose.resumed`` is set on it).

The SDK and exporter are optional (``pip install compose-sdd[otel]``); without them
:func:`create` logs a warning and returns None. Prompts and file contents are never exported.
"""

from __future__ import annotations

import hashlib
import logging
from datetime import datetime
from typing import TYPE_CHECKING, Any

from compose.core import store
from compose.core.db import Database
from compose.core.models import ExecStatus, Run, StepExec

if TYPE_CHECKING:
    from compose.core.config import Config

log = logging.getLogger(__name__)

# Steps whose usage is their own (control steps' totals are their children's, so counting
# them would count twice).
LEAF_TYPES = frozenset({"command", "prompt", "shell", "gate", "questions", "clarity"})


def _id(label: str, bits: int) -> int:
    digest = hashlib.sha256(label.encode()).digest()
    return int.from_bytes(digest[: bits // 8], "big") or 1


def trace_id_for(root_run_id: str) -> int:
    return _id(f"trace:{root_run_id}", 128)


def run_span_id(run_id: str) -> int:
    return _id(f"run:{run_id}", 64)


def step_span_id(exec_id: str) -> int:
    return _id(f"exec:{exec_id}", 64)


def _ns(moment: datetime | None) -> int | None:
    return None if moment is None else int(moment.timestamp() * 1_000_000_000)


class Telemetry:
    """Turns run events into spans and metrics on the given tracer and meter."""

    def __init__(self, db: Database, tracer: Any, meter: Any = None, ids: Any = None) -> None:
        self.db = db
        self.tracer = tracer
        self._ids = ids  # the SDK id generator to preset, when ids are ours
        self._cost = meter.create_counter("compose.cost", unit="USD") if meter else None
        self._tokens = meter.create_counter("compose.tokens", unit="{token}") if meter else None
        self._steps = meter.create_counter("compose.steps", unit="{step}") if meter else None
        self._runs = meter.create_counter("compose.runs", unit="{run}") if meter else None

    # ------------------------------------------------------------------ events

    def handle(self, event: dict[str, Any]) -> None:
        """Never raises: telemetry must not break a run."""
        try:
            kind = event.get("type")
            if kind == "step_finished":
                self._step_finished(event)
            elif kind == "run_finished":
                self._run_finished(str(event["run_id"]))
        except Exception as exc:
            log.debug("telemetry failed: %s", exc)

    def _root_id(self, run: Run) -> str:
        seen = {run.id}
        while run.parent_run_id and run.parent_run_id not in seen:
            parent = store.get(self.db, Run, run.parent_run_id)
            if parent is None:
                break
            seen.add(parent.id)
            run = parent
        return run.id

    def _run_attrs(self, run: Run) -> dict[str, Any]:
        attrs: dict[str, Any] = {
            "compose.run_id": run.id,
            "compose.workflow": run.workflow_id,
            "compose.repo_id": run.repo_id,
        }
        if run.feature_id:
            attrs["compose.feature_id"] = run.feature_id
        if run.started_by:
            attrs["enduser.id"] = run.started_by
        return attrs

    def _step_finished(self, event: dict[str, Any]) -> None:
        row = store.get(self.db, StepExec, str(event["exec_id"]))
        if row is None or row.status is ExecStatus.PAUSED:
            return  # exported when it finally ends
        run = store.get(self.db, Run, row.run_id)
        if run is None:
            return
        parent = step_span_id(row.parent_exec_id) if row.parent_exec_id else run_span_id(run.id)
        attrs = {
            **self._run_attrs(run),
            "compose.step_id": row.step_id,
            "compose.step_type": row.step_type,
            "compose.status": row.status.value,
            "compose.attempt": row.attempt,
            "compose.cost_usd": row.cost_usd,
            "compose.files_changed": row.files_changed,
        }
        if row.engine:
            attrs["gen_ai.system"] = row.engine
        if row.model:
            attrs["gen_ai.request.model"] = row.model
        if row.step_type in LEAF_TYPES and (row.input_tokens or row.output_tokens):
            attrs["gen_ai.usage.input_tokens"] = row.input_tokens
            attrs["gen_ai.usage.output_tokens"] = row.output_tokens
        if row.error:
            attrs["compose.error"] = row.error[:500]
        self._span(
            f"{row.step_type} {row.step_id}",
            trace_id_for(self._root_id(run)),
            step_span_id(row.id),
            parent,
            row.started_at,
            row.ended_at,
            attrs,
            failed=row.status in (ExecStatus.FAILED, ExecStatus.ABORTED),
        )
        if row.step_type in LEAF_TYPES:
            self._count(row, run)

    def _run_finished(self, run_id: str) -> None:
        run = store.get(self.db, Run, run_id)
        if run is None:
            return
        parent = step_span_id(run.parent_exec_id) if run.parent_exec_id else None
        self._span(
            f"run {run.workflow_id}",
            trace_id_for(self._root_id(run)),
            run_span_id(run.id),
            parent,
            run.started_at or run.created_at,
            run.ended_at,
            {**self._run_attrs(run), "compose.status": run.status.value},
            failed=run.status.value in ("failed", "aborted"),
        )
        if self._runs is not None and not run.parent_run_id:
            self._runs.add(1, {"compose.status": run.status.value, **self._metric_attrs(run)})

    # --------------------------------------------------------------- recording

    def _span(
        self,
        name: str,
        trace_id: int,
        span_id: int,
        parent_span_id: int | None,
        start: datetime | None,
        end: datetime | None,
        attributes: dict[str, Any],
        *,
        failed: bool,
    ) -> None:
        from opentelemetry import trace

        context = None
        if parent_span_id is not None:
            parent = trace.NonRecordingSpan(
                trace.SpanContext(
                    trace_id, parent_span_id, is_remote=False, trace_flags=trace.TraceFlags(1)
                )
            )
            context = trace.set_span_in_context(parent)
        if self._ids is not None:
            self._ids.preset(trace_id, span_id)
        span = self.tracer.start_span(
            name, context=context, start_time=_ns(start), attributes=attributes
        )
        if failed:
            span.set_status(trace.Status(trace.StatusCode.ERROR))
        span.end(end_time=_ns(end))

    def _metric_attrs(self, run: Run) -> dict[str, Any]:
        attrs = {"compose.workflow": run.workflow_id, "compose.repo_id": run.repo_id}
        if run.started_by:
            attrs["enduser.id"] = run.started_by
        return attrs

    def _count(self, row: StepExec, run: Run) -> None:
        attrs = self._metric_attrs(run)
        if row.engine:
            attrs["gen_ai.system"] = row.engine
        if row.model:
            attrs["gen_ai.request.model"] = row.model
        if self._steps is not None:
            self._steps.add(1, {**attrs, "compose.status": row.status.value})
        if self._cost is not None and row.cost_usd:
            self._cost.add(row.cost_usd, attrs)
        if self._tokens is not None:
            for kind, value in (
                ("input", row.input_tokens),
                ("output", row.output_tokens),
                ("cache_read", row.cache_read_tokens),
                ("cache_write", row.cache_write_tokens),
            ):
                if value:
                    self._tokens.add(value, {**attrs, "gen_ai.token.type": kind})


def create(db: Database, config: Config) -> Telemetry | None:
    """The exporter the config asks for: None when off, or when the SDK isn't installed.
    Where spans go is set by the standard ``OTEL_EXPORTER_OTLP_*`` environment variables."""
    if not config.telemetry.enabled:
        return None
    try:
        from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
        from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
    except ImportError:
        log.warning(
            "telemetry is enabled but the OpenTelemetry SDK is missing: "
            "install compose-sdd[otel] (spans are not exported)"
        )
        return None
    return build(
        db,
        config.telemetry.service_name,
        BatchSpanProcessor(OTLPSpanExporter()),
        PeriodicExportingMetricReader(OTLPMetricExporter()),
    )


def build(db: Database, service_name: str, span_processor: Any, metric_reader: Any) -> Telemetry:
    """A :class:`Telemetry` on SDK providers using the given span processor and metric reader."""
    from opentelemetry.sdk.metrics import MeterProvider
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.id_generator import IdGenerator

    class PresetIds(IdGenerator):
        """Ids derived from the run and step ids, so a resumed run joins its trace."""

        def __init__(self) -> None:
            self._next: tuple[int, int] | None = None

        def preset(self, trace_id: int, span_id: int) -> None:
            self._next = (trace_id, span_id)

        def generate_trace_id(self) -> int:
            return self._next[0] if self._next else _id("fallback-trace", 128)

        def generate_span_id(self) -> int:
            return self._next[1] if self._next else _id("fallback-span", 64)

    from compose import __version__

    resource = Resource.create({"service.name": service_name, "service.version": __version__})
    ids = PresetIds()
    provider = TracerProvider(resource=resource, id_generator=ids)
    provider.add_span_processor(span_processor)
    meter_provider = MeterProvider(resource=resource, metric_readers=[metric_reader])
    return Telemetry(
        db, provider.get_tracer("compose"), meter_provider.get_meter("compose"), ids=ids
    )
