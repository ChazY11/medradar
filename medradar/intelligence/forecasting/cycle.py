"""Continuous forecasting cycle: train -> score -> register -> verify -> export.

One idempotent run of the unified forecasting pipeline over the research
database:

1. **train** - load the frozen continuation examples (``dataset_version``
   ``reverse_rd_v1``) from ``forecast_examples`` and fit the same deterministic
   :class:`~medradar.intelligence.models.baseline.LogisticBaseline` used by the
   frozen reverse_rd_v2 run (same 10 R&D-history + 11 SEC features, defaults
   180 epochs / lr 0.15 / l2 1.0);
2. **score** - build the current quarter's pending company-track candidates and
   rank them by predicted probability;
3. **create** - assemble Horizon records (:func:`horizon.build_forecasts`,
   the pure counterpart of ``horizon.create_forecasts``);
4. **register** - map every record into the canonical immutable
   :class:`~medradar.forecast_registry.ForecastRegistry` as a ``nowcast`` via
   :mod:`medradar.intelligence.forecasting.registry_adapter` (idempotent, never
   overwrites a conflicting probability);
5. **verify** - resolve matured registered nowcasts from the real events table
   only when their entire window matured inside the observed coverage;
6. **export** - deterministic evaluation artifact + a JSON cycle log.

The cycle is offline (no network) and deterministic apart from timestamps: the
same inputs produce the same forecast ids, probabilities, registration outcome
and artifact hash; a second run registers zero new rows (``idempotent`` > 0).

CLI entry point: ``scripts/forecast_cycle.py``.
"""
from __future__ import annotations

import hashlib
import time
from pathlib import Path
from typing import Any, Mapping

from ...forecast_registry import ForecastRegistry, canonical_json, sha256_hex, write_artifact
from ...util import read_json, utc_now_iso, write_json
from ..features.financial_features import FEATURES as FINANCIAL_FEATURES
from ..features.research_features import BASE_FEATURES, DATASET_VERSION
from ..storage import IntelligenceStore
from . import horizon
from .registry_adapter import FEATURE_VERSION, register_horizon_forecasts, verify_registered_forecasts

CYCLE_VERSION = "forecast-cycle-1"


def _display_path(path: Path) -> str:
    """Stable-ish source locator: relative to cwd when possible."""
    try:
        return path.resolve().relative_to(Path.cwd().resolve()).as_posix()
    except ValueError:
        return path.resolve().as_posix()


def _data_provenance(store: IntelligenceStore, db_path: Path,
                     provenance_path: Path | None) -> dict[str, Any]:
    """Explicit provenance block for the canonical evidence record.

    Prefers the frozen collection provenance file (real file SHA256 + real
    ``retrieved_at``) when present; otherwise falls back to the research DB
    itself with the observed coverage as the retrieval marker. Never invents a
    hash: the evidence digest is the SHA256 of the canonical provenance JSON.
    """
    if provenance_path is not None:
        path = Path(provenance_path)
        if path.is_file():
            payload = read_json(path, {}) or {}
            entry: dict[str, Any] = {
                "source": _display_path(path),
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "note": (
                    "frozen reverse_rd_v2 collection provenance"
                    f" (fda_event_count={payload.get('fda_event_count')},"
                    f" coverage {payload.get('fda_coverage_start')}..{payload.get('fda_coverage_end')})"
                ),
            }
            if payload.get("retrieved_at"):
                entry["retrieved_at"] = str(payload["retrieved_at"])
            return {"entries": [entry]}
    coverage = store.conn.execute("SELECT MAX(event_date) FROM events").fetchone()[0]
    return {"entries": [{
        "source": f"sqlite:///{Path(db_path).as_posix()}",
        "retrieved_at": str(coverage) if coverage else None,
        "note": "research DB event coverage at cycle time",
    }]}


def _coverage_end(store: IntelligenceStore, coverage_end: Any) -> str:
    if coverage_end is None:
        observed = store.conn.execute("SELECT MAX(event_date) FROM events").fetchone()[0]
        if not observed:
            raise ValueError("cannot derive coverage end: no events in the research DB")
        return str(observed)[:10]
    text = str(coverage_end).strip()
    if not text:
        raise ValueError("invalid coverage end")
    return text[:10]


