"""openFDA device recall — connector for the ``openfda_device_recall`` source.

API (probed live 2026-11-09)
---------------------------
``GET https://api.fda.gov/device/recall.json``

* no key required in practice; documented limits are 240 requests/min and
  1,000 requests/day per IP without a key (openFDA authentication docs);
* ``skip`` is capped at 25,000 by the API;
* device recall records expose ``event_date_initiated`` (the date the firm began
  the action) and ``event_date_posted`` (the date FDA posted the record to the
  enforcement report) — *not* the drug-enforcement ``report_date`` field.

Time semantics
--------------
``event_at``          = ``event_date_initiated`` (fallback ``event_date_created``)
``source_public_at``  = ``event_date_posted``
``first_observed_at`` = ``fetched_at`` (a backfill is not an observation history)

Interpretation
--------------
A recall record is one enforcement action.  It is **not** a failure rate and its
count is not comparable across firms without exposure denominators, which this
source does not publish.
"""

from __future__ import annotations

from typing import Any, Iterable, Mapping

from medradar.external_sources import identity as ev_identity
from medradar.external_sources import schema as ev_schema
from medradar.external_sources.regulatory import postmarket_common as common

SOURCE_ID = "openfda_device_recall"
SOURCE_NAME = "openFDA device recall"
KIND = "recall"
LICENCE_STATUS = "public_domain"
API_URL = "https://api.fda.gov/device/recall.json"
ATTRIBUTION = (
    "U.S. Food and Drug Administration, openFDA device recall endpoint "
    "(public domain / CC0 1.0 dedication)"
)
PAGE_LIMIT = 1000
SKIP_CAP = 25_000

#: Ordered candidate fields.  ``event_date_initiated`` is the action start.
EVENT_AT_FIELDS: tuple[str, ...] = ("event_date_initiated", "event_date_created")
#: Ordered candidate fields for the *public* clock.
PUBLIC_AT_FIELDS: tuple[str, ...] = ("event_date_posted",)

#: Field-name fallbacks: device recall uses ``event_date_*`` while the drug
#: enforcement schema uses ``report_date``/``center_classification_date``.
FIELD_ALIASES: dict[str, tuple[str, ...]] = {
    "event_date_initiated": ("event_date_initiated", "report_date", "center_classification_date"),
    "event_date_posted": ("event_date_posted", "report_date"),
    "classification": ("classification", "recall_status"),
    "res_event_number": ("res_event_number", "event_id"),
}

#: Keyword queries used for the five-firm family retrieval.  Each entry is a real
#: openFDA ``search`` expression; retrieval is a *superset* of the firm and the
#: final link is decided locally by ``CompanyIndex.resolve``.
FIVE_FIRM_QUERIES: dict[str, tuple[str, ...]] = {
    "medtronic": ("recalling_firm:medtronic",),
    "ge_healthcare": ('recalling_firm:"ge healthcare"', 'recalling_firm:"ge medical"'),
    "philips": ("recalling_firm:philips",),
    "draeger": ("recalling_firm:draeger", "recalling_firm:drager"),
    "mindray": ("recalling_firm:mindray",),
}

INTERPRETATION_WARNING = (
    common.RECALL_WARNING
    + " A recall count is also not a device reliability metric: FDA seeks publicity "
    "selectively and firms self-report corrective actions."
)


def _first(record: Mapping[str, Any], names: Iterable[str]) -> Any:
    for name in names:
        value = record.get(name)
        if value not in (None, "", [], {}):
            return value
    return None


def source_record_id(record: Mapping[str, Any]) -> str:
    """Stable record identity: ``cfres_id`` then ``product_res_number`` then event no."""
    for field in ("cfres_id", "product_res_number", "res_event_number"):
        value = record.get(field)
        if value not in (None, ""):
            return str(value).strip()
    return ""


