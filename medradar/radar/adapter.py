"""The source-adapter contract and the incremental run engine.

An adapter answers three questions and nothing else:

* ``plan`` - which resumable scopes exist right now (one query, one sitemap, one product
  code sweep);
* ``fetch_page`` - one page of records for a scope, plus the cursor that continues it and
  the watermark that proves how far the scope actually got;
* ``map_record`` - what the *rule layer* can attribute for one record.

Everything else - identity, deduplication, versioning, change states, cursors, retries,
failure accounting, resumability - lives in this engine, so a new source cannot get those
rules subtly wrong.

Cursor rules the engine enforces:

1. A scope's cursor is checkpointed **after a page is durably recorded**, so a crash repeats
   at most one page - never loses one. Re-recording a page is idempotent by content hash.
2. The source watermark only advances from scopes that completed without a failure. A
   failed request therefore never advances the cursor.
3. A resumed run reuses its run id and its saved checkpoints; the interrupted status is
   preserved in history rather than being overwritten.
4. A refresh scope (a bounded inventory the source exposes in full) cannot report a removal
   unless the engine saw the complete inventory in this run; otherwise removal is not
   inferred.

Provenance: adapted from the Live Observatory collector engine (PR #13/#14,
``medradar/observatory/adapter.py``).
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any, Mapping, Protocol, Sequence, runtime_checkable

from .http import (
    BudgetExceeded,
    FetchError,
    NotFound,
    ParseFailure,
    PoliteFetcher,
    RateLimited,
    Refused,
)
from .ledger import ObservationLedger
from .records import (
    CHANGE_NEW,
    CHANGE_UPDATED,
    MAPPING_VERSION,
    ORIGIN_BACKFILLED,
    ORIGIN_LIVE,
    OUTCOME_DEFERRED,
    OUTCOME_FETCH_FAILED,
    OUTCOME_LOCKED,
    OUTCOME_NEW_RECORDS,
    OUTCOME_NO_NEW_RECORDS,
    OUTCOME_PARTIAL,
    OUTCOME_UPDATED_RECORDS,
    PHASE_BACKFILL,
    RECORD_TYPES,
    RUN_DEFERRED,
    RUN_FAILED,
    RUN_INTERRUPTED,
    RUN_OK,
    RUN_PARTIAL,
    SOURCE_STATUS_OK,
    MappingResult,
    Page,
    RawRecord,
    RecordOutcome,
    Scope,
    canonical_json,
    utc_now_iso,
)

MAX_PAGES_PER_SCOPE = 200


@dataclass
class CollectContext:
    """Everything an adapter is allowed to use. No hidden globals."""

    fetcher: PoliteFetcher
    ledger: ObservationLedger
    run_id: str = ""
    trigger: str = "manual"
    adapter_version: str = "unknown"
    mapping_version: str = MAPPING_VERSION
    limit: int = 0
    dry_run: bool = False
    origin: str = ORIGIN_LIVE
    backfill_reason: str | None = None
    phase: str | None = None
    watermark: str | None = None
    cursor: Mapping[str, Any] = field(default_factory=dict)
    #: Adapter-owned durable state (e.g. an official endpoint version). Persisted with the
    #: watermark, and only when the run did not fail, so a failure cannot advance it.
    adapter_state: dict[str, Any] = field(default_factory=dict)
    now: str = field(default_factory=utc_now_iso)
    log: Any = print

    @property
    def requests_remaining(self) -> int:
        return self.fetcher.requests_remaining

    def emit(self, message: str) -> None:
        try:
            self.log(message)
        except Exception:  # pragma: no cover - logging must never kill a run
            pass


@runtime_checkable
class SourceAdapter(Protocol):
    source_id: str
    label: str
    adapter_version: str
    declared_cadence_hours: float
    record_types: Sequence[str]

    def plan(self, ctx: CollectContext) -> list[Scope]: ...

    def fetch_page(self, ctx: CollectContext, scope: Scope, cursor: str | None) -> Page: ...

    def map_record(self, record: RawRecord, ctx: CollectContext) -> MappingResult: ...


def structure_signature(sample: Any, depth: int = 4) -> str:
    """A stable fingerprint of a payload's *shape* (keys and types, never values)."""

    def shape(value: Any, level: int) -> Any:
        if level <= 0:
            return type(value).__name__
        if isinstance(value, Mapping):
            return {str(k): shape(v, level - 1) for k, v in sorted(value.items(), key=lambda kv: str(kv[0]))}
        if isinstance(value, (list, tuple)):
            head = shape(value[0], level - 1) if value else "empty"
            return {"__list__": head, "len_band": len(value) // 50}
        return type(value).__name__

    return hashlib.sha256(canonical_json(shape(sample, depth)).encode("utf-8")).hexdigest()[:32]


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
        "records_skipped": 0,
        "scopes_total": 0,
        "scopes_completed": 0,
        "scopes_failed": 0,
    }


