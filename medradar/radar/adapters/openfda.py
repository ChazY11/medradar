"""openFDA device adapter - the existing FDA lane, reused rather than rebuilt.

This adapter does **not** re-implement the FDA infrastructure. It reuses:

* ``medradar.data_pipeline.openfda.build_url`` - the exact URL construction the DATA-001
  pipeline uses;
* ``medradar.data_pipeline.model.SOURCES`` - the official endpoint, display name and
  ``official_url`` builder for 510(k) and PMA records;
* the openFDA record identifiers (K-number, PMA number) as the cross-source join key.

What it adds for RADAR-001 is a **narrower, incremental scope**: instead of sweeping all
176k 510(k) rows, it queries the 21 ICU-monitoring product codes (about 5.7k records), and
it re-checks only a recent window unless the official endpoint version changed.

Time semantics, stated because getting this wrong is how a system invents freshness:

* ``decision_date`` is the regulatory decision date published by FDA. It is the record's
  ``event_at``.
* openFDA publishes **no per-record publication timestamp** for 510(k) or PMA rows. So
  ``published_at`` is absent, and the source says so through
  ``extra["published_at_status"] = "not_published_by_source"`` rather than borrowing the
  decision date.
* ``meta.last_updated`` is an **endpoint-level** version marker. It is used as a trigger
  for a full reconciliation sweep, and is never presented as a record's update time.
* ``first_observed_at`` is written by the ledger from the real clock at ingest, so a record
  that FDA published in 2016 and MedRadar first saw today is honestly both.
"""

from __future__ import annotations
from ..watermark import utc_today

from datetime import date, timedelta
from typing import Any, Mapping, Sequence

from ...data_pipeline.model import SOURCES
from ...data_pipeline.openfda import build_url
from ..adapter import CollectContext
from ..http import OPENFDA_MAX_LIMIT_WITHOUT_KEY, with_openfda_key
from ..records import (
    MappingResult,
    Page,
    PRECISION_DATE,
    RawRecord,
    Scope,
    normalize_moment,
)

DEFAULT_BASE = "https://api.fda.gov"
#: openFDA refuses limit=1000 from an unidentified client (measured 2026-11-21:
#: 999 -> 200, 1000 -> 403 API_KEY_MISSING), so the shipped page size is 999.
PAGE_SIZE = OPENFDA_MAX_LIMIT_WITHOUT_KEY
WINDOW_DAYS = 45
#: Record fields that constitute the *content* of a 510(k) row. The hash covers exactly
#: these, so a re-fetch of unchanged data is idempotent and a real correction is a version.
_FIELDS_510K = (
    "k_number", "applicant", "device_name", "product_code", "decision_date", "decision_code",
    "decision_description", "clearance_type", "advisory_committee",
    "advisory_committee_description", "date_received", "statement_or_summary",
)
_FIELDS_PMA = (
    "pma_number", "supplement_number", "supplement_type", "applicant", "trade_name",
    "product_code", "decision_date", "decision_code", "decision_description", "pma_type",
    "ao_statement", "advisory_committee", "advisory_committee_description",
)


