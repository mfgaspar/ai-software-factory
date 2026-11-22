from __future__ import annotations

from compose.core.ids import new_id, ulid


def test_ulid_shape() -> None:
    value = ulid()
    assert len(value) == 26
    assert set(value) <= set("0123456789ABCDEFGHJKMNPQRSTVWXYZ")


def test_ulid_unique_and_sorted() -> None:
    values = [ulid() for _ in range(5000)]
    assert len(set(values)) == len(values)
    assert values == sorted(values)


def test_new_id_prefix() -> None:
    assert new_id("run").startswith("run_")
