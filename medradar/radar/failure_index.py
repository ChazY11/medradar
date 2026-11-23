"""The third leg: does this device actually appear in the failure corpus?

Why the first attempt failed
----------------------------
The chain 510(k) document -> device -> DUNS was finished, and then it stopped: matching
``device.model_number`` exactly against MAUDE returned **0 events for all three samples**. That
looked like "these models never failed", which would have been a false and comfortable conclusion.

The real cause is that ``model_number`` in MAUDE is free-text and most manufacturers leave it
empty: measured on product code DQY, only **944 of 999** sampled reports carried one. Exact model
matching against a field that is usually blank is not a query, it is a coin flip.

What this module does instead
-----------------------------
Same pattern as the premarket bridge, which worked: **sweep once at a coarse key, then join
locally.**

* coarse key = product code. It is a controlled vocabulary, always present, and a product code
  with 42,296 events is cheap to walk at 999 rows a page.
* the sweep writes one row per (product code, normalised model, normalised brand), and from then
  on a device is matched locally with no further requests.
* model match is reported separately from brand match, because they mean different things: the
  same model number failing is this device; the same brand failing is this manufacturer's
  family, which is a weaker claim and must not be presented as the same one.

Storage
-------
A derived lookup index in ``reference.db``, beside ``assignee_alias``. It is explicitly **not**
the event ledger: ``radar.db`` remains the authoritative, bitemporal record. This table exists
only so that "has this device failed, and how often" is a local question.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable, Mapping, Sequence

EVENTS_ENDPOINT = "https://api.fda.gov/device/event.json"
#: MAUDE payloads are heavy. Measured: a 999-row page of ``device/event`` is about **9 MB**, and
#: one arrived truncated (5,209,171 of 8,852,529 bytes) which is what made the first sweep die.
#: 250 rows is ~2.2 MB, survives a flaky link, and costs only four times the request count on a
#: budget that has room for it (240 requests/minute anonymous).
PAGE_SIZE = 250
#: A product code with tens of thousands of events does not need all of them to answer "has this
#: model failed". Forty pages is 10,000 recent events, far past the point where a count stops
#: meaning anything different.
DEFAULT_MAX_PAGES_PER_CODE = 40
DEFAULT_SINCE = "2015-01-01"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS maude_failure_index (
    product_code  TEXT NOT NULL,
    model_norm    TEXT NOT NULL,
    brand_norm    TEXT,
    event_type    TEXT,
    date_received TEXT,
    PRIMARY KEY (product_code, model_norm, event_type, date_received)
);
CREATE INDEX IF NOT EXISTS idx_failure_model ON maude_failure_index(model_norm);
CREATE INDEX IF NOT EXISTS idx_failure_brand ON maude_failure_index(brand_norm);
"""


def ensure_schema(reference) -> None:
    reference.conn.executescript(_SCHEMA)
    reference.conn.commit()


def normalise_model(text: str) -> str:
    """Uppercase alphanumerics only.

    Models arrive as ``EPD6AB252``, ``GalaxyStar-WR-14-B4``, ``11504D``, ``Rev C``. A human would
    call the first and third identical whether or not the label prints a hyphen, so separators go.
    Deliberately not fuzzy: a near-miss on a model number is a wrong device.
    """
    return re.sub(r"[^A-Z0-9]+", "", str(text or "").upper())


def normalise_brand(text: str) -> str:
    return re.sub(r"[^A-Z0-9]+", " ", str(text or "").upper()).strip()


@dataclass
class FailureIndexStats:
    product_codes: int = 0
    pages: int = 0
    events_seen: int = 0
    rows_written: int = 0
    rows_skipped: int = 0
    per_code: dict[str, int] = field(default_factory=dict)
    stop_reason: str | None = None

    def summary(self) -> dict[str, Any]:
        return {
            "product_codes": self.product_codes,
            "pages": self.pages,
            "events_seen": self.events_seen,
            "rows_written": self.rows_written,
            "rows_skipped": self.rows_skipped,
            "per_code": self.per_code,
            "stop_reason": self.stop_reason,
        }


