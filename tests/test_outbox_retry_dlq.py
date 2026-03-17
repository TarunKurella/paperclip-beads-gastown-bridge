from __future__ import annotations

from bridge.adapters.base import AdapterBundle
from bridge.mock_adapters import InMemoryBeads, InMemoryPaperclip
from bridge.models import WorkItem
from bridge.service import BridgeService


class FailingGastown:
    def attach_hook(self, issue_id: str, assignee: str) -> str:
        raise RuntimeError("boom")


def test_outbox_retry_then_dlq(conn) -> None:
    svc = BridgeService(
        conn,
        AdapterBundle(
            paperclip=InMemoryPaperclip({"1": WorkItem(id="1", status="todo", assignee="alice")}),
            beads=InMemoryBeads({"1": WorkItem(id="1", status="new")}),
            gastown=FailingGastown(),
        ),
    )
    svc.phase2_assignment_automation()
    for _ in range(4):
        svc.process_outbox(max_retries=2)
        conn.execute("UPDATE outbox_events SET next_attempt_at=0")
        conn.commit()
    row = conn.execute("SELECT status,retry_count FROM outbox_events").fetchone()
    assert row[0] == "dlq"
    assert row[1] >= 3
