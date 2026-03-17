from __future__ import annotations

import json

import pytest

from bridge.config import ConfigError, load_config


def test_load_config_from_file_and_env_override(tmp_path, monkeypatch):
    cfg_path = tmp_path / "config.json"
    cfg_path.write_text(
        json.dumps(
            {
                "mode": "mock",
                "db_path": str(tmp_path / "a.db"),
                "intervals": {"phase1_seconds": 99},
            }
        )
    )
    monkeypatch.setenv("BRIDGE_PHASE1_SECONDS", "3")
    monkeypatch.setenv("BRIDGE_DB_PATH", str(tmp_path / "b.db"))

    cfg = load_config(str(cfg_path))
    assert cfg.intervals.phase1_seconds == 3
    assert cfg.db_path.endswith("b.db")


def test_real_mode_requires_paperclip_base_url(tmp_path):
    cfg_path = tmp_path / "config.json"
    cfg_path.write_text(json.dumps({"mode": "real"}))

    with pytest.raises(ConfigError):
        load_config(str(cfg_path))
