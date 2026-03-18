from __future__ import annotations

from bridge.adapters.paperclip import PaperclipHTTPAdapter


def test_checkout_release_and_comment_call_api_paths(monkeypatch):
    calls = []

    def fake_request(self, path, method="GET", body=None):
        calls.append((path, method, body))
        return {"ok": True}

    monkeypatch.setattr(PaperclipHTTPAdapter, "_request", fake_request)

    a = PaperclipHTTPAdapter(base_url="http://127.0.0.1:3100")
    a.checkout_item("pc-1", "agent-1")
    a.release_item("pc-1", "agent-1")
    a.add_comment("pc-1", "hello")

    assert calls[0][0] == "api/issues/pc-1/checkout"
    assert calls[1][0] == "api/issues/pc-1/release"
    assert calls[2][0] == "api/issues/pc-1/comments"


def test_set_status_prefers_api_issue_patch(monkeypatch):
    calls = []

    def fake_request(self, path, method="GET", body=None):
        calls.append((path, method, body))
        return {"ok": True}

    monkeypatch.setattr(PaperclipHTTPAdapter, "_request", fake_request)
    a = PaperclipHTTPAdapter(base_url="http://127.0.0.1:3100")
    a.set_status("pc-1", "done")
    assert calls[0][0] == "api/issues/pc-1"
