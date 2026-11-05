"""Local continuous collector loop (supervised-process friendly).

The honest framing matters: this is a *polling* watchdog, not a real-time feed.
It sleeps between passes, records a heartbeat so a human can tell it is alive,
skips passes while paused, backs off after consecutive failures, and never
pretends a missed pass did not happen (the ledger keeps the run history and the
watermark makes the next pass catch up).

Operational guarantees added for the reliability programme:

* the loop holds the **single-writer collector lease** for its whole lifetime, so a
  second collector (cron, task scheduler, a human) is refused instead of writing
  the same SQLite ledger twice;
* SIGTERM/SIGINT stop it gracefully: the current pass is allowed to finish, the
  lock is released and the heartbeat records ``stopped``;
* optional log file (rotated by date) in addition to stdout/journald;
* one `ops_metric` snapshot per pass (counts + ledger bytes) so storage growth can
  be charted without changing the research evidence.

GitHub Actions can run the same CLI; its cron can be delayed or dropped, which is
exactly why the watermark/checkpoint design does not depend on pass frequency.
"""

from __future__ import annotations

import json
import signal
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Sequence

from .ledger import ObservationLedger, default_ledger_path
from .lock import CollectorLock, LedgerLocked
from .records import RUN_FAILED
from .runner import sync


class _StopFlag:
    def __init__(self) -> None:
        self._event = threading.Event()

    def set(self, *_args: Any) -> None:
        self._event.set()

    def __call__(self) -> bool:
        return self._event.is_set()


def _make_logger(log: Callable[[str], None], log_file: str | Path | None) -> Callable[[str], None]:
    if not log_file:
        return log
    target = Path(log_file)
    target.parent.mkdir(parents=True, exist_ok=True)

    def emit(message: str) -> None:
        stamp = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
        line = f"{stamp} {message}\n"
        try:
            with open(target, "a", encoding="utf-8") as handle:
                handle.write(line)
                handle.flush()
        except OSError:
            pass
        try:
            log(message)
        except Exception:  # noqa: BLE001 - logging must never kill the loop
            pass

    return emit


def _install_signal_handlers(flag: _StopFlag) -> list[tuple[int, Any]]:
    previous: list[tuple[int, Any]] = []
    if threading.current_thread() is not threading.main_thread():
        return previous
    for signame in ("SIGTERM", "SIGINT"):
        signum = getattr(signal, signame, None)
        if signum is None:
            continue
        try:
            previous.append((signum, signal.getsignal(signum)))
            signal.signal(signum, flag.set)
        except (ValueError, OSError):  # pragma: no cover - exotic embedders
            continue
    return previous


def _restore_signal_handlers(previous: list[tuple[int, Any]]) -> None:
    for signum, handler in previous:
        try:
            signal.signal(signum, handler)
        except (ValueError, OSError):  # pragma: no cover
            continue


