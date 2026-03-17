from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


class ConfigError(ValueError):
    pass


@dataclass
class IntervalConfig:
    phase1_seconds: int = 30
    phase2_seconds: int = 60
    phase3_seconds: int = 120
    outbox_drain_seconds: int = 15
    loop_sleep_seconds: int = 1


@dataclass
class AlertConfig:
    webhook_url: str | None = None
    dlq_warn_threshold: int = 1


@dataclass
class MetricsConfig:
    file_path: str = "bridge.metrics.json"


@dataclass
class RuntimeConfig:
    mode: str = "mock"  # mock|real
    db_path: str = "bridge.db"
    worker_id: str = "worker-1"
    intervals: IntervalConfig = field(default_factory=IntervalConfig)
    metrics: MetricsConfig = field(default_factory=MetricsConfig)
    alerts: AlertConfig = field(default_factory=AlertConfig)
    paperclip_base_url: str | None = None
    paperclip_token: str | None = None
    beads_bin: str = "bd"
    gastown_bin: str = "gt"


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    out = dict(base)
    for k, v in override.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def _load_file(path: str | None) -> dict[str, Any]:
    if not path:
        return {}
    p = Path(path)
    if not p.exists():
        raise ConfigError(f"config file not found: {path}")
    try:
        return json.loads(p.read_text())
    except json.JSONDecodeError as exc:
        raise ConfigError(f"invalid JSON in config file {path}: {exc}") from exc


def _load_env() -> dict[str, Any]:
    # Flat env -> nested config
    intervals = {}
    for key, field in [
        ("BRIDGE_PHASE1_SECONDS", "phase1_seconds"),
        ("BRIDGE_PHASE2_SECONDS", "phase2_seconds"),
        ("BRIDGE_PHASE3_SECONDS", "phase3_seconds"),
        ("BRIDGE_OUTBOX_DRAIN_SECONDS", "outbox_drain_seconds"),
        ("BRIDGE_LOOP_SLEEP_SECONDS", "loop_sleep_seconds"),
    ]:
        if os.getenv(key):
            intervals[field] = int(os.environ[key])

    raw: dict[str, Any] = {
        "mode": os.getenv("BRIDGE_MODE"),
        "db_path": os.getenv("BRIDGE_DB_PATH"),
        "worker_id": os.getenv("BRIDGE_WORKER_ID"),
        "paperclip_base_url": os.getenv("PAPERCLIP_BASE_URL"),
        "paperclip_token": os.getenv("PAPERCLIP_TOKEN"),
        "beads_bin": os.getenv("BEADS_BIN"),
        "gastown_bin": os.getenv("GASTOWN_BIN"),
        "metrics": {"file_path": os.getenv("BRIDGE_METRICS_FILE")},
        "alerts": {
            "webhook_url": os.getenv("BRIDGE_ALERT_WEBHOOK"),
            "dlq_warn_threshold": os.getenv("BRIDGE_DLQ_WARN_THRESHOLD"),
        },
        "intervals": intervals,
    }

    # remove empty/nulls recursively
    def clean(obj: Any) -> Any:
        if isinstance(obj, dict):
            return {k: clean(v) for k, v in obj.items() if v not in (None, "", {})}
        return obj

    return clean(raw)


def _validate_positive_int(name: str, value: Any) -> int:
    try:
        out = int(value)
    except Exception as exc:
        raise ConfigError(f"{name} must be an integer") from exc
    if out <= 0:
        raise ConfigError(f"{name} must be > 0")
    return out


def _validate(data: dict[str, Any]) -> RuntimeConfig:
    mode = data.get("mode", "mock")
    if mode not in {"mock", "real"}:
        raise ConfigError("mode must be one of: mock, real")

    intervals_raw = data.get("intervals", {})
    intervals = IntervalConfig(
        phase1_seconds=_validate_positive_int("intervals.phase1_seconds", intervals_raw.get("phase1_seconds", 30)),
        phase2_seconds=_validate_positive_int("intervals.phase2_seconds", intervals_raw.get("phase2_seconds", 60)),
        phase3_seconds=_validate_positive_int("intervals.phase3_seconds", intervals_raw.get("phase3_seconds", 120)),
        outbox_drain_seconds=_validate_positive_int(
            "intervals.outbox_drain_seconds", intervals_raw.get("outbox_drain_seconds", 15)
        ),
        loop_sleep_seconds=_validate_positive_int("intervals.loop_sleep_seconds", intervals_raw.get("loop_sleep_seconds", 1)),
    )

    alerts_raw = data.get("alerts", {})
    dlq_warn = _validate_positive_int("alerts.dlq_warn_threshold", alerts_raw.get("dlq_warn_threshold", 1))
    alerts = AlertConfig(webhook_url=alerts_raw.get("webhook_url"), dlq_warn_threshold=dlq_warn)

    metrics_raw = data.get("metrics", {})
    metrics = MetricsConfig(file_path=str(metrics_raw.get("file_path", "bridge.metrics.json")))

    cfg = RuntimeConfig(
        mode=mode,
        db_path=str(data.get("db_path", "bridge.db")),
        worker_id=str(data.get("worker_id", "worker-1")),
        intervals=intervals,
        metrics=metrics,
        alerts=alerts,
        paperclip_base_url=data.get("paperclip_base_url"),
        paperclip_token=data.get("paperclip_token"),
        beads_bin=str(data.get("beads_bin", "bd")),
        gastown_bin=str(data.get("gastown_bin", "gt")),
    )

    if cfg.mode == "real" and not cfg.paperclip_base_url:
        raise ConfigError("paperclip_base_url is required when mode=real")

    return cfg


def load_config(config_path: str | None = None) -> RuntimeConfig:
    defaults = {
        "mode": "mock",
        "db_path": "bridge.db",
        "worker_id": "worker-1",
        "intervals": {
            "phase1_seconds": 30,
            "phase2_seconds": 60,
            "phase3_seconds": 120,
            "outbox_drain_seconds": 15,
            "loop_sleep_seconds": 1,
        },
        "metrics": {"file_path": "bridge.metrics.json"},
        "alerts": {"dlq_warn_threshold": 1},
        "beads_bin": "bd",
        "gastown_bin": "gt",
    }
    merged = _deep_merge(defaults, _load_file(config_path))
    merged = _deep_merge(merged, _load_env())
    return _validate(merged)
