from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass

from bridge.models import WorkItem


def _normalize_list_payload(payload: dict | list) -> list[dict]:
    if isinstance(payload, list):
        return [x for x in payload if isinstance(x, dict)]
    if isinstance(payload, dict):
        issues = payload.get("issues")
        if isinstance(issues, list):
            return [x for x in issues if isinstance(x, dict)]
        items = payload.get("items")
        if isinstance(items, list):
            return [x for x in items if isinstance(x, dict)]
    return []


def _to_bd_status(status: str) -> str:
    """Map canonical bridge status into current bd status vocabulary."""
    status = str(status)
    return {
        "open": "open",
        "in_progress": "in_progress",
        "blocked": "blocked",
        "done": "closed",
        # compatibility with older bridge payloads
        "new": "open",
        "active": "in_progress",
        "closed": "closed",
    }.get(status, status)


@dataclass
class BeadsCLIAdapter:
    bin_name: str = "bd"

    def _json(self, *args: str) -> dict | list:
        proc = subprocess.run(
            [self.bin_name, *args, "--json"],
            check=True,
            capture_output=True,
            text=True,
        )
        return json.loads(proc.stdout)

    def list_items(self) -> list[WorkItem]:
        payload = self._json("list")
        return [parse_beads_item(x) for x in _normalize_list_payload(payload)]

    def set_status(self, item_id: str, status: str) -> None:
        mapped = _to_bd_status(status)
        self._json("update", item_id, "--status", mapped)

    def get_item(self, item_id: str) -> WorkItem:
        payload = self._json("show", item_id)
        if isinstance(payload, list):
            if not payload:
                raise ValueError(f"bd show returned empty payload for item {item_id}")
            payload = payload[0]
        if not isinstance(payload, dict):
            raise ValueError(f"unexpected bd show payload type: {type(payload).__name__}")
        return parse_beads_item(payload)


def parse_beads_item(payload: dict) -> WorkItem:
    return WorkItem(
        id=str(payload["id"]),
        status=str(payload.get("state") or payload.get("status") or "open"),
        assignee=payload.get("owner") or payload.get("assignee"),
        raw=payload,
    )
