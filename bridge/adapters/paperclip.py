from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass

from bridge.models import WorkItem


@dataclass
class PaperclipHTTPAdapter:
    base_url: str
    token: str | None = None
    company_id: str | None = None
    retries: int = 2
    timeout_seconds: int = 20

    def _request(self, path: str, method: str = "GET", body: dict | None = None) -> dict | list:
        url = f"{self.base_url.rstrip('/')}/{path.lstrip('/')}"
        data = json.dumps(body).encode() if body else None
        req = urllib.request.Request(url, method=method, data=data)
        req.add_header("Content-Type", "application/json")
        if self.token:
            req.add_header("Authorization", f"Bearer {self.token}")

        attempts = max(1, int(self.retries) + 1)
        last_exc: Exception | None = None
        for attempt in range(attempts):
            try:
                with urllib.request.urlopen(req, timeout=self.timeout_seconds) as res:  # nosec B310
                    return json.loads(res.read().decode())
            except urllib.error.HTTPError as exc:
                # retry only 5xx responses
                if 500 <= int(exc.code) < 600 and attempt < attempts - 1:
                    time.sleep(0.2 * (attempt + 1))
                    last_exc = exc
                    continue
                raise RuntimeError(f"paperclip request failed: {method} {url} -> {exc.code}") from exc
            except urllib.error.URLError as exc:
                if attempt < attempts - 1:
                    time.sleep(0.2 * (attempt + 1))
                    last_exc = exc
                    continue
                raise RuntimeError(f"paperclip request failed: {method} {url} -> network error") from exc
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
                if attempt < attempts - 1:
                    time.sleep(0.2 * (attempt + 1))
                    continue
                raise RuntimeError(f"paperclip request failed: {method} {url}") from exc

        # defensive fallback (should never hit)
        if last_exc:
            raise RuntimeError(f"paperclip request failed: {method} {url}") from last_exc
        raise RuntimeError(f"paperclip request failed: {method} {url}")

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
            if self.company_id:
                issues = self._request(f"api/companies/{self.company_id}/issues")
                if isinstance(issues, list):
                    return [parse_paperclip_item(x) for x in issues]
            companies = self._request("api/companies")
            if isinstance(companies, list) and companies:
                company_id = companies[0].get("id")
                if company_id:
                    issues = self._request(f"api/companies/{company_id}/issues")
                    if isinstance(issues, list):
                        return [parse_paperclip_item(x) for x in issues]
        except Exception:
            pass

        # If we reached here, rethrow the most compatible call for clearer errors
        payload = self._request("items")
        if isinstance(payload, dict):
            return [parse_paperclip_item(x) for x in payload.get("items", [])]
        return []

    def set_status(self, item_id: str, status: str) -> None:
        # Prefer current API, fallback to legacy endpoint
        try:
            self._request(f"api/issues/{item_id}", method="PATCH", body={"status": status})
            return
        except Exception:
            pass
        self._request(f"items/{item_id}/status", method="POST", body={"status": status})

    def add_comment(self, item_id: str, body: str) -> None:
        try:
            self._request(f"api/issues/{item_id}/comments", method="POST", body={"body": body})
            return
        except Exception:
            pass
        # fallback via PATCH comment field
        self._request(f"api/issues/{item_id}", method="PATCH", body={"comment": body})

    def checkout_item(self, item_id: str, agent_id: str, expected_statuses: list[str] | None = None) -> None:
        statuses = expected_statuses or ["todo"]
        self._request(
            f"api/issues/{item_id}/checkout",
            method="POST",
            body={"agentId": agent_id, "expectedStatuses": statuses},
        )

    def release_item(self, item_id: str, agent_id: str) -> None:
        self._request(f"api/issues/{item_id}/release", method="POST", body={"agentId": agent_id})

    def get_item(self, item_id: str) -> WorkItem:
        try:
            payload = self._request(f"api/issues/{item_id}")
            if isinstance(payload, dict):
                return parse_paperclip_item(payload)
        except Exception:
            pass
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
