"""Host resource assessment shared by the web dataset activation and the FDA pipeline.

DATA-002 showed the failure mode this module exists for: the web process (~1.6 GB) and a
single-source reconciliation (~2.0 GB peak) can both be asked to run on a 3.7 GB host. The
kernel then swaps, and a request that should take 20 ms can take seconds. A per-unit
``MemoryMax`` cannot express "the *host* still has room", so both processes ask this module
before they start a memory-heavy operation.

The module is deliberately dependency-free and read-only: it reads ``/proc`` (Linux) or the
Win32 ``GlobalMemoryStatusEx`` counters (Windows, used by the test suite), plus the disk
budget. It never allocates a large object and never changes system state.

Two different decisions use it:

* the pipeline decides whether it may start a reconciliation (``PIPELINE_GUARD``);
* the web decides whether it may load a second dataset while the first is still serving
  (``ACTIVATION_GUARD``), and it asks the pipeline lock whether a sync is running.

Thresholds are calibrated in ``docs/data/data_003/RESOURCE_GUARDS.md``; they are not
guesses copied from a blog post.
"""
from __future__ import annotations

import calendar
import ctypes
import json
import os
import shutil
import sys
import time
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any


# --------------------------------------------------------------------------- memory facts
def _read_meminfo() -> dict[str, int]:
    values: dict[str, int] = {}
    try:
        with open("/proc/meminfo", "r", encoding="utf-8") as handle:
            for line in handle:
                key, _, rest = line.partition(":")
                if not rest:
                    continue
                try:
                    values[key] = int(rest.strip().split()[0])  # kB
                except (ValueError, IndexError):
                    continue
    except OSError:
        pass
    return values


def _read_psi() -> tuple[float | None, float | None, int | None]:
    """Linux pressure-stall information for memory: (some.avg10, full.avg10, some.total us)."""
    try:
        with open("/proc/pressure/memory", "r", encoding="utf-8") as handle:
            text = handle.read()
    except OSError:
        return (None, None, None)
    some = full = None
    total = None
    for line in text.splitlines():
        parts = line.split()
        if not parts:
            continue
        fields = {}
        for part in parts[1:]:
            key, _, value = part.partition("=")
            fields[key] = value
        if parts[0] == "some":
            some = float(fields.get("avg10", "nan"))
            try:
                total = int(fields.get("total", "0"))
            except ValueError:
                total = None
        elif parts[0] == "full":
            full = float(fields.get("avg10", "nan"))
    return (some, full, total)


def _read_oom_kills() -> int | None:
    try:
        with open("/proc/vmstat", "r", encoding="utf-8") as handle:
            for line in handle:
                if line.startswith("oom_kill "):
                    return int(line.split()[1])
    except OSError:
        pass
    return None


if sys.platform == "win32":  # pragma: no cover - test host only

    class _MEMORYSTATUSEX(ctypes.Structure):
        _fields_ = [
            ("dwLength", ctypes.c_uint32),
            ("dwMemoryLoad", ctypes.c_uint32),
            ("ullTotalPhys", ctypes.c_uint64),
            ("ullAvailPhys", ctypes.c_uint64),
            ("ullTotalPageFile", ctypes.c_uint64),
            ("ullAvailPageFile", ctypes.c_uint64),
            ("ullTotalVirtual", ctypes.c_uint64),
            ("ullAvailVirtual", ctypes.c_uint64),
            ("ullAvailExtendedVirtual", ctypes.c_uint64),
        ]

    def _win_memory() -> dict[str, int]:
        status = _MEMORYSTATUSEX()
        status.dwLength = ctypes.sizeof(status)
        if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
            return {}
        return {
            "MemTotal": status.ullTotalPhys // 1024,
            "MemAvailable": status.ullAvailPhys // 1024,
            "MemFree": status.ullAvailPhys // 1024,
            "SwapTotal": status.ullTotalPageFile // 1024,
            "SwapFree": status.ullAvailPageFile // 1024,
        }


