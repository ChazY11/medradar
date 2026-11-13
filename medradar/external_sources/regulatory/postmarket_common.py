"""Shared helpers for the postmarket (recall / adverse event / shortage / import-alert)
connectors of DATA-EXPANSION-001.

Design rules
------------
* **No network at import time.**  Every network call happens inside a function
  that receives an :class:`medradar.external_sources.base.HttpClient`.
* **Pure parsing.**  HTML table extraction, record ids and company resolution
  are pure functions so they can be unit-tested offline.
* **Uncertainty is preserved.**  A company string is only *confirmed* through
  :meth:`medradar.external_sources.identity.CompanyIndex.resolve`; semantic
  candidates stay candidates and are counted separately.
* **Interpretation guards.**  The postmarket sources are *passive reporting
  systems*.  Every evidence record produced by this package carries the same
  interpretation warning in ``normalized["interpretation_warning"]`` so that a
  downstream reader cannot mistake a report count for an incidence rate.
"""

from __future__ import annotations

import hashlib
import re
from datetime import date
from html.parser import HTMLParser
from typing import Any, Iterable, Mapping, Sequence

from medradar.external_sources import identity as ev_identity
from medradar.external_sources import schema as ev_schema
from medradar.external_sources import timeq as ev_timeq

#: The five firms this expansion round is anchored on (identity.TARGET_FIRM_KEYS).
FIVE_FIRM_KEYS: tuple[str, ...] = ev_identity.TARGET_FIRM_KEYS

FIVE_FIRM_LABELS: dict[str, str] = {
    "medtronic": "Medtronic",
    "ge_healthcare": "GE HealthCare",
    "philips": "Philips",
    "draeger": "Dräger",
    "mindray": "Mindray",
}

#: The single most important scientific caveat of this whole subpackage.
#: Wording is deliberately blunt: a count of reports is not a rate.
PASSIVE_SURVEILLANCE_WARNING = (
    "PASSIVE REPORTING COUNT, NOT AN INCIDENCE RATE. Postmarket report counts are "
    "driven by reporting incentives, litigation, media attention, product usage "
    "volume and FDA collection efforts. Increases can reflect better reporting "
    "rather than worse product quality. Never interpret a count (or a change in a "
    "count) as a failure rate, a defect rate, or evidence of quality deterioration."
)

RECALL_WARNING = (
    "A recall record documents one enforcement action, not the underlying failure "
    "rate of a device family. Recall publication lags the initiating event and "
    "FDA does not update the status after classification; a terminated status is "
    "not evidence that the product was safe."
)

SHORTAGE_WARNING = (
    "The FDA shortage/discontinuance lists are point-in-time snapshots of the "
    "current list. The page is not an archive: entries disappear when resolved and "
    "earlier states are not queryable, so a short current list is not evidence that "
    "shortages were absent historically."
)

IMPORT_ALERT_WARNING = (
    "An import alert is a detention-without-physical-examination instruction aimed "
    "at named foreign establishments or product types. It is not a company-level "
    "quality rating, and absence of a firm from the current red list carries no "
    "information about that firm's compliance history."
)

_EVENT_AT_HINT = "event_at is the real-world event date published by the source"
_PUBLIC_AT_HINT = "source_public_at is the date the record first became publicly visible at the source"


# --------------------------------------------------------------------------- ids
def record_digest(*parts: object) -> str:
    """Stable 32-hex digest over ordered parts (no clock, no randomness)."""
    joined = "|".join("" if part is None else str(part) for part in parts)
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()[:32]


def clip(value: Any, limit: int = 2000) -> str:
    """Trimmed string, never ``None`` (the schema prefers "" to null for text)."""
    if value is None:
        return ""
    text = str(value).strip()
    return text if len(text) <= limit else text[:limit] + "…"


def as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        return [item for item in value if item not in (None, "")]
    return [value] if value != "" else []


# ------------------------------------------------------------------------- time
def year_of(value: Any) -> str:
    """Four-digit year string of a parsed date, or ``""``."""
    day = ev_timeq.parse_date(value)
    return f"{day.year:04d}" if day else ""


_US_DATE_RE = re.compile(r"^(\d{1,2})/(\d{1,2})/(\d{4})$")


def us_date_iso(value: Any) -> str:
    """Parse an FDA-page date as **MM/DD/YYYY** and return ISO ``YYYY-MM-DD``.

    ``timeq.parse_date`` tries ``%d/%m/%Y`` before ``%m/%d/%Y``, so an ambiguous
    US date such as ``11/06/2026`` would silently become 11 June instead of
    6 November.  FDA pages are US-formatted, so slash dates are disambiguated
    here first; unambiguous ``YYYY/MM/DD`` values still go through ``timeq``.
    """
    text = str(value or "").strip()
    match = _US_DATE_RE.match(text)
    if match:
        month, day, year = (int(part) for part in match.groups())
        try:
            return date(year, month, day).isoformat()
        except ValueError:
            return ""
    parsed = ev_timeq.parse_date(text)
    return parsed.isoformat() if parsed else ""


