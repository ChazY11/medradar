"""Measure the monitoring-recall channel on a real radar ledger (V1-001).

Read-only. It answers, from the ledger and the committed rules only:

1. how many recall observations are stored, and how many distinct FDA recall EVENTS they are;
2. how the monitoring screen classifies them (product code / device text / unconfirmed / out
   of scope), with the count of records that were stored but excluded;
3. which monitoring events exist per year and per company;
4. whether the four reference events named in FIRST PRINCIPLES-001 are present, with their
   official identifiers, dates and statuses as the source states them;
5. the discovery lag (first_observed_at minus the source-stated publication date).

Usage:
    python docs/v1/001/_scripts/recall_coverage.py --db <radar.db> --json <out.json>
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))

from medradar.radar.recall import (  # noqa: E402
    BASIS_OUT_OF_SCOPE,
    monitoring_codes,
    screen_recall,
)
from medradar.radar.taxonomy import load_taxonomy  # noqa: E402

#: The four cases FIRST PRINCIPLES-001 named as missed. Each entry lists the substrings the
#: official record must contain. Nothing is asserted from the earlier report: the script only
#: reports what the ledger now holds.
REFERENCE_CASES = (
    {"name": "GE Portrait - software may cause loss of monitoring",
     "all_terms": ["portrait", "loss of patient monitoring"]},
    {"name": "Philips PIC iX - telemetry loses the central station",
     "all_terms": ["pic ix"]},
    {"name": "Mindray - operator manual alarm wording",
     "all_terms": ["mindray", "manual"]},
    {"name": "Nihon Kohden - central station cybersecurity",
     "all_terms": ["nihon kohden", "central"]},
)


def _text(payload: dict) -> str:
    return " ".join(str(payload.get(field) or "") for field in
                    ("product_description", "reason_for_recall", "recalling_firm",
                     "action")).lower()


def load(db: Path) -> list[dict]:
    import sqlite3

    uri = "file:" + db.as_posix() + "?mode=ro"
    con = sqlite3.connect(uri, uri=True)
    con.row_factory = sqlite3.Row
    sql = (
        "SELECT o.observation_id, o.source, o.official_identifier, o.title, o.event_at,"
        " o.event_at_precision, o.published_at, o.published_at_precision, o.first_observed_at,"
        " o.discovery_phase, o.observation_origin, o.source_url, v.payload"
        " FROM observation o JOIN observation_version v ON v.version_id = o.latest_version_id"
        " WHERE o.source = ?"
    )
    rows = con.execute(sql, ("openfda_recall",)).fetchall()
    out = []
    for row in rows:
        item = dict(row)
        item["payload"] = json.loads(item["payload"] or "{}")
        out.append(item)
    con.close()
    return out


def summarise(rows: list[dict], taxonomy) -> dict:
    codes = monitoring_codes(taxonomy)
    basis = Counter()
    events_by_basis = defaultdict(set)
    monitoring_events = defaultdict(list)
    years = Counter()
    firms = Counter()
    excluded = []
    lags = []
    for row in rows:
        payload = row["payload"]
        verdict = screen_recall(payload, codes=codes, taxonomy=taxonomy)
        basis[verdict["basis"]] += 1
        event = str(payload.get("res_event_number") or row["observation_id"])
        events_by_basis[verdict["basis"]].add(event)
        if verdict["basis"] == BASIS_OUT_OF_SCOPE:
            excluded.append({"event": event, "code": payload.get("product_code"),
                             "firm": payload.get("recalling_firm"),
                             "reason": verdict["reason"]})
            continue
        year = str(payload.get("event_date_posted") or row["published_at"] or "")[:4]
        years[year or "unknown"] += 1
        firms[str(payload.get("recalling_firm") or "unknown")] += 1
        monitoring_events[event].append({
            "product_res_number": payload.get("product_res_number"),
            "product_code": payload.get("product_code"),
            "firm": payload.get("recalling_firm"),
            "posted": payload.get("event_date_posted"),
            "status": payload.get("recall_status"),
            "device": " ".join(str(payload.get("product_description") or "").split())[:180],
            "reason": " ".join(str(payload.get("reason_for_recall") or "").split())[:400],
            "basis": verdict["basis"],
            "needs_review": verdict["needs_review"],
        })
        try:
            posted = datetime.fromisoformat(str(payload.get("event_date_posted"))[:10])
            observed = datetime.fromisoformat(
                str(row["first_observed_at"]).replace("Z", "+00:00")).replace(tzinfo=None)
            lags.append((observed - posted).days)
        except (TypeError, ValueError):
            pass
    lags.sort()
    return {
        "recall_observations": len(rows),
        "distinct_events_all": len({str(record["payload"].get("res_event_number")
                                    or record["observation_id"]) for record in rows}),
        "basis_records": dict(basis),
        "basis_events": {key: len(value) for key, value in events_by_basis.items()},
        "monitoring_events_total": len(monitoring_events),
        "monitoring_records_by_year": dict(sorted(years.items())),
        "monitoring_records_by_firm": dict(firms.most_common(20)),
        "out_of_scope_records": len(excluded),
        "out_of_scope_sample": excluded[:10],
        "discovery_lag_days": {
            "n": len(lags),
            "median": lags[len(lags) // 2] if lags else None,
            "min": lags[0] if lags else None,
            "max": lags[-1] if lags else None,
        },
        "monitoring_events": monitoring_events,
    }


def reference_cases(rows: list[dict]) -> list[dict]:
    found = []
    for case in REFERENCE_CASES:
        hits = [row for row in rows
                if all(term in _text(row["payload"]) for term in case["all_terms"])]
        events = sorted({str(row["payload"].get("res_event_number")) for row in hits})
        found.append({
            "case": case["name"],
            "matched_rows": len(hits),
            "distinct_events": events,
            "present": bool(hits),
            "records": [{
                "event": row["payload"].get("res_event_number"),
                "product_res_number": row["payload"].get("product_res_number"),
                "product_code": row["payload"].get("product_code"),
                "firm": row["payload"].get("recalling_firm"),
                "posted": row["payload"].get("event_date_posted"),
                "initiated": row["payload"].get("event_date_initiated"),
                "status": row["payload"].get("recall_status"),
                "device": " ".join(str(row["payload"].get("product_description")
                                    or "").split())[:200],
                "reason": " ".join(str(row["payload"].get("reason_for_recall")
                                    or "").split())[:400],
                "url": row["source_url"],
                "first_observed_at": row["first_observed_at"],
                "origin": row["observation_origin"],
                "phase": row["discovery_phase"],
            } for row in hits[:6]],
        })
    return found


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="recall coverage probe")
    parser.add_argument("--db", required=True)
    parser.add_argument("--json", default=None)
    args = parser.parse_args(argv)
    taxonomy = load_taxonomy()
    rows = load(Path(args.db))
    payload = summarise(rows, taxonomy)
    payload["reference_cases"] = reference_cases(rows)
    payload["monitoring_codes_configured"] = sorted(monitoring_codes(taxonomy))
    events = payload.pop("monitoring_events")
    recent = sorted(events.items(), key=lambda kv: str(kv[1][0].get("posted") or ""),
                    reverse=True)[:40]
    payload["recent_monitoring_events"] = [
        {"event": key, "records": value} for key, value in recent
    ]
    text = json.dumps(payload, indent=2, ensure_ascii=False, default=str)
    if args.json:
        Path(args.json).parent.mkdir(parents=True, exist_ok=True)
        Path(args.json).write_text(text, encoding="utf-8")
        print("wrote " + args.json)
    print("recall observations      : " + str(payload["recall_observations"]))
    print("distinct recall events   : " + str(payload["distinct_events_all"]))
    print("basis (records)          : " + json.dumps(payload["basis_records"]))
    print("basis (events)           : " + json.dumps(payload["basis_events"]))
    print("monitoring events        : " + str(payload["monitoring_events_total"]))
    print("by year (records)        : " + json.dumps(payload["monitoring_records_by_year"]))
    print("discovery lag (days)     : " + json.dumps(payload["discovery_lag_days"]))
    for case in payload["reference_cases"]:
        marker = "[FOUND]  " if case["present"] else "[MISSING]"
        print("  " + marker + " " + case["case"] + " rows=" + str(case["matched_rows"])
              + " events=" + ",".join(case["distinct_events"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
