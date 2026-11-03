"""Unified incremental collection engine for the Live Observatory.

Adapters stay declarative (plan scopes → fetch a page → map one record); this
engine owns everything that must behave identically for every source:

* pagination + cursor checkpointing after every page (so a crash resumes, not restarts);
* polite rate limiting, retries and backoff (delegated to :mod:`medradar.http`);
* request budgets and page ceilings (a cheap laptop can run this unattended);
* idempotent writes through the ledger (re-running a page changes nothing);
* structure-change detection (a silently reshaped API becomes a recorded event,
  not a mysterious empty result);
* failure rows, never swallowed (a failed fetch is not "no new events");
* run lifecycle, sync status, watermark commit only for *completed* scopes.

A source that returns fewer records than expected is not evidence of fewer
events; a source that errors is recorded as an error and the other scopes
continue, so one broken issuer cannot blind the whole source.
"""

from __future__ import annotations

import hashlib
import json
import time
import traceback
from dataclasses import dataclass, field
from typing import Any, Mapping, Protocol, Sequence, runtime_checkable

from ..http import BudgetExceeded, Fetcher, HttpError, NotFound, OfflineMiss
from ..util import utc_now_iso
from . import mapping as mapping_mod
from .ledger import ObservationLedger
from .records import (
    COLLECTOR_VERSION,
    ORIGIN_LIVE,
    PRECISION_UNKNOWN,
    RUN_FAILED,
    RUN_OK,
    RUN_PARTIAL,
    SOURCE_STATUS_DEGRADED,
    SOURCE_STATUS_OK,
    MappingResult,
    Page,
    RawRecord,
    Scope,
    canonical_json,
)

DONE = "__DONE__"
MAX_PAGES_PER_SCOPE = 200
BUDGET_FLOOR = 8
FETCH_FAILED_MARK_LIMIT = 25


@dataclass
class CollectContext:
    """Everything an adapter is allowed to use (no hidden globals)."""

    fetcher: Fetcher
    ledger: ObservationLedger
    run_id: str
    trigger: str = "manual"
    collector_version: str = COLLECTOR_VERSION
    mapping_version: str = mapping_mod.MAPPING_VERSION
    limit: int = 0
    dry_run: bool = False
    offline: bool = False
    companies: tuple[str, ...] = ()
    origin: str = ORIGIN_LIVE
    backfill_reason: str | None = None
    now: str = field(default_factory=utc_now_iso)
    log: Any = print

    def get_json(self, url: str, params: Mapping[str, Any] | None = None,
                 *, refresh: bool | None = None) -> Any:
        """Fetch JSON through the shared polite layer.

        Live runs always refresh (a cached page would hide an update); offline
        runs replay a committed fixture/cassette directory instead.
        """
        if refresh is None:
            refresh = not self.offline
        return self.fetcher.get_json(url, dict(params or {}), refresh=refresh)

    def structure(self, sample: Any) -> str:
        return structure_signature(sample)

    @property
    def requests_remaining(self) -> int:
        return max(0, int(self.fetcher.max_requests) - int(self.fetcher.stats["requests"]) - BUDGET_FLOOR)


@runtime_checkable
class SourceAdapter(Protocol):
    source_id: str
    label_zh: str
    collector_version: str
    declared_cadence_zh: str
    record_type_labels: Mapping[str, str]

    def plan(self, ctx: CollectContext) -> list[Scope]: ...

    def fetch_page(self, ctx: CollectContext, scope: Scope, cursor: str | None) -> Page: ...

    def map_record(self, record: RawRecord, ctx: CollectContext) -> MappingResult: ...


