from __future__ import annotations

from bridge import db


def test_lease_single_worker(conn) -> None:
    assert db.acquire_lease(conn, "reconcile", "w1", ttl_seconds=100)
    assert not db.acquire_lease(conn, "reconcile", "w2", ttl_seconds=100)