def identifiers_for(record: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Authoritative *record-level* identifiers only.

    ``k_numbers`` / ``pma_numbers`` are kept in ``normalized`` but deliberately
    **not** promoted to identifiers: ``schema.canonical_key`` ranks a 510(k)
    above a recall number, so promoting it would make two different recalls of
    the same device family collide as duplicates.
    """
    idents: list[dict[str, Any]] = []
    for scheme, field, primary in (
        ("recall_number", "product_res_number", True),
        ("accession", "res_event_number", False),
    ):
        ident = ev_identity.build_identifier(scheme, record.get(field), is_primary=primary)
        if ident:
            idents.append(ident)
    return idents


def to_evidence(
    raw_item: Mapping[str, Any],
    *,
    fetched_at: str,
    company_index: ev_identity.CompanyIndex | None = None,
) -> dict[str, Any] | None:
    """One openFDA device-recall record -> one schema-v1 evidence record."""
    rec_id = source_record_id(raw_item)
    if not rec_id:
        return None

    firm = common.clip(raw_item.get("recalling_firm"), 300)
    description = common.clip(raw_item.get("product_description"), 1200)
    reason = common.clip(raw_item.get("reason_for_recall"), 1200)
    action = common.clip(raw_item.get("action"), 800)
    root_cause = common.clip(raw_item.get("root_cause_description"), 300)
    status = common.clip(raw_item.get("recall_status"), 120)
    classification = common.clip(_first(raw_item, FIELD_ALIASES["classification"]), 120)
    initiated = _first(raw_item, FIELD_ALIASES["event_date_initiated"])
    posted = _first(raw_item, FIELD_ALIASES["event_date_posted"])
    terminated = raw_item.get("event_date_terminated")
    country = common.clip(raw_item.get("country"), 80) or "US"

    resolver = company_index or ev_identity.CompanyIndex.from_config()
    entity_ref = common.resolve_company(resolver, firm, country=country)

    normalized = {
        "record_type": "device_recall",
        "recalling_firm": firm,
        "product_description": description,
        "product_code": common.clip(raw_item.get("product_code"), 40),
        "reason_for_recall": reason,
        "action": action,
        "root_cause_description": root_cause,
        "recall_status": status,
        "classification": classification,
        "distribution_pattern": common.clip(raw_item.get("distribution_pattern"), 400),
        "product_quantity": common.clip(raw_item.get("product_quantity"), 200),
        "city": common.clip(raw_item.get("city"), 120),
        "state": common.clip(raw_item.get("state"), 80),
        "country": country,
        "cfres_id": common.clip(raw_item.get("cfres_id"), 40),
        "res_event_number": common.clip(raw_item.get("res_event_number"), 40),
        "product_res_number": common.clip(raw_item.get("product_res_number"), 60),
        "k_numbers": [common.clip(v, 40) for v in common.as_list(raw_item.get("k_numbers"))],
        "pma_numbers": [common.clip(v, 40) for v in common.as_list(raw_item.get("pma_numbers"))],
        "event_date_initiated": common.clip(initiated, 40),
        "event_date_posted": common.clip(posted, 40),
        "event_date_created": common.clip(raw_item.get("event_date_created"), 40),
        "event_date_terminated": common.clip(terminated, 40),
        # Product-code lists contain a trailing "--" padding in openFDA; keep raw.
        "interpretation_warning": INTERPRETATION_WARNING,
    }
    time_block = common.clock_block(
        event_at=initiated,
        source_public_at=posted,
        fetched_at=fetched_at,
        notes=(
            "event_at=event_date_initiated (fallback: event_date_created); "
            "source_public_at=event_date_posted (FDA enforcement posting date). "
            "event_date_terminated is administrative and is never used as a clock."
        ),
    )
    source_url = (
        f"https://www.accessdata.fda.gov/scripts/cdrh/cfdocs/cfRES/res.cfm?id={raw_item.get('res_event_number')}"
        if raw_item.get("res_event_number")
        else "https://www.accessdata.fda.gov/scripts/cdrh/cfdocs/cfRES/res.cfm"
    )
    return common.make_postmarket_evidence(
        source_id=SOURCE_ID,
        kind=KIND,
        source_record_id=rec_id,
        source_url=source_url,
        normalized=normalized,
        raw=common.raw_block_from_object(raw_item, path=f"openfda:device/recall#{rec_id}"),
        time=time_block,
        identifiers=identifiers_for(raw_item),
        entity_refs=[entity_ref],
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
    """Turn a decoded openFDA payload into ``(evidence records, meta)``."""
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
    """Fetch one page and normalise it.  Returns ``(records, meta)``; never raises on HTTP."""
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
    max_pages: int = 2,
    fetched_at: str = "",
    company_index: ev_identity.CompanyIndex | None = None,
) -> list[dict[str, Any]]:
    """Retrieve ≤ ``limit`` real recall records across ≤ ``max_pages`` pages."""
    from medradar.external_sources import base as _base

    fetched = fetched_at or _base.utc_iso()
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


__all__ = [
    "API_URL",
    "EVENT_AT_FIELDS",
    "FIVE_FIRM_QUERIES",
    "INTERPRETATION_WARNING",
    "KIND",
    "LICENCE_STATUS",
    "PUBLIC_AT_FIELDS",
    "SKIP_CAP",
    "SOURCE_ID",
    "SOURCE_NAME",
    "collect",
    "collect_page",
    "fetch",
    "identifiers_for",
    "normalise_payload",
    "page_params",
    "source_record_id",
    "to_evidence",
]
