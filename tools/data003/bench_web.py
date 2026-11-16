"""DATA-003 web benchmark: latency, availability and server memory under snapshot switches.

The harness starts a real ``python -m medradar.product.web`` process from a chosen tree,
pre-warms the device index, then drives concurrent HTTP requests through a fixed endpoint
mix while (optionally) switching the active snapshot underneath it. It records per-endpoint
latency percentiles, failures, request stalls, and the server's RSS over time.

Everything runs on loopback against a *copy* of a data root. No production endpoint is ever
contacted.

Examples
--------

    python tools/data003/bench_web.py --data-root ../data003-work/pipeline-root \
        --duration 30 --concurrency 4 --switch-at 8 --json-out bench.json

    python tools/data003/bench_web.py --repo-root ../data003-baseline --label baseline ...
"""
from __future__ import annotations

import argparse
import ctypes
import http.client
import json
import os
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]

ENDPOINTS = [
    ("home", 1, "/"),
    ("organizations", 2, "/api/organizations"),
    ("organization", 2, "/api/organizations/medtronic"),
    ("events", 2, "/api/events?page_size=25"),
    ("devices", 2, "/api/devices?page_size=25"),
    ("device_quality", 1, "/api/devices/quality"),
    ("device_family", 1, "/api/device-families/family:pma:P980016"),
    ("compare", 1, "/api/compare?orgs=medtronic,abbott"),
    ("data_status", 1, "/api/data-status"),
    ("health", 1, "/api/health"),
    ("search", 1, "/api/search?q=medtronic"),
    ("meta", 1, "/api/meta"),
]


