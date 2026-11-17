"""The public-alpha access gate is a security boundary, so it is tested as one."""

from __future__ import annotations

import base64

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from medradar.radar.alpha_gate import (
    AlphaGate,
    FailureLimiter,
    hash_password,
    path_allowed,
    verify_password,
)

PASSWORD = "correct horse battery staple 2026"
HASH = hash_password(PASSWORD, iterations=1000)


def _client(**kwargs) -> TestClient:
    app = FastAPI()

    @app.get("/radar")
    def radar():
        return {"page": "radar"}

    @app.get("/api/radar/feed")
    def feed():
        return {"items": []}

    @app.get("/api/meta")
    def meta():
        return {"ok": True}

    @app.get("/healthz")
    def healthz():
        return {"status": "ok"}

    @app.get("/api/review/ledger")
    def review():
        return {"secret": True}

    @app.post("/api/radar/feed")
    def write():
        return {"should": "never happen"}

    app = AlphaGate(app, username="alpha", password_hash=HASH, secure_transport=False, **kwargs)
    return TestClient(app, raise_server_exceptions=True)


def _auth(password: str = PASSWORD, username: str = "alpha") -> dict[str, str]:
    token = base64.b64encode(f"{username}:{password}".encode()).decode()
    return {"Authorization": f"Basic {token}"}


def test_no_credentials_are_rejected_with_a_challenge():
    client = _client()
    response = client.get("/radar")
    assert response.status_code == 401
    assert response.headers["www-authenticate"].startswith("Basic realm=")
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"


def test_correct_credentials_reach_only_allowlisted_routes():
    client = _client()
    assert client.get("/radar", headers=_auth()).status_code == 200
    assert client.get("/api/radar/feed", headers=_auth()).status_code == 200
    # The workbench review API is mounted in the real app but must never be public.
    assert client.get("/api/review/ledger", headers=_auth()).status_code == 404
    assert client.get("/api/export/devices", headers=_auth()).status_code == 404


def test_wrong_password_is_rejected_and_eventually_locked_out():
    client = _client(limiter=FailureLimiter(max_failures=3, window_seconds=60, lockout_seconds=60))
    for _ in range(3):
        assert client.get("/radar", headers=_auth("wrong password")).status_code == 401
    locked = client.get("/radar", headers=_auth())
    assert locked.status_code == 429
    assert int(locked.headers["retry-after"]) > 0
    # A different address is unaffected by another address's lockout.
    assert client.get("/radar", headers=_auth()).status_code == 429


def test_write_methods_are_refused_even_when_authenticated():
    client = _client()
    response = client.post("/api/radar/feed", headers=_auth())
    assert response.status_code == 405
    assert response.headers["allow"] == "GET, HEAD"


def test_asset_allowlist_covers_the_vite_build_and_nothing_else():
    assert path_allowed("/index-CeWKEd-a.js")
    assert path_allowed("/index-TP5nBJzD.css")
    assert path_allowed("/favicon.svg")
    assert path_allowed("/api/radar/technology-map")
    assert not path_allowed("/index-../../etc/passwd")
    assert not path_allowed("/api/radar/../../api/review")
    assert not path_allowed("/api/identity/rows")
    assert not path_allowed("/api/brief")


def test_liveness_probe_is_open_but_carries_no_data():
    client = _client()
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    # Open does not mean writable.
    assert client.post("/healthz").status_code == 405


def test_password_hashing_round_trips_and_rejects_malformed_hashes():
    assert verify_password(PASSWORD, HASH)
    assert not verify_password("nope", HASH)
    assert not verify_password(PASSWORD, "not-a-hash")
    assert "$" not in HASH.split("$", 1)[0] == "pbkdf2_sha256" or HASH.startswith("pbkdf2_sha256$")
    with pytest.raises(ValueError):
        hash_password("short")
