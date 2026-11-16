"""DATA-003 pipeline benchmark: run one real reconciliation and record its resource use.

Spawns the real ``medradar.data_pipeline`` CLI against an isolated copy of a pipeline root
(never the production root), samples the process tree's RSS, and records wall time, exit code,
the run JSON and the final active snapshot. This is the measurement used to calibrate the
DATA-003 host resource guard; it also proves that a guarded deferral does not touch any state.

Examples
--------

    python tools/data003/bench_pipeline.py --root ../data003-work/pipeline-sync-root \
        --args "sync --sources openfda_recall --force --json" --json-out sync.json

    # guarded dry run: impossible memory floor, expect DEFERRED_RESOURCE_PRESSURE
    python tools/data003/bench_pipeline.py --root <root> --args "run --json" \
        --env MEDRADAR_PIPELINE_MIN_AVAILABLE_MB=999999
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
from bench_web import process_tree_memory  # noqa: E402


class Sampler:
    def __init__(self, pid: int, interval: float = 0.5) -> None:
        self.pid = pid
        self.interval = interval
        self.samples: list[dict[str, Any]] = []
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, name="pipeline-sampler", daemon=True)

    def _run(self) -> None:
        started = time.perf_counter()
        while not self._stop.is_set():
            memory = process_tree_memory(self.pid)
            memory["t"] = round(time.perf_counter() - started, 2)
            if memory.get("rss"):
                self.samples.append(memory)
            self._stop.wait(self.interval)

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._thread.join(5)

    def summary(self) -> dict[str, Any]:
        rss = [s["rss"] for s in self.samples if s.get("rss")]
        return {
            "samples": len(self.samples),
            "rss_max_mb": round(max(rss) / 1048576.0, 1) if rss else None,
            "rss_end_mb": round(rss[-1] / 1048576.0, 1) if rss else None,
            "largest_max_mb": round(
                max((s.get("largest_rss", 0) for s in self.samples), default=0) / 1048576.0, 1
            ),
            "swap_max_mb": round(
                max((s.get("swap", 0) for s in self.samples), default=0) / 1048576.0, 1
            ),
            "series_mb": [
                {"t": s["t"], "rss": round(s["rss"] / 1048576.0, 1)} for s in self.samples
            ],
        }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True, help="isolated pipeline root (never production)")
    parser.add_argument("--args", dest="pipeline_args", required=True, help="CLI arguments after module")
    parser.add_argument("--label", default=None)
    parser.add_argument("--json-out", default=None)
    parser.add_argument("--slug", default=None)
    parser.add_argument("--timeout", type=float, default=3600.0)
    parser.add_argument("--env", action="append", default=[], metavar="KEY=VALUE")
    args = parser.parse_args(argv)

    root = Path(args.root).resolve()
    pointer_before = None
    try:
        pointer_before = json.loads((root / "active.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        pass
    env = os.environ.copy()
    env["PYTHONPATH"] = str(REPO_ROOT)
    env["MEDRADAR_PIPELINE_ROOT"] = str(root)
    env.setdefault("MEDRADAR_REVIEW_DB", str(root / "no-review.db"))
    env["PYTHONUNBUFFERED"] = "1"
    for item in args.env:
        key, _, value = item.partition("=")
        env[key] = value
    command = [sys.executable, "-m", "medradar.data_pipeline"] + args.pipeline_args.split()
    started = time.perf_counter()
    process = subprocess.Popen(
        command,
        cwd=str(REPO_ROOT),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    sampler = Sampler(process.pid)
    sampler.start()
    timed_out = False
    try:
        stdout, stderr = process.communicate(timeout=args.timeout)
    except subprocess.TimeoutExpired:
        timed_out = True
        process.kill()
        stdout, stderr = process.communicate()
    elapsed = time.perf_counter() - started
    sampler.stop()
    pointer_after = None
    try:
        pointer_after = json.loads((root / "active.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        pass
    payload_json = None
    try:
        payload_json = json.loads(stdout)
    except ValueError:
        payload_json = None
    status = None
    message = None
    if isinstance(payload_json, dict):
        status = payload_json.get("status")
        message = payload_json.get("message")
    result = {
        "schema": "data003.pipeline_bench.v1",
        "label": args.label or args.slug or "pipeline",
        "root": str(root),
        "command": command,
        "env_overrides": args.env,
        "exit_code": process.returncode,
        "timed_out": timed_out,
        "elapsed_s": round(elapsed, 1),
        "status": status,
        "message": message,
        "result": payload_json,
        "stdout_tail": stdout[-4000:] if stdout and payload_json is None else None,
        "stderr_tail": (stderr or "")[-4000:],
        "pointer_before": (pointer_before or {}).get("snapshot_id"),
        "pointer_after": (pointer_after or {}).get("snapshot_id"),
        "memory": sampler.summary(),
    }
    text = json.dumps(result, indent=2, sort_keys=True)
    if args.json_out:
        Path(args.json_out).write_text(text, encoding="utf-8")
    print(json.dumps({k: v for k, v in result.items() if k != "memory"}, indent=2, sort_keys=True))
    print("memory:", json.dumps(result["memory"]["rss_max_mb"]), "MB peak, samples",
          result["memory"]["samples"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
