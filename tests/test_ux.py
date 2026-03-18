from __future__ import annotations

import json

from bridge import db
from bridge.config import AlertConfig, MetricsConfig, RuntimeConfig
from bridge.ux import dashboard_snapshot, write_runtime_config


def test_write_runtime_config(tmp_path):
    out = tmp_path / "config.json"
    cfg = RuntimeConfig(
        mode="real",
        db_path="./state/bridge.db",
        worker_id="node-1",
        paperclip_base_url="http://127.0.0.1:3100",
        metrics=MetricsConfig(file_path="./state/bridge.metrics.json"),
        alerts=AlertConfig(dlq_warn_threshold=5),
    )
    write_runtime_config(str(out), cfg)

    payload = json.loads(out.read_text())
    assert payload["mode"] == "real"
    assert payload["paperclip_base_url"] == "http://127.0.0.1:3100"
    assert payload["alerts"]["dlq_warn_threshold"] == 5


def test_dashboard_snapshot(conn):
    db.enqueue_outbox(conn, "k1", "status_mirror", "paperclip", "beads", {"item_id": "1", "status": "open"})
    row = db.fetch_pending_outbox(conn, 1)[0]
    db.mark_outbox_sent(conn, row["event_id"])

    snap = dashboard_snapshot(conn, paperclip_count=9, beads_count=4)
    assert snap["paperclip_items"] == 9
    assert snap["beads_items"] == 4
    assert snap["outbox_sent"] == 1
