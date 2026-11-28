"""Per-source scheduling, single-writer lease and safe AI deferral.

Why not one cron job that runs everything every N minutes:

* the sources have very different natural cadences (FDA is monthly, PubMed is continuous, a
  vendor newsroom changes a few times a month), so a single interval either hammers the slow
  ones or misses the fast ones;
* a failure at one source must not delay another;
* the optional AI stage must be *skippable* without touching discovery.

So one scheduler owns the process, asks each source whether it is due, runs only those, then
advances the shared pipeline once.

Safety properties:

* **single writer.** The same cross-platform lock the DATA-003 pipeline uses guards every
  cycle. A second scheduler exits immediately with ``LOCKED`` instead of interleaving writes.
* **restart recovery.** Interrupted runs are re-opened, not silently abandoned; stale AI
  claims are released back to the queue.
* **AI never blocks discovery.** If the resource guard refuses, the AI backlog grows and the
  cycle is still ``OK``; the deferral is recorded with the numbers that caused it.
* **honest cycles.** A cycle where every source failed is not reported as "no news".
"""

from __future__ import annotations

import signal
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Sequence

from .adapter import CollectContext
from .engine import advance, ingest
from .graph import TechnologyGraph
from .health import detection_latency, source_status
from .http import HostPolicy, PoliteFetcher
from .ledger import ObservationLedger, RadarLocked
from .paths import RadarPaths
from .records import RUN_DEFERRED
from .resources import ResourceGuard, set_low_priority
from .taxonomy import Taxonomy

#: Per-host politeness, taken from config/radar/sources.json.
def build_fetcher(taxonomy: Taxonomy, *, max_requests: int = 400) -> PoliteFetcher:
    policies: dict[str, HostPolicy] = {}
    for source in taxonomy.sources():
        rate = ((source.get("rate_limit") or {}).get("requests_per_second")) or 1.0
        kind = source.get("kind")
        url = str(((source.get("access") or {}).get("read_path")) or "")
        for token in ("api.fda.gov", "eutils.ncbi.nlm.nih.gov", "api.crossref.org",
                      "www.philips.com", "www.draeger.com", "www.gehealthcare.com"):
            if token in url:
                policies[token] = HostPolicy(
                    requests_per_second=float(rate),
                    timeout_seconds=45.0 if kind == "html" else 30.0,
                )
    return PoliteFetcher(
        user_agent=str((taxonomy.sources_doc.get("policy") or {}).get("user_agent")
                       or "MedRadarBot/0.1 (+https://github.com/ChazY11/medradar)"),
        policies=policies,
        max_requests=max_requests,
    )


@dataclass
class CycleResult:
    started_at: str
    finished_at: str
    status: str
    ingested: dict[str, Any]
    advanced: dict[str, Any]
    ai: dict[str, Any]
    note: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "status": self.status,
            "ingested": self.ingested,
            "advanced": self.advanced,
            "ai": self.ai,
            "note": self.note,
        }


