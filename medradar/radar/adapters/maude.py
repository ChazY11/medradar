"""MAUDE adapter - FDA device adverse-event reports, narrative included.

Why this source matters more than a market estimate
---------------------------------------------------
MAUDE is the only public corpus in which a clinician or a manufacturer describes, in free
text, *how* a device failed: "when catheter was removed from the artery, after the third
pass, the balloon and spring tip were missing". 513,481 device event reports are currently
indexed through openFDA. Nobody sells this as an engineering corpus, and a design engineer
cannot get it from any market-intelligence platform.

Time semantics, stated because a safety record is the easiest place to invent freshness:

* ``date_of_event`` is when the event happened. It is the record's ``event_at``.
* ``date_received`` is when FDA received the report. It is the incremental bound, because
  that is the only date that is monotonic in the feed.
* ``date_added`` is when the record entered the MAUDE database. It is used as
  ``published_at`` - the closest thing to "a member of the public could have read this" -
  and it is labelled as a database-add date in ``extra``, not as a publication timestamp.
  This is a real advantage over 510(k)/PMA, which publish no such field at all.
* ``first_observed_at`` is still written by the ledger from the real clock, so a 1997 report
  first seen today is honestly both.
"""

from __future__ import annotations
from ..watermark import utc_today

from datetime import date, timedelta
from typing import Any, Mapping, Sequence

from ..adapter import CollectContext
from ..http import OPENFDA_MAX_LIMIT_WITHOUT_KEY, with_openfda_key
from ..records import (
    PRECISION_DATE,
    MappingResult,
    Page,
    RawRecord,
    Scope,
    normalize_moment,
)

DEFAULT_BASE = "https://api.fda.gov"
ENDPOINT = "/device/event.json"
#: openFDA refuses limit=1000 from an unidentified client (measured 2026-11-21:
#: 999 -> 200, 1000 -> 403 API_KEY_MISSING). One shared constant, one place to change.
PAGE_SIZE = OPENFDA_MAX_LIMIT_WITHOUT_KEY
WINDOW_DAYS = 30
#: A window scope is allowed to run long, but never unbounded: a first run over the whole
#: history is a backfill decision, not something a scheduled cycle should discover.
MAX_ROWS_PER_SCOPE = 40_000

#: The fields that constitute one event's content. The ledger hashes exactly these, so a
#: re-fetch of an unchanged report is idempotent and an FDA correction is a new version.
_FIELDS = (
    "mdr_report_key", "report_number", "event_type", "date_of_event", "date_received",
    "date_report", "date_added", "mdr_report_key", "manufacturer_name", "product_problems",
    "type_of_report", "report_source_code", "adverse_event_flag",
)

_TEXT_TYPES = (
    "Description of Event or Problem",
    "Manufacturer Narrative",
    "Additional Manufacturer Narrative",
)


