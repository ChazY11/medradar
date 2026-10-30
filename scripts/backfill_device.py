"""Full-history openFDA device backfill for ``data/medradar.sqlite`` (task-10).

Runs the existing ``medradar.collect_device.collect`` with ``months=720`` (openFDA device
history starts around 1976) and a bounded request budget, then records a resumable
progress/coverage report. Nothing in ``medradar/`` is modified.

Why a wrapper instead of the plain CLI?

* it persists the per-run progress (request stats, per-kind windows, coverage) to
  ``data/backfill_device_progress.json`` so a run interrupted by the openFDA daily quota can
  be reported and resumed later;
* it distinguishes a *quota* stop (429 storm) from a generic failure and exits cleanly
  instead of hammering the API;
* ``--report-only`` prints the post-backfill data-quality report requested by the task
  (events per kind, earliest/latest date, company match rate, track match rate, requests).

Re-running is safe: events are keyed by deterministic ``event_id`` and every openFDA
response is cached under ``data/cache``, so a second run only fetches what is still missing.

Usage
-----
    python scripts/backfill_device.py --db data/medradar.sqlite --months 720 --budget 600
    # targeted, chunked, kill-safe resume for a single endpoint family:
    python scripts/backfill_device.py --kinds device_recall --months 720 --budget 300
    python scripts/backfill_device.py --report-only --db data/medradar.sqlite

Exit codes: ``0`` = finished (possibly partially, with warnings recorded), ``2`` = hard error.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import timedelta
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from medradar.collect_device import (  # noqa: E402
    DEVICE_ENDPOINTS,
    _clean,
    _event_track,
    _fetch_window,
    _keyword_index,
    _NORMALIZERS,
    collect,
)
from medradar.config import CACHE_DIR, DATA_DIR, load_companies, load_tracks  # noqa: E402
from medradar.db import DB  # noqa: E402
from medradar.http import BudgetExceeded, Fetcher, HttpError  # noqa: E402
from medradar.util import add_months, iso, today_utc, utc_now_iso  # noqa: E402

DEFAULT_DB = DATA_DIR / "medradar.sqlite"
DEFAULT_PROGRESS = DATA_DIR / "backfill_device_progress.json"
DEVICE_KIND_SQL = ", ".join(f"'{kind}'" for kind in DEVICE_ENDPOINTS)


class QuotaAwareFetcher(Fetcher):
    """Fetcher that stops the run after an unusual number of surfaced 429 (quota) errors.

    ``Fetcher`` already retries 429/5xx with backoff; this only escalates to
    :class:`BudgetExceeded` when the daily quota looks exhausted, so the collector records
    progress and exits instead of burning the whole request budget in retries.
    """

    def __init__(self, *args: Any, abort_after_quota_errors: int = 10, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._quota_errors = 0
        self.abort_after_quota_errors = max(1, int(abort_after_quota_errors))

    def _request_json(self, url: str, retries: int = 3, backoff: float = 2.0) -> Any:
        try:
            return super()._request_json(url, retries=retries, backoff=backoff)
        except HttpError as exc:
            if exc.status == 429:
                self._quota_errors += 1
                if self._quota_errors >= self.abort_after_quota_errors:
                    raise BudgetExceeded(
                        f"openFDA returned 429 x{self._quota_errors}; daily quota likely "
                        "exhausted - stopping (re-run after 00:00 UTC to resume)"
                    ) from exc
            raise


def db_snapshot(db: DB) -> dict[str, Any]:
    """Data-quality numbers for the device events now in the DB."""
    per_kind: list[dict[str, Any]] = []
    for row in db.query(
        f"SELECT kind, COUNT(*) AS n, MIN(NULLIF(event_date, '')) AS min_date,"
        f"       MAX(NULLIF(event_date, '')) AS max_date"
        f"  FROM events WHERE kind IN ({DEVICE_KIND_SQL}) GROUP BY kind ORDER BY kind"
    ):
        per_kind.append(dict(row))

    totals = db.query(
        f"SELECT COUNT(*) AS total,"
        f"       SUM(CASE WHEN company_key IS NOT NULL THEN 1 ELSE 0 END) AS matched,"
        f"       SUM(CASE WHEN company_key IN (SELECT key FROM companies WHERE is_major = 1)"
        f"                THEN 1 ELSE 0 END) AS major_matched,"
        f"       SUM(CASE WHEN track_id IS NOT NULL THEN 1 ELSE 0 END) AS tracked,"
        f"       MIN(NULLIF(event_date, '')) AS min_date,"
        f"       MAX(NULLIF(event_date, '')) AS max_date"
        f"  FROM events WHERE kind IN ({DEVICE_KIND_SQL})"
    )[0]
    total = int(totals["total"] or 0)
    matched = int(totals["matched"] or 0)
    major_matched = int(totals["major_matched"] or 0)
    tracked = int(totals["tracked"] or 0)

    product_codes = db.query(
        "SELECT COUNT(*) AS n, SUM(CASE WHEN track_id IS NOT NULL THEN 1 ELSE 0 END) AS mapped"
        "  FROM product_codes"
    )[0]
    codes = int(product_codes["n"] or 0)
    mapped_codes = int(product_codes["mapped"] or 0)

    db_bytes = 0
    try:
        db_bytes = db.path.stat().st_size if hasattr(db, "path") else 0
    except OSError:
        pass

    return {
        "events_total": total,
        "per_kind": per_kind,
        "earliest_event_date": totals["min_date"],
        "latest_event_date": totals["max_date"],
        "company_matched": matched,
        "company_match_rate": round(matched / total, 4) if total else 0.0,
        "major_matched": major_matched,
        "major_match_rate": round(major_matched / total, 4) if total else 0.0,
        "track_matched": tracked,
        "track_match_rate": round(tracked / total, 4) if total else 0.0,
        "product_codes": codes,
        "product_codes_mapped": mapped_codes,
        "product_codes_mapped_rate": round(mapped_codes / codes, 4) if codes else 0.0,
        "db_bytes": db_bytes,
        "db_mb": round(db_bytes / (1024 * 1024), 1),
    }


def _load_code_map(db: DB) -> dict[str, str]:
    """Existing product-code → track dictionary straight from the DB (7k rows)."""
    rows = db.query("SELECT product_code, track_id FROM product_codes WHERE track_id IS NOT NULL")
    return {str(row["product_code"]): str(row["track_id"]) for row in rows}


def _iter_chunks(start, end, chunk_months: int):
    cursor = start
    while cursor <= end:
        next_start = add_months(cursor, chunk_months)
        chunk_end = min(end, next_start - timedelta(days=1))
        yield cursor, chunk_end
        cursor = next_start


def run_targeted(args: argparse.Namespace) -> int:
    """Chunked, kill-safe collection of selected kinds (used for the PMA/recall backfill).

    Unlike ``collect()`` this upserts every date window as soon as it is fetched, so memory
    stays bounded to one window (~3-5k records) and an interrupted run keeps every completed
    window; ``data/backfill_device_progress.json`` is refreshed after each window. This is
    what makes it safe to retry against openFDA 500/429 flakiness without re-normalising the
    176k 510(k) / 57k PMA events that are already in the DB.
    """
    kinds = [part.strip() for part in str(args.kinds).split(",") if part.strip()]
    unknown = [kind for kind in kinds if kind not in DEVICE_ENDPOINTS]
    if unknown:
        raise SystemExit(f"unknown kinds {unknown}; choose from {sorted(DEVICE_ENDPOINTS)}")

    db_path = Path(args.db)
    progress_path = Path(args.progress)
    end = today_utc()
    start = add_months(end, -max(1, int(args.months)))
    as_of = iso(end)
    fetcher = QuotaAwareFetcher(
        cache_dir=CACHE_DIR,
        min_interval=args.min_interval,
        max_requests=args.budget,
        timeout=args.timeout,
    )
    started = utc_now_iso()
    t0 = time.monotonic()
    warnings: list[str] = []
    budget_hit = False
    per_kind: dict[str, dict[str, Any]] = {}
    state: dict[str, Any] = {
        "task": "task-10",
        "mode": "targeted",
        "db": str(db_path),
        "months": args.months,
        "chunk_months": args.chunk_months,
        "budget": args.budget,
        "kinds": kinds,
        "started_at": started,
        "finished_at": None,
        "elapsed_sec": None,
        "request_stats": None,
        "before": None,
        "after": None,
        "per_kind": per_kind,
        "warnings": warnings,
        "error": None,
    }

    def persist() -> None:
        state["request_stats"] = dict(fetcher.stats)
        state["elapsed_sec"] = round(time.monotonic() - t0, 1)
        _write_progress(progress_path, state)

    with DB(db_path) as db:
        state["before"] = db_snapshot(db)
        companies = load_companies("device")
        tracks = load_tracks("device")
        db.upsert_companies(companies.all())
        db.upsert_tracks(tracks.all())
        code_map = _load_code_map(db)
        keyword_index = _keyword_index(tracks)
        print(
            "[targeted] before: events_total="
            f"{state['before']['events_total']} per_kind={json.dumps(state['before']['per_kind'], ensure_ascii=False)}"
        )
        print(
            f"[targeted] kinds={kinds} months={args.months} chunk={args.chunk_months}mo"
            f" budget={args.budget} code_map={len(code_map)} window={iso(start)}..{iso(end)}"
        )
        persist()

        exit_code = 0
        try:
            for kind in kinds:
                endpoint, date_field = DEVICE_ENDPOINTS[kind]
                kind_stats: dict[str, Any] = {"events": 0, "matched": 0, "tracked": 0, "chunks": []}
                per_kind[kind] = kind_stats
                if budget_hit:
                    continue
                for chunk_start, chunk_end in _iter_chunks(start, end, args.chunk_months):
                    if budget_hit:
                        break
                    window_log: list[dict[str, Any]] = []
                    chunk_info: dict[str, Any] = {
                        "start": iso(chunk_start),
                        "end": iso(chunk_end),
                        "windows": window_log,
                    }
                    kind_stats["chunks"].append(chunk_info)
                    try:
                        records = _fetch_window(
                            fetcher,
                            endpoint,
                            date_field,
                            chunk_start,
                            chunk_end,
                            0,
                            warnings,
                            windows=window_log,
                        )
                    except BudgetExceeded as exc:
                        budget_hit = True
                        state["error"] = f"budget: {exc}"
                        chunk_info["error"] = "budget exhausted"
                        print(f"[targeted] budget exhausted at {kind} {chunk_info['start']}..{chunk_info['end']}")
                        persist()
                        break

                    by_id: dict[str, dict[str, Any]] = {}
                    for record in records:
                        applicant = _clean(record.get("applicant")) or _clean(record.get("recalling_firm"))
                        company_key = companies.resolve(applicant)[0]
                        track_id, _ = _event_track(kind, record, code_map, tracks, keyword_index)
                        event = _NORMALIZERS[kind](
                            record,
                            company_key=company_key,
                            track_id=track_id,
                            track_zh=tracks.name_zh(track_id),
                            as_of=as_of,
                        )
                        if event is not None:
                            by_id[event["event_id"]] = event
                    events = list(by_id.values())
                    if events:
                        db.upsert_events(events)
                    kind_stats["events"] += len(events)
                    kind_stats["matched"] += sum(1 for event in events if event.get("company_key"))
                    kind_stats["tracked"] += sum(1 for event in events if event.get("track_id"))
                    chunk_info["records"] = len(records)
                    chunk_info["events"] = len(events)
                    print(
                        f"[targeted] {kind} {chunk_info['start']}..{chunk_info['end']}: "
                        f"records={len(records)} events={len(events)} requests={fetcher.stats['requests']}"
                    )
                    persist()
        except KeyboardInterrupt:
            state["error"] = "interrupted"
            exit_code = 0
        except Exception as exc:  # keep the progress record for the Lead
            state["error"] = f"{type(exc).__name__}: {exc}"
            exit_code = 2
        finally:
            state["finished_at"] = utc_now_iso()
            state["after"] = db_snapshot(db)
            persist()

    print(
        f"[targeted] done: per_kind={json.dumps({k: v['events'] for k, v in per_kind.items()}, ensure_ascii=False)} "
        f"requests={fetcher.stats['requests']} cache_hits={fetcher.stats['cache_hits']} "
        f"events_total={state['after']['events_total'] if state['after'] else '?'}"
    )
    if warnings:
        print("[targeted] warnings:")
        for warning in warnings[:20]:
            print(f"  - {warning}")
    print(f"[targeted] progress saved to {progress_path}")
    return exit_code


def _read_progress(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _write_progress(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    tmp.replace(path)


def run(args: argparse.Namespace) -> int:
    db_path = Path(args.db)
    progress_path = Path(args.progress)
    started = utc_now_iso()
    t0 = time.monotonic()
    fetcher = QuotaAwareFetcher(
        cache_dir=CACHE_DIR,
        min_interval=args.min_interval,
        max_requests=args.budget,
        timeout=args.timeout,
    )
    snapshot_before: dict[str, Any] = {}
    stats: dict[str, Any] | None = None
    error: str | None = None

    with DB(db_path) as db:
        snapshot_before = db_snapshot(db)
        print(f"[backfill] before: {json.dumps({k: snapshot_before[k] for k in ('events_total', 'per_kind')}, ensure_ascii=False)}")
        print(f"[backfill] months={args.months} budget={args.budget} db={db_path}")
        try:
            stats = collect(db, fetcher, months=args.months, limit=0)
        except BudgetExceeded as exc:
            error = f"budget: {exc}"
        except KeyboardInterrupt:
            error = "interrupted"
        except Exception as exc:  # keep the progress record even on an unexpected failure
            error = f"{type(exc).__name__}: {exc}"
        finally:
            snapshot_after = db_snapshot(db)
            payload = {
                "task": "task-10",
                "db": str(db_path),
                "months": args.months,
                "budget": args.budget,
                "started_at": started,
                "finished_at": utc_now_iso(),
                "elapsed_sec": round(time.monotonic() - t0, 1),
                "request_stats": dict(fetcher.stats),
                "collect": stats,
                "before": snapshot_before,
                "after": snapshot_after,
                "error": error,
            }
            _write_progress(progress_path, payload)
    if stats is not None and not error:
        # Task wording: report quotas / partial runs explicitly, then stop.
        print(f"[backfill] done in {payload['elapsed_sec']}s: "
              f"per_kind={json.dumps(stats.get('per_kind'), ensure_ascii=False)} "
              f"events_total={stats.get('events_total')} requests={stats.get('requests')}")
        if stats.get("warnings"):
            print("[backfill] warnings:")
            for warning in stats["warnings"]:
                print(f"  - {warning}")
        return 0
    print(f"[backfill] stopped: {error}")
    if stats is not None:
        print(f"[backfill] partial: per_kind={json.dumps(stats.get('per_kind'), ensure_ascii=False)} "
              f"requests={stats.get('requests')}")
        for warning in stats.get("warnings", []):
            print(f"  - {warning}")
    print(f"[backfill] progress saved to {progress_path}")
    return 0 if error and ("budget" in error or "quota" in error or "interrupted" in error) else 2


def report(args: argparse.Namespace) -> int:
    progress_path = Path(args.progress)
    with DB(args.db) as db:
        snapshot = db_snapshot(db)
    progress = _read_progress(progress_path)
    payload = {
        "db": str(args.db),
        "data": snapshot,
        "backfill": {
            "started_at": progress.get("started_at"),
            "finished_at": progress.get("finished_at"),
            "elapsed_sec": progress.get("elapsed_sec"),
            "months": progress.get("months"),
            "budget": progress.get("budget"),
            "request_stats": progress.get("request_stats"),
            "error": progress.get("error"),
            "collect_per_kind": (progress.get("collect") or {}).get("per_kind"),
            "warnings": (progress.get("collect") or {}).get("warnings"),
            "windows": (progress.get("collect") or {}).get("windows"),
            "product_codes": (progress.get("collect") or {}).get("product_codes"),
        },
    }
    print(json.dumps(payload, ensure_ascii=False, indent=1, default=str))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--db", default=str(DEFAULT_DB), help="SQLite store (default: data/medradar.sqlite)")
    parser.add_argument("--months", type=int, default=720, help="history window in months (720 = full history)")
    parser.add_argument("--budget", type=int, default=600, help="max openFDA requests for this run")
    parser.add_argument("--min-interval", type=float, default=0.3, help="seconds between HTTP requests")
    parser.add_argument("--timeout", type=float, default=45.0, help="HTTP timeout in seconds")
    parser.add_argument("--progress", default=str(DEFAULT_PROGRESS), help="progress/coverage JSON path")
    parser.add_argument("--report-only", action="store_true", help="print the post-backfill report and exit")
    parser.add_argument(
        "--kinds",
        default=None,
        help="targeted chunked mode: comma list of 510k,pma,device_recall (kill-safe, bounded memory)",
    )
    parser.add_argument("--chunk-months", type=int, default=48, help="date-window size for --kinds mode")
    args = parser.parse_args(argv)
    if args.report_only:
        return report(args)
    if args.kinds:
        return run_targeted(args)
    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())
