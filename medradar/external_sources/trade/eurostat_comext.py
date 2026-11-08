"""Eurostat Comext connector — EU trade in goods by HS2-4-6 and CN8.

Probed 2026-11-09: the Comext dissemination API is open and keyless.  Two call
shape traps were confirmed live and are encoded here so a caller cannot fall
into them again:

* the path is ``/api/comext/dissemination/...`` — the mainstream
  ``/api/dissemination/...`` answers 404 for this dataset;
* the dimensions are ``freq, reporter, partner, product, flow, indicators,
  time`` — a ``geo=`` parameter is rejected with 400.

Records are ``trade_aggregate``: no company can be identified, and the
connector emits no entity links.
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from .. import base, schema, timeq

SOURCE_ID = "eurostat_comext"
KIND = "trade_aggregate"
LICENCE_STATUS = "open_licence"  # free reuse with attribution (Commission Decision 2011/833/EU)
REDISTRIBUTION = "allowed_with_attribution"

COMEXT_URL = "https://ec.europa.eu/eurostat/api/comext/dissemination/statistics/1.0/data/DS-045409"
DATASET = "DS-045409"
DATASET_LABEL = "EU trade since 1988 by HS2-4-6 and CN8"

FLOW_LABELS = {1: "imports", 2: "exports"}

#: Medical-device-relevant product codes used as the default scope.
PRODUCT_CODES: tuple[str, ...] = ("9018", "9019", "9021", "9022", "9402")


def _category_entry(dimension: Mapping[str, Any], position: int) -> tuple[str, str]:
    """Map a zero-based dimension position to its ``(code, label)`` pair.

    The code comes from ``category.index`` (label -> position, inverted here), so
    a record's identity is built from the stable code and never from a label that
    Eurostat may reword.
    """
    category = (dimension or {}).get("category") or {}
    index = category.get("index") or {}
    code: str | None = None
    for name, pos in index.items():
        if pos == position:
            code = str(name)
            break
    if code is None:
        code = str(position)
    label = str((category.get("label") or {}).get(code) or code)
    return code, label


def flatten_jsonstat(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Flatten a JSON-stat 2.0 cube into one dict per **published** cell.

    JSON-stat is sparse: ``value`` only contains non-null cells keyed by the flat
    index.  Nothing is interpolated here — a missing cell simply does not exist,
    which is the correct behaviour for "value not published".

    Each cell carries both the label (``reporter``, ``product``, …) and the
    stable code (``reporter_code``, ``product_code``, …).
    """
    ids = list(payload.get("id") or [])
    sizes = list(payload.get("size") or [])
    values = payload.get("value") or {}
    if not ids or not sizes or len(ids) != len(sizes):
        return []
    dimensions = payload.get("dimension") or {}
    multi = 1
    strides: list[int] = []
    for size in sizes:
        multi *= int(size)
        strides.append(multi)
    observations: list[dict[str, Any]] = []
    for flat, value in sorted(values.items(), key=lambda item: int(item[0])):
        coords: list[int] = []
        # strides[i] = product of sizes[0..i]; coordinate of dim i is
        # (flat // strides[i-1]) % sizes[i]
        for index, size in enumerate(sizes):
            divisor = strides[index - 1] if index else 1
            coords.append((int(flat) // divisor) % int(size))
        cell: dict[str, Any] = {}
        for pos, dim in enumerate(ids):
            code, label = _category_entry(dimensions.get(dim, {}), coords[pos])
            cell[dim] = label
            cell[f"{dim}_code"] = code
        cell["value"] = value
        observations.append(cell)
    return observations


def normalize_observation(observation: Mapping[str, Any]) -> dict[str, Any]:
    """One flattened cell -> a labelled, unit-annotated observation."""
    flow_code = str(observation.get("flow_code") or observation.get("flow") or "")
    return {
        "data_class": "country_level_aggregate",
        "dataset": DATASET,
        "frequency": str(observation.get("freq_code") or observation.get("freq") or ""),
        "reporter": str(observation.get("reporter") or ""),
        "reporter_code": str(observation.get("reporter_code") or ""),
        "partner": str(observation.get("partner") or ""),
        "partner_code": str(observation.get("partner_code") or ""),
        "product_code": str(observation.get("product_code") or observation.get("product") or ""),
        "product_description": str(observation.get("product") or ""),
        "flow": flow_code,
        "flow_direction": FLOW_LABELS.get(int(flow_code) if flow_code.isdigit() else -1, "UNKNOWN"),
        "indicator": str(observation.get("indicators_code") or observation.get("indicators") or ""),
        "period": str(observation.get("time_code") or observation.get("time") or ""),
        "value": float(observation["value"]) if observation.get("value") is not None else None,
        "currency": "EUR",
    }


def source_record_id(normalized: Mapping[str, Any]) -> str:
    return (
        f"{DATASET}:{normalized.get('frequency')}:{normalized.get('reporter_code')}"
        f":{normalized.get('partner_code')}:{normalized.get('product_code')}"
        f":{normalized.get('flow')}:{normalized.get('period')}"
        f":{normalized.get('indicator')}"
    )


def to_evidence(observation: Mapping[str, Any], *, fetched_at: Any = None) -> dict[str, Any]:
    """One flattened Comext cell -> a schema-v1 aggregate evidence record."""
    normalized = normalize_observation(observation)
    period = normalized.get("period") or ""
    frequency = normalized.get("frequency") or ""
    # Annual -> year end anchor; monthly -> month end is not knowable without a
    # calendar, so use the first of the month and downgrade quality.
    if frequency.lower().startswith("a") and len(period) == 4 and period.isdigit():
        anchor = f"{period}-12-31"
    elif len(period) == 4 and period.isdigit():
        anchor = f"{period}-01-01"
    else:
        anchor = None
    fetched = timeq.parse_datetime(fetched_at) if fetched_at else None
    raw_payload = dict(observation)
    return schema.make_evidence(
        source_id=SOURCE_ID,
        kind=KIND,
        source_record_id=source_record_id(normalized),
        source_url=COMEXT_URL,
        normalized=normalized,
        raw={
            "content_hash": schema.sha256_json(raw_payload),
            "bytes": len(schema.canonical_json(raw_payload).encode("utf-8")),
        },
        time=timeq.build_time(
            event_at=anchor,
            source_public_at=None,
            quality="unknown",
            fetched_at=fetched,
            notes=(
                "HS/CN aggregate by reporting period. event_at is a derived period anchor; the dataset's "
                "'updated' field is a refresh timestamp for the whole dataset, NOT the publication date of "
                "this figure, so source_public_at is UNKNOWN."
            ),
        ),
        identifiers=(),
        entity_refs=(),  # an aggregate cannot be linked to a company
        provenance={
            "source_name": "Eurostat Comext (DS-045409)",
            "licence_status": LICENCE_STATUS,
            "redistribution": REDISTRIBUTION,
            "attribution": "Source: Eurostat (Comext dataset DS-045409)",
            "evidence_reference": "see research/data_expansion/probes/eurostat_comext/",
            "source_time_quality": "unknown (period only; dataset refresh time is not a record clock)",
        },
        fetched_at=timeq.iso(fetched) if fetched else "",
    )


def collect(
    client: base.HttpClient,
    *,
    reporter: str = "DE",
    partners: Sequence[str] = ("US",),
    products: Sequence[str] = PRODUCT_CODES,
    flow: int = 1,
    period: int = 2023,
    indicators: str = "VALUE_IN_EUROS",
    limit: int = 50,
) -> list[dict[str, Any]]:
    """Fetch at most ``limit`` aggregate cells.

    One request is made per (product, partner) pair, hard-capped at
    ``len(products) * len(partners)`` requests; the loop stops at ``limit``.
    """
    if limit <= 0:
        return []
    records: list[dict[str, Any]] = []
    for product in products:
        if len(records) >= limit:
            break
        for partner in partners:
            if len(records) >= limit:
                break
            result = client.get(
                COMEXT_URL,
                params={
                    "format": "JSON",
                    "lang": "EN",
                    "reporter": reporter,
                    "partner": partner,
                    "product": product,
                    "flow": flow,
                    "time": period,
                    "indicators": indicators,
                },
            )
            if not result.ok:
                continue
            try:
                payload = result.json()
            except ValueError:
                continue
            for cell in flatten_jsonstat(payload):
                if len(records) >= limit:
                    break
                records.append(to_evidence(cell, fetched_at=base.utc_iso()))
    return records
