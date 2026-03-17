from __future__ import annotations

from bridge import db


def test_outbox_dedupe(conn) -> None:
    a = db.enqueue_outbox(conn, "k1", "status_mirror", "paperclip", "beads", {"item_id": "1", "status": "new"})
    b = db.enqueue_outbox(conn, "k1", "status_mirror", "paperclip", "beads", {"item_id": "1", "status": "new"})
    assert a == b
    rows = conn.execute("SELECT count(*) FROM outbox_events WHERE dedupe_key='k1'").fetchone()[0]
    assert rows == 1
