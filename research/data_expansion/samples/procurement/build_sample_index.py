#!/usr/bin/env python
"""Write ``samples/<source_id>/SAMPLES.json`` from the real probe artifacts.

For every sample a probe actually stored, this records:
  * the request URL,
  * the fetch timestamp taken from that probe's ``requests.jsonl`` ledger,
  * ``total_bytes`` / ``stored_bytes`` (so a truncated sample can never be
    mistaken for the whole response),
  * ``sha256_full`` of the complete response bytes and ``sha256_stored`` of the
    bytes on disk, re-verified by hashing the stored file.

Nothing is written for a source that stored no sample (e.g. a probe where every
request failed), which keeps "no sample" honest rather than empty.

Run:  python research/data_expansion/samples/procurement/build_sample_index.py
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve()
ROOT = HERE.parents[2]                       # research/data_expansion
REPO = ROOT.parents[1]

SOURCES = [
    "usaspending",
    "eu_ted",
    "sam_gov",
    "uk_find_a_tender",
    "ocds_registry",
    "china_ccgp",
    "greenhouse",
    "lever",
    "workday_phenom",
    "company_careers_pages",
]


def _ledger_times(probe_dir: Path) -> dict[str, str]:
    """url -> first logged_at for successful requests."""
    out: dict[str, str] = {}
    path = probe_dir / "requests.jsonl"
    if not path.is_file():
        return out
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if row.get("status") and 200 <= int(row["status"]) < 300:
            out.setdefault(str(row.get("url", "")), str(row.get("logged_at", "")))
    return out


def build(source_id: str) -> dict | None:
    probe_path = ROOT / "probes" / source_id / "PROBE_RESULT.json"
    if not probe_path.is_file():
        return None
    probe = json.loads(probe_path.read_text(encoding="utf-8"))
    times = _ledger_times(ROOT / "probes" / source_id)
    entries = []
    for p in probe.get("probes", []) or []:
        sample = p.get("sample")
        if not sample:
            continue
        path = Path(sample["path"])
        stored_sha = hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else ""
        entries.append(
            {
                "file": path.name,
                "request_url": p.get("url", ""),
                "http_status": p.get("status"),
                "fetched_at": times.get(str(p.get("url", "")), ""),
                "total_bytes": sample.get("total_bytes"),
                "stored_bytes": sample.get("stored_bytes"),
                "truncated": sample.get("truncated"),
                "sha256_full": sample.get("sha256_full"),
                "sha256_stored_verified": stored_sha,
                "sha256_matches_probe": stored_sha == sample.get("sha256_stored"),
                "probe_name": p.get("name"),
            }
        )
    if not entries:
        return None
    return {
        "schema": "medradar.external.samples.v1",
        "source_id": source_id,
        "probe_result": str(probe_path.relative_to(REPO)).replace("\\", "/"),
        "n_samples": len(entries),
        "note": (
            "Every file listed here is a real response body stored by the probe. "
            "sha256_full is of the complete response; if truncated is true the file "
            "holds only the first stored_bytes of it."
        ),
        "samples": sorted(entries, key=lambda e: e["file"]),
    }


def main() -> int:
    written = 0
    for source_id in SOURCES:
        payload = build(source_id)
        if payload is None:
            print(f"{source_id:<24} no stored sample -> no SAMPLES.json")
            continue
        out = ROOT / "samples" / source_id / "SAMPLES.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        missing = [e["file"] for e in payload["samples"] if not e["sha256_matches_probe"]]
        print(
            f"{source_id:<24} {payload['n_samples']:>2} sample(s)  hash_mismatch={missing or 'none'}"
        )
        written += 1
    print(f"wrote {written} SAMPLES.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
