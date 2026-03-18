from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass

from bridge.models import WorkItem


@dataclass
class PaperclipHTTPAdapter:
    base_url: str
    token: str | None = None

    def _request(self, path: str, method: str = "GET", body: dict | None = None) -> dict | list:
        url = f"{self.base_url.rstrip('/')}/{path.lstrip('/')}"
        data = json.dumps(body).encode() if body else None
        req = urllib.request.Request(url, method=method, data=data)
        req.add_header("Content-Type", "application/json")
        if self.token:
            req.add_header("Authorization", f"Bearer {self.token}")
        with urllib.request.urlopen(req, timeout=20) as res:  # nosec B310
            return json.loads(res.read().decode())

    def list_items(self) -> list[WorkItem]:
        # Legacy bridge contract
        try:
            payload = self._request("items")
            if isinstance(payload, dict):
                return [parse_paperclip_item(x) for x in payload.get("items", [])]
        except Exception:
            pass

        # Paperclip OSS local API shape:
        # GET /api/companies -> [{id,...}], then GET /api/companies/{id}/issues
        try:
            companies = self._request("api/companies")
            if isinstance(companies, list) and companies:
                company_id = companies[0].get("id")
                if company_id:
                    issues = self._request(f"api/companies/{company_id}/issues")
                    if isinstance(issues, list):
                        return [parse_paperclip_item(x) for x in issues]
        except urllib.error.HTTPError:
            pass

        # If we reached here, rethrow the most compatible call for clearer errors
        payload = self._request("items")
        if isinstance(payload, dict):
            return [parse_paperclip_item(x) for x in payload.get("items", [])]
        return []

    def set_status(self, item_id: str, status: str) -> None:
        self._request(f"items/{item_id}/status", method="POST", body={"status": status})

    def get_item(self, item_id: str) -> WorkItem:
        payload = self._request(f"items/{item_id}")
        if not isinstance(payload, dict):
            raise ValueError("unexpected paperclip item payload")
        return parse_paperclip_item(payload)


def parse_paperclip_item(payload: dict) -> WorkItem:
    return WorkItem(
        id=str(payload["id"]),
        status=str(payload.get("status", "todo")),
        assignee=payload.get("assignee") or payload.get("assigneeAgentId"),
        raw=payload,
    )
