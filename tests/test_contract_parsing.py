from __future__ import annotations

import json
from pathlib import Path

from bridge.adapters.beads import parse_beads_item
from bridge.adapters.gastown import parse_gastown_hook
from bridge.adapters.paperclip import parse_paperclip_item


def test_parse_paperclip_fixture() -> None:
    payload = json.loads((Path(__file__).parent / "fixtures" / "paperclip" / "item.json").read_text())
    item = parse_paperclip_item(payload)
    assert item.id == "42"
    assert item.status == "in_progress"
    assert item.assignee == "alice"


def test_parse_beads_fixture() -> None:
    payload = json.loads((Path(__file__).parent / "fixtures" / "beads" / "item.json").read_text())
    item = parse_beads_item(payload)
    assert item.id == "42"
    assert item.status == "active"
    assert item.assignee == "alice"


def test_parse_gastown_fixture() -> None:
    payload = json.loads((Path(__file__).parent / "fixtures" / "gastown" / "hook.json").read_text())
    hook_id = parse_gastown_hook(payload)
    assert hook_id == "hook-42-alice"