# ------------------------------------------------------------------ structure diff
def structure_signature(sample: Any, depth: int = 4) -> str:
    """A stable fingerprint of a payload's *shape* (keys + types, not values)."""

    def shape(value: Any, level: int) -> Any:
        if level <= 0:
            return type(value).__name__
        if isinstance(value, Mapping):
            return {str(key): shape(val, level - 1) for key, val in sorted(value.items(), key=lambda kv: str(kv[0]))}
        if isinstance(value, (list, tuple)):
            head = shape(value[0], level - 1) if value else "empty"
            return {"__list__": head, "len_band": len(value) // 50}
        return type(value).__name__

    return hashlib.sha1(canonical_json(shape(sample, depth)).encode("utf-8")).hexdigest()


# ----------------------------------------------------------------------- counters
def _zero_counters() -> dict[str, int]:
    return {
        "requests": 0,
        "pages": 0,
        "records_seen": 0,
        "records_new": 0,
        "records_updated": 0,
        "records_unchanged": 0,
        "records_removed": 0,
        "records_failed": 0,
    }


def _error_kind(exc: BaseException) -> tuple[str, bool]:
    if isinstance(exc, BudgetExceeded):
        return "BUDGET", False
    if isinstance(exc, OfflineMiss):
        return "FIXTURE_MISS", False
    if isinstance(exc, NotFound):
        return "HTTP_ERROR", False
    if isinstance(exc, HttpError):
        status = getattr(exc, "status", 0) or 0
        retryable = status == 429 or status >= 500 or status == 0
        kind = "RATE_LIMIT" if status == 429 else "HTTP_ERROR"
        return kind, retryable
    if isinstance(exc, TimeoutError):
        return "TIMEOUT", True
    if isinstance(exc, (ValueError, KeyError, TypeError, json.JSONDecodeError)):
        return "PARSE_ERROR", False
    return "SCOPE_ERROR", True


def _short_error(exc: BaseException) -> str:
    return f"{type(exc).__name__}: {exc}"[:900]


# --------------------------------------------------------------------------- engine
def run_source(adapter: SourceAdapter, ctx: CollectContext, *, resume: bool = True,
               max_pages_per_scope: int = MAX_PAGES_PER_SCOPE) -> dict[str, Any]:
    """Collect one source incrementally into the observation ledger."""
    ledger = ctx.ledger
    source = adapter.source_id
    ledger.ensure_source(
        source,
        label_zh=adapter.label_zh,
        adapter_version=adapter.collector_version,
        declared_cadence_zh=adapter.declared_cadence_zh,
    )
    state_before = ledger.get_source_state(source) or {}
    watermark_before = _decode_watermark(state_before.get("watermark"))
    resume_run = ledger.last_resumable_run(source) if resume else None
    resumed = False
    if resume_run and resume_run["status"] in ("RUNNING", "INTERRUPTED", "PARTIAL", "FAILED"):
        run_id = resume_run["run_id"]
        resumed = True
        if resume_run["status"] == "RUNNING":
            ledger.con.execute(
                "UPDATE sync_run SET status='INTERRUPTED', finished_at=? WHERE run_id=?",
                (utc_now_iso(), run_id),
            )
            ledger.con.commit()
        checkpoints = ledger.load_checkpoints(source, run_id)
        ledger.con.execute(
            "UPDATE sync_run SET status='RUNNING', finished_at=NULL, error_detail=NULL WHERE run_id=?",
            (run_id,),
        )
        ledger.con.commit()
    else:
        run_id = ledger.start_run(
            source, trigger=ctx.trigger, collector_version=adapter.collector_version
        )
        checkpoints = {}
    ctx.run_id = run_id

    counters = _zero_counters()
    started_perf = time.perf_counter()
    requests_at_start = int(ctx.fetcher.stats["requests"])
    errors: list[dict[str, Any]] = []
    structure_changed = False
    structure_checked = False
    structure_note: str | None = None
    scopes_total = 0
    scopes_completed = 0
    scopes_failed = 0
    limited = False
    watermarks = dict(watermark_before)
    status = RUN_OK

    def _log(message: str) -> None:
        try:
            ctx.log(message)
        except Exception:  # pragma: no cover - logging must never kill a run
            pass

    try:
        scopes = list(adapter.plan(ctx))
    except Exception as exc:  # noqa: BLE001 - a broken plan is a recorded failure
        kind, retryable = _error_kind(exc)
        ledger.record_failure(source, kind=kind, message=_short_error(exc), run_id=run_id,
                              retryable=retryable)
        errors.append({"scope": "*plan*", "error": _short_error(exc)})
        ledger.finish_run(run_id, status=RUN_FAILED, counters=counters,
                          error_detail=_short_error(exc))
        ledger.note_source_failure(source, run_id=run_id, message=_short_error(exc))
        return _result(adapter, run_id, RUN_FAILED, counters, scopes_total, scopes_completed,
                       scopes_failed, watermarks, errors, structure_changed, structure_note,
                       resumed, started_perf, limited)

    scopes_total = len(scopes)
    for scope in scopes:
        if ctx.limit and counters["records_seen"] >= ctx.limit:
            limited = True
            break
        stored = checkpoints.get(scope.scope_id)
        if stored == DONE:
            scopes_completed += 1
            continue
        cursor = stored
        pages = 0
        scope_failed = False
        while True:
            if ctx.requests_remaining <= 0:
                errors.append({"scope": scope.scope_id, "error": "request budget exhausted before the scope finished"})
                ledger.record_failure(source, kind="BUDGET",
                                      message=f"budget exhausted in scope {scope.scope_id}",
                                      run_id=run_id, retryable=False)
                scope_failed = True
                status = RUN_PARTIAL
                break
            try:
                page = adapter.fetch_page(ctx, scope, cursor)
            except Exception as exc:  # noqa: BLE001 - record, continue with other scopes
                kind, retryable = _error_kind(exc)
                message = _short_error(exc)
                ledger.record_failure(source, kind=kind, message=message, run_id=run_id,
                                      retryable=retryable)
                errors.append({"scope": scope.scope_id, "error": message})
                # A failed scope is not evidence that its records are unchanged:
                # explicitly mark the ones we know about as FETCH_FAILED.
                _mark_scope_fetch_failed(adapter, ctx, scope, counters, message)
                scope_failed = True
                status = RUN_PARTIAL
                break
            pages += 1
            counters["pages"] += 1
            # Structure is a *source-level* property: check it once per run, on the
            # first page of the first scope. Comparing every scope's sample would
            # compare different issuers/queries with each other and raise false
            # alarms on ordinary data.
            if (page.structure_sample is not None and not structure_checked):
                structure_checked = True
                signature = structure_signature(page.structure_sample)
                previous = state_before.get("structure_signature")
                if previous and previous != signature:
                    structure_changed = True
                    structure_note = (
                        f"{source} 返回结构指纹变化：{previous[:10]} → {signature[:10]}；"
                        "采集继续，但字段含义需人工复核"
                    )
                    ledger.set_structure(source, signature, True, structure_note)
                    ledger.record_failure(source, kind="STRUCTURE_CHANGE", message=structure_note,
                                          run_id=run_id, retryable=False)
                    errors.append({"scope": "*structure*", "error": structure_note})
                    status = RUN_PARTIAL
                else:
                    ledger.set_structure(source, signature, False, None)
            for record in page.records:
                if ctx.limit and counters["records_seen"] >= ctx.limit:
                    limited = True
                    break
                counters["records_seen"] += 1
                try:
                    mapped = adapter.map_record(record, ctx)
                    outcome = ledger.record_observation(
                        record,
                        mapped,
                        run_id=run_id,
                        collector_version=adapter.collector_version,
                        mapping_version=ctx.mapping_version,
                        seen_at=ctx.now,
                        origin=ctx.origin,
                        backfill_reason=ctx.backfill_reason,
                    )
                except Exception as exc:  # noqa: BLE001 - one bad record must not lose the page
                    counters["records_failed"] += 1
                    ledger.record_failure(source, kind="PARSE_ERROR", message=_short_error(exc),
                                          run_id=run_id, retryable=False,
                                          url=record.url)
                    errors.append({"scope": scope.scope_id, "record": record.source_record_id,
                                   "error": _short_error(exc)})
                    continue
                _tally(counters, outcome.state)
            for obs_id in page.removed_ids:
                try:
                    if ledger.mark_removed(obs_id, run_id=run_id, seen_at=ctx.now,
                                           note_zh="来源在本次核对中不再提供该记录"):
                        counters["records_removed"] += 1
                except Exception as exc:  # noqa: BLE001
                    errors.append({"scope": scope.scope_id, "error": _short_error(exc)})
            for obs_id in page.failed_ids:
                try:
                    ledger.mark_fetch_failed(obs_id, run_id=run_id, seen_at=ctx.now,
                                             message=page.failure_note_zh or "record fetch failed")
                    counters["records_failed"] += 1
                except Exception as exc:  # noqa: BLE001
                    errors.append({"scope": scope.scope_id, "error": _short_error(exc)})
            if page.watermark:
                watermarks[scope.scope_id] = page.watermark
            next_cursor = page.next_cursor
            ledger.save_checkpoint(source, run_id, scope.scope_id, next_cursor or DONE,
                                   counters["records_seen"])
            if next_cursor is None:
                scopes_completed += 1
                break
            cursor = next_cursor
            if pages >= max_pages_per_scope:
                errors.append({"scope": scope.scope_id,
                               "error": f"page ceiling {max_pages_per_scope} reached; resume later"})
                ledger.record_failure(source, kind="BUDGET",
                                      message=f"page ceiling in scope {scope.scope_id}",
                                      run_id=run_id, retryable=False)
                status = RUN_PARTIAL
                break
        if scope_failed:
            scopes_failed += 1
        if limited:
            break

    # ---------------------------------------------------------------- finalise
    counters["requests"] = int(ctx.fetcher.stats["requests"]) - requests_at_start
    if errors:
        # PARTIAL means the run made observable progress and is resumable; FAILED
        # means it produced no evidence at all. A failed page is never reported as
        # "no change".
        made_progress = bool(
            scopes_completed
            or counters["records_seen"]
            or counters["pages"]
            or counters["records_new"]
            or counters["records_updated"]
            or counters["records_failed"]
            or counters["records_removed"]
        )
        status = RUN_PARTIAL if made_progress else RUN_FAILED
        if structure_changed and scopes_completed:
            status = RUN_PARTIAL
    if scopes_total and scopes_completed == scopes_total and not errors:
        status = RUN_OK
    watermarks_dumped = canonical_json(watermarks) if watermarks else None
    notes = []
    if resumed:
        notes.append("本次运行从上次中断的检查点继续")
    if limited:
        notes.append(f"按 --limit {ctx.limit} 提前结束（可继续运行）")
    if structure_changed and structure_note:
        notes.append(structure_note)
    ledger.finish_run(run_id, status=status, counters=counters,
                      error_detail=None if not errors else _short_error_text(errors),
                      watermark_after=watermarks_dumped, notes_zh="；".join(notes) or None)
    if watermarks:
        ledger.set_watermark(source, watermarks)
    if status == RUN_OK:
        if counters["requests"] > 0 or counters["records_seen"] > 0:
            ledger.note_source_success(source, run_id=run_id, status=SOURCE_STATUS_OK)
        else:
            ledger.note_source_finish_without_requests(
                source, run_id=run_id,
                message="本次运行仅收尾上次中断的运行（从检查点确认全部范围已完成），未发起新请求",
            )
    elif status == RUN_PARTIAL:
        ledger.note_source_failure(
            source, run_id=run_id,
            message=f"{scopes_completed}/{scopes_total} 个范围完成；" + _short_error_text(errors),
            degraded=True,
        )
    else:
        ledger.note_source_failure(
            source, run_id=run_id,
            message=f"0/{scopes_total} 个范围完成；" + _short_error_text(errors),
        )
    return _result(adapter, run_id, status, counters, scopes_total, scopes_completed,
                   scopes_failed, watermarks, errors, structure_changed, structure_note,
                   resumed, started_perf, limited)


def _tally(counters: dict[str, int], state: str) -> None:
    from .records import CHANGE_NEW, CHANGE_UNCHANGED, CHANGE_UPDATED

    if state == CHANGE_NEW:
        counters["records_new"] += 1
    elif state == CHANGE_UPDATED:
        counters["records_updated"] += 1
    elif state == CHANGE_UNCHANGED:
        counters["records_unchanged"] += 1


def _mark_scope_fetch_failed(adapter: SourceAdapter, ctx: CollectContext, scope: Scope,
                             counters: dict[str, int], message: str) -> None:
    getter = getattr(adapter, "scope_known_ids", None)
    if getter is None:
        return
    try:
        known: Sequence[str] = getter(ctx, scope) or []
    except Exception:  # noqa: BLE001 - best effort by design
        return
    for obs_id in list(known)[:FETCH_FAILED_MARK_LIMIT]:
        try:
            ctx.ledger.mark_fetch_failed(obs_id, run_id=ctx.run_id, seen_at=ctx.now,
                                         message=message)
            counters["records_failed"] += 1
        except Exception:  # noqa: BLE001
            continue


def _short_error_text(errors: Sequence[Mapping[str, Any]], limit: int = 3) -> str:
    parts = []
    for item in errors[:limit]:
        scope = item.get("scope") or "?"
        parts.append(f"{scope}: {str(item.get('error'))[:160]}")
    if len(errors) > limit:
        parts.append(f"…共 {len(errors)} 条错误")
    return " | ".join(parts)


def _decode_watermark(value: Any) -> dict[str, Any]:
    if not value:
        return {}
    if isinstance(value, dict):
        return dict(value)
    try:
        decoded = json.loads(value)
        return decoded if isinstance(decoded, dict) else {}
    except (TypeError, ValueError):
        return {}


def _result(adapter: SourceAdapter, run_id: str, status: str, counters: dict[str, int],
            scopes_total: int, scopes_completed: int, scopes_failed: int,
            watermarks: dict[str, Any], errors: list[dict[str, Any]], structure_changed: bool,
            structure_note: str | None, resumed: bool, started_perf: float,
            limited: bool) -> dict[str, Any]:
    return {
        "source": adapter.source_id,
        "label_zh": adapter.label_zh,
        "run_id": run_id,
        "status": status,
        "trigger": None,
        "collector_version": adapter.collector_version,
        "declared_cadence_zh": adapter.declared_cadence_zh,
        "counters": dict(counters),
        "scopes": {
            "total": scopes_total,
            "completed": scopes_completed,
            "failed": scopes_failed,
        },
        "watermark": watermarks,
        "structure": {"changed": structure_changed, "note_zh": structure_note},
        "errors": errors,
        "resumed": resumed,
        "limited": limited,
        "duration_ms": int((time.perf_counter() - started_perf) * 1000),
        "finished_at": utc_now_iso(),
    }


# ------------------------------------------------------------------ dry-run probe
def dry_run_source(adapter: SourceAdapter, ctx: CollectContext,
                   *, preview: int = 5) -> dict[str, Any]:
    """Fetch the first page of the first scope and **write nothing**.

    Used by ``observatory sync --dry-run``: an operator can see what a source now
    returns before committing an observation history.
    """
    scopes = adapter.plan(ctx)
    if not scopes:
        return {"source": adapter.source_id, "dry_run": True, "scopes": 0, "preview": []}
    page = adapter.fetch_page(ctx, scopes[0], None)
    items = []
    for record in page.records[:preview]:
        items.append(
            {
                "source_record_id": record.source_record_id,
                "record_type": record.record_type,
                "title": record.title,
                "event_at": record.event_at,
                "published_at": record.published_at,
                "payload_position": "would be hashed and versioned on a real run",
            }
        )
    return {
        "source": adapter.source_id,
        "dry_run": True,
        "scopes": len(scopes),
        "records_on_first_page": len(page.records),
        "next_cursor": page.next_cursor,
        "structure_signature": structure_signature(page.structure_sample)
        if page.structure_sample is not None
        else None,
        "preview": items,
    }
