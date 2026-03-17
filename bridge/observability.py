from __future__ import annotations

import json
import time
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


class JsonLogger:
    def __init__(self, component: str = "bridge"):
        self.component = component

    def log(self, level: str, message: str, **fields: Any) -> None:
        payload = {
            "ts": int(time.time()),
            "level": level,
            "component": self.component,
            "msg": message,
            **fields,
        }
        print(json.dumps(payload, sort_keys=True))

    def info(self, message: str, **fields: Any) -> None:
        self.log("info", message, **fields)

    def warning(self, message: str, **fields: Any) -> None:
        self.log("warning", message, **fields)

    def error(self, message: str, **fields: Any) -> None:
        self.log("error", message, **fields)


@dataclass
class Metrics:
    file_path: str
    counters: dict[str, int] = field(default_factory=dict)

    def inc(self, key: str, value: int = 1) -> None:
        self.counters[key] = int(self.counters.get(key, 0)) + value

    def set(self, key: str, value: int) -> None:
        self.counters[key] = int(value)

    def snapshot(self) -> dict[str, Any]:
        return {"ts": int(time.time()), "counters": dict(sorted(self.counters.items()))}

    def flush(self) -> None:
        p = Path(self.file_path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(self.snapshot(), indent=2, sort_keys=True))


class AlertSink:
    def __init__(self, logger: JsonLogger, webhook_url: str | None = None):
        self.logger = logger
        self.webhook_url = webhook_url

    def send(self, severity: str, message: str, **context: Any) -> None:
        self.logger.warning("alert", severity=severity, alert_message=message, **context)
        if not self.webhook_url:
            return
        body = json.dumps({"severity": severity, "message": message, "context": context}).encode()
        req = urllib.request.Request(self.webhook_url, method="POST", data=body)
        req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=10):  # nosec B310
                pass
        except Exception as exc:
            self.logger.error("alert_webhook_failed", error=str(exc), severity=severity)
