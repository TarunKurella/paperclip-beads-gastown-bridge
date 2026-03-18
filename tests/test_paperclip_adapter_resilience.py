from __future__ import annotations

import io
import urllib.error

from bridge.adapters.paperclip import PaperclipHTTPAdapter


class _Resp:
    def __init__(self, payload: bytes):
        self._payload = payload

    def read(self) -> bytes:
        return self._payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


def test_request_retries_on_5xx_then_succeeds(monkeypatch):
    calls = {"n": 0}

    def fake_urlopen(req, timeout=0):
        calls["n"] += 1
        if calls["n"] == 1:
            raise urllib.error.HTTPError(req.full_url, 503, "boom", hdrs=None, fp=io.BytesIO(b"x"))
        return _Resp(b'{"items": []}')

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    adapter = PaperclipHTTPAdapter(base_url="http://127.0.0.1:3100", retries=2)
    out = adapter._request("items")
    assert out == {"items": []}
    assert calls["n"] == 2


def test_request_raises_clear_error_after_retries(monkeypatch):
    def fake_urlopen(req, timeout=0):
        raise urllib.error.URLError("offline")

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    adapter = PaperclipHTTPAdapter(base_url="http://127.0.0.1:3100", retries=1)

    try:
        adapter._request("items")
        assert False, "expected failure"
    except RuntimeError as exc:
        assert "paperclip request failed" in str(exc)
        assert "items" in str(exc)
