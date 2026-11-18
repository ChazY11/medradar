"""openFDA device-recall adapter - the safety-event channel of the monitoring scope.

Why this is a separate adapter and not a third pipeline
------------------------------------------------------
It implements the existing :class:`medradar.radar.adapter.SourceAdapter` contract and reuses
the existing ledger, mapping, assessment, watermarks, cursors, retries and health reporting.
The only things it adds are the read path (the openFDA recall endpoint that
``medradar.data_pipeline.model.SOURCES`` already declares) and the record shape. There is no
recall-specific store, no second company registry and no second relevance engine.

Row identity versus event identity
---------------------------------
The observation is one recalled *product record* (product_res_number), because that is what
the source publishes and what the ledger can re-identify idempotently. The FDA recall *event*
(res_event_number) is declared as an official identifier, so "how many recalls" is a GROUP BY
over the existing identifier table rather than a count of database rows. Measured on the 2026
monitoring recalls: 42 rows, 19 events.

Time semantics
--------------
* event_date_initiated  -> event_at        (when the firm began the action)
* event_date_posted     -> published_at    (when FDA published the record)
* event_date_terminated -> payload only    (the source state, never a publication date)
* meta.last_updated     -> an endpoint-level version marker, used only to decide when a full
                           inventory sweep is due. It is never a record timestamp.
* first_observed_at     -> written by the ledger from the real clock at ingest, so a 2026-07
                           recall imported today is honestly both old and newly observed.

Collection scopes
-----------------
``code:<CODE>``  the complete recall history of one monitored product code. Precise (it is
                FDA's own classification) and it is what makes the reference coverage
                reproducible.
``window``       every recall posted in the incremental window, regardless of product code.
                This is what finds a patient monitor that FDA filed under an unexpected code;
                the screen in ``medradar.radar.recall`` decides what it is.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Mapping, Sequence

from ...data_pipeline.model import SOURCES
from ...data_pipeline.openfda import build_url
from ..adapter import CollectContext
from ..recall import (
    RECALL_EVENT_IDENTIFIER,
    RECALL_PAYLOAD_FIELDS,
    RECALL_PRODUCT_IDENTIFIER,
    recall_event_id,
    recall_product_id,
    screen_recall,
    monitoring_codes,
)
from ..records import MappingResult, PRECISION_DATE, Page, RawRecord, Scope, normalize_moment

DEFAULT_BASE = "https://api.fda.gov"
PAGE_SIZE = 1000
WINDOW_OVERLAP_DAYS = 30
#: The earliest publication date a first (unrequested) incremental run looks back to.
#: A deliberate historical import uses --backfill-reason, which widens this to BACKFILL_START.
RECENT_DAYS = 90
BACKFILL_START = "2025-01-01"
MAX_SKIP = 24000


class OpenFDARecallAdapter:
    source_id = "openfda_recall"
    label = "FDA device recalls (openFDA)"
    adapter_version = "radar-openfda-recall-1"
    declared_cadence_hours = 24.0
    record_types = ("regulatory_record",)

    def __init__(
        self,
        taxonomy,
        *,
        base: str = DEFAULT_BASE,
        product_codes: Sequence[str] | None = None,
        page_size: int = PAGE_SIZE,
        inventory: bool = True,
    ) -> None:
        self.taxonomy = taxonomy
        self.base = base.rstrip("/")
        #: The code list is the committed taxonomy, never a second register.
        self.product_codes = tuple(
            product_codes if product_codes is not None else sorted(monitoring_codes(taxonomy))
        )
        self.page_size = int(page_size)
        self.inventory = bool(inventory)

    # --------------------------------------------------------------------- plan
    def plan(self, ctx: CollectContext) -> list[Scope]:
        state = _state(ctx)
        official_version = state.get("official_version")
        swept_version = state.get("swept_version")
        completed = {str(code) for code in (state.get("completed_codes") or [])}
        if official_version and swept_version != official_version:
            # A new official endpoint version invalidates a previous partial inventory.
            completed = set()
        pending = [code for code in self.product_codes if code not in completed]
        scopes = [Scope("version")]
        if self.inventory and pending:
            scopes.extend(Scope("code:" + code) for code in pending)
            ctx.emit(
                "[openfda_recall] " + str(len(pending)) + " of " + str(len(self.product_codes))
                + " monitoring product codes still need an inventory pass"
            )
        # The all-code incremental window always runs: it is the only scope that can find a
        # monitoring device filed under a product code the taxonomy does not list.
        scopes.append(Scope("window"))
        return scopes

    # -------------------------------------------------------------------- fetch
    def fetch_page(self, ctx: CollectContext, scope: Scope, cursor: str | None) -> Page:
        if scope.scope_id == "version":
            return self._version_page(ctx)
        if scope.scope_id == "window":
            return self._window_page(ctx, cursor)
        if scope.scope_id.startswith("code:"):
            return self._code_page(ctx, scope.scope_id.split(":", 1)[1], cursor)
        raise ValueError("unknown scope " + repr(scope.scope_id))

    def _version_page(self, ctx: CollectContext) -> Page:
        data = ctx.fetcher.get_json(
            build_url(self.base, SOURCES["openfda_recall"].endpoint, {"limit": 1})
        )
        meta = (data or {}).get("meta") or {}
        version = str(meta.get("last_updated") or "").strip() or None
        state = _state(ctx)
        state["official_version"] = version
        ctx.adapter_state["openfda_recall"] = state
        return Page(records=[], next_cursor=None, watermark=None,
                    note="official recall endpoint version: " + str(version))

    def _code_page(self, ctx: CollectContext, code: str, cursor: str | None) -> Page:
        skip = int(cursor or 0)
        params = {
            "search": 'product_code:"' + code + '"',
            "limit": self.page_size,
            "skip": skip,
            "sort": "event_date_posted:asc",
        }
        # openFDA answers 404 when a search has no matches. For a product code with no recall
        # history that is a legitimate empty inventory, not a source failure: treating it as one
        # marked the scope failed and left the code permanently un-inventoried (measured: CAP,
        # DRW, FLA, GLY, QYW and one more on the first real run).
        data = ctx.fetcher.get_json(
            build_url(self.base, SOURCES["openfda_recall"].endpoint, params),
            allow_not_found=True,
        )
        rows = _results(data)
        total = _total(data)
        records = [record for row in rows if (record := self._record(row))]
        state = _state(ctx)
        version = str(((data or {}).get("meta") or {}).get("last_updated") or "").strip()
        if version:
            state["observed_version"] = version
        next_cursor = _next_cursor(skip, len(rows), total, self.page_size)
        if next_cursor is None:
            completed = {str(value) for value in (state.get("completed_codes") or [])}
            completed.add(code)
            state["completed_codes"] = sorted(completed)
            if all(value in completed for value in self.product_codes):
                state["swept_version"] = state.get("official_version") or state.get("observed_version")
                state["last_full_sweep_at"] = date.today().isoformat()
        ctx.adapter_state["openfda_recall"] = state
        return Page(records=records, next_cursor=next_cursor, watermark=_max_posted(rows),
                    note="product_code " + code + ": " + str(len(rows)) + " of " + str(total) + " rows")

    def _window_page(self, ctx: CollectContext, cursor: str | None) -> Page:
        skip = int(cursor or 0)
        since = _window_start(ctx.watermark, backfill=_is_backfill(ctx))
        today = date.today().isoformat()
        params = {
            "search": "event_date_posted:[" + since + " TO " + today + "]",
            "limit": self.page_size,
            "skip": skip,
            "sort": "event_date_posted:asc",
        }
        data = ctx.fetcher.get_json(
            build_url(self.base, SOURCES["openfda_recall"].endpoint, params),
            allow_not_found=True,
        )
        rows = _results(data)
        total = _total(data)
        records = [record for row in rows if (record := self._record(row))]
        next_cursor = _next_cursor(skip, len(rows), total, self.page_size)
        return Page(records=records, next_cursor=next_cursor, watermark=_max_posted(rows),
                    note="all-code window since " + since + ": " + str(len(rows)) + " of "
                         + str(total) + " rows")

    # ------------------------------------------------------------------- record
    def _record(self, raw: Mapping[str, Any]) -> RawRecord | None:
        product_res = recall_product_id(raw)
        cfres = str(raw.get("cfres_id") or "").strip()
        identity = product_res or (("CFRES-" + cfres) if cfres else "")
        if not identity:
            # A row with neither an official recall number nor a cfres id cannot be
            # re-identified, so recording it would create a duplicate on every run.
            return None
        payload = {field: raw.get(field) for field in RECALL_PAYLOAD_FIELDS}
        # The endpoint states the official FDA device classification for the product code. It is
        # a small, stable projection of the nested openfda object; the registration and k_number
        # arrays are deliberately not stored (they are bulk identifiers, not this record).
        official = raw.get("openfda")
        if isinstance(official, Mapping):
            payload["openfda_device"] = {
                "device_name": official.get("device_name"),
                "device_class": official.get("device_class"),
                "medical_specialty_description": official.get("medical_specialty_description"),
                "regulation_number": official.get("regulation_number"),
            }
        description = str(raw.get("product_description") or "").strip() or "(unnamed product)"
        initiated = normalize_moment(raw.get("event_date_initiated"))
        posted = normalize_moment(raw.get("event_date_posted"))
        spec = SOURCES["openfda_recall"]
        event_id = recall_event_id(raw)
        identifiers = [(RECALL_PRODUCT_IDENTIFIER, identity)]
        if event_id:
            identifiers.append((RECALL_EVENT_IDENTIFIER, event_id))
        code = str(raw.get("product_code") or "").strip().upper()
        firm = str(raw.get("recalling_firm") or "").strip() or None
        return RawRecord(
            source=self.source_id,
            source_record_id="recall:" + identity,
            official_identifier=identity,
            record_type="regulatory_record",
            title=description,
            url=spec.official_url(identity, dict(raw)),
            event_at=initiated[0],
            event_at_precision=initiated[1],
            published_at=posted[0],
            published_at_precision=posted[1],
            source_updated_at=None,
            source_updated_at_precision="unknown",
            payload=payload,
            text=" ".join(filter(None, [
                description,
                str(raw.get("reason_for_recall") or ""),
                str(raw.get("action") or ""),
            ])),
            extra={
                # The recalling firm is the regulated firm of record for this device. It plays
                # the same identity role as a 510(k) applicant, so the existing role
                # vocabulary is reused instead of adding a company registry.
                "organization_hint": firm,
                "organization_role": "regulatory_applicant",
                "product_codes": [code] if code else [],
                "product_hint": description,
                "product_identifier": identity,
                "official_identifier": identity,
                "identifiers": identifiers,
                "published_at_status": "event_date_posted_by_source",
                "recall": {
                    "event_id": event_id,
                    "product_res_number": product_res,
                    "recall_status": raw.get("recall_status"),
                    "root_cause": raw.get("root_cause_description"),
                    "k_numbers": raw.get("k_numbers"),
                },
            },
        )

    # ------------------------------------------------------------------ mapping
    def map_record(self, record: RawRecord, ctx: CollectContext) -> MappingResult:
        from ..classify import RuleMapper

        return RuleMapper(self.taxonomy).map(record)


def _results(data: Any) -> list[dict[str, Any]]:
    if not isinstance(data, dict):
        return []
    rows = data.get("results") or []
    return [row for row in rows if isinstance(row, dict)]


def _total(data: Any) -> int:
    if not isinstance(data, dict):
        return 0
    return int(((data.get("meta") or {}).get("results") or {}).get("total") or 0)


def _max_posted(rows: Sequence[Mapping[str, Any]]) -> str | None:
    dates = [str(row.get("event_date_posted") or "").strip() for row in rows]
    dates = [value for value in dates if value]
    return max(dates) if dates else None


def _next_cursor(skip: int, seen: int, total: int, page_size: int) -> str | None:
    following = skip + seen
    if seen < page_size or following >= total or following >= MAX_SKIP:
        return None
    return str(following)


def _is_backfill(ctx: CollectContext) -> bool:
    return str(getattr(ctx, "origin", "") or "") == "BACKFILLED" or str(
        getattr(ctx, "phase", "") or ""
    ) == "HISTORICAL_BACKFILL"


def _window_start(watermark: str | None, *, backfill: bool) -> str:
    """The lower bound of the all-code window.

    A watermark means "published up to here"; the overlap absorbs late-posted records. With no
    usable watermark the window depends on intent: a deliberate historical import starts at
    BACKFILL_START, an ordinary first run only looks back RECENT_DAYS. The distinction is what
    keeps a backfill from being reported as newly discovered news.
    """
    today = date.today()
    if watermark:
        normalized = normalize_moment(watermark)[0]
        if normalized:
            try:
                anchor = date.fromisoformat(str(normalized)[:10])
                start = anchor - timedelta(days=WINDOW_OVERLAP_DAYS)
                return min(start, today).isoformat()
            except ValueError:
                pass
    if backfill:
        return BACKFILL_START
    return (today - timedelta(days=RECENT_DAYS)).isoformat()


def _state(ctx: CollectContext) -> dict[str, Any]:
    return dict(ctx.adapter_state.get("openfda_recall") or (ctx.cursor or {}).get("openfda_recall") or {})
