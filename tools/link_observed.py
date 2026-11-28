"""Link observed papers to fields, using the query that found them.

The radar lane records which of its queries produced an observation; the field pages need a specialty.
Those are two different vocabularies, and the mapping between them is **our editorial judgement, not
FDA's** - "surgical_robotics" is not a specialty in the product-code table, so somebody has to say which
field it belongs to. This file is that statement, in one place, reviewable.

Run after a radar collection:

    python3 tools/link_observed.py --radar /srv/medradar/data/radar/radar.db \
        --reference /srv/medradar/reference_slim.db

Why it exists: measured 2026-11-28, 190 observed records carried a PMCID and none could be linked, because
the query that produced them was not recorded. That is now recorded (payload ``medradar_query``), and this
tool closes the loop. Nothing is inferred from a title.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

#: query id -> specialty in ``product_code_class``. Editorial, deliberately narrow, and one line each so a
#: reader can disagree with a specific choice instead of the whole mechanism.
SPECIALTY_BY_QUERY: dict[str, str] = {
    "monitoring": "General Hospital",
    "respiratory": "Anesthesiology",
    "cardiovascular_devices": "Cardiovascular",
    "surgical_robotics": "General, Plastic Surgery",
    "device_safety": "General Hospital",
}


def observed_papers(radar_path: Path) -> dict[str, list[str]]:
    """specialty -> PMCIDs, from the queries the radar recorded."""
    out: dict[str, list[str]] = {}
    conn = sqlite3.connect(f"file:{radar_path}?mode=ro", uri=True, timeout=60)
    try:
        rows = conn.execute(
            "SELECT v.payload FROM observation o"
            " JOIN observation_version v ON v.observation_id = o.observation_id"
            " WHERE o.source = 'europepmc' AND v.payload LIKE '%medradar_query%'"
        ).fetchall()
    finally:
        conn.close()
    for (payload,) in rows:
        try:
            data = json.loads(payload)
        except (TypeError, ValueError):
            continue
        pmcid = str(data.get("pmcid") or "")
        query = str(data.get("medradar_query") or "")
        specialty = SPECIALTY_BY_QUERY.get(query)
        if pmcid.startswith("PMC") and specialty:
            out.setdefault(specialty, []).append(pmcid)
    return {key: sorted(dict.fromkeys(value)) for key, value in out.items()}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--radar", default="/srv/medradar/data/radar/radar.db")
    parser.add_argument("--reference", default="/srv/medradar/reference_slim.db")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    grouped = observed_papers(Path(args.radar))
    if not grouped:
        print("no observed papers carry a query; nothing to link")
        return 0
    if args.dry_run:
        print(json.dumps({k: len(v) for k, v in grouped.items()}, ensure_ascii=False, indent=2))
        return 0

    from medradar.radar.paper_passes import record_field
    from medradar.radar.reference import UdiReference

    store = UdiReference(args.reference)
    try:
        total = 0
        for specialty, ids in grouped.items():
            linked = record_field(store, specialty, ids)
            total += int(linked or 0)
            print(f"  {specialty}: {linked} of {len(ids)} linked")
    finally:
        store.close()
    print(f"linked {total} observations to fields")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
