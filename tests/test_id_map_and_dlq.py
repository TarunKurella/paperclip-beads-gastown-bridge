from __future__ import annotations

from bridge import db
from bridge.adapters.base import AdapterBundle
from bridge.mock_adapters import InMemoryBeads, InMemoryGastown, InMemoryPaperclip
from bridge.models import WorkItem
from bridge.service import BridgeService


def test_explicit_id_map_is_preferred(conn):
    paperclip = InMemoryPaperclip(
        {"pc-1": WorkItem(id="pc-1", status="todo", assignee="alice", raw={"title": "X"})}
    )
    beads = InMemoryBeads({"bead-a": WorkItem(id="bead-a", status="open", raw={"title": "Other"})})
    gastown = InMemoryGastown()
    svc = BridgeService(conn, AdapterBundle(paperclip=paperclip, beads=beads, gastown=gastown))

    db.put_id_map(conn, "pc-1", "bead-a")
    result = svc.phase2_assignment_automation()
    assert result.assignments_attached == 1

    sent = svc.process_outbox()
    assert sent == 1
    assert gastown.attached == [("bead-a", "alice")]


def test_replay_dlq_moves_events_to_pending(conn):
    eid = db.enqueue_outbox(conn, "k-dlq", "status_mirror", "paperclip", "beads", {"item_id": "1", "status": "open"})
    # force to dlq
    for _ in range(4):
        db.mark_outbox_retry_or_dlq(conn, eid, max_retries=3)

    assert db.count_outbox_by_status(conn, "dlq") == 1
    moved = db.replay_dlq(conn, limit=10)
    assert moved == 1
    assert db.count_outbox_by_status(conn, "pending") == 1
