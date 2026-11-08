"""openFDA device adverse events (MAUDE) — connector for ``openfda_device_maude``.

API (probed live 2026-11-09)
---------------------------
``GET https://api.fda.gov/device/event.json``

* MAUDE = Manufacturer and User Facility Device Experience; the FDA collects
  mandatory (manufacturer / importer / user-facility) and voluntary reports.
* ``device.manufacturer_d_name`` lives inside the ``device`` array; a nested
  search must use the dot path (``device.manufacturer_d_name:...``).  The
  top-level ``manufacturer_name`` field is empty for most historical records and
  must not be used for identity.
* ``device.manufacturer_d_name.exact`` is the aggregatable exact-value subfield;
  unauthenticated ``count`` requests are capped at 100 buckets (asking for more
  returns ``API_KEY_MISSING``, verified live).

Time semantics — the three MAUDE dates are *different facts*
-------------------------------------------------------------
``date_of_event``      when the event happened            -> ``event_at``
``date_received``      when FDA received the report       -> ``source_public_at``
``date_report``        when the reporter sent the report
``date_report_to_fda`` when the report reached FDA
``date_added``         when the record entered the database

Only ``date_received`` is used for ``source_public_at`` because the task
contract allows it as a public-visibility proxy; the field is *not* the same
thing as publication and each record says so in ``time.notes``.

Interpretation
--------------
MAUDE is a passive surveillance system.  openFDA's own page states that
"the incidence or prevalence of an event cannot be determined from this
reporting system alone due to potential under-reporting of events and lack of
information about frequency of device use" and that increases in report volume
are "likely caused by improved reporting".  Report counts are therefore never
converted to rates by this package.
"""

from __future__ import annotations

from typing import Any, Iterable, Mapping

from medradar.external_sources import base as ev_base
from medradar.external_sources import identity as ev_identity
from medradar.external_sources import schema as ev_schema
from medradar.external_sources.regulatory import postmarket_common as common

SOURCE_ID = "openfda_device_maude"
SOURCE_NAME = "openFDA device adverse events (MAUDE)"
KIND = "postmarket_event"
LICENCE_STATUS = "public_domain"
API_URL = "https://api.fda.gov/device/event.json"
ATTRIBUTION = "U.S. Food and Drug Administration, openFDA device/event (MAUDE) endpoint (public domain / CC0 1.0)"
PAGE_LIMIT = 1000
SKIP_CAP = 25_000

#: The three MAUDE dates, kept apart on purpose.
EVENT_AT_FIELDS: tuple[str, ...] = ("date_of_event",)
PUBLIC_AT_FIELDS: tuple[str, ...] = ("date_received",)

#: Keyword searches used to retrieve each target firm's family from MAUDE.
FIVE_FIRM_QUERIES: dict[str, tuple[str, ...]] = {
    "medtronic": ("device.manufacturer_d_name:medtronic",),
    "ge_healthcare": ('device.manufacturer_d_name:"ge healthcare"',),
    "philips": ("device.manufacturer_d_name:philips",),
    "draeger": ("device.manufacturer_d_name:draeger",),
    "mindray": ("device.manufacturer_d_name:mindray",),
}

INTERPRETATION_WARNING = (
    common.PASSIVE_SURVEILLANCE_WARNING
    + " MAUDE only contains reports that someone chose to submit; it has no "
    "denominator of devices in use, and openFDA states that incidence cannot be "
    "determined from it."
)


def source_record_id(record: Mapping[str, Any]) -> str:
    for field in ("mdr_report_key", "report_number"):
        value = record.get(field)
        if value not in (None, ""):
            return str(value).strip()
    return ""


