from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass

from bridge import db
from bridge.adapters.base import AdapterBundle
from bridge.mapping import denormalize_status, normalize_status
from bridge.models import BridgeStatus, SystemName, WorkItem


@dataclass
class SyncResult:
    mirrored: int = 0
    assignments_attached: int = 0
    reconciled: int = 0
    skipped_owner: int = 0
    skipped_lock: int = 0
    skipped_unmapped: int = 0


class BridgeService:
    def __init__(
        self,
        conn: sqlite3.Connection,
        adapters: AdapterBundle,
        worker_id: str = "worker-1",
        single_writer: bool = False,
        status_authority: str = "paperclip",
        scope_key: str = "default",
    ):
        self.conn = conn
        self.adapters = adapters
        self.worker_id = worker_id
        self.single_writer = single_writer
        self.status_authority = status_authority
        self.scope_key = scope_key

    def _resolve_beads_id_for_paperclip(self, paperclip_item: WorkItem, beads_items: list[WorkItem]) -> str | None:
        """Best-effort mapping from Paperclip issue -> Beads/Gastown bead id.

        Priority:
        0) Explicit DB map (id_map table)
        1) Direct ID match
        2) Beads raw.external_ref / externalRef equals paperclip id
        3) Exact title match (case-insensitive)
        """
        explicit = db.get_beads_id_for_paperclip(self.conn, self.scope_key, paperclip_item.id)
        if explicit:
            return explicit

        # 1) direct id
        for b in beads_items:
            if b.id == paperclip_item.id:
                return b.id

        # 2) external reference mapping
        for b in beads_items:
            raw = b.raw or {}
            ext = raw.get("external_ref") or raw.get("externalRef")
            if ext and str(ext) == str(paperclip_item.id):
                return b.id

        # 3) title mapping
        p_title = str((paperclip_item.raw or {}).get("title") or "").strip().lower()
        if p_title:
            for b in beads_items:
                b_title = str((b.raw or {}).get("title") or "").strip().lower()
                if b_title and b_title == p_title:
                    return b.id

        return None

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
                dedupe_key = f"{self.scope_key}:status:{p.id}:{target_status}"
                db.enqueue_outbox(
                    self.conn,
                    dedupe_key,
                    "status_mirror",
                    "paperclip",
                    "beads",
                    {"item_id": p.id, "status": target_status},
                )
            db.set_last_synced_status(self.conn, "paperclip", f"{self.scope_key}:{p.id}", p.status)
            db.set_last_synced_status(self.conn, "beads", f"{self.scope_key}:{b.id}", b.status)
        self.conn.commit()
        return result

    def process_outbox(self, max_retries: int = 3, on_failure: callable | None = None) -> int:
        sent = 0
        for row in db.fetch_pending_outbox(self.conn):
            payload = json.loads(row["payload"])
            try:
                allow_paperclip = bool(payload.get("allow_paperclip_write"))
                if self.single_writer and row["target_system"] == "paperclip" and not allow_paperclip:
                    raise ValueError("single_writer policy blocks writes targeting paperclip")

                if row["event_type"] == "status_mirror":
                    self.adapters.beads.set_status(payload["item_id"], payload["status"])
                elif row["event_type"] == "attach_hook":
                    self.adapters.gastown.attach_hook(payload["item_id"], payload["assignee"])
                    if payload.get("lock_key"):
                        db.release_run_lock(self.conn, str(payload["lock_key"]), owner=self.worker_id)
                elif row["event_type"] == "status_feedback":
                    self.adapters.paperclip.set_status(payload["item_id"], payload["status"])
                db.mark_outbox_sent(self.conn, row["event_id"])
                sent += 1
            except Exception as exc:
                db.mark_outbox_retry_or_dlq(self.conn, row["event_id"], max_retries=max_retries)
                if on_failure:
                    on_failure(row, exc)
        return sent

    def phase2_assignment_automation(self) -> SyncResult:
        result = SyncResult()
        beads_items = self.adapters.beads.list_items()
        for item in self.adapters.paperclip.list_items():
            if not item.assignee:
                continue

            owner = db.get_execution_owner(self.conn, self.scope_key, item.id) or (
                "paperclip_runner" if self.single_writer else "beads_runner"
            )
            if owner != "beads_runner":
                result.skipped_owner += 1
                continue

            beads_id = self._resolve_beads_id_for_paperclip(item, beads_items)
            if not beads_id:
                result.skipped_unmapped += 1
                continue

            lock_key = f"{self.scope_key}:run:{item.id}:phase2"
            if not db.acquire_run_lock(self.conn, lock_key, owner=self.worker_id, ttl_seconds=300):
                result.skipped_lock += 1
                continue

            dedupe_key = f"{self.scope_key}:assign:{beads_id}:{item.assignee}"
            db.enqueue_outbox(
                self.conn,
                dedupe_key,
                "attach_hook",
                "paperclip",
                "gastown",
                {"item_id": beads_id, "assignee": item.assignee, "lock_key": lock_key},
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
                if self.status_authority == "paperclip":
                    target = denormalize_status(SystemName.BEADS, normalize_status(SystemName.PAPERCLIP, p.status))
                    self.adapters.beads.set_status(item_id, target)
                    result.reconciled += 1
                elif self.status_authority == "beads" and not self.single_writer:
                    target = denormalize_status(SystemName.PAPERCLIP, normalize_status(SystemName.BEADS, b.status))
                    self.adapters.paperclip.set_status(item_id, target)
                    result.reconciled += 1
        return result

    def phase_feedback_sync(self) -> SyncResult:
        """Bounded reverse sync: only execution signal statuses from beads -> paperclip.

        Allowed when execution_owner == beads_runner. This avoids broad bi-directional races.
        """
        result = SyncResult()
        p_items = {i.id: i for i in self.adapters.paperclip.list_items()}
        b_items = self.adapters.beads.list_items()
        for b in b_items:
            # find mapped paperclip id by reverse lookup through scoped map table
            # (simple scan, low volume; can optimize later)
            mapped_pc = None
            for row in db.list_id_map(self.conn, scope_key=self.scope_key, limit=10000):
                if str(row["beads_id"]) == b.id:
                    mapped_pc = str(row["paperclip_id"])
                    break
            if not mapped_pc or mapped_pc not in p_items:
                continue

            owner = db.get_execution_owner(self.conn, self.scope_key, mapped_pc) or "paperclip_runner"
            if owner != "beads_runner":
                result.skipped_owner += 1
                continue

            norm = normalize_status(SystemName.BEADS, b.status)
            if norm not in {BridgeStatus.IN_PROGRESS.value, BridgeStatus.BLOCKED.value, BridgeStatus.DONE.value}:
                continue

            target = denormalize_status(SystemName.PAPERCLIP, norm)
            dedupe_key = f"{self.scope_key}:feedback:{mapped_pc}:{target}"
            db.enqueue_outbox(
                self.conn,
                dedupe_key,
                "status_feedback",
                "beads",
                "paperclip",
                {"item_id": mapped_pc, "status": target, "allow_paperclip_write": True},
            )
            result.reconciled += 1
        return result