def _ops_snapshot(ledger: ObservationLedger) -> None:
    try:
        counts = ledger.counts()
        ledger.record_ops_metric(
            "daily_snapshot",
            {
                "observations": counts["observations"],
                "versions": counts["versions"],
                "changes": counts["changes"],
                "runs": counts["runs"],
                "db_bytes": counts["db_bytes"],
            },
        )
    except Exception:  # noqa: BLE001 - operational metric must not break collection
        pass


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
    log_file: str | Path | None = None,
    sleep: Callable[[float], None] = time.sleep,
    now: Callable[[], datetime] | None = None,
    stop: Callable[[], bool] | None = None,
    lock_stale_seconds: float = 90.0,
    acquire_lock: bool = True,
) -> dict[str, Any]:
    """Run ``cycles`` collection passes separated by ``interval_minutes``."""
    clock = now or (lambda: datetime.now(timezone.utc))
    interval_seconds = max(1.0, float(interval_minutes) * 60.0)
    ledger = ObservationLedger(ledger_path)
    emit = _make_logger(log, log_file)
    flag = _StopFlag()
    previous_handlers = _install_signal_handlers(flag)
    lock: CollectorLock | None = None
    passive_stop = stop

    def should_stop() -> bool:
        return flag() or (passive_stop is not None and passive_stop())

    started_at = clock().replace(microsecond=0).isoformat()
    passes: list[dict[str, Any]] = []
    cycles_done = 0
    failures = 0
    try:
        if acquire_lock:
            lock = CollectorLock(ledger.path, stale_seconds=lock_stale_seconds)
            try:
                lock.acquire(mode="watch", command="observatory watch")
            except LedgerLocked as exc:
                emit(f"[observatory] refusing to start: {exc}")
                return {
                    "status": "LOCKED",
                    "locked": True,
                    "lock_holder": exc.holder,
                    "passes": [],
                    "cycles": 0,
                    "failures": 0,
                    "started_at": started_at,
                    "finished_at": clock().replace(microsecond=0).isoformat(),
                    "ledger": str(ledger.path),
                }
        ledger.heartbeat(
            {
                "state": "started",
                "interval_minutes": interval_minutes,
                "pid": __import__("os").getpid(),
                "checked_at": started_at,
            }
        )
        emit(f"[observatory] watch started at {started_at} (interval {interval_minutes} min)")
        while cycles is None or cycles_done < cycles:
            if should_stop():
                emit("[observatory] stop requested; finishing gracefully")
                break
            cycle_started = clock().replace(microsecond=0)
            if ledger.is_paused():
                emit("[observatory] collector paused; skipping pass")
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
                emit(f"[observatory] pass {cycles_done + 1} starting at {cycle_started.isoformat()}")
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
                        # The watcher already holds the single-writer lease for its
                        # whole lifetime; asking sync to acquire it again would make
                        # every pass refuse itself. (When --no-lock is explicit, sync
                        # acquires on its own.)
                        acquire_lock=lock is None,
                        log=emit,
                    )
                    ok = bool(report.get("ok"))
                    failures = 0 if ok else failures + 1
                    if lock is not None:
                        lock.heartbeat()
                    ledger.heartbeat(
                        {
                            "state": "ok" if ok else "degraded",
                            "cycle": cycles_done + 1,
                            "interval_minutes": interval_minutes,
                            "checked_at": clock().replace(microsecond=0).isoformat(),
                            "totals": report.get("totals"),
                        }
                    )
                    _ops_snapshot(ledger)
                    passes.append(
                        {
                            "cycle": cycles_done + 1,
                            "status": "OK" if ok else "DEGRADED",
                            "started_at": cycle_started.isoformat(),
                            "finished_at": report.get("finished_at"),
                            "locked": bool(report.get("locked")),
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
                    emit(f"[observatory] pass failed: {message}")
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
            emit(f"[observatory] next pass at {next_at.isoformat()} (sleep {wait_seconds:.0f}s)")
            _sleep_interruptible(wait_seconds, sleep, should_stop)
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
        try:
            ledger.heartbeat(
                {
                    "state": "stopped",
                    "cycles": cycles_done,
                    "checked_at": clock().replace(microsecond=0).isoformat(),
                }
            )
        except Exception:  # noqa: BLE001
            pass
        if lock is not None:
            lock.release()
        _restore_signal_handlers(previous_handlers)
        ledger.close()


def _sleep_interruptible(seconds: float, sleep: Callable[[float], None],
                         stop: Callable[[], bool] | None) -> None:
    remaining = float(seconds)
    while remaining > 0:
        if stop is not None and stop():
            return
        chunk = min(1.0, remaining)
        sleep(chunk)
        remaining -= chunk


def pause_ledger(*, ledger_path: str | Path | None = None, reason: str) -> dict[str, Any]:
    """Pause collection (recorded in the ledger so cron/systemd/manual all obey)."""
    from .runner import pause

    return pause(reason=reason, ledger_path=ledger_path)


def resume_ledger(*, ledger_path: str | Path | None = None) -> dict[str, Any]:
    from .runner import resume

    return resume(ledger_path=ledger_path)


def default_path() -> Path:
    return default_ledger_path()
