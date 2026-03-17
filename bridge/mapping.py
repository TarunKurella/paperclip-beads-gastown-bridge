from __future__ import annotations

from bridge.models import BridgeStatus, SystemName

STATUS_MAP_TO_BRIDGE: dict[SystemName, dict[str, BridgeStatus]] = {
    SystemName.PAPERCLIP: {
        "todo": BridgeStatus.OPEN,
        "in_progress": BridgeStatus.IN_PROGRESS,
        "blocked": BridgeStatus.BLOCKED,
        "done": BridgeStatus.DONE,
    },
    SystemName.BEADS: {
        "new": BridgeStatus.OPEN,
        "active": BridgeStatus.IN_PROGRESS,
        "blocked": BridgeStatus.BLOCKED,
        "closed": BridgeStatus.DONE,
    },
}

STATUS_MAP_FROM_BRIDGE: dict[SystemName, dict[BridgeStatus, str]] = {
    SystemName.PAPERCLIP: {
        BridgeStatus.OPEN: "todo",
        BridgeStatus.IN_PROGRESS: "in_progress",
        BridgeStatus.BLOCKED: "blocked",
        BridgeStatus.DONE: "done",
    },
    SystemName.BEADS: {
        BridgeStatus.OPEN: "new",
        BridgeStatus.IN_PROGRESS: "active",
        BridgeStatus.BLOCKED: "blocked",
        BridgeStatus.DONE: "closed",
    },
}


def normalize_status(system: SystemName, status: str) -> BridgeStatus:
    try:
        return STATUS_MAP_TO_BRIDGE[system][status]
    except KeyError as exc:
        raise ValueError(f"Unknown status '{status}' for {system.value}") from exc


def denormalize_status(system: SystemName, status: BridgeStatus) -> str:
    return STATUS_MAP_FROM_BRIDGE[system][status]