class RadarScheduler:
    def __init__(
        self,
        paths: RadarPaths,
        ledger: ObservationLedger,
        graph: TechnologyGraph,
        taxonomy: Taxonomy,
        *,
        sources: Sequence[str] | None = None,
        trigger: str = "scheduler",
        ai_enabled: bool = True,
        max_requests: int = 400,
        log: Callable[[str], None] = print,
    ) -> None:
        self.paths = paths
        self.ledger = ledger
        self.graph = graph
        self.taxonomy = taxonomy
        self.sources = list(sources) if sources else None
        self.trigger = trigger
        self.ai_enabled = ai_enabled
        self.max_requests = max_requests
        self.log = log
        self.guard = ResourceGuard()

    # ------------------------------------------------------------------- cycle
    def cycle(self, *, force: bool = False, limit: int = 0) -> CycleResult:
        started = _now()
        from .adapters import build_adapters

        adapters = build_adapters(self.taxonomy, self.sources)
        due = [adapter for adapter in adapters
               if force or self._is_due(adapter.source_id)]
        skipped = [adapter.source_id for adapter in adapters if adapter not in due]
        for source_id in skipped:
            self._log(f"[scheduler] {source_id} is not due yet")
        if not due:
            finished = _now()
            # Nothing was due at the sources, but the pipeline may still hold pending work from
            # an interrupted or previous cycle. Draining it on an idle cycle is what makes a
            # kill-during-materialise recoverable without waiting for the next source window.
            advanced = advance(self.ledger, self.graph, self.taxonomy, log=self._log,
                               enqueue_ai=self.ai_enabled)
            result = CycleResult(
                started_at=started, finished_at=finished, status="IDLE",
                ingested={"sources": [], "note": "no source was due in this cycle",
                          "skipped": skipped},
                advanced=advanced, ai={},
                note="Nothing was due. No request was sent and nothing was claimed to have changed.",
            )
            # An idle cycle is still a cycle: the operator must be able to see that the
            # scheduler is alive and that nothing was due, without reading a log file.
            self.ledger.set_runtime("last_cycle", result.as_dict())
            self.ledger.set_runtime(
                "cycle_counter", int(self.ledger.get_runtime("cycle_counter", 0) or 0) + 1
            )
            return result

        fetcher = build_fetcher(self.taxonomy, max_requests=self.max_requests)
        report = ingest(due, self.ledger, self.taxonomy, fetcher=fetcher,
                        trigger=self.trigger, limit=limit, log=self._log)
        # With the AI stage disabled, do not enqueue enrichment work either: a queue that can
        # never drain would grow on every cycle and misreport itself as "pending" forever.
        advanced = advance(self.ledger, self.graph, self.taxonomy, log=self._log,
                           enqueue_ai=self.ai_enabled)

        ai_result = self._run_ai(limit=limit)

        finished = _now()
        ingested = report.as_dict()
        ingested["skipped_sources"] = skipped
        status = "OK"
        if report.sources and len(report.failed_sources) == len(report.sources):
            # Every attempted source failed. This is not a quiet period and must not read as one.
            status = "FAILED"
        elif report.failed_sources:
            status = "PARTIAL"
        note = ingested.get("statement") or ""
        result = CycleResult(started_at=started, finished_at=finished, status=status,
                             ingested=ingested, advanced=advanced, ai=ai_result, note=note)
        self.ledger.set_runtime("last_cycle", result.as_dict())
        self.ledger.set_runtime("cycle_counter", int(self.ledger.get_runtime("cycle_counter", 0) or 0) + 1)
        return result

    def _is_due(self, source_id: str) -> bool:
        state = self.ledger.get_source_state(source_id)
        if state is None:
            return True
        if not bool(state.get("enabled", 1)):
            return False
        last = state.get("last_checked_at")
        cadence = float(state.get("cadence_hours") or 12.0)
        if not last:
            return True
        from .records import parse_moment

        moment = parse_moment(last)
        if moment is None:
            return True
        elapsed = (_now_dt() - moment).total_seconds()
        failures = int(state.get("consecutive_failures") or 0)
        if failures:
            # A failure that cannot succeed by retrying is not made better by retrying sooner. Measured
            # 2026-11-28: openalex needs a credential (401, retryable=0) and draeger refuses automated
            # access (403, retryable=0); the old rule shrank the interval as failures grew, so the
            # 5-minute watcher wrote 3,900 failure rows a week for calls that could never succeed.
            latest = self.ledger.failures(source=source_id, limit=1)
            if latest:
                flag = latest[0].get("retryable")
                # A missing flag means "unknown", which is treated as retryable - the conservative side.
                if flag is not None and not int(flag):
                    return elapsed >= 24 * 3600
            # Retry a *transient* failure sooner, but never faster than every 15 minutes.
            cadence = min(cadence, max(0.25, cadence / max(1, failures)))
        return elapsed >= cadence * 3600

    # ---------------------------------------------------------------------- ai
    def _run_ai(self, *, limit: int = 0) -> dict[str, Any]:
        if not self.ai_enabled:
            return {"state": "disabled", "reason": "ai_enabled is false"}
        queue = self.ledger.queue_summary()
        if not queue["backlog"]:
            state = {"state": "idle", "reason": "the AI backlog is empty"}
            self.ledger.set_runtime("ai_state", state)
            return state
        # 3,300 MB is the measured peak RSS of the Qwen3-0.6B float32 batch on the acceptance
        # host (docs/radar/AI.md). The guard asks for 1.5x that headroom, so on the 2 vCPU / 4 GB
        # production host the batch is deferred and discovery continues - which is the intended
        # behaviour, not a failure.
        decision = self.guard.evaluate(self.paths.root, estimated_model_mb=3300.0)
        if not decision.allowed:
            state = {
                "state": "deferred",
                "reason": decision.reason,
                "detail": decision.detail,
                "backlog": queue["backlog"],
                "statement": (
                    "AI enrichment was deferred to protect the host. Discovery is unaffected and "
                    "the backlog is retained; the next cycle retries."
                ),
            }
            self.ledger.set_runtime("ai_state", state)
            self._log(f"[scheduler] AI deferred: {decision.reason}")
            return state
        try:
            result = self._spawn_worker(limit=limit or 12)
        except Exception as error:  # noqa: BLE001
            state = {
                "state": "failed",
                "reason": f"{type(error).__name__}: {error}",
                "backlog": self.ledger.queue_summary()["backlog"],
            }
            self.ledger.set_runtime("ai_state", state)
            self._log(f"[scheduler] AI batch failed: {type(error).__name__}: {error}")
            return state
        state = {"state": "ran", **result} if isinstance(result, dict) else {"state": "ran"}
        self.ledger.set_runtime("ai_state", state)
        return state

    def _spawn_worker(self, *, limit: int) -> dict[str, Any]:
        """Start the worker for one batch in its own low-priority process, then let it exit.

        A separate process is the point: when the model unloads, its memory goes back to the
        OS, so a 4 GB host is not permanently down 1.5 GB after one batch.
        """
        import json as json_module
        import os
        import subprocess
        import sys

        from ..config import SOURCE_ROOT

        # The model needs torch/transformers, which the serving interpreter does not have to have.
        # Point MEDRADAR_AI_PYTHON at an ML virtualenv; nothing else in the radar uses it.
        interpreter = str(os.environ.get("MEDRADAR_AI_PYTHON") or sys.executable)
        command = [
            interpreter, "-m", "medradar.radar.ai.worker",
            "--data-dir", str(self.paths.root),
            "--limit", str(int(limit)),
            "--json",
        ]
        completed = subprocess.run(
            command, capture_output=True, text=True, timeout=1800, cwd=str(SOURCE_ROOT), check=False,
        )
        payload: dict[str, Any] = {}
        for line in reversed((completed.stdout or "").strip().splitlines()):
            line = line.strip()
            if line.startswith("{"):
                try:
                    payload = json_module.loads(line)
                    break
                except ValueError:
                    continue
        if completed.returncode != 0 and not payload:
            raise RuntimeError(
                f"the AI worker exited {completed.returncode}: "
                f"{(completed.stderr or completed.stdout or '')[-400:]}"
            )
        payload.setdefault("state", "ran")
        payload["worker_return_code"] = completed.returncode
        return payload

    # -------------------------------------------------------------------- watch
    def watch(self, *, interval_seconds: float = 300.0, max_cycles: int | None = None,
              stop_event: threading.Event | None = None) -> dict[str, Any]:
        stop = stop_event or threading.Event()
        previous = _install_signal_handlers(stop)
        cycles = 0
        results: list[dict[str, Any]] = []
        try:
            while not stop.is_set():
                if max_cycles is not None and cycles >= max_cycles:
                    break
                try:
                    with self.ledger.lock(timeout_seconds=0.0):
                        self.ledger.recover_interrupted_runs()
                        self.ledger.release_stale_claims()
                        result = self.cycle()
                    results.append(result.as_dict())
                    cycles += 1
                    self._log(
                        f"[scheduler] cycle {cycles}: {result.status} "
                        f"new={result.ingested.get('new_records', 0)} "
                        f"updated={result.ingested.get('updated_records', 0)} "
                        f"ai={result.ai.get('state')}"
                    )
                except RadarLocked:
                    self._log("[scheduler] another process holds the radar lock; waiting")
                except Exception as error:  # noqa: BLE001 - the loop must survive a bad cycle
                    self._log(f"[scheduler] cycle error: {type(error).__name__}: {error}")
                if stop.wait(interval_seconds):
                    break
        except KeyboardInterrupt:  # pragma: no cover - interactive
            self._log("[scheduler] interrupted; no cursor was advanced by the interruption")
        finally:
            _restore_signal_handlers(previous)
        return {"cycles": cycles, "results": results, "stopped": stop.is_set()}

    def _log(self, message: str) -> None:
        try:
            self.log(message)
        except Exception:  # pragma: no cover
            pass


