"""Local continuous collector loop.

The honest framing matters: this is a *polling* watchdog, not a real-time feed.
It sleeps between passes, records a heartbeat so a human can tell it is alive,
skips passes while paused, backs off after consecutive failures, and never
pretends a missed pass did not happen (the ledger keeps the run history and the
watermark makes the next pass catch up).

GitHub Actions can run the same command; its cron can be delayed or dropped, which
is exactly why the watermark/checkpoint design does not depend on pass frequency.
"""

from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Mapping, Sequence

from .ledger import ObservationLedger
from .records import RUN_FAILED
from .runner import sync


def watch(
    *,
    interval_minutes: float = 60.0,
    cycles: int | None = None,
    sources: Sequence[str] | None = None,
    companies: Sequence[str] | None = None,
    all_companies: bool = False,
    since_days: int = 30,
    ledger_path: str | None = None,
    max_requests: int = 600,
    min_interval: float = 0.25,
    trigger: str = "schedule",
    log: Callable[[str], None] = print,
    sleep: Callable[[float], None] = time.sleep,
    now: Callable[[], datetime] | None = None,
    stop: Callable[[], bool] | None = None,
) -> dict[str, Any]:
    """Run ``cycles`` collection passes separated by ``interval_minutes``."""
    clock = now or (lambda: datetime.now(timezone.utc))
    interval_seconds = max(1.0, float(interval_minutes) * 60.0)
    ledger = ObservationLedger(ledger_path)
    cycles_done = 0
    failures = 0
    passes: list[dict[str, Any]] = []
    started_at = clock().replace(microsecond=0).isoformat()
    try:
        while cycles is None or cycles_done < cycles:
            if stop is not None and stop():
                log("[observatory] stop requested")
                break
            cycle_started = clock().replace(microsecond=0)
            if ledger.is_paused():
                log("[observatory] collector paused; skipping pass")
                ledger.heartbeat(
                    {
                        "state": "paused",
                        "cycle": cycles_done + 1,
                        "interval_minutes": interval_minutes,
                        "checked_at": cycle_started.isoformat(),
                    }
                )
                passes.append({"cycle": cycles_done + 1, "status": "PAUSED",
                               "started_at": cycle_started.isoformat()})
            else:
                log(f"[observatory] pass {cycles_done + 1} starting at {cycle_started.isoformat()}")
                try:
                    report = sync(
                        sources=sources,
                        companies=companies,
                        all_companies=all_companies,
                        since_days=since_days,
                        trigger=trigger,
                        max_requests=max_requests,
                        min_interval=min_interval,
                        ledger=ledger,
                        log=log,
                    )
                    ok = bool(report.get("ok"))
                    failures = 0 if ok else failures + 1
                    ledger.heartbeat(
                        {
                            "state": "ok" if ok else "degraded",
                            "cycle": cycles_done + 1,
                            "interval_minutes": interval_minutes,
                            "checked_at": clock().replace(microsecond=0).isoformat(),
                            "totals": report.get("totals"),
                        }
                    )
                    passes.append(
                        {
                            "cycle": cycles_done + 1,
                            "status": "OK" if ok else "DEGRADED",
                            "started_at": cycle_started.isoformat(),
                            "finished_at": report.get("finished_at"),
                            "totals": report.get("totals"),
                            "sources": {
                                key: value.get("status")
                                for key, value in report.get("sources", {}).items()
                            },
                        }
                    )
                except Exception as exc:  # noqa: BLE001 - the loop must survive one bad pass
                    failures += 1
                    message = f"{type(exc).__name__}: {exc}"
                    log(f"[observatory] pass failed: {message}")
                    ledger.record_failure("scheduler", kind="SCOPE_ERROR", message=message)
                    ledger.heartbeat(
                        {
                            "state": "failed",
                            "cycle": cycles_done + 1,
                            "checked_at": clock().replace(microsecond=0).isoformat(),
                            "error": message,
                        }
                    )
                    passes.append(
                        {"cycle": cycles_done + 1, "status": "FAILED",
                         "started_at": cycle_started.isoformat(), "error": message}
                    )
            cycles_done += 1
            if cycles is not None and cycles_done >= cycles:
                break
            wait_seconds = interval_seconds * (2 ** min(failures, 3))
            next_at = clock().replace(microsecond=0) + timedelta(seconds=wait_seconds)
            ledger.heartbeat(
                {
                    "state": "sleeping",
                    "cycle": cycles_done,
                    "interval_minutes": interval_minutes,
                    "next_pass_at": next_at.isoformat(),
                    "checked_at": clock().replace(microsecond=0).isoformat(),
                }
            )
            log(f"[observatory] next pass at {next_at.isoformat()} (sleep {wait_seconds:.0f}s)")
            _sleep_interruptible(wait_seconds, sleep, stop)
        return {
            "passes": passes,
            "cycles": cycles_done,
            "failures": failures,
            "started_at": started_at,
            "finished_at": clock().replace(microsecond=0).isoformat(),
            "ledger": str(ledger.path),
            "status": "OK" if failures == 0 else "DEGRADED",
        }
    finally:
        ledger.close()


def _sleep_interruptible(seconds: float, sleep: Callable[[float], None],
                         stop: Callable[[], bool] | None) -> None:
    remaining = float(seconds)
    while remaining > 0:
        if stop is not None and stop():
            return
        chunk = min(5.0, remaining)
        sleep(chunk)
        remaining -= chunk
