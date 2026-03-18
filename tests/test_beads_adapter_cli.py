from __future__ import annotations

import json
import subprocess

from bridge.adapters.beads import BeadsCLIAdapter, _to_bd_status, parse_beads_item


def _cp(payload: object) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(args=["bd"], returncode=0, stdout=json.dumps(payload), stderr="")


def test_set_status_uses_update_status(monkeypatch):
    calls: list[list[str]] = []

    def fake_run(args, check, capture_output, text):
        calls.append(args)
        return _cp({"ok": True})

    monkeypatch.setattr(subprocess, "run", fake_run)
    BeadsCLIAdapter("bd").set_status("bd-1", "done")

    assert calls == [["bd", "update", "bd-1", "--status", "closed", "--json"]]


def test_list_items_supports_array_payload(monkeypatch):
    def fake_run(args, check, capture_output, text):
        return _cp([{"id": "bd-1", "status": "open", "assignee": "alice"}])

    monkeypatch.setattr(subprocess, "run", fake_run)
    items = BeadsCLIAdapter("bd").list_items()

    assert len(items) == 1
    assert items[0].id == "bd-1"
    assert items[0].status == "open"
    assert items[0].assignee == "alice"


def test_get_item_supports_array_payload(monkeypatch):
    def fake_run(args, check, capture_output, text):
        return _cp([{"id": "bd-2", "state": "in_progress", "owner": "bob"}])

    monkeypatch.setattr(subprocess, "run", fake_run)
    item = BeadsCLIAdapter("bd").get_item("bd-2")

    assert item.id == "bd-2"
    assert item.status == "in_progress"
    assert item.assignee == "bob"


def test_parse_beads_item_fallback_fields():
    item = parse_beads_item({"id": "x", "status": "blocked", "assignee": "sam"})
    assert item.status == "blocked"
    assert item.assignee == "sam"


def test_status_mapping():
    assert _to_bd_status("done") == "closed"
    assert _to_bd_status("new") == "open"
    assert _to_bd_status("active") == "in_progress"
