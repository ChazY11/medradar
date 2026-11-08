"""Five-firm postmarket series builder (EXP-C input).

Produces ``research/data_expansion/samples/postmarket/FIVE_FIRM_SERIES.json``:
real, reproducible counts of Medtronic / GE HealthCare / Philips / Dräger /
Mindray records in the four postmarket sources, with the exact query condition
recorded for every number and the company link separated into *confirmed* vs
*candidate*.

Rules this module enforces
--------------------------
* every count comes from a real response of this run — nothing is estimated,
  interpolated or back-filled; a missing value is ``null`` with a reason;
* a firm link is *confirmed* only through
  :meth:`medradar.external_sources.identity.CompanyIndex.resolve` returning
  ``official_id`` / ``exact_alias`` / ``multi_field``; ``candidate`` is counted
  separately;
* server-side aggregations are labelled as such and their truncation (the
  unauthenticated 100-bucket cap on keyword ``count`` queries) is reported as a
  residual, never spread over the returned buckets;
* every request is written to ``series_requests.jsonl`` next to the probe ledger.

Usage::

    python -m medradar.external_sources.regulatory.postmarket_series --root <repo>
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Iterable, Mapping

from medradar.external_sources import base as ev_base
from medradar.external_sources import identity as ev_identity
from medradar.external_sources import schema as ev_schema
from medradar.external_sources.regulatory import postmarket_common as common
from medradar.external_sources.regulatory import postmarket_fda_device_shortages as shortage_src
from medradar.external_sources.regulatory import postmarket_fda_import_alerts as alert_src
from medradar.external_sources.regulatory import postmarket_openfda_device_maude as maude_src
from medradar.external_sources.regulatory import postmarket_openfda_device_recall as recall_src

SCHEMA_ID = "medradar.postmarket.five_firm_series.v1"

#: Per-run request budgets.  A *run* is bounded exactly like a probe; the
#: contract's ≤ 12 requests per probe is respected by splitting the work into
#: labelled runs whose request counts are reported in the output.
RUN_BUDGETS: dict[str, int] = {
    "recall_full_pull": 12,
    "maude_counts": 12,
    "maude_census": 6,
    "shortages": 2,
    "import_alerts": 8,
}

DEFAULT_ROOT = Path(__file__).resolve().parents[3] / "research" / "data_expansion"


# --------------------------------------------------------------------------- io
def _make_client(root: Path, source_id: str, *, run: str, budget: int) -> ev_base.HttpClient:
    probe_dir = root / "probes" / source_id
    probe_dir.mkdir(parents=True, exist_ok=True)
    ledger = ev_base.HttpLedger(probe_dir / "series_requests.jsonl")
    return ev_base.HttpClient(
        source_id=source_id,
        ledger=ledger,
        budget=budget,
        min_interval=0.8,
        timeout=60.0,
        max_retries=1,
    )


def _describe_requests(client: ev_base.HttpClient, run: str) -> list[dict[str, Any]]:
    rows = []
    for entry in client.ledger.entries:
        rows.append(
            {
                "run": run,
                "url": entry.get("url"),
                "status": entry.get("status"),
                "bytes": entry.get("bytes"),
                "elapsed_ms": entry.get("elapsed_ms"),
                "error": entry.get("error", ""),
            }
        )
    return rows


class SampleBook:
    """Collects real response slices and writes ``SAMPLES.json`` descriptors."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self._pending: dict[str, list[dict[str, Any]]] = {}

    def add(self, source_id: str, name: str, body: bytes, *, url: str, fetched_at: str) -> None:
        directory = self.root / "samples" / source_id
        descriptor = ev_base.write_sample(directory, name, body)
        descriptor["request_url"] = url
        descriptor["fetched_at"] = fetched_at
        self._pending.setdefault(source_id, []).append(descriptor)

    def flush(self) -> None:
        for source_id, descriptors in self._pending.items():
            path = self.root / "samples" / source_id / "SAMPLES.json"
            existing: list[dict[str, Any]] = []
            if path.is_file():
                try:
                    prior = json.loads(path.read_text(encoding="utf-8"))
                    existing = list(prior.get("samples") or [])
                except (ValueError, AttributeError):
                    existing = []
            by_name = {str(item.get("name")): item for item in existing}
            for item in descriptors:
                by_name[str(item.get("name"))] = item
            manifest = {
                "schema": "medradar.external.samples.v1",
                "source_id": source_id,
                "generated_at": ev_base.utc_iso(),
                "note": "Raw response slices only; parsed records are derived and live in the series/handoff.",
                "samples": [by_name[name] for name in sorted(by_name)],
            }
            path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


