"""Freeze the S-028 pre-registration and record its hashes.

Run ONCE, before any model fit. The resulting artifact proves the protocol text was
not edited after results were seen.
"""
from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

STUDY = Path(__file__).resolve().parents[1]
FILES = ["PRE_REGISTRATION.md", "HYPOTHESIS_REGISTRY.md"]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--suffix", default="", help="e.g. _amendment1 keeps the original freeze intact")
    args = parser.parse_args()
    payload = {
        "study": "S-028",
        "frozen_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "note": ("Hashes of the protocol documents as frozen BEFORE any S-028 model was fitted. "
                 "Only label-census and feasibility statistics existed at freeze time."),
        "files": {},
        "input_database": {
            "path": r"D:\DEPPSKK\worktrees\integration-v2\data\research.sqlite",
            "sha256": "dd241bfec138d7977d7eb8f4c1db25119d59b6fe7ff573060b24d14eeeb71e0d",
            "size_bytes": 289443840,
        },
    }
    for name in FILES:
        path = STUDY / name
        payload["files"][name] = {"sha256": sha256(path),
                                  "size_bytes": path.stat().st_size}
    out = STUDY / "artifacts" / f"prereg_freeze{args.suffix}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                   encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    print(f"\nwrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
