from __future__ import annotations

from bridge.adapters.base import AdapterBundle
from bridge.mock_adapters import InMemoryBeads, InMemoryGastown, InMemoryPaperclip
from bridge.models import WorkItem
from bridge.service import BridgeService


def test_phase2_maps_paperclip_to_beads_by_title(conn) -> None:
    paperclip = InMemoryPaperclip(
        {
            "pc-uuid-1": WorkItem(
                id="pc-uuid-1",
                status="todo",
                assignee="alice",
                raw={"title": "Launch keynote prep"},
            )
        }
    )
    beads = InMemoryBeads(
        {
            "gt-abc": WorkItem(
                id="gt-abc",
                status="open",
                assignee=None,
                raw={"title": "Launch keynote prep"},
            )
        }
    )
    gastown = InMemoryGastown()
    svc = BridgeService(conn, AdapterBundle(paperclip=paperclip, beads=beads, gastown=gastown))

    result = svc.phase2_assignment_automation()
    assert result.assignments_attached == 1

    sent = svc.process_outbox()
    assert sent == 1
    assert gastown.attached == [("gt-abc", "alice")]
