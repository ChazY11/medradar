"""Independently re-verify stored recall events against the live openFDA API (V1-001).

What this checks, and what it cannot check
-----------------------------------------
For each requested FDA recall event it sends a NEW query to the official openFDA endpoint
(search=res_event_number:"ID") and compares the live answer with what the ledger stored: the set
of product recall numbers, the event and posting dates, the action status, the recalling firm and
a normalised hash of the reason text. A mismatch is reported, never smoothed.

It does NOT open the FDA web page: www.accessdata.fda.gov answers an automated client with a
JavaScript countdown interstitial (HTTP 400), so the human-readable page was not retrieved from
this host. The openFDA answer is the same regulatory record in machine-readable form; that is a
real verification of content identity, not of the rendered page.

Usage:
    python docs/v1/001/_scripts/verify_reference_events.py --db DB --events 99908,99549 --json OUT
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))

API = "https://api.fda.gov/device/recall.json"
UA = "MedRadarBot/0.1 (+https://github.com/ChazY11/medradar; research)"


def _norm(text) -> str:
    return " ".join(str(text or "").lower().split())


def _digest(text) -> str:
    return hashlib.sha256(_norm(text).encode("utf-8")).hexdigest()[:16]


def live_event(event_id: str) -> list:
    params = {"search": "res_event_number:" + json.dumps(str(event_id)), "limit": 100}
    url = API + "?" + urllib.parse.urlencode(params)
    request = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(request, timeout=45) as response:
            data = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        if error.code == 404:
            return []
        raise
    return [row for row in (data.get("results") or []) if isinstance(row, dict)]


def stored_event(db: Path, event_id: str) -> list:
    con = sqlite3.connect("file:" + db.as_posix() + "?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    sql = ("SELECT o.observation_id, o.official_identifier, o.source_url, o.first_observed_at,"
           " v.payload FROM observation o"
           " JOIN observation_version v ON v.version_id = o.latest_version_id")
    out = []
    for row in con.execute(sql).fetchall():
        payload = json.loads(row["payload"] or "{}")
        if str(payload.get("res_event_number") or "") != str(event_id):
            continue
        out.append({"observation_id": row["observation_id"],
                    "official_identifier": row["official_identifier"],
                    "source_url": row["source_url"],
                    "first_observed_at": row["first_observed_at"],
                    "payload": payload})
    con.close()
    return out


def compare(event_id: str, stored: list, live: list) -> dict:
    stored_numbers = sorted(str(item["payload"].get("product_res_number") or "") for item in stored)
    live_numbers = sorted(str(item.get("product_res_number") or "") for item in live)
    stored_row = stored[0]["payload"] if stored else {}
    live_row = live[0] if live else {}
    checks = {
        "event_present_live": bool(live),
        "same_product_numbers": stored_numbers == live_numbers,
        "same_posted_date": str(stored_row.get("event_date_posted") or "")
                            == str(live_row.get("event_date_posted") or ""),
        "same_status": str(stored_row.get("recall_status") or "")
                       == str(live_row.get("recall_status") or ""),
        "same_firm": _norm(stored_row.get("recalling_firm")) == _norm(live_row.get("recalling_firm")),
        "same_reason_text": _digest(stored_row.get("reason_for_recall"))
                            == _digest(live_row.get("reason_for_recall")),
    }
    return {
        "event_id": str(event_id),
        "stored_records": len(stored),
        "live_records": len(live),
        "checks": checks,
        "ok": all(checks.values()),
        "stored": {"product_res_numbers": stored_numbers,
                   "posted": stored_row.get("event_date_posted"),
                   "status": stored_row.get("recall_status"),
                   "firm": stored_row.get("recalling_firm"),
                   "reason_digest": _digest(stored_row.get("reason_for_recall")),
                   "url": (stored[0]["source_url"] if stored else None),
                   "first_observed_at": (stored[0]["first_observed_at"] if stored else None)},
        "live": {"product_res_numbers": live_numbers,
                 "posted": live_row.get("event_date_posted"),
                 "status": live_row.get("recall_status"),
                 "firm": live_row.get("recalling_firm"),
                 "reason_digest": _digest(live_row.get("reason_for_recall"))},
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="verify stored recall events against openFDA")
    parser.add_argument("--db", required=True)
    parser.add_argument("--events", required=True, help="comma separated res_event_number values")
    parser.add_argument("--json", default=None)
    args = parser.parse_args(argv)
    results = []
    for event_id in [item.strip() for item in args.events.split(",") if item.strip()]:
        results.append(compare(event_id, stored_event(Path(args.db), event_id),
                              live_event(event_id)))
    payload = {"api": API, "verified_at": "live openFDA request made by this run",
               "results": results, "ok": all(item["ok"] for item in results),
               "limitation": "the human-readable FDA page was not retrieved (the site answers a"
                             " JavaScript interstitial); identity is verified against the same"
                             " record in the official machine-readable API"}
    if args.json:
        Path(args.json).parent.mkdir(parents=True, exist_ok=True)
        Path(args.json).write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        print("wrote " + args.json)
    for item in results:
        tag = "[OK]   " if item["ok"] else "[FAIL] "
        print("  " + tag + " event " + item["event_id"] + " stored=" + str(item["stored_records"])
              + " live=" + str(item["live_records"]))
        if not item["ok"]:
            for name, value in item["checks"].items():
                if not value:
                    print("         mismatch: " + name)
    print("all events verified: " + str(payload["ok"]))
    return 0 if payload["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
