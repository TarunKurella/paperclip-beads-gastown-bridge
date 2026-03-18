from __future__ import annotations

from bridge import db
from bridge.adapters.base import AdapterBundle
from bridge.mock_adapters import InMemoryBeads, InMemoryGastown, InMemoryPaperclip
from bridge.models import WorkItem
from bridge.service import BridgeService


def test_phase2_respects_owner_rule(conn):
    paperclip = InMemoryPaperclip({"pc-1": WorkItem(id="pc-1", status="todo", assignee="alice", raw={"title": "A"})})
    beads = InMemoryBeads({"b-1": WorkItem(id="b-1", status="open", raw={"title": "A"})})
    svc = BridgeService(conn, AdapterBundle(paperclip=paperclip, beads=beads, gastown=InMemoryGastown()), scope_key="demo", single_writer=True)

    r = svc.phase2_assignment_automation()
    assert r.assignments_attached == 0
    assert r.skipped_owner == 1

    db.set_execution_owner(conn, "demo", "pc-1", "beads_runner")
    r2 = svc.phase2_assignment_automation()
    assert r2.assignments_attached == 1


def test_phase_feedback_enqueues_limited_reverse_updates(conn):
    paperclip = InMemoryPaperclip({"pc-1": WorkItem(id="pc-1", status="todo", raw={"title": "A"})})
    beads = InMemoryBeads({"b-1": WorkItem(id="b-1", status="active", raw={"title": "A"})})
    svc = BridgeService(conn, AdapterBundle(paperclip=paperclip, beads=beads, gastown=InMemoryGastown()), scope_key="demo", single_writer=True)

    db.put_id_map(conn, "demo", "pc-1", "b-1")
    db.set_execution_owner(conn, "demo", "pc-1", "beads_runner")

    res = svc.phase_feedback_sync()
    assert res.reconciled == 1
    sent = svc.process_outbox()
    assert sent == 1
