from __future__ import annotations

from bridge.mapping import denormalize_status, normalize_status
from bridge.models import BridgeStatus, SystemName


def test_status_mapping_roundtrip() -> None:
    assert normalize_status(SystemName.PAPERCLIP, "todo") == BridgeStatus.OPEN
    assert normalize_status(SystemName.BEADS, "active") == BridgeStatus.IN_PROGRESS
    assert denormalize_status(SystemName.BEADS, BridgeStatus.DONE) == "closed"