def _registry_summary(registry: ForecastRegistry) -> dict[str, Any]:
    by_kind = {
        row[0]: int(row[1])
        for row in registry.conn.execute(
            "SELECT record_kind, COUNT(*) FROM forecasts GROUP BY record_kind")
    }
    return {
        "forecasts_total": registry.count("forecasts"),
        "by_record_kind": by_kind,
        "resolutions_total": registry.count("resolutions"),
        "idempotency_keys_total": registry.count("forecast_idempotency"),
    }


def _calibration_status(store: IntelligenceStore, artifact: Mapping[str, Any]) -> dict[str, Any]:
    evaluation = artifact["evaluation"]
    nowcast = evaluation["nowcast"]["counts"]
    eligible = int(nowcast["eligible"])
    research_verified = int(store.conn.execute(
        "SELECT COUNT(*) FROM horizon_forecasts WHERE status = 'verified'").fetchone()[0])
    return {
        "nowcast_registered": int(nowcast["total_forecasts"]),
        "nowcast_eligible": eligible,
        "nowcast_unresolved": int(nowcast["unresolved"]),
        "research_registry_verified": research_verified,
        "status": "evaluated" if eligible >= 20 else "insufficient_matured_forecasts",
        "note": (
            "No calibration claim is made until at least 20 registered nowcasts have matured"
            " and been verified inside the observed coverage; ECE/Brier for fewer rows are not"
            " meaningful. Registered 2026-Q4 nowcasts mature 2027-10-01, after the frozen"
            " coverage end, so they are expected to stay pending."
        ),
    }


def _artifact_as_of(registry: ForecastRegistry) -> str:
    """Deterministic evaluation cutoff for the exported artifact.

    ``registry._read_now()`` would embed the wall clock, so two identical
    re-runs of the same registry state would produce different artifact
    hashes. The artifact is instead cut at the latest *assigned* registry
    timestamp (``clock_guard.last_at``) or the latest resolution: duplicate
    retries consume no write clock, so a re-run of the same state exports the
    identical artifact. Timestamps only differ when new history is written.
    """
    candidates: list[str] = []
    row = registry.conn.execute("SELECT last_at FROM clock_guard WHERE id = 1").fetchone()
    if row is not None and row[0]:
        candidates.append(str(row[0]))
    row = registry.conn.execute("SELECT MAX(resolved_at) AS last FROM resolutions").fetchone()
    if row is not None and row["last"]:
        candidates.append(str(row["last"]))
    return max(candidates) if candidates else registry._read_now()