def date_quality(value: Any) -> str:
    """``day`` when a real calendar day was parsed, else ``unknown`` (never inflated)."""
    return "day" if us_date_iso(value) else "unknown"


def clock_block(
    *,
    event_at: Any,
    source_public_at: Any,
    fetched_at: str,
    notes: str,
    quality: str | None = None,
) -> dict[str, Any]:
    """Four-clock block with an explicit, non-invented ``event_at``.

    ``first_observed_at`` is the fetch clock, never a back-filled history.
    ``quality`` defaults to the precision the source actually published.
    """
    fetched = ev_timeq.parse_datetime(fetched_at)
    return ev_timeq.build_time(
        event_at=event_at,
        source_public_at=source_public_at,
        quality=quality,
        fetched_at=fetched,
        notes=notes,
    )


# --------------------------------------------------------------------- raw hash
def raw_block_from_object(item: Mapping[str, Any], *, path: str, media_type: str = "application/json") -> dict[str, Any]:
    """Content hash of one record exactly as received (canonical JSON of the item)."""
    payload = ev_schema.canonical_json(dict(item)).encode("utf-8")
    return {
        "content_hash": ev_schema.sha256_bytes(payload),
        "bytes": len(payload),
        "path": path,
        "media_type": media_type,
    }


def raw_block_from_page(body: bytes, *, path: str, media_type: str = "text/html") -> dict[str, Any]:
    """Content hash of the whole HTML page a parsed record came from."""
    return {
        "content_hash": ev_schema.sha256_bytes(body),
        "bytes": len(body),
        "path": path,
        "media_type": media_type,
    }


# ------------------------------------------------------------------- identity
def resolve_company(
    index: ev_identity.CompanyIndex,
    raw_name: Any,
    *,
    country: str = "",
) -> dict[str, Any]:
    """Resolve one source company string to an ``entity_ref`` (schema v1 shape)."""
    resolution = index.resolve(raw_name, country=country)
    return {
        "entity_type": "company",
        "name_raw": resolution.get("name_raw", ""),
        "resolved_key": resolution.get("resolved_key"),
        "method": resolution.get("method", "none"),
        "confidence": float(resolution.get("confidence", 0.0)),
        "evidence": dict(resolution.get("evidence") or {}),
        "note": resolution.get("note", ""),
    }


def confirmed_firm_key(ref: Mapping[str, Any]) -> str | None:
    """Firm key only when the link is deterministic (never for ``candidate``)."""
    if ref.get("method") in ev_schema.CONFIRMED_METHODS:
        key = ref.get("resolved_key")
        return str(key) if key else None
    return None


def is_five_firm(ref: Mapping[str, Any]) -> bool:
    return confirmed_firm_key(ref) in FIVE_FIRM_KEYS


class FirmResolver:
    """Counts confirmed vs candidate links for one evidence record.

    Used by the sampling scripts so the numbers reported to the register and to
    ``FIVE_FIRM_SERIES.json`` are produced by one code path.
    """

    def __init__(self, index: ev_identity.CompanyIndex | None = None) -> None:
        self.index = index or ev_identity.CompanyIndex.from_config()

    def refs(self, names: Iterable[Any], *, country: str = "") -> list[dict[str, Any]]:
        refs: list[dict[str, Any]] = []
        seen: set[str] = set()
        for name in names:
            key = ev_identity.normalize_name(name)
            if not key or key in seen:
                continue
            seen.add(key)
            refs.append(resolve_company(self.index, name, country=country))
        return refs