# --------------------------------------------------------------------------- sampling
if sys.platform == "win32":  # pragma: no cover - benchmark host only
    class _PMC(ctypes.Structure):
        _fields_ = [
            ("cb", ctypes.c_uint32),
            ("PageFaultCount", ctypes.c_uint32),
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

    def process_memory(pid: int) -> dict[str, int]:
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        psapi = ctypes.WinDLL("psapi", use_last_error=True)
        kernel32.OpenProcess.restype = ctypes.c_void_p
        kernel32.OpenProcess.argtypes = [ctypes.c_uint32, ctypes.c_int, ctypes.c_uint32]
        handle = kernel32.OpenProcess(0x1000 | 0x0400, False, pid)
        if not handle:
            return {}
        try:
            counters = _PMC()
            counters.cb = ctypes.sizeof(counters)
            psapi.GetProcessMemoryInfo.argtypes = [ctypes.c_void_p, ctypes.POINTER(_PMC), ctypes.c_uint32]
            if not psapi.GetProcessMemoryInfo(handle, ctypes.byref(counters), counters.cb):
                return {}
            return {
                "rss": int(counters.WorkingSetSize),
                "peak_rss": int(counters.PeakWorkingSetSize),
                "private": int(counters.PrivateUsage),
            }
        finally:
            kernel32.CloseHandle(ctypes.c_void_p(handle))

else:  # pragma: no cover - production shape
    def process_memory(pid: int) -> dict[str, int]:
        values: dict[str, int] = {}
        try:
            with open(f"/proc/{pid}/status", "r", encoding="utf-8") as handle:
                for line in handle:
                    if line.startswith(("VmRSS:", "VmHWM:", "VmSwap:")):
                        key, rest = line.split(":", 1)
                        values[key.strip()] = int(rest.strip().split()[0]) * 1024
        except OSError:
            return {}
        return {
            "rss": values.get("VmRSS", 0),
            "peak_rss": values.get("VmHWM", 0),
            "swap": values.get("VmSwap", 0),
        }


def child_pids(pid: int) -> list[int]:
    """Direct children of ``pid``.

    On Windows the venv's ``python.exe`` is a trampoline, so the process that serves HTTP is a
    child of the PID returned by Popen. Sampling only ``Popen.pid`` would report the trampoline's
    few MB and hide the dataset. Linux production has no trampoline, but the tree walk is cheap
    and keeps the harness honest on both.
    """
    if sys.platform == "win32":  # pragma: no cover - benchmark host only
        TH32CS_SNAPPROCESS = 0x00000002

        class PROCESSENTRY32(ctypes.Structure):
            _fields_ = [
                ("dwSize", ctypes.c_uint32),
                ("cntUsage", ctypes.c_uint32),
                ("th32ProcessID", ctypes.c_uint32),
                ("th32DefaultHeapID", ctypes.c_void_p),
                ("th32ModuleID", ctypes.c_uint32),
                ("cntThreads", ctypes.c_uint32),
                ("th32ParentProcessID", ctypes.c_uint32),
                ("pcPriClassBase", ctypes.c_long),
                ("dwFlags", ctypes.c_uint32),
                ("szExeFile", ctypes.c_char * 260),
            ]

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.CreateToolhelp32Snapshot.restype = ctypes.c_void_p
        snapshot = kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
        if snapshot in (None, ctypes.c_void_p(-1).value):
            return []
        children: list[int] = []
        try:
            entry = PROCESSENTRY32()
            entry.dwSize = ctypes.sizeof(entry)
            ok = kernel32.Process32First(ctypes.c_void_p(snapshot), ctypes.byref(entry))
            while ok:
                if entry.th32ParentProcessID == pid:
                    children.append(int(entry.th32ProcessID))
                ok = kernel32.Process32Next(ctypes.c_void_p(snapshot), ctypes.byref(entry))
        finally:
            kernel32.CloseHandle(ctypes.c_void_p(snapshot))
        return children
    children = []
    try:
        for name in os.listdir("/proc"):
            if not name.isdigit():
                continue
            try:
                with open(f"/proc/{name}/stat", "r", encoding="utf-8") as handle:
                    fields = handle.read().split()
                if len(fields) > 3 and int(fields[3]) == pid:
                    children.append(int(name))
            except (OSError, ValueError):
                continue
    except OSError:
        return []
    return children


def process_tree_memory(pid: int) -> dict[str, int]:
    """Memory of ``pid`` and every descendant: sum, and the largest single process."""
    total = {"rss": 0, "peak_rss": 0, "swap": 0}
    largest = 0
    frontier = [pid]
    seen: set[int] = set()
    while frontier:
        current = frontier.pop()
        if current in seen:
            continue
        seen.add(current)
        memory = process_memory(current)
        if memory:
            rss = memory.get("rss", 0)
            total["rss"] += rss
            total["peak_rss"] += memory.get("peak_rss", 0)
            total["swap"] += memory.get("swap", 0)
            largest = max(largest, rss)
        frontier.extend(child_pids(current))
        if len(seen) > 64:
            break
    total["largest_rss"] = largest
    return total


class Sampler:
    def __init__(self, pid: int, interval: float = 0.25) -> None:
        self.pid = pid
        self.interval = interval
        self.samples: list[dict[str, Any]] = []
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, name="mem-sampler", daemon=True)

    def _run(self) -> None:
        started = time.perf_counter()
        while not self._stop.is_set():
            snapshot = process_tree_memory(self.pid)
            snapshot["t"] = round(time.perf_counter() - started, 3)
            if snapshot.get("rss"):
                self.samples.append(snapshot)
            self._stop.wait(self.interval)

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._thread.join(5)

    def summary(self) -> dict[str, Any]:
        rss = [s.get("rss", 0) for s in self.samples if s.get("rss")]
        return {
            "samples": len(self.samples),
            "rss_start": rss[0] if rss else None,
            "rss_max": max(rss) if rss else None,
            "rss_end": rss[-1] if rss else None,
            "largest_process_max": max((s.get("largest_rss", 0) for s in self.samples), default=None),
            "peak_rss": max((s.get("peak_rss", 0) for s in self.samples), default=None),
            "swap_max": max((s.get("swap", 0) for s in self.samples), default=None),
        }


# --------------------------------------------------------------------------- load
@dataclass
class RequestResult:
    endpoint: str
    status: int | None
    ms: float
    error: str | None
    at: float


