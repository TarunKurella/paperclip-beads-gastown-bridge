from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


class SystemName(str, Enum):
    PAPERCLIP = "paperclip"
    BEADS = "beads"
    GASTOWN = "gastown"


class BridgeStatus(str, Enum):
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    BLOCKED = "blocked"
    DONE = "done"


@dataclass(frozen=True)
class WorkItem:
    id: str
    status: str
    assignee: str | None = None
    raw: dict[str, Any] | None = None


@dataclass(frozen=True)
class OutboxEvent:
    event_id: str
    dedupe_key: str
    event_type: str
    source_system: SystemName
    target_system: SystemName
    payload: dict[str, Any]
    retry_count: int = 0