def identifiers_for(record: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Record-level identifier only.

    MAUDE has no per-report authoritative device identifier, and
    ``pma_pmn_number`` may be a PMA *or* a 510(k) number, so it stays in
    ``normalized`` instead of being promoted (which would also outrank the
    report accession in ``schema.canonical_key``).
    """
    report_number = record.get("report_number") or record.get("mdr_report_key")
    ident = ev_identity.build_identifier("accession", report_number, is_primary=True)
    return [ident] if ident else []


def _device_rows(record: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    return [row for row in common.as_list(record.get("device")) if isinstance(row, Mapping)]


def to_evidence(
    raw_item: Mapping[str, Any],
    *,
    fetched_at: str,
    company_index: ev_identity.CompanyIndex | None = None,
) -> dict[str, Any] | None:
    """One MAUDE report -> one schema-v1 evidence record (one report = one record)."""
    rec_id = source_record_id(raw_item)
    if not rec_id:
        return None

    devices = _device_rows(raw_item)
    manufacturer_names: list[str] = []
    brand_names: list[str] = []
    generic_names: list[str] = []
    product_codes: list[str] = []
    model_numbers: list[str] = []
    for device in devices:
        for target, field, limit in (
            (manufacturer_names, "manufacturer_d_name", 200),
            (brand_names, "brand_name", 300),
            (generic_names, "generic_name", 300),
            (product_codes, "device_report_product_code", 40),
            (model_numbers, "model_number", 120),
        ):
            value = common.clip(device.get(field), limit)
            if value and value.upper() not in {"N/A", "NA", "UNKNOWN", "SAME AS ABOVE"}:
                if value not in target:
                    target.append(value)

    resolver = company_index or ev_identity.CompanyIndex.from_config()
    entity_refs = [
        common.resolve_company(resolver, name, country=common.clip(raw_item.get("manufacturer_country"), 80))
        for name in manufacturer_names[:8]
    ]

    event_date = raw_item.get("date_of_event")
    received = raw_item.get("date_received")
    normalized = {
        "record_type": "mdr",
        "mdr_report_key": common.clip(raw_item.get("mdr_report_key"), 40),
        "report_number": common.clip(raw_item.get("report_number"), 80),
        "event_type": common.clip(raw_item.get("event_type"), 60),
        "report_source_code": common.clip(raw_item.get("report_source_code"), 80),
        "mfr_report_type": common.clip(raw_item.get("mfr_report_type"), 60),
        "manufacturer_name_top_level": common.clip(raw_item.get("manufacturer_name"), 300),
        "manufacturer_country": common.clip(raw_item.get("manufacturer_country"), 80),
        "device_manufacturer_names": manufacturer_names,
        "device_brand_names": brand_names,
        "device_generic_names": generic_names,
        "device_product_codes": product_codes,
        "device_model_numbers": model_numbers,
        "number_devices_in_event": raw_item.get("number_devices_in_event"),
        "number_patients_in_event": raw_item.get("number_patients_in_event"),
        "product_problem_flag": common.clip(raw_item.get("product_problem_flag"), 8),
        "date_of_event": common.clip(event_date, 40),
        "date_received": common.clip(received, 40),
        "date_report": common.clip(raw_item.get("date_report"), 40),
        "date_report_to_fda": common.clip(raw_item.get("date_report_to_fda"), 40),
        "date_facility_aware": common.clip(raw_item.get("date_facility_aware"), 40),
        "date_added": common.clip(raw_item.get("date_added"), 40),
        "date_changed": common.clip(raw_item.get("date_changed"), 40),
        "interpretation_warning": INTERPRETATION_WARNING,
    }
    time_block = common.clock_block(
        event_at=event_date,
        source_public_at=received,
        fetched_at=fetched_at,
        notes=(
            "event_at=date_of_event (when the event happened); "
            "source_public_at=date_received (when FDA received the report) — used as a "
            "public-visibility proxy per the DATA-EXPANSION-001 contract, NOT as a "
            "verified publication timestamp. date_report/date_report_to_fda/date_added "
            "are different facts and are kept in normalized only."
        ),
    )
    source_url = (
        "https://www.accessdata.fda.gov/scripts/cdrh/cfdocs/cfmaude/detail.cfm?mdrfoi__id="
        f"{raw_item.get('mdr_report_key')}"
        if raw_item.get("mdr_report_key")
        else "https://www.accessdata.fda.gov/scripts/cdrh/cfdocs/cfmaude/search.cfm"
    )
    return common.make_postmarket_evidence(
        source_id=SOURCE_ID,
        kind=KIND,
        source_record_id=rec_id,
        source_url=source_url,
        normalized=normalized,
        raw=common.raw_block_from_object(raw_item, path=f"openfda:device/event#{rec_id}"),
        time=time_block,
        identifiers=identifiers_for(raw_item),
        entity_refs=entity_refs,
        source_name=SOURCE_NAME,
        licence_status=LICENCE_STATUS,
        attribution=ATTRIBUTION,
        fetched_at=fetched_at,
    )


def page_params(search: str, *, skip: int = 0, limit: int = PAGE_LIMIT) -> dict[str, Any]:
    if skip < 0 or skip > SKIP_CAP:
        raise ValueError(f"skip {skip} outside openFDA's documented cap 0..{SKIP_CAP}")
    params: dict[str, Any] = {"limit": min(limit, PAGE_LIMIT), "skip": skip}
    if search:
        params["search"] = search
    return params


def fetch(
    client: Any,
    search: str,
    *,
    skip: int = 0,
    limit: int = PAGE_LIMIT,
) -> Any:
    """One bounded GET of a result page (returns the raw ``HttpResult``)."""
    return client.get(API_URL, params=page_params(search, skip=skip, limit=limit))


def normalise_payload(
    payload: Mapping[str, Any],
    *,
    fetched_at: str,
    company_index: ev_identity.CompanyIndex | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    rows = payload.get("results") or []
    payload_meta = payload.get("meta") or {}
    meta: dict[str, Any] = {
        "total": (payload_meta.get("results") or {}).get("total"),
        "last_updated": payload_meta.get("last_updated"),
    }
    records: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        evidence = to_evidence(row, fetched_at=fetched_at, company_index=company_index)
        if evidence is not None:
            records.append(evidence)
    meta["records"] = len(records)
    return records, meta


def collect_page(
    client: Any,
    search: str,
    *,
    skip: int = 0,
    limit: int = PAGE_LIMIT,
    fetched_at: str,
    company_index: ev_identity.CompanyIndex | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Fetch one MAUDE page and normalise it.  Returns ``(records, meta)``."""
    result = fetch(client, search, skip=skip, limit=limit)
    meta: dict[str, Any] = {"url": result.url, "status": result.status, "bytes": len(result.body), "error": result.error}
    if not result.ok:
        return [], meta
    records, page_meta = normalise_payload(result.json(), fetched_at=fetched_at, company_index=company_index)
    meta.update(page_meta)
    return records, meta


def collect(
    client: Any,
    *,
    limit: int = 50,
    search: str = "",
    max_pages: int = 1,
    fetched_at: str = "",
    company_index: ev_identity.CompanyIndex | None = None,
) -> list[dict[str, Any]]:
    """Retrieve ≤ ``limit`` real MAUDE reports across ≤ ``max_pages`` pages."""
    fetched = fetched_at or ev_base.utc_iso()
    if limit <= 0 or max_pages <= 0:
        return []
    out: list[dict[str, Any]] = []
    skip = 0
    for _ in range(max_pages):
        page_size = min(PAGE_LIMIT, limit - len(out))
        if page_size <= 0:
            break
        records, _meta = collect_page(
            client,
            search,
            skip=skip,
            limit=page_size,
            fetched_at=fetched,
            company_index=company_index,
        )
        out.extend(records)
        if len(records) < page_size:
            break
        skip += page_size
        if skip > SKIP_CAP:
            break
    return out[:limit]


def count_by(
    client: Any,
    field: str,
    *,
    search: str = "",
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Server-side ``count`` aggregation (real returned buckets, never estimates).

    ``field`` must be an aggregatable field: a date field such as
    ``date_received`` or the ``.exact`` subfield of a keyword field.  The API caps
    unauthenticated ``count`` responses at 100 buckets for keyword fields and
    returns every date bucket.
    """
    params: dict[str, Any] = {"count": field}
    if search:
        params["search"] = search
    result = client.get(API_URL, params=params)
    meta: dict[str, Any] = {"url": result.url, "status": result.status, "bytes": len(result.body), "error": result.error}
    if not result.ok:
        return [], meta
    payload = result.json()
    buckets = [
        {"value": str(bucket.get("term", bucket.get("time", ""))), "count": int(bucket.get("count", 0))}
        for bucket in (payload.get("results") or [])
        if isinstance(bucket, Mapping)
    ]
    meta["buckets"] = len(buckets)
    meta["bucket_sum"] = sum(bucket["count"] for bucket in buckets)
    return buckets, meta


def annual_histogram(buckets: Iterable[Mapping[str, Any]]) -> dict[str, int]:
    """Aggregate day-buckets into ``{YYYY: count}`` using the bucket date itself."""
    histogram: dict[str, int] = {}
    for bucket in buckets:
        year = common.year_of(bucket.get("value"))
        if not year:
            continue
        histogram[year] = histogram.get(year, 0) + int(bucket.get("count", 0))
    return dict(sorted(histogram.items()))


__all__ = [
    "API_URL",
    "EVENT_AT_FIELDS",
    "FIVE_FIRM_QUERIES",
    "INTERPRETATION_WARNING",
    "KIND",
    "LICENCE_STATUS",
    "PUBLIC_AT_FIELDS",
    "SOURCE_ID",
    "SOURCE_NAME",
    "annual_histogram",
    "collect",
    "collect_page",
    "count_by",
    "fetch",
    "identifiers_for",
    "normalise_payload",
    "page_params",
    "source_record_id",
    "to_evidence",
]