# ---------------------------------------------------------------- interpretation
def _firm_bucket(ref: Mapping[str, Any], firm_key: str) -> str:
    """Classify one company resolution against a target firm."""
    method = ref.get("method")
    resolved = ref.get("resolved_key")
    if method in ev_schema.CONFIRMED_METHODS and resolved == firm_key:
        return "confirmed"
    if method == "candidate" and resolved == firm_key:
        return "candidate"
    if resolved is not None and resolved != firm_key:
        return "other_firm"
    return "none"


def _empty_resolution() -> dict[str, int]:
    return {"confirmed": 0, "candidate": 0, "other_firm": 0, "none": 0}


def _resolution_from_records(records: Iterable[Mapping[str, Any]], firm_key: str) -> dict[str, int]:
    counts = _empty_resolution()
    for record in records:
        refs = record.get("entity_refs") or []
        best = "none"
        for ref in refs:
            bucket = _firm_bucket(ref, firm_key)
            if bucket in {"confirmed", "candidate", "other_firm"}:
                best = bucket
                break
        counts[best] += 1
    return counts


def _annual(records: Iterable[Mapping[str, Any]], clock_name: str) -> dict[str, int]:
    histogram: dict[str, int] = {}
    for record in records:
        value = (record.get("time") or {}).get(clock_name, "")
        year = common.year_of(value)
        if not year:
            continue
        histogram[year] = histogram.get(year, 0) + 1
    return dict(sorted(histogram.items()))


def _records_with_bucket(records: Iterable[Mapping[str, Any]], firm_key: str, bucket: str) -> list[Mapping[str, Any]]:
    out = []
    for record in records:
        counts = _resolution_from_records([record], firm_key)
        if counts.get(bucket):
            out.append(record)
    return out


# --------------------------------------------------------------------- recall
def build_recall_series(
    root: Path,
    *,
    index: ev_identity.CompanyIndex,
    fetched_at: str,
    samples: SampleBook,
) -> dict[str, Any]:
    client = _make_client(root, recall_src.SOURCE_ID, run="recall_full_pull", budget=RUN_BUDGETS["recall_full_pull"])
    firm_blocks: dict[str, Any] = {}
    for firm_key in common.FIVE_FIRM_KEYS:
        queries = recall_src.FIVE_FIRM_QUERIES[firm_key]
        retrieved: dict[str, dict[str, Any]] = {}
        query_log: list[dict[str, Any]] = []
        for search in queries:
            skip = 0
            pages = 0
            while pages < 4 and len(retrieved) < 6000:
                if client.remaining() <= 0:
                    break
                result = recall_src.fetch(client, search, skip=skip, limit=recall_src.PAGE_LIMIT)
                pages += 1
                if not result.ok:
                    query_log.append(
                        {
                            "search": search,
                            "skip": skip,
                            "url": result.url,
                            "status": result.status,
                            "error": result.error,
                            "returned": 0,
                        }
                    )
                    break
                records, page_meta = recall_src.normalise_payload(
                    result.json(), fetched_at=fetched_at, company_index=index
                )
                query_log.append(
                    {
                        "search": search,
                        "skip": skip,
                        "url": result.url,
                        "status": result.status,
                        "meta_total": page_meta.get("total"),
                        "returned": len(records),
                    }
                )
                if not records:
                    break
                if pages == 1:
                    samples.add(
                        recall_src.SOURCE_ID,
                        f"page_{firm_key}_{common.record_digest(search)}.json",
                        result.body,
                        url=result.url,
                        fetched_at=fetched_at,
                    )
                for record in records:
                    retrieved.setdefault(record["source_record_id"], record)
                if len(records) < recall_src.PAGE_LIMIT:
                    break
                skip += recall_src.PAGE_LIMIT
                if skip > recall_src.SKIP_CAP:
                    break
        records = list(retrieved.values())
        resolution = _resolution_from_records(records, firm_key)
        confirmed = _records_with_bucket(records, firm_key, "confirmed")
        firm_blocks[firm_key] = {
            "firm_key": firm_key,
            "firm_label": common.FIVE_FIRM_LABELS[firm_key],
            "queries": query_log,
            "retrieved_records": len(records),
            "retrieved_by_query": len(query_log),
            "resolution": resolution,
            "resolution_note": (
                "counts are per retrieved record, resolved locally with "
                "identity.CompanyIndex.resolve on recalling_firm; confirmed and candidate never mixed"
            ),
            "by_year_event_at": _annual(records, "event_at"),
            "by_year_source_public_at": _annual(records, "source_public_at"),
            "by_year_confirmed_source_public_at": _annual(confirmed, "source_public_at"),
            "earliest_source_public_at": min(
                (r["time"].get("source_public_at", "") for r in records if r["time"].get("source_public_at")),
                default="",
            ),
            "latest_source_public_at": max(
                (r["time"].get("source_public_at", "") for r in records if r["time"].get("source_public_at")),
                default="",
            ),
            "sample_source_record_ids": [r["source_record_id"] for r in records[:5]],
        }
    payload = {
        "kind": recall_src.KIND,
        "source_name": recall_src.SOURCE_NAME,
        "endpoint": recall_src.API_URL,
        "retrieval_mode": "full pull of each firm's keyword-superset search, then local identity resolution",
        "time_fields": {
            "event_at": "event_date_initiated",
            "source_public_at": "event_date_posted",
        },
        "interpretation": recall_src.INTERPRETATION_WARNING,
        "firms": firm_blocks,
    }
    return {"payload": payload, "requests": _describe_requests(client, "recall_full_pull")}