def _tally(counters: dict[str, int], outcome: RecordOutcome) -> None:
    if outcome.state == CHANGE_NEW:
        counters["records_new"] += 1
    elif outcome.state == CHANGE_UPDATED:
        counters["records_updated"] += 1
    else:
        counters["records_unchanged"] += 1


def _outcome_for(status: str, counters: Mapping[str, int]) -> str:
    if status == RUN_FAILED:
        return OUTCOME_FETCH_FAILED
    if status == RUN_INTERRUPTED:
        return OUTCOME_PARTIAL
    if status == RUN_DEFERRED:
        return OUTCOME_DEFERRED
    if status == RUN_PARTIAL:
        return OUTCOME_PARTIAL
    if counters.get("records_new"):
        return OUTCOME_NEW_RECORDS
    if counters.get("records_updated"):
        return OUTCOME_UPDATED_RECORDS
    return OUTCOME_NO_NEW_RECORDS


def classify_exception(error: BaseException) -> tuple[str, bool]:
    """Map a transport failure onto (kind, retryable). Never guesses a success."""
    if isinstance(error, Refused):
        return "ACCESS_REFUSED", False
    if isinstance(error, BudgetExceeded):
        return "BUDGET", False
    if isinstance(error, NotFound):
        return "NOT_FOUND", False
    if isinstance(error, RateLimited):
        return "RATE_LIMITED", True
    if isinstance(error, ParseFailure):
        return "PARSE_ERROR", False
    if isinstance(error, FetchError):
        return error.kind, bool(error.retryable)
    return "SCOPE_ERROR", True


