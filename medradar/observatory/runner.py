"""Sync orchestration: one entry point for cron jobs, GitHub Actions and humans.

This module is the reliability layer around the adapters: it builds a polite
HTTP client, recovers interrupted runs, honours the pause switch, runs each
source independently (one broken source never blinds another), and reports what
actually happened. It writes only to the observation ledger.
"""

from __future__ import annotations

import inspect
import json
import os
import shutil
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from ..config import CACHE_DIR, DATA_DIR
from ..http import Fetcher
from .adapter import CollectContext, dry_run_source, run_source
from .adapters import DEFAULT_SOURCE_ORDER, known_sources, load_adapter
from .lag import measure_lag
from .ledger import ObservationLedger, default_ledger_path
from .records import COLLECTOR_VERSION, RUN_OK

OBSERVATORY_DATA_DIR = Path(DATA_DIR) / "observatory"
OBSERVATORY_CACHE_DIR = OBSERVATORY_DATA_DIR / "cache"

#: SEC's published access policy requires a User-Agent that identifies the client
#: and a contact address; a generic name is rejected with HTTP 403. Operators of a
#: long-running deployment should set ``MEDRADAR_SEC_UA`` to their own contact.
SEC_POLICY_UA = os.environ.get(
    "MEDRADAR_SEC_UA",
    "MedRadar research (open-source; contact: medradar@example.com)",
)


def build_fetcher(
    *,
    offline: bool = False,
    fixtures_dir: str | Path | None = None,
    cache_dir: str | Path | None = None,
    no_cache: bool = False,
    min_interval: float = 0.25,
    max_requests: int = 600,
    timeout: float = 45.0,
    ua: str | None = None,
) -> Fetcher:
    return Fetcher(
        cache_dir=None if no_cache else (cache_dir or OBSERVATORY_CACHE_DIR),
        fixtures_dir=fixtures_dir,
        offline=offline,
        min_interval=min_interval,
        max_requests=max_requests,
        timeout=timeout,
        ua=ua or SEC_POLICY_UA,
    )


def _adapter_kwargs(source: str, options: Mapping[str, Any]) -> dict[str, Any]:
    """Pass only the constructor parameters an adapter actually declares.

    The CLI/API expose one ``since_days`` knob; adapters whose initial window has
    its own name (``initial_days``) get it translated here so the public interface
    stays uniform.
    """
    accepted = {
        "sec_edgar": {"companies", "all_companies", "since_days", "page_size", "overlap_hours",
                      "max_companies"},
        "ctgov": {"companies", "all_companies", "initial_days", "page_size", "max_pages",
                  "max_companies"},
        "europepmc": {"companies", "all_companies", "initial_days", "page_size", "max_pages",
                      "max_companies"},
    }.get(source, set())
    if not accepted:
        return {}
    prepared = dict(options)
    if "initial_days" in accepted and "since_days" in prepared:
        prepared["initial_days"] = prepared.pop("since_days")
    return {key: value for key, value in prepared.items() if key in accepted}


def _load(source: str, options: Mapping[str, Any]) -> Any:
    return load_adapter(source, **_adapter_kwargs(source, options))


def _phase_for_source_run(ledger: ObservationLedger, source: str, resume: bool,
                          origin: str) -> str:
    """Acquisition phase of *this* run (initial sweep vs incremental vs backfill)."""
    from .records import ORIGIN_BACKFILLED, PHASE_BACKFILL, PHASE_INCREMENTAL, PHASE_INITIAL

    if origin == ORIGIN_BACKFILLED:
        return PHASE_BACKFILL
    first_run = ledger.first_observation_run(source)
    if not first_run:
        return PHASE_INITIAL
    if resume:
        resumable = ledger.last_resumable_run(source)
        if resumable and resumable.get("run_id") == first_run:
            # Resuming the go-live sweep: its records remain INITIAL_DISCOVERY.
            return PHASE_INITIAL
    return PHASE_INCREMENTAL


