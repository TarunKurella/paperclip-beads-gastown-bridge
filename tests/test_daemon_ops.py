from __future__ import annotations

import json

from bridge import db
from bridge.adapters.base import AdapterBundle
from bridge.config import RuntimeConfig
from bridge.daemon import run_daemon
from bridge.mock_adapters import InMemoryGastown, InMemoryPaperclip
from bridge.models import WorkItem
from bridge.observability import AlertSink, JsonLogger, Metrics
from bridge.service import BridgeService


class FailingBeads:
    def list_items(self):
        return [WorkItem(id="1", status="new")]

    def set_status(self, item_id: str, status: str) -> None:
        raise RuntimeError("boom")

    def get_item(self, item_id: str):
        return WorkItem(id=item_id, status="new")


def test_daemon_flushes_metrics_and_alerts_on_dlq(conn, tmp_path):
    paperclip = InMemoryPaperclip({"1": WorkItem(id="1", status="todo", assignee="alice")})
    svc = BridgeService(conn, AdapterBundle(paperclip=paperclip, beads=FailingBeads(), gastown=InMemoryGastown()))

    cfg = RuntimeConfig(
        mode="mock",
        db_path=str(tmp_path / "x.db"),
    )
    cfg.metrics.file_path = str(tmp_path / "metrics.json")
    cfg.alerts.dlq_warn_threshold = 1
    cfg.intervals.phase1_seconds = 1
    cfg.intervals.phase2_seconds = 1
    cfg.intervals.phase3_seconds = 1
    cfg.intervals.outbox_drain_seconds = 1
    cfg.intervals.loop_sleep_seconds = 1

    logger = JsonLogger(component="test")
    metrics = Metrics(file_path=cfg.metrics.file_path)
    alerts = AlertSink(logger=logger, webhook_url=None)

    # Pre-seed one failing event, then force immediate DLQ transition
    event_id = db.enqueue_outbox(
        conn,
        dedupe_key="t-1",
        event_type="status_mirror",
        source_system="paperclip",
        target_system="beads",
        payload={"item_id": "1", "status": "new"},
    )
    db.mark_outbox_retry_or_dlq(conn, event_id, max_retries=0)

    run_daemon(svc, cfg, logger, metrics, alerts, max_loops=1)

    payload = json.loads((tmp_path / "metrics.json").read_text())
    assert payload["counters"]["outbox_dlq"] >= 1
