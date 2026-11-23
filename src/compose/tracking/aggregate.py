"""Cost, token and change totals by step, run, feature, repo or day.

Counting rules (so nothing is counted twice):

- tokens and cost come from leaf step executions (``command``, ``prompt``, ``shell``,
  ``gate``), which already include their hooks once closed, plus hooks not folded into a
  leaf: run hooks, hooks around a fan-out, and hooks of a step still paused or running;
- files and lines come from the recorded file changes of whole step windows (the
  per-hook breakdown rows are left out); a file changed in two steps of the same
  feature counts once per group;
- a child run (``type: workflow``) counts toward its root run.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal

from compose.core.db import Database

GroupBy = Literal["step", "run", "feature", "repo", "day"]
LEAF = "('command', 'prompt', 'shell', 'gate', 'questions', 'clarity')"

_KEYS: dict[str, str] = {
    "step": "step_id",
    "run": "root_run_id",
    "feature": "feature_id",
    "repo": "repo_id",
    "day": "day",
}


@dataclass(frozen=True)
class Totals:
    key: str | None
    cost_usd: float = 0.0
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    files_changed: int = 0
    lines_added: int = 0
    lines_removed: int = 0
    runs: int = 0

    def to_json(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "cost_usd": self.cost_usd,
            "tokens": {
                "input": self.input_tokens,
                "output": self.output_tokens,
                "cache_read": self.cache_read_tokens,
                "cache_write": self.cache_write_tokens,
            },
            "changes": {
                "files": self.files_changed,
                "added": self.lines_added,
                "removed": self.lines_removed,
            },
            "runs": self.runs,
        }


_BASE = f"""
WITH RECURSIVE roots(id, root) AS (
    SELECT id, id FROM runs WHERE parent_run_id IS NULL
    UNION ALL
    SELECT r.id, roots.root FROM runs r JOIN roots ON r.parent_run_id = roots.id
),
usage(run_id, step_id, started_at, cost, tin, tout, tcr, tcw) AS (
    SELECT run_id, step_id, started_at, cost_usd, input_tokens, output_tokens,
           cache_read_tokens, cache_write_tokens
    FROM step_execs WHERE step_type IN {LEAF}
    UNION ALL
    SELECT h.run_id, COALESCE(s.step_id, h.event), h.started_at, h.cost_usd, h.input_tokens,
           h.output_tokens, h.cache_read_tokens, h.cache_write_tokens
    FROM hook_execs h LEFT JOIN step_execs s ON s.id = h.step_exec_id
    WHERE s.id IS NULL OR s.status IN ('paused', 'running') OR s.step_type NOT IN {LEAF}
),
changes(run_id, step_id, started_at, path, added, removed) AS (
    SELECT c.run_id, s.step_id, s.started_at, c.path, COALESCE(c.added, 0),
           COALESCE(c.removed, 0)
    FROM file_changes c JOIN step_execs s ON s.id = c.step_exec_id
    WHERE c.hook_exec_id IS NULL
),
rows(kind, root_run_id, feature_id, repo_id, step_id, day, started_at,
     cost, tin, tout, tcr, tcw, path, added, removed) AS (
    SELECT 'u', roots.root, r.feature_id, r.repo_id, u.step_id, substr(u.started_at, 1, 10),
           u.started_at, u.cost, u.tin, u.tout, u.tcr, u.tcw, NULL, 0, 0
    FROM usage u JOIN runs r ON r.id = u.run_id JOIN roots ON roots.id = r.id
    UNION ALL
    SELECT 'c', roots.root, r.feature_id, r.repo_id, c.step_id, substr(c.started_at, 1, 10),
           c.started_at, 0, 0, 0, 0, 0, COALESCE(r.feature_id, r.repo_id) || ':' || c.path,
           c.added, c.removed
    FROM changes c JOIN runs r ON r.id = c.run_id JOIN roots ON roots.id = r.id
)
"""


def utc(moment: datetime) -> str:
    """Timestamps are stored as UTC ISO strings; compare in the same form."""
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    return moment.astimezone(UTC).isoformat()


def totals(
    db: Database,
    by: GroupBy,
    *,
    run_id: str | None = None,
    feature_id: str | None = None,
    repo_id: str | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
) -> list[Totals]:
    """Totals grouped by ``by``, filtered by run (with its child runs), feature, repo and
    a time window on when each step started (``since`` inclusive, ``until`` exclusive)."""
    key = _KEYS[by]
    where: list[str] = []
    params: list[Any] = []
    for column, value in (
        ("root_run_id", run_id),
        ("feature_id", feature_id),
        ("repo_id", repo_id),
    ):
        if value is not None:
            where.append(f"{column} = ?")
            params.append(value)
    if since is not None:
        where.append("julianday(started_at) >= julianday(?)")
        params.append(utc(since))
    if until is not None:
        where.append("julianday(started_at) < julianday(?)")
        params.append(utc(until))
    clause = f"WHERE {' AND '.join(where)}" if where else ""
    sql = f"""{_BASE}
    SELECT {key}, SUM(cost), SUM(tin), SUM(tout), SUM(tcr), SUM(tcw),
           COUNT(DISTINCT path), SUM(added), SUM(removed), COUNT(DISTINCT root_run_id)
    FROM rows {clause}
    GROUP BY {key} ORDER BY {key}
    """
    out: list[Totals] = []
    for row in db.conn.execute(sql, params).fetchall():
        out.append(
            Totals(
                key=row[0],
                cost_usd=float(row[1] or 0),
                input_tokens=int(row[2] or 0),
                output_tokens=int(row[3] or 0),
                cache_read_tokens=int(row[4] or 0),
                cache_write_tokens=int(row[5] or 0),
                files_changed=int(row[6] or 0),
                lines_added=int(row[7] or 0),
                lines_removed=int(row[8] or 0),
                runs=int(row[9] or 0),
            )
        )
    return out


def grand_total(db: Database, **filters: Any) -> Totals:
    """One total across everything matching the filters (see :func:`totals`)."""
    rows = totals(db, "repo", **filters)
    if not rows:
        return Totals(key=None)
    return Totals(
        key=None,
        cost_usd=sum(r.cost_usd for r in rows),
        input_tokens=sum(r.input_tokens for r in rows),
        output_tokens=sum(r.output_tokens for r in rows),
        cache_read_tokens=sum(r.cache_read_tokens for r in rows),
        cache_write_tokens=sum(r.cache_write_tokens for r in rows),
        files_changed=sum(r.files_changed for r in rows),
        lines_added=sum(r.lines_added for r in rows),
        lines_removed=sum(r.lines_removed for r in rows),
        runs=sum(r.runs for r in rows),
    )
