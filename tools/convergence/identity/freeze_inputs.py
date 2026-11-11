#!/usr/bin/env python
"""P0-B / task-2: freeze every input used by the 934-vs-0 identity reconciliation.

Writes research/convergence/identity/FROZEN_INPUTS.json with, for every input:
absolute path, size in bytes, mtime (UTC, ISO-8601), SHA-256, and a role label.

This is deliberately offline and read-only: it only opens files for reading.
The ATLAS research DB and the MDALL cache live in the *original* atlas-001
worktree (they are gitignored there) and are never modified.

Run:
    python tools/convergence/identity/freeze_inputs.py
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path

WT = Path(r"D:\DEPPSKK\worktrees\convergence-001")
ATLAS_ORIG = Path(r"D:\DEPPSKK\worktrees\atlas-001")
HORIZON_ORIG = Path(r"D:\DEPPSKK\worktrees\horizon-001")
OUT = WT / "research" / "convergence" / "identity" / "FROZEN_INPUTS.json"

# (role, path, note)
REQUIRED = [
    ("atlas_db", ATLAS_ORIG / "research/atlas/staging/atlas.sqlite",
     "ATLAS research SQLite DB; source of the 934 SAME_DEVICE_IDENTITY relations and both evidence payloads. READ ONLY (mode=ro)."),
    ("mdall_cache", ATLAS_ORIG / "research/atlas/cache/mdall_active_deviceidentifier.json",
     "Raw Health Canada MDALL active device-identifier table (single-line JSON array, 1.67M rows). Frozen evidence for the 0.33% GTIN minority. READ ONLY."),
    ("atlas_identity_report", WT / "research/atlas/reports/identity_pilot.json",
     "ATLAS identity pilot report (PR #28 head c636836): counts 934 / 1200 / 5005 / 1673926 / 0.003293."),
    ("horizon_mdall_records", WT / "research/horizon/DATASETS/regulatory/canada_mdall/records.jsonl",
     "HORIZON Canada MDALL frozen slice, 174 records (60 licences / 65 devices / 49 identifiers). Canada side of EXP-H2."),
    ("horizon_gudid_records", WT / "research/horizon/DATASETS/regulatory/accessgudid/records.jsonl",
     "HORIZON AccessGUDID frozen slice, 320 records, all scheme=udi_di. US side of EXP-H2."),
    ("horizon_h2_pairs", WT / "research/horizon/experiments/regulatory/EXP_H2_PAIRS.jsonl",
     "HORIZON EXP-H2 pair table: 726 pairs, every verdict UNKNOWN, S4 fired 0."),
]

SUPPORTING = [
    ("atlas_pairs_sample", WT / "research/atlas/samples/identity_pilot_pairs.json",
     "ATLAS sample export: first 40 confirmed pairs only (not the full 934); used for cross-checking fields, never as the source of counts."),
    ("atlas_request_log", ATLAS_ORIG / "research/atlas/staging/atlas_requests.jsonl",
     "ATLAS HTTP request ledger (150 rows) proving where the US records came from; no network is used here."),
    ("horizon_h2_summary", WT / "research/horizon/experiments/regulatory/EXP_H2_SUMMARY.json",
     "HORIZON EXP-H2 summary: 726 UNKNOWN, S4 fired 0, eight signal-sufficiency rows."),
    ("horizon_h2_rule", WT / "research/horizon/experiments/regulatory/EXP_H2_SELECTION_RULE.md",
     "Pre-registered H2 rule: CONFIRMED only if S4 = shared official identifier in the same scheme."),
    ("horizon_mdall_counts", WT / "research/horizon/DATASETS/regulatory/canada_mdall/COUNTS.json",
     "HORIZON Canada selection rule: 60 licences by licence_name, 65 devices by device_name, 49 identifiers by internal device id."),
    ("horizon_gudid_counts", WT / "research/horizon/DATASETS/regulatory/accessgudid/COUNTS.json",
     "HORIZON US selection rule: 320 GUDID records for the five pre-declared firms."),
    ("atlas_identity_model", WT / "docs/atlas/IDENTITY_MODEL.md",
     "ATLAS identity model: identifier scheme/scope/is_primary contract and the rule 'comparisons only match a scheme against itself'."),
    ("atlas_firm_registry", WT / "config/atlas_firms.json",
     "Curated firm alias registry used by ATLAS company resolution (5 firms + negative guards)."),
]

METHOD_SOURCES = [
    ("atlas_pilot_source", WT / "medradar/atlas/identity/pilot.py",
     "ATLAS pipeline source: GTIN screening (is_gtin_like), 1200-of-5005 bridge subsample, exact-DI comparison."),
    ("atlas_normalize_source", WT / "medradar/atlas/identity/normalize.py",
     "ATLAS is_gtin_like = 14 digits, NO check-digit validation (this report adds the check)."),
    ("atlas_mdall_connector", WT / "medradar/atlas/connectors/canada_mdall.py",
     "ATLAS MDALL connector: iter_json_array cache reader, GTIN flag, licence/company fetches."),
    ("atlas_openfda_connector", WT / "medradar/atlas/connectors/openfda_udi.py",
     "ATLAS openFDA UDI connector: identifiers.id batch query, primary-DI selection."),
    ("horizon_exp_h2_source", WT / "research/horizon/experiments/regulatory/exp_h2_identity.py",
     "HORIZON EXP-H2 implementation: ids_overlap() requires the SAME scheme string on both sides."),
    ("horizon_mdall_connector", WT / "research/horizon/CONNECTORS/regulatory/canada_mdall.py",
     "HORIZON MDALL connector: how the 174-record slice was built and scheme-labelled."),
]


def sha256_file(path: Path, chunk: int = 1 << 22) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            block = f.read(chunk)
            if not block:
                break
            h.update(block)
    return h.hexdigest()


def stat_block(path: Path) -> dict:
    st = path.stat()
    return {
        "path": str(path),
        "size_bytes": st.st_size,
        "mtime_utc": datetime.fromtimestamp(st.st_mtime, tz=timezone.utc).isoformat(),
        "sha256": sha256_file(path),
    }


def git_head(path: Path) -> str | None:
    """Read-only git query; never mutates a branch or index."""
    try:
        out = subprocess.run(
            ["git", "-C", str(path), "rev-parse", "HEAD"],
            capture_output=True, text=True, timeout=30, check=False,
        )
        return out.stdout.strip() if out.returncode == 0 else None
    except Exception:  # pragma: no cover - git absence is not fatal
        return None


def main() -> int:
    required = []
    for role, path, note in REQUIRED:
        if not path.exists():
            raise SystemExit(f"REQUIRED INPUT MISSING: {role} -> {path}")
        required.append({"role": role, "note": note, **stat_block(path)})

    supporting = []
    for role, path, note in SUPPORTING:
        if path.exists():
            supporting.append({"role": role, "note": note, **stat_block(path)})
        else:
            supporting.append({"role": role, "note": note, "path": str(path), "missing": True})

    method_sources = []
    for role, path, note in METHOD_SOURCES:
        if path.exists():
            method_sources.append({"role": role, "note": note, **stat_block(path)})
        else:
            method_sources.append({"role": role, "note": note, "path": str(path), "missing": True})

    doc = {
        "schema": "medradar.convergence.frozen_inputs.v1",
        "task": "P0-B / task-2: 934-vs-0 cross-border UDI identity reconciliation",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "generated_by": "tools/convergence/identity/freeze_inputs.py",
        "network_used": False,
        "note": (
            "All counts in docs/convergence/IDENTITY_RECONCILIATION.md are bound to these "
            "SHA-256 digests. The two original worktrees are READ-ONLY inputs; nothing outside "
            "docs/convergence/, tools/convergence/identity/, research/convergence/identity/ and "
            "tests/convergence/ is written."
        ),
        "worktrees": {
            "convergence_001": {"path": str(WT), "git_head": git_head(WT)},
            "atlas_001": {"path": str(ATLAS_ORIG), "git_head": git_head(ATLAS_ORIG)},
        },
        "required_inputs": required,
        "supporting_inputs": supporting,
        "method_sources": method_sources,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")

    print(f"wrote {OUT}")
    for block in required + supporting + method_sources:
        if block.get("missing"):
            print(f"  MISSING  {block['role']}")
        else:
            print(f"  {block['sha256'][:16]}  {block['size_bytes']:>12}  {block['role']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
