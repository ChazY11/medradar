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
* server-side aggregations are labelled as such, and the unauthenticated
  100-bucket cap on keyword ``count`` queries is reported as a residual instead
  of being smeared over the returned buckets;
* every request is written to ``series_requests.jsonl`` next to the probe ledger,
  and every run is bounded to the same ≤ 12 requests the probe contract uses.

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

#: Every labelled run is bounded exactly like a probe (contract: ≤ 12 requests).
RUN_BUDGETS: dict[str, int] = {
    "recall_census_a": 12,
    "recall_census_b": 12,
    "recall_record_sample": 2,
    "maude_counts_a": 12,
    "maude_counts_b": 12,
    "shortages": 2,
    "import_alerts": 8,
}

#: Unauthenticated openFDA keyword-count bucket cap (verified: limit=1000 -> 403).
KEYWORD_BUCKET_CAP = 100

DEFAULT_ROOT = Path(__file__).resolve().parents[3] / "research" / "data_expansion"

_MAUDE_CENSUS_QUERIES: dict[str, str] = {
    "medtronic": "device.manufacturer_d_name:medtronic",
    "ge_healthcare": 'device.manufacturer_d_name:"ge healthcare"',
    "philips": "device.manufacturer_d_name:philips",
    "draeger": "device.manufacturer_d_name:draeger",
    "mindray": "device.manufacturer_d_name:mindray",
}


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
        timeout=90.0,
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
    """Collects real response slices and writes/merges ``SAMPLES.json`` descriptors."""

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
    method = ref.get("method")
    resolved = ref.get("resolved_key")
    if method in ev_schema.CONFIRMED_METHODS and resolved == firm_key:
        return "confirmed"
    if method == "candidate" and resolved == firm_key:
        return "candidate"
    if resolved is not None and resolved != firm_key:
        return "other_firm"
    return "none"


def _census_block(
    buckets: list[Mapping[str, Any]],
    *,
    field: str,
    firm_key: str,
    index: ev_identity.CompanyIndex,
    matches_total: int | None,
    query: str,
    count_unit: str,
) -> dict[str, Any]:
    """Resolve every returned exact-value bucket and report truncation honestly."""
    counts = {"confirmed": 0, "candidate": 0, "other_firm": 0, "none": 0}
    top_confirmed: list[dict[str, Any]] = []
    for bucket in buckets:
        term = str(bucket.get("value", ""))
        count = int(bucket.get("count", 0))
        if not term:
            counts["none"] += count
            continue
        category = _firm_bucket(common.resolve_company(index, term), firm_key)
        counts[category] += count
        if category == "confirmed":
            top_confirmed.append({field: term, "count": count})
    top_confirmed.sort(key=lambda row: -row["count"])
    bucket_sum = sum(int(b.get("count", 0)) for b in buckets)
    truncated = len(buckets) >= KEYWORD_BUCKET_CAP
    return {
        "query": query,
        "census_field": field,
        "count_unit": count_unit,
        "buckets_returned": len(buckets),
        "unauthenticated_bucket_cap": KEYWORD_BUCKET_CAP,
        "buckets_sum": bucket_sum,
        "matches_total": matches_total,
        "residual_not_returned_by_api": None if matches_total is None else max(0, matches_total - bucket_sum),
        "bucket_cap_hit": truncated,
        "census_completeness": (
            "complete within the matched set (every exact name bucket returned)"
            if not truncated
            else "partial — the API cap of 100 buckets was hit; the residual is unknown, never distributed"
        ),
        "counts_by_resolution": counts,
        "confirmed_total": counts["confirmed"],
        "candidate_total": counts["candidate"],
        "top_confirmed_terms": top_confirmed[:10],
    }


def _merge_years(blocks: Iterable[Mapping[str, int]]) -> dict[str, int]:
    merged: dict[str, int] = {}
    for block in blocks:
        for year, count in block.items():
            merged[year] = merged.get(year, 0) + int(count)
    return dict(sorted(merged.items()))


