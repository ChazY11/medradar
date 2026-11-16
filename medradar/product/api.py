"""FastAPI application for the MedRadar workbench.

Thin projection of medradar.product.dataset: routing, query parsing, HTTP semantics and static
file serving. All measurement lives in the dataset / compare / export modules so that the tests
can exercise the same code the API uses.

Run:

    python -m medradar web --port 8787
"""
from __future__ import annotations

import json
import os
import sys
import threading
import time
from pathlib import Path
from typing import Any, Iterable

from fastapi import FastAPI, Query, Request
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse, Response

from . import dataset as dataset_module
from . import resources
from . import brief as brief_module
from .compare import build_compare
from .dataset import (
    EVENT_TYPE_ORDER,
    OWNERSHIP_BASES,
    RETIRED_OWNERSHIP_BASES,
    PRODUCT_NAME,
    PRODUCT_VERSION,
    REVIEW_FILTERS,
    Dataset,
    default_data_dir,
    load_dataset,
)
from .attribution import ownership as ownership_module
from .attribution import status as status_module
from medradar.data_pipeline.status_service import changes_feed, data_status
from .export import (
    compare_markdown,
    compare_markdown_filename,
    csv_filename,
    events_csv,
    organization_markdown,
    organization_markdown_filename,
    provenance_header,
)

MAX_PAGE_SIZE = 100
DEFAULT_PAGE_SIZE = 25


def _utc_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