def run_cycle(
    *,
    db_path: str | Path,
    out_dir: str | Path,
    registry_db: str | Path | None = None,
    registry: ForecastRegistry | None = None,
    horizon_months: int = 12,
    top_n: int = 25,
    coverage_end: Any = None,
    dataset_version: str = DATASET_VERSION,
    feature_version: str = FEATURE_VERSION,
    provenance_path: str | Path | None = None,
    snapshot_path: str | Path | None = None,
    as_of: Any = None,
    offline: bool = True,
    save_log: bool = True,
) -> dict[str, Any]:
    """Run one cycle; returns the JSON-serialisable cycle log.

    ``registry`` may be supplied for deterministic tests (e.g. an in-memory
    registry with an injected clock); otherwise a registry is opened at
    ``registry_db`` and closed before returning. ``offline`` is accepted so the
    CLI can state the mode explicitly; the cycle never performs network I/O.
    """
    started = time.perf_counter()
    timings: dict[str, float] = {}
    db = Path(db_path)
    out = Path(out_dir)
    owns_registry = registry is None
    store = IntelligenceStore(db)
    try:
        coverage = _coverage_end(store, coverage_end)
        if registry is None:
            registry_path = Path(registry_db) if registry_db is not None else db.parent / "registry.sqlite"
            registry = ForecastRegistry(registry_path)
        provenance = _data_provenance(store, db, Path(provenance_path) if provenance_path else None)

        step = time.perf_counter()
        records = horizon.build_forecasts(
            store,
            base_features=list(BASE_FEATURES),
            financial_features=list(FINANCIAL_FEATURES),
            coverage_end=coverage,
            horizon_months=horizon_months,
            top_n=top_n,
            dataset_version=dataset_version,
        )
        timings["train_score_seconds"] = round(time.perf_counter() - step, 3)

        step = time.perf_counter()
        registration = register_horizon_forecasts(
            registry, records,
            data_provenance=provenance,
            feature_version=feature_version,
            snapshot_path=snapshot_path,
        )
        timings["register_seconds"] = round(time.perf_counter() - step, 3)

        step = time.perf_counter()
        verification = verify_registered_forecasts(registry, store, coverage, as_of=as_of)
        timings["verify_seconds"] = round(time.perf_counter() - step, 3)

        step = time.perf_counter()
        artifact_as_of = as_of if as_of is not None else _artifact_as_of(registry)
        artifact = registry.build_artifact(artifact_as_of)
        written = write_artifact(artifact, out)
        timings["export_seconds"] = round(time.perf_counter() - step, 3)
        timings["total_seconds"] = round(time.perf_counter() - started, 3)

        forecast_ids = sorted(str(record["forecast_id"]) for record in records)
        run_id = sha256_hex(canonical_json({
            "cycle_version": CYCLE_VERSION,
            "coverage_end": coverage,
            "dataset_version": dataset_version,
            "feature_version": feature_version,
            "horizon_months": horizon_months,
            "top_n": top_n,
            "forecast_ids": forecast_ids,
        }))[:16]
        evaluation = artifact["evaluation"]
        log: dict[str, Any] = {
            "cycle_version": CYCLE_VERSION,
            "run_id": run_id,
            "generated_at": utc_now_iso(),
            "offline": bool(offline),
            "inputs": {
                "db": str(db),
                "registry": str(registry.path),
                "coverage_end": coverage,
                "horizon_months": horizon_months,
                "top_n": top_n,
                "dataset_version": dataset_version,
                "feature_version": feature_version,
                "provenance": provenance,
            },
            "counts": {
                "horizon_records": len(records),
                "registered": registration["registered"],
                "idempotent": registration["idempotent"],
                "rejected": len(registration["rejected"]),
                "verified": verification["verified"],
                "positives": verification["positives"],
                "pending": verification["pending"],
                "verification_errors": verification["errors"],
            },
            "registration": registration,
            "verification": verification,
            "registry": _registry_summary(registry),
            "artifact": {
                "path": str(written["evaluation.json"]),
                "sha256": artifact["manifest"]["artifact_sha256"],
                "as_of": artifact["manifest"]["as_of"],
                "counts_by_record_kind": artifact["manifest"]["counts_by_record_kind"],
            },
            "evaluation": {
                "pure_forecast_headline": evaluation["headline"],
                "nowcast_headline": evaluation["nowcast"]["headline"],
                "record_kind_breakdown": evaluation["record_kind_breakdown"],
            },
            "calibration": _calibration_status(store, artifact),
            "timings": timings,
        }
        if save_log:
            write_json(out / "cycle.json", log)
        return log
    finally:
        store.close()
        if owns_registry and registry is not None:
            registry.close()


def summary(log: Mapping[str, Any]) -> dict[str, Any]:
    """Compact console summary (no per-forecast dump)."""
    return {
        "run_id": log["run_id"],
        "coverage_end": log["inputs"]["coverage_end"],
        "horizon_records": log["counts"]["horizon_records"],
        "registered": log["counts"]["registered"],
        "idempotent": log["counts"]["idempotent"],
        "rejected": log["counts"]["rejected"],
        "verified": log["counts"]["verified"],
        "pending": log["counts"]["pending"],
        "registry": log["registry"],
        "artifact_sha256": log["artifact"]["sha256"],
        "calibration_status": log["calibration"]["status"],
        "timings": log["timings"],
    }