def sync(
    *,
    sources: Sequence[str] | None = None,
    ledger: ObservationLedger | None = None,
    ledger_path: str | Path | None = None,
    companies: Sequence[str] | None = None,
    all_companies: bool = False,
    since_days: int = 30,
    limit: int = 0,
    offline: bool = False,
    fixtures_dir: str | Path | None = None,
    no_cache: bool = False,
    resume: bool = True,
    dry_run: bool = False,
    trigger: str = "manual",
    origin: str = "LIVE",
    backfill_reason: str | None = None,
    force: bool = False,
    min_interval: float = 0.25,
    max_requests: int = 600,
    timeout: float = 45.0,
    max_pages_per_scope: int | None = None,
    acquire_lock: bool = True,
    lock_stale_seconds: float = 90.0,
    log: Any = None,
) -> dict[str, Any]:
    """Run an incremental collection pass and return a machine-readable report.

    A sync always takes the single-writer collector lease first: two processes must
    never write the same observation ledger. Read-only commands never take it.
    """
    emit = log or (lambda message: None)
    owns_ledger = ledger is None
    ledger = ledger or ObservationLedger(ledger_path)
    selected = [str(item).strip() for item in (sources or DEFAULT_SOURCE_ORDER) if str(item).strip()]
    unknown = [item for item in selected if item not in known_sources()]
    if unknown:
        raise ValueError(f"unknown source(s): {', '.join(unknown)}; known: {', '.join(known_sources())}")

    started = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    report: dict[str, Any] = {
        "ledger": str(ledger.path),
        "trigger": trigger,
        "started_at": started,
        "sources": {},
        "paused": False,
        "dry_run": bool(dry_run),
    }
    lock = None
    if acquire_lock and not dry_run:
        from .lock import CollectorLock, LedgerLocked

        lock = CollectorLock(ledger.path, stale_seconds=lock_stale_seconds)
        try:
            lock.acquire(mode="sync", command="observatory sync")
        except LedgerLocked as exc:
            report.update(
                {
                    "locked": True,
                    "lock_holder": exc.holder,
                    "ok": False,
                    "finished_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
                    "sources": {
                        source: {"source": source, "status": "LOCKED_SKIPPED",
                                 "reason": "another collector holds the lease"}
                        for source in selected
                    },
                }
            )
            try:
                ledger.set_runtime(
                    "lock_conflict",
                    {"at": report["finished_at"], "holder": exc.holder,
                     "by": {"pid": os.getpid(), "mode": "sync"}},
                )
            except Exception:  # noqa: BLE001 - reporting must not mask the refusal
                pass
            if owns_ledger:
                ledger.close()
            return report
    try:
        if not dry_run:
            recovered = ledger.recover_interrupted_runs()
            report["recovered_runs"] = recovered
            if ledger.is_paused() and not force:
                state = ledger.get_runtime("paused", {}) or {}
                report["paused"] = True
                report["pause"] = state
                report["sources"] = {source: {"status": "SKIPPED", "reason": "collector paused"}
                                     for source in selected}
                report["finished_at"] = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
                # A paused skip is not a collection attempt: leave source_state's
                # last_outcome/last_success untouched (the pause itself is recorded).
                return report
        fetcher = build_fetcher(
            offline=offline,
            fixtures_dir=fixtures_dir,
            no_cache=no_cache,
            min_interval=min_interval,
            max_requests=max_requests,
            timeout=timeout,
        )
        totals = {
            "records_seen": 0,
            "records_new": 0,
            "records_updated": 0,
            "records_unchanged": 0,
            "records_removed": 0,
            "records_failed": 0,
            "requests": 0,
            "pages": 0,
        }
        for source in selected:
            try:
                adapter = _load(
                    source,
                    {
                        "companies": list(companies or []),
                        "all_companies": all_companies,
                        "since_days": since_days,
                    },
                )
            except Exception as exc:  # noqa: BLE001 - one missing adapter must not stop the run
                report["sources"][source] = {
                    "source": source,
                    "status": "FAILED",
                    "error": f"adapter unavailable: {type(exc).__name__}: {exc}",
                }
                continue
            ctx = CollectContext(
                fetcher=fetcher,
                ledger=ledger,
                run_id="pending",
                trigger=trigger,
                collector_version=getattr(adapter, "collector_version", COLLECTOR_VERSION),
                limit=int(limit or 0),
                dry_run=bool(dry_run),
                offline=bool(offline),
                companies=tuple(companies or ()),
                origin=origin,
                backfill_reason=backfill_reason,
                phase=_phase_for_source_run(ledger, source, resume, origin),
                log=emit,
            )
            try:
                if dry_run:
                    result = dry_run_source(adapter, ctx)
                else:
                    kwargs = {}
                    if max_pages_per_scope:
                        kwargs["max_pages_per_scope"] = int(max_pages_per_scope)
                    result = run_source(adapter, ctx, resume=resume, **kwargs)
                report["sources"][source] = result
                for key in totals:
                    totals[key] += int((result.get("counters") or {}).get(key, 0))
            except Exception as exc:  # noqa: BLE001 - report, do not crash the loop
                report["sources"][source] = {
                    "source": source,
                    "status": "FAILED",
                    "error": f"{type(exc).__name__}: {exc}",
                }
                emit(f"[observatory] {source} failed: {type(exc).__name__}: {exc}")
        report["totals"] = totals
        report["fetcher_stats"] = dict(fetcher.stats)
        report["counts"] = ledger.counts()
        report["phase"] = ledger.phase_counts()
        report["finished_at"] = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
        report["ok"] = all(
            (item.get("status") in ("OK", "SKIPPED")) for item in report["sources"].values()
        )
        return report
    finally:
        if lock is not None:
            lock.release()
        if owns_ledger:
            ledger.close()