class MaudeAdapter:
    source_id = "openfda_maude"
    label = "FDA device adverse events (MAUDE, openFDA)"
    adapter_version = "radar-maude-1"
    declared_cadence_hours = 24.0
    record_types = ("regulatory_record",)

    def __init__(
        self,
        taxonomy,
        *,
        base: str = DEFAULT_BASE,
        product_codes: Sequence[str] | None = None,
        page_size: int = PAGE_SIZE,
        max_rows: int = MAX_ROWS_PER_SCOPE,
    ) -> None:
        self.taxonomy = taxonomy
        self.base = base.rstrip("/")
        self.product_codes = tuple(product_codes or _codes_from(taxonomy))
        self.page_size = min(int(page_size), OPENFDA_MAX_LIMIT_WITHOUT_KEY)
        self.max_rows = int(max_rows)

    # --------------------------------------------------------------------- plan
    def plan(self, ctx: CollectContext) -> list[Scope]:
        # One window scope: the feed is ordered by date_received, so a single resumable
        # cursor is enough and a per-product-code sweep would multiply the same rows.
        return [Scope("window")]

    # -------------------------------------------------------------------- fetch
    def fetch_page(self, ctx: CollectContext, scope: Scope, cursor: str | None) -> Page:
        if scope.scope_id != "window":
            raise ValueError(f"unknown scope {scope.scope_id!r}")
        skip = int(cursor or 0)
        if skip >= self.max_rows:
            return Page(records=[], next_cursor=None, watermark=ctx.watermark,
                        note=f"row cap {self.max_rows} reached; resume in a later cycle")
        since = _window_start(ctx.watermark)
        end = utc_today().isoformat()
        clause = f"date_received:[{since} TO {end}]" if since else f"date_received:[* TO {end}]"
        if self.product_codes:
            codes = " OR ".join(f'device.device_report_product_code:"{code}"'
                                for code in self.product_codes)
            clause = f"({codes}) AND {clause}"
        data = ctx.fetcher.get_json(
            self.base + ENDPOINT,
            params=with_openfda_key({
                "search": clause, "limit": self.page_size, "skip": skip,
                "sort": "date_received:asc",
            }),
            allow_not_found=True,
        )
        rows = _results(data)
        total = _total(data)
        records = [record for row in rows if (record := self._record(row))]
        advance = skip + len(rows)
        next_cursor = str(advance) if len(rows) >= self.page_size and advance < total else None
        return Page(
            records=records,
            next_cursor=next_cursor,
            watermark=_max_received(rows) or ctx.watermark,
                watermark_inclusive=bool(_max_received(rows)),
            note=f"MAUDE date_received window since {since or 'unbounded'}: "
                 f"{len(rows)} of {total} rows",
        )

    # ------------------------------------------------------------------- record
    def _record(self, raw: Mapping[str, Any]) -> RawRecord | None:
        key = str(raw.get("mdr_report_key") or "").strip()
        if not key:
            return None
        devices = raw.get("device") or []
        first = devices[0] if isinstance(devices, list) and devices else {}
        if not isinstance(first, Mapping):
            first = {}
        brand = str(first.get("brand_name") or "").strip()
        generic = str(first.get("generic_name") or "").strip()
        manufacturer = (
            str(first.get("manufacturer_d_name") or "").strip()
            or str(raw.get("manufacturer_name") or "").strip()
        )
        report_number = str(raw.get("report_number") or "").strip()
        event = normalize_moment(raw.get("date_of_event"))
        received = normalize_moment(raw.get("date_received"))
        added = normalize_moment(raw.get("date_added"))
        event_type = str(raw.get("event_type") or "").strip()
        problems = [str(value) for value in (raw.get("product_problems") or []) if value]
        narratives, skipped = _narratives(raw)

        title = brand or generic or f"MDR {report_number or key}"
        if event_type:
            title = f"{event_type}: {title}"

        return RawRecord(
            source=self.source_id,
            source_record_id=f"mdr:{key}",
            official_identifier=report_number or key,
            record_type="regulatory_record",
            title=title[:400],
            url=(
                "https://www.accessdata.fda.gov/scripts/cdrh/cfdocs/cfMAUDE/detail.cfm"
                f"?mdrfoi__id={key}"
            ),
            event_at=event[0] or received[0],
            event_at_precision=event[1] if event[0] else received[1],
            published_at=added[0],
            published_at_precision=added[1] if added[0] else PRECISION_DATE,
            payload={
                "mdr_report_key": key,
                "report_number": report_number,
                "event_type": event_type,
                "date_of_event": raw.get("date_of_event"),
                "date_received": raw.get("date_received"),
                "date_added": raw.get("date_added"),
                "manufacturer": manufacturer,
                "brand_name": brand,
                "generic_name": generic,
                "model_number": first.get("model_number"),
                "catalog_number": first.get("catalog_number"),
                "baseline_510k": first.get("baseline_510_k__number"),
                "product_problems": problems,
            },
            text=" ".join(filter(None, [brand, generic, " ".join(problems), narratives]))[:8000],
            extra={
                "organization_hint": manufacturer or None,
                "organization_role": "adverse_event_manufacturer",
                "product_codes": [
                    str(device.get("device_report_product_code") or "").strip()
                    for device in devices
                    if isinstance(device, Mapping) and device.get("device_report_product_code")
                ],
                "product_hint": brand or generic or None,
                "product_identifier": first.get("model_number") or first.get("catalog_number"),
                "official_identifier": report_number or key,
                "published_at_status": "database_add_date" if added[0] else "not_published_by_source",
                "maude": {
                    "event_type": event_type,
                    "product_problems": problems,
                    "narrative_chars": len(narratives),
                    "narrative_blocks_kept": len(_TEXT_TYPES) - len(skipped),
                    "narrative_blocks_skipped": skipped,
                    "has_model_number": bool(first.get("model_number")),
                    "has_baseline_510k": bool(first.get("baseline_510_k__number")),
                },
            },
        )

    # ------------------------------------------------------------------ mapping
    def map_record(self, record: RawRecord, ctx: CollectContext) -> MappingResult:
        from ..classify import RuleMapper

        return RuleMapper(self.taxonomy).map(record)


def _narratives(raw: Mapping[str, Any]) -> tuple[str, list[str]]:
    """Join the narrative blocks, reporting which types were not present.

    The skipped list is recorded rather than dropped: "the manufacturer narrative is
    missing" is a fact about the report, and a reader comparing two events needs to know
    that one of them has no explanation in it.
    """
    blocks = raw.get("mdr_text") or []
    found: dict[str, list[str]] = {}
    for block in blocks:
        if not isinstance(block, Mapping):
            continue
        kind = str(block.get("text_type_code") or "").strip()
        text = " ".join(str(block.get("text") or "").split())
        if text and kind in _TEXT_TYPES:
            found.setdefault(kind, []).append(text)
    ordered = [" ".join(found.get(kind, [])) for kind in _TEXT_TYPES]
    skipped = [kind for kind in _TEXT_TYPES if kind not in found]
    return " ".join(part for part in ordered if part), skipped


def _codes_from(taxonomy) -> tuple[str, ...]:
    codes: list[str] = []
    for topic in taxonomy.topics:
        for code in topic.product_codes:
            if code not in codes:
                codes.append(code)
    return tuple(sorted(codes))


def _results(data: Any) -> list[dict[str, Any]]:
    if not isinstance(data, dict):
        return []
    rows = data.get("results") or []
    return [row for row in rows if isinstance(row, dict)]


def _total(data: Any) -> int:
    if not isinstance(data, dict):
        return 0
    return int(((data.get("meta") or {}).get("results") or {}).get("total") or 0)


def _max_received(rows: Sequence[Mapping[str, Any]]) -> str | None:
    dates = [str(row.get("date_received") or "").strip() for row in rows]
    dates = [value for value in dates if value]
    return max(dates) if dates else None


def _window_start(watermark: str | None) -> str | None:
    """Open the window ``WINDOW_DAYS`` before the watermark.

    The overlap is deliberate: a report can be entered late with an earlier ``date_received``
    than the newest row already seen, and a zero-overlap window would silently skip it.
    """
    if not watermark:
        return None
    moment = normalize_moment(watermark)[0]
    if not moment:
        return None
    try:
        anchor = date.fromisoformat(moment[:10])
    except ValueError:
        return None
    return (anchor - timedelta(days=WINDOW_DAYS)).isoformat()


__all__ = ["MaudeAdapter"]
