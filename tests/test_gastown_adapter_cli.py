from __future__ import annotations

import subprocess

from bridge.adapters.gastown import GastownCLIAdapter, parse_gastown_hook_output


def _cp(stdout: str = "") -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(args=["gt"], returncode=0, stdout=stdout, stderr="")


def test_attach_hook_falls_back_to_local_when_target_fails(monkeypatch):
    calls: list[list[str]] = []

    def fake_run(args, check, capture_output, text, **kwargs):
        calls.append(args)
        if len(calls) == 1:
            raise subprocess.CalledProcessError(returncode=1, cmd=args)
        return _cp("ok")

    monkeypatch.setattr(subprocess, "run", fake_run)
    hook_id = GastownCLIAdapter("gt").attach_hook("gt-abc", "some-target")

    assert calls[0] == ["gt", "hook", "attach", "gt-abc", "some-target"]
    assert calls[1] == ["gt", "hook", "attach", "gt-abc"]
    assert hook_id == "hook:gt-abc"


def test_parse_json_hook_output():
    assert parse_gastown_hook_output('{"hook_id":"h-1"}', "gt-1") == "h-1"