class OpenFDAAdapter:
    source_id = "openfda_device"
    label = "FDA device clearances (openFDA)"
    adapter_version = "radar-openfda-1"
    declared_cadence_hours = 24.0
    record_types = ("regulatory_record",)

    def __init__(
        self,
        taxonomy,
        *,
        base: str = DEFAULT_BASE,
        product_codes: Sequence[str] | None = None,
        include_pma: bool = True,
        page_size: int = PAGE_SIZE,
    ) -> None:
        self.taxonomy = taxonomy
        self.base = base.rstrip("/")
        self.product_codes = tuple(product_codes or _codes_from(taxonomy))
        self.include_pma = include_pma
        self.page_size = min(int(page_size), OPENFDA_MAX_LIMIT_WITHOUT_KEY)

    # --------------------------------------------------------------------- plan
    def plan(self, ctx: CollectContext) -> list[Scope]:
        state = dict((ctx.cursor or {}).get("openfda") or {})
        official_version = state.get("official_version")
        swept_version = state.get("swept_version")
        completed = {str(code) for code in (state.get("completed_codes") or [])}
        if official_version and swept_version != official_version:
            # A new official version invalidates a previous partial sweep.
            completed = set()
        pending = [code for code in self.product_codes if code not in completed]
        scopes = [Scope("version")]
        if pending:
            scopes.extend(Scope(f"code:{code}") for code in pending)
            if self.include_pma and not state.get("pma_swept"):
                scopes.append(Scope("pma"))
            ctx.emit(
                f"[{self.source_id}] {len(pending)} of {len(self.product_codes)} product codes still "
                f"need a reconciliation at official version {official_version or 'unknown'}"
            )
        else:
            scopes.append(Scope("window"))
        return scopes

    # -------------------------------------------------------------------- fetch
    def fetch_page(self, ctx: CollectContext, scope: Scope, cursor: str | None) -> Page:
        if scope.scope_id == "version":
            return self._version_page(ctx)
        if scope.scope_id == "window":
            return self._window_page(ctx, cursor)
        if scope.scope_id == "pma":
            return self._pma_page(ctx, cursor)
        if scope.scope_id.startswith("code:"):
            return self._code_page(ctx, scope.scope_id.split(":", 1)[1], cursor)
        raise ValueError(f"unknown scope {scope.scope_id!r}")

    def _version_page(self, ctx: CollectContext) -> Page:
        data = ctx.fetcher.get_json(
            build_url(self.base, SOURCES["openfda_510k"].endpoint,
                      with_openfda_key({"limit": 1}))
        )
        meta = (data or {}).get("meta") or {}
        version = str(meta.get("last_updated") or "").strip() or None
        state = dict((ctx.cursor or {}).get("openfda") or {})
        state["official_version"] = version
        ctx.adapter_state["openfda"] = state
        return Page(records=[], next_cursor=None, watermark=version,
                    note=f"official 510(k) endpoint version: {version}")

    def _code_page(self, ctx: CollectContext, code: str, cursor: str | None) -> Page:
        skip = int(cursor or 0)
        params = {
            "search": f'product_code:"{code}"',
            "limit": self.page_size,
            "skip": skip,
            "sort": "decision_date:asc",
        }
        data = ctx.fetcher.get_json(
            build_url(self.base, SOURCES["openfda_510k"].endpoint, with_openfda_key(params))
        )
        rows = _results(data)
        records = [self._record_510k(row) for row in rows]
        total = _total(data)
        state = _state(ctx)
        version = str(((data or {}).get("meta") or {}).get("last_updated") or "").strip()
        if version:
            state["observed_version"] = version
        ctx.adapter_state["openfda"] = state
        next_cursor = str(skip + len(rows)) if len(rows) >= self.page_size and skip + len(rows) < total else None
        watermark = _max_date(rows)
        state = _state(ctx)
        if next_cursor is None:
            completed = {str(value) for value in (state.get("completed_codes") or [])}
            completed.add(code)
            state["completed_codes"] = sorted(completed)
            all_done = all(value in completed for value in self.product_codes) and (
                state.get("pma_swept") or not self.include_pma
            )
            if all_done:
                state["swept_version"] = state.get("official_version") or state.get("observed_version")
                state["last_full_sweep_at"] = utc_today().isoformat()
        ctx.adapter_state["openfda"] = state
        return Page(records=records, next_cursor=next_cursor, watermark=watermark, watermark_inclusive=True,
                    note=f"product_code {code}: {len(rows)} of {total} rows")

    def _window_page(self, ctx: CollectContext, cursor: str | None) -> Page:
        skip = int(cursor or 0)
        since = _window_start(ctx.watermark)
        code_clause = " OR ".join(f'product_code:"{code}"' for code in self.product_codes)
        search = f"({code_clause})"
        if since:
            search += f" AND decision_date:[{since} TO {(utc_today() + timedelta(days=1)).isoformat()}]"
        params = {"search": search, "limit": self.page_size, "skip": skip,
                  "sort": "decision_date:asc"}
        data = ctx.fetcher.get_json(
            build_url(self.base, SOURCES["openfda_510k"].endpoint, with_openfda_key(params))
        )
        rows = _results(data)
        total = _total(data)
        records = [self._record_510k(row) for row in rows]
        next_cursor = str(skip + len(rows)) if len(rows) >= self.page_size and skip + len(rows) < total else None
        return Page(records=records, next_cursor=next_cursor, watermark=_max_date(rows), watermark_inclusive=True,
                    note=f"incremental window since {since or 'unbounded'}: {len(rows)} of {total} rows")

    def _pma_page(self, ctx: CollectContext, cursor: str | None) -> Page:
        skip = int(cursor or 0)
        code_clause = " OR ".join(f'product_code:"{code}"' for code in self.product_codes)
        params = {
            "search": f"({code_clause})",
            "limit": self.page_size,
            "skip": skip,
            "sort": "decision_date:asc",
        }
        data = ctx.fetcher.get_json(
            build_url(self.base, SOURCES["openfda_pma"].endpoint, with_openfda_key(params)),
            allow_not_found=True,
        )
        rows = _results(data)
        total = _total(data)
        records = [record for row in rows if (record := self._record_pma(row))]
        next_cursor = str(skip + len(rows)) if len(rows) >= self.page_size and skip + len(rows) < total else None
        state = _state(ctx)
        if next_cursor is None:
            state["pma_swept"] = True
            completed = {str(value) for value in (state.get("completed_codes") or [])}
            if all(value in completed for value in self.product_codes):
                state["swept_version"] = state.get("official_version") or state.get("observed_version")
                state["last_full_sweep_at"] = utc_today().isoformat()
            ctx.adapter_state["openfda"] = state
        return Page(records=records, next_cursor=next_cursor, watermark=_max_date(rows), watermark_inclusive=True,
                    note=f"PMA sweep: {len(rows)} of {total} rows")

    # ------------------------------------------------------------------- record
    def _record_510k(self, raw: Mapping[str, Any]) -> RawRecord:
        payload = {field: raw.get(field) for field in _FIELDS_510K}
        k_number = str(raw.get("k_number") or "").strip()
        device_name = str(raw.get("device_name") or "").strip() or "(unnamed device)"
        decision = normalize_moment(raw.get("decision_date"))
        spec = SOURCES["openfda_510k"]
        return RawRecord(
            source=self.source_id,
            source_record_id=f"510k:{k_number}",
            official_identifier=k_number,
            record_type="regulatory_record",
            title=device_name,
            url=spec.official_url(k_number, dict(raw)),
            event_at=decision[0],
            event_at_precision=decision[1],
            published_at=None,
            source_updated_at_precision="unknown",
            payload=payload,
            text=" ".join(filter(None, [
                device_name,
                str(raw.get("statement_or_summary") or ""),
                str(raw.get("advisory_committee_description") or ""),
            ])),
            extra={
                "organization_hint": str(raw.get("applicant") or "").strip() or None,
                "organization_role": "regulatory_applicant",
                "product_codes": [str(raw.get("product_code") or "").strip()] if raw.get("product_code") else [],
                "product_hint": device_name,
                "product_identifier": k_number,
                "official_identifier": k_number,
                "published_at_status": "not_published_by_source",
                "fda": {
                    "decision_code": raw.get("decision_code"),
                    "decision_description": raw.get("decision_description"),
                    "clearance_type": raw.get("clearance_type"),
                    "advisory_committee": raw.get("advisory_committee"),
                },
            },
        )

    def _record_pma(self, raw: Mapping[str, Any]) -> RawRecord | None:
        pma_number = str(raw.get("pma_number") or "").strip()
        if not pma_number:
            return None
        supplement = str(raw.get("supplement_number") or "").strip()
        payload = {field: raw.get(field) for field in _FIELDS_PMA}
        device_name = (
            str(raw.get("trade_name") or "").strip()
            or str(raw.get("device_name") or "").strip()
            or "(unnamed device)"
        )
        decision = normalize_moment(raw.get("decision_date"))
        supplement_label = supplement.upper().lstrip("S") if supplement else ""
        if supplement_label and supplement.upper() not in ("0", "-", "S000"):
            identity = f"{pma_number}:S{supplement_label}"
        else:
            identity = pma_number
        spec = SOURCES["openfda_pma"]
        return RawRecord(
            source=self.source_id,
            source_record_id=f"pma:{identity}",
            official_identifier=identity,
            record_type="regulatory_record",
            title=device_name,
            url=spec.official_url(identity, dict(raw)),
            event_at=decision[0],
            event_at_precision=decision[1],
            published_at=None,
            payload=payload,
            text=" ".join(filter(None, [device_name, str(raw.get("ao_statement") or "")])),
            extra={
                "organization_hint": str(raw.get("applicant") or "").strip() or None,
                "organization_role": "regulatory_applicant",
                "product_codes": [str(raw.get("product_code") or "").strip()] if raw.get("product_code") else [],
                "product_hint": device_name,
                "product_identifier": identity,
                "official_identifier": identity,
                "published_at_status": "not_published_by_source",
                "fda": {"pma_number": pma_number, "supplement_number": supplement,
                        "decision_code": raw.get("decision_code")},
            },
        )

    # ------------------------------------------------------------------ mapping
    def map_record(self, record: RawRecord, ctx: CollectContext) -> MappingResult:
        from ..classify import RuleMapper

        return RuleMapper(self.taxonomy).map(record)


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


def _max_date(rows: Sequence[Mapping[str, Any]]) -> str | None:
    dates = [str(row.get("decision_date") or "").strip() for row in rows]
    dates = [value for value in dates if value]
    return max(dates) if dates else None


def _window_start(watermark: str | None) -> str | None:
    """Start the incremental window ``WINDOW_DAYS`` before the watermark.

    A short overlap is deliberate: a record whose decision date is in the past can appear in
    the endpoint later, and a zero-overlap window would silently skip it.
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


def scope_finished(next_cursor: str | None) -> bool:
    return next_cursor is None


def _state(ctx: CollectContext) -> dict[str, Any]:
    # In-run state (``adapter_state``) wins over the state loaded at the start of the run.
    return dict(ctx.adapter_state.get("openfda") or (ctx.cursor or {}).get("openfda") or {})