# ---------------------------------------------------------------- HTML tables
class _TableParser(HTMLParser):
    """Minimal table extractor: text + link hrefs per cell, headers per table."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.tables: list[dict[str, Any]] = []
        self._table: dict[str, Any] | None = None
        self._row: list[dict[str, Any]] | None = None
        self._row_is_header = False
        self._cell: list[str] | None = None
        self._cell_hrefs: list[str] = []
        self._cell_is_header = False
        self._skip_depth = 0

    # -- parser callbacks
    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style"}:
            self._skip_depth += 1
            return
        if self._skip_depth:
            return
        if tag == "table":
            self._table = {"headers": [], "rows": []}
            return
        if self._table is None:
            return
        if tag == "tr":
            self._row = []
            self._row_is_header = False
            return
        if tag in {"td", "th"} and self._row is not None:
            self._cell = []
            self._cell_hrefs = []
            self._cell_is_header = tag == "th"
            return
        if tag == "a" and self._cell is not None:
            href = dict(attrs).get("href")
            if href:
                self._cell_hrefs.append(str(href))
            return
        if tag == "br" and self._cell is not None:
            self._cell.append(" ")
            return

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style"}:
            self._skip_depth = max(0, self._skip_depth - 1)
            return
        if self._skip_depth or self._table is None:
            return
        if tag in {"td", "th"} and self._cell is not None and self._row is not None:
            self._row.append(
                {
                    "text": re.sub(r"\s+", " ", "".join(self._cell)).strip(),
                    "hrefs": list(self._cell_hrefs),
                    "is_header": self._cell_is_header,
                }
            )
            self._cell = None
            return
        if tag == "tr" and self._row is not None:
            if self._row:
                if all(cell["is_header"] for cell in self._row) and not self._table["headers"]:
                    self._table["headers"] = [cell["text"] for cell in self._row]
                else:
                    self._table["rows"].append(self._row)
            self._row = None
            return
        if tag == "table":
            if self._table["rows"] or self._table["headers"]:
                self.tables.append(self._table)
            self._table = None

    def handle_data(self, data: str) -> None:
        if self._skip_depth or self._cell is None:
            return
        if data.strip():
            self._cell.append(data)

    # -- convenience
    def close(self) -> None:  # noqa: D401 - HTMLParser API
        super().close()
        if self._table is not None and (self._table["rows"] or self._table["headers"]):
            self.tables.append(self._table)
            self._table = None


def html_tables(html: str) -> list[dict[str, Any]]:
    """Parse every ``<table>`` into ``{headers, rows:[{cells:[{text,hrefs,is_header}]}]}``."""
    parser = _TableParser()
    parser.feed(html)
    parser.close()
    out: list[dict[str, Any]] = []
    for table in parser.tables:
        rows = []
        for raw_row in table["rows"]:
            rows.append(
                {
                    "cells": [cell["text"] for cell in raw_row],
                    "hrefs": [cell["hrefs"] for cell in raw_row],
                }
            )
        out.append({"headers": list(table["headers"]), "rows": rows})
    return out


def find_table(tables: Sequence[Mapping[str, Any]], required_headers: Iterable[str]) -> Mapping[str, Any] | None:
    """First table whose header list contains every required header (case-insensitive)."""
    wanted = [h.lower() for h in required_headers]
    for table in tables:
        headers = [str(h).lower() for h in table.get("headers", [])]
        if all(any(w in h for h in headers) for w in wanted):
            return table
    return None


def visible_text(html: str) -> str:
    """Tag-stripped, whitespace-collapsed page text (for bounded firm-token checks)."""
    text = re.sub(r"<script.*?</script>", " ", html, flags=re.S | re.I)
    text = re.sub(r"<style.*?</style>", " ", text, flags=re.S | re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def count_firm_tokens(html: str, *, index: ev_identity.CompanyIndex | None = None) -> dict[str, int]:
    """Count raw occurrences of the five firms' alias strings in a page's text.

    This is a **bounded keyword scan of one page**, deliberately not presented as
    identity resolution: the caller reports it as a text match only.
    """
    resolver = index or ev_identity.CompanyIndex.from_config()
    text = visible_text(html).upper()
    counts: dict[str, int] = {}
    for key in FIVE_FIRM_KEYS:
        aliases = ev_identity.TARGET_FIRM_ALIASES.get(key, ())
        total = 0
        for alias in aliases:
            needle = alias.upper()
            if len(needle) < 4:
                continue
            total += text.count(needle)
        counts[key] = total
    return counts


# --------------------------------------------------------------------- helper
def evidence_id_for(source_id: str, kind: str, source_record_id: str) -> str:
    return ev_schema.make_evidence_id(source_id, source_record_id, kind)


def make_postmarket_evidence(
    *,
    source_id: str,
    kind: str,
    source_record_id: str,
    source_url: str,
    normalized: Mapping[str, Any],
    raw: Mapping[str, Any],
    time: Mapping[str, Any],
    identifiers: Iterable[Mapping[str, Any]] = (),
    entity_refs: Iterable[Mapping[str, Any]] = (),
    source_name: str,
    licence_status: str,
    attribution: str,
    fetched_at: str,
) -> dict[str, Any]:
    """Thin wrapper that pins provenance defaults and then validates the record."""
    record = ev_schema.make_evidence(
        source_id=source_id,
        kind=kind,
        source_record_id=source_record_id,
        source_url=source_url,
        normalized=normalized,
        raw=raw,
        time=time,
        identifiers=identifiers,
        entity_refs=entity_refs,
        provenance={
            "source_name": source_name,
            "licence_status": licence_status,
            "redistribution": "allowed",
            "attribution": attribution,
            "evidence_reference": source_url,
            "source_time_quality": time.get("source_public_at_quality", ""),
        },
        fetched_at=fetched_at,
    )
    ev_schema.require_valid(record)
    return record


__all__ = [
    "FIVE_FIRM_KEYS",
    "FIVE_FIRM_LABELS",
    "PASSIVE_SURVEILLANCE_WARNING",
    "RECALL_WARNING",
    "SHORTAGE_WARNING",
    "IMPORT_ALERT_WARNING",
    "FirmResolver",
    "as_list",
    "clip",
    "clock_block",
    "confirmed_firm_key",
    "count_firm_tokens",
    "evidence_id_for",
    "find_table",
    "html_tables",
    "is_five_firm",
    "make_postmarket_evidence",
    "raw_block_from_object",
    "raw_block_from_page",
    "record_digest",
    "resolve_company",
    "visible_text",
    "year_of",
]
