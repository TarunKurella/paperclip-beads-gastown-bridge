from __future__ import annotations

from bridge.preflight import package_hint, run_preflight


def test_package_hint_rhel():
    assert package_hint("rhel", "tmux").startswith("dnf install -y")


def test_run_preflight_shape():
    result = run_preflight()
    assert "ok" in result
    assert "os" in result
    assert isinstance(result.get("checks"), list)
    assert any(c["name"] == "runtime_dir" for c in result["checks"])
