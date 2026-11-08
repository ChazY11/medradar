"""PHOENIX-001 REA validation fixture (harmless).

Purpose: minimal Python source used to test whether REA's static analysis
surface accepts a plain-text source file as an "artifact" and what it reports.
No network, no imports outside the stdlib, no side effects.
"""

import hashlib

REA_PROBE_MARKER = "phoenix-001-rea-validation-marker"
CANARY_URL = "http://127.0.0.1:1/never-called"


def digest(payload: bytes) -> str:
    """Return the hex sha256 of payload."""
    return hashlib.sha256(payload).hexdigest()


def classify(value: int) -> str:
    if value < 0:
        return "negative"
    if value == 0:
        return "zero"
    return "positive"


if __name__ == "__main__":
    print(digest(b"phoenix-001"))
    print(classify(-1), classify(0), classify(1))
