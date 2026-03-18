from __future__ import annotations

from bridge.plugin_scaffold import create_plugin_scaffold


def test_create_plugin_scaffold(tmp_path):
    out = create_plugin_scaffold(str(tmp_path / "plugin"), package_name="@acme/plugin-bridge-ops")

    assert (out / "package.json").exists()
    assert (out / "README.md").exists()
    assert (out / "src" / "manifest.ts").exists()
    assert (out / "src" / "worker.ts").exists()
    assert (out / "src" / "ui" / "index.tsx").exists()

    manifest = (out / "src" / "manifest.ts").read_text()
    worker = (out / "src" / "worker.ts").read_text()
    readme = (out / "README.md").read_text()
    assert "acme.plugin-bridge-ops" in manifest
    assert "BRIDGE_BIN" in worker
    assert "bridge-guardrail-check" in worker
    assert "pip install paperclip-beads-gastown-bridge" in readme


def test_create_plugin_scaffold_with_ci(tmp_path):
    out = create_plugin_scaffold(str(tmp_path / "plugin-ci"), package_name="@acme/plugin-bridge-ops", with_ci=True)
    assert (out / "tsconfig.json").exists()
    assert (out / ".github" / "workflows" / "plugin-ci.yml").exists()