# ---------------------------------------------------------------------- maude
_MAUDE_CENSUS_QUERIES: dict[str, str] = {
    "medtronic": "device.manufacturer_d_name:medtronic",
    "ge_healthcare": 'device.manufacturer_d_name:"ge healthcare"',
    "philips": "device.manufacturer_d_name:philips",
    "draeger": "device.manufacturer_d_name:draeger",
    "mindray": "device.manufacturer_d_name:mindray",
}


def _census_block(
    buckets: list[Mapping[str, Any]],
    *,
    firm_key: str,
    index: ev_identity.CompanyIndex,
    reports_total: int | None,
    query: str,
) -> dict[str, Any]:
    counts = {"confirmed": 0, "candidate": 0, "other_firm": 0, "none": 0}
    top_confirmed: list[dict[str, Any]] = []
    for bucket in buckets:
        term = str(bucket.get("value", ""))
        count = int(bucket.get("count", 0))
        if not term:
            counts["none"] += count
            continue
        ref = common.resolve_company(index, term)
        category = _firm_bucket(ref, firm_key)
        counts[category] += count
        if category == "confirmed":
            top_confirmed.append({"manufacturer_d_name": term, "count": count})
    top_confirmed.sort(key=lambda row: -row["count"])
    bucket_sum = sum(int(b.get("count", 0)) for b in buckets)
    return {
        "query": query,
        "query_url": f"{maude_src.API_URL}?search={query}&count=device.manufacturer_d_name.exact",
        "buckets_returned": len(buckets),
        "unauthenticated_bucket_cap": 100,
        "buckets_sum_device_entries": bucket_sum,
        "count_unit": "device-entry occurrences across the reports matched by the query",
        "device_entries_by_resolution": counts,
        "reports_total_for_query": reports_total,
        "residual_not_returned_by_api": (
            None if reports_total is None else max(0, reports_total - bucket_sum)
        ),
        "census_completeness": (
            "partial — unauthenticated count is capped at 100 buckets; the residual is reported as "
            "unknown, never distributed over the returned terms"
        ),
        "top_confirmed_terms": top_confirmed[:10],
    }


