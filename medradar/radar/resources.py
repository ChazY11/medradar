"""Host resource measurements and guards, with no hard third-party dependency.

The production host is 2 vCPU / 4 GB. The rules that keep the radar from hurting it:

* **discovery never waits for AI.** The AI stage is deferred when memory is tight; ingest and
  the graph are not.
* **AI is a separate process**, started for one batch and torn down, so a model cannot hold
  memory between cycles.
* **the guard is measured, not assumed** - available memory is read from the OS every time,
  and a deferral is recorded with the numbers that produced it.

``psutil`` is used when present, because it reports the figure the rest of the system sees.
Without it, the platform primitives are used directly; if neither is available the guard
returns ``unknown`` and AI is *not* deferred (an unknown guard must not silently disable a
feature), but the deferral reason is recorded so the state is visible.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


def available_memory_mb() -> float | None:
    try:
        import psutil  # type: ignore

        return round(psutil.virtual_memory().available / (1024 * 1024), 1)
    except Exception:
        pass
    if sys.platform.startswith("win"):
        return _windows_available_mb()
    if os.name == "posix":
        return _proc_available_mb()
    return None


def total_memory_mb() -> float | None:
    try:
        import psutil  # type: ignore

        return round(psutil.virtual_memory().total / (1024 * 1024), 1)
    except Exception:
        pass
    if sys.platform.startswith("win"):
        return _windows_total_mb()
    if os.name == "posix":
        return _proc_total_mb()
    return None


def _windows_memory() -> tuple[float | None, float | None]:
    import ctypes

    class MEMORYSTATUSEX(ctypes.Structure):
        _fields_ = [
            ("dwLength", ctypes.c_ulong),
            ("dwMemoryLoad", ctypes.c_ulong),
            ("ullTotalPhys", ctypes.c_ulonglong),
            ("ullAvailPhys", ctypes.c_ulonglong),
            ("ullTotalPageFile", ctypes.c_ulonglong),
            ("ullAvailPageFile", ctypes.c_ulonglong),
            ("ullTotalVirtual", ctypes.c_ulonglong),
            ("ullAvailVirtual", ctypes.c_ulonglong),
            ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
        ]

    status = MEMORYSTATUSEX()
    status.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
    if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):  # type: ignore[attr-defined]
        return None, None
    return (round(status.ullAvailPhys / (1024 * 1024), 1), round(status.ullTotalPhys / (1024 * 1024), 1))


def _windows_available_mb() -> float | None:
    return _windows_memory()[0]


def _windows_total_mb() -> float | None:
    return _windows_memory()[1]


def _proc_meminfo() -> dict[str, float]:
    values: dict[str, float] = {}
    try:
        for line in Path("/proc/meminfo").read_text(encoding="utf-8").splitlines():
            key, _, rest = line.partition(":")
            parts = rest.strip().split()
            if parts and parts[0].isdigit():
                values[key] = float(parts[0]) / 1024.0
    except OSError:
        pass
    return values


def _proc_available_mb() -> float | None:
    info = _proc_meminfo()
    return round(info["MemAvailable"], 1) if "MemAvailable" in info else None


def _proc_total_mb() -> float | None:
    info = _proc_meminfo()
    return round(info["MemTotal"], 1) if "MemTotal" in info else None


def cpu_count() -> int:
    try:
        return max(1, len(os.sched_getaffinity(0)))  # type: ignore[attr-defined]
    except Exception:
        return max(1, os.cpu_count() or 1)


def load_average() -> float | None:
    try:
        return round(os.getloadavg()[0], 2)  # type: ignore[attr-defined]
    except Exception:
        return None


def disk_free_mb(path: Path | str) -> float | None:
    try:
        return round(shutil.disk_usage(str(path)).free / (1024 * 1024), 1)
    except OSError:
        return None


@dataclass
class ResourceSnapshot:
    available_mb: float | None
    total_mb: float | None
    cpus: int
    load_average: float | None
    disk_free_mb: float | None

    def as_dict(self) -> dict[str, Any]:
        return {
            "available_mb": self.available_mb,
            "total_mb": self.total_mb,
            "cpus": self.cpus,
            "load_average": self.load_average,
            "disk_free_mb": self.disk_free_mb,
            "guard_basis": "psutil when installed, else the OS primitive",
        }


def snapshot(data_dir: Path | str | None = None) -> ResourceSnapshot:
    return ResourceSnapshot(
        available_mb=available_memory_mb(),
        total_mb=total_memory_mb(),
        cpus=cpu_count(),
        load_average=load_average(),
        disk_free_mb=disk_free_mb(data_dir) if data_dir else None,
    )


@dataclass
class GuardDecision:
    allowed: bool
    reason: str
    detail: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return {"allowed": self.allowed, "reason": self.reason, **self.detail}


class ResourceGuard:
    """Decide whether the optional AI stage may run right now.

    Two independent thresholds:

    ``min_available_mb``
        An absolute floor. Below it, a model load would risk the OOM killer on a 4 GB host.
    ``min_available_fraction``
        A relative floor, so the guard also holds on a small CI box and on a large dev host
        that is already busy.

    A deferral is *not* a failure: the backlog keeps growing, discovery continues, and the next
    cycle retries.
    """

    def __init__(
        self,
        *,
        min_available_mb: float = 900.0,
        min_available_fraction: float = 0.22,
        min_disk_free_mb: float = 512.0,
    ) -> None:
        self.min_available_mb = float(min_available_mb)
        self.min_available_fraction = float(min_available_fraction)
        self.min_disk_free_mb = float(min_disk_free_mb)

    def evaluate(self, data_dir: Path | str | None = None, *,
                 estimated_model_mb: float = 0.0) -> GuardDecision:
        snap = snapshot(data_dir)
        detail = snap.as_dict() | {"estimated_model_mb": estimated_model_mb,
                                   "min_available_mb": self.min_available_mb,
                                   "min_available_fraction": self.min_available_fraction}
        if snap.available_mb is None:
            return GuardDecision(True, "available memory unknown; the guard does not block", detail)
        needed = max(self.min_available_mb, (snap.total_mb or 0) * self.min_available_fraction)
        needed = max(needed, estimated_model_mb * 1.5 if estimated_model_mb else needed)
        if snap.available_mb < needed:
            detail["needed_mb"] = round(needed, 1)
            return GuardDecision(
                False,
                f"available memory {snap.available_mb} MB is below the {round(needed, 1)} MB floor",
                detail,
            )
        if snap.disk_free_mb is not None and snap.disk_free_mb < self.min_disk_free_mb:
            detail["needed_disk_mb"] = self.min_disk_free_mb
            return GuardDecision(
                False,
                f"free disk {snap.disk_free_mb} MB is below the {self.min_disk_free_mb} MB floor",
                detail,
            )
        detail["needed_mb"] = round(needed, 1)
        return GuardDecision(True, "resource guard satisfied", detail)


def set_low_priority() -> dict[str, Any]:
    """Lower this process's priority so a batch cannot starve the web process.

    Best effort by design: a platform where this is unavailable reports ``applied_on: none``
    instead of pretending it lowered anything.
    """
    info: dict[str, Any] = {"platform": sys.platform, "applied_on": "none"}
    try:
        if os.name == "nt":
            import ctypes

            below_normal = 0x00004000
            idle = 0x00000040
            handle = ctypes.windll.kernel32.GetCurrentProcess()  # type: ignore[attr-defined]
            ok = ctypes.windll.kernel32.SetPriorityClass(handle, below_normal)  # type: ignore[attr-defined]
            info.update({"applied_on": "process", "api": "SetPriorityClass",
                         "class": "BELOW_NORMAL_PRIORITY_CLASS", "ok": bool(ok)})
        else:
            os.nice(10)
            info.update({"applied_on": "process", "api": "os.nice", "niceness": 10, "ok": True})
    except Exception as error:  # pragma: no cover - platform dependent
        info["error"] = f"{type(error).__name__}: {error}"
    return info


def peak_rss_mb() -> float | None:
    """Peak resident set size of this process, in MB, when the OS exposes it."""
    try:
        import psutil  # type: ignore

        return round(psutil.Process().memory_info().rss / (1024 * 1024), 1)
    except Exception:
        pass
    if os.name == "posix":
        try:
            import resource

            return round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0, 1)
        except Exception:
            return None
    if sys.platform.startswith("win"):
        try:
            import ctypes
            from ctypes import wintypes

            class PROCESS_MEMORY_COUNTERS(ctypes.Structure):
                _fields_ = [
                    ("cb", wintypes.DWORD),
                    ("PageFaultCount", wintypes.DWORD),
                    ("PeakWorkingSetSize", ctypes.c_size_t),
                    ("WorkingSetSize", ctypes.c_size_t),
                    ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                    ("PagefileUsage", ctypes.c_size_t),
                    ("PeakPagefileUsage", ctypes.c_size_t),
                ]

            counters = PROCESS_MEMORY_COUNTERS()
            counters.cb = ctypes.sizeof(PROCESS_MEMORY_COUNTERS)
            handle = ctypes.windll.kernel32.GetCurrentProcess()  # type: ignore[attr-defined]
            if ctypes.windll.psapi.GetProcessMemoryInfo(  # type: ignore[attr-defined]
                handle, ctypes.byref(counters), counters.cb
            ):
                return round(counters.PeakWorkingSetSize / (1024 * 1024), 1)
        except Exception:
            return None
    return None


def command_output(command: list[str], timeout: float = 5.0) -> str | None:
    try:
        completed = subprocess.run(command, capture_output=True, text=True, timeout=timeout,
                                   check=False)
        return completed.stdout.strip() or None
    except Exception:
        return None
