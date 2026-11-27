"""Build a versioned export for ATLAS-001 from the finalised dataset files.

    python tools/build_export.py --export-id horizon-2026-11-10

Reads every ``DATASETS/*/*/RECORDS.jsonl``, validates each row against
``horizon.evidence.v1``, and writes ``exports/<export_id>/`` with a MANIFEST that
states the counts **next to** the coverage limits.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from hz.export import write_export  # noqa: E402
from hz.schema import QUALITY_FLAGS, read_jsonl, dedupe_key  # noqa: E402
from hz.registry import load_all  # noqa: E402

DATASETS = os.path.join(ROOT, "DATASETS")

# Some acquisitions are far larger than a "bounded sample". The full extract stays
# on disk (and is regenerable from committed code + documented URLs), while the
# committed export carries a deterministic, stratified slice so the repository does
# not carry ~200 MB of duplicated JSONL. The cap is applied by stratum, not by
# truncation, so every firm and every decade survives.
MAX_RECORDS_PER_SOURCE = {"cipo_canada": 2000}


def _stratified_cap(recs: list[dict], cap: int) -> list[dict]:
    """Deterministic proportional sample across (firm candidate, publication decade)."""
    if len(recs) <= cap:
        return recs

    def stratum(r: dict) -> tuple[str, str]:
        attrs = r.get("attributes") or {}
        firms = attrs.get("firm_group_candidates") or []
        firm = sorted(firms)[0] if firms else "UNATTRIBUTED"
        d = (r.get("source_public_at") or r.get("event_at") or "")[:3]
        return (firm, d or "UNKNOWN")

    buckets: dict[tuple[str, str], list[dict]] = {}
    for r in sorted(recs, key=lambda x: str(x.get("source_record_id"))):
        buckets.setdefault(stratum(r), []).append(r)
    total = len(recs)
    out: list[dict] = []
    for key in sorted(buckets):
        rows = buckets[key]
        take = max(1, round(len(rows) * cap / total))
        out.extend(rows[:take])
    out.sort(key=lambda x: str(x.get("source_record_id")))
    return out[:cap]


def _records_file(sdir: str) -> str | None:
    """Accept RECORDS.jsonl / records.jsonl / *_records.jsonl (case-insensitive)."""
    names = sorted(os.listdir(sdir))
    lower = {n.lower(): n for n in names}
    for cand in ("records.jsonl", "horizon_records.jsonl"):
        if cand in lower:
            return os.path.join(sdir, lower[cand])
    for n in names:
        ln = n.lower()
        if ln.endswith("records.jsonl") or ln.endswith("_horizon.jsonl"):
            return os.path.join(sdir, n)
    return None


# Workstreams that keep their emitted records next to their evidence instead of
# under DATASETS/ are still first-class inputs; the location is declared here
# rather than guessed, so nothing is silently excluded from the export.
EXTRA_RECORD_DIRS = [
    ("experiments/industry/evidence", "industry workstream emitted-records directory"),
]


def discover_extra() -> dict[str, list[tuple[str, list[dict]]]]:
    found: dict[str, list[tuple[str, list[dict]]]] = {}
    for rel, _why in EXTRA_RECORD_DIRS:
        d = os.path.join(ROOT, rel)
        if not os.path.isdir(d):
            continue
        for name in sorted(os.listdir(d)):
            if not name.endswith(".jsonl"):
                continue
            source_id = name[: -len(".jsonl")]
            path = os.path.join(d, name)
            recs = read_jsonl(path)
            if recs and recs[0].get("schema_version") == "horizon.evidence.v1":
                found.setdefault(source_id, []).append(
                    (os.path.relpath(path, ROOT), recs)
                )
    return found


def discover() -> dict[str, list[tuple[str, list[dict]]]]:
    """source_id -> [(dataset path, records)], from DATASETS/ plus declared extras."""
    found: dict[str, list[tuple[str, list[dict]]]] = {}
    for group in sorted(os.listdir(DATASETS)):
        gdir = os.path.join(DATASETS, group)
        if not os.path.isdir(gdir) or group.startswith("_"):
            continue
        for src in sorted(os.listdir(gdir)):
            sdir = os.path.join(gdir, src)
            if not os.path.isdir(sdir) or src.startswith("_"):
                continue
            path = _records_file(sdir)
            if not path:
                continue
            recs = read_jsonl(path)
            if not recs:
                continue
            found.setdefault(src, []).append((os.path.relpath(path, ROOT), recs))
    for sid, entries in discover_extra().items():
        found.setdefault(sid, []).extend(entries)
    return found


def validate(rec: dict) -> list[str]:
    errs = []
    for f in ("schema_version", "source_id", "source_record_id", "entity_type",
              "original_name", "source_url", "licence_status", "identity_status",
              "evidence_status"):
        if not rec.get(f):
            errs.append(f"empty {f}")
    if rec.get("schema_version") != "horizon.evidence.v1":
        errs.append("bad schema_version")
    bad = set(rec.get("quality_flags") or []) - QUALITY_FLAGS
    if bad:
        errs.append(f"unknown quality_flags {sorted(bad)}")
    return errs


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--export-id", default="horizon-2026-11-10")
    args = ap.parse_args(argv)

    found = discover()
    if not found:
        print("no RECORDS.jsonl found under DATASETS/*/*/")
        return 2

    registry = {e["source_id"]: e for e in load_all(ROOT)}
    by_source: dict[str, list[dict]] = {}
    licence_summary: dict[str, str] = {}
    provenance: dict[str, list[str]] = {}
    issues: list[str] = []
    entity_key_notes: list[str] = []
    capped_notes: list[str] = []

    for source_id, entries in found.items():
        recs: list[dict] = []
        paths: list[str] = []
        for rel, rows in entries:
            paths.append(rel)
            for r in rows:
                e = validate(r)
                if e:
                    issues.append(f"{rel}: {r.get('source_record_id')}: {e}")
                recs.append(r)
        # De-duplicate on RECORD identity, not on dedupe_key.
        # dedupe_key is an *entity* key: many records legitimately share it (299
        # TED supplier rows -> 93 notices; 62 FTS rows -> 16 releases). Filtering
        # on it would silently delete distinct suppliers. Record identity is
        # (source_record_id, content_hash).
        seen: set[tuple[str, str]] = set()
        uniq: list[dict] = []
        for r in recs:
            k = (str(r.get("source_record_id")), str(r.get("content_hash")))
            if k in seen:
                continue
            seen.add(k)
            uniq.append(r)
        cap = MAX_RECORDS_PER_SOURCE.get(source_id)
        if cap and len(uniq) > cap:
            before = len(uniq)
            uniq = _stratified_cap(uniq, cap)
            capped_notes.append(
                f"`{source_id}`: export carries a DETERMINISTIC STRATIFIED SAMPLE of "
                f"{len(uniq)} from {before} acquired records (cap {cap}). The full "
                f"extract is regenerable with the committed connector; the stratum is "
                f"(firm candidate, publication decade), so every firm and decade survives."
            )
        by_source[source_id] = uniq
        provenance[source_id] = paths
        reg = registry.get(source_id)
        licence_summary[source_id] = (reg or {}).get("licence_status") or (
            uniq[0].get("licence_status") if uniq else "unknown"
        )
        # record the entity-key multiplicity so ATLAS-001 knows to group, not filter
        entity_keys = {dedupe_key(r) for r in uniq}
        if len(entity_keys) < len(uniq):
            entity_key_notes.append(
                f"`{source_id}`: {len(uniq)} records share only {len(entity_keys)} "
                f"`dedupe_key` entity keys — group on `dedupe_key`, do NOT filter on it."
            )

    if issues:
        print(f"VALIDATION ISSUES ({len(issues)}):")
        for i in issues[:20]:
            print("  ", i)
        return 1

    # coverage notes are computed, not asserted
    notes: list[str] = []
    for sid, recs in sorted(by_source.items()):
        n = len(recs)
        with_pub = sum(1 for r in recs if r.get("source_public_at"))
        with_ev = sum(1 for r in recs if r.get("event_at"))
        flags = Counter(f for r in recs for f in (r.get("quality_flags") or []))
        notes.append(
            f"`{sid}`: {n} records; {with_pub} ({with_pub/n:.0%}) carry a recorded public "
            f"observation date and {with_ev} ({with_ev/n:.0%}) a recorded event date. "
            f"Top quality flags: {', '.join(f'{k}={v}' for k, v in flags.most_common(4)) or 'none'}."
        )
    notes.append(
        "These are SAMPLES, not censuses. EP: 10 weekly publication dates enumerated "
        "out of ~2 500. CA: firm-scoped slice of an open bulk extract ending 2022-02-28. "
        "Row counts must not be read as coverage."
    )
    notes.append(
        "`identity_status = CANDIDATE` records carry a name-fragment firm attribution only. "
        "No record in this export claims a confirmed cross-source identity."
    )
    notes.extend(entity_key_notes)
    notes.extend(capped_notes)

    out = write_export(
        ROOT,
        args.export_id,
        by_source,
        generator="tools/build_export.py",
        command=f"python tools/build_export.py --export-id {args.export_id}",
        coverage_notes=notes,
        licence_summary=licence_summary,
        extra={
            "provenance_files": provenance,
            "registry_snapshot": {
                sid: {
                    "access_state": (registry.get(sid) or {}).get("access_state"),
                    "licence_status": (registry.get(sid) or {}).get("licence_status"),
                    "licence_url": (registry.get(sid) or {}).get("licence_url"),
                }
                for sid in sorted(by_source)
            },
        },
    )
    print("export written:", os.path.relpath(out, ROOT))
    for sid, recs in sorted(by_source.items()):
        print(f"  {sid:28} {len(recs):6} records  licence={licence_summary[sid]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
