"""UN Comtrade — public preview connector (country-level aggregates only).

Probed 2026-11-09: ``/public/v1/preview/C/A/HS`` answers **without a key** and
returns real records; the full ``/data/v1/get/...`` endpoint answers 401 without
a subscription key.  This connector therefore uses the preview endpoint only and
reports honestly what a preview is: a capped slice.

Every record produced here is ``trade_aggregate``.  It carries **no company
identity at all** — the connector emits an empty ``entity_refs`` list on purpose,
because the source cannot support a firm link and a keyword guess must never be
promoted to one.
"""

from __future__ import annotations

from typing import Any, Iterable, Mapping, Sequence

from .. import base, schema, timeq

SOURCE_ID = "un_comtrade"
KIND = "trade_aggregate"
LICENCE_STATUS = "restricted"  # UN Comtrade terms: free non-commercial use, redistribution restricted
REDISTRIBUTION = "restricted"

PREVIEW_URL = "https://comtradeapi.un.org/public/v1/preview/C/A/HS"

#: Medical-device-relevant HS6 codes used as the default scope.
HS6_CODES: tuple[str, ...] = ("9018", "9019", "9021", "9022", "9402")

#: Comtrade uses partnerCode 0 for the "World" total row.
WORLD_PARTNER_CODE = 0


def preview_url(reporter_code: int | str, period: int | str, cmd_code: str, flow_code: str) -> str:
    return (
        f"{PREVIEW_URL}?reporterCode={reporter_code}&period={period}"
        f"&cmdCode={cmd_code}&flowCode={flow_code}"
    )


def _num(value: Any) -> float | None:
    """Return a float, or ``None`` — never a guessed zero."""
    if value is None or value == "":
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number


def _int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def normalize_item(item: Mapping[str, Any]) -> dict[str, Any]:
    """One Comtrade row -> a flat, unit-annotated observation.

    The preview leaves ``reporterDesc``/``partnerDesc``/``cmdDesc`` null, so no
    label is invented here; only the numeric codes survive.
    """
    partner = _int(item.get("partnerCode"))
    flow = str(item.get("flowCode") or "")
    return {
        "data_class": "country_level_aggregate",
        "reporter_code": _int(item.get("reporterCode")),
        "partner_code": partner,
        "partner_is_world_total": partner == WORLD_PARTNER_CODE,
        "flow_code": flow,
        "flow_direction": {"M": "imports", "X": "exports", "R": "re_exports"}.get(flow, "UNKNOWN"),
        "hs_code": str(item.get("cmdCode") or ""),
        "classification": str(item.get("classificationCode") or ""),
        "period": str(item.get("period") or ""),
        "ref_year": _int(item.get("refYear")),
        "ref_month": _int(item.get("refMonth")),
        "trade_value_usd": _num(item.get("primaryValue")),
        "cif_value_usd": _num(item.get("cifvalue")),
        "fob_value_usd": _num(item.get("fobvalue")),
        "net_weight_kg": _num(item.get("netWgt")),
        "quantity": _num(item.get("qty")),
        "quantity_unit_code": _int(item.get("qtyUnitCode")),
        "quantity_is_estimated": item.get("isQtyEstimated"),
    }


def source_record_id(normalized: Mapping[str, Any]) -> str:
    """Stable identity of one aggregate cell (never of a company)."""
    return (
        f"reporter={normalized.get('reporter_code')}"
        f":partner={normalized.get('partner_code')}"
        f":flow={normalized.get('flow_code')}"
        f":hs={normalized.get('hs_code')}"
        f":period={normalized.get('period')}"
        f":cls={normalized.get('classification')}"
    )


def to_evidence(item: Mapping[str, Any], *, fetched_at: Any = None) -> dict[str, Any]:
    """One raw Comtrade row -> a schema-v1 evidence record.

    Time semantics: an annual aggregate has a *reference period*, not an
    occurrence date, and Comtrade publishes no release timestamp.  ``event_at``
    is therefore a documented, derived year-end anchor and ``source_public_at``
    is left empty with quality ``unknown`` — it must not be used for lead-time.
    """
    normalized = normalize_item(item)
    year = normalized.get("ref_year")
    anchor = f"{year}-12-31" if year else None
    fetched = timeq.parse_datetime(fetched_at) if fetched_at else None
    raw_payload = dict(item)
    return schema.make_evidence(
        source_id=SOURCE_ID,
        kind=KIND,
        source_record_id=source_record_id(normalized),
        source_url=preview_url(
            normalized.get("reporter_code"),
            normalized.get("period"),
            normalized.get("hs_code") or "",
            normalized.get("flow_code") or "",
        ),
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
                "annual HS aggregate; event_at is a derived year-end anchor, not an observed event date. "
                "Comtrade exposes no publication timestamp, so source_public_at is UNKNOWN and this record "
                "must not be used for lead-time claims."
            ),
        ),
        identifiers=(),  # an aggregate cell has no authoritative identifier
        entity_refs=(),  # deliberately empty: an aggregate cannot be linked to a company
        provenance={
            "source_name": "UN Comtrade (public preview endpoint)",
            "licence_status": LICENCE_STATUS,
            "redistribution": REDISTRIBUTION,
            "attribution": "UN Comtrade Database, United Nations Statistics Division",
            "evidence_reference": "preview endpoint; see research/data_expansion/probes/un_comtrade/",
            "source_time_quality": "unknown (no publication clock; period only)",
        },
        fetched_at=timeq.iso(fetched) if fetched else "",
    )


def collect(
    client: base.HttpClient,
    *,
    reporter_code: int = 842,
    period: int = 2023,
    cmd_codes: Sequence[str] = HS6_CODES,
    flow_code: str = "M",
    limit: int = 50,
) -> list[dict[str, Any]]:
    """Fetch at most ``limit`` aggregate rows, one preview request per HS code.

    Bounded by construction: at most ``len(cmd_codes)`` requests, and the loop
    stops as soon as ``limit`` records have been produced.  A failed request is
    skipped, not retried forever and not raised.
    """
    if limit <= 0:
        return []
    records: list[dict[str, Any]] = []
    for cmd_code in cmd_codes:
        if len(records) >= limit:
            break
        result = client.get(
            PREVIEW_URL,
            params={
                "reporterCode": reporter_code,
                "period": period,
                "cmdCode": cmd_code,
                "flowCode": flow_code,
            },
        )
        if not result.ok:
            continue
        try:
            payload = result.json()
        except ValueError:
            continue
        rows: Iterable[Mapping[str, Any]] = payload.get("data") or []
        for row in rows:
            if len(records) >= limit:
                break
            records.append(to_evidence(row, fetched_at=base.utc_iso()))
    return records
