"""Compute the coverage table for the REGULATORY frontier report.

Run:  python CONNECTORS/regulatory/_coverage.py
Writes DATASETS/regulatory/COVERAGE.json and prints a markdown table.
"""

from __future__ import annotations

import glob
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from hz.schema import read_jsonl  # noqa: E402

from CONNECTORS.regulatory._util import ROOT, utc_now, write_json  # noqa: E402

DS = os.path.join(ROOT, "DATASETS", "regulatory")

SOURCES = [
    "accessgudid",
    "canada_mdall",
    "openfda_device_510k",
    "openfda_device_pma",
    "openfda_device_registrationlisting",
    "openfda_device_classification",
    "openfda_bulk_download",
    "brazil_anvisa",
    "australia_tga_artg",
    "eudamed",
    "japan_pmda",
    "uk_mhra_device",
    "china_nmpa_udi",
]


def main() -> int:
    rows = []
    for sid in SOURCES:
        d = os.path.join(DS, sid)
        raw_files = glob.glob(os.path.join(d, "raw", "*"))
        raw_bytes = sum(os.path.getsize(f) for f in raw_files if os.path.isfile(f))
        rec_path = os.path.join(d, "records.jsonl")
        recs = read_jsonl(rec_path) if os.path.isfile(rec_path) else []
        counts = {}
        cpath = os.path.join(d, "COUNTS.json")
        if os.path.isfile(cpath):
            counts = json.load(open(cpath, encoding="utf-8"))
        with_id = sum(1 for r in recs if r.get("identifiers"))
        with_pub = sum(1 for r in recs if r.get("source_public_at"))
        with_event = sum(1 for r in recs if r.get("event_at"))
        with_both = sum(1 for r in recs if r.get("source_public_at") and r.get("event_at"))
        rows.append({
            "source_id": sid,
            "raw_responses_saved": len([f for f in raw_files if os.path.isfile(f)]),
            "raw_bytes": raw_bytes,
            "records_parsed": len(recs),
            "records_with_official_identifier": with_id,
            "records_with_source_public_at": with_pub,
            "records_with_event_at": with_event,
            "records_with_both_clocks": with_both,
            "counts_file": (f"DATASETS/regulatory/{sid}/COUNTS.json"
                            if os.path.isfile(cpath) else None),
        })

    total = sum(r["records_parsed"] for r in rows)
    doc = {
        "generated_at": utc_now(),
        "note": ("'fetched' = raw responses saved verbatim under DATASETS/regulatory/<id>/raw/. "
                 "'parsed' = horizon.evidence.v1 records emitted. A record counting as "
                 "'with official identifier' has at least one identifier whose value appeared in "
                 "the source response."),
        "sources": rows,
        "totals": {
            "records_parsed": total,
            "records_with_official_identifier": sum(r["records_with_official_identifier"] for r in rows),
            "records_with_source_public_at": sum(r["records_with_source_public_at"] for r in rows),
            "records_with_event_at": sum(r["records_with_event_at"] for r in rows),
            "records_with_both_clocks": sum(r["records_with_both_clocks"] for r in rows),
            "raw_bytes": sum(r["raw_bytes"] for r in rows),
        },
    }
    write_json("", "COVERAGE.json", doc) if False else None
    with open(os.path.join(DS, "COVERAGE.json"), "w", encoding="utf-8", newline="\n") as fh:
        json.dump(doc, fh, indent=2, ensure_ascii=False)
        fh.write("\n")

    print("| source_id | fetched | parsed | with id | with public date | with event date |")
    print("|---|---|---|---|---|---|")
    for r in rows:
        print(f'| `{r["source_id"]}` | {r["raw_responses_saved"]} | {r["records_parsed"]} | '
              f'{r["records_with_official_identifier"]} | {r["records_with_source_public_at"]} | '
              f'{r["records_with_event_at"]} |')
    print(f'\nTOTALS: {json.dumps(doc["totals"])}')
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
