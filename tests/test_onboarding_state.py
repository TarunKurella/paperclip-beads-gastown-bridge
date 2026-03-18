from __future__ import annotations

from pathlib import Path

from bridge.ux import load_onboarding_state, save_onboarding_state


def test_onboarding_state_roundtrip(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert load_onboarding_state()["completed"] is False

    save_onboarding_state("config.real.local.json")
    state = load_onboarding_state()
    assert state["completed"] is True
    assert state["config_path"] == "config.real.local.json"
    assert Path(".runtime/onboarding-state.json").exists()
