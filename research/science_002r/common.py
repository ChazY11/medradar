"""Shared paths and helpers for the SCIENCE-002R audit.

The audit never edits the frozen SCIENCE-002 code. It imports it as a library and
resolves the raw cache explicitly, so a run in this worktree cannot rewrite the
artifacts under review.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

STUDY_R = Path(__file__).resolve().parent
DATA_R = STUDY_R / "data"
ARTIFACTS_R = STUDY_R / "artifacts"

#: The cache produced by the original SCIENCE-002 run (raw sources, gitignored).
CACHE_RAW = Path(os.environ.get(
    "MEDRADAR_S2_CACHE",
    str(REPO / "research" / "science_002" / "data" / "cache")))


def raw(name: str) -> Path:
    return CACHE_RAW / name


def zip510k() -> Path:
    return CACHE_RAW / "openfda" / "device-510k-0001-of-0001.json.zip"


def zip_registration_parts() -> list[Path]:
    base = CACHE_RAW / "openfda"
    return sorted(base.glob("device-registrationlisting-*.json.zip"))


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def write_json(path: Path, payload) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = (json.dumps(payload, indent=1, sort_keys=True, default=str) + "\n").encode("utf-8")
    path.write_bytes(data)
    return hashlib.sha256(data).hexdigest()


def environment() -> dict:
    import platform
    return {
        "python": sys.version.split()[0],
        "implementation": platform.python_implementation(),
        "platform": platform.platform(),
        "machine": platform.machine(),
        "cwd": str(Path.cwd()),
        "cache_root": str(CACHE_RAW),
        "cache_env_override": "MEDRADAR_S2_CACHE" in os.environ,
    }