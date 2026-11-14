#!/usr/bin/env python3
"""Build the MedRadar PRODUCT-001 regulatory snapshot from openFDA.

This is the only component that writes medradar/product/snapshot/. It is deliberately boring and auditable:

* it queries the public openFDA API (no key, no paid service) with a documented User-Agent;
* every request URL is recorded in the manifest so a reviewer can replay the collection;
* records keep the source identifiers, dates, applicant strings and product codes needed for
  evidence, and drop the large "openfda" cross-reference blocks that a product record does not
  need and that would bloat the repository;
* output is deterministic (sorted keys, gzip mtime 0) so a re-run can be diffed.

Usage:

    python scripts/product_collect.py                 # full collection
    python scripts/product_collect.py --orgs medtronic,ge_healthcare
    python scripts/product_collect.py --dry-run       # print the queries only

The snapshot is data, not truth: the product layer attributes applicant strings to
organizations using medradar/product/identity/organizations.json and reports everything it
cannot attribute. See docs/product/DATA_CONTRACT.md.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "medradar" / "product" / "identity" / "organizations.json"
#: The snapshot is vendored product data (committed, hash-addressed), not runtime output: it
#: ships with the package and is what the API serves by default.
OUT_DIR = ROOT / "medradar" / "product" / "snapshot"

VERSION = "medradar-collector/1.0.0"
BASE = "https://api.fda.gov"
USER_AGENT = "MedRadar/1.0 (medical technology intelligence; +https://github.com/ChazY11/medradar)"
PAGE_LIMIT = 1000
MAX_PAGES = 60
SLEEP_SECONDS = 0.35
RETRIES = 4

SOURCES = {
    "openfda_510k": {
        "path": "/device/510k.json",
        "search_field": "applicant",
        "name": "FDA 510(k) premarket notifications",
    },
    "openfda_pma": {
        "path": "/device/pma.json",
        "search_field": "applicant",
        "name": "FDA premarket approval (PMA) decisions",
    },
    "openfda_recall": {
        "path": "/device/recall.json",
        "search_field": "recalling_firm",
        "name": "FDA device recall records",
    },
}

CLASSIFICATION_PATH = "/device/classification.json"


class Fetcher:
    def __init__(self, delay: float = SLEEP_SECONDS) -> None:
        self.delay = delay
        self.requests = 0
        self.bytes = 0
        self.last_meta: dict = {}
        self.errors: list[dict] = []

    def get_json(self, url: str) -> dict:
        attempt = 0
        while True:
            attempt += 1
            request = urllib.request.Request(
                url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"}
            )
            try:
                with urllib.request.urlopen(request, timeout=90) as response:
                    payload = response.read()
                self.requests += 1
                self.bytes += len(payload)
                time.sleep(self.delay)
                data = json.loads(payload.decode("utf-8"))
                meta = data.get("meta") or {}
                if meta.get("last_updated"):
                    self.last_meta = meta
                return data
            except urllib.error.HTTPError as error:
                body = ""
                try:
                    body = error.read().decode("utf-8", "replace")[:400]
                except Exception:
                    pass
                if error.code == 404:
                    # openFDA returns 404 for "no matches found": an empty result, not a failure.
                    time.sleep(self.delay)
                    return {"meta": {"results": {"total": 0, "skip": 0, "limit": PAGE_LIMIT}}, "results": []}
                if error.code in (429, 500, 502, 503, 504) and attempt <= RETRIES:
                    wait = min(60.0, 2.0 ** attempt + 0.5 * attempt)
                    print("    HTTP " + str(error.code) + "; retry in " + format(wait, ".0f") + "s", file=sys.stderr)
                    time.sleep(wait)
                    continue
                self.errors.append({"url": url, "status": error.code, "body": body})
                raise
            except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as error:
                if attempt <= RETRIES:
                    wait = min(60.0, 2.0 ** attempt)
                    print("    network error " + str(error) + "; retry in " + format(wait, ".0f") + "s", file=sys.stderr)
                    time.sleep(wait)
                    continue
                self.errors.append({"url": url, "status": "network", "body": str(error)})
                raise


def build_url(path: str, search_field: str | None, tokens: list[str], skip: int, limit: int = PAGE_LIMIT) -> str:
    params: list[tuple[str, str]] = []
    if search_field:
        expression = search_field + ":(" + " OR ".join('"' + token + '"' for token in tokens) + ")"
        params.append(("search", expression))
    params.append(("limit", str(limit)))
    params.append(("skip", str(skip)))
    query = urllib.parse.urlencode(params, quote_via=urllib.parse.quote)
    return BASE + path + "?" + query


def clean(value) -> str | None:
    if value is None:
        return None
    if isinstance(value, list):
        value = "; ".join(str(item) for item in value if item not in (None, ""))
    text = " ".join(str(value).split())
    return text or None


def multiline(value) -> str | None:
    if value is None:
        return None
    text = " ".join(str(value).replace("\r", " ").split("\n"))
    text = " ".join(text.split())
    return text or None


def normalise_510k(record: dict) -> dict:
    k_number = clean(record.get("k_number")) or ""
    decision = clean(record.get("decision_date"))
    raw = {
        "k_number": k_number,
        "applicant": clean(record.get("applicant")),
        "decision_date": decision,
        "date_received": clean(record.get("date_received")),
        "device_name": clean(record.get("device_name")),
        "product_code": clean(record.get("product_code")),
        "decision_code": clean(record.get("decision_code")),
        "decision_description": clean(record.get("decision_description")),
        "advisory_committee": clean(record.get("advisory_committee")),
        "advisory_committee_description": clean(record.get("advisory_committee_description")),
        "country_code": clean(record.get("country_code")),
        "clearance_type": clean(record.get("clearance_type")),
        "expedited_review_flag": clean(record.get("expedited_review_flag")),
        "statement_or_summary": clean(record.get("statement_or_summary")),
    }
    device = raw["device_name"] or ""
    return {
        "event_id": "openfda_510k:" + k_number,
        "source_id": "openfda_510k",
        "event_type": "510k",
        "official_id": k_number,
        "event_date": decision,
        "published_at": None,
        "published_at_status": "not_published_by_source",
        "time_quality": "date_from_source" if decision else "unknown",
        "applicant_name": raw["applicant"] or "",
        "product_code": raw["product_code"],
        "device_name": raw["device_name"],
        "summary": raw["statement_or_summary"],
        "title": (k_number + " " + device).strip(),
        "official_url": "https://www.accessdata.fda.gov/scripts/cdrh/cfdocs/cfpmn/pmn.cfm?ID=" + urllib.parse.quote(k_number),
        "raw": raw,
    }


def normalise_pma(record: dict) -> dict:
    pma_number = clean(record.get("pma_number")) or ""
    supplement = clean(record.get("supplement_number")) or ""
    is_original = supplement in ("", "0", "-", "S000")
    decision = clean(record.get("decision_date"))
    official_id = pma_number if is_original else pma_number + ":" + supplement
    raw = {
        "pma_number": pma_number,
        "supplement_number": supplement,
        "supplement_type": clean(record.get("supplement_type")),
        "supplement_reason": clean(record.get("supplement_reason")),
        "applicant": clean(record.get("applicant")),
        "decision_date": decision,
        "date_received": clean(record.get("date_received")),
        "product_code": clean(record.get("product_code")),
        "generic_name": clean(record.get("generic_name")),
        "trade_name": clean(record.get("trade_name")),
        "advisory_committee": clean(record.get("advisory_committee")),
        "advisory_committee_description": clean(record.get("advisory_committee_description")),
        "decision_code": clean(record.get("decision_code")),
        "ao_statement": multiline(record.get("ao_statement")),
        "expedited_review_flag": clean(record.get("expedited_review_flag")),
        "docket_number": clean(record.get("docket_number")),
    }
    summary = raw["generic_name"]
    if raw["trade_name"]:
        summary = (summary + " - " + raw["trade_name"]) if summary else raw["trade_name"]
    if not is_original and raw["supplement_type"]:
        summary = (summary + " (" + raw["supplement_type"] + ")") if summary else raw["supplement_type"]
    url = "https://www.accessdata.fda.gov/scripts/cdrh/cfdocs/cfpma/pma.cfm?id=" + urllib.parse.quote(pma_number)
    if not is_original:
        url += "&supplement_number=" + urllib.parse.quote(supplement)
    label = pma_number if is_original else pma_number + " " + supplement
    device = raw["generic_name"] or raw["trade_name"] or ""
    return {
        "event_id": "openfda_pma:" + official_id,
        "source_id": "openfda_pma",
        "event_type": "pma" if is_original else "pma_supplement",
        "official_id": official_id,
        "event_date": decision,
        "published_at": None,
        "published_at_status": "not_published_by_source",
        "time_quality": "date_from_source" if decision else "unknown",
        "applicant_name": raw["applicant"] or "",
        "product_code": raw["product_code"],
        "device_name": device or None,
        "summary": summary,
        "title": (label + " " + device).strip(),
        "official_url": url,
        "raw": raw,
    }


def normalise_recall(record: dict) -> dict:
    product_res = clean(record.get("product_res_number")) or ""
    event_number = clean(record.get("res_event_number")) or ""
    cfres = clean(record.get("cfres_id")) or ""
    initiated = clean(record.get("event_date_initiated"))
    posted = clean(record.get("event_date_posted"))
    official_id = product_res or cfres or event_number
    k_numbers = record.get("k_numbers")
    raw = {
        "product_res_number": product_res,
        "res_event_number": event_number,
        "cfres_id": cfres,
        "recalling_firm": clean(record.get("recalling_firm")),
        "event_date_initiated": initiated,
        "event_date_posted": posted,
        "event_date_created": clean(record.get("event_date_created")),
        "event_date_terminated": clean(record.get("event_date_terminated")),
        "recall_status": clean(record.get("recall_status")),
        "product_code": clean(record.get("product_code")),
        "product_description": multiline(record.get("product_description")),
        "reason_for_recall": multiline(record.get("reason_for_recall")),
        "root_cause_description": clean(record.get("root_cause_description")),
        "action": multiline(record.get("action")),
        "distribution_pattern": multiline(record.get("distribution_pattern")),
        "code_info": multiline(record.get("code_info")),
        "product_quantity": clean(record.get("product_quantity")),
        "city": clean(record.get("city")),
        "state": clean(record.get("state")),
        "k_numbers": k_numbers[:5] if isinstance(k_numbers, list) else None,
    }
    if initiated:
        event_date, time_quality = initiated, "date_from_source"
    elif posted:
        event_date, time_quality = posted, "date_derived_from_source"
    else:
        event_date, time_quality = None, "unknown"
    url = "https://www.accessdata.fda.gov/scripts/cdrh/cfdocs/cfRes/res.cfm?id=" + urllib.parse.quote(event_number)
    device = raw["product_description"] or ""
    return {
        "event_id": "openfda_recall:" + official_id,
        "source_id": "openfda_recall",
        "event_type": "recall",
        "official_id": official_id,
        "event_date": event_date,
        "published_at": posted,
        "published_at_status": "from_source" if posted else "not_published_by_source",
        "time_quality": time_quality,
        "applicant_name": raw["recalling_firm"] or "",
        "product_code": raw["product_code"],
        "device_name": raw["product_description"],
        "summary": raw["reason_for_recall"],
        "title": (official_id + " " + device).strip(),
        "official_url": url,
        "raw": raw,
    }


NORMALISE = {
    "openfda_510k": normalise_510k,
    "openfda_pma": normalise_pma,
    "openfda_recall": normalise_recall,
}


def collect_org_source(fetcher: Fetcher, source_id: str, org: dict, tokens: list[str]) -> tuple[list[dict], dict]:
    source = SOURCES[source_id]
    records: list[dict] = []
    audit = {"source_id": source_id, "pages": 0, "urls": [], "records": 0, "total_reported": 0}
    seen: set[str] = set()
    skip = 0
    page = 0
    while page < MAX_PAGES:
        url = build_url(source["path"], source["search_field"], tokens, skip)
        payload = fetcher.get_json(url)
        meta_results = (payload.get("meta") or {}).get("results") or {}
        total = int(meta_results.get("total") or 0)
        audit["urls"].append(url)
        audit["total_reported"] = max(audit["total_reported"], total)
        results = payload.get("results") or []
        page += 1
        audit["pages"] = page
        for record in results:
            event = NORMALISE[source_id](record)
            if event["event_id"] in seen:
                continue
            seen.add(event["event_id"])
            event["retrieved_by"] = org["key"]
            records.append(event)
        if not results or skip + PAGE_LIMIT >= total:
            break
        skip += PAGE_LIMIT
    audit["records"] = len(records)
    return records, audit


def collect_classifications(fetcher: Fetcher) -> tuple[list[dict], dict]:
    rows: list[dict] = []
    audit = {"pages": 0, "urls": [], "records": 0}
    skip = 0
    page = 0
    while page < MAX_PAGES:
        url = build_url(CLASSIFICATION_PATH, None, [], skip)
        payload = fetcher.get_json(url)
        total = int(((payload.get("meta") or {}).get("results") or {}).get("total") or 0)
        audit["urls"].append(url)
        results = payload.get("results") or []
        page += 1
        audit["pages"] = page
        for record in results:
            code = clean(record.get("product_code"))
            if not code:
                continue
            rows.append({
                "product_code": code,
                "device_name": clean(record.get("device_name")),
                "specialty": clean(record.get("medical_specialty_description")) or clean(record.get("review_panel")),
                "device_class": clean(record.get("device_class")),
                "regulation_number": clean(record.get("regulation_number")),
                "implant_flag": clean(record.get("implant_flag")),
                "life_sustaining": clean(record.get("life_sustain_support_flag")),
            })
        if not results or skip + PAGE_LIMIT >= total:
            break
        skip += PAGE_LIMIT
    audit["records"] = len(rows)
    return rows, audit


def gzip_write(path: Path, lines: list[str]) -> dict:
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = ("\n".join(lines) + "\n").encode("utf-8")
    digest = hashlib.sha256(raw).hexdigest()
    with path.open("wb") as handle:
        with gzip.GzipFile(filename="", mode="wb", fileobj=handle, mtime=0) as gz:
            gz.write(raw)
    return {"sha256": digest, "bytes": path.stat().st_size, "records": len(lines)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Collect the MedRadar regulatory snapshot.")
    parser.add_argument("--orgs", help="comma separated organization keys (default: all)")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--out", default=str(OUT_DIR))
    parser.add_argument("--keep-scope", action="store_true", help="keep per-record collection scope (used by sharded runs, removed by --merge)")
    parser.add_argument("--merge", nargs="*", default=None, help="merge shard snapshot directories into --out")
    args = parser.parse_args(argv)

    if args.merge is not None:
        return merge_snapshots([Path(item) for item in args.merge], Path(args.out))

    registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
    organizations = registry["organizations"]
    if args.orgs:
        wanted = {item.strip() for item in args.orgs.split(",") if item.strip()}
        organizations = [org for org in organizations if org["key"] in wanted]
        missing = wanted - {org["key"] for org in organizations}
        if missing:
            print("unknown organization key(s): " + ", ".join(sorted(missing)), file=sys.stderr)
            return 2

    if args.dry_run:
        for org in organizations:
            for source_id in SOURCES:
                print(org["key"], source_id, build_url(SOURCES[source_id]["path"], SOURCES[source_id]["search_field"], org["search_tokens"], 0, 10))
        return 0

    started = datetime.now(timezone.utc)
    fetcher = Fetcher()
    all_events: dict[str, dict] = {}
    org_audit: list[dict] = []
    print("collecting " + str(len(organizations)) + " organizations from openFDA ...")
    for index, org in enumerate(organizations, 1):
        tokens = org["search_tokens"]
        entry = {"key": org["key"], "display_name": org["display_name"], "queries": [], "records": 0}
        for source_id in SOURCES:
            print("  [" + str(index) + "/" + str(len(organizations)) + "] " + org["key"] + " / " + source_id + " ...", end="", flush=True)
            try:
                records, audit = collect_org_source(fetcher, source_id, org, tokens)
            except Exception as error:
                print(" FAILED (" + str(error) + ")")
                entry["queries"].append({"source_id": source_id, "error": str(error)})
                continue
            print(" " + str(audit["records"]) + " records (" + str(audit["pages"]) + " pages)")
            for record in records:
                existing = all_events.get(record["event_id"])
                if existing is None:
                    all_events[record["event_id"]] = record
                else:
                    scopes = existing.setdefault("retrieved_by_all", [existing.get("retrieved_by")])
                    if record["retrieved_by"] not in scopes:
                        scopes.append(record["retrieved_by"])
            entry["records"] += len(records)
            entry["queries"].append(audit)
        org_audit.append(entry)

    print("collecting product-code classification ...", end="", flush=True)
    classifications, class_audit = collect_classifications(fetcher)
    print(" " + str(len(classifications)) + " codes")

    finished = datetime.now(timezone.utc)
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    events = sorted(all_events.values(), key=lambda item: item["event_id"])

    applicants: dict[str, dict] = {}
    for event in events:
        name = event["applicant_name"]
        if not name:
            continue
        bucket = applicants.setdefault(name, {"applicant_name": name, "records": 0, "by_source": {}, "by_org_scope": {}})
        bucket["records"] += 1
        bucket["by_source"][event["source_id"]] = bucket["by_source"].get(event["source_id"], 0) + 1
        for scope in event.get("retrieved_by_all") or [event.get("retrieved_by")]:
            if scope:
                bucket["by_org_scope"][scope] = bucket["by_org_scope"].get(scope, 0) + 1

    if not args.keep_scope:
        for event in events:
            event.pop("retrieved_by", None)
            event.pop("retrieved_by_all", None)

    compacted, compaction = apply_compaction(events)
    event_lines = [json.dumps(item, ensure_ascii=False, sort_keys=True) for item in compacted]
    applicant_lines = [json.dumps(applicants[name], ensure_ascii=False, sort_keys=True) for name in sorted(applicants)]
    classification_lines = [
        json.dumps(row, ensure_ascii=False, sort_keys=True)
        for row in sorted(classifications, key=lambda item: item["product_code"])
    ]

    files = {
        "events.jsonl.gz": gzip_write(out_dir / "events.jsonl.gz", event_lines),
        "applicants.jsonl.gz": gzip_write(out_dir / "applicants.jsonl.gz", applicant_lines),
        "classifications.jsonl.gz": gzip_write(out_dir / "classifications.jsonl.gz", classification_lines),
    }

    by_source: dict[str, int] = {}
    by_type: dict[str, int] = {}
    dates = []
    for event in compacted:
        by_source[event["source_id"]] = by_source.get(event["source_id"], 0) + 1
        by_type[event["event_type"]] = by_type.get(event["event_type"], 0) + 1
        if event.get("event_date"):
            dates.append(event["event_date"])

    snapshot_id = finished.strftime("%Y-%m-%dT%H:%M:%SZ") + "-openfda"
    manifest = {
        "schema": "medradar.snapshot.v1",
        "id": snapshot_id,
        "collected_at": finished.isoformat().replace("+00:00", "Z"),
        "collection_started_at": started.isoformat().replace("+00:00", "Z"),
        "collector": {"name": VERSION, "user_agent": USER_AGENT, "api_base": BASE},
        "openfda": {"last_updated": (fetcher.last_meta or {}).get("last_updated")},
        "organization_count": len(organizations),
        "request_count": fetcher.requests,
        "response_bytes": fetcher.bytes,
        "errors": fetcher.errors,
        "files": files,
        "counts": {
            "records": len(events),
            "applicant_strings": len(applicant_lines),
            "product_codes": len(classification_lines),
            "by_source": by_source,
            "by_event_type": by_type,
        },
        "coverage": {
            "min_event_date": min(dates) if dates else None,
            "max_event_date": max(dates) if dates else None,
        },
        "classification_query": class_audit,
        "data_quality": compaction,
        "organizations": org_audit,
        "notes": [
            "Snapshot of openFDA device endpoints collected by scripts/product_collect.py.",
            "Records are organisational data from the source; applicant-to-organization attribution happens at read time using medradar/product/identity/organizations.json.",
            "510(k) and PMA records expose no publication timestamp in openFDA; published_at is null for those sources by rule.",
        ],
    }
    (out_dir / "snapshot.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print()
    print("wrote snapshot " + snapshot_id + ": " + str(len(events)) + " events, " + str(len(applicant_lines)) + " applicant strings, " + str(len(classification_lines)) + " product codes")
    print("requests=" + str(fetcher.requests) + " response_bytes=" + str(fetcher.bytes) + " output=" + str(out_dir))
    return 0


# --------------------------------------------------------------------------- compaction
#: Long free-text fields are kept for evidence but bounded, so the snapshot stays a
#: reasonable repository artefact. Nothing is added; only verbatim text is truncated.
RAW_LIMITS = {
    "action": 300,
    "distribution_pattern": 200,
    "code_info": 200,
    "product_quantity": 80,
    "product_description": 300,
    "reason_for_recall": 400,
    "statement_or_summary": 200,
    "ao_statement": 240,
    "trade_name": 160,
    "generic_name": 160,
    "supplement_reason": 140,
    "supplement_type": 80,
    "decision_description": 120,
    "advisory_committee_description": 80,
}
SUMMARY_LIMIT = 400
DEVICE_NAME_LIMIT = 220
MIN_PLAUSIBLE_YEAR = 1900


def _truncate(text: str | None, limit: int) -> str | None:
    if text is None:
        return None
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def _plausible_date(value: str | None) -> bool:
    if not value:
        return False
    try:
        year = int(str(value)[:4])
    except ValueError:
        return False
    return MIN_PLAUSIBLE_YEAR <= year <= 2100


def finalise_event(event: dict) -> tuple[dict, list[str]]:
    """Bound text fields and quarantine implausible dates. Returns (event, flags)."""
    flags: list[str] = []
    result = dict(event)
    raw = dict(result.get("raw") or {})
    for key, limit in RAW_LIMITS.items():
        if key in raw:
            raw[key] = _truncate(raw.get(key), limit)
    for key in list(raw.keys()):
        if raw[key] in (None, ""):
            raw.pop(key)
    if not _plausible_date(result.get("event_date")):
        if result.get("event_date"):
            flags.append("implausible_event_date")
            raw["event_date_as_published"] = result.get("event_date")
        result["event_date"] = None
        result["time_quality"] = "unknown"
    result["device_name"] = _truncate(result.get("device_name"), DEVICE_NAME_LIMIT)
    result["summary"] = _truncate(result.get("summary"), SUMMARY_LIMIT)
    result.pop("title", None)
    result["raw"] = raw
    return result, flags


def apply_compaction(events: list[dict]) -> tuple[list[dict], dict]:
    """Bound text fields and quarantine implausible dates, returning compacted records."""
    stats = {"records": len(events), "implausible_event_date": 0, "truncated_text_fields": 0}
    compacted_rows = []
    for event in events:
        compacted, flags = finalise_event(event)
        if flags:
            stats["implausible_event_date"] += 1
        compacted_rows.append(compacted)
    return compacted_rows, stats


# --------------------------------------------------------------------------- merge
def _read_jsonl(path: Path) -> list[dict]:
    rows: list[dict] = []
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def merge_snapshots(dirs: list[Path], out_dir: Path) -> int:
    """Merge shard snapshots produced with --keep-scope into one final snapshot.

    Sharded collection exists because openFDA responses are large and the full sweep is
    otherwise serial. The merge is deterministic: events are de-duplicated by event id, the
    per-record collection scope is combined, applicant aggregates are recomputed from the merged
    records, and the manifest is rebuilt with a single collected_at = the latest shard time.
    """
    if not dirs:
        print("no shard directories given", file=sys.stderr)
        return 2
    events: dict[str, dict] = {}
    organizations: list[dict] = []
    errors: list[dict] = []
    request_count = 0
    response_bytes = 0
    last_updated = None
    started_at = None
    finished_at = None
    classifications: list[dict] = []
    for directory in dirs:
        manifest_path = directory / "snapshot.json"
        if not manifest_path.exists():
            print("missing manifest in " + str(directory), file=sys.stderr)
            return 2
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        request_count += int(manifest.get("request_count") or 0)
        response_bytes += int(manifest.get("response_bytes") or 0)
        errors.extend(manifest.get("errors") or [])
        organizations.extend(manifest.get("organizations") or [])
        candidate = (manifest.get("openfda") or {}).get("last_updated")
        last_updated = last_updated or candidate
        started_at = min(filter(None, [started_at, manifest.get("collection_started_at")]))
        finished_at = max(filter(None, [finished_at, manifest.get("collected_at")]))
        if not classifications:
            class_file = directory / "classifications.jsonl.gz"
            if class_file.exists():
                classifications = _read_jsonl(class_file)
        events_file = directory / "events.jsonl.gz"
        if not events_file.exists():
            continue
        for event in _read_jsonl(events_file):
            existing = events.get(event["event_id"])
            if existing is None:
                events[event["event_id"]] = event
            else:
                scopes = set(existing.get("retrieved_by_all") or [existing.get("retrieved_by")])
                scopes.update(event.get("retrieved_by_all") or [event.get("retrieved_by")])
                existing["retrieved_by_all"] = sorted(item for item in scopes if item)

    merged = sorted(events.values(), key=lambda item: item["event_id"])
    applicants: dict[str, dict] = {}
    for event in merged:
        name = event.get("applicant_name") or ""
        if not name:
            continue
        bucket = applicants.setdefault(name, {"applicant_name": name, "records": 0, "by_source": {}, "by_org_scope": {}})
        bucket["records"] += 1
        bucket["by_source"][event["source_id"]] = bucket["by_source"].get(event["source_id"], 0) + 1
        for scope in event.get("retrieved_by_all") or ([event["retrieved_by"]] if event.get("retrieved_by") else []):
            if scope:
                bucket["by_org_scope"][scope] = bucket["by_org_scope"].get(scope, 0) + 1
    for event in merged:
        event.pop("retrieved_by", None)
        event.pop("retrieved_by_all", None)

    compacted, compaction = apply_compaction(merged)
    event_lines = [json.dumps(event, ensure_ascii=False, sort_keys=True) for event in compacted]
    applicant_lines = [json.dumps(applicants[name], ensure_ascii=False, sort_keys=True) for name in sorted(applicants)]
    classification_lines = [json.dumps(row, ensure_ascii=False, sort_keys=True) for row in sorted(classifications, key=lambda item: item["product_code"])]

    out_dir.mkdir(parents=True, exist_ok=True)
    files = {
        "events.jsonl.gz": gzip_write(out_dir / "events.jsonl.gz", event_lines),
        "applicants.jsonl.gz": gzip_write(out_dir / "applicants.jsonl.gz", applicant_lines),
        "classifications.jsonl.gz": gzip_write(out_dir / "classifications.jsonl.gz", classification_lines),
    }
    by_source: dict[str, int] = {}
    by_type: dict[str, int] = {}
    dates = []
    for event in compacted:
        by_source[event["source_id"]] = by_source.get(event["source_id"], 0) + 1
        by_type[event["event_type"]] = by_type.get(event["event_type"], 0) + 1
        if event.get("event_date"):
            dates.append(event["event_date"])
    organizations.sort(key=lambda item: item["key"])
    snapshot_id = ((finished_at or "unknown")[:19] + "Z") + "-openfda"
    manifest = {
        "schema": "medradar.snapshot.v1",
        "id": snapshot_id,
        "collected_at": finished_at,
        "collection_started_at": started_at,
        "collector": {"name": VERSION, "user_agent": USER_AGENT, "api_base": BASE, "mode": "sharded-merge"},
        "openfda": {"last_updated": last_updated},
        "organization_count": len(organizations),
        "request_count": request_count,
        "response_bytes": response_bytes,
        "errors": errors,
        "files": files,
        "counts": {
            "records": len(merged),
            "applicant_strings": len(applicant_lines),
            "product_codes": len(classification_lines),
            "by_source": by_source,
            "by_event_type": by_type,
        },
        "coverage": {"min_event_date": min(dates) if dates else None, "max_event_date": max(dates) if dates else None},
        "classification_query": {"source": "merged from shard snapshot", "records": len(classifications)},
        "data_quality": compaction,
        "organizations": organizations,
        "notes": [
            "Merged from sharded openFDA collection (see scripts/product_collect.py).",
            "Records are organisational data from the source; applicant-to-organization attribution happens at read time using medradar/product/identity/organizations.json.",
            "510(k) and PMA records expose no publication timestamp in openFDA; published_at is null for those sources by rule.",
        ],
    }
    (out_dir / "snapshot.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print("merged " + str(len(dirs)) + " shards -> " + str(out_dir))
    print("events=" + str(len(merged)) + " applicants=" + str(len(applicant_lines)) + " product_codes=" + str(len(classification_lines)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
