from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass

from bridge import db
from bridge.adapters.base import AdapterBundle
from bridge.mapping import denormalize_status, normalize_status
from bridge.models import BridgeStatus, SystemName


@dataclass
class SyncResult:
    mirrored: int = 0
    assignments_attached: int = 0
    reconciled: int = 0


class BridgeService:
    def __init__(self, conn: sqlite3.Connection, adapters: AdapterBundle, worker_id: str = "worker-1"):
        self.conn = conn
        self.adapters = adapters
        self.worker_id = worker_id

    def phase1_visibility_sync(self) -> SyncResult:
        result = SyncResult()
        p_items = self.adapters.paperclip.list_items()
        b_items = {i.id: i for i in self.adapters.beads.list_items()}

        for p in p_items:
            b = b_items.get(p.id)
            if not b:
                continue
            p_norm = normalize_status(SystemName.PAPERCLIP, p.status)
            b_norm = normalize_status(SystemName.BEADS, b.status)
            if p_norm != b_norm:
                target_status = denormalize_status(SystemName.BEADS, p_norm)
                dedupe_key = f"status:{p.id}:{target_status}"
                db.enqueue_outbox(
                    self.conn,
                    dedupe_key,
                    "status_mirror",
                    "paperclip",
                    "beads",
                    {"item_id": p.id, "status": target_status},
                )
            db.set_last_synced_status(self.conn, "paperclip", p.id, p.status)
            db.set_last_synced_status(self.conn, "beads", b.id, b.status)
        return result

    def process_outbox(self, max_retries: int = 3) -> int:
        sent = 0
        for row in db.fetch_pending_outbox(self.conn):
            payload = json.loads(row["payload"])
            try:
                if row["event_type"] == "status_mirror":
                    self.adapters.beads.set_status(payload["item_id"], payload["status"])
                elif row["event_type"] == "attach_hook":
                    self.adapters.gastown.attach_hook(payload["item_id"], payload["assignee"])
                db.mark_outbox_sent(self.conn, row["event_id"])
                sent += 1
            except Exception:
                db.mark_outbox_retry_or_dlq(self.conn, row["event_id"], max_retries=max_retries)
        return sent

    def phase2_assignment_automation(self) -> SyncResult:
        result = SyncResult()
        for item in self.adapters.paperclip.list_items():
            if not item.assignee:
                continue
            dedupe_key = f"assign:{item.id}:{item.assignee}"
            db.enqueue_outbox(
                self.conn,
                dedupe_key,
                "attach_hook",
                "paperclip",
                "gastown",
                {"item_id": item.id, "assignee": item.assignee},
            )
            result.assignments_attached += 1
        return result

    def phase3_reconcile(self) -> SyncResult:
        result = SyncResult()
        if not db.acquire_lease(self.conn, "reconcile", self.worker_id, ttl_seconds=20):
            return result
        p_items = {i.id: i for i in self.adapters.paperclip.list_items()}
        b_items = {i.id: i for i in self.adapters.beads.list_items()}
        for item_id, p in p_items.items():
            b = b_items.get(item_id)
            if not b:
                continue
            if normalize_status(SystemName.PAPERCLIP, p.status) != normalize_status(SystemName.BEADS, b.status):
                target = denormalize_status(SystemName.BEADS, normalize_status(SystemName.PAPERCLIP, p.status))
                self.adapters.beads.set_status(item_id, target)
                result.reconciled += 1
        return result
