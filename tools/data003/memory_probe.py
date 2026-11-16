"""DATA-003 memory probe.

Measures the four memory states that DATA-003 must distinguish, on a real snapshot
and in an isolated process:

    import   -> modules imported, no dataset
    load     -> one Dataset built by load_dataset()
    queries  -> normal organization / event / metrics queries executed
    index    -> Dataset.device_index() built (warm device index)
    reload   -> a second Dataset built while the first is still referenced
    steady   -> old Dataset released, gc collected

Every stage records process RSS / peak RSS / swap, Python heap (tracemalloc) when
enabled, and object counts. The probe never writes to the data directory and never
touches a running server.

Usage:

    python tools/data003/memory_probe.py --data-dir .data/active --mode full
    python tools/data003/memory_probe.py --data-dir .data/active --mode full --tracemalloc
    python tools/data003/memory_probe.py --data-dir .data/active --mode reload --reloads 3

Output is one JSON document on stdout (and optionally --json-out).
"""
from __future__ import annotations

import argparse
import ctypes
import gc
import json
import os
import platform
import sys
import time
import tracemalloc
from collections import Counter
from pathlib import Path
from typing import Any, Callable

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


# --------------------------------------------------------------------------- metrics
def _read_proc_status() -> dict[str, int]:
    out: dict[str, int] = {}
    try:
        with open("/proc/self/status", "r", encoding="utf-8") as handle:
            for line in handle:
                if line.startswith(("VmRSS:", "VmHWM:", "VmSwap:", "VmSize:", "VmPeak:")):
                    key, rest = line.split(":", 1)
                    out[key.strip()] = int(rest.strip().split()[0]) * 1024
    except OSError:
        pass
    return out


if sys.platform == "win32":  # pragma: no cover - exercised by the benchmark host only
    import ctypes
    from ctypes import wintypes

    class _PROCESS_MEMORY_COUNTERS_EX(ctypes.Structure):
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
            ("PrivateUsage", ctypes.c_size_t),
        ]

    def _win_memory() -> dict[str, int]:
        counters = _PROCESS_MEMORY_COUNTERS_EX()
        counters.cb = ctypes.sizeof(counters)
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        get_info = kernel32.K32GetProcessMemoryInfo
        get_info.argtypes = [
            wintypes.HANDLE,
            ctypes.POINTER(_PROCESS_MEMORY_COUNTERS_EX),
            wintypes.DWORD,
        ]
        get_info.restype = wintypes.BOOL
        kernel32.GetCurrentProcess.restype = wintypes.HANDLE
        handle = kernel32.GetCurrentProcess()
        ok = get_info(handle, ctypes.byref(counters), counters.cb)
        if not ok:
            return {}
        return {
            "rss": int(counters.WorkingSetSize),
            "peak_rss": int(counters.PeakWorkingSetSize),
            "private": int(counters.PrivateUsage),
            "pagefile_peak": int(counters.PeakPagefileUsage),
        }


def memory() -> dict[str, int]:
    if sys.platform == "win32":
        return _win_memory()
    status = _read_proc_status()
    return {
        "rss": status.get("VmRSS", 0),
        "peak_rss": status.get("VmHWM", 0),
        "swap": status.get("VmSwap", 0),
    }


def trim_allocator() -> str:
    """Return malloc's retained free pages to the OS, when the platform supports it.

    Used only to separate "live Python objects" from "freed but retained by the
    allocator". Production code must not depend on it.
    """
    if sys.platform.startswith("linux"):
        try:
            libc = ctypes.CDLL("libc.so.6")
            released = int(libc.malloc_trim(0))
            return "malloc_trim=%d" % released
        except Exception as error:  # pragma: no cover - platform dependent
            return "malloc_trim unavailable: %s" % error
    return "unsupported-platform"


def heap() -> dict[str, int] | None:
    if not tracemalloc.is_tracing():
        return None
    current, peak = tracemalloc.get_traced_memory()
    return {"current": current, "peak": peak}


