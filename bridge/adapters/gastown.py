from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass


@dataclass
class GastownCLIAdapter:
    bin_name: str = "gt"

    def attach_hook(self, issue_id: str, assignee: str) -> str:
        proc = subprocess.run(
            [self.bin_name, "hook", "attach", issue_id, "--assignee", assignee, "--json"],
            check=True,
            capture_output=True,
            text=True,
        )
        payload = json.loads(proc.stdout)
        return str(payload["hook_id"])


def parse_gastown_hook(payload: dict) -> str:
    return str(payload["hook_id"])
