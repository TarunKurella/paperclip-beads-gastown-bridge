from __future__ import annotations

from bridge.adapters.base import AdapterBundle
from bridge.mock_adapters import InMemoryBeads, InMemoryGastown, InMemoryPaperclip
from bridge.models import WorkItem
from bridge.service import BridgeService


def test_reconciliation_repairs_drift(conn) -> None:
    paperclip = InMemoryPaperclip({"1": WorkItem(id="1", status="done", assignee=None)})
    beads = InMemoryBeads({"1": WorkItem(id="1", status="active", assignee=None)})
    svc = BridgeService(conn, AdapterBundle(paperclip=paperclip, beads=beads, gastown=InMemoryGastown()))
    result = svc.phase3_reconcile()
    assert result.reconciled == 1
    assert beads.get_item("1").status == "closed"
