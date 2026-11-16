"""Isolate DATA-003 activation starvation: is it the GIL, the GC, or the request path?"""
from __future__ import annotations

import gc
import json
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from medradar.product.dataset import load_dataset  # noqa: E402

ROOT = r"D:\DEPPSKK\data003-work\pipeline-root"
MODE = sys.argv[1] if len(sys.argv) > 1 else "gc-on"
WORKERS = int(sys.argv[2]) if len(sys.argv) > 2 else 2

if MODE == "gc-off":
    gc.disable()
if MODE == "fast":
    # DATA-003 candidate: shorten the interpreter's GIL switch interval so a background
    # activation thread is not starved by long CPU-bound request threads.
    sys.setswitchinterval(0.001)

ds = load_dataset(ROOT)
print("base", len(ds.events), "gc", "off" if MODE == "gc-off" else "on", flush=True)


def api_work() -> None:
    rows = ds.filter_events(org_keys=[], event_types=["recall"])
    rows = ds.sort_events(rows, "date_desc")
    ds.counts(rows)
    json.dumps([event.to_public() for event in rows[:25]])


stop = threading.Event()


def spin() -> None:
    while not stop.is_set():
        api_work()


threads = [threading.Thread(target=spin, daemon=True) for _ in range(WORKERS)]
for thread in threads:
    thread.start()
time.sleep(0.5)

started = time.perf_counter()
last = [0.0]


def progress(phase: str, done: int, total: int) -> None:
    now = time.perf_counter() - started
    if now - last[0] > 1.0 or done in (0, 10000, 20000, 30000):
        last[0] = now
        print(f"{now:6.1f}s {phase} {done}", flush=True)


load_dataset(ROOT, progress=progress)
elapsed = time.perf_counter() - started
stop.set()
for thread in threads:
    thread.join(2)
print(f"load under {WORKERS} workers ({MODE}): {elapsed:.1f}s", flush=True)