_GC_TRACKED_SKIP = (
    "list",
    "dict",
    "tuple",
    "set",
    "str",
    "int",
    "float",
    "bytes",
    "bool",
    "NoneType",
    "code",
    "cell",
    "function",
    "method_descriptor",
    "wrapper_descriptor",
    "getset_descriptor",
    "member_descriptor",
    "type",
    "module",
)


def object_counts() -> dict[str, int]:
    counts: Counter[str] = Counter()
    for item in gc.get_objects():
        counts[type(item).__name__] += 1
    return {name: count for name, count in counts.most_common(25)}


def top_allocations(limit: int = 12) -> list[dict[str, Any]]:
    if not tracemalloc.is_tracing():
        return []
    snapshot = tracemalloc.take_snapshot()
    out = []
    for stat in snapshot.statistics("lineno")[:limit]:
        frame = stat.traceback[0]
        out.append(
            {
                "file": frame.filename,
                "line": frame.lineno,
                "size": stat.size,
                "count": stat.count,
            }
        )
    return out


class Recorder:
    def __init__(self, label: str, tracemalloc_on: bool) -> None:
        self.label = label
        self.tracemalloc_on = tracemalloc_on
        self.stages: list[dict[str, Any]] = []
        self.started = time.perf_counter()

    def stage(self, name: str, **extra: Any) -> dict[str, Any]:
        record: dict[str, Any] = {
            "stage": name,
            "at_s": round(time.perf_counter() - self.started, 3),
            "memory": memory(),
        }
        mem = heap()
        if mem is not None:
            record["heap"] = mem
        record.update(extra)
        self.stages.append(record)
        print(
            "  [{label}] {name}: rss={rss:.1f}MB peak={peak:.1f}MB swap={swap:.1f}MB".format(
                label=self.label,
                name=name,
                rss=record["memory"].get("rss", 0) / 1e6,
                peak=record["memory"].get("peak_rss", 0) / 1e6,
                swap=record["memory"].get("swap", 0) / 1e6,
            ),
            file=sys.stderr,
        )
        return record

    def result(self, **extra: Any) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "probe": "data003.memory_probe.v1",
            "label": self.label,
            "python": sys.version.split()[0],
            "platform": platform.platform(),
            "tracemalloc": self.tracemalloc_on,
            "stages": self.stages,
        }
        payload.update(extra)
        return payload


def timed(func: Callable[[], Any]) -> tuple[Any, float]:
    started = time.perf_counter()
    value = func()
    return value, round((time.perf_counter() - started) * 1000.0, 1)


# --------------------------------------------------------------------------- workload
def run_queries(dataset: Any) -> dict[str, Any]:
    """The ordinary read workload that must not change PRODUCT semantics.

    Mirrors what the API does on a normal page load: search, the organization list,
    organization profiles, the event list with filters, and the metrics summary.
    """
    timings: dict[str, float] = {}

    def _measure(name: str, func: Callable[[], Any]) -> Any:
        started = time.perf_counter()
        value = func()
        timings[name + "_ms"] = round((time.perf_counter() - started) * 1000.0, 1)
        return value

    _measure("search", lambda: dataset.search("medtronic"))
    payload = _measure("organizations", dataset.organizations_payload)
    keys = [row["key"] for row in payload["organizations"]][:3]
    for key in keys:
        _measure("organization_" + key, lambda key=key: dataset.organization_profile(key))
    _measure(
        "events_recall",
        lambda: dataset.filter_events(org_keys=[], event_types=["recall"]),
    )
    _measure(
        "events_sorted",
        lambda: dataset.sort_events(dataset.filter_events(org_keys=keys), "date_desc"),
    )
    _measure("metrics", dataset.metrics_summary)
    return {"organizations": len(payload["organizations"]), "sample_keys": keys, "timings": timings}


