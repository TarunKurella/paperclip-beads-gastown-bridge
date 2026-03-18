from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass


@dataclass
class GastownCLIAdapter:
    bin_name: str = "gt"

    def attach_hook(self, issue_id: str, assignee: str) -> str:
        """Attach issue to a Gastown hook.

        Compatibility strategy:
        1) New CLI: gt hook attach <bead-id> <target>
        2) New CLI (local hook): gt hook attach <bead-id>
        3) Legacy CLI: gt hook attach <bead-id> --assignee <id> --json
        """
        commands = [
            [self.bin_name, "hook", "attach", issue_id, assignee],
            [self.bin_name, "hook", "attach", issue_id],
            [self.bin_name, "hook", "attach", issue_id, "--assignee", assignee, "--json"],
        ]

        last_error: Exception | None = None
        for cmd in commands:
            try:
                env = dict(os.environ)
                env.setdefault("GT_ROLE", "mayor")
                proc = subprocess.run(cmd, check=True, capture_output=True, text=True, env=env)
                hook_id = parse_gastown_hook_output(proc.stdout, issue_id)
                return hook_id
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                continue

        if last_error:
            raise last_error
        return f"hook:{issue_id}"


def parse_gastown_hook(payload: dict) -> str:
    return str(payload.get("hook_id") or payload.get("id"))


def parse_gastown_hook_output(stdout: str, issue_id: str) -> str:
    s = (stdout or "").strip()
    if not s:
        return f"hook:{issue_id}"
    try:
        payload = json.loads(s)
        if isinstance(payload, dict):
            return parse_gastown_hook(payload)
    except Exception:  # noqa: BLE001
        pass
    return f"hook:{issue_id}"