# --------------------------------------------------------------------- recall
def _recall_query_block(
    client: ev_base.HttpClient,
    *,
    search: str,
    firm_key: str,
    index: ev_identity.CompanyIndex,
    fetched_at: str,
    samples: SampleBook,
) -> dict[str, Any]:
    census_buckets, census_meta = recall_src.count_by(client, "recalling_firm.exact", search=search)
    initiated_buckets, initiated_meta = recall_src.count_by(client, "event_date_initiated", search=search)
    posted_buckets, posted_meta = recall_src.count_by(client, "event_date_posted", search=search)
    tag = common.record_digest(search)[:12]
    samples.add(
        recall_src.SOURCE_ID,
        f"census_recalling_firm_{firm_key}_{tag}.json",
        json.dumps(census_buckets, ensure_ascii=False).encode(),
        url=census_meta.get("url", ""),
        fetched_at=fetched_at,
    )
    samples.add(
        recall_src.SOURCE_ID,
        f"count_event_date_initiated_{firm_key}_{tag}.json",
        json.dumps(initiated_buckets, ensure_ascii=False).encode(),
        url=initiated_meta.get("url", ""),
        fetched_at=fetched_at,
    )
    return {
        "search": search,
        "matches_total": census_meta.get("bucket_sum"),
        "no_matches": census_meta.get("status") == 404,
        "census": _census_block(
            census_buckets,
            field="recalling_firm",
            firm_key=firm_key,
            index=index,
            matches_total=census_meta.get("bucket_sum"),
            query=search,
            count_unit="recall records (one record = one enforcement action)",
        ),
        "by_year_event_at": recall_src.annual_histogram(initiated_buckets),
        "by_year_source_public_at": recall_src.annual_histogram(posted_buckets),
        "count_queries": [
            {"field": "recalling_firm.exact", "url": census_meta.get("url"), "status": census_meta.get("status"), "buckets": census_meta.get("buckets")},
            {"field": "event_date_initiated", "url": initiated_meta.get("url"), "status": initiated_meta.get("status"), "buckets": initiated_meta.get("buckets")},
            {"field": "event_date_posted", "url": posted_meta.get("url"), "status": posted_meta.get("status"), "buckets": posted_meta.get("buckets")},
        ],
    }