@dataclass
class Stats:
    results: list[RequestResult] = field(default_factory=list)
    lock: threading.Lock = field(default_factory=threading.Lock)

    def add(self, result: RequestResult) -> None:
        with self.lock:
            self.results.append(result)

    def summary(self) -> dict[str, Any]:
        by: dict[str, list[float]] = {}
        errors = 0
        server_errors = 0
        timeouts = 0
        slow = 0
        for row in self.results:
            by.setdefault(row.endpoint, []).append(row.ms)
            if row.error:
                errors += 1
                if "timed out" in row.error:
                    timeouts += 1
            elif row.status and row.status >= 500:
                server_errors += 1
            if row.ms >= 1000.0:
                slow += 1
        all_ms = sorted(row.ms for row in self.results)

        def pct(values: list[float], p: float) -> float | None:
            if not values:
                return None
            index = min(len(values) - 1, max(0, int(round((p / 100.0) * len(values))) - 1))
            return round(values[index], 2)

        return {
            "requests": len(self.results),
            "errors": errors,
            "timeouts": timeouts,
            "http_5xx": server_errors,
            "slow_over_1s": slow,
            "p50_ms": pct(all_ms, 50),
            "p95_ms": pct(all_ms, 95),
            "p99_ms": pct(all_ms, 99),
            "max_ms": round(all_ms[-1], 2) if all_ms else None,
            "by_endpoint": {
                name: {
                    "n": len(vals),
                    "p50_ms": pct(sorted(vals), 50),
                    "p95_ms": pct(sorted(vals), 95),
                    "max_ms": round(max(vals), 2),
                }
                for name, vals in sorted(by.items())
            },
        }


class Driver:
    def __init__(self, host: str, port: int, stats: Stats, stop: threading.Event,
                 concurrency: int, timeout: float = 20.0, think_ms: float = 0.0) -> None:
        self.host = host
        self.port = port
        self.stats = stats
        self.stop = stop
        self.concurrency = concurrency
        self.timeout = timeout
        self.think_ms = think_ms
        self.started = time.perf_counter()
        self._threads = [
            threading.Thread(target=self._worker, args=(index,), name=f"load-{index}", daemon=True)
            for index in range(concurrency)
        ]

    def start(self) -> None:
        for thread in self._threads:
            thread.start()

    def join(self) -> None:
        for thread in self._threads:
            thread.join(30)

    def _worker(self, index: int) -> None:
        plan: list[tuple[str, str]] = []
        for name, weight, path in ENDPOINTS:
            plan.extend([(name, path)] * weight)
        position = index
        connection: http.client.HTTPConnection | None = None
        while not self.stop.is_set():
            name, path = plan[position % len(plan)]
            position += 1
            started = time.perf_counter()
            status = None
            error = None
            try:
                if connection is None:
                    connection = http.client.HTTPConnection(self.host, self.port, timeout=self.timeout)
                connection.request("GET", path)
                response = connection.getresponse()
                status = response.status
                response.read()
            except Exception as exc:  # noqa: BLE001 - the harness records every failure
                error = type(exc).__name__ + ": " + str(exc)
                try:
                    if connection is not None:
                        connection.close()
                except Exception:
                    pass
                connection = None
            elapsed = (time.perf_counter() - started) * 1000.0
            self.stats.add(
                RequestResult(
                    endpoint=name,
                    status=status,
                    ms=elapsed,
                    error=error,
                    at=round(started - self.started, 3),
                )
            )
            if self.think_ms:
                self.stop.wait(self.think_ms / 1000.0)


# --------------------------------------------------------------------------- server
def wait_until_ready(port: int, timeout: float = 120.0) -> dict[str, Any]:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            connection = http.client.HTTPConnection("127.0.0.1", port, timeout=2.0)
            connection.request("GET", "/api/livez")
            response = connection.getresponse()
            body = response.read()
            connection.close()
            if response.status == 200:
                return json.loads(body)
        except Exception:
            pass
        time.sleep(0.2)
    raise RuntimeError("server did not become ready on port " + str(port))


def http_json(port: int, path: str, timeout: float = 60.0) -> tuple[int, Any, float]:
    started = time.perf_counter()
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=timeout)
    connection.request("GET", path)
    response = connection.getresponse()
    body = response.read()
    connection.close()
    elapsed = (time.perf_counter() - started) * 1000.0
    try:
        payload = json.loads(body)
    except ValueError:
        payload = body[:200].decode("utf-8", "replace")
    return response.status, payload, elapsed


