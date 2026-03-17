from __future__ import annotations

import json
import sqlite3
import time
import uuid
from pathlib import Path
from typing import Any

DB_DEFAULT = "bridge.db"


def connect(db_path: str = DB_DEFAULT) -> sqlite3.Connection:
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def migrate(conn: sqlite3.Connection, migrations_dir: str) -> None:
    conn.execute("CREATE TABLE IF NOT EXISTS schema_migrations (name TEXT PRIMARY KEY)")
    applied = {r[0] for r in conn.execute("SELECT name FROM schema_migrations").fetchall()}
    for path in sorted(Path(migrations_dir).glob("*.sql")):
        if path.name in applied:
            continue
        conn.executescript(path.read_text())
        conn.execute("INSERT INTO schema_migrations(name) VALUES (?)", (path.name,))
    conn.commit()


def now_ts() -> int:
    return int(time.time())


def set_last_synced_status(conn: sqlite3.Connection, system: str, item_id: str, status: str) -> None:
    conn.execute(
        """
        INSERT INTO state_status(system, item_id, status, updated_at)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(system, item_id) DO UPDATE SET
          status=excluded.status,
          updated_at=excluded.updated_at
        """,
        (system, item_id, status, now_ts()),
    )


def get_last_synced_status(conn: sqlite3.Connection, system: str, item_id: str) -> str | None:
    row = conn.execute(
        "SELECT status FROM state_status WHERE system=? AND item_id=?", (system, item_id)
    ).fetchone()
    return str(row[0]) if row else None


def acquire_lease(conn: sqlite3.Connection, name: str, owner: str, ttl_seconds: int = 60) -> bool:
    expires = now_ts() + ttl_seconds
    conn.execute("BEGIN IMMEDIATE")
    row = conn.execute("SELECT owner, expires_at FROM leases WHERE name=?", (name,)).fetchone()
    if row is None:
        conn.execute(
            "INSERT INTO leases(name, owner, expires_at) VALUES (?, ?, ?)",
            (name, owner, expires),
        )
        conn.commit()
        return True
    if int(row["expires_at"]) < now_ts() or row["owner"] == owner:
        conn.execute(
            "UPDATE leases SET owner=?, expires_at=? WHERE name=?", (owner, expires, name)
        )
        conn.commit()
        return True
    conn.rollback()
    return False


def enqueue_outbox(
    conn: sqlite3.Connection,
    dedupe_key: str,
    event_type: str,
    source_system: str,
    target_system: str,
    payload: dict[str, Any],
) -> str:
    event_id = str(uuid.uuid4())
    conn.execute(
        """
        INSERT OR IGNORE INTO outbox_events
        (event_id, dedupe_key, event_type, source_system, target_system, payload, status, retry_count, next_attempt_at, created_at)
        VALUES (?, ?, ?, ?, ?, ?, 'pending', 0, ?, ?)
        """,
        (event_id, dedupe_key, event_type, source_system, target_system, json.dumps(payload), now_ts(), now_ts()),
    )
    row = conn.execute("SELECT event_id FROM outbox_events WHERE dedupe_key=?", (dedupe_key,)).fetchone()
    conn.commit()
    return str(row[0])


def fetch_pending_outbox(conn: sqlite3.Connection, limit: int = 50) -> list[sqlite3.Row]:
    return conn.execute(
        """
        SELECT * FROM outbox_events
        WHERE status='pending' AND next_attempt_at <= ?
        ORDER BY created_at ASC
        LIMIT ?
        """,
        (now_ts(), limit),
    ).fetchall()


def mark_outbox_sent(conn: sqlite3.Connection, event_id: str) -> None:
    conn.execute("UPDATE outbox_events SET status='sent' WHERE event_id=?", (event_id,))
    conn.commit()


def mark_outbox_retry_or_dlq(conn: sqlite3.Connection, event_id: str, max_retries: int = 3) -> None:
    row = conn.execute(
        "SELECT retry_count FROM outbox_events WHERE event_id=?", (event_id,)
    ).fetchone()
    if row is None:
        return
    retry_count = int(row[0]) + 1
    if retry_count > max_retries:
        conn.execute("UPDATE outbox_events SET status='dlq', retry_count=? WHERE event_id=?", (retry_count, event_id))
    else:
        backoff = 2 ** retry_count
        conn.execute(
            "UPDATE outbox_events SET retry_count=?, next_attempt_at=? WHERE event_id=?",
            (retry_count, now_ts() + backoff, event_id),
        )
    conn.commit()
