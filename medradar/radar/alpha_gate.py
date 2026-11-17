"""Access gate for the public Radar alpha.

This is the only thing standing between the internet and a read-only intelligence database, so
it is deliberately small, explicit and testable:

* **authentication.** HTTP Basic over TLS, verified against a PBKDF2-SHA256 hash. No plaintext
  password is stored in a unit file, in the repository or in a log line.
* **route allowlist.** Only the Radar SPA routes and the read-only Radar API are reachable.
  Everything else - the workbench API, exports, review actions, the OpenAPI schema - returns
  404, not 403: an unauthenticated scanner learns nothing about what exists.
* **read-only methods.** GET/HEAD only. The Radar API is read-only by construction; the gate
  enforces it as well so a future write route cannot become public by accident.
* **failure rate limit.** Repeated wrong credentials from one address are locked out for a
  window, which is what makes a short password guessable-in-principle but not in practice.
* **response headers.** Sent on every response, including 401/404.

It is WSGI/ASGI middleware rather than a reverse-proxy rule so that the allowlist is covered by
the repository's tests. The proxy in front of it terminates TLS and forwards the real client
address; ``trust_proxy`` is only enabled when the listener is bound to loopback behind it.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import logging
import os
import re
import threading
import time
from collections import defaultdict, deque
from typing import Any, Callable

LOGGER = logging.getLogger("medradar.radar.alpha")

REALM = "MedRadar Radar Alpha"
HASH_SCHEME = "pbkdf2_sha256"
DEFAULT_ITERATIONS = 240_000

#: Pages the alpha exposes. React Router renders these; the document is the SPA index.
PUBLIC_PAGES = frozenset({"/", "/radar", "/radar/", "/radar/technology-map", "/radar/technology-map/"})
#: Exact non-page paths that the app itself needs.
PUBLIC_EXACT = frozenset({"/favicon.svg", "/api/meta"})
#: Liveness probe: no data, no database access. Unauthenticated so a proxy or an operator's
#: monitoring check does not have to hold the alpha credentials.
OPEN_PATHS = frozenset({"/healthz"})
#: Read-only API namespaces. Everything not listed here is invisible.
PUBLIC_PREFIXES = ("/api/radar/",)
#: Vite emits a flat build: index-<hash>.js / index-<hash>.css next to index.html.
PUBLIC_ASSET = re.compile(r"^/index-[A-Za-z0-9_-]+\.(?:js|css)$")
SAFE_METHODS = frozenset({"GET", "HEAD"})

SECURITY_HEADERS = (
    (b"x-content-type-options", b"nosniff"),
    (b"x-frame-options", b"DENY"),
    (b"referrer-policy", b"same-origin"),
    (b"permissions-policy", b"camera=(), microphone=(), geolocation=()"),
    (b"cache-control", b"no-store"),
)


def hash_password(password: str, *, iterations: int = DEFAULT_ITERATIONS) -> str:
    """Encode a password as ``pbkdf2_sha256$iterations$salt$digest`` (hex)."""
    if not password or len(password) < 12:
        raise ValueError("the alpha password must be at least 12 characters")
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, int(iterations))
    return f"{HASH_SCHEME}${int(iterations)}${salt.hex()}${digest.hex()}"


def verify_password(password: str, encoded: str) -> bool:
    """Constant-time verification of an encoded password. A malformed hash never authenticates."""
    try:
        scheme, iterations, salt_hex, digest_hex = str(encoded).split("$", 3)
        if scheme != HASH_SCHEME:
            return False
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(digest_hex)
        actual = hashlib.pbkdf2_hmac("sha256", str(password).encode("utf-8"), salt, int(iterations))
    except (ValueError, binascii.Error):
        return False
    return hmac.compare_digest(actual, expected)


def path_allowed(path: str) -> bool:
    """The allowlist, as one pure function so it can be tested directly."""
    if path in PUBLIC_PAGES or path in PUBLIC_EXACT or path in OPEN_PATHS:
        return True
    if path.startswith(PUBLIC_PREFIXES):
        # The API namespace itself, not a path-traversal trick through it.
        return ".." not in path and "\\" not in path
    return bool(PUBLIC_ASSET.match(path))


class FailureLimiter:
    """Per-address failures inside a window, with a lockout once the budget is spent."""

    def __init__(self, *, max_failures: int = 10, window_seconds: float = 600.0,
                 lockout_seconds: float = 900.0, max_addresses: int = 4096) -> None:
        self.max_failures = int(max_failures)
        self.window_seconds = float(window_seconds)
        self.lockout_seconds = float(lockout_seconds)
        self.max_addresses = int(max_addresses)
        self._failures: dict[str, deque[float]] = defaultdict(deque)
        self._locked_until: dict[str, float] = {}
        self._lock = threading.Lock()

    def locked(self, address: str, *, now: float | None = None) -> float:
        """Seconds remaining in the lockout, or 0 when the address may try again."""
        moment = time.monotonic() if now is None else now
        with self._lock:
            until = self._locked_until.get(address, 0.0)
            if until <= moment:
                self._locked_until.pop(address, None)
                return 0.0
            return round(until - moment, 1)

    def record_failure(self, address: str, *, now: float | None = None) -> bool:
        """Record a failure. Returns True when this failure triggered a lockout."""
        moment = time.monotonic() if now is None else now
        with self._lock:
            if len(self._failures) > self.max_addresses:
                # Bound memory: drop the oldest half rather than grow without limit.
                for stale in list(self._failures)[: self.max_addresses // 2]:
                    self._failures.pop(stale, None)
                    self._locked_until.pop(stale, None)
            bucket = self._failures[address]
            bucket.append(moment)
            while bucket and moment - bucket[0] > self.window_seconds:
                bucket.popleft()
            if len(bucket) >= self.max_failures:
                self._locked_until[address] = moment + self.lockout_seconds
                bucket.clear()
                return True
            return False

    def record_success(self, address: str) -> None:
        with self._lock:
            self._failures.pop(address, None)
            self._locked_until.pop(address, None)


def _client_address(scope: dict[str, Any], *, trust_proxy: bool) -> str:
    headers = {key.lower(): value for key, value in scope.get("headers") or []}
    if trust_proxy:
        forwarded = headers.get(b"cf-connecting-ip") or headers.get(b"x-real-ip")
        if forwarded:
            return forwarded.decode("latin-1").strip()
        chain = headers.get(b"x-forwarded-for")
        if chain:
            return chain.decode("latin-1").split(",")[0].strip()
    client = scope.get("client") or ("unknown", 0)
    return str(client[0] or "unknown")


def _basic_credentials(scope: dict[str, Any]) -> tuple[str, str] | None:
    for key, value in scope.get("headers") or []:
        if key.lower() != b"authorization":
            continue
        text = value.decode("latin-1").strip()
        if not text.lower().startswith("basic "):
            return None
        try:
            decoded = base64.b64decode(text[6:].strip(), validate=True).decode("utf-8")
        except (binascii.Error, UnicodeDecodeError):
            return None
        username, separator, password = decoded.partition(":")
        if not separator:
            return None
        return username, password
    return None


class AlphaGate:
    """ASGI middleware implementing the public-alpha access policy."""

    def __init__(self, app: Callable, *, username: str, password_hash: str,
                 trust_proxy: bool = False, limiter: FailureLimiter | None = None,
                 secure_transport: bool = True) -> None:
        if not username or not password_hash:
            raise ValueError("the alpha gate requires a username and a password hash")
        self.app = app
        self.username = username
        self.password_hash = password_hash
        self.trust_proxy = bool(trust_proxy)
        self.limiter = limiter or FailureLimiter()
        self.secure_transport = bool(secure_transport)

    async def __call__(self, scope: dict[str, Any], receive: Callable, send: Callable) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        path = str(scope.get("path") or "/")
        method = str(scope.get("method") or "GET").upper()
        address = _client_address(scope, trust_proxy=self.trust_proxy)

        if path in OPEN_PATHS:
            if method not in SAFE_METHODS:
                await self._plain(send, 405, b"Method Not Allowed\n", scope,
                                  extra_headers=((b"allow", b"GET, HEAD"),))
                return
            await self.app(scope, receive, self._secured(send, scope))
            return

        if not path_allowed(path):
            await self._plain(send, 404, b"Not Found\n", scope)
            return
        if method not in SAFE_METHODS:
            await self._plain(send, 405, b"Method Not Allowed\n", scope,
                              extra_headers=((b"allow", b"GET, HEAD"),))
            return

        remaining = self.limiter.locked(address)
        if remaining > 0:
            LOGGER.warning("alpha auth locked out address=%s path=%s retry_after=%ss",
                           address, path, remaining)
            await self._plain(
                send, 429, b"Too Many Attempts\n", scope,
                extra_headers=((b"retry-after", str(int(remaining)).encode()),),
            )
            return

        credentials = _basic_credentials(scope)
        valid = bool(
            credentials
            and hmac.compare_digest(str(credentials[0]), self.username)
            and verify_password(credentials[1], self.password_hash)
        )
        if not valid:
            triggered = self.limiter.record_failure(address)
            LOGGER.warning("alpha auth failure address=%s path=%s method=%s lockout=%s",
                           address, path, method, triggered)
            await self._unauthorized(send, scope)
            return

        self.limiter.record_success(address)
        await self.app(scope, receive, self._secured(send, scope))

    # ------------------------------------------------------------------ responses
    def _secured(self, send: Callable, scope: dict[str, Any]) -> Callable:
        async def wrapped(message: dict[str, Any]) -> None:
            if message.get("type") == "http.response.start":
                headers = list(message.get("headers") or [])
                headers.extend(SECURITY_HEADERS)
                if self._is_https(scope):
                    headers.append((b"strict-transport-security", b"max-age=31536000"))
                headers.append((b"x-robots-tag", b"noindex, nofollow"))
                message = {**message, "headers": headers}
            await send(message)

        return wrapped

    def _is_https(self, scope: dict[str, Any]) -> bool:
        if scope.get("scheme") == "https":
            return True
        if not self.trust_proxy:
            return False
        for key, value in scope.get("headers") or []:
            if key.lower() == b"x-forwarded-proto":
                return value.decode("latin-1").split(",")[0].strip().lower() == "https"
        return False

    async def _unauthorized(self, send: Callable, scope: dict[str, Any]) -> None:
        await self._plain(
            send, 401, b"Authentication required\n", scope,
            extra_headers=((b"www-authenticate", f'Basic realm="{REALM}", charset="UTF-8"'.encode()),),
        )

    async def _plain(self, send: Callable, status: int, body: bytes, scope: dict[str, Any],
                     *, extra_headers: tuple[tuple[bytes, bytes], ...] = ()) -> None:
        headers = [
            (b"content-type", b"text/plain; charset=utf-8"),
            (b"content-length", str(len(body)).encode()),
            (b"x-robots-tag", b"noindex, nofollow"),
            *SECURITY_HEADERS,
            *extra_headers,
        ]
        if self._is_https(scope):
            headers.append((b"strict-transport-security", b"max-age=31536000"))
        await send({"type": "http.response.start", "status": status, "headers": headers})
        await send({"type": "http.response.body", "body": body})


def install_alpha_gate(app: Callable) -> Callable:
    """Wrap ``app`` when the environment enables the gate; otherwise return it unchanged.

    Fails closed: ``MEDRADAR_ALPHA_GATE=1`` with a missing or malformed hash raises at import,
    so a misconfigured deployment does not serve an unauthenticated database.
    """
    if os.environ.get("MEDRADAR_ALPHA_GATE") != "1":
        return app
    username = str(os.environ.get("MEDRADAR_ALPHA_USER") or "").strip()
    password_hash = str(os.environ.get("MEDRADAR_ALPHA_HASH") or "").strip()
    if not username or not password_hash:
        raise RuntimeError(
            "MEDRADAR_ALPHA_GATE=1 requires MEDRADAR_ALPHA_USER and MEDRADAR_ALPHA_HASH"
        )
    trust_proxy = os.environ.get("MEDRADAR_ALPHA_TRUST_PROXY") == "1"
    LOGGER.info("public alpha gate enabled user=%s trust_proxy=%s", username, trust_proxy)
    return AlphaGate(app, username=username, password_hash=password_hash,
                     trust_proxy=trust_proxy)


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Generate a MedRadar alpha password hash.")
    parser.add_argument("--hash", dest="password", required=True,
                        help="plaintext password to hash (it is not written anywhere)")
    args = parser.parse_args(argv)
    print(hash_password(args.password))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
