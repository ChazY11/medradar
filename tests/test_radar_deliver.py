"""Delivery: the digest leaves the page, and every attempt is recorded."""
from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

from medradar.radar.deliver import deliver, render_text, send_webhook
from medradar.radar.human import HumanStore


def _payload() -> dict:
    return {
        "empty": False,
        "window": {"hours": 24},
        "totals": {"arrived": 1660, "feed": 17, "review": 17, "excluded": 1626, "safety": 0},
        "items": [{"observation_id": "o1", "title": "Patient monitor SpO2 accuracy",
                   "source": "crossref", "published_at": "2026-11-19",
                   "source_url": "https://example.invalid/1", "duplicates": 2}],
        "safety": [],
        "review": {"count": 17, "categories": []},
        "warnings": [{"code": "future_dated", "count": 2},
                     {"code": "blocked_sources", "sources": ["gehealthcare_official"]}],
    }


def test_the_text_carries_the_counts_the_items_and_the_caveats():
    text = render_text(_payload())
    assert "1,660" in text or "1660" in text
    assert "17" in text
    assert "Patient monitor SpO2 accuracy" in text
    assert "https://example.invalid/1" in text
    assert "未来" in text or "future" in text
    assert "gehealthcare_official" in text


def test_an_empty_day_says_so_instead_of_printing_zeros():
    payload = _payload()
    payload.update({"empty": True, "totals": {"arrived": 0, "feed": 0, "excluded": 0}})
    text = render_text(payload)
    assert "没有新记录" in text
    assert "值得看" not in text


def test_a_dry_run_sends_nothing_and_leaves_a_row(tmp_path: Path):
    store = HumanStore(str(tmp_path / "human.db"))
    outcome = deliver(_payload(), human=store, channels={}, dry_run=True)
    assert outcome["dry_run"] is True
    rows = store.deliveries()
    assert rows and rows[0]["channel"] == "dry-run"
    assert rows[0]["status"] == "skipped"
    store.close()


def test_without_a_channel_it_still_refuses_to_send(tmp_path: Path):
    store = HumanStore(str(tmp_path / "human.db"))
    outcome = deliver(_payload(), human=store, channels={}, dry_run=False)
    assert outcome["dry_run"] is True
    assert store.deliveries()[0]["status"] == "skipped"
    store.close()


class _Collector(BaseHTTPRequestHandler):
    received: list[dict] = []

    def do_POST(self):  # noqa: N802 - http.server API
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length).decode("utf-8")
        _Collector.received.append(json.loads(body))
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"ok")

    def log_message(self, *args):  # keep the test output clean
        return


def test_a_webhook_receives_the_text_and_the_payload(tmp_path: Path):
    _Collector.received = []
    server = HTTPServer(("127.0.0.1", 0), _Collector)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    url = f"http://127.0.0.1:{server.server_port}/hook"
    try:
        store = HumanStore(str(tmp_path / "human.db"))
        outcome = deliver(_payload(), human=store, channels={"webhook": url}, dry_run=False)
        assert outcome["dry_run"] is False
        assert outcome["results"][0]["ok"] is True
        assert _Collector.received and "text" in _Collector.received[0]
        assert _Collector.received[0]["digest"]["totals"]["arrived"] == 1660
        rows = store.deliveries()
        assert rows[0]["channel"] == "webhook" and rows[0]["status"] == "ok"
        store.close()
    finally:
        server.shutdown()


def test_a_failed_webhook_is_recorded_not_swallowed(tmp_path: Path):
    store = HumanStore(str(tmp_path / "human.db"))
    bad = send_webhook("http://127.0.0.1:9/nope", "x", {"a": 1}, timeout=2)
    assert bad["ok"] is False
    outcome = deliver(_payload(), human=store, channels={"webhook": "http://127.0.0.1:9/nope"},
                      dry_run=False)
    assert outcome["results"][0]["ok"] is False
    rows = store.deliveries()
    assert rows[0]["status"] == "failed"
    store.close()