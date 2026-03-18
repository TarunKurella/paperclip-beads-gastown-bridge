from __future__ import annotations

import json
import shutil
import sqlite3
import urllib.request
from dataclasses import asdict
from pathlib import Path
from typing import Any

from bridge import db
from bridge.config import RuntimeConfig


def detect_paperclip_base_url() -> str:
    candidates = [
        "http://127.0.0.1:3100",
        "http://localhost:3100",
    ]
    for base in candidates:
        try:
            with urllib.request.urlopen(f"{base}/api/health", timeout=1.5) as r:  # nosec B310
                if r.status == 200:
                    return base
        except Exception:
            continue
    return candidates[0]


def detect_bin(name: str, fallback: str) -> str:
    return shutil.which(name) or fallback


def write_runtime_config(path: str, cfg: RuntimeConfig) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    payload = asdict(cfg)
    p.write_text(json.dumps(payload, indent=2) + "\n")


def dashboard_snapshot(conn: sqlite3.Connection, paperclip_count: int, beads_count: int) -> dict[str, Any]:
    snap = {
        "paperclip_items": paperclip_count,
        "beads_items": beads_count,
        "outbox_pending": db.count_outbox_by_status(conn, "pending"),
        "outbox_dlq": db.count_outbox_by_status(conn, "dlq"),
        "outbox_sent": db.count_outbox_by_status(conn, "sent"),
    }
    snap["health"] = "ok" if snap["outbox_dlq"] == 0 else "warn"
    if snap["outbox_dlq"] > 0:
        snap["next_action"] = "Run: bridge outbox-drain --config <config>; inspect failing IDs"
    elif snap["outbox_pending"] > 0:
        snap["next_action"] = "Run: bridge outbox-drain --config <config>"
    else:
        snap["next_action"] = "System healthy. Run: bridge run-daemon --config <config>"
    return snap


def onboarding_state_path() -> Path:
    return Path(".runtime/onboarding-state.json")


def load_onboarding_state() -> dict[str, Any]:
    p = onboarding_state_path()
    if not p.exists():
        return {"completed": False}
    try:
        return json.loads(p.read_text())
    except Exception:
        return {"completed": False}


def save_onboarding_state(config_path: str) -> None:
    p = onboarding_state_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"completed": True, "config_path": config_path}, indent=2) + "\n")
