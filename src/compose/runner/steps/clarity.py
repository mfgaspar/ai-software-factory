"""The internal ``clarity`` step: compose's own bookkeeping in clarity runs.

``record-verdict`` reads the validator's last line and writes ``.clarity/verdict.yml``;
``publish-memory`` copies the documents to ``.compose/memory/`` and writes its index,
stamped with the fingerprint it came from;
``commit`` commits the clarity paths on the clarity branch; ``merge`` fast-forwards the
default branch after a PASS that still holds. Only built-in workflows may use it.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

from compose.clarity import branch, constitution, fingerprint, memory, service, verdict
from compose.core.models import StepExec
from compose.repos.git import GitError
from compose.runner.context import Scope
from compose.runner.steps.base import Outcome
from compose.workflows.schema import ClarityStep

if TYPE_CHECKING:
    from compose.runner.runner import RunContext

CLARITY_WORKFLOWS = ("clarity", "clarity-validate")


def mode_of(workflow_id: str, inputs: dict[str, Any]) -> str:
    """The clarity mode a run works in, for commit messages."""
    if workflow_id == "clarity-validate":
        return "validate"
    return str(inputs.get("mode") or "mixed")


def commit_message(rc: RunContext, status: str | None = None) -> str:
    mode = mode_of(rc.definition.id, rc.run.inputs)
    suffix = f" ({status})" if status else ""
    return f"clarity: {mode} run {rc.shared.root_run_id}{suffix}"


async def execute(rc: RunContext, step: ClarityStep, row: StepExec, scope: Scope) -> Outcome:
    workdir = rc.worktree
    if step.action == "record-verdict":
        result = rc.results.get(step.from_step or "") or {}
        text = (result.get("output") or {}).get("text") or ""
        found = verdict.parse(str(text))
        fp = fingerprint.of_dir(workdir)
        verdict.write(workdir, found, fp, rc.shared.root_run_id)
        rc.emit("clarity_verdict", exec_id=row.id, result=found.result, fingerprint=fp)
        return Outcome.ok(
            result=found.result,
            incomplete=found.incomplete,
            fingerprint=fp,
            constitution_current=_constitution_fingerprint(workdir) == fp,
        )
    if step.action == "publish-memory":
        fp = fingerprint.of_dir(workdir)
        try:
            published = memory.publish(workdir, fp)
        except memory.PublishError as exc:
            return Outcome.failed(f"could not publish {memory.MEMORY_DIR}: {exc}")
        return Outcome.ok(
            fingerprint=fp, written=len(published.written), removed=len(published.removed)
        )
    if step.action == "commit":
        try:
            sha = branch.commit_paths(workdir, commit_message(rc))
        except GitError as exc:
            return Outcome.failed(f"could not commit the clarity files: {exc}")
        return Outcome.ok(sha=sha)
    return _merge(rc, row)


def _constitution_fingerprint(workdir: Path) -> str | None:
    path = workdir / constitution.CONSTITUTION_FILE
    return constitution.read_text(path.read_text(encoding="utf-8")) if path.is_file() else None


def _merge(rc: RunContext, row: StepExec) -> Outcome:
    """Merge only on a recorded PASS that still describes the documents; never fail."""
    outcome = service.merge_if_passing(rc.repo, rc.worktree)
    if not outcome.merged:
        rc.emit("clarity_merge_pending", exec_id=row.id, reason=outcome.pending_reason)
        return Outcome.ok(merged=False, pending_reason=outcome.pending_reason)
    rc.emit("clarity_merged", exec_id=row.id, branch=branch.default_branch(rc.repo))
    return Outcome.ok(merged=True, pending_reason=None)
