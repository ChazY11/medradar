"""Shared, network-free helpers for the scholarly connectors.

Everything here is a pure function over data that a connector already fetched.
Nothing in this module performs I/O at import time; the company index is built
lazily from ``config/companies_device.json`` on first use.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, Iterable, Mapping

from .. import identity, schema, timeq

#: Preferred representative order when several sources describe the same work.
#: Chosen by *timestamp reliability* for ``source_public_at``: Europe PMC
#: publishes an explicit first-publication date, Crossref publishes
#: ``published-online``, OpenAlex publishes ``publication_date`` (often the issue
#: date), and so on.  The order is fixed before looking at any result.
TIME_SOURCE_PREFERENCE: tuple[str, ...] = (
    "europepmc",
    "crossref",
    "openalex",
    "pubmed_eutils",
    "semantic_scholar",
    "openaire",
)

_INDEX: identity.CompanyIndex | None = None


def as_datetime(value: Any) -> datetime:
    """Coerce a fetch clock (datetime, ISO string or ``None``) to an aware datetime."""
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    parsed = timeq.parse_datetime(value)
    return parsed or timeq.utc_now()


def company_index() -> identity.CompanyIndex:
    """Lazily built index over the five target firms plus configured companies."""
    global _INDEX
    if _INDEX is None:
        _INDEX = identity.CompanyIndex.from_config()
    return _INDEX


def raw_block(item: Mapping[str, Any]) -> dict[str, Any]:
    """Content-addressed descriptor of one raw item, as required by the schema."""
    canonical = schema.canonical_json(item)
    return {
        "content_hash": schema.sha256_text(canonical),
        "bytes": len(canonical.encode("utf-8")),
        "type": "json-record",
    }


_DMY = re.compile(r"^(\d{1,2})/(\d{1,2})/(\d{4})$")
_MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}


def date10(value: Any) -> str:
    """Extract a ``YYYY-MM-DD`` prefix from an ISO-ish timestamp, or ``""``."""
    if value is None:
        return ""
    text = str(value).strip()
    if not text:
        return ""
    match = re.match(r"^(\d{4})-(\d{2})-(\d{2})", text)
    if match:
        return f"{match.group(1)}-{match.group(2)}-{match.group(3)}"
    match = _DMY.match(text)  # CTIS publishes DD/MM/YYYY
    if match:
        return f"{match.group(3)}-{int(match.group(2)):02d}-{int(match.group(1)):02d}"
    return ""


def coerce_date(value: Any) -> tuple[str, str]:
    """Return ``(iso_date, quality)`` without ever inflating the precision.

    ``quality`` follows :data:`medradar.external_sources.schema.TIME_QUALITIES`:
    a full calendar date is ``day``; month/year or "2020 Dec"/"2026 Nov-Dec"
    becomes the first day of the period with quality ``coarse``; unknown values
    stay empty.  Nothing is guessed beyond the first day of a published period.
    """
    if value is None:
        return "", "unknown"
    text = str(value).strip()
    if not text:
        return "", "unknown"
    day = date10(text)
    if day:
        return day, "day"
    match = re.match(r"^(\d{4})[-/](\d{2})$", text)
    if match:
        return f"{match.group(1)}-{match.group(2)}-01", "coarse"
    match = re.match(r"^(\d{4})$", text)
    if match:
        return f"{match.group(1)}-01-01", "coarse"
    # "2020 Dec", "Dec 2020", "2026 Nov-Dec", "2019 Jan-Feb"
    match = re.match(r"^(\d{4})\s+([A-Za-z]{3})", text) or re.match(
        r"^([A-Za-z]{3})\s+(\d{4})$", text
    )
    if match:
        first, second = match.group(1), match.group(2)
        if first.isdigit():
            year, month_name = int(first), second
        else:
            year, month_name = int(second), first
        month = _MONTHS.get(month_name[:3].lower())
        if month:
            return f"{year:04d}-{month:02d}-01", "coarse"
    return "", "unknown"


def company_refs(
    names: Iterable[Any],
    *,
    tier: str,
    max_refs: int = 12,
) -> list[dict[str, Any]]:
    """Resolve company strings into ``entity_refs`` with an explicit signal tier.

    ``tier`` records *why* the name matched, because the three signals are not
    evidence of the same strength:

    * ``funder`` / ``grantee`` / ``participant`` / ``lead_sponsor`` — the source
      assigns the name in a structured field (strongest);
    * ``author_affiliation`` — the name appears in an author's institution
      string (a real affiliation of the work, but not a funder);
    * ``text_mention`` — only a keyword/abstract hit; always downgraded to
      ``candidate`` so it can never enter a confirmed-link denominator.
    """
    index = company_index()
    refs: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for name in names:
        if name is None:
            continue
        resolved = index.resolve(name)
        key = str(resolved.get("resolved_key") or "")
        if not key:
            continue
        marker = (key, tier)
        if marker in seen:
            continue
        seen.add(marker)
        method = str(resolved.get("method", "none"))
        confidence = float(resolved.get("confidence", 0.0))
        evidence = dict(resolved.get("evidence") or {})
        evidence["signal"] = tier
        if tier == "text_mention" or method == "candidate":
            method = "candidate"
            confidence = min(confidence or 0.55, 0.55)
        if method == "none":
            continue
        ref = {
            "entity_type": "company",
            "name_raw": str(resolved.get("name_raw") or name),
            "resolved_key": key,
            "method": method,
            "confidence": confidence,
            "evidence": evidence,
            "note": str(resolved.get("note") or ""),
        }
        refs.append(ref)
        if len(refs) >= max_refs:
            break
    return refs


def time_block(
    *,
    event_at: Any,
    source_public_at: Any,
    fetched_at: datetime,
    notes: str = "",
) -> dict[str, Any]:
    """Build the four-clock block, keeping quality in step with the raw value."""
    public_date, quality = coerce_date(source_public_at)
    event_date, _ = coerce_date(event_at)
    return timeq.build_time(
        event_at=event_date or None,
        source_public_at=public_date or None,
        quality=quality,
        fetched_at=fetched_at,
        notes=notes,
    )


def metadata_clock_fields(*values: Any) -> list[dict[str, str]]:
    """Describe dates that are *ingestion* clocks, never publication clocks.

    These are kept in ``normalized`` so a reviewer can see them, but connectors
    must never pass them to ``source_public_at``.
    """
    return [
        {"field": str(field), "value": str(value), "role": "metadata_ingestion_clock"}
        for field, value in values
        if value not in (None, "")
    ]


def provenance(
    *,
    source_name: str,
    licence_status: str,
    attribution: str,
    redistribution: str = "unknown",
    evidence_reference: str = "",
    quality: str = "",
) -> dict[str, Any]:
    """Assemble the provenance block consistently across connectors."""
    return {
        "source_name": source_name,
        "licence_status": licence_status,
        "redistribution": redistribution,
        "attribution": attribution,
        "evidence_reference": evidence_reference,
        "source_time_quality": quality,
    }


def nct_ids_in_text(value: Any) -> list[str]:
    """Deterministic NCT identifiers found in a *structured* string field."""
    if value is None:
        return []
    found = re.findall(r"NCT\d{8}", str(value))
    out: list[str] = []
    for nct in found:
        if nct not in out:
            out.append(nct)
    return out

