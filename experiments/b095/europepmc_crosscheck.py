"""Europe PMC cross-check of the nine small-sample events (protocol frozen first).

Per event: build the verbatim query, call the Europe PMC REST search API once (page size 25), classify the hits under
the frozen rules, and record everything. Emits:

  THIRD_SOURCE_CROSSWALK.json / .md          — per-event status, lead, and the earliest record
  CASE_PACKETS_SMALL_SAMPLE_V2.json          — original packets + third_source evidence, still unlabelled

Disclosed deviation: the packets do not carry the crosswalk's matched keyword phrases (they were not propagated when the
packets were built), so keyword terms come from the track's own keyword list, longest first, as recorded in each query.

    python experiments/b095/europepmc_crosscheck.py
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from medradar.studies.thirdsource import build_query, classify, keyword_terms, parse_date  # noqa: E402

STUDY = Path("research/studies/early_signal_5firms")
PACKETS = STUDY / "CASE_PACKETS_SMALL_SAMPLE.json"
STORE = Path("D:/DEPPSKK/medradar/data/medradar.sqlite")
API = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"
PAGE_SIZE = 25


def track_keywords(con: sqlite3.Connection, track: str) -> list[str]:
    row = con.execute("select keywords from tracks where id = ?", (track,)).fetchone()
    if not row or not row[0]:
        return []
    try:
        parsed = json.loads(row[0])
    except (TypeError, ValueError):
        return []
    return [str(item) for item in parsed or []]


def search(query: str, timeout: int = 30) -> dict:
    params = urllib.parse.urlencode({"query": query, "format": "json", "pageSize": PAGE_SIZE,
                                     "resultType": "core"})
    request = urllib.request.Request(f"{API}?{params}",
                                     headers={"User-Agent": "medradar-study/1.0 (research)"})
    try:
        with urllib.request.urlopen(request, timeout=timeout,
                                    context=ssl.create_default_context()) as response:
            return {"status": response.status, "payload": json.loads(response.read().decode("utf-8", "replace"))}
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, OSError, ValueError) as error:
        return {"status": None, "error": f"{type(error).__name__}: {error}"[:200]}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--packets", default=str(PACKETS))
    parser.add_argument("--out-dir", default=str(STUDY))
    args = parser.parse_args(argv)

    packets = json.loads(Path(args.packets).read_text(encoding="utf-8"))["packets"]
    con = sqlite3.connect(f"file:{STORE}?mode=ro", uri=True)

    events = []
    updated_packets = []
    for packet in packets:
        company = str(packet["company"])
        track = str(packet["technology_track"])
        clearance_date = parse_date((packet.get("later_clearance") or {}).get("date"))
        keywords = keyword_terms(track_keywords(con, track))
        if clearance_date is None or not keywords:
            events.append({"event_id": packet["event_id"], "status": "NOT_EVALUABLE",
                           "reason": "no clearance date or no track keywords"})
            updated_packets.append(dict(packet))
            continue
        built = build_query(company, keywords)
        response = search(built["query"])
        time.sleep(0.4)
        records = []
        if response.get("payload"):
            hits = ((response["payload"].get("resultList") or {}).get("result") or [])
            records = hits
        result = classify(records, clearance_date=clearance_date)
        event = {
            "event_id": packet["event_id"],
            "company": company,
            "technology_track": track,
            "clearance_date": clearance_date.isoformat(),
            "query": built["query"],
            "query_terms": {"affiliation": built["affiliation_terms"], "keywords": built["keyword_terms"]},
            "api_status": response.get("status"),
            "api_error": response.get("error"),
            "hits_total": (response.get("payload") or {}).get("hitCount"),
            "records_inspected": len(records),
            **result,
        }
        # distance classification: a keyword+affiliation hit decades old is not programme-level corroboration
        lead_days_value = event.get("lead_days")
        if lead_days_value is None:
            event["lead_years"] = None
            event["distance_class"] = "NOT_APPLICABLE"
        else:
            years = round(lead_days_value / 365.25, 2)
            event["lead_years"] = years
            event["distance_class"] = ("NEAR" if years <= 1.0 else
                                       "MID" if years <= 3.0 else "DISTANT")
        events.append(event)
        enriched = dict(packet)
        enriched["third_source"] = {
            "source": "Europe PMC",
            "query": built["query"],
            "status": result["status"],
            "earliest_date": result.get("earliest_date"),
            "lead_days": result.get("lead_days"),
            "lead_quarters": result.get("lead_quarters"),
            "earliest_record": result.get("earliest_record"),
            "hits_total": event["hits_total"],
            "protocol": "THIRD_SOURCE_PROTOCOL.md",
        }
        enriched["human_review_status"] = "PENDING_HUMAN_REVIEW"
        enriched["final_label"] = None
        updated_packets.append(enriched)
    con.close()

    counts = {}
    for event in events:
        counts[event["status"]] = counts.get(event["status"], 0) + 1

    distance_counts: dict[str, int] = {}
    for event in events:
        key = str(event.get("distance_class", "NOT_APPLICABLE"))
        distance_counts[key] = distance_counts.get(key, 0) + 1

    payload = {
        "schema": "third_source_crosswalk_v1",
        "protocol": "THIRD_SOURCE_PROTOCOL.md (frozen before any query)",
        "source": "Europe PMC REST API",
        "disclosed_deviation": ("packets carry no crosswalk keyword phrases, so keyword terms are the track's own "
                                "keywords, longest first; each query is recorded verbatim"),
        "events": events,
        "status_counts": counts,
        "distance_counts": distance_counts,
        "distance_interpretation": ("a SUPPORTED_BEFORE hit whose earliest record predates the clearance by more than "
                                    "three years is a keyword+affiliation match decades old, NOT programme-level "
                                    "corroboration; only NEAR hits may be read that way, and even then a human must "
                                    "confirm relevance"),
        "interpretation": {
            "SUPPORTED_BEFORE": "an independent, dated publication precedes the clearance",
            "NO_RECORD": "the query returned nothing usable; this is a null search, not evidence of absence",
            "AMBIGUOUS": "records exist but none is independent or dated",
            "AFTER_CLEARANCE": "records exist but none precedes the clearance",
            "NOT_EVALUABLE": "no clearance date or no track keywords",
        },
        "not_claimed": [
            "no label: every packet remains PENDING_HUMAN_REVIEW with final_label null",
            "no predictive claim: a paper before a clearance is compatible with routine incremental work",
            "no aggregate claim across nine events, three firms, and a post-hoc keyword crosswalk",
            "NO_RECORD is not evidence that no research existed",
        ],
    }
    out_dir = Path(args.out_dir)
    (out_dir / "THIRD_SOURCE_CROSSWALK.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    (out_dir / "CASE_PACKETS_SMALL_SAMPLE_V2.json").write_text(
        json.dumps({"schema": "case_packets_small_sample_v2", "count": len(updated_packets),
                    "note": "original fields preserved; third_source added; all PENDING_HUMAN_REVIEW, no labels",
                    "packets": updated_packets}, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8", newline="\n")

    lines = ["# THIRD-SOURCE CROSS-CHECK — Europe PMC against the nine events", "",
             f"Protocol frozen first (`THIRD_SOURCE_PROTOCOL.md`). Status counts: `{counts}`.", "",
             "| event | firm | track | clearance | hits | status | distance | earliest pub | lead (d) | lead (q) |",
             "|---|---|---|---|---:|---|---|---|---:|---:|"]
    for event in events:
        lines.append(f"| {event['event_id']} | {event.get('company')} | {event.get('technology_track')} | "
                     f"{event.get('clearance_date')} | {event.get('hits_total')} | **{event['status']}** | "
                     f"{event.get('distance_class') or '—'} | "
                     f"{event.get('earliest_date') or '—'} | {event.get('lead_days') if event.get('lead_days') is not None else '—'} | "
                     f"{event.get('lead_quarters') if event.get('lead_quarters') is not None else '—'} |")
    lines += ["", "## Queries (verbatim)", ""]
    for event in events:
        if event.get("query"):
            lines.append(f"- **{event['event_id']}**: `{event['query']}`")
    lines += ["", "## Not claimed", ""] + [f"- {item}" for item in payload["not_claimed"]]
    (out_dir / "THIRD_SOURCE_CROSSWALK.md").write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")

    print(f"status counts: {counts}")
    for event in events:
        print(f"  {event['event_id']} {str(event.get('company')):14s} {str(event.get('technology_track')):20s} "
              f"{event['status']:16s} hits={event.get('hits_total')} lead_days={event.get('lead_days')}")
    print(f"wrote {out_dir}/THIRD_SOURCE_CROSSWALK.{{json,md}} and CASE_PACKETS_SMALL_SAMPLE_V2.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
