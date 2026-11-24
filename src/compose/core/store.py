"""Generic CRUD for :class:`~compose.core.models.Record` types."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, TypeVar

from compose.core.db import Database
from compose.core.models import Record

R = TypeVar("R", bound=Record)


def insert(db: Database, record: R) -> R:
    """Insert a record."""
    row = record.to_row()
    cols = ", ".join(row)
    marks = ", ".join("?" for _ in row)
    db.execute(f"INSERT INTO {record.TABLE} ({cols}) VALUES ({marks})", tuple(row.values()))
    return record


def get(db: Database, cls: type[R], pk: Any) -> R | None:
    row = db.execute(f"SELECT * FROM {cls.TABLE} WHERE {cls.PK} = ?", (pk,)).fetchone()
    return None if row is None else cls.from_row(row)


def update(db: Database, record: R) -> None:
    """Write every column of an existing record."""
    row = record.to_row()
    pk = row.pop(record.PK)
    sets = ", ".join(f"{col} = ?" for col in row)
    cur = db.execute(f"UPDATE {record.TABLE} SET {sets} WHERE {record.PK} = ?", (*row.values(), pk))
    if cur.rowcount != 1:
        raise LookupError(f"{record.TABLE} row {pk!r} not found")


def select(
    db: Database,
    cls: type[R],
    where: str = "",
    params: Sequence[Any] = (),
    order_by: str | None = None,
) -> list[R]:
    """Select records. ``where``/``order_by`` are trusted SQL fragments from code."""
    sql = f"SELECT * FROM {cls.TABLE}"
    if where:
        sql += f" WHERE {where}"
    if order_by:
        sql += f" ORDER BY {order_by}"
    return [cls.from_row(row) for row in db.execute(sql, tuple(params))]