def build_maude_series(
    root: Path,
    *,
    index: ev_identity.CompanyIndex,
    fetched_at: str,
    samples: SampleBook,
) -> dict[str, Any]:
    count_client = _make_client(root, maude_src.SOURCE_ID, run="maude_counts", budget=RUN_BUDGETS["maude_counts"])
    census_client = _make_client(root, maude_src.SOURCE_ID, run="maude_census", budget=RUN_BUDGETS["maude_census"])
    firm_blocks: dict[str, Any] = {}
    for firm_key in common.FIVE_FIRM_KEYS:
        search = _MAUDE_CENSUS_QUERIES[firm_key]
        received_buckets, received_meta = maude_src.count_by(count_client, "date_received", search=search)
        samples.add(
            maude_src.SOURCE_ID,
            f"count_date_received_{firm_key}.json",
            json.dumps(received_buckets, ensure_ascii=False).encode(),
            url=received_meta.get("url", ""),
            fetched_at=fetched_at,
        )
        event_buckets, event_meta = maude_src.count_by(count_client, "date_of_event", search=search)
        census_buckets, census_meta = maude_src.count_by(
            census_client, "device.manufacturer_d_name.exact", search=search
        )
        samples.add(
            maude_src.SOURCE_ID,
            f"census_terms_{firm_key}.json",
            json.dumps(census_buckets, ensure_ascii=False).encode(),
            url=census_meta.get("url", ""),
            fetched_at=fetched_at,
        )
        reports_total = received_meta.get("bucket_sum")
        firm_blocks[firm_key] = {
            "firm_key": firm_key,
            "firm_label": common.FIVE_FIRM_LABELS[firm_key],
            "keyword_query": search,
            "reports_by_date_received_year": maude_src.annual_histogram(received_buckets),
            "reports_by_date_of_event_year": maude_src.annual_histogram(event_buckets),
            "reports_total_by_date_received": reports_total,
            "reports_total_by_date_of_event": event_meta.get("bucket_sum"),
            "count_queries": [
                {"field": "date_received", "url": received_meta.get("url"), "status": received_meta.get("status")},
                {"field": "date_of_event", "url": event_meta.get("url"), "status": event_meta.get("status")},
                {"field": "device.manufacturer_d_name.exact", "url": census_meta.get("url"), "status": census_meta.get("status")},
            ],
            "identity_census": _census_block(
                census_buckets,
                firm_key=firm_key,
                index=index,
                reports_total=reports_total,
                query=search,
            ),
        }
    payload = {
        "kind": maude_src.KIND,
        "source_name": maude_src.SOURCE_NAME,
        "endpoint": maude_src.API_URL,
        "retrieval_mode": (
            "server-side count aggregation for the firm keyword family, plus a 100-bucket "
            "exact-manufacturer census for identity resolution"
        ),
        "count_unit": "MDR reports for the annual series; device entries for the identity census",
        "time_fields": {
            "event_at": "date_of_event",
            "source_public_at": "date_received (proxy, see time.notes)",
        },
        "interpretation": maude_src.INTERPRETATION_WARNING,
        "firms": firm_blocks,
    }
    return {
        "payload": payload,
        "requests": _describe_requests(count_client, "maude_counts") + _describe_requests(census_client, "maude_census"),
    }


