"""Single-writer lease for the observation ledger.

Two collectors writing the same SQLite file is not a concurrency problem to be
tolerated; it is a data-integrity problem. This module makes the invariant
explicit and testable:

* exactly one process may hold the collector lease at a time;
* a crashed holder is detected by heartbeat staleness (and pid liveness on the
  same host) and is taken over **with an audit record**, never silently;
* the lease is released on normal exit, on SIGINT/SIGTERM, and by the CLI
  ``observatory lock release --force`` escape hatch (which is itself recorded).

The lease file is plain JSON next to the ledger. It is operational state, not
research evidence, so it is excluded from backups.
"""

from __future__ import annotations

import json
import os
import socket
import sys
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Iterator

from .records import utc_now

LOCK_FILENAME = "collector.lock"
DEFAULT_STALE_SECONDS = 90.0
HEARTBEAT_SECONDS = 15.0


class LedgerLocked(RuntimeError):
    """Another live collector owns the ledger lease."""

    def __init__(self, holder: dict[str, Any] | None, message: str) -> None:
        super().__init__(message)
        self.holder = holder or {}


def _hostname() -> str:
    try:
        return socket.gethostname()
    except OSError:  # pragma: no cover
        return "unknown"


def _pid_alive(pid: int) -> bool:
    """Cross-platform pid liveness without third-party dependencies."""
    if pid <= 0:
        return False
    if os.name == "nt":
        import ctypes

        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        STILL_ACTIVE = 259
        kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
        handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, int(pid))
        if not handle:
            return False
        try:
            code = ctypes.c_ulong()
            ok = kernel32.GetExitCodeProcess(handle, ctypes.byref(code))
            return bool(ok) and code.value == STILL_ACTIVE
        finally:
            kernel32.CloseHandle(handle)
    try:
        os.kill(int(pid), 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _age_seconds(timestamp: str | None) -> float | None:
    if not timestamp:
        return None
    try:
        from datetime import datetime, timezone

        moment = datetime.fromisoformat(str(timestamp).replace("Z", "+00:00"))
        if moment.tzinfo is None:
            moment = moment.replace(tzinfo=timezone.utc)
        return max(0.0, (datetime.now(timezone.utc) - moment).total_seconds())
    except (TypeError, ValueError):
        return None


@dataclass
class LockInfo:
    pid: int
    host: str
    mode: str
    run_id: str | None
    started_at: str
    heartbeat_at: str
    source: str = ""
    command: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "LockInfo":
        return cls(
            pid=int(payload.get("pid") or 0),
            host=str(payload.get("host") or ""),
            mode=str(payload.get("mode") or ""),
            run_id=payload.get("run_id"),
            started_at=str(payload.get("started_at") or ""),
            heartbeat_at=str(payload.get("heartbeat_at") or ""),
            source=str(payload.get("source") or ""),
            command=str(payload.get("command") or ""),
        )


class CollectorLock:
    """Lease file with heartbeat; use :func:`acquire` or the context manager."""

    def __init__(self, ledger_path: str | Path, *, stale_seconds: float = DEFAULT_STALE_SECONDS) -> None:
        ledger = Path(ledger_path)
        self.ledger_path = ledger
        self.path = ledger.parent / LOCK_FILENAME
        self.stale_seconds = float(stale_seconds)
        self.info: LockInfo | None = None
        self._fd: int | None = None
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._lock = threading.RLock()

    # ------------------------------------------------------------------ introspection
    def read(self) -> dict[str, Any] | None:
        try:
            text = self.path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            return None
        try:
            payload = json.loads(text)
        except (TypeError, ValueError):
            return None
        return payload if isinstance(payload, dict) else None

    def status(self) -> dict[str, Any]:
        payload = self.read()
        if not payload:
            return {
                "held": False,
                "path": str(self.path),
                "stale": None,
                "holder": None,
                "heartbeat_age_seconds": None,
            }
        info = LockInfo.from_dict(payload)
        age = _age_seconds(info.heartbeat_at)
        same_host = info.host == _hostname()
        alive = _pid_alive(info.pid) if same_host else None
        stale = bool(age is None or age > self.stale_seconds or (same_host and not alive))
        return {
            "held": not stale,
            "path": str(self.path),
            "stale": stale,
            "alive_pid": alive,
            "heartbeat_age_seconds": round(age, 3) if age is not None else None,
            "holder": payload,
        }

    # ------------------------------------------------------------------- acquisition
    def acquire(self, *, mode: str, source: str = "", command: str = "",
                run_id: str | None = None, takeover: bool = True) -> LockInfo:
        payload = {
            "pid": os.getpid(),
            "host": _hostname(),
            "mode": mode,
            "source": source,
            "command": command,
            "run_id": run_id,
            "started_at": utc_now().replace(microsecond=0).isoformat(),
            "heartbeat_at": utc_now().replace(microsecond=0).isoformat(),
        }
        serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        for _attempt in range(3):
            try:
                fd = os.open(str(self.path), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
            except FileExistsError:
                existing = self.status()
                if existing["held"]:
                    raise LedgerLocked(
                        existing.get("holder"),
                        "another collector holds the ledger lease "
                        f"(pid={ (existing.get('holder') or {}).get('pid') }, "
                        f"host={ (existing.get('holder') or {}).get('host') }, "
                        f"heartbeat_age={existing.get('heartbeat_age_seconds')}s); "
                        "refusing to write the same ledger twice",
                    )
                if not takeover:
                    raise LedgerLocked(
                        existing.get("holder"),
                        "stale collector lease present; takeover disabled",
                    )
                # Stale lease: take it over, and record why (the audit trail matters).
                stale_payload = existing.get("holder") or {}
                _unlink_with_retry(self.path)
                self._record_takeover(stale_payload)
                continue
            os.write(fd, serialized.encode("utf-8"))
            try:
                os.fsync(fd)
            except OSError:  # pragma: no cover - odd filesystems
                pass
            # The lease is represented by the file + heartbeat, not by keeping an
            # open handle (Windows refuses to unlink a file whose handle is open,
            # which would make force-release and stale takeover impossible).
            try:
                os.close(fd)
            except OSError:  # pragma: no cover
                pass
            self._fd = None
            self.info = LockInfo.from_dict(payload)
            self._start_heartbeat()
            return self.info
        raise LedgerLocked(self.read(), "could not acquire the collector lease")

    def _record_takeover(self, stale: dict[str, Any]) -> None:
        """Append an audit record to the ledger runtime state (best effort, read-write)."""
        try:
            import sqlite3

            con = sqlite3.connect(str(self.ledger_path), timeout=30.0, isolation_level=None)
            try:
                con.execute("PRAGMA busy_timeout=30000")
                con.execute(
                    "CREATE TABLE IF NOT EXISTS runtime_state (key TEXT PRIMARY KEY, value TEXT,"
                    " updated_at TEXT)"
                )
                record = json.dumps(
                    {
                        "at": utc_now().replace(microsecond=0).isoformat(),
                        "reason": "stale collector lease taken over",
                        "previous": stale,
                        "by": {"pid": os.getpid(), "host": _hostname()},
                    },
                    ensure_ascii=False,
                )
                con.execute(
                    "INSERT INTO runtime_state(key, value, updated_at) VALUES('lock_recovery', ?, ?)"
                    " ON CONFLICT(key) DO UPDATE SET value=excluded.value,"
                    " updated_at=excluded.updated_at",
                    (record, utc_now().replace(microsecond=0).isoformat()),
                )
                con.commit()
            finally:
                con.close()
        except Exception:  # noqa: BLE001 - audit write must not block takeover
            pass

    # -------------------------------------------------------------------- heartbeat
    def heartbeat(self) -> None:
        with self._lock:
            if self.info is None:
                return
            self.info.heartbeat_at = utc_now().replace(microsecond=0).isoformat()
            try:
                self.path.write_text(
                    json.dumps(self.info.to_dict(), ensure_ascii=False, sort_keys=True),
                    encoding="utf-8",
                )
            except OSError:
                pass

    def _start_heartbeat(self) -> None:
        self._stop.clear()

        def _loop() -> None:
            while not self._stop.wait(HEARTBEAT_SECONDS):
                self.heartbeat()

        self._thread = threading.Thread(target=_loop, name="collector-lock-heartbeat", daemon=True)
        self._thread.start()

    # --------------------------------------------------------------------- release
    def release(self) -> None:
        self._stop.set()
        thread = self._thread
        if thread is not None and thread.is_alive():
            thread.join(timeout=2.0)
        with self._lock:
            if self._fd is not None:
                try:
                    os.close(self._fd)
                except OSError:
                    pass
                self._fd = None
            if self.info is not None:
                _unlink_with_retry(self.path)
            self.info = None
            self._thread = None

    def touch_run(self, run_id: str | None, source: str = "") -> None:
        with self._lock:
            if self.info is None:
                return
            self.info.run_id = run_id
            self.info.source = source
            self.heartbeat()

    # ---------------------------------------------------------------- context mgmt
    def __enter__(self) -> "CollectorLock":
        if self.info is None:
            raise RuntimeError("acquire() must be called before entering the lock context")
        return self

    def __exit__(self, *exc: Any) -> None:
        self.release()


@contextmanager
def hold_lock(ledger_path: str | Path, *, mode: str, source: str = "", command: str = "",
              run_id: str | None = None, stale_seconds: float = DEFAULT_STALE_SECONDS,
              takeover: bool = True) -> Iterator[CollectorLock]:
    lock = CollectorLock(ledger_path, stale_seconds=stale_seconds)
    lock.acquire(mode=mode, source=source, command=command, run_id=run_id, takeover=takeover)
    try:
        yield lock
    finally:
        lock.release()


def _unlink_with_retry(path: Path, attempts: int = 6, delay: float = 0.1) -> bool:
    """Windows can briefly hold a file open; deleting the lease is not optional."""
    for attempt in range(attempts):
        try:
            path.unlink()
            return True
        except FileNotFoundError:
            return True
        except OSError:
            if attempt == attempts - 1:
                return False
            time.sleep(delay)
    return False


def force_release(ledger_path: str | Path, *, reason: str) -> dict[str, Any]:
    """Operator escape hatch; records the action, then removes the lease."""
    lock = CollectorLock(ledger_path)
    previous = lock.read()
    if not _unlink_with_retry(lock.path):
        return {
            "released": False,
            "reason": "lease file could not be removed (still in use)",
            "previous": previous,
        }
    try:
        import sqlite3

        con = sqlite3.connect(str(ledger_path), timeout=30.0, isolation_level=None)
        try:
            con.execute("PRAGMA busy_timeout=30000")
            con.execute(
                "CREATE TABLE IF NOT EXISTS runtime_state (key TEXT PRIMARY KEY, value TEXT,"
                " updated_at TEXT)"
            )
            con.execute(
                "INSERT INTO runtime_state(key, value, updated_at) VALUES('lock_force_release', ?, ?)"
                " ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at",
                (
                    json.dumps(
                        {"at": utc_now().replace(microsecond=0).isoformat(),
                         "reason": reason, "previous": previous},
                        ensure_ascii=False,
                    ),
                    utc_now().replace(microsecond=0).isoformat(),
                ),
            )
            con.commit()
        finally:
            con.close()
    except Exception:  # noqa: BLE001
        pass
    return {"released": True, "previous": previous, "reason": reason}


__all__ = [
    "CollectorLock",
    "LedgerLocked",
    "LockInfo",
    "force_release",
    "hold_lock",
    "DEFAULT_STALE_SECONDS",
]


if __name__ == "__main__":  # pragma: no cover - tiny operational helper
    status = CollectorLock(sys.argv[1] if len(sys.argv) > 1 else "data/observatory/observatory.sqlite").status()
    print(json.dumps(status, ensure_ascii=False, indent=1))
    time.sleep(0)