class DatasetHolder:
    """Serves one validated dataset and activates new snapshots without blocking requests.

    DATA-002 loaded the new snapshot inside whichever request noticed that the active pointer
    changed, holding one global lock for the whole load. Every other request - including
    ``/api/health`` - queued behind it, and with the 1.6 GB dataset partly in swap that is the
    8 s health timeout observed during the recall sync.

    DATA-003 changes the activation contract:

    * a request never waits for a snapshot load; it always receives the currently validated
      dataset (the old one stays valid until the new one is completely loaded);
    * exactly one background thread loads and validates the new snapshot, then swaps a single
      reference; the old dataset is released by the garbage collector;
    * a failed load keeps the previous dataset and is reported as degraded, as before;
    * activation asks the resource guard first. On a host that cannot hold a second copy the
      activation is *deferred*, the old snapshot keeps serving, and the state is visible.

    ``invalidate(wait=True)`` and :meth:`reload_now` remain synchronous for the loopback review
    service, which needs the new ledger to be visible on the very next read.
    """

    #: How often a request may stat the active pointer and ask the review ledger for its
    #: fingerprint. Two stat calls per request are cheap; a SQLite fingerprint per request is not.
    FINGERPRINT_INTERVAL = 2.0
    #: Backoff after a failed activation, so a broken pointer cannot spin the loader.
    RETRY_DELAYS = (30.0, 60.0, 120.0, 300.0)

    def __init__(self, data_dir: Path | None = None) -> None:
        self.data_dir = data_dir
        self._dataset: Dataset | None = None
        self._error: str | None = None
        self._state_lock = threading.Lock()
        self._load_lock = threading.Lock()
        self.fingerprint_fn: Any = None
        self._fingerprint: Any = None
        self._snapshot_fingerprint: Any = None
        self.review_db: Path | None = None

        self._next_check = 0.0
        self._next_attempt_at = 0.0
        self._attempts = 0
        self._retry_state: Any = None
        self._reload_thread: threading.Thread | None = None
        self._reload_state = "idle"
        self._reload_error: str | None = None
        self._reload_started_at: str | None = None
        self._reload_finished_at: str | None = None
        self._reload_snapshot: str | None = None
        self._pending_snapshot: str | None = None
        self._reload_phase: str | None = None
        self._reload_progress: tuple[int, int] = (0, 0)
        self._reload_started_mono = 0.0
        self._last_guard: dict[str, Any] | None = None
        self._deferral_count = 0
        self.guard_enabled = True
        self.guard_policy = resources.ACTIVATION_GUARD

    # ------------------------------------------------------------------ paths and state
    def _data_root(self) -> Path:
        root = Path(self.data_dir) if self.data_dir else default_data_dir()
        if (root / "snapshot.json").is_file():
            return root.parent
        return root

    def _data_state(self) -> tuple[Any, Any]:
        review = None
        if self.fingerprint_fn is not None:
            try:
                review = self.fingerprint_fn()
            except Exception:
                review = None
        root = self.data_dir or default_data_dir()
        parts = []
        for name in ("active.json", "snapshot.json"):
            candidate = Path(root) / name
            try:
                stat = candidate.stat()
                parts.append((name, stat.st_mtime_ns, stat.st_size))
            except OSError:
                parts.append((name, None, None))
        return tuple(parts), review

    def _pointer_snapshot_id(self) -> str | None:
        """The snapshot id the active pointer names, without loading the dataset."""
        root = Path(self.data_dir) if self.data_dir else default_data_dir()
        pointer = root / "active.json"
        try:
            payload = json.loads(pointer.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        if not isinstance(payload, dict):
            return None
        return str(payload.get("snapshot_id") or "") or None

    def _changed(self, snapshot_fingerprint: Any, fingerprint: Any) -> bool:
        if self._dataset is None:
            return True
        if snapshot_fingerprint != self._snapshot_fingerprint:
            return True
        return self.fingerprint_fn is not None and fingerprint != self._fingerprint

    # ------------------------------------------------------------------ public API
    def get(self) -> Dataset:
        current = self._dataset
        if current is not None:
            # Never loads here: only decides whether a background activation is due.
            self._maybe_reload()
            return current
        return self._load_initial()

    def _load_initial(self) -> Dataset:
        """Cold start blocks once; there is no older dataset to keep serving."""
        with self._load_lock:
            current = self._dataset
            if current is not None:
                return current
            snapshot_fingerprint, fingerprint = self._data_state()
            try:
                loaded = load_dataset(self.data_dir, review_db=self.review_db)
                # DATA-003 Correction-1: a dataset is only published once its device index is
                # built. Otherwise the first Device Explorer request after the swap could block
                # on a multi-second index build, and /api/devices could serve a dataset whose
                # index was still being constructed.
                loaded.device_index()
            except Exception as error:
                self._error = str(error)
                raise FileNotFoundError(str(error)) from error
            with self._state_lock:
                self._dataset = loaded
                self._error = None
                self._fingerprint = fingerprint
                self._snapshot_fingerprint = snapshot_fingerprint
            return loaded

    def _maybe_reload(self) -> None:
        now = time.monotonic()
        if now < self._next_check:
            return
        self._next_check = now + self.FINGERPRINT_INTERVAL
        thread = self._reload_thread
        if thread is not None and thread.is_alive():
            return
        snapshot_fingerprint, fingerprint = self._data_state()
        if not self._changed(snapshot_fingerprint, fingerprint):
            return
        if self._retry_state is not None and snapshot_fingerprint != self._retry_state:
            # The active pointer moved since the last failed (or deferred) attempt. This is a
            # different snapshot, so the old backoff must not delay it: retry immediately.
            self._attempts = 0
            self._next_attempt_at = 0.0
            self._retry_state = None
        if now < self._next_attempt_at:
            return
        if not self._start_activation(snapshot_fingerprint, fingerprint):
            # A guard deferral is remembered against this pointer state so a *new* snapshot can
            # still be attempted without waiting out the 15 s deferral cadence.
            if self._reload_state == "deferred":
                self._retry_state = snapshot_fingerprint

    def _start_activation(self, snapshot_fingerprint: Any, fingerprint: Any) -> bool:
        with self._state_lock:
            thread = self._reload_thread
            if thread is not None and thread.is_alive():
                return False
            pending = self._pointer_snapshot_id()
            if not self._guard_allows_activation(pending):
                self._retry_state = snapshot_fingerprint
                return False
            self._reload_state = "loading"
            self._reload_error = None
            self._reload_started_at = _utc_now()
            self._reload_started_mono = time.monotonic()
            self._reload_phase = "starting"
            self._reload_progress = (0, 0)
            self._reload_finished_at = None
            self._reload_snapshot = None
            self._pending_snapshot = pending
            thread = threading.Thread(
                target=self._activation_worker,
                args=(snapshot_fingerprint, fingerprint, pending),
                name="medradar-dataset-activation",
                daemon=True,
            )
            self._reload_thread = thread
        thread.start()
        return True

    def _guard_allows_activation(self, pending: str | None) -> bool:
        """Decide, before allocating a second dataset, that the host can hold it."""
        if not self.guard_enabled:
            return True
        root = self._data_root()
        lock_path = root / "pipeline.lock"
        if resources.pipeline_operation_active(lock_path):
            self._mark_deferred(
                ["pipeline_operation_active"],
                guard={"allowed": False, "reasons": ["pipeline_operation_active"]},
            )
            return False
        rss = resources.process_rss_mb()
        # The new copy is the dataset *plus* its device index (Correction-1 builds the index
        # before the swap), so budget one full anonymous RSS, not 95 % of it.
        required = int(rss * 1.0) + 128 if rss else 512
        decision = resources.evaluate_guard(
            self.guard_policy.with_required(required),
            disk_root=root,
        )
        self._last_guard = decision.to_public()
        if not decision.allowed:
            self._mark_deferred(list(decision.reasons), guard=decision.to_public())
            return False
        return True

    def _mark_deferred(self, reasons: list[str], *, guard: dict[str, Any] | None = None) -> None:
        self._reload_state = "deferred"
        self._deferral_count += 1
        self._reload_error = "deferred: " + ", ".join(reasons)
        if guard is not None:
            self._last_guard = guard
        # Retry on the next fingerprint tick (a few seconds); deferral is not a failure, but it
        # must not be silent either: reload_status() exposes every reason.
        self._next_attempt_at = time.monotonic() + 15.0

    def _activation_worker(self, snapshot_fingerprint: Any, fingerprint: Any, pending: str | None) -> None:
        root = self._data_root()
        resources.write_activation(
            root,
            state="loading",
            snapshot_id=pending,
            started_at=self._reload_started_at,
        )

        def progress(phase: str, done: int, total: int) -> None:
            self._reload_phase = phase
            self._reload_progress = (done, total)

        try:
            loaded = load_dataset(self.data_dir, review_db=self.review_db, progress=progress)
            # Publish only a complete dataset: build the device index before the swap. If this
            # fails, the previous dataset keeps serving and the attempt is retried, so
            # /api/devices can never observe a half-ready index.
            self._reload_phase = "indexing"
            self._reload_progress = (0, 0)
            loaded.device_index()
        except Exception as error:
            with self._state_lock:
                self._error = str(error)
                self._reload_state = "failed"
                self._reload_error = str(error)
                self._reload_phase = "failed"
                self._reload_finished_at = _utc_now()
                self._retry_state = snapshot_fingerprint
                self._attempts += 1
                delay = self.RETRY_DELAYS[min(self._attempts - 1, len(self.RETRY_DELAYS) - 1)]
                self._next_attempt_at = time.monotonic() + delay
            resources.write_activation(
                root,
                state="failed",
                snapshot_id=pending,
                started_at=self._reload_started_at,
                finished_at=self._reload_finished_at,
                error=str(error),
            )
            return
        with self._state_lock:
            # The swap is one reference assignment: a request either sees the old dataset or
            # the new one, never a half-loaded object.
            self._dataset = loaded
            self._error = None
            self._fingerprint = fingerprint
            self._snapshot_fingerprint = snapshot_fingerprint
            self._reload_state = "idle"
            self._reload_error = None
            self._reload_finished_at = _utc_now()
            self._reload_snapshot = loaded.snapshot_id
            self._reload_phase = None
            self._pending_snapshot = None
            self._attempts = 0
            self._retry_state = None
            self._deferral_count = 0
        resources.write_activation(
            root,
            state="loaded",
            snapshot_id=loaded.snapshot_id,
            started_at=self._reload_started_at,
            finished_at=self._reload_finished_at,
        )
        self._reload_progress = (0, 0)

    def reload_now(self, *, timeout: float = 300.0) -> bool:
        """Force a synchronous activation. Used by the loopback review service only."""
        thread = self._reload_thread
        if thread is not None and thread.is_alive():
            thread.join(timeout)
            return False if thread.is_alive() else True
        snapshot_fingerprint, fingerprint = self._data_state()
        with self._load_lock:
            loaded = load_dataset(self.data_dir, review_db=self.review_db)
            # Same completeness rule as the background path.
            loaded.device_index()
            with self._state_lock:
                self._dataset = loaded
                self._error = None
                self._fingerprint = fingerprint
                self._snapshot_fingerprint = snapshot_fingerprint
                self._reload_state = "idle"
                self._reload_error = None
                self._reload_finished_at = _utc_now()
                self._reload_snapshot = loaded.snapshot_id
                self._pending_snapshot = None
                self._retry_state = None
                self._attempts = 0
        return True

    def wait_for_reload(self, timeout: float = 60.0) -> bool:
        """Wait for an in-flight activation; returns True when nothing is loading."""
        deadline = time.monotonic() + timeout
        while True:
            thread = self._reload_thread
            if thread is None or not thread.is_alive():
                return True
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return False
            thread.join(min(remaining, 0.5))

    def poll_once(self, *, force: bool = True) -> dict[str, Any]:
        """Check the active pointer immediately instead of waiting for the next request tick.

        Public so an operator tool (or the review CLI) can ask "is there a newer snapshot?"
        without sleeping through the per-request throttle. Activation itself stays asynchronous.
        """
        if force:
            self._next_check = 0.0
        self._maybe_reload()
        return self.reload_status()

    def reload_status(self) -> dict[str, Any]:
        with self._state_lock:
            current = self._dataset
            now = time.monotonic()
            next_attempt = max(0.0, self._next_attempt_at - now) if self._next_attempt_at else 0.0
            elapsed = (
                round(now - self._reload_started_mono, 1)
                if self._reload_state == "loading" and self._reload_started_mono
                else None
            )
            return {
                "state": self._reload_state,
                "phase": self._reload_phase,
                "progress": {"done": self._reload_progress[0], "total": self._reload_progress[1]},
                "elapsed_s": elapsed,
                "active_snapshot": current.snapshot_id if current is not None else None,
                # Correction-1: a published dataset always has its device index built, so this
                # is True whenever a dataset is active. It exists so an operator can prove the
                # data and the index were published together.
                "index_ready": bool(
                    current is not None and getattr(current, "_device_index", None) is not None
                ),
                "pending_snapshot": self._pending_snapshot,
                "started_at": self._reload_started_at,
                "finished_at": self._reload_finished_at,
                "last_activated_snapshot": self._reload_snapshot,
                "attempts": self._attempts,
                "deferrals": self._deferral_count,
                "next_attempt_in_s": round(next_attempt, 1) if next_attempt else 0.0,
                "last_error": self._reload_error,
                "guard": self._last_guard,
                "using_fallback": bool(self._error),
            }

    @property
    def degraded_error(self) -> str | None:
        return self._error

    def invalidate(self, *, wait: bool = False) -> None:
        """Mark the current dataset stale. The old dataset keeps serving until the swap."""
        with self._state_lock:
            self._snapshot_fingerprint = None
            self._fingerprint = None
        self._next_check = 0.0
        self._next_attempt_at = 0.0
        self._retry_state = None
        self._attempts = 0
        if wait:
            self.reload_now()
        else:
            self._maybe_reload()

    def status(self) -> tuple[str, str | None]:
        try:
            self.get()
        except Exception as error:
            return "degraded", str(error)
        if self._error:
            return "degraded", self._error
        return "ok", None


def raise_for_basis(basis: str | None) -> None:
    if not basis:
        return
    if basis in RETIRED_OWNERSHIP_BASES:
        raise HTTPExceptionCompat(
            400,
            "retired_basis",
            "the basis " + basis + " was retired in PRODUCT-003",
            "it excluded predecessor applicant names, which is not the same as restoring the owner at event time; "
            "use " + RETIRED_OWNERSHIP_BASES[basis] + ", which requires a verified relation with an effective date and "
            "reports the excluded unknown records",
        )
    if basis not in OWNERSHIP_BASES:
        raise HTTPExceptionCompat(400, "bad_basis", "basis must be one of " + ", ".join(OWNERSHIP_BASES))


def _error(status_code: int, code: str, message: str, hint: str | None = None) -> JSONResponse:
    body: dict[str, Any] = {"error": {"code": code, "message": message}}
    if hint:
        body["error"]["hint"] = hint
    return JSONResponse(status_code=status_code, content=body)


def _parse_csv(value: str | None) -> list[str]:
    if not value:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


def _parse_event_types(value: str | None) -> list[str]:
    items = _parse_csv(value)
    invalid = [item for item in items if item not in EVENT_TYPE_ORDER]
    if invalid:
        raise ValueError("unknown event type(s): " + ", ".join(invalid) + "; expected " + ", ".join(EVENT_TYPE_ORDER))
    return items


def _parse_int(value: str | None, name: str, default: int, minimum: int, maximum: int) -> int:
    if value is None or value == "":
        return default
    try:
        parsed = int(value)
    except ValueError as error:
        raise ValueError("invalid integer for " + name) from error
    if parsed < minimum or parsed > maximum:
        raise ValueError(name + " must be between " + str(minimum) + " and " + str(maximum))
    return parsed


def _events_payload(dataset: Dataset, applied: dict[str, str], org_keys: list[str], event_types: list[str],
                    date_from: str | None, date_to: str | None, categories: list[str], query: str | None,
                    review: str | None, basis: str | None, sort: str, page: int, page_size: int,
                    product_code: str | None = None) -> dict[str, Any]:
    filtered = dataset.filter_events(
        org_keys=org_keys or None,
        event_types=event_types or None,
        date_from=date_from,
        date_to=date_to,
        categories=categories or None,
        query=query,
        review=review,
        basis=basis,
        product_code=product_code,
    )
    ordered = dataset.sort_events(filtered, sort)
    total = len(ordered)
    total_pages = max(1, (total + page_size - 1) // page_size)
    page = min(page, total_pages)
    start = (page - 1) * page_size
    items = ordered[start:start + page_size]
    window = {"from": date_from, "to": date_to}
    return {
        "items": [event.to_public() for event in items],
        "page": page,
        "page_size": page_size,
        "total": total,
        "total_pages": total_pages,
        "applied_filters": applied,
        "aggregations": dataset_module.aggregate(ordered),
        "counts": dataset.counts(ordered),
        "basis": dataset.basis(
            ordered,
            event_types=event_types or list(EVENT_TYPE_ORDER),
            window=window,
            rule="Count of attributed regulatory records matching the filters; "
            + (
                "current-group attribution (records filed by an acquired predecessor are counted under the current group; owner at event time is reported per record)"
                if basis != "historical_owner_verified"
                else "historical-owner basis (only records where a verified relation with an effective date places control with this group at the event date)"
            ),
        ),
        "ownership_basis": basis or "current_group",
        "review_filter": review or "any",
        "snapshot": dataset.snapshot_ref(),
    }


def create_app(
    data_dir: Path | str | None = None,
    web_dir: Path | str | None = None,
    setup=None,
    pipeline_db: Path | str | None = None,
    radar_dir: Path | str | None = None,
) -> FastAPI:
    """Build the read-only public application.

    setup(app) is invoked after the API routes and before the SPA static routes are registered.
    The internal review service uses it to mount write routes on its own application; the public
    application is this function without setup, so it contains no write route at all.
    """
    holder = DatasetHolder(Path(data_dir) if data_dir else None)
    resolved_web = Path(web_dir) if web_dir else _default_web_dir()

    app = FastAPI(
        title="MedRadar workbench API",
        version=PRODUCT_VERSION,
        description="Medical technology intelligence over an immutable openFDA snapshot.",
        docs_url="/api/docs",
        redoc_url=None,
    )
    app.state.holder = holder
    app.state.web_dir = resolved_web
    app.state.pipeline_db = Path(pipeline_db) if pipeline_db is not None else None

    @app.middleware("http")
    async def timing(request: Request, call_next):  # type: ignore[no-untyped-def]
        started = time.perf_counter()
        response = await call_next(request)
        response.headers["X-Response-Time-ms"] = format((time.perf_counter() - started) * 1000.0, ".1f")
        return response

    def dataset() -> Dataset:
        try:
            return holder.get()
        except FileNotFoundError as error:
            raise HTTPExceptionCompat(503, "dataset_unavailable", str(error), "collect the snapshot with: python scripts/product_collect.py")
        except Exception as error:
            raise HTTPExceptionCompat(503, "dataset_error", str(error))

    # ---------------------------------------------------------------- health & meta
    def _health_payload() -> tuple[int, dict[str, Any]]:
        data = None
        dataset_error = holder.degraded_error
        try:
            data = holder.get()
        except Exception as error:
            dataset_error = str(error)
        try:
            status_payload = data_status(
                data_dir=holder.data_dir or dataset_module.default_data_dir(),
                pipeline_db=app.state.pipeline_db,
            )
        except Exception as error:
            status_payload = {
                "health": {
                    "data": {"state": "unknown"},
                    "sync": {"state": "unknown", "error": str(error)},
                    "freshness": {"state": "unknown", "error": str(error)},
                }
            }
        pipeline_health = status_payload.get("health") or {}
        if pipeline_health.get("data") is not None:
            pipeline_health["data"]["using_fallback"] = bool(holder.degraded_error)
        activation = holder.reload_status()
        activation_state = str(activation.get("state") or "idle")
        if activation_state in ("deferred", "failed"):
            activation_health = "degraded"
        elif activation_state == "loading":
            activation_health = "loading"
        else:
            activation_health = "ok"
        data_state = "available" if data is not None else "unavailable"
        if holder.degraded_error:
            data_state = "degraded"
        checks = {
            "liveness": {"state": "ok", "detail": "the web process answered"},
            "readiness": {
                "state": "ok" if data is not None else "not_ready",
                "detail": "a validated dataset is loadable" if data is not None else "no validated dataset is loadable",
            },
            "data": {
                "state": data_state,
                "snapshot_id": (data.snapshot_ref().get("id") if data is not None else None),
                "using_fallback": bool(holder.degraded_error),
                "error": dataset_error,
            },
            "activation": {
                "state": activation_health,
                "detail": activation_state,
                "pending_snapshot": activation.get("pending_snapshot"),
                "next_attempt_in_s": activation.get("next_attempt_in_s"),
                "deferrals": activation.get("deferrals"),
                "last_error": activation.get("last_error") if activation_state != "idle" else None,
                "guard_reasons": (activation.get("guard") or {}).get("reasons") if activation.get("guard") else None,
            },
            "sync": pipeline_health.get("sync") or {"state": "unknown"},
            "freshness": pipeline_health.get("freshness") or {"state": "unknown"},
        }
        states = {str(check.get("state") or "unknown") for check in checks.values()}
        if data is None:
            overall = "not_ready"
        elif states & {"degraded", "not_ready", "failed", "unavailable", "stale"}:
            overall = "degraded"
        elif "unknown" in states:
            overall = "unknown"
        else:
            overall = "ok"
        payload = {
            "status": overall,
            "snapshot": data.snapshot_ref() if data is not None else None,
            "version": PRODUCT_VERSION,
            "store": str(data.data_dir) if data is not None else str(holder.data_dir or dataset_module.default_data_dir()),
            "checks": checks,
            "activation": activation,
            "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
        return (200 if data is not None else 503), payload

    @app.get("/api/livez")
    def livez() -> Any:
        return {"status": "alive", "version": PRODUCT_VERSION}

    @app.get("/api/readyz")
    def readyz() -> Any:
        status_code, payload = _health_payload()
        return JSONResponse(
            status_code=status_code,
            content={
                "ready": payload["status"] != "not_ready",
                "status": payload["status"],
                "snapshot": payload["snapshot"],
                "checks": {"readiness": payload["checks"]["readiness"], "data": payload["checks"]["data"]},
            },
        )

    @app.get("/api/health")
    def health() -> Any:
        status_code, payload = _health_payload()
        return JSONResponse(status_code=status_code, content=payload)

    @app.get("/api/meta")
    def meta() -> Any:
        return dataset().meta()

    # ---------------------------------------------------------------- data lifecycle
    @app.get("/api/data-status")
    def pipeline_status() -> Any:
        try:
            status = data_status(
                data_dir=holder.data_dir or dataset_module.default_data_dir(),
                pipeline_db=app.state.pipeline_db,
            )
        except Exception as error:
            status = {
                "schema": "medradar.data_status.v1",
                "configured": True,
                "state": "error",
                "message": "The pipeline state database could not be read: " + str(error),
                "terminology": {"continuously_monitored": True, "automatically_synchronized": True, "real_time_claim": False, "labels": []},
                "snapshot": None,
                "synchronization": {"state": "error", "last_successful_sync": None, "last_check_attempt": None},
                "sources": [],
                "health": {"data": {"state": "unknown"}, "sync": {"state": "unknown"}, "freshness": {"state": "unknown"}},
                "change_counts": {}, "recent_runs": [], "incidents": [], "change_feed": [],
                "latency": {"official_source_version": None, "last_checked_by_medradar": None,
                            "last_successful_sync": None, "sync_lag_hours": None,
                            "statement": "Pipeline state is unreadable; no synchronization claim is made."},
            }
        try:
            data = dataset()
            status["data_snapshot"] = data.snapshot_ref()
            status["freshness"] = data.freshness()
            status.setdefault("health", {}).setdefault("data", {})["using_fallback"] = bool(holder.degraded_error)
            status["dataset_error"] = holder.degraded_error
        except Exception as error:
            # The lifecycle page must remain usable when the active snapshot is the thing
            # that failed to load. Do not replace it with a 503 and hide the pipeline state.
            status["data_snapshot"] = None
            status["freshness"] = None
            status["dataset_error"] = str(error)
        # DATA-003: a published snapshot can be waiting for activation (loading, or deferred by
        # the resource guard). The page must show that difference instead of a stale "ok".
        status["dataset_activation"] = holder.reload_status()
        return status

    @app.get("/api/changes")
    def changes(
        source: str | None = None,
        type: str | None = None,
        org: str | None = None,
        limit: int = Query(default=50),
        offset: int = Query(default=0),
    ) -> Any:
        allowed_sources = {
            "openfda_510k", "openfda_pma", "openfda_recall", "openfda_classification",
        }
        allowed_types = {
            "ADDED", "UPDATED", "REMOVED_CONFIRMED", "UNCHANGED",
            "MISSING_ON_RECHECK", "UNRESOLVED",
        }
        if source and source not in allowed_sources:
            raise HTTPExceptionCompat(400, "bad_source", "source must be one of " + ", ".join(sorted(allowed_sources)))
        if type and type not in allowed_types:
            raise HTTPExceptionCompat(400, "bad_change_type", "type must be one of " + ", ".join(sorted(allowed_types)))
        if limit < 1 or limit > 200:
            raise HTTPExceptionCompat(400, "bad_limit", "limit must be between 1 and 200")
        if offset < 0:
            raise HTTPExceptionCompat(400, "bad_offset", "offset must be non-negative")
        return changes_feed(
            source_id=source, change_type=type, organization_key=org,
            limit=int(limit), offset=int(offset),
            pipeline_db=app.state.pipeline_db,
            data_dir=holder.data_dir or dataset_module.default_data_dir(),
        )

    # ---------------------------------------------------------------- search
    @app.get("/api/search")
    def search(q: str = Query(default=""), limit: int = Query(default=8)) -> Any:
        if not q.strip():
            raise HTTPExceptionCompat(400, "empty_query", "q is required")
        data = dataset()
        return data.search(q.strip(), max(1, min(int(limit), 20)))

    # ---------------------------------------------------------------- organizations
    @app.get("/api/organizations")
    def organizations() -> Any:
        return dataset().organizations_payload()

    @app.get("/api/organizations/{key}")
    def organization(key: str) -> Any:
        data = dataset()
        if data.organization(key) is None:
            raise HTTPExceptionCompat(404, "organization_not_found", "unknown organization key: " + key)
        return data.organization_profile(key)

    @app.get("/api/organizations/{key}/events")
    def organization_events(key: str, types: str | None = None, date_from: str | None = Query(default=None, alias="from"),
                            date_to: str | None = Query(default=None, alias="to"), category: str | None = None,
                            q: str | None = None, review: str | None = None, basis: str | None = None,
                            product_code: str | None = None,
                            sort: str = "event_date_desc",
                            page: str | None = None, page_size: str | None = None) -> Any:
        data = dataset()
        if data.organization(key) is None:
            raise HTTPExceptionCompat(404, "organization_not_found", "unknown organization key: " + key)
        return _event_response(data, [key], types, date_from, date_to, category, q, review, basis, sort, page, page_size, product_code)

    # ---------------------------------------------------------------- events
    @app.get("/api/events")
    def events(org: str | None = None, types: str | None = None, date_from: str | None = Query(default=None, alias="from"),
               date_to: str | None = Query(default=None, alias="to"), category: str | None = None,
               q: str | None = None, review: str | None = None, basis: str | None = None,
               product_code: str | None = None,
               sort: str = "event_date_desc",
               page: str | None = None, page_size: str | None = None) -> Any:
        data = dataset()
        org_keys = _parse_csv(org)
        unknown = [key for key in org_keys if data.organization(key) is None]
        if unknown:
            raise HTTPExceptionCompat(400, "unknown_organization", "unknown organization key(s): " + ", ".join(unknown))
        return _event_response(data, org_keys, types, date_from, date_to, category, q, review, basis, sort, page, page_size, product_code)

    def _event_response(data: Dataset, org_keys: list[str], types: str | None, date_from: str | None, date_to: str | None,
                        category: str | None, q: str | None, review: str | None, basis: str | None, sort: str,
                        page: str | None, page_size: str | None, product_code: str | None = None) -> Any:
        try:
            event_types = _parse_event_types(types)
            categories = _parse_csv(category)
            page_number = _parse_int(page, "page", 1, 1, 100000)
            size = _parse_int(page_size, "page_size", DEFAULT_PAGE_SIZE, 10, MAX_PAGE_SIZE)
        except ValueError as error:
            raise HTTPExceptionCompat(400, "bad_request", str(error))
        if sort not in ("event_date_desc", "event_date_asc", "official_id_asc"):
            raise HTTPExceptionCompat(400, "bad_sort", "sort must be one of event_date_desc, event_date_asc, official_id_asc")
        if review and review not in REVIEW_FILTERS:
            raise HTTPExceptionCompat(400, "bad_review", "review must be one of " + ", ".join(REVIEW_FILTERS))
        raise_for_basis(basis)
        applied = {
            "org": ",".join(org_keys),
            "types": ",".join(event_types),
            "from": date_from or "",
            "to": date_to or "",
            "category": ",".join(categories),
            "product_code": product_code or "",
            "q": q or "",
            "review": review or "",
            "basis": basis or "current_group",
            "sort": sort,
        }
        return _events_payload(data, applied, org_keys, event_types, date_from, date_to, categories, q,
                               None if review in (None, "", "any") else review,
                               None if basis in (None, "", "current_group") else basis, sort, page_number, size,
                               product_code)

    @app.get("/api/events/{event_id:path}")
    def event_detail(event_id: str) -> Any:
        data = dataset()
        event = data.resolve_event(event_id)
        if event is None:
            raise HTTPExceptionCompat(404, "event_not_found", "unknown event identifier: " + event_id + " (expected a full event id such as openfda_510k:K231234, or a unique official FDA identifier)")
        source = next((row for row in data.sources() if row["source_id"] == event.source_id), None)
        queried = None
        for entry in data.manifest.get("organizations") or []:
            for query in entry.get("queries") or []:
                if query.get("source_id") == event.source_id and query.get("urls"):
                    queried = query["urls"][0]
                    break
            if queried:
                break
        return {
            "event": event.to_public(),
            "provenance": {
                "source_id": event.source_id,
                "source_name": source["name"] if source else event.source_id,
                "official_url": event.official_url,
                "queried_endpoint": queried,
                "collected_at": data.collected_at,
                "official_identifier_label": {
                    "openfda_510k": "510(k) number",
                    "openfda_pma": "PMA number (and supplement)",
                    "openfda_recall": "FDA recall product reference",
                }.get(event.source_id, "official identifier"),
                "raw": event.raw,
            },
            "freshness": data.freshness(),
        }

    # ---------------------------------------------------------------- device intelligence (PRODUCT-003)
    def _device_payloads():
        from .device import payloads

        return payloads

    @app.get("/api/devices")
    def devices(q: str | None = None, org: str | None = None, product_code: str | None = None,
                category: str | None = None, pathway: str | None = None, relation: str | None = None,
                sort: str = "relevance", page: int = 1, page_size: int = 25) -> Any:
        data = dataset()
        if org and data.organization(org) is None:
            raise HTTPExceptionCompat(400, "unknown_organization", "unknown organization key: " + org)
        if pathway and pathway not in ("510k", "pma"):
            raise HTTPExceptionCompat(400, "bad_pathway", "pathway must be 510k or pma")
        if relation and relation not in ("confirmed", "candidate", "none", "any"):
            raise HTTPExceptionCompat(400, "bad_relation", "relation must be confirmed, candidate, none or any")
        return _device_payloads().explorer(
            data,
            q=q,
            organization=org,
            product_code=product_code,
            category=category,
            pathway=pathway,
            relation=None if relation in (None, "", "any") else relation,
            page=page,
            page_size=page_size,
            sort=sort,
        )

    @app.get("/api/devices/quality")
    def devices_quality() -> Any:
        data = dataset()
        from .device import quality_report

        payload = quality_report(data.device_index())
        payload["index_build_ms"] = round(data.device_index_build_ms or 0.0, 1)
        payload["snapshot"] = data.snapshot_ref()
        return payload

    @app.get("/api/devices/unlinked")
    def devices_unlinked(page: int = 1, page_size: int = 25) -> Any:
        return _device_payloads().unlinked_recalls(dataset(), page=page, page_size=page_size)

    @app.get("/api/devices/{device_id:path}")
    def device_detail(device_id: str) -> Any:
        payload = _device_payloads().detail(dataset(), device_id)
        if payload is None:
            raise HTTPExceptionCompat(
                404,
                "device_not_found",
                "unknown device identifier: " + device_id,
                "device identifiers look like device:openfda_510k:K123456 or an FDA identifier such as K123456",
            )
        return payload

    @app.get("/api/device-families/{family_id:path}")
    def device_family(family_id: str) -> Any:
        payload = _device_payloads().family_payload(dataset(), family_id)
        if payload is None:
            raise HTTPExceptionCompat(
                404,
                "family_not_found",
                "unknown device family: " + family_id,
                "family identifiers look like family:pma:P980016",
            )
        return payload

    # ---------------------------------------------------------------- compare
    @app.get("/api/compare")
    def compare(orgs: str = Query(default=""), date_from: str | None = Query(default=None, alias="from"),
                date_to: str | None = Query(default=None, alias="to"), types: str | None = None,
                basis: str | None = None, review: str | None = None) -> Any:
        data = dataset()
        keys = _parse_csv(orgs)
        if not keys:
            raise HTTPExceptionCompat(400, "missing_orgs", "orgs is required (comma separated organization keys)")
        try:
            event_types = _parse_event_types(types)
        except ValueError as error:
            raise HTTPExceptionCompat(400, "bad_request", str(error))
        raise_for_basis(basis)
        if review and review not in REVIEW_FILTERS:
            raise HTTPExceptionCompat(400, "bad_review", "review must be one of " + ", ".join(REVIEW_FILTERS))
        try:
            return build_compare(
                data,
                keys,
                date_from,
                date_to,
                event_types or None,
                basis=None if basis in (None, "", "current_group") else basis,
                review=None if review in (None, "", "any") else review,
            )
        except KeyError as error:
            raise HTTPExceptionCompat(404, "organization_not_found", "unknown organization key: " + str(error).strip("'"))
        except ValueError as error:
            raise HTTPExceptionCompat(400, "bad_request", str(error))

    # ---------------------------------------------------------------- exports
    # ---------------------------------------------------------------- intelligence brief (PRODUCT-004)
    def _brief_request(data: Dataset, mode: str, org: str | None, orgs: str | None, device: str | None,
                       years: str | None, date_from: str | None, date_to: str | None, types: str | None,
                       basis: str | None, review: str | None) -> dict[str, Any]:
        """Parse and build one brief. Shared by the JSON endpoint and both exports."""
        if mode not in ("company", "compare", "device"):
            raise HTTPExceptionCompat(400, "bad_mode", "mode must be company, compare or device")
        try:
            event_types = _parse_event_types(types)
            year_value = _parse_int(years, "years", 5, 1, 30) if years else None
        except ValueError as error:
            raise HTTPExceptionCompat(400, "bad_request", str(error))
        if review and review not in REVIEW_FILTERS:
            raise HTTPExceptionCompat(400, "bad_review", "review must be one of " + ", ".join(REVIEW_FILTERS))
        raise_for_basis(basis)
        if date_from or date_to:
            # An explicit window is a complete statement; a years selector is not applied on top.
            year_value = None
        try:
            return brief_module.build_brief(
                data,
                mode=mode,
                org=org,
                orgs=_parse_csv(orgs),
                device=device,
                years=year_value,
                date_from=date_from,
                date_to=date_to,
                event_types=event_types or None,
                basis=basis or "current_group",
                review=None if review in (None, "", "any") else review,
                pipeline_db=app.state.pipeline_db,
            )
        except KeyError as error:
            key = str(error).strip("'")
            code = "device_not_found" if mode == "device" else "organization_not_found"
            raise HTTPExceptionCompat(404, code, "unknown identifier: " + key)
        except ValueError as error:
            raise HTTPExceptionCompat(400, "bad_request", str(error))

    @app.get("/api/brief")
    def brief(mode: str = "company", org: str | None = None, orgs: str | None = None, device: str | None = None,
              years: str | None = None, date_from: str | None = Query(default=None, alias="from"),
              date_to: str | None = Query(default=None, alias="to"), types: str | None = None,
              basis: str | None = None, review: str | None = None) -> Any:
        """The Intelligence Brief: a question, a scope, findings, evidence and limitations."""
        payload = _brief_request(dataset(), mode, org, orgs, device, years, date_from, date_to, types, basis, review)
        return payload

    @app.get("/api/brief/explain")
    def brief_explain(metric: str = Query(default=""), org: str | None = None, orgs: str | None = None,
                      years: str | None = None, date_from: str | None = Query(default=None, alias="from"),
                      date_to: str | None = Query(default=None, alias="to"), types: str | None = None,
                      basis: str | None = None, review: str | None = None) -> Any:
        """Definition, numerator, denominator and the records behind one comparison metric."""
        data = dataset()
        if not metric:
            raise HTTPExceptionCompat(400, "missing_metric", "metric is required")
        try:
            event_types = _parse_event_types(types)
            year_value = _parse_int(years, "years", 5, 1, 30) if years else None
        except ValueError as error:
            raise HTTPExceptionCompat(400, "bad_request", str(error))
        if review and review not in REVIEW_FILTERS:
            raise HTTPExceptionCompat(400, "bad_review", "review must be one of " + ", ".join(REVIEW_FILTERS))
        raise_for_basis(basis)
        if date_from or date_to:
            year_value = None
        keys = _parse_csv(orgs) or _parse_csv(org)
        try:
            return brief_module.explain_metric(
                data, metric=metric, org_keys=keys, years=year_value, date_from=date_from, date_to=date_to,
                event_types=event_types or None, basis=basis or "current_group",
                review=None if review in (None, "", "any") else review,
            )
        except KeyError as error:
            raise HTTPExceptionCompat(404, "organization_not_found", "unknown organization key: " + str(error).strip("'"))
        except ValueError as error:
            raise HTTPExceptionCompat(400, "bad_request", str(error))

    @app.get("/api/export/brief.md")
    def export_brief_md(mode: str = "company", org: str | None = None, orgs: str | None = None,
                        device: str | None = None, years: str | None = None,
                        date_from: str | None = Query(default=None, alias="from"),
                        date_to: str | None = Query(default=None, alias="to"), types: str | None = None,
                        basis: str | None = None, review: str | None = None, lang: str = "en") -> Any:
        """The Intelligence Brief as a Markdown deliverable (English or Chinese)."""
        payload = _brief_request(dataset(), mode, org, orgs, device, years, date_from, date_to, types, basis, review)
        language = lang if lang in ("en", "zh") else "en"
        body = brief_module.brief_markdown(payload, language)
        headers = {"Content-Disposition": 'attachment; filename="' + brief_module.brief_filename(payload) + '"'}
        return Response(content=body.encode("utf-8"), media_type="text/markdown; charset=utf-8", headers=headers)

    @app.get("/api/export/brief-evidence.csv")
    def export_brief_evidence(mode: str = "company", org: str | None = None, orgs: str | None = None,
                              device: str | None = None, years: str | None = None,
                              date_from: str | None = Query(default=None, alias="from"),
                              date_to: str | None = Query(default=None, alias="to"), types: str | None = None,
                              basis: str | None = None, review: str | None = None) -> Any:
        """The Evidence Appendix: one row per supporting record, with official URLs."""
        data = dataset()
        payload = _brief_request(data, mode, org, orgs, device, years, date_from, date_to, types, basis, review)
        body = brief_module.brief_evidence_csv(data, payload)
        rows = body.count("\n") - 1
        headers = {
            "Content-Disposition": 'attachment; filename="' + brief_module.brief_filename(payload).replace(".md", "-evidence.csv") + '"',
            "X-MedRadar-Provenance": provenance_header(data, {"brief": mode, "org": org or "", "orgs": orgs or "", "device": device or ""}),
            "X-MedRadar-Records": str(max(rows, 0)),
        }
        return Response(content=body.encode("utf-8"), media_type="text/csv; charset=utf-8", headers=headers)

    @app.get("/api/export/events.csv")
    def export_events_csv(org: str | None = None, types: str | None = None,
                          date_from: str | None = Query(default=None, alias="from"),
                          date_to: str | None = Query(default=None, alias="to"), category: str | None = None,
                          q: str | None = None, review: str | None = None, basis: str | None = None,
                          product_code: str | None = None,
                          sort: str = "event_date_desc") -> Any:
        data = dataset()
        try:
            event_types = _parse_event_types(types)
            categories = _parse_csv(category)
        except ValueError as error:
            raise HTTPExceptionCompat(400, "bad_request", str(error))
        if review and review not in REVIEW_FILTERS:
            raise HTTPExceptionCompat(400, "bad_review", "review must be one of " + ", ".join(REVIEW_FILTERS))
        raise_for_basis(basis)
        org_keys = _parse_csv(org)
        unknown = [key for key in org_keys if data.organization(key) is None]
        if unknown:
            raise HTTPExceptionCompat(400, "unknown_organization", "unknown organization key(s): " + ", ".join(unknown))
        filtered = data.filter_events(org_keys=org_keys or None, event_types=event_types or None, date_from=date_from,
                                      date_to=date_to, categories=categories or None, query=q,
                                      review=None if review in (None, "", "any") else review,
                                      basis=None if basis in (None, "", "current_group") else basis,
                                      product_code=product_code)
        ordered = data.sort_events(filtered, sort)
        body = events_csv(data, ordered, basis=basis or "current_group")
        filters = {"org": org_keys, "types": event_types, "from": date_from, "to": date_to, "category": categories,
                   "product_code": product_code, "q": q, "review": review, "basis": basis or "current_group"}
        headers = {
            "Content-Disposition": 'attachment; filename="' + csv_filename(data) + '"',
            "X-MedRadar-Provenance": provenance_header(data, filters),
            "X-MedRadar-Records": str(len(ordered)),
        }
        return Response(content=body.encode("utf-8"), media_type="text/csv; charset=utf-8", headers=headers)

    @app.get("/api/export/compare.md")
    def export_compare_md(orgs: str = Query(default=""), date_from: str | None = Query(default=None, alias="from"),
                          date_to: str | None = Query(default=None, alias="to"), types: str | None = None,
                          basis: str | None = None, review: str | None = None) -> Any:
        data = dataset()
        keys = _parse_csv(orgs)
        if not keys:
            raise HTTPExceptionCompat(400, "missing_orgs", "orgs is required")
        raise_for_basis(basis)
        if review and review not in REVIEW_FILTERS:
            raise HTTPExceptionCompat(400, "bad_review", "review must be one of " + ", ".join(REVIEW_FILTERS))
        try:
            event_types = _parse_event_types(types)
            body = compare_markdown(
                data,
                keys,
                date_from,
                date_to,
                event_types or None,
                basis=None if basis in (None, "", "current_group") else basis,
                review=None if review in (None, "", "any") else review,
            )
        except KeyError as error:
            raise HTTPExceptionCompat(404, "organization_not_found", "unknown organization key: " + str(error).strip("'"))
        except ValueError as error:
            raise HTTPExceptionCompat(400, "bad_request", str(error))
        headers = {"Content-Disposition": 'attachment; filename="' + compare_markdown_filename(keys, data) + '"'}
        return Response(content=body.encode("utf-8"), media_type="text/markdown; charset=utf-8", headers=headers)

    @app.get("/api/export/organization.md")
    def export_organization_md(key: str = Query(default="")) -> Any:
        data = dataset()
        if not key or data.organization(key) is None:
            raise HTTPExceptionCompat(404, "organization_not_found", "unknown organization key: " + key)
        body = organization_markdown(data, key)
        headers = {"Content-Disposition": 'attachment; filename="' + organization_markdown_filename(key, data) + '"'}
        return Response(content=body.encode("utf-8"), media_type="text/markdown; charset=utf-8", headers=headers)

    @app.get("/api/export/devices.csv")
    def export_devices_csv(q: str | None = None, org: str | None = None, product_code: str | None = None,
                           category: str | None = None, pathway: str | None = None, relation: str | None = None,
                           sort: str = "relevance") -> Any:
        data = dataset()
        payloads = _device_payloads()
        if org and data.organization(org) is None:
            raise HTTPExceptionCompat(400, "unknown_organization", "unknown organization key: " + org)
        result = payloads.explorer(
            data,
            q=q,
            organization=org,
            product_code=product_code,
            category=category,
            pathway=pathway,
            relation=None if relation in (None, "", "any") else relation,
            page=1,
            page_size=100,
            sort=sort,
        )
        # CSV must contain every matching row, not the first page: rebuild without paging.
        all_rows = payloads.explorer(
            data,
            q=q,
            organization=org,
            product_code=product_code,
            category=category,
            pathway=pathway,
            relation=None if relation in (None, "", "any") else relation,
            page=1,
            page_size=result["total"] or 1,
            sort=sort,
        )
        rows = []
        index = data.device_index()
        for item in all_rows["items"]:
            device = index.devices.get(item["device_id"])
            if device is None:
                continue
            rows.append({"device": device, "counts": item["counts"], "organization_display": item.get("organization_display")})
        body = payloads.devices_csv(data, rows)
        filters = {"q": q, "org": org, "product_code": product_code, "category": category, "pathway": pathway, "relation": relation}
        headers = {
            "Content-Disposition": 'attachment; filename="medradar-devices-' + str(data.collected_at)[:10] + '.csv"',
            "X-MedRadar-Provenance": provenance_header(data, filters),
            "X-MedRadar-Records": str(len(rows)),
        }
        return Response(content=body.encode("utf-8"), media_type="text/csv; charset=utf-8", headers=headers)

    @app.get("/api/export/device.md")
    def export_device_md(device: str = Query(default="")) -> Any:
        payloads = _device_payloads()
        data = dataset()
        if not device:
            raise HTTPExceptionCompat(400, "missing_device", "device is required (a device id or an FDA identifier)")
        body = payloads.device_markdown(data, device)
        if body is None:
            raise HTTPExceptionCompat(404, "device_not_found", "unknown device identifier: " + device)
        headers = {"Content-Disposition": 'attachment; filename="medradar-device-' + device.replace(":", "-") + '.md"'}
        return Response(content=body.encode("utf-8"), media_type="text/markdown; charset=utf-8", headers=headers)

    # ---------------------------------------------------------------- transparency
    @app.get("/api/metrics")
    def metrics() -> Any:
        """Every attribution/coverage claim the product makes, with definitions and UNKNOWNs."""
        data = dataset()
        payload = data.metrics()
        payload["snapshot"] = data.snapshot_ref()
        payload["freshness"] = data.freshness()
        payload["metric_definitions"] = status_module.metric_definitions()
        return payload

    @app.get("/api/ownership")
    def ownership() -> Any:
        """Ownership relations: what is verified, with dates and sources, and what is UNKNOWN."""
        registry = ownership_module.ownership()
        return {
            "schema": "medradar.ownership.v1",
            "updated_at": registry.updated_at,
            "note": registry.note,
            "concepts": {
                "original_applicant": "The exact applicant string FDA recorded on the record.",
                "historical_owner": "Who controlled the filing entity when the event happened; stated only where an independent source with an effective date exists.",
                "current_group": "The tracked organization the entity belongs to today; this is what the product counts by default.",
            },
            "relations": [relation.to_public() for relation in registry.relations],
            "verified_count": sum(1 for relation in registry.relations if relation.verified),
            "unresolved_count": sum(1 for relation in registry.relations if not relation.verified),
            "organizations_with_verified_history": sorted(
                {relation.organization_key for relation in registry.relations if relation.verified}
            ),
        }

    @app.get("/api/coverage")
    def coverage() -> Any:
        data = dataset()
        organizations = []
        for org in sorted(data.registry.organizations, key=lambda item: item.display_name.casefold()):
            stats = data.org_stats.get(org.key)
            organizations.append({
                "key": org.key,
                "display_name": org.display_name,
                "records": stats.counts["records"] if stats else 0,
                "sources": [
                    {"source_id": row["source_id"], "records": row["records"],
                     "min_event_date": row["min_event_date"], "max_event_date": row["max_event_date"]}
                    for row in (stats.sources if stats else [])
                ],
                "pending_review_spellings": len([item for item in data.registry.accepted_spellings_by_org.get(org.key, ()) if item.review == "pending_review"]),
            })
        audit = _collection_audit(data)
        counts = data.manifest.get("counts") or {}
        files = data.manifest.get("files") or {}
        return {
            "snapshot": data.snapshot_ref(),
            "freshness": data.freshness(),
            "sources": data.sources(),
            "organizations": organizations,
            "collection_audit": audit,
            "out_of_scope": dataset_module.OUT_OF_SCOPE,
            "time_semantics": dataset_module.TIME_SEMANTICS,
            "manifest": {
                "id": data.snapshot_id,
                "collected_at": data.collected_at,
                "collection_started_at": data.manifest.get("collection_started_at"),
                "openfda_last_updated": (data.manifest.get("openfda") or {}).get("last_updated"),
                "request_count": data.manifest.get("request_count"),
                "response_bytes": data.manifest.get("response_bytes"),
                "organization_count": data.manifest.get("organization_count"),
                "counts": counts,
                "data_quality": data.manifest.get("data_quality") or {},
                "errors": data.manifest.get("errors") or [],
                "files": [
                    {"name": name, "sha256": meta.get("sha256"), "bytes": meta.get("bytes"), "records": meta.get("records")}
                    for name, meta in files.items()
                ],
                "notes": data.manifest.get("notes") or [],
            },
            "limitations": data.limitations(),
            "metrics": data.metrics_summary(),
            "status_vocabulary": status_module.status_summary(data.registry.status_counts()),
            "attribution_summary": {
                "accepted_spellings": len(data.registry.decisions),
                "verified_spellings": sum(1 for decision in data.registry.decisions.values() if decision.verified),
                "rule_verified_spellings": sum(1 for decision in data.registry.decisions.values() if decision.rule_verified),
                "proposed_spellings": sum(1 for decision in data.registry.decisions.values() if decision.provisional),
                "curated_spellings": sum(1 for decision in data.registry.decisions.values() if decision.verified),
                "pending_review_spellings": sum(1 for decision in data.registry.decisions.values() if decision.provisional),
                "rejected_spellings": sum(len(org.reject_exact) for org in data.registry.organizations),
                "unattributed_applicant_strings": len(audit["unattributed"]),
                "unattributed_records": len(data.events) - data.global_counts["records"],
                "review_ledger_decisions_applied": data.review_overlay_applied,
            },
            "reproduce": {
                "collect": "python scripts/product_collect.py",
                "curate": "python scripts/product_curate_aliases.py --apply",
                "serve": "python -m medradar web --port 8787",
                "test": "python -m pytest tests/product -q",
            },
        };

    def _collection_audit(data: Dataset) -> dict[str, Any]:
        tokens = []
        for entry in data.manifest.get("organizations") or []:
            for query in entry.get("queries") or []:
                tokens.append({
                    "token": entry.get("key") or "",
                    "org_key": entry.get("key") or "",
                    "endpoint": query.get("source_id") or "",
                    "records_retrieved": int(query.get("records") or 0),
                    "pages": int(query.get("pages") or 0),
                    "urls": (query.get("urls") or [])[:3],
                })
        unattributed = []
        rejected = []
        for row in data.applicants:
            name = str(row.get("applicant_name") or "")
            decision, rejection = data.registry.decide(name)
            if decision is not None:
                continue
            if rejection is not None:
                rejected.append({"applicant_name": name, "org_key": rejection.organization_key, "reason": rejection.reason})
            else:
                unattributed.append({
                    "applicant_name": name,
                    "records": int(row.get("records") or 0),
                    "endpoints": sorted((row.get("by_source") or {}).keys()),
                })
        unattributed.sort(key=lambda item: -item["records"])
        return {"tokens": tokens, "unattributed": unattributed, "rejected": rejected}

    @app.get("/api/attribution")
    def attribution() -> Any:
        data = dataset()
        decisions = []
        for org in data.registry.organizations:
            for decision in data.registry.accepted_spellings_by_org.get(org.key, ()):
                row = data.applicant_by_name.get(decision.applicant_name) or {}
                decisions.append({
                    "organization_key": org.key,
                    "organization_display": org.display_name,
                    "applicant_name": decision.applicant_name,
                    "basis": decision.basis,
                    "review": decision.review,
                    "status": decision.status,
                    "status_label_en": status_module.STATUS_LABELS_EN.get(decision.status, decision.status),
                    "status_label_zh": status_module.STATUS_LABELS_ZH.get(decision.status, decision.status),
                    "verified": decision.verified,
                    "rule_verified": decision.rule_verified,
                    "provisional": decision.provisional,
                    "rule": decision.rule,
                    "rule_detail": decision.rule_detail,
                    "evidence": [item.to_public() for item in decision.evidence] or [{"evidence_type": "registry_record", "note": decision.source or "registry"}],
                    "evidence_count": len(decision.evidence),
                    "reviewer": decision.reviewer,
                    "reviewer_kind": decision.reviewer_kind,
                    "decision_uid": decision.decision_uid,
                    "record_count": int(row.get("records") or 0),
                })
        decisions.sort(key=lambda item: (-item["record_count"], item["organization_key"], item["applicant_name"]))
        rejected = []
        unmatched = []
        for row in data.applicants:
            name = str(row.get("applicant_name") or "")
            decision, rejection = data.registry.decide(name)
            if decision is not None:
                continue
            if rejection is not None:
                rejected.append({"applicant_name": name, "organization_key": rejection.organization_key, "reason": rejection.reason})
            else:
                unmatched.append({
                    "applicant_name": name,
                    "records": int(row.get("records") or 0),
                    "endpoints": sorted((row.get("by_source") or {}).keys()),
                    "seen_with_tokens": sorted((row.get("by_org_scope") or {}).keys()),
                })
        unmatched.sort(key=lambda item: -item["records"])
        return {
            "decisions": decisions,
            "rejected": rejected,
            "unmatched": unmatched,
            "policy": [
                "Attribution is exact applicant-name matching after case folding and whitespace collapse; the verbatim string is preserved.",
                "No fuzzy, prefix or substring matching is used for attribution.",
                "Strings not in the registry stay unattributed and are counted in the audit, never folded into an organization.",
                "Each mapping carries a verification status: proposed (no verification), rule_verified (deterministic rule), evidence_verified (independent document recorded) or human_reviewed (named human decision).",
                "Rule-verified is NOT human review and is reported separately from curated share.",
                "Only the internal review workspace can change a mapping; the public API is read-only.",
            ],
            "status_counts": data.registry.status_counts(),
            "snapshot": data.snapshot_ref(),
        }

    # ---------------------------------------------------------------- extension point
    # Anything registered here is matched before the SPA catch-all below.
    # RADAR-001: the Live Intelligence Radar and the Company Technology Graph are mounted as a
    # separate read-only router. Its absence (no radar data directory) is a visible 503 from
    # the radar endpoints, never a broken workbench.
    resolved_radar = radar_dir if radar_dir is not None else os.environ.get("MEDRADAR_RADAR_DIR")
    if resolved_radar:
        try:
            from ..radar.api import RadarService, build_router

            app.include_router(build_router(RadarService(resolved_radar)))
            app.state.radar_dir = str(resolved_radar)
        except Exception as error:  # pragma: no cover - the workbench must still start
            app.state.radar_error = f"{type(error).__name__}: {error}"
    if setup is not None:
        setup(app)

    # ---------------------------------------------------------------- static UI
    @app.get("/")
    def index() -> Any:
        return _serve_index(resolved_web)

    @app.get("/favicon.svg")
    def favicon() -> Any:
        candidate = resolved_web / "favicon.svg"
        if candidate.is_file():
            return FileResponse(candidate, media_type="image/svg+xml")
        raise HTTPExceptionCompat(404, "not_found", "favicon not built")

    @app.get("/{path:path}")
    def spa(path: str) -> Any:
        if path.startswith("api/"):
            raise HTTPExceptionCompat(404, "not_found", "unknown API route: /" + path)
        candidate = resolved_web / path
        if candidate.is_file() and resolved_web in candidate.resolve().parents:
            return FileResponse(candidate)
        return _serve_index(resolved_web)

    @app.exception_handler(HTTPExceptionCompat)
    async def handle_http_error(request: Request, exc: "HTTPExceptionCompat") -> JSONResponse:
        return _error(exc.status_code, exc.code, exc.message, exc.hint)

    @app.exception_handler(Exception)
    async def handle_unexpected(request: Request, exc: Exception) -> JSONResponse:
        return _error(500, "internal_error", "unexpected server error: " + str(exc))

    return app


def _default_web_dir() -> Path:
    candidates = []
    env = os.environ.get("MEDRADAR_WEB_DIR")
    if env:
        candidates.append(Path(env))
    candidates.append(Path(__file__).resolve().parents[2] / "web" / "dist")
    candidates.append(Path(__file__).resolve().parents[2] / "web")
    candidates.append(Path(sys.prefix) / "share" / "medradar" / "web")
    for candidate in candidates:
        if (candidate / "index.html").is_file():
            return candidate
    return candidates[-1]


def _serve_index(web_dir: Path) -> Any:
    index = web_dir / "index.html"
    if not index.is_file():
        return _error(503, "ui_not_built", "the web workbench has not been built",
                      "run: cd web && npm install && npm run build")
    return FileResponse(index)


class HTTPExceptionCompat(Exception):
    def __init__(self, status_code: int, code: str, message: str, hint: str | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.hint = hint