def build_failure_index(fetcher, reference, product_codes: Sequence[str], *,
                        since: str = DEFAULT_SINCE,
                        max_pages_per_code: int = DEFAULT_MAX_PAGES_PER_CODE,
                        page_size: int = PAGE_SIZE,
                        progress: Callable[[FailureIndexStats], None] | None = None
                        ) -> FailureIndexStats:
    """Walk the failure corpus once per product code and record what can be joined locally."""
    from .http import OPENFDA_MAX_SKIP, with_openfda_key

    ensure_schema(reference)
    stats = FailureIndexStats()
    limit = min(int(page_size), PAGE_SIZE)
    cursor = reference.conn.cursor()

    for code in product_codes:
        stats.product_codes += 1
        search = (f'device.device_report_product_code:"{code}" '
                  f"AND date_received:[{since} TO 9999-12-31]")
        written_before = stats.rows_written
        skip = 0
        pages_for_code = 0
        while pages_for_code < max_pages_per_code:
            if skip > OPENFDA_MAX_SKIP:
                # Deep paging is capped; the code already has more history than the index needs.
                break
            params = with_openfda_key({"search": search, "limit": limit, "skip": skip,
                                       "sort": "date_received:desc"})
            data = fetcher.get_json(EVENTS_ENDPOINT, params=params, allow_not_found=True)
            if not data:
                break
            rows = [row for row in (data.get("results") or []) if isinstance(row, dict)]
            if not rows:
                break
            stats.events_seen += len(rows)
            stats.pages += 1
            pages_for_code += 1
            for event in rows:
                event_type = str(event.get("event_type") or "").strip() or None
                received = str(event.get("date_received") or "").strip()[:10] or None
                for device in (event.get("device") or []):
                    if not isinstance(device, Mapping):
                        continue
                    model = normalise_model(device.get("model_number"))
                    if not model:
                        # No model number: nothing can be joined to it later, so it is counted
                        # rather than stored. This is the field that made exact matching useless.
                        stats.rows_skipped += 1
                        continue
                    brand = normalise_brand(device.get("brand_name")) or None
                    try:
                        cursor.execute(
                            "INSERT OR IGNORE INTO maude_failure_index "
                            "(product_code, model_norm, brand_norm, event_type, date_received) "
                            "VALUES (?,?,?,?,?)",
                            (str(code), model, brand, event_type, received),
                        )
                        stats.rows_written += 1
                    except Exception:  # noqa: BLE001
                        stats.rows_skipped += 1
            reference.conn.commit()
            skip += len(rows)
            if len(rows) < limit:
                break
        stats.per_code[str(code)] = stats.rows_written - written_before
        if progress:
            progress(stats)
        if pages_for_code >= max_pages_per_code:
            stats.stop_reason = f"page cap reached for at least one code ({max_pages_per_code})"
    reference.conn.commit()
    return stats


def failures_for_model(reference, model: str, *, product_codes: Sequence[str] | None = None
                       ) -> dict[str, Any]:
    """How often this exact model appears, split by event type."""
    ensure_schema(reference)
    key = normalise_model(model)
    if not key:
        return {"model": None, "events": 0, "by_type": {}, "method": "none"}
    sql = ("SELECT event_type, COUNT(*) FROM maude_failure_index WHERE model_norm = ?")
    args: list[Any] = [key]
    if product_codes:
        sql += " AND product_code IN (" + ",".join("?" * len(product_codes)) + ")"
        args.extend(str(code) for code in product_codes)
    sql += " GROUP BY event_type"
    by_type = {str(row[0] or "unknown"): int(row[1])
               for row in reference.conn.execute(sql, args)}
    return {"model": key, "events": sum(by_type.values()), "by_type": by_type,
            "method": "model_exact"}


def failures_for_brand(reference, brand: str, *,
                       product_codes: Sequence[str] | None = None) -> dict[str, Any]:
    """A weaker claim, kept separate: the manufacturer's family, not this device."""
    ensure_schema(reference)
    key = normalise_brand(brand)
    if not key:
        return {"brand": None, "events": 0, "by_type": {}, "method": "none"}
    sql = "SELECT event_type, COUNT(*) FROM maude_failure_index WHERE brand_norm = ?"
    args: list[Any] = [key]
    if product_codes:
        sql += " AND product_code IN (" + ",".join("?" * len(product_codes)) + ")"
        args.extend(str(code) for code in product_codes)
    sql += " GROUP BY event_type"
    by_type = {str(row[0] or "unknown"): int(row[1])
               for row in reference.conn.execute(sql, args)}
    return {"brand": key, "events": sum(by_type.values()), "by_type": by_type,
            "method": "brand_exact", "weaker_than_model": True}


def index_summary(reference) -> dict[str, Any]:
    ensure_schema(reference)

    def scalar(sql: str) -> int:
        row = reference.conn.execute(sql).fetchone()
        return int(row[0]) if row and row[0] is not None else 0

    return {
        "rows": scalar("SELECT COUNT(*) FROM maude_failure_index"),
        "product_codes": scalar("SELECT COUNT(DISTINCT product_code) FROM maude_failure_index"),
        "distinct_models": scalar("SELECT COUNT(DISTINCT model_norm) FROM maude_failure_index"),
        "distinct_brands": scalar(
            "SELECT COUNT(DISTINCT brand_norm) FROM maude_failure_index "
            "WHERE brand_norm IS NOT NULL"),
    }


__all__ = [
    "DEFAULT_MAX_PAGES_PER_CODE",
    "DEFAULT_SINCE",
    "FailureIndexStats",
    "build_failure_index",
    "failures_for_brand",
    "failures_for_model",
    "index_summary",
    "normalise_brand",
    "normalise_model",
]
