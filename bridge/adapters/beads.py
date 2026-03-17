from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass

from bridge.models import WorkItem


@dataclass
class BeadsCLIAdapter:
    bin_name: str = "bd"

    def _json(self, *args: str) -> dict:
        proc = subprocess.run(
            [self.bin_name, *args, "--json"],
            check=True,
            capture_output=True,
            text=True,
        )
        return json.loads(proc.stdout)

    def list_items(self) -> list[WorkItem]:
        payload = self._json("issues", "list")
        return [parse_beads_item(x) for x in payload.get("issues", [])]

    def set_status(self, item_id: str, status: str) -> None:
        self._json("issues", "set-status", item_id, status)

    def get_item(self, item_id: str) -> WorkItem:
        payload = self._json("issues", "get", item_id)
        return parse_beads_item(payload)


def parse_beads_item(payload: dict) -> WorkItem:
    return WorkItem(
        id=str(payload["id"]),
        status=str(payload["state"]),
        assignee=payload.get("owner"),
        raw=payload,
    )