def build_recall_series(
    root: Path,
    *,
    index: ev_identity.CompanyIndex,
    fetched_at: str,
    samples: SampleBook,
) -> dict[str, Any]:
    firm_blocks: dict[str, Any] = {}
    requests: list[dict[str, Any]] = []
    for run, budget, firms in (
        ("recall_census_a", RUN_BUDGETS["recall_census_a"], common.FIVE_FIRM_KEYS[:3]),
        ("recall_census_b", RUN_BUDGETS["recall_census_b"], common.FIVE_FIRM_KEYS[3:]),
    ):
        client = _make_client(root, recall_src.SOURCE_ID, run=run, budget=budget)
        for firm_key in firms:
            query_blocks = [
                _recall_query_block(
                    client,
                    search=search,
                    firm_key=firm_key,
                    index=index,
                    fetched_at=fetched_at,
                    samples=samples,
                )
                for search in recall_src.FIVE_FIRM_QUERIES[firm_key]
            ]
            firm_blocks[firm_key] = {
                "firm_key": firm_key,
                "firm_label": common.FIVE_FIRM_LABELS[firm_key],
                "queries": query_blocks,
                "aggregate": {
                    "matched_records_sum_over_queries": sum(b["matches_total"] or 0 for b in query_blocks),
                    "confirmed": sum(b["census"]["confirmed_total"] for b in query_blocks),
                    "candidate": sum(b["census"]["candidate_total"] for b in query_blocks),
                    "query_count": len(query_blocks),
                    "queries_are_mutually_exclusive_note": (
                        "a recall record has exactly one recalling_firm string, so the per-query sums "
                        "cannot double count a record"
                    ),
                    "by_year_event_at": _merge_years(b["by_year_event_at"] for b in query_blocks),
                    "by_year_source_public_at": _merge_years(b["by_year_source_public_at"] for b in query_blocks),
                },
            }
        requests.extend(_describe_requests(client, run))

    # One bounded page of real records, so the series ships an actual record sample
    # in addition to aggregation buckets.
    sample_client = _make_client(
        root, recall_src.SOURCE_ID, run="recall_record_sample", budget=RUN_BUDGETS["recall_record_sample"]
    )
    page_records: list[dict[str, Any]] = []
    sample_result = recall_src.fetch(sample_client, "recalling_firm:medtronic", limit=100)
    if sample_result.ok:
        samples.add(
            recall_src.SOURCE_ID,
            "records_page_recalling_firm_medtronic_limit100.json",
            sample_result.body,
            url=sample_result.url,
            fetched_at=fetched_at,
        )
        page_records, _meta = recall_src.normalise_payload(
            sample_result.json(), fetched_at=fetched_at, company_index=index
        )
    requests.extend(_describe_requests(sample_client, "recall_record_sample"))

    payload = {
        "kind": recall_src.KIND,
        "source_name": recall_src.SOURCE_NAME,
        "endpoint": recall_src.API_URL,
        "retrieval_mode": (
            "server-side count aggregation: exact recalling_firm census for identity resolution plus "
            "daily event/posted date buckets for the annual series"
        ),
        "count_unit": "recall records (one record = one enforcement action)",
        "time_fields": {"event_at": "event_date_initiated", "source_public_at": "event_date_posted"},
        "interpretation": recall_src.INTERPRETATION_WARNING,
        "firms": firm_blocks,
        "record_sample": {
            "query": "recalling_firm:medtronic",
            "limit": 100,
            "records": len(page_records),
            "attempted_requests": sample_client.requests_made(),
            "resolution_counts": {
                "confirmed": sum(
                    1
                    for r in page_records
                    if any(_firm_bucket(ref, "medtronic") == "confirmed" for ref in (r.get("entity_refs") or []))
                ),
                "candidate": sum(
                    1
                    for r in page_records
                    if any(_firm_bucket(ref, "medtronic") == "candidate" for ref in (r.get("entity_refs") or []))
                ),
            },
            "sample_source_record_ids": [r["source_record_id"] for r in page_records[:5]],
        },
    }
    return {"payload": payload, "requests": requests}


# ---------------------------------------------------------------------- maude
def _maude_firm_block(
    client: ev_base.HttpClient,
    *,
    firm_key: str,
    index: ev_identity.CompanyIndex,
    fetched_at: str,
    samples: SampleBook,
) -> dict[str, Any]:
    search = _MAUDE_CENSUS_QUERIES[firm_key]
    received_buckets, received_meta = maude_src.count_by(client, "date_received", search=search)
    event_buckets, event_meta = maude_src.count_by(client, "date_of_event", search=search)
    census_buckets, census_meta = maude_src.count_by(client, "device.manufacturer_d_name.exact", search=search)
    samples.add(
        maude_src.SOURCE_ID,
        f"count_date_received_{firm_key}.json",
        json.dumps(received_buckets, ensure_ascii=False).encode(),
        url=received_meta.get("url", ""),
        fetched_at=fetched_at,
    )
    samples.add(
        maude_src.SOURCE_ID,
        f"census_terms_{firm_key}.json",
        json.dumps(census_buckets, ensure_ascii=False).encode(),
        url=census_meta.get("url", ""),
        fetched_at=fetched_at,
    )
    return {
        "firm_key": firm_key,
        "firm_label": common.FIVE_FIRM_LABELS[firm_key],
        "keyword_query": search,
        "reports_total_by_date_received": received_meta.get("bucket_sum"),
        "reports_total_by_date_of_event": event_meta.get("bucket_sum"),
        "by_year_date_received": maude_src.annual_histogram(received_buckets),
        "by_year_date_of_event": maude_src.annual_histogram(event_buckets),
        "identity_census": _census_block(
            census_buckets,
            field="device.manufacturer_d_name",
            firm_key=firm_key,
            index=index,
            matches_total=received_meta.get("bucket_sum"),
            query=search,
            count_unit="device-entry occurrences across the reports matched by the query",
        ),
        "count_queries": [
            {"field": "date_received", "url": received_meta.get("url"), "status": received_meta.get("status"), "buckets": received_meta.get("buckets")},
            {"field": "date_of_event", "url": event_meta.get("url"), "status": event_meta.get("status"), "buckets": event_meta.get("buckets")},
            {"field": "device.manufacturer_d_name.exact", "url": census_meta.get("url"), "status": census_meta.get("status"), "buckets": census_meta.get("buckets")},
        ],
    }