@dataclass(frozen=True)
class MemorySnapshot:
    """One observation of host memory. All sizes are MiB unless stated otherwise."""

    total_mb: int
    available_mb: int
    free_mb: int
    swap_total_mb: int
    swap_free_mb: int
    swap_used_mb: int
    swap_cached_mb: int
    anon_mb: int
    psi_some_avg10: float | None
    psi_full_avg10: float | None
    oom_kills: int | None
    captured_at: float

    @property
    def supported(self) -> bool:
        return self.total_mb > 0

    def to_public(self) -> dict[str, Any]:
        return {
            "supported": self.supported,
            "captured_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(self.captured_at)),
            "mem_total_mb": self.total_mb,
            "mem_available_mb": self.available_mb,
            "mem_free_mb": self.free_mb,
            "swap_total_mb": self.swap_total_mb,
            "swap_free_mb": self.swap_free_mb,
            "swap_used_mb": self.swap_used_mb,
            "swap_cached_mb": self.swap_cached_mb,
            "anon_pages_mb": self.anon_mb,
            "psi_some_avg10": self.psi_some_avg10,
            "psi_full_avg10": self.psi_full_avg10,
            "oom_kills": self.oom_kills,
        }

    @classmethod
    def read(cls) -> "MemorySnapshot":
        if sys.platform == "win32":  # pragma: no cover - test host only
            raw = _win_memory()
            psi = (None, None)
            kills = None
        else:
            raw = _read_meminfo()
            psi_some, psi_full, _ = _read_psi()
            psi = (psi_some, psi_full)
            kills = _read_oom_kills()
        total = raw.get("MemTotal", 0) // 1024
        available = raw.get("MemAvailable", raw.get("MemFree", 0)) // 1024
        swap_total = raw.get("SwapTotal", 0) // 1024
        swap_free = raw.get("SwapFree", 0) // 1024
        return cls(
            total_mb=total,
            available_mb=available,
            free_mb=raw.get("MemFree", 0) // 1024,
            swap_total_mb=swap_total,
            swap_free_mb=swap_free,
            swap_used_mb=max(0, swap_total - swap_free),
            swap_cached_mb=raw.get("SwapCached", 0) // 1024,
            anon_mb=raw.get("AnonPages", 0) // 1024,
            psi_some_avg10=psi[0],
            psi_full_avg10=psi[1],
            oom_kills=kills,
            captured_at=time.time(),
        )


def process_rss_mb() -> int | None:
    """This process's anonymous resident size, the best cheap proxy for live dataset bytes."""
    if sys.platform == "win32":  # pragma: no cover - test host only
        return None
    try:
        with open("/proc/self/status", "r", encoding="utf-8") as handle:
            for line in handle:
                if line.startswith("RssAnon:"):
                    return int(line.split()[1]) // 1024
    except (OSError, ValueError):
        pass
    return None


# --------------------------------------------------------------------------- guard policy
@dataclass(frozen=True)
class GuardPolicy:
    """A named budget. ``required_mb`` is the extra room the operation itself will need."""

    name: str
    min_available_mb: int
    min_swap_free_mb: int = 256
    max_psi_some_avg10: float = 8.0
    required_mb: int = 0
    min_disk_free_mb: int = 0

    def with_required(self, required_mb: int) -> "GuardPolicy":
        return replace(self, required_mb=max(0, required_mb))


#: Starting a reconciliation needs room for the pipeline's own measured peak. DATA-002 measured
#: ~2.0 GiB for a recall reconciliation; the host should still keep a service floor afterwards.
PIPELINE_GUARD = GuardPolicy(
    name="pipeline_sync",
    min_available_mb=1200,
    min_swap_free_mb=384,
    max_psi_some_avg10=8.0,
    required_mb=0,
    min_disk_free_mb=2048,
)

#: Activating a new snapshot loads a second copy of the dataset while the old one serves.
#: ``required_mb`` is filled from the current anonymous RSS of the web process.
ACTIVATION_GUARD = GuardPolicy(
    name="web_activation",
    min_available_mb=384,
    min_swap_free_mb=192,
    max_psi_some_avg10=6.0,
    required_mb=0,
)


@dataclass(frozen=True)
class GuardDecision:
    allowed: bool
    policy: GuardPolicy
    snapshot: MemorySnapshot
    reasons: tuple[str, ...]
    disk_free_mb: int | None = None

    def to_public(self) -> dict[str, Any]:
        return {
            "allowed": self.allowed,
            "policy": {
                "name": self.policy.name,
                "min_available_mb": self.policy.min_available_mb,
                "min_swap_free_mb": self.policy.min_swap_free_mb,
                "max_psi_some_avg10": self.policy.max_psi_some_avg10,
                "required_mb": self.policy.required_mb,
                "min_disk_free_mb": self.policy.min_disk_free_mb,
            },
            "memory": self.snapshot.to_public(),
            "disk_free_mb": self.disk_free_mb,
            "reasons": list(self.reasons),
        }