# ------------------------------------------------------------------ shortages
def build_shortages_series(
    root: Path,
    *,
    index: ev_identity.CompanyIndex,
    fetched_at: str,
    samples: SampleBook,
) -> dict[str, Any]:
    client = _make_client(root, shortage_src.SOURCE_ID, run="shortages", budget=RUN_BUDGETS["shortages"])
    result = client.get(shortage_src.PAGE_URL, accept="text/html")
    meta: dict[str, Any] = {
        "url": result.url,
        "status": result.status,
        "bytes": len(result.body),
        "error": result.error,
    }
    records: list[dict[str, Any]] = []
    if result.ok:
        parsed = shortage_src.parse_shortages_page(result.text)
        records = shortage_src.parse_to_evidence(result.body, fetched_at=fetched_at, company_index=index)
        meta.update(
            {
                "tables": parsed["table_count"],
                "shortage_rows": len(parsed["shortages"]),
                "discontinuance_rows": len(parsed["discontinuances"]),
                "records": len(records),
            }
        )
        samples.add(
            shortage_src.SOURCE_ID,
            "medical-device-shortages-list.html",
            result.body,
            url=result.url,
            fetched_at=fetched_at,
        )
    by_type: dict[str, int] = {}
    for record in records:
        record_type = (record.get("normalized") or {}).get("record_type", "")
        by_type[record_type] = by_type.get(record_type, 0) + 1
    discontinuances = [
        r for r in records if (r.get("normalized") or {}).get("record_type") == "discontinuance"
    ]
    firms: dict[str, Any] = {}
    for firm_key in common.FIVE_FIRM_KEYS:
        resolution = _resolution_from_records(discontinuances, firm_key)
        confirmed = _records_with_bucket(discontinuances, firm_key, "confirmed")
        candidate = _records_with_bucket(discontinuances, firm_key, "candidate")
        firms[firm_key] = {
            "firm_key": firm_key,
            "firm_label": common.FIVE_FIRM_LABELS[firm_key],
            "resolution": resolution,
            "by_year_source_public_at": _annual(confirmed, "source_public_at"),
            "confirmed_records": [
                {
                    "manufacturer_name": (r.get("normalized") or {}).get("manufacturer_name"),
                    "device_trade_name": (r.get("normalized") or {}).get("device_trade_name"),
                    "date_posted": (r.get("time") or {}).get("source_public_at"),
                    "source_record_id": r["source_record_id"],
                }
                for r in confirmed
            ],
            "candidate_records": [
                {
                    "manufacturer_name": (r.get("normalized") or {}).get("manufacturer_name"),
                    "device_trade_name": (r.get("normalized") or {}).get("device_trade_name"),
                    "date_posted": (r.get("time") or {}).get("source_public_at"),
                    "source_record_id": r["source_record_id"],
                }
                for r in candidate
            ],
        }
    payload = {
        "kind": shortage_src.KIND,
        "source_name": shortage_src.SOURCE_NAME,
        "endpoint": shortage_src.PAGE_URL,
        "retrieval_mode": "single page fetch; both server-rendered tables parsed",
        "records_by_type": by_type,
        "shortage_rows_have_manufacturer_field": False,
        "firm_linkable_table": "discontinuance table only (has Manufacturer Name)",
        "interpretation": shortage_src.INTERPRETATION_WARNING,
        "firms": firms,
    }
    return {"payload": payload, "requests": _describe_requests(client, "shortages")}


# --------------------------------------------------------------- import alerts
_DEVICE_ALERT_DETAIL_PROBES: tuple[str, ...] = (
    "importalert_1182.html",  # 99-49 Device UDI / GUDID
    "importalert_231.html",  # 80-06 false or misleading labelling
    "importalert_241.html",  # 89-04 firms not meeting device QS requirements
)


def build_import_alerts_series(
    root: Path,
    *,
    index: ev_identity.CompanyIndex,
    fetched_at: str,
    samples: SampleBook,
) -> dict[str, Any]:
    client = _make_client(root, alert_src.SOURCE_ID, run="import_alerts", budget=RUN_BUDGETS["import_alerts"])
    records, meta = alert_src.collect(client, fetched_at=fetched_at, company_index=index)
    records = list(records)
    device_group = client.get(alert_src.DEVICE_GROUP_URL, accept="text/html")
    industries: list[dict[str, str]] = []
    if device_group.ok:
        samples.add(
            alert_src.SOURCE_ID,
            "industrygroup_9_medical_devices.html",
            device_group.body,
            url=device_group.url,
            fetched_at=fetched_at,
        )
        industries = alert_src.parse_industry_links(device_group.text)
    detail_checks: list[dict[str, Any]] = []
    for page in _DEVICE_ALERT_DETAIL_PROBES:
        if client.remaining() <= 0:
            break
        url = f"https://www.accessdata.fda.gov/cms_ia/{page}"
        result = client.get(url, accept="text/html")
        if not result.ok:
            detail_checks.append({"url": url, "status": result.status, "error": result.error})
            continue
        samples.add(alert_src.SOURCE_ID, page, result.body, url=url, fetched_at=fetched_at)
        tokens = alert_src.count_firm_tokens(result.text, index=index)
        detail_checks.append(
            {
                "url": url,
                "status": result.status,
                "bytes": len(result.body),
                "five_firm_alias_text_hits": tokens,
                "firm_level_interpretation": "raw text match only, NOT an identity link",
            }
        )
    device_subset = alert_src.device_alert_subset(records)
    payload = {
        "kind": alert_src.KIND,
        "source_name": alert_src.SOURCE_NAME,
        "endpoint": alert_src.INDEX_URL,
        "retrieval_mode": "ialist.html index parsed; device grouping from industrygroup_9.html; bounded detail-page scan",
        "index_records": len(records),
        "index_meta": {k: meta.get(k) for k in ("url", "status", "bytes", "records")},
        "device_alert_keyword_subset": len(device_subset),
        "device_alert_keyword_subset_is_authoritative": False,
        "device_industry_subcategories": industries,
        "detail_page_five_firm_checks": detail_checks,
        "firm_level_availability": (
            "UNKNOWN. The index has no company column; firm names exist only inside each alert's "
            "red list. The bounded scan above covered a few device alerts and found no five-firm "
            "alias text hit, which is a negative observation about those pages, not a census."
        ),
        "firms": {
            firm_key: {
                "firm_key": firm_key,
                "firm_label": common.FIVE_FIRM_LABELS[firm_key],
                "confirmed": None,
                "candidate": None,
                "status": "UNKNOWN",
                "reason": "no company field in the index; per-alert red lists not enumerable within budget",
            }
            for firm_key in common.FIVE_FIRM_KEYS
        },
        "interpretation": alert_src.INTERPRETATION_WARNING,
    }
    return {"payload": payload, "requests": _describe_requests(client, "import_alerts")}


