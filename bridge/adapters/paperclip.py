from __future__ import annotations

import json
import urllib.request
from dataclasses import dataclass

from bridge.models import WorkItem


@dataclass
class PaperclipHTTPAdapter:
    base_url: str
    token: str | None = None

    def _request(self, path: str, method: str = "GET", body: dict | None = None) -> dict:
        url = f"{self.base_url.rstrip('/')}/{path.lstrip('/')}"
        data = json.dumps(body).encode() if body else None
        req = urllib.request.Request(url, method=method, data=data)
        req.add_header("Content-Type", "application/json")
        if self.token:
            req.add_header("Authorization", f"Bearer {self.token}")
        with urllib.request.urlopen(req, timeout=20) as res:  # nosec B310
            return json.loads(res.read().decode())

    def list_items(self) -> list[WorkItem]:
        payload = self._request("items")
        return [parse_paperclip_item(x) for x in payload.get("items", [])]

    def set_status(self, item_id: str, status: str) -> None:
        self._request(f"items/{item_id}/status", method="POST", body={"status": status})

    def get_item(self, item_id: str) -> WorkItem:
        payload = self._request(f"items/{item_id}")
        return parse_paperclip_item(payload)


def parse_paperclip_item(payload: dict) -> WorkItem:
    return WorkItem(
        id=str(payload["id"]),
        status=str(payload["status"]),
        assignee=payload.get("assignee"),
        raw=payload,
    )