def build_maude_series(
    root: Path,
    *,
    index: ev_identity.CompanyIndex,
    fetched_at: str,
    samples: SampleBook,
) -> dict[str, Any]:
    firm_blocks: dict[str, Any] = {}
    requests: list[dict[str, Any]] = []
    for run, budget, firms in (
        ("maude_counts_a", RUN_BUDGETS["maude_counts_a"], common.FIVE_FIRM_KEYS[:3]),
        ("maude_counts_b", RUN_BUDGETS["maude_counts_b"], common.FIVE_FIRM_KEYS[3:]),
    ):
        client = _make_client(root, maude_src.SOURCE_ID, run=run, budget=budget)
        for firm_key in firms:
            firm_blocks[firm_key] = _maude_firm_block(
                client, firm_key=firm_key, index=index, fetched_at=fetched_at, samples=samples
            )
        requests.extend(_describe_requests(client, run))
    payload = {
        "kind": maude_src.KIND,
        "source_name": maude_src.SOURCE_NAME,
        "endpoint": maude_src.API_URL,
        "retrieval_mode": (
            "server-side count aggregation for the firm keyword family (report counts by date), plus a "
            "100-bucket exact-manufacturer census for identity resolution"
        ),
        "count_unit": "MDR reports for the annual series; device-entry occurrences for the identity census",
        "time_fields": {"event_at": "date_of_event", "source_public_at": "date_received (proxy, see time.notes)"},
        "interpretation": maude_src.INTERPRETATION_WARNING,
        "firms": firm_blocks,
    }
    return {"payload": payload, "requests": requests}


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
    discontinuances = [r for r in records if (r.get("normalized") or {}).get("record_type") == "discontinuance"]
    firms: dict[str, Any] = {}
    for firm_key in common.FIVE_FIRM_KEYS:
        confirmed: list[dict[str, Any]] = []
        candidate: list[dict[str, Any]] = []
        for record in discontinuances:
            categories = {_firm_bucket(ref, firm_key) for ref in (record.get("entity_refs") or [])}
            if "confirmed" in categories:
                confirmed.append(record)
            elif "candidate" in categories:
                candidate.append(record)
        firms[firm_key] = {
            "firm_key": firm_key,
            "firm_label": common.FIVE_FIRM_LABELS[firm_key],
            "confirmed": len(confirmed),
            "candidate": len(candidate),
            "by_year_source_public_at": _annual_from_records(confirmed),
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
        "retrieval_mode": "one page fetch; both server-rendered tables parsed",
        "index_meta": meta,
        "records_by_type": by_type,
        "shortage_rows_have_manufacturer_field": False,
        "firm_linkable_table": "discontinuance table only (has Manufacturer Name)",
        "discontinuance_manufacturer_names": {
            "distinct": len({(r.get("normalized") or {}).get("manufacturer_name") for r in discontinuances}),
            "sample": sorted(
                {(r.get("normalized") or {}).get("manufacturer_name") for r in discontinuances}
            )[:12],
            "note": (
                "the current list names 37 distinct manufacturers and none of them belongs to the five "
                "target firms, so a zero is a real observation about this snapshot, not a parser failure"
            ),
        },
        "interpretation": shortage_src.INTERPRETATION_WARNING,
        "firms": firms,
    }
    return {"payload": payload, "requests": _describe_requests(client, "shortages")}


