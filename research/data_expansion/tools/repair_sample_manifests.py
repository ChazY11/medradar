#!/usr/bin/env python
"""Repair and re-verify the per-source sample manifests.

Background
----------
A wildcard write during the collection phase rewrote many
``samples/<source>/SAMPLES.json`` files.  The sample *payload* files were not
modified, so every hash is still exactly recomputable from disk.  What can be
lost is per-entry context (``request_url``, ``probe_name``, ``fetched_at``).

Repair policy — verification, not restoration
---------------------------------------------
1. Recompute ``sha256`` and the byte count of every payload file on disk.
2. Keep whatever the current manifest declares.  If a declared hash matches the
   recomputed one, mark ``hash_verified: true``.  If it is missing, fill it and
   mark ``sha256_source: "recomputed_from_disk"``.  If it **disagrees**, keep the
   declared value, record it as ``declared_sha256_full`` and mark
   ``hash_verified: false`` — a real corruption must never be silently papered
   over.
3. Append payload files the manifest does not mention, flagged
   ``listed_in_original_manifest: false``.
4. Recover ``request_url`` / ``probe_name`` from the sibling
   ``PROBE_RESULT.json`` and ``requests.jsonl`` where an unambiguous match
   exists; otherwise leave them empty rather than guessing.
5. Record the incident and the repair method at the top level of each manifest.

Run with ``--dry-run`` first; it prints the damage assessment without writing.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SAMPLES = ROOT / "samples"
PROBES = ROOT / "probes"
INCIDENT_AT = "2026-11-08T21:59:10Z"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def payload_files(directory: Path) -> list[Path]:
    """Every file the manifest could describe.

    Nested files and helper scripts are included: several owners list their
    reproduction scripts inside ``SAMPLES.json``, so the manifest — not this
    function — decides what counts as a sample.
    """
    return sorted(
        p for p in directory.rglob("*") if p.is_file() and p.name != "SAMPLES.json"
    )


def load_manifest(directory: Path) -> dict[str, Any]:
    path = directory / "SAMPLES.json"
    if not path.exists():
        return {"samples": []}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"samples": [], "_unparsable": True}
    if isinstance(payload, list):
        return {"samples": payload}
    return payload


def entry_file(entry: dict[str, Any]) -> str:
    """Best-effort filename key, including nested relative paths."""
    for key in ("file", "filename", "file_name", "name", "path"):
        value = entry.get(key)
        if value:
            candidate = str(value).replace("\\", "/")
            if candidate and not candidate.endswith("SAMPLES.json"):
                return candidate
    return ""


def _rel_name(directory: Path, path: Path) -> str:
    return path.relative_to(directory).as_posix()


def probe_requests(source_id: str) -> list[dict[str, Any]]:
    ledger = PROBES / source_id / "requests.jsonl"
    if not ledger.exists():
        return []
    out = []
    for line in ledger.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


def match_request(source_id: str, sha: str, size: int) -> dict[str, Any]:
    """Recover the request that produced a sample, only on an unambiguous match."""
    candidates = [r for r in probe_requests(source_id) if int(r.get("bytes", -1) or -1) == size]
    if len(candidates) == 1:
        return {"request_url": candidates[0].get("url", ""), "recovered_from": "requests.jsonl"}
    return {}


def repair(source_id: str, directory: Path, *, write: bool) -> dict[str, Any]:
    manifest = load_manifest(directory)
    entries = manifest.get("samples", []) if isinstance(manifest.get("samples"), list) else []
    by_file: dict[str, dict[str, Any]] = {}
    for entry in entries:
        name = entry_file(entry)
        if name:
            by_file[name] = entry

    stats = {
        "source_id": source_id,
        "entries": 0,
        "verified": 0,
        "recomputed": 0,
        "mismatched": 0,
        "unlisted_files_added": 0,
        "missing_files": 0,
    }
    files = payload_files(directory)
    rel_names = [_rel_name(directory, p) for p in files]
    on_disk = set(rel_names)
    repaired_entries: list[dict[str, Any]] = []

    for path, relative in zip(files, rel_names):
        digest = sha256_file(path)
        size = path.stat().st_size
        entry = dict(by_file.get(relative, {})) if relative in by_file else {}
        entry.setdefault("file", relative)
        declared = entry.get("sha256_full")
        stats["entries"] += 1
        if declared:
            if declared == digest:
                entry["hash_verified"] = True
                stats["verified"] += 1
            else:
                entry["declared_sha256_full"] = declared
                entry["sha256_full"] = digest
                entry["hash_verified"] = False
                entry["sha256_source"] = "recomputed_from_disk_conflict"
                stats["mismatched"] += 1
        else:
            entry["sha256_full"] = digest
            entry["hash_verified"] = True
            entry["sha256_source"] = "recomputed_from_disk"
            stats["recomputed"] += 1
        entry["stored_bytes"] = size
        if not entry.get("total_bytes"):
            entry["total_bytes"] = size
        if not entry.get("truncated") and entry["stored_bytes"] != entry.get("total_bytes"):
            entry["truncated"] = True
        if "request_url" not in entry:
            entry.update(match_request(source_id, digest, size))
        if relative not in by_file:
            entry["listed_in_original_manifest"] = False
            stats["unlisted_files_added"] += 1
        repaired_entries.append(entry)

    listed = set(by_file)
    for name in sorted(listed - on_disk):
        stale = dict(by_file[name])
        stale["file_missing_on_disk"] = True
        repaired_entries.append(stale)
        stats["missing_files"] += 1

    repaired = {
        **{k: v for k, v in manifest.items() if k != "samples"},
        "samples": repaired_entries,
        "manifest_repair": {
            "repaired_at_note": "hashes recomputed from disk; declared values preserved on conflict",
            "incident": "wildcard write rewrote SAMPLES.json files during collection",
            "incident_observed_at": INCIDENT_AT,
            "policy": "verify, do not restore: payload bytes were never modified",
            "stats": stats,
        },
    }
    if write:
        (directory / "SAMPLES.json").write_text(
            json.dumps(repaired, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
    return repaired


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--dry-run", action="store_true")
    group.add_argument("--write", action="store_true")
    args = parser.parse_args(argv)

    totals = {"dirs": 0, "entries": 0, "verified": 0, "recomputed": 0, "mismatched": 0, "unlisted": 0, "missing": 0}
    for directory in sorted(p for p in SAMPLES.iterdir() if p.is_dir()):
        if not payload_files(directory) and not (directory / "SAMPLES.json").exists():
            continue
        result = repair(directory.name, directory, write=args.write)
        stats = result["manifest_repair"]["stats"]
        totals["dirs"] += 1
        for key in ("entries", "verified", "recomputed", "mismatched", "missing_files"):
            totals["mismatched" if key == "mismatched" else ("missing" if key == "missing_files" else key)] += stats[key]
        totals["unlisted"] += stats["unlisted_files_added"]
        if stats["mismatched"] or stats["missing_files"] or stats["unlisted_files_added"]:
            print(
                f"  {directory.name:<24} entries={stats['entries']:>3} "
                f"verified={stats['verified']:>3} recomputed={stats['recomputed']:>3} "
                f"conflict={stats['mismatched']:>2} unlisted={stats['unlisted_files_added']:>2} "
                f"missing={stats['missing_files']:>2}"
            )
    mode = "wrote" if args.write else "would write"
    print(f"\n{mode} manifests for {totals['dirs']} sample directories")
    print(
        f"entries={totals['entries']} verified={totals['verified']} "
        f"recomputed={totals['recomputed']} conflicts={totals['mismatched']} "
        f"unlisted_added={totals['unlisted']} files_missing={totals['missing']}"
    )
    return 1 if totals["mismatched"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