def load_review_items(review_db: Path | None) -> Any:
    return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", required=True)
    parser.add_argument("--review-db", default=None)
    parser.add_argument("--mode", choices=["cold", "load", "full", "reload"], default="full")
    parser.add_argument("--reloads", type=int, default=1)
    parser.add_argument("--tracemalloc", action="store_true")
    parser.add_argument("--gc-counts", action="store_true")
    parser.add_argument("--trim", action="store_true", help="call malloc_trim after reload release")
    parser.add_argument("--json-out", default=None)
    parser.add_argument("--label", default=None)
    args = parser.parse_args(argv)

    label = args.label or ("%s/%s" % (args.mode, "tracemalloc" if args.tracemalloc else "rss"))
    if args.tracemalloc:
        tracemalloc.start(20)

    recorder = Recorder(label, args.tracemalloc)
    result_extra: dict[str, Any] = {"data_dir": str(Path(args.data_dir).resolve())}
    recorder.stage("process_start")
    if args.gc_counts:
        result_extra["objects_start"] = object_counts()

    from medradar.product import dataset as dataset_module

    recorder.stage("import")

    dataset, load_ms = timed(
        lambda: dataset_module.load_dataset(args.data_dir, review_db=args.review_db)
    )
    recorder.stage(
        "load",
        load_ms=load_ms,
        snapshot_id=dataset.snapshot_id,
        events=len(dataset.events),
        applicants=len(dataset.applicants),
        organizations=len(dataset.registry.organizations),
        top_allocations=top_allocations() if args.tracemalloc else [],
    )
    if args.gc_counts:
        result_extra["objects_load"] = object_counts()

    if args.mode in ("full", "reload"):
        workloads, queries_ms = timed(lambda: run_queries(dataset))
        recorder.stage("queries", queries_ms=queries_ms, workload=workloads)

        index, index_ms = timed(dataset.device_index)
        recorder.stage(
            "device_index",
            index_ms=index_ms,
            applications=len(index.applications),
            devices=len(index.devices),
            families=len(index.families),
            recalls=len(index.recalls),
            relations=len(index.relations),
            build_ms=dataset.device_index_build_ms,
            top_allocations=top_allocations() if args.tracemalloc else [],
        )
        if args.gc_counts:
            result_extra["objects_index"] = object_counts()

    reload_records: list[dict[str, Any]] = []
    if args.mode == "reload":
        # Model DatasetHolder exactly: one live dataset, and while the next one loads the
        # previous one is still referenced (that is what keeps the service alive if the new
        # snapshot is broken).
        holder: dict[str, Any] = {"current": dataset}
        del dataset  # the holder must be the only long-lived reference
        for attempt in range(1, args.reloads + 1):
            previous = holder["current"]
            fresh, reload_ms = timed(
                lambda: dataset_module.load_dataset(args.data_dir, review_db=args.review_db)
            )
            during = recorder.stage(
                "reload_%d_coexist" % attempt,
                reload_ms=reload_ms,
                old_snapshot=previous.snapshot_id,
                new_snapshot=fresh.snapshot_id,
                events=len(fresh.events),
            )
            new_index, new_index_ms = timed(fresh.device_index)
            during_peak = recorder.stage(
                "reload_%d_new_index" % attempt,
                index_ms=new_index_ms,
                applications=len(new_index.applications),
                devices=len(new_index.devices),
                relations=len(new_index.relations),
            )
            holder["current"] = fresh
            del previous
            gc.collect()
            after = recorder.stage("reload_%d_after_release" % attempt)
            trim_note = None
            if args.trim:
                trim_note = trim_allocator()
                recorder.stage("reload_%d_after_trim" % attempt, trim=trim_note)
            reload_records.append(
                {
                    "attempt": attempt,
                    "reload_ms": reload_ms,
                    "index_ms": new_index_ms,
                    "rss_before": during["memory"].get("rss", 0),
                    "rss_coexist": during_peak["memory"].get("rss", 0),
                    "peak_rss": during_peak["memory"].get("peak_rss", 0),
                    "rss_after_release": after["memory"].get("rss", 0),
                    "trim": trim_note,
                }
            )

    result_extra["reloads"] = reload_records
    result_extra["final"] = {
        "rss": memory().get("rss", 0),
        "peak_rss": memory().get("peak_rss", 0),
        "swap": memory().get("swap", 0),
        "heap": heap(),
    }
    payload = recorder.result(**result_extra)
    text = json.dumps(payload, indent=2, sort_keys=True)
    if args.json_out:
        Path(args.json_out).write_text(text, encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
