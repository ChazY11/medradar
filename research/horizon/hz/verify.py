"""Offline integrity checks.

Runs without network. Fails loudly when a deliverable claims something the
files on disk do not support.
"""

from __future__ import annotations

import json
import os
from typing import Any

from .schema import (
    EVIDENCE_STATUS,
    IDENTITY_STATUS,
    LICENCE_STATUS,
    SCHEMA_VERSION,
)


def _iter_jsonl(path):
    with open(path, "r", encoding="utf-8") as fh:
        for i, line in enumerate(fh, 1):
            line = line.strip()
            if not line:
                continue
            try:
                yield i, json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{i}: invalid JSON ({exc})") from exc


def check_export(export_dir: str) -> dict[str, Any]:
    issues: list[str] = []
    man_path = os.path.join(export_dir, "MANIFEST.json")
    if not os.path.isfile(man_path):
        return {"ok": False, "issues": [f"missing {man_path}"]}
    with open(man_path, "r", encoding="utf-8") as fh:
        man = json.load(fh)
    if man.get("schema_version") != SCHEMA_VERSION:
        issues.append(f"manifest schema_version {man.get('schema_version')!r}")

    total = 0
    for f in man.get("files", []):
        path = os.path.join(export_dir, f["path"])
        if not os.path.isfile(path):
            issues.append(f"missing data file {f['path']}")
            continue
        n = 0
        seen_hashes = set()
        for ln, rec in _iter_jsonl(path):
            n += 1
            if rec.get("schema_version") != SCHEMA_VERSION:
                issues.append(f"{f['path']}:{ln}: bad schema_version")
            for field in ("source_id", "source_record_id", "entity_type", "source_url"):
                if not rec.get(field):
                    issues.append(f"{f['path']}:{ln}: empty {field}")
            if rec.get("identity_status") not in IDENTITY_STATUS:
                issues.append(f"{f['path']}:{ln}: bad identity_status")
            if rec.get("evidence_status") not in EVIDENCE_STATUS:
                issues.append(f"{f['path']}:{ln}: bad evidence_status")
            if rec.get("licence_status") not in LICENCE_STATUS:
                issues.append(f"{f['path']}:{ln}: bad licence_status")
            ch = rec.get("content_hash")
            if ch in seen_hashes:
                issues.append(f"{f['path']}:{ln}: duplicate content_hash {ch[:12]}")
            seen_hashes.add(ch)
            total += 1
        if n != f["records"]:
            issues.append(f"{f['path']}: file has {n} rows, manifest says {f['records']}")
        # hash check
        import hashlib

        h = hashlib.sha256()
        with open(path, "rb") as fh2:
            for chunk in iter(lambda: fh2.read(1 << 20), b""):
                h.update(chunk)
        if h.hexdigest() != f["sha256"]:
            issues.append(f"{f['path']}: sha256 mismatch")
    if total != man.get("totals", {}).get("records"):
        issues.append(
            f"manifest totals.records={man.get('totals', {}).get('records')} but counted {total}"
        )
    return {
        "export_dir": export_dir,
        "export_id": man.get("export_id"),
        "records": total,
        "ok": not issues,
        "issues": issues,
    }


def check_registry(root: str) -> dict[str, Any]:
    from .registry import ACCESS_STATES, load_all

    issues: list[str] = []
    entries = load_all(root)
    ids = set()
    for e in entries:
        sid = e.get("source_id")
        if sid in ids:
            issues.append(f"duplicate source_id {sid}")
        ids.add(sid)
        if e.get("access_state") not in ACCESS_STATES:
            issues.append(f"{sid}: bad access_state {e.get('access_state')!r}")
        if e.get("licence_status") not in LICENCE_STATUS:
            issues.append(f"{sid}: bad licence_status {e.get('licence_status')!r}")
        if e.get("auth_required") and e.get("access_state") == "OPEN":
            issues.append(f"{sid}: auth_required contradicts OPEN")
        if e.get("access_state") in ("BLOCKED_TECHNICAL", "BLOCKED_LEGAL", "REQUIRES_REGISTRATION"):
            if not e.get("unlock_route"):
                issues.append(f"{sid}: blocked/registered but no unlock_route recorded")
    return {
        "sources": len(entries),
        "ok": not issues,
        "issues": issues[:50],
        "issue_count": len(issues),
    }


def check_probes(root: str) -> dict[str, Any]:
    """Every probe dir must contain PROBES.json with a budget record."""
    issues: list[str] = []
    base = os.path.join(root, "SOURCE_PROBES")
    n = 0
    if not os.path.isdir(base):
        return {"probe_suites": 0, "ok": True, "issues": []}
    for name in sorted(os.listdir(base)):
        d = os.path.join(base, name)
        if not os.path.isdir(d) or name.startswith("_"):
            continue
        p = os.path.join(d, "PROBES.json")
        if not os.path.isfile(p):
            issues.append(f"{name}: no PROBES.json")
            continue
        with open(p, "r", encoding="utf-8") as fh:
            doc = json.load(fh)
        if "budget" not in doc:
            issues.append(f"{name}: PROBES.json has no budget record")
        if not doc.get("probes"):
            issues.append(f"{name}: PROBES.json has no probe entries")
        n += 1
    return {"probe_suites": n, "ok": not issues, "issues": issues}


def run_all(root: str) -> dict[str, Any]:
    exp_dir = os.path.join(root, "exports")
    exports = []
    if os.path.isdir(exp_dir):
        for name in sorted(os.listdir(exp_dir)):
            d = os.path.join(exp_dir, name)
            if os.path.isdir(d) and os.path.isfile(os.path.join(d, "MANIFEST.json")):
                exports.append(check_export(d))
    reg = check_registry(root)
    probes = check_probes(root)
    ok = reg["ok"] and probes["ok"] and all(e["ok"] for e in exports)
    return {
        "ok": ok,
        "schema_version": SCHEMA_VERSION,
        "registry": reg,
        "probes": probes,
        "exports": exports,
    }


if __name__ == "__main__":
    import sys

    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    print(json.dumps(run_all(here), indent=2, ensure_ascii=False))
    sys.exit(0)
