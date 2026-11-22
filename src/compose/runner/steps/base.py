"""What step executors return."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from compose.core.models import ExecStatus


@dataclass
class Outcome:
    status: ExecStatus
    output: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
    abort_run: str | None = None  # finish this step, then abort the run with this reason

    @classmethod
    def ok(cls, **output: Any) -> Outcome:
        return cls(ExecStatus.COMPLETED, dict(output))

    @classmethod
    def failed(cls, error: str, **output: Any) -> Outcome:
        return cls(ExecStatus.FAILED, dict(output), error)