def _now() -> str:
    return _now_dt().strftime("%Y-%m-%dT%H:%M:%SZ")


def _now_dt() -> datetime:
    return datetime.now(timezone.utc)


def _install_signal_handlers(stop: threading.Event) -> list[tuple[int, Any]]:
    previous: list[tuple[int, Any]] = []
    for name in ("SIGINT", "SIGTERM"):
        number = getattr(signal, name, None)
        if number is None:
            continue
        try:
            previous.append((number, signal.getsignal(number)))
            signal.signal(number, lambda *_args: stop.set())
        except (ValueError, OSError):  # pragma: no cover - not the main thread
            pass
    return previous


def _restore_signal_handlers(previous: list[tuple[int, Any]]) -> None:
    for number, handler in previous:
        try:
            signal.signal(number, handler)
        except (ValueError, OSError):  # pragma: no cover
            pass


def scheduler_from_paths(paths: RadarPaths, taxonomy: Taxonomy, *, sources=None,
                         ai_enabled: bool = True, log=print) -> RadarScheduler:
    ledger = ObservationLedger(paths.ledger)
    from .graph import open_graph

    graph = open_graph(paths.graph, taxonomy)
    return RadarScheduler(paths, ledger, graph, taxonomy, sources=sources,
                         ai_enabled=ai_enabled, log=log)