def status_report(*, ledger: ObservationLedger | None = None,
                  ledger_path: str | Path | None = None,
                  include_consistency: bool = True) -> dict[str, Any]:
    owns_ledger = ledger is None
    ledger = ledger or ObservationLedger(ledger_path)
    try:
        counts = ledger.counts()
        paused_state = ledger.get_runtime("paused", {}) or {}
        heartbeat = ledger.get_runtime("heartbeat", {}) or {}
        sources: list[dict[str, Any]] = []
        for row in ledger.con.execute("SELECT * FROM source_state ORDER BY source").fetchall():
            state = dict(row)
            source = state["source"]
            runs = _recent_runs(ledger, source, limit=10)
            failures = _recent_failures(ledger, source, limit=10)
            observations = ledger.con.execute(
                "SELECT COUNT(*) FROM observation WHERE source=?", (source,)
            ).fetchone()[0]
            windows = {
                "24h": ledger.window_counts(24, source=source),
                "7d": ledger.window_counts(24 * 7, source=source),
                "30d": ledger.window_counts(24 * 30, source=source),
            }
            lag = measure_lag(ledger, source)
            sources.append(
                {
                    "source": source,
                    "label_zh": state.get("label_zh"),
                    "status": state.get("status"),
                    "declared_cadence_zh": state.get("declared_cadence_zh"),
                    "adapter_version": state.get("adapter_version"),
                    "last_attempt_at": state.get("last_attempt_at"),
                    "last_success_at": state.get("last_success_at"),
                    "last_failure_at": state.get("last_failure_at"),
                    "consecutive_failures": state.get("consecutive_failures"),
                    "last_status_message": state.get("last_status_message"),
                    "watermark": _decode(state.get("watermark")),
                    "watermark_updated_at": state.get("watermark_updated_at"),
                    "structure": {
                        "signature": state.get("structure_signature"),
                        "changed_at": state.get("structure_changed_at"),
                        "note_zh": state.get("structure_note_zh"),
                    },
                    "entity_coverage": _decode(state.get("entity_coverage")),
                    "observations": int(observations),
                    "windows": windows,
                    "measured_lag": lag,
                    "last_outcome": state.get("last_outcome"),
                    "last_new_records": state.get("last_new_records"),
                    "last_updated_records": state.get("last_updated_records"),
                    "last_finished_at": state.get("last_finished_at"),
                    "recent_runs": runs,
                    "recent_failures": failures,
                }
            )
        report = {
            "ledger": counts,
            "paused": bool(paused_state.get("paused")) if isinstance(paused_state, dict) else False,
            "pause_state": paused_state,
            "heartbeat": heartbeat,
            "sources": sources,
            "phases": ledger.phase_summary(),
            "deployment": ledger.get_deployment(),
            "validation": ledger.get_validation(),
            "checked_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        }
        if include_consistency:
            report["consistency"] = ledger.consistency_check()
        return report
    finally:
        if owns_ledger:
            ledger.close()


def replay(*, as_of: str, ledger: ObservationLedger | None = None,
           ledger_path: str | Path | None = None, source: str | None = None,
           limit: int | None = None) -> dict[str, Any]:
    owns_ledger = ledger is None
    ledger = ledger or ObservationLedger(ledger_path, create=False)
    try:
        return ledger.snapshot(as_of, source=source, limit=limit)
    finally:
        if owns_ledger:
            ledger.close()


def reconcile(*, ledger: ObservationLedger | None = None,
              ledger_path: str | Path | None = None) -> dict[str, Any]:
    owns_ledger = ledger is None
    ledger = ledger or ObservationLedger(ledger_path)
    try:
        check = ledger.consistency_check()
        counts = ledger.counts()
        connection = sqlite3.connect(str(ledger.path))
        try:
            integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
        finally:
            connection.close()
        return {
            "ok": bool(check["ok"] and integrity == "ok"),
            "sqlite_integrity": integrity,
            "consistency": check,
            "counts": counts,
            "checked_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        }
    finally:
        if owns_ledger:
            ledger.close()


def backup(*, dest_dir: str | Path, ledger: ObservationLedger | None = None,
           ledger_path: str | Path | None = None,
           include_raw_cache: bool = True) -> dict[str, Any]:
    """Consistent backup of the observation ledger (+ optional raw response cache).

    The raw HTTP cache is the unparsed source archive: if a parser bug is ever
    found, the evidence can be re-derived from it without re-querying the API.
    """
    owns_ledger = ledger is None
    ledger = ledger or ObservationLedger(ledger_path)
    destination = Path(dest_dir)
    destination.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    target = destination / f"observatory-{stamp}.sqlite"
    try:
        source_conn = sqlite3.connect(str(ledger.path))
        try:
            out = sqlite3.connect(str(target))
            try:
                source_conn.backup(out)
            finally:
                out.close()
        finally:
            source_conn.close()
        result: dict[str, Any] = {
            "ledger": str(target),
            "bytes": target.stat().st_size,
            "counts": ledger.counts(),
            "created_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        }
        if include_raw_cache and OBSERVATORY_CACHE_DIR.is_dir():
            cache_target = destination / f"raw-cache-{stamp}"
            shutil.copytree(OBSERVATORY_CACHE_DIR, cache_target)
            files = [path for path in cache_target.rglob("*") if path.is_file()]
            result["raw_cache"] = {"path": str(cache_target), "files": len(files),
                                   "bytes": sum(path.stat().st_size for path in files)}
        return result
    finally:
        if owns_ledger:
            ledger.close()


def pause(*, reason: str = "manual pause", ledger_path: str | Path | None = None) -> dict[str, Any]:
    ledger = ObservationLedger(ledger_path)
    try:
        ledger.pause(reason)
        return {"paused": True, "reason": reason, "at": datetime.now(timezone.utc).isoformat()}
    finally:
        ledger.close()


def resume(*, ledger_path: str | Path | None = None) -> dict[str, Any]:
    ledger = ObservationLedger(ledger_path)
    try:
        ledger.resume()
        return {"paused": False}
    finally:
        ledger.close()


def is_paused(*, ledger_path: str | Path | None = None) -> bool:
    ledger = ObservationLedger(ledger_path)
    try:
        return ledger.is_paused()
    finally:
        ledger.close()


def _recent_runs(ledger: ObservationLedger, source: str, limit: int = 10) -> list[dict[str, Any]]:
    rows = ledger.con.execute(
        "SELECT * FROM sync_run WHERE source=? ORDER BY started_at DESC LIMIT ?",
        (source, limit),
    ).fetchall()
    return [dict(row) for row in rows]


def _recent_failures(ledger: ObservationLedger, source: str, limit: int = 10) -> list[dict[str, Any]]:
    rows = ledger.con.execute(
        "SELECT * FROM source_failure WHERE source=? ORDER BY occurred_at DESC LIMIT ?",
        (source, limit),
    ).fetchall()
    return [dict(row) for row in rows]


def _decode(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return value