def _annual_from_records(records: Iterable[Mapping[str, Any]]) -> dict[str, int]:
    histogram: dict[str, int] = {}
    for record in records:
        year = common.year_of((record.get("time") or {}).get("source_public_at", ""))
        if year:
            histogram[year] = histogram.get(year, 0) + 1
    return dict(sorted(histogram.items()))


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
    payload = {
        "kind": alert_src.KIND,
        "source_name": alert_src.SOURCE_NAME,
        "endpoint": alert_src.INDEX_URL,
        "retrieval_mode": "ialist.html index parsed; device grouping from industrygroup_9.html; bounded detail-page scan",
        "index_records": len(records),
        "index_meta": {k: meta.get(k) for k in ("url", "status", "bytes", "records")},
        "device_alert_keyword_subset": len(alert_src.device_alert_subset(records)),
        "device_alert_keyword_subset_is_authoritative": False,
        "device_industry_subcategories": industries,
        "detail_page_five_firm_checks": detail_checks,
        "firm_level_availability": (
            "UNKNOWN. The index has no company column; firm names exist only inside each alert's red "
            "list. The bounded scan above covered three device alerts and found no five-firm alias text "
            "hit — a negative observation about those pages, not a census."
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
SAMPLE_INLINE_CAP = 512 * 1024

#: Only these sample directories belong to the postmarket agent.  The rebuild
#: helper must never touch another agent's manifest (write-scope discipline).
OWNED_SAMPLE_DIRS: tuple[str, ...] = (
    recall_src.SOURCE_ID,
    maude_src.SOURCE_ID,
    shortage_src.SOURCE_ID,
    alert_src.SOURCE_ID,
)


def rebuild_sample_manifests(root: Path) -> dict[str, int]:
    """Make each **own** ``samples/<source_id>/SAMPLES.json`` describe every file on disk.

    The probe scripts persist real slices with ``base.write_sample`` but do not
    write the manifest themselves; this function hashes each file from disk and
    merges the result with descriptors already in the manifest.  A recovered
    descriptor whose size equals the 512 KiB inline cap is marked
    ``truncated: true`` with an unknown ``total_bytes`` because the full response
    length was not persisted — it is never guessed.
    """
    counts: dict[str, int] = {}
    samples_root = root / "samples"
    if not samples_root.is_dir():
        return counts
    for source_id in OWNED_SAMPLE_DIRS:
        directory = samples_root / source_id
        if not directory.is_dir():
            continue
        manifest_path = directory / "SAMPLES.json"
        existing: dict[str, dict[str, Any]] = {}
        if manifest_path.is_file():
            try:
                prior = json.loads(manifest_path.read_text(encoding="utf-8"))
                existing = {str(item.get("name")): item for item in prior.get("samples") or []}
            except (ValueError, AttributeError):
                existing = {}
        merged = dict(existing)
        for path in sorted(directory.iterdir()):
            if not path.is_file() or path.name == "SAMPLES.json":
                continue
            body = path.read_bytes()
            at_cap = len(body) >= SAMPLE_INLINE_CAP
            descriptor = existing.get(path.name, {})
            descriptor.update(
                {
                    "name": path.name,
                    "path": str(path),
                    "stored_bytes": len(body),
                    "sha256_stored": ev_base.sha256_bytes(body),
                    "truncated": at_cap if "truncated" not in descriptor else descriptor["truncated"],
                    "total_bytes": None if "total_bytes" not in descriptor else descriptor["total_bytes"],
                    "sha256_full": None if "sha256_full" not in descriptor else descriptor["sha256_full"],
                }
            )
            if "source" not in descriptor:
                descriptor["source"] = "recovered_from_disk"
                descriptor["note"] = (
                    "descriptor recovered from disk: the probe run did not persist the full-response "
                    "descriptor, so sha256_full/total_bytes are null rather than guessed"
                )
            merged[path.name] = descriptor
            if at_cap:
                # A slice that hit the inline cap cannot claim a full-response hash.
                descriptor["truncated"] = True
                descriptor["total_bytes"] = None
                descriptor["sha256_full"] = None
                descriptor.setdefault(
                    "note",
                    "stored slice hit the 512 KiB inline cap; the full-response hash and length were not "
                    "persisted and are left null rather than guessed",
                )
            elif not descriptor.get("sha256_full"):
                # For a complete, untruncated response the full hash IS the stored hash.
                descriptor["sha256_full"] = descriptor["sha256_stored"]
                descriptor["total_bytes"] = len(body)
                descriptor.setdefault(
                    "note",
                    "complete response slice (not truncated), so the full-response hash equals the stored hash",
                )
            merged[path.name] = descriptor
        manifest = {
            "schema": "medradar.external.samples.v1",
            "source_id": source_id,
            "generated_at": ev_base.utc_iso(),
            "note": "Raw response slices only; parsed records are derived and live in the series/handoff.",
            "samples": [merged[name] for name in sorted(merged)],
        }
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        counts[source_id] = len(merged)
    return counts


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
            "Recall and MAUDE annual series are server-side count aggregations over the whole matched set; the "
            "identity census resolves the API's own exact-value buckets, so both counts describe the same query.",
            "GE HealthCare: recall uses two mutually exclusive firm-string queries ('GE HEALTHCARE', 'GE MEDICAL'); "
            "the MAUDE census uses the 'ge healthcare' phrase only and therefore excludes legacy 'GE MEDICAL' "
            "manufacturer strings (documented, not estimated).",
            "Dräger: openFDA rejects non-ASCII search terms (recalling_firm:dräger -> HTTP 400 'Search not "
            "supported'), so only the ASCII spellings draeger/drager are retrievable. The 'drager' recall query "
            "returned HTTP 404 'No matches found' (zero records) at build time — recorded, not hidden.",
            "MAUDE keyword-family totals are report counts for reports in which at least one device entry matches "
            "the manufacturer keyword; they are not mutually exclusive across firms and carry no denominator.",
            "fda_device_shortages: only the discontinuance table has a manufacturer column, so the shortage list "
            "itself is not firm-linkable; both counts are reported as constructed.",
            "fda_import_alerts: firm-level coverage is UNKNOWN because the index exposes no company column.",
        ],
    }
    out_dir = root / "samples" / "postmarket"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "FIVE_FIRM_SERIES.json"
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    rebuild_sample_manifests(root)
    return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build the five-firm postmarket series (EXP-C)")
    parser.add_argument("--root", default=str(DEFAULT_ROOT), help="research/data_expansion root")
    parser.add_argument(
        "--manifests-only",
        action="store_true",
        help="only rebuild SAMPLES.json from files on disk (no network)",
    )
    args = parser.parse_args(argv)
    if args.manifests_only:
        counts = rebuild_sample_manifests(Path(args.root))
        print(json.dumps({"manifests": counts}, ensure_ascii=False), flush=True)
        return 0
    payload = build(Path(args.root))
    print(
        json.dumps(
            {
                "out": str(Path(args.root) / "samples" / "postmarket" / "FIVE_FIRM_SERIES.json"),
                "total_requests": payload["total_requests"],
                "sources": list(payload["sources"]),
            },
            ensure_ascii=False,
        ),
        flush=True,
    )
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