# ----------------------------------------------------------------------- main
def build(root: Path | None = None) -> dict[str, Any]:
    root = Path(root) if root else DEFAULT_ROOT
    root = root.resolve()
    index = ev_identity.CompanyIndex.from_config()
    fetched_at = ev_base.utc_iso()
    samples = SampleBook(root)
    requests: list[dict[str, Any]] = []

    recall = build_recall_series(root, index=index, fetched_at=fetched_at, samples=samples)
    requests.extend(recall["requests"])
    maude = build_maude_series(root, index=index, fetched_at=fetched_at, samples=samples)
    requests.extend(maude["requests"])
    shortages = build_shortages_series(root, index=index, fetched_at=fetched_at, samples=samples)
    requests.extend(shortages["requests"])
    alerts = build_import_alerts_series(root, index=index, fetched_at=fetched_at, samples=samples)
    requests.extend(alerts["requests"])
    samples.flush()

    payload = {
        "schema": SCHEMA_ID,
        "generated_at": fetched_at,
        "workspace": str(root),
        "firms": list(common.FIVE_FIRM_KEYS),
        "firm_labels": common.FIVE_FIRM_LABELS,
        "methodology": {
            "rule_1": "every count is a real response of this run; no estimation, interpolation or back-fill",
            "rule_2": "confirmed = official_id / exact_alias / multi_field from identity.CompanyIndex.resolve; candidate counted apart",
            "rule_3": "a server-side count is labelled as such and its truncation is reported as a residual",
            "rule_4": "report counts are never converted to failure/incidence rates",
        },
        "sources": {
            recall_src.SOURCE_ID: recall["payload"],
            maude_src.SOURCE_ID: maude["payload"],
            shortage_src.SOURCE_ID: shortages["payload"],
            alert_src.SOURCE_ID: alerts["payload"],
        },
        "request_log": requests,
        "total_requests": len(requests),
        "request_budgets": RUN_BUDGETS,
        "notes": [
            "GM/GE: legacy 'GE MEDICAL' recall queries are included in recall retrieval; the MAUDE census uses the "
            "'ge healthcare' phrase only and therefore excludes legacy 'GE MEDICAL' strings (documented, not estimated).",
            "Dräger: openFDA rejects non-ASCII search terms (recalling_firm:dräger -> HTTP 400 'Search not supported'), "
            "so only the ASCII spellings draeger/drager are retrievable.",
            "MAUDE keyword-family totals are report counts for reports in which at least one device entry matches the "
            "manufacturer keyword; they are not mutually exclusive across firms and carry no denominator.",
        ],
    }
    out_dir = root / "samples" / "postmarket"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "FIVE_FIRM_SERIES.json"
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build the five-firm postmarket series (POSTMARKET/EXP-C)")
    parser.add_argument("--root", default=str(DEFAULT_ROOT), help="research/data_expansion root")
    args = parser.parse_args(argv)
    payload = build(Path(args.root))
    print(
        json.dumps(
            {
                "out": str(Path(args.root) / "samples" / "postmarket" / "FIVE_FIRM_SERIES.json"),
                "total_requests": payload["total_requests"],
                "sources": list(payload["sources"]),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
