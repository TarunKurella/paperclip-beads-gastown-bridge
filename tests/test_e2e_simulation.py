from __future__ import annotations

from bridge.adapters.base import AdapterBundle
from bridge.mock_adapters import InMemoryBeads, InMemoryGastown, InMemoryPaperclip
from bridge.models import WorkItem
from bridge.service import BridgeService


def test_e2e_phases(conn) -> None:
    paperclip = InMemoryPaperclip(
        {
            "1": WorkItem(id="1", status="in_progress", assignee="alice"),
            "2": WorkItem(id="2", status="todo", assignee=None),
        }
    )
    beads = InMemoryBeads(
        {
            "1": WorkItem(id="1", status="new", assignee=None),
            "2": WorkItem(id="2", status="new", assignee=None),
        }
    )
    gastown = InMemoryGastown()
    svc = BridgeService(conn, AdapterBundle(paperclip=paperclip, beads=beads, gastown=gastown))

    svc.phase1_visibility_sync()
    sent1 = svc.process_outbox()
    assert sent1 == 1
    assert beads.get_item("1").status == "active"

    svc.phase2_assignment_automation()
    sent2 = svc.process_outbox()
    assert sent2 == 1
    assert gastown.attached == [("1", "alice")]

    # force drift and reconcile
    beads.set_status("1", "blocked")
    result = svc.phase3_reconcile()
    assert result.reconciled == 1
    assert beads.get_item("1").status == "active"