def run_source(adapter: SourceAdapter, ctx: CollectContext, *, resume: bool = True,
               max_pages_per_scope: int = MAX_PAGES_PER_SCOPE) -> dict[str, Any]:
    """Collect one source incrementally into the ledger. Never advances a failed cursor."""
    ledger = ctx.ledger
    source = adapter.source_id
    state_before = ledger.ensure_source(
        source,
        label=adapter.label,
        adapter_version=adapter.adapter_version,
        cadence_hours=float(adapter.declared_cadence_hours),
        access_state=str(getattr(adapter, "access_state", "ENABLED")),
        access_reason=getattr(adapter, "access_reason", None),
        enabled=bool(getattr(adapter, "enabled", True)),
    )
    watermark_before = (state_before or {}).get("watermark")
    ctx.watermark = watermark_before
    ctx.cursor = (state_before or {}).get("cursor") or {}

    if not bool((state_before or {}).get("enabled", 1)):
        return {
            "source": source, "status": RUN_DEFERRED, "outcome": OUTCOME_DEFERRED,
            "reason": "source is disabled in config/radar/sources.json",
            "counters": _zero_counters(), "errors": [],
        }

    run = ledger.last_resumable_run(source) if resume else None
    checkpoints: dict[str, dict[str, Any]] = {}
    resumed = False
    if run and run["status"] in ("INTERRUPTED", "PARTIAL", "FAILED"):
        ctx.run_id = run["run_id"]
        resumed = True
        if run["status"] == "INTERRUPTED":
            # Keep the interruption in history: only the live status is reopened.
            ledger.con.execute("UPDATE sync_run SET status='RUNNING', finished_at=NULL WHERE run_id=?", (ctx.run_id,))
            ledger.con.commit()
        else:
            ledger.con.execute("UPDATE sync_run SET status='RUNNING', finished_at=NULL WHERE run_id=?", (ctx.run_id,))
            ledger.con.commit()
        checkpoints = ledger.load_checkpoints(source, ctx.run_id)
        ctx.emit(f"[{source}] resuming run {ctx.run_id} with {len(checkpoints)} checkpoint(s)")
    else:
        ctx.run_id = ledger.start_run(source, trigger=ctx.trigger,
                                      adapter_version=adapter.adapter_version)

    counters = _zero_counters()
    errors: list[dict[str, Any]] = []
    scope_watermarks: dict[str, str] = {}
    started = time.perf_counter()
    interrupted = False

    try:
        scopes = list(adapter.plan(ctx))
    except Exception as error:  # noqa: BLE001 - a planning failure is a source failure
        kind, retryable = classify_exception(error)
        ledger.note_source_failure(source, run_id=ctx.run_id, message=f"{type(error).__name__}: {error}",
                                   kind=kind, retryable=retryable)
        ledger.finish_run(ctx.run_id, status=RUN_FAILED, counters=counters,
                          errors=[{"phase": "plan", "kind": kind, "message": str(error)[:800]}])
        return {
            "source": source, "status": RUN_FAILED, "outcome": OUTCOME_FETCH_FAILED,
            "counters": counters, "errors": [{"phase": "plan", "kind": kind, "message": str(error)}],
            "watermark_before": watermark_before, "watermark_after": watermark_before,
        }

    counters["scopes_total"] = len(scopes)
    if ctx.limit:
        counters["limit"] = int(ctx.limit)

    for scope in scopes:
        checkpoint = checkpoints.get(scope.scope_id) or {}
        cursor = checkpoint.get("cursor") if checkpoint else None
        seen_in_scope = int(checkpoint.get("records_seen") or 0) if checkpoint else 0
        scope_ok = True
        page_count = 0
        while True:
            if ctx.limit and counters["records_seen"] >= ctx.limit:
                ctx.emit(f"[{source}] limit {ctx.limit} reached; stopping with a clean cursor")
                break
            page_count += 1
            if page_count > max_pages_per_scope:
                errors.append({"phase": "fetch", "scope": scope.scope_id, "kind": "PAGE_LIMIT",
                               "message": f"more than {max_pages_per_scope} pages; cursor not advanced"})
                scope_ok = False
                break
            try:
                page = adapter.fetch_page(ctx, scope, cursor)
            except KeyboardInterrupt:
                interrupted = True
                scope_ok = False
                break
            except Exception as error:  # noqa: BLE001
                kind, retryable = classify_exception(error)
                scope_ok = False
                errors.append({"phase": "fetch", "scope": scope.scope_id, "kind": kind,
                               "message": f"{type(error).__name__}: {error}"[:800]})
                ledger.note_source_failure(source, run_id=ctx.run_id,
                                           message=f"{scope.scope_id}: {type(error).__name__}: {error}",
                                           kind=kind, retryable=retryable)
                ctx.emit(f"[{source}] scope {scope.scope_id} failed: {kind}: {error}")
                break

            counters["pages"] += 1
            if not page.records and page.next_cursor is None and page.watermark is None and not page.failed_ids:
                break

            for record in page.records:
                counters["records_seen"] += 1
                if record.record_type not in RECORD_TYPES:
                    counters["records_skipped"] += 1
                    errors.append({"phase": "record", "kind": "BAD_RECORD_TYPE",
                                   "id": record.source_record_id, "record_type": record.record_type})
                    continue
                try:
                    mapping = adapter.map_record(record, ctx)
                except Exception as error:  # noqa: BLE001 - a mapping bug must not lose the record
                    counters["records_skipped"] += 1
                    errors.append({"phase": "map", "kind": "MAP_ERROR", "id": record.source_record_id,
                                   "message": f"{type(error).__name__}: {error}"[:400]})
                    mapping = MappingResult(note="mapping failed; stored unmapped")
                accept = getattr(adapter, "accept_record", None)
                if callable(accept):
                    try:
                        accepted, reason = accept(record, mapping)
                    except Exception as error:  # noqa: BLE001 - a scope bug must fail closed
                        accepted, reason = False, f"scope gate failed: {type(error).__name__}: {error}"
                    if not accepted:
                        counters["records_skipped"] += 1
                        if len(errors) < 50:
                            errors.append({"phase": "scope", "kind": "OUT_OF_SCOPE",
                                           "id": record.source_record_id, "message": str(reason)[:300]})
                        continue
                if ctx.dry_run:
                    counters["records_seen"] += 0
                    continue
                try:
                    outcome = ledger.record_observation(
                        record, mapping, run_id=ctx.run_id,
                        adapter_version=adapter.adapter_version,
                        mapping_version=ctx.mapping_version, origin=ctx.origin,
                        backfill_reason=ctx.backfill_reason, phase=ctx.phase,
                    )
                except Exception as error:  # noqa: BLE001
                    counters["records_skipped"] += 1
                    errors.append({"phase": "record", "kind": "RECORD_ERROR", "id": record.source_record_id,
                                   "message": f"{type(error).__name__}: {error}"[:400]})
                    continue
                _tally(counters, outcome)

            for obs_id in page.failed_ids:
                counters["records_failed"] += 1
                if not ctx.dry_run:
                    ledger.mark_fetch_failed(obs_id, run_id=ctx.run_id,
                                             message=page.failure_note or "record could not be re-read")
            for obs_id in page.removed_ids:
                counters["records_removed"] += 1
                if not ctx.dry_run:
                    ledger.mark_removed(obs_id, run_id=ctx.run_id,
                                        note=page.note or "the source no longer lists this record")

            seen_in_scope += len(page.records)
            cursor = page.next_cursor
            if page.watermark:
                scope_watermarks[scope.scope_id] = page.watermark
            if not ctx.dry_run:
                ledger.save_checkpoint(source, ctx.run_id, scope.scope_id, cursor, seen_in_scope)
            if cursor is None:
                break

        if scope_ok:
            counters["scopes_completed"] += 1
        else:
            counters["scopes_failed"] += 1
            scope_watermarks.pop(scope.scope_id, None)
        if interrupted:
            break

    elapsed = round(time.perf_counter() - started, 2)
    counters["elapsed_seconds"] = int(elapsed)
    counters["requests"] = int(ctx.fetcher.stats.get("requests", 0))

    if ctx.dry_run:
        status = RUN_PARTIAL
    elif interrupted:
        status = RUN_INTERRUPTED
    elif counters["scopes_failed"] and counters["scopes_completed"]:
        status = RUN_PARTIAL
    elif counters["scopes_failed"] and not counters["scopes_completed"]:
        status = RUN_FAILED
    elif counters["scopes_completed"] == 0 and counters["scopes_total"] > 0:
        status = RUN_FAILED
    else:
        status = RUN_OK

    # Merge only the watermarks of scopes that finished without a failure.
    watermark_after = watermark_before
    if not ctx.dry_run and status in (RUN_OK, RUN_PARTIAL):
        merged = _max_moment([watermark_before, *scope_watermarks.values()]) if scope_watermarks else watermark_before
        persisted_state = dict(ctx.adapter_state or {})
        if merged != watermark_before or persisted_state:
            ledger.set_watermark(source, merged, {"scopes": scope_watermarks, **persisted_state})
            watermark_after = merged

    outcome = _outcome_for(status, counters)
    if not ctx.dry_run:
        if status == RUN_OK:
            ledger.note_source_success(source, run_id=ctx.run_id,
                                       observed_update=bool(counters["records_new"] or counters["records_updated"]))
        ledger.finish_run(ctx.run_id, status=status, counters=counters, errors=errors,
                          watermark_after=watermark_after)
    ctx.emit(f"[{source}] {status} {outcome} new={counters['records_new']} "
             f"updated={counters['records_updated']} unchanged={counters['records_unchanged']} "
             f"failed={counters['records_failed']} in {elapsed}s")
    return {
        "source": source,
        "run_id": ctx.run_id,
        "resumed": resumed,
        "status": status,
        "outcome": outcome,
        "counters": counters,
        "errors": errors,
        "watermark_before": watermark_before,
        "watermark_after": watermark_after,
        "dry_run": ctx.dry_run,
    }


def _max_moment(values: Sequence[str | None]) -> str | None:
    """Lexicographic max is chronological max for the ISO forms used as watermarks."""
    candidates = [str(v) for v in values if v]
    return max(candidates) if candidates else None