def write_pointer(root: Path, snapshot_id: str) -> dict[str, Any]:
    """Point active.json at a snapshot exactly as the publisher does (atomic replace)."""
    manifest = json.loads((root / "snapshots" / snapshot_id / "snapshot.json").read_text(encoding="utf-8"))
    payload = {
        "schema": "medradar.pipeline.active.v1",
        "snapshot_id": snapshot_id,
        "path": "snapshots/" + snapshot_id,
        "content_hash": (manifest.get("lineage") or {}).get("content_hash"),
        "previous_snapshot_id": (manifest.get("lineage") or {}).get("previous_snapshot_id"),
        "published_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "published_by": "data003-benchmark",
        "action": "switch",
    }
    temporary = root / "active.json.tmp"
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    os.replace(temporary, root / "active.json")
    return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default=str(REPO_ROOT))
    parser.add_argument("--data-root", required=True)
    parser.add_argument("--port", type=int, default=8899)
    parser.add_argument("--duration", type=float, default=30.0)
    parser.add_argument("--concurrency", type=int, default=4)
    parser.add_argument("--think-ms", type=float, default=0.0, help="pause between requests per client (paced load)")
    parser.add_argument("--switch-at", type=float, default=-1.0, help="seconds into the run; -1 disables")
    parser.add_argument("--switch-back-at", type=float, default=-1.0)
    parser.add_argument("--snapshot", default=None, help="target snapshot id; default: the second newest")
    parser.add_argument("--label", default=None)
    parser.add_argument("--json-out", default=None)
    parser.add_argument("--no-prewarm", action="store_true")
    args = parser.parse_args(argv)

    repo_root = Path(args.repo_root).resolve()
    data_root = Path(args.data_root).resolve()
    label = args.label or repo_root.name
    snapshots = sorted(
        [path.name for path in (data_root / "snapshots").iterdir() if path.is_dir()]
    )
    if args.snapshot:
        target = args.snapshot
    else:
        active = json.loads((data_root / "active.json").read_text(encoding="utf-8"))
        others = [snap for snap in snapshots if snap != active["snapshot_id"]]
        target = others[-1] if others else snapshots[-1]
    original = json.loads((data_root / "active.json").read_text(encoding="utf-8"))["snapshot_id"]

    env = os.environ.copy()
    env["PYTHONPATH"] = str(repo_root)
    env["MEDRADAR_DEVICE_CACHE"] = "on"
    env["PYTHONUNBUFFERED"] = "1"
    creationflags = 0
    if sys.platform == "win32":
        creationflags = 0x08000000  # CREATE_NO_WINDOW
    log_path = Path(args.json_out).with_suffix(".server.log") if args.json_out else None
    log_handle = open(log_path, "w", encoding="utf-8") if log_path else subprocess.DEVNULL
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "medradar.product.web",
            "--host",
            "127.0.0.1",
            "--port",
            str(args.port),
            "--no-reload",
            "--data-dir",
            str(data_root),
        ],
        env=env,
        cwd=str(repo_root),
        stdout=log_handle,
        stderr=subprocess.STDOUT,
        creationflags=creationflags,
    )
    try:
        livez = wait_until_ready(args.port)
        module_check = subprocess.run(
            [sys.executable, "-c", "import medradar.product.dataset as d; print(d.__file__)"],
            env=env,
            cwd=str(repo_root),
            capture_output=True,
            text=True,
        )
        module_file = (module_check.stdout or "").strip().splitlines()[-1:] or [""]
        sampler = Sampler(process.pid, 0.25)
        sampler.start()
        prewarm_ms = None
        if not args.no_prewarm:
            status, _body, prewarm_ms = http_json(args.port, "/api/devices/quality", timeout=180)
            prewarm_status = status
        else:
            prewarm_status = None
        # A second call is the warm path; the first may have built the index.
        _status, quality, warm_ms = http_json(args.port, "/api/devices/quality", timeout=60)
        index_build_ms = quality.get("index_build_ms") if isinstance(quality, dict) else None

        stats = Stats()
        stop = threading.Event()
        driver = Driver("127.0.0.1", args.port, stats, stop, args.concurrency, think_ms=args.think_ms)
        started = time.perf_counter()
        driver.start()
        switch_events: list[dict[str, Any]] = []

        def switch_to(snapshot_id: str, reason: str) -> None:
            before = http_json(args.port, "/api/health", timeout=60)[1]
            payload = write_pointer(data_root, snapshot_id)
            moment = round(time.perf_counter() - started, 3)
            # Wait until the service reports the new snapshot (activation observation). The web
            # is under load here, so keep polling and record what the activation block said.
            deadline = time.time() + 90
            observed_at = None
            last_status = None
            last_activation: dict[str, Any] | None = None
            last_snapshot = None
            states: list[str] = []
            while time.time() < deadline:
                try:
                    status, health, _ = http_json(args.port, "/api/health", timeout=30)
                except Exception as exc:  # a request failure during a switch is data, not a crash
                    last_status = None
                    states.append("request_error:" + type(exc).__name__)
                    time.sleep(0.1)
                    continue
                last_status = status
                if not isinstance(health, dict):
                    time.sleep(0.1)
                    continue
                last_snapshot = (health.get("snapshot") or {}).get("id")
                last_activation = health.get("activation")
                state = (last_activation or {}).get("state")
                if state and (not states or states[-1] != state):
                    states.append(state)
                if last_snapshot == snapshot_id:
                    observed_at = round(time.perf_counter() - started, 3)
                    break
                time.sleep(0.1)
            switch_events.append(
                {
                    "reason": reason,
                    "from": (before.get("snapshot") or {}).get("id") if isinstance(before, dict) else None,
                    "to": snapshot_id,
                    "at_s": moment,
                    "observed_at_s": observed_at,
                    "activation_s": round(observed_at - moment, 3) if observed_at else None,
                    "http_status": last_status,
                    "last_snapshot": last_snapshot,
                    "last_activation": last_activation,
                    "activation_states": states,
                    "pointer": payload,
                }
            )

        if args.switch_at >= 0:
            while time.perf_counter() - started < args.switch_at and not stop.is_set():
                time.sleep(0.05)
            switch_to(target, "switch")
        if args.switch_back_at >= 0:
            while time.perf_counter() - started < args.switch_back_at and not stop.is_set():
                time.sleep(0.05)
            switch_to(original, "switch_back")
        while time.perf_counter() - started < args.duration:
            time.sleep(0.05)
        stop.set()
        driver.join()
        sampler.stop()
        summary = stats.summary()
        activation_states = []
        for event in switch_events:
            activation_states.append(event["activation_s"])
        payload = {
            "schema": "data003.web_bench.v1",
            "label": label,
            "repo_root": str(repo_root),
            "module_file": module_file[0],
            "data_root": str(data_root),
            "snapshot_active": original,
            "switch_target": target if args.switch_at >= 0 else None,
            "duration_s": args.duration,
            "concurrency": args.concurrency,
            "think_ms": args.think_ms,
            "prewarm_status": prewarm_status,
            "prewarm_ms": prewarm_ms,
            "index_build_ms": index_build_ms,
            "warm_quality_ms": round(warm_ms, 2),
            "server": {
                "version": livez.get("version") if isinstance(livez, dict) else None,
                "memory": sampler.summary(),
            },
            "switches": switch_events,
            "activation_s": activation_states,
            "requests": summary,
        }
        text = json.dumps(payload, indent=2, sort_keys=True)
        if args.json_out:
            Path(args.json_out).write_text(text, encoding="utf-8")
        print(text)
        return 0
    finally:
        process.terminate()
        try:
            process.wait(10)
        except subprocess.TimeoutExpired:
            process.kill()
        if log_handle not in (None, subprocess.DEVNULL):
            log_handle.close()
        # Restore the pointer so repeated runs start from the same state.
        try:
            write_pointer(data_root, original)
        except Exception:
            pass


if __name__ == "__main__":
    raise SystemExit(main())
