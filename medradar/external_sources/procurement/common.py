"""Shared helpers for the procurement / hiring connectors.

Why a local ``common`` module instead of importing another subpackage's
-------------------------------------------------------------
Each external-source subpackage is owned by a different agent and is reviewed
independently; a cross-subpackage import would couple two write scopes.  The few
helpers needed here (bounded text, stable digests, four-clock assembly, raw-byte
block, company resolution) are therefore local.

The two rules this module exists to enforce
-------------------------------------------
1. **Four clocks, never three.**  :func:`clock_block` is the only way these
   connectors build a ``time`` block, and it always requires the caller to say
   explicitly what ``source_public_at`` and ``event_at`` mean.  A procurement
   award date is not a publication date; a job's ``first_published`` is not our
   fetch time.
2. **Publication quality is downgraded, not guessed.**  A month-only or
   derived date is labelled ``coarse``/``derived`` so
   :func:`medradar.external_sources.timeq.lead_time_days` refuses to use it.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Mapping

from medradar.external_sources import identity as ev_identity
from medradar.external_sources import schema as ev_schema
from medradar.external_sources import timeq

#: Text is clipped hard at the boundary: these are free-text procurement and job
#: fields, and an unbounded string must never reach the evidence store.
DEFAULT_TEXT_LIMIT = 1200


def clip(value: Any, limit: int = DEFAULT_TEXT_LIMIT) -> str:
    """Trim to ``limit`` characters without inventing content."""
    if value is None:
        return ""
    text = str(value)
    text = " ".join(text.split())
    return text[:limit]


def utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def digest(*parts: Any) -> str:
    """Stable 32-char digest over ordered parts (never includes a clock)."""
    payload = "\u241f".join("" if p is None else str(p) for p in parts)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:32]


def epoch_millis_to_iso(value: Any) -> tuple[str, str]:
    """``1788199939703`` -> ``("2026-08-31T18:12:19Z", "exact")``.

    Lever publishes ``createdAt`` in **milliseconds**.  Reading it as seconds
    yields a 1970 date, so the conversion lives in one place and returns the
    quality alongside the value.  Non-numeric input returns ``("", "unknown")``
    rather than a guessed date.
    """
    if value is None or isinstance(value, bool):
        return "", "unknown"
    try:
        millis = int(value)
    except (TypeError, ValueError):
        return "", "unknown"
    if millis <= 0:
        return "", "unknown"
    # anything below 10^11 is almost certainly seconds, not milliseconds
    seconds = millis / 1000.0 if millis >= 100_000_000_000 else float(millis)
    try:
        moment = datetime.fromtimestamp(seconds, tz=timezone.utc)
    except (OverflowError, OSError, ValueError):
        return "", "unknown"
    return moment.isoformat().replace("+00:00", "Z"), "exact"


def date_quality(*values: Any) -> str:
    """Worst-case quality across the supplied raw date strings."""
    qualities = [timeq.implied_quality(v) for v in values if v]
    if not qualities:
        return "unknown"
    for worst in ("unknown", "derived", "coarse", "day", "exact"):
        if worst in qualities:
            return worst
    return "unknown"


def clock_block(
    *,
    event_at: Any,
    source_public_at: Any,
    fetched_at: str,
    quality: str | None = None,
    notes: str = "",
) -> dict[str, Any]:
    """Assemble the four-clock block, with ``first_observed_at`` = fetch clock.

    ``first_observed_at`` is never back-filled from ``source_public_at``: for a
    first collection they coincide, and for a backfill they must not.
    """
    fetched = timeq.parse_datetime(fetched_at) or timeq.utc_now()
    return timeq.build_time(
        event_at=event_at,
        source_public_at=source_public_at,
        quality=quality or date_quality(source_public_at),
        fetched_at=fetched,
        notes=notes,
    )


def raw_block(
    body: bytes,
    *,
    path: str,
    media_type: str = "application/json",
) -> dict[str, Any]:
    """Immutable raw-byte descriptor required by ``schema.make_evidence``."""
    return {
        "content_hash": ev_schema.sha256_bytes(body),
        "bytes": len(body),
        "path": path,
        "media_type": media_type,
    }


def resolve_company(
    index: ev_identity.CompanyIndex | None,
    name: Any,
    *,
    country: str = "",
) -> dict[str, Any]:
    """Resolve a supplier/employer name through the shared company index.

    Returns a ``method="none"`` reference for an empty name instead of raising:
    a record with an unknown supplier is still a valid record, but it must not
    look like an attempted link.
    """
    resolver = index or ev_identity.CompanyIndex.from_config()
    resolution = resolver.resolve(name, country=country)
    return {
        "entity_type": "company",
        "name_raw": "" if name is None else str(name),
        "resolved_key": resolution.get("resolved_key"),
        "method": resolution.get("method", "none"),
        "confidence": resolution.get("confidence", 0.0),
        "evidence": resolution.get("evidence", {}),
        "note": resolution.get("note", ""),
    }


def evidence(
    *,
    source_id: str,
    kind: str,
    source_record_id: str,
    source_url: str,
    normalized: Mapping[str, Any],
    raw: Mapping[str, Any],
    time_block: Mapping[str, Any],
    identifiers: list[Mapping[str, Any]] | None = None,
    entity_refs: list[Mapping[str, Any]] | None = None,
    source_name: str,
    licence_status: str,
    attribution: str,
    redistribution: str = "unknown",
    fetched_at: str = "",
    collection_run_id: str = "",
) -> dict[str, Any]:
    """Thin wrapper over :func:`schema.make_evidence` with the licence metadata."""
    return ev_schema.make_evidence(
        source_id=source_id,
        kind=kind,
        source_record_id=source_record_id,
        source_url=source_url,
        normalized=normalized,
        raw=raw,
        time=time_block,
        identifiers=identifiers or [],
        entity_refs=entity_refs or [],
        provenance={
            "source_name": source_name,
            "licence_status": licence_status,
            "redistribution": redistribution,
            "attribution": attribution,
            "evidence_reference": source_url,
            "source_time_quality": time_block.get("source_public_at_quality", ""),
        },
        collection_run_id=collection_run_id,
        fetched_at=fetched_at,
    )


def identifier(scheme: str, value: Any, *, is_primary: bool = False, note: str = "") -> dict[str, Any] | None:
    """Build one identifier entry, normalising by scheme when we know it."""
    scheme_key = str(scheme).strip().lower()
    text = "" if value is None else str(value).strip()
    if not text:
        return None
    if scheme_key == "doi":
        text = ev_identity.normalize_doi(text)
    return {
        "scheme": scheme_key,
        "value": text,
        "raw_value": "" if value is None else str(value),
        "is_primary": bool(is_primary),
        "note": note,
    }


def identifier_list(*entries: tuple[str, Any] | tuple[str, Any, dict[str, Any]] | None) -> list[dict[str, Any]]:
    """Build a de-duplicated identifier list from ``(scheme, value[, kwargs])`` tuples."""
    out: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for entry in entries:
        if not entry:
            continue
        scheme, value = entry[0], entry[1]
        kwargs = entry[2] if len(entry) > 2 else {}
        built = identifier(str(scheme), value, **kwargs)  # type: ignore[arg-type]
        if not built:
            continue
        key = (built["scheme"], built["value"])
        if key in seen:
            continue
        seen.add(key)
        out.append(built)
    return out


def dedupe_report(items: list[Mapping[str, Any]], key_fields: tuple[str, ...]) -> dict[str, Any]:
    """Report duplicate postings by a business key (never by evidence id).

    The hiring protocol requires de-duplication on ``(company, title, location)``
    and a reported duplicate rate, because the same requisition is routinely
    re-posted.  This function only *measures*; it does not delete anything, so a
    re-posted role stays visible as a separate posting with the same business key.
    """
    total = len(items)
    groups: dict[tuple[Any, ...], list[int]] = {}
    for index, item in enumerate(items):
        key = tuple(_normalise_key_part(item.get(field)) for field in key_fields)
        groups.setdefault(key, []).append(index)
    duplicated = {k: v for k, v in groups.items() if len(v) > 1}
    duplicate_instances = sum(len(v) - 1 for v in duplicated.values())
    return {
        "key_fields": list(key_fields),
        "n_items": total,
        "n_business_keys": len(groups),
        "n_keys_with_duplicates": len(duplicated),
        "duplicate_instances": duplicate_instances,
        "duplicate_rate": round(duplicate_instances / total, 4) if total else 0.0,
        "examples": [
            {"key": list(key), "count": len(indices)}
            for key, indices in list(duplicated.items())[:5]
        ],
    }


def _normalise_key_part(value: Any) -> Any:
    if value is None:
        return ""
    return " ".join(str(value).lower().split())


def canonical_json_line(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)


__all__ = [
    "DEFAULT_TEXT_LIMIT",
    "canonical_json_line",
    "clip",
    "clock_block",
    "date_quality",
    "dedupe_report",
    "digest",
    "epoch_millis_to_iso",
    "evidence",
    "identifier",
    "identifier_list",
    "raw_block",
    "resolve_company",
    "utc_iso",
]
