from __future__ import annotations

import os
import platform
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class Check:
    name: str
    ok: bool
    detail: str
    fix: str | None = None


def detect_os() -> dict[str, str]:
    system = platform.system()
    info = {"system": system, "release": platform.release()}
    if system == "Linux":
        os_release = Path("/etc/os-release")
        if os_release.exists():
            data: dict[str, str] = {}
            for line in os_release.read_text().splitlines():
                if "=" in line:
                    k, v = line.split("=", 1)
                    data[k] = v.strip('"')
            info["id"] = data.get("ID", "linux")
            info["name"] = data.get("PRETTY_NAME", data.get("NAME", "Linux"))
        else:
            info["id"] = "linux"
            info["name"] = "Linux"
    elif system == "Darwin":
        info["id"] = "macos"
        info["name"] = "macOS"
    else:
        info["id"] = system.lower()
        info["name"] = system
    return info


def package_hint(os_id: str, package: str) -> str:
    if os_id == "macos":
        return f"brew install {package}"
    if os_id in {"rhel", "centos", "fedora", "rocky", "almalinux", "ubi"}:
        return f"dnf install -y {package}"
    if os_id in {"debian", "ubuntu"}:
        return f"apt-get update && apt-get install -y {package}"
    if os_id in {"alpine"}:
        return f"apk add {package}"
    return f"Install '{package}' using your distro package manager"


def run_preflight() -> dict[str, Any]:
    os_info = detect_os()
    os_id = os_info.get("id", "linux")

    checks: list[Check] = []
    for bin_name, pkg in [("python3", "python3"), ("bd", "beads"), ("gt", "gastown"), ("dolt", "dolt"), ("tmux", "tmux")]:
        path = shutil.which(bin_name)
        checks.append(
            Check(
                name=f"bin:{bin_name}",
                ok=bool(path),
                detail=path or "missing",
                fix=None if path else package_hint(os_id, pkg),
            )
        )

    runtime_dir = Path(".runtime")
    checks.append(
        Check(
            name="runtime_dir",
            ok=runtime_dir.exists(),
            detail="present" if runtime_dir.exists() else "missing",
            fix="mkdir -p .runtime",
        )
    )

    ok = all(c.ok for c in checks)
    return {
        "ok": ok,
        "os": os_info,
        "checks": [c.__dict__ for c in checks],
    }
