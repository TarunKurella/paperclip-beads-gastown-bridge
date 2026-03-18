from __future__ import annotations

import json
import sqlite3

import pytest

from bridge import db
from bridge.adapters.base import AdapterBundle
from bridge.config import ConfigError, load_config
from bridge.mock_adapters import InMemoryBeads, InMemoryGastown, InMemoryPaperclip
from bridge.models import WorkItem
from bridge.service import BridgeService


def test_default_config_is_single_writer(tmp_path):
    cfg_path = tmp_path / "cfg.json"
    cfg_path.write_text(json.dumps({"mode": "real", "paperclip_base_url": "http://localhost:3100"}))
    cfg = load_config(str(cfg_path))
    assert cfg.single_writer is True
    assert cfg.status_authority == "paperclip"


def test_invalid_single_writer_beads_authority(tmp_path):
    cfg_path = tmp_path / "cfg.json"
    cfg_path.write_text(
        json.dumps(
            {
                "mode": "real",
                "paperclip_base_url": "http://localhost:3100",
                "single_writer": True,
                "status_authority": "beads",
            }
        )
    )
    with pytest.raises(ConfigError):
        load_config(str(cfg_path))


def test_single_writer_blocks_paperclip_target(conn):
    paperclip = InMemoryPaperclip({"1": WorkItem(id="1", status="todo")})
    beads = InMemoryBeads({"1": WorkItem(id="1", status="open")})
    gastown = InMemoryGastown()
    svc = BridgeService(conn, AdapterBundle(paperclip=paperclip, beads=beads, gastown=gastown), single_writer=True)

    db.enqueue_outbox(conn, "k-paperclip", "status_mirror", "beads", "paperclip", {"item_id": "1", "status": "todo"})
    sent = svc.process_outbox(max_retries=0)
    assert sent == 0
    assert db.count_outbox_by_status(conn, "dlq") == 1
