"""Exceptions used to drive and report runs."""

from __future__ import annotations


class RunError(Exception):
    """A run cannot be started, resumed or aborted (user-facing)."""


class InputError(RunError):
    """Inputs are missing or invalid."""


class StepFailed(Exception):
    """A step failed and the run must stop (no ``continue_on_error``)."""

    def __init__(self, step_id: str, error: str) -> None:
        super().__init__(f"step {step_id!r} failed: {error}")
        self.step_id = step_id
        self.error = error


class RunPaused(Exception):
    """The run stops here and waits for input (a gate)."""

    def __init__(self, step_id: str, reason: str) -> None:
        super().__init__(reason)
        self.step_id = step_id
        self.reason = reason


class RunAborted(Exception):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class LimitExceeded(Exception):
    def __init__(self, message: str) -> None:
        super().__init__(f"limit_exceeded: {message}")
