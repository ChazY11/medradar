"""Adapter: Horizon forecasting records -> canonical Forecast Registry.

The Horizon lane (`medradar.intelligence.forecasting.horizon`) produces real
forecasts anchored on a quarterly information cutoff ``t`` with target window
``(t, t + horizon]``. It used to store those rows only in the research DB,
disconnected from the canonical immutable registry. This module maps a Horizon
record to a canonical registration spec and provides the two operations a
continuous cycle needs:

* :func:`to_registry_spec` / :func:`register_horizon_forecasts` - register the
  records as ``record_kind='nowcast'``. A quarterly-cutoff forecast is created
  after its cutoff, i.e. while the target window is already open; that is a
  nowcast, not a pure ex-ante ``forecast`` (impossible under the future-only
  rule) and not a ``retrospective_fixture`` (which would be false).
* :func:`verify_registered_forecasts` - resolve matured registered nowcasts
  from the real events table with strict coverage guards. A window that has
  not fully matured inside the observed coverage is left ``pending``; it is
  never resolved from incomplete data.

Honesty boundaries: this adapter derives probabilities only from the frozen
Horizon model (it never invents a probability), all provenance is explicit, and
the canonical registry remains append-only. Re-registering the same mapping is
idempotent; a different probability under the same key raises
:class:`~medradar.forecast_registry.IdempotencyConflict` instead of silently
overwriting.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from ...forecast_registry import (
    ForecastRegistry,
    ForecastRegistryError,
    ForecastValidationError,
    IdempotencyConflict,
    canonical_json,
    normalize_moment,
    sha256_hex,
)
from ..features.research_features import _material_pma

# Feature contract of the frozen reverse_rd_v2 continuation run: the set of
# features the Horizon model was trained on (ten R&D-history + eleven SEC
# Company Facts features). Kept as an explicit version string so a future
# feature change cannot silently masquerade as the same forecast.
FEATURE_VERSION = "reverse-rd-v2-features"
RECORD_KIND = "nowcast"
EVIDENCE_KIND = "source_observed"
EVENT_KINDS = ("510k", "pma")


# --------------------------------------------------------------- provenance
def _provenance_entries(data_provenance: Any) -> list[dict[str, str]]:
    """Normalise the caller's provenance block into sorted source entries.

    Accepted shapes: a single mapping (``{source, retrieved_at, note, sha256}``
    or ``{path|sqlite_uri, ...}``), a mapping with an ``entries`` list, or a
    list of such mappings. ``source`` is required; ``sha256`` is the real file
    digest when the caller has one, otherwise it is derived deterministically.
    """
    if isinstance(data_provenance, Mapping):
        raw_entries = data_provenance.get("entries") if "entries" in data_provenance else [data_provenance]
    elif isinstance(data_provenance, (list, tuple)):
        raw_entries = list(data_provenance)
    else:  # pragma: no cover - defensive; cycle always passes structured data
        raise ForecastValidationError("data_provenance must be an object or a list of objects")
    entries: list[dict[str, str]] = []
    for index, entry in enumerate(raw_entries or []):
        if not isinstance(entry, Mapping):
            raise ForecastValidationError(f"data_provenance[{index}] must be an object")
        source = str(
            entry.get("source") or entry.get("source_locator") or entry.get("path")
            or entry.get("sqlite_uri") or ""
        ).strip()
        if not source:
            raise ForecastValidationError(f"data_provenance[{index}]: a source locator is required")
        cleaned = {"source": source}
        for key in ("retrieved_at", "note"):
            value = entry.get(key)
            if value:
                cleaned[key] = str(value)
        if entry.get("sha256"):
            cleaned["sha256"] = str(entry["sha256"]).strip().lower()
        entries.append(cleaned)
    if not entries:
        raise ForecastValidationError("data_provenance must contain at least one source entry")
    entries.sort(key=lambda item: (item["source"], item.get("retrieved_at") or ""))
    return entries


def _provenance_payload(entries: Sequence[Mapping[str, str]]) -> list[dict[str, str | None]]:
    return [
        {"source": entry["source"], "retrieved_at": entry.get("retrieved_at"), "note": entry.get("note")}
        for entry in entries
    ]


def _registry_provenance(entries: Sequence[Mapping[str, str]]) -> list[dict[str, str]]:
    """Registry-shaped provenance: ``{source_locator, evidence_sha256}`` pairs."""
    provenance = []
    for entry in entries:
        digest = entry.get("sha256") or sha256_hex(canonical_json({
            "source": entry["source"],
            "retrieved_at": entry.get("retrieved_at"),
            "note": entry.get("note"),
        }))
        provenance.append({"source_locator": entry["source"], "evidence_sha256": digest})
    return provenance


def _snapshot_block(snapshot_path: str | Path | None) -> dict[str, Any]:
    """A local TKG ``snapshot.json`` becomes verified-local snapshot provenance."""
    if snapshot_path is None:
        return {}
    path = Path(snapshot_path)
    if not path.is_file():
        raise ForecastValidationError(f"snapshot_path does not exist: {path}")
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
        digest = document["manifest"]["snapshot_sha256"]
    except (OSError, json.JSONDecodeError, KeyError, TypeError) as exc:
        raise ForecastValidationError(f"snapshot_path is not a medradar-tkg snapshot.json: {path}") from exc
    return {"snapshot": {"sha256": digest, "path": str(path.resolve())}}


# ------------------------------------------------------------------ mapping
def to_registry_spec(
    record: Mapping[str, Any],
    *,
    data_provenance: Any,
    feature_version: str,
    snapshot_path: str | Path | None = None,
) -> dict[str, Any]:
    """Map one Horizon record to a canonical (nowcast) registration spec.

    Mapping table (also documented in ``docs/PHASE3_REGISTRY.md``):

    =========================  =================================================
    Horizon record             registry spec
    =========================  =================================================
    ``forecast_id`` +          ``idempotency_key = "horizon:<fid>:<model>``
    ``model_version``
    (always)                   ``record_kind = "nowcast"``
    ``target_company`` +       ``target.type = "company_track"``, ``target.id``
    ``technology_track``       ``"<company>/<track>"``, attrs carry the
                               company/track/event filter
    ``predicted_probability``  ``p``
    ``forecast_horizon_months````horizon_months``
    ``historical_information_  ``information_cutoff`` and ``window_start``
    cutoff``
    ``horizon_end``            explicit ``window_end`` (registry re-derives and
                               rejects a mismatch)
    ``model_version``          ``model_version``
    --                         ``feature_version`` (caller constant)
    provenance block            ``evidence`` (locator, sha256 of canonical
                               provenance JSON, ``source_observed``, entries)
    snapshot file (optional)   ``snapshot`` (verified-local if supplied)
    =========================  =================================================
    """
    if not isinstance(record, Mapping):
        raise ForecastValidationError("horizon record must be an object")
    forecast_id = str(record.get("forecast_id") or "").strip()
    company = str(record.get("target_company") or "").strip()
    track = str(record.get("technology_track") or "").strip()
    cutoff = record.get("historical_information_cutoff")
    horizon = record.get("forecast_horizon_months")
    model_version = str(record.get("model_version") or "").strip()
    if not forecast_id:
        raise ForecastValidationError("horizon record is missing forecast_id")
    if not company or not track:
        raise ForecastValidationError(f"forecast {forecast_id}: target_company and technology_track are required")
    if cutoff is None:
        raise ForecastValidationError(f"forecast {forecast_id}: historical_information_cutoff is required")
    if not model_version:
        raise ForecastValidationError(f"forecast {forecast_id}: model_version is required")
    if isinstance(horizon, bool) or not isinstance(horizon, int):
        raise ForecastValidationError(f"forecast {forecast_id}: forecast_horizon_months must be an integer")

    entries = _provenance_entries(data_provenance)
    provenance_payload = _provenance_payload(entries)
    spec: dict[str, Any] = {
        "idempotency_key": f"horizon:{forecast_id}:{model_version}",
        "record_kind": RECORD_KIND,
        "target": {
            "type": "company_track",
            "id": f"{company}/{track}",
            "attrs": {
                "company": company,
                "track": track,
                "event_kinds": list(EVENT_KINDS),
                "material_pma_only": True,
            },
        },
        "horizon_months": horizon,
        "p": record.get("predicted_probability"),
        "information_cutoff": cutoff,
        "window_start": cutoff,
        "model_version": model_version,
        "feature_version": str(feature_version or "").strip(),
        "evidence": {
            "source_locator": entries[0]["source"],
            "evidence_sha256": sha256_hex(canonical_json(provenance_payload)),
            "evidence_kind": EVIDENCE_KIND,
            "provenance": _registry_provenance(entries),
        },
    }
    if record.get("horizon_end") is not None:
        # The registry re-derives the end from window_start + horizon and
        # rejects any mismatch, so this cross-checks the Horizon record itself.
        spec["window_end"] = record["horizon_end"]
    spec.update(_snapshot_block(snapshot_path))
    return spec


# ------------------------------------------------------------- registration
def register_horizon_forecasts(
    registry: ForecastRegistry,
    records: Iterable[Mapping[str, Any]],
    *,
    data_provenance: Any,
    feature_version: str,
    snapshot_path: str | Path | None = None,
) -> dict[str, Any]:
    """Register Horizon records idempotently; never overwrite on conflict.

    Returns ``{"registered", "idempotent", "rejected": [{forecast_id, error}],
    "prediction_ids": [...]}``. An exact retry is counted as ``idempotent``;
    a reused key with **different** content raises
    :class:`IdempotencyConflict` (it is *not* downgraded to a rejection, so an
    operator cannot miss a silently conflicting forecast).
    """
    counts: dict[str, Any] = {"registered": 0, "idempotent": 0, "rejected": [], "prediction_ids": []}
    for record in records:
        forecast_id = str(record.get("forecast_id") or "") if isinstance(record, Mapping) else ""
        try:
            spec = to_registry_spec(
                record, data_provenance=data_provenance,
                feature_version=feature_version, snapshot_path=snapshot_path,
            )
            result = registry.register(spec)
        except IdempotencyConflict:
            raise
        except ForecastRegistryError as exc:
            counts["rejected"].append({"forecast_id": forecast_id, "error": str(exc)})
            continue
        if result.get("status") == "duplicate":
            counts["idempotent"] += 1
        else:
            counts["registered"] += 1
        counts["prediction_ids"].append(result["prediction_id"])
    return counts


# ------------------------------------------------------------- verification
def _material_events(
    store: Any,
    *,
    company: str,
    track: str,
    window_start: str,
    window_end: str,
    coverage_day: str,
    kinds: Sequence[str],
    material_pma_only: bool,
) -> list[dict[str, Any]]:
    """Material public events inside ``(window_start, window_end]``.

    Event dates are day-granular (the Horizon verification condition also uses
    ``event_date_after``/``event_date_on_or_before``), so the datetime window
    is narrowed to its day bounds. Rows whose public availability is after
    ``coverage_day`` are excluded: using them would resolve from knowledge the
    coverage window does not contain.
    """
    start_day, end_day = window_start[:10], window_end[:10]
    placeholders = ",".join("?" for _ in kinds)
    rows = store.conn.execute(
        "SELECT event_id, kind, event_date, available_at, payload FROM events"
        " WHERE company_key = ? AND track_id = ?"
        f" AND kind IN ({placeholders}) AND event_date > ? AND event_date <= ?"
        " ORDER BY event_date, event_id",
        (company, track, *kinds, start_day, end_day),
    ).fetchall()
    material: list[dict[str, Any]] = []
    for row in rows:
        event = dict(row)
        if event["kind"] == "pma" and material_pma_only and not _material_pma(event.get("payload") or ""):
            continue  # non-material PMA supplements do not count
        available = str(event.get("available_at") or event.get("event_date") or "")[:10]
        if available and available > coverage_day:
            continue  # not public yet inside the observed coverage
        material.append(event)
    return material


def _resolution_evidence(company: str, track: str, window_start: str, window_end: str,
                         coverage_day: str, event: Mapping[str, Any] | None) -> dict[str, str]:
    if event is not None:
        payload = {
            "event_id": event["event_id"],
            "kind": event["kind"],
            "event_date": event["event_date"],
            "payload": event.get("payload"),
        }
        return {
            "source_locator": f"research-db://events/{event['event_id']}",
            "evidence_kind": EVIDENCE_KIND,
            "evidence_sha256": sha256_hex(canonical_json(payload)),
        }
    payload = {
        "company": company,
        "track": track,
        "window_start": window_start,
        "window_end": window_end,
        "coverage_end": coverage_day,
        "material_events": 0,
    }
    return {
        "source_locator": f"research-db://events#company={company}&track={track}",
        "evidence_kind": EVIDENCE_KIND,
        "evidence_sha256": sha256_hex(canonical_json(payload)),
    }


def verify_registered_forecasts(
    registry: ForecastRegistry,
    store: Any,
    coverage_end: Any,
    as_of: Any = None,
) -> dict[str, Any]:
    """Resolve matured, still-unresolved registered nowcasts from real events.

    A registered ``record_kind='nowcast'`` is verified only when its full
    target window matured **inside the observed coverage**
    (``window_end <= min(as_of, coverage_end)``); otherwise it stays
    ``pending``. Outcome 1 requires a material 510(k)/PMA event in
    ``(window_start, window_end]`` (first event date is the ``event_time``);
    outcome 0 is recorded only for a matured window with no such event.
    Resolution errors are counted, never raised past the caller's control.
    """
    coverage_text, _ = normalize_moment(coverage_end, "coverage_end")
    coverage_day = coverage_text[:10]
    if as_of is None:
        as_of_text = registry._read_now()  # store clock: real clock in production
    else:
        as_of_text, _ = normalize_moment(as_of, "as_of")
    matured_cutoff = min(coverage_text, as_of_text)

    resolved = {row[0] for row in registry.conn.execute("SELECT DISTINCT prediction_id FROM resolutions")}
    rows = registry.conn.execute(
        "SELECT * FROM forecasts WHERE record_kind = 'nowcast' ORDER BY prediction_id"
    ).fetchall()
    verified = positives = pending = 0
    errors: list[dict[str, str]] = []
    for row in rows:
        prediction_id = row["prediction_id"]
        if prediction_id in resolved:
            continue
        if row["window_end"] > matured_cutoff:
            pending += 1
            continue
        attrs = json.loads(row["target_attrs"])
        company = str(attrs.get("company") or "")
        track = str(attrs.get("track") or "")
        kinds = tuple(attrs.get("event_kinds") or EVENT_KINDS)
        material_pma_only = bool(attrs.get("material_pma_only", True))
        try:
            material = _material_events(
                store, company=company, track=track,
                window_start=row["window_start"], window_end=row["window_end"],
                coverage_day=coverage_day, kinds=kinds, material_pma_only=material_pma_only,
            )
            event = material[0] if material else None
            outcome = 1 if event is not None else 0
            registry.resolve({
                "prediction_id": prediction_id,
                "outcome": outcome,
                "event_time": event["event_date"] if event is not None else None,
                "evidence": _resolution_evidence(
                    company, track, row["window_start"], row["window_end"], coverage_day, event),
            })
        except ForecastRegistryError as exc:
            errors.append({"prediction_id": prediction_id, "error": str(exc)})
            continue
        verified += 1
        positives += outcome
    return {
        "checked": len(rows),
        "verified": verified,
        "positives": positives,
        "pending": pending,
        "errors": len(errors),
        "error_details": errors,
    }