def evaluate_guard(
    policy: GuardPolicy,
    *,
    snapshot: MemorySnapshot | None = None,
    disk_root: Path | str | None = None,
) -> GuardDecision:
    """Return whether ``policy`` is satisfied right now, with the reasons when it is not.

    An unsupported platform (no memory counters) is treated as *allowed* so the product keeps
    working on development machines; the reason list records that the check was unavailable.
    """
    snap = snapshot or MemorySnapshot.read()
    reasons: list[str] = []
    disk_free: int | None = None
    if disk_root is not None:
        try:
            disk_free = int(shutil.disk_usage(str(disk_root)).free // (1024 * 1024))
        except OSError:
            disk_free = None
    if not snap.supported:
        reasons.append("memory_counters_unavailable")
        return GuardDecision(True, policy, snap, tuple(reasons), disk_free)
    needed = policy.min_available_mb + policy.required_mb
    if snap.available_mb < needed:
        reasons.append("mem_available_below_floor")
    if snap.swap_total_mb > 0 and snap.swap_free_mb < policy.min_swap_free_mb:
        reasons.append("swap_free_below_floor")
    if snap.psi_some_avg10 is not None and snap.psi_some_avg10 > policy.max_psi_some_avg10:
        reasons.append("memory_pressure_high")
    if policy.min_disk_free_mb and disk_free is not None and disk_free < policy.min_disk_free_mb:
        reasons.append("disk_free_below_floor")
    return GuardDecision(not reasons, policy, snap, tuple(reasons), disk_free)


# --------------------------------------------------------------------------- cross-process
def pipeline_operation_active(lock_path: Path | str) -> bool:
    """True when another process holds the pipeline single-writer lock.

    The lock is an OS advisory lock, so probing it is exact and cannot be confused by a stale
    pid file. Opening the file does not truncate it; the flock is released immediately.
    """
    path = Path(lock_path)
    if not path.exists():
        return False
    if os.name == "nt":  # pragma: no cover - test host only
        # Windows: the single-writer lock is a byte-range lock, and a second handle may simply
        # fail to open the file while it is held. Both signals mean "someone is running".
        try:
            handle = path.open("a+b")
        except PermissionError:
            return True
        except OSError:
            return False
        try:
            import msvcrt

            handle.seek(0)
            if handle.read(1) == b"":
                return False
            handle.seek(0)
            try:
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError:
                return True
            else:
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                return False
        except OSError:
            return False
        finally:
            handle.close()
    try:
        import fcntl

        with path.open("rb") as handle:
            try:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError:
                return True
            finally:
                try:
                    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
                except OSError:
                    pass
    except OSError:
        return False
    return False


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if os.name == "nt":  # pragma: no cover - test host only
        return True
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


# --------------------------------------------------------------------------- activation file
ACTIVATION_SCHEMA = "medradar.dataset_activation.v1"
ACTIVATION_FILENAME = "activation.json"
ACTIVATION_STATES = ("loading", "loaded", "failed")
ACTIVATION_STALE_SECONDS = 1800


def activation_path(data_root: Path | str) -> Path:
    return Path(data_root) / ACTIVATION_FILENAME


def write_activation(
    data_root: Path | str,
    *,
    state: str,
    snapshot_id: str | None = None,
    started_at: str | None = None,
    finished_at: str | None = None,
    error: str | None = None,
    pid: int | None = None,
) -> dict[str, Any] | None:
    """Atomic, best-effort activation marker.

    Best effort on purpose: a read-only data directory must never turn a working activation
    into a failure. The in-process state is authoritative for the web; the file exists so the
    pipeline can see that a dataset switch is in flight.
    """
    payload = {
        "schema": ACTIVATION_SCHEMA,
        "state": state,
        "snapshot_id": snapshot_id,
        "started_at": started_at,
        "finished_at": finished_at,
        "error": error,
        "pid": pid if pid is not None else os.getpid(),
        "written_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    target = activation_path(data_root)
    try:
        temporary = target.with_suffix(".json.tmp")
        temporary.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        os.replace(temporary, target)
        return payload
    except OSError:
        return None


def read_activation(data_root: Path | str) -> dict[str, Any] | None:
    try:
        payload = json.loads(activation_path(data_root).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(payload, dict) or payload.get("schema") != ACTIVATION_SCHEMA:
        return None
    return payload


def activation_in_flight(data_root: Path | str, *, max_age_seconds: int = ACTIVATION_STALE_SECONDS) -> dict[str, Any] | None:
    """Return the marker only when it says a switch is in progress and it is not stale."""
    payload = read_activation(data_root)
    if payload is None or payload.get("state") != "loading":
        return None
    written = payload.get("written_at")
    age = None
    if isinstance(written, str):
        try:
            # written_at is UTC; time.mktime would read it as local time and shift the age by
            # the host offset, which made a fresh marker look stale on any non-UTC host.
            age = time.time() - calendar.timegm(time.strptime(written, "%Y-%m-%dT%H:%M:%SZ"))
        except ValueError:
            age = None
    if age is not None and age > max_age_seconds:
        return None
    return payload
