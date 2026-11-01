"""Immutable Forecast Registry + deterministic binary-outcome evaluation.

A forecast, once registered, can never be changed: every row is stamped with a
**server-assigned** ``generated_at`` (strict UTC, monotonic store clock), the
target window must be genuinely in the future at registration, and SQL triggers
physically reject ``UPDATE``/``DELETE`` (including ``INSERT OR REPLACE``) on
both ledgers. Retries are safe through an explicit ``idempotency_key``: an
exact retry returns the original record without consuming the write clock, a
conflicting reuse of the key fails loudly.

Outcome resolution is a **separate append-only ledger** keyed by
``prediction_id``: outcomes are 0/1 only, corrections are new versions that
preserve the original, and evaluation at an ``as_of`` cutoff only sees
forecasts/resolutions known by that time. Scoring (Brier, clipped log loss,
fixed-boundary calibration bins / ECE) is a pure deterministic function of the
as-of-visible ledger, and the export artifact carries a canonical SHA256 that
later writes cannot alter. ``retrospective_fixture`` records (prior backtests)
are stored but never mixed into prospective headline metrics or denominators;
they are reported only in an explicitly labeled separate cohort.

Scope: this is a *registry and evaluation foundation*. It contains no model,
generates no predictions, and makes no accuracy claims. All hashes are
**declared provenance** unless an optional local TKG snapshot file is verified
against the existing ``medradar.tkg`` APIs - a 64-hex string is never treated
as proof of anything by itself, and nothing here is tamper-proof against the
database owner. Single-writer per store file; demos are in-memory synthetic
records only.
"""

from __future__ import annotations

import argparse
import calendar
import hashlib
import json
import math
import re
import sqlite3
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping

import medradar

SCHEMA_VERSION = "forecast-registry-1"
SCORING_VERSION = "scoring-1"

FORMAT = "medradar-forecast-evaluation"
FORMAT_VERSION = 1

HORIZON_MONTHS = (3, 6, 12, 24)
EVIDENCE_KINDS = ("source_observed", "inferred", "reconstructed")
RECORD_KINDS = ("forecast", "retrospective_fixture")
RESOLUTION_KINDS = ("outcome", "censor")

# Documented scoring constants (see docs/FORECAST_REGISTRY.md):
LOG_LOSS_EPSILON = 1e-15  # p is clipped into [eps, 1-eps] before the log loss
CALIBRATION_BIN_COUNT = 10  # equal-width bins; boundaries i/10, last bin closed
CALIBRATION_BOUNDARIES = [round(i / CALIBRATION_BIN_COUNT, 10) for i in range(CALIBRATION_BIN_COUNT + 1)]

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_DATE_ONLY = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class ForecastRegistryError(Exception):
    """Base error for the forecast registry."""


class ForecastValidationError(ForecastRegistryError):
    """A forecast/resolution/evaluation input failed validation."""


class IdempotencyConflict(ForecastRegistryError):
    """An idempotency key was reused with different content."""


class ClockRegressionError(ForecastRegistryError):
    """The store clock moved backwards; writes would reorder history."""


SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT
);

-- Monotonicity anchor: the highest store timestamp ever assigned.
CREATE TABLE IF NOT EXISTS clock_guard (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    last_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS forecasts (
    prediction_id     TEXT PRIMARY KEY,
    generated_at      TEXT NOT NULL,
    record_kind       TEXT NOT NULL DEFAULT 'forecast'
                      CHECK (record_kind IN ('forecast', 'retrospective_fixture')),
    information_cutoff TEXT NOT NULL,
    information_cutoff_precision TEXT NOT NULL DEFAULT 'datetime',
    target_type       TEXT NOT NULL,
    target_id         TEXT NOT NULL,
    target_attrs      TEXT NOT NULL,
    horizon_months    INTEGER NOT NULL CHECK (horizon_months IN (3, 6, 12, 24)),
    window_start      TEXT NOT NULL,
    window_end        TEXT NOT NULL,
    model_version     TEXT NOT NULL,
    feature_version   TEXT NOT NULL,
    snapshot_sha256   TEXT NOT NULL,
    snapshot_verification TEXT NOT NULL DEFAULT 'declared',
    provenance        TEXT NOT NULL,
    source_locator    TEXT NOT NULL,
    evidence_sha256   TEXT NOT NULL,
    evidence_kind     TEXT NOT NULL,
    p                 REAL NOT NULL CHECK (p >= 0.0 AND p <= 1.0),
    idempotency_key   TEXT NOT NULL UNIQUE,
    CHECK (information_cutoff <= generated_at),
    CHECK (window_start >= generated_at),
    CHECK (window_end > window_start)
);
CREATE INDEX IF NOT EXISTS idx_forecasts_generated ON forecasts(generated_at);

CREATE TABLE IF NOT EXISTS resolutions (
    prediction_id       TEXT NOT NULL,
    resolution_version  INTEGER NOT NULL,
    kind                TEXT NOT NULL CHECK (kind IN ('outcome', 'censor')),
    outcome             INTEGER CHECK (outcome IS NULL OR outcome IN (0, 1)),
    event_time          TEXT,
    event_time_precision TEXT,
    resolved_at         TEXT NOT NULL,
    seq                 INTEGER NOT NULL,
    source_locator      TEXT NOT NULL,
    evidence_sha256     TEXT NOT NULL,
    evidence_kind       TEXT NOT NULL,
    reason              TEXT,
    PRIMARY KEY (prediction_id, resolution_version),
    FOREIGN KEY (prediction_id) REFERENCES forecasts(prediction_id),
    CHECK ((kind = 'outcome' AND outcome IS NOT NULL AND (outcome = 0 OR event_time IS NOT NULL))
           OR (kind = 'censor' AND outcome IS NULL)),
    CHECK (kind = 'outcome' OR event_time IS NULL)
);
CREATE INDEX IF NOT EXISTS idx_resolutions_resolved ON resolutions(resolved_at);

CREATE TABLE IF NOT EXISTS forecast_idempotency (
    idempotency_key TEXT PRIMARY KEY,
    prediction_id   TEXT NOT NULL
);

-- ------------------------------------------------------------- append-only
-- The API never exposes UPDATE/DELETE; these triggers make the invariant
-- physical: even a stray raw SQL session cannot alter registered history.
-- INSERT OR REPLACE is rejected too: SQLite resolves REPLACE conflicts at
-- the btree layer without firing DELETE triggers, so a dedicated BEFORE
-- INSERT existence guard is required on top of the no-update/no-delete pair.
CREATE TRIGGER IF NOT EXISTS forecasts_no_update BEFORE UPDATE ON forecasts
BEGIN SELECT RAISE(ABORT, 'forecast history is append-only: UPDATE rejected'); END;
CREATE TRIGGER IF NOT EXISTS forecasts_no_delete BEFORE DELETE ON forecasts
BEGIN SELECT RAISE(ABORT, 'forecast history is append-only: DELETE rejected'); END;
CREATE TRIGGER IF NOT EXISTS forecasts_no_replace BEFORE INSERT ON forecasts
WHEN EXISTS (SELECT 1 FROM forecasts WHERE prediction_id = NEW.prediction_id)
BEGIN SELECT RAISE(ABORT, 'forecast already registered: INSERT OR REPLACE rejected'); END;
CREATE TRIGGER IF NOT EXISTS resolutions_no_update BEFORE UPDATE ON resolutions
BEGIN SELECT RAISE(ABORT, 'resolution history is append-only: UPDATE rejected'); END;
CREATE TRIGGER IF NOT EXISTS resolutions_no_delete BEFORE DELETE ON resolutions
BEGIN SELECT RAISE(ABORT, 'resolution history is append-only: DELETE rejected'); END;
CREATE TRIGGER IF NOT EXISTS resolutions_no_replace BEFORE INSERT ON resolutions
WHEN EXISTS (SELECT 1 FROM resolutions WHERE prediction_id = NEW.prediction_id
             AND resolution_version = NEW.resolution_version)
BEGIN SELECT RAISE(ABORT, 'resolution version already recorded: INSERT OR REPLACE rejected'); END;
"""


# --------------------------------------------------------------------- helpers
def code_version() -> str:
    return f"medradar-{medradar.__version__}"


def canonical_json(obj: Any) -> str:
    """Deterministic serialization: sorted keys, compact separators, no NaN."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def sha256_hex(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def normalize_moment(value: Any, field: str) -> tuple[str, str]:
    """Normalize a time input to strict UTC ISO-8601 with fixed microseconds.

    Returns ``(iso_string, precision)`` where precision is ``"date"`` for
    date-only input (explicitly widened to ``T00:00:00.000000Z``) and
    ``"datetime"`` otherwise. Naive datetimes are rejected outright - the
    caller must state a timezone; we never guess one. Offsets and fractional
    seconds are normalized so lexicographic order equals chronological order.
    """
    if isinstance(value, datetime):
        moment, precision = value, "datetime"
        if moment.tzinfo is None or moment.utcoffset() is None:
            raise ForecastValidationError(f"{field}: naive datetime without timezone is rejected")
    elif isinstance(value, date):
        return value.isoformat() + "T00:00:00.000000Z", "date"
    elif isinstance(value, str):
        text = value.strip()
        if not text:
            raise ForecastValidationError(f"{field}: empty timestamp")
        if _DATE_ONLY.match(text):
            return text + "T00:00:00.000000Z", "date"
        try:
            moment = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ForecastValidationError(f"{field}: unparseable timestamp {value!r}") from exc
        precision = "datetime"
        if moment.tzinfo is None or moment.utcoffset() is None:
            raise ForecastValidationError(f"{field}: naive timestamp without timezone is rejected")
    else:
        raise ForecastValidationError(f"{field}: unsupported timestamp type {type(value).__name__}")
    utc = moment.astimezone(timezone.utc)
    return f"{utc:%Y-%m-%dT%H:%M:%S}.{utc.microsecond:06d}Z", precision


def _render_moment(utc: datetime) -> str:
    return f"{utc:%Y-%m-%dT%H:%M:%S}.{utc.microsecond:06d}Z"


def add_months_clamped(moment: datetime, months: int) -> datetime:
    """Add calendar months, clamping the day to the target month's last day.

    ``2024-01-31`` + 3 months -> ``2024-04-30`` (April has 30 days);
    ``2024-02-29`` + 12 months -> ``2025-02-28`` (2025 is not a leap year).
    This is the documented month-end clamping rule for horizon windows.
    """
    if months <= 0:
        raise ForecastValidationError(f"months must be positive, got {months}")
    total = moment.year * 12 + (moment.month - 1) + months
    year, month0 = divmod(total, 12)
    month = month0 + 1
    day = min(moment.day, calendar.monthrange(year, month)[1])
    return moment.replace(year=year, month=month, day=day)


def _validate_probability(value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ForecastValidationError(f"p must be a finite number in [0,1], got {value!r}")
    p = float(value)
    if not math.isfinite(p) or p < 0.0 or p > 1.0:
        raise ForecastValidationError(f"p must be finite and within [0,1], got {value!r}")
    return p


def _validate_sha256(value: Any, field: str) -> str:
    text = str(value or "").strip().lower()
    if not _SHA256_RE.match(text):
        raise ForecastValidationError(
            f"{field} must be a lowercase 64-hex SHA256 string (declared provenance), got {value!r}"
        )
    return text


def _validate_evidence(evidence: Any) -> tuple[str, str, str]:
    if not isinstance(evidence, Mapping):
        raise ForecastValidationError("evidence must be an object with source_locator/evidence_sha256/evidence_kind")
    locator = str(evidence.get("source_locator") or "").strip()
    if not locator:
        raise ForecastValidationError("evidence.source_locator is required (got empty)")
    kind = str(evidence.get("evidence_kind") or "").strip()
    if kind not in EVIDENCE_KINDS:
        raise ForecastValidationError(f"evidence.evidence_kind must be one of {EVIDENCE_KINDS}, got {kind!r}")
    digest = _validate_sha256(evidence.get("evidence_sha256"), "evidence.evidence_sha256")
    return locator, digest, kind


def _validate_provenance(provenance: Any) -> list[dict[str, str]]:
    """Selected provenance/evidence locators: a non-empty list of locator+hash pairs."""
    if not isinstance(provenance, list) or not provenance:
        raise ForecastValidationError("evidence.provenance must be a non-empty list of {source_locator, evidence_sha256}")
    cleaned: list[dict[str, str]] = []
    for index, item in enumerate(provenance):
        if not isinstance(item, Mapping):
            raise ForecastValidationError(f"evidence.provenance[{index}] must be an object")
        locator = str(item.get("source_locator") or "").strip()
        if not locator:
            raise ForecastValidationError(f"evidence.provenance[{index}]: source_locator is required")
        digest = _validate_sha256(item.get("evidence_sha256"), f"evidence.provenance[{index}].evidence_sha256")
        cleaned.append({"source_locator": locator, "evidence_sha256": digest})
    cleaned.sort(key=lambda row: (row["source_locator"], row["evidence_sha256"]))
    return cleaned


def _validate_target(target: Any) -> tuple[str, str, str]:
    if not isinstance(target, Mapping):
        raise ForecastValidationError("target must be an object with type/id (explicit target identity)")
    target_type = str(target.get("type") or "").strip()
    target_id = str(target.get("id") or "").strip()
    if not target_type or not target_id:
        raise ForecastValidationError("target.type and target.id are required (explicit target identity)")
    attrs = target.get("attrs") or {}
    if not isinstance(attrs, Mapping):
        raise ForecastValidationError("target.attrs must be a JSON object")
    try:
        attrs_text = canonical_json(dict(attrs))
    except ValueError as exc:
        raise ForecastValidationError(f"target.attrs are not canonically serializable: {exc}") from exc
    return target_type, target_id, attrs_text


def _verify_snapshot(snapshot: Any) -> tuple[str, str | None]:
    """Classify snapshot provenance honestly.

    ``sha256`` alone is *declared* provenance - we never claim cryptographic
    validation from hash length. If the caller also supplies ``path`` to a
    local TKG ``snapshot.json``, the hash is recomputed with the existing
    ``medradar.tkg`` APIs and a mismatch is a hard validation error.
    """
    if not isinstance(snapshot, Mapping):
        raise ForecastValidationError("snapshot must be an object with sha256 (and optional path)")
    digest = _validate_sha256(snapshot.get("sha256"), "snapshot.sha256")
    path = snapshot.get("path")
    if not path:
        return "declared", None
    target = Path(str(path))
    if not target.is_file():
        raise ForecastValidationError(f"snapshot.path does not exist: {target}")
    try:
        from medradar.tkg.store import canonical_json as tkg_canonical
        from medradar.tkg.store import sha256_hex as tkg_sha256

        document = json.loads(target.read_text(encoding="utf-8"))
        manifest = document.get("manifest")
        if not isinstance(manifest, Mapping) or "snapshot_sha256" not in manifest:
            raise ForecastValidationError(f"snapshot.path is not a medradar-tkg snapshot.json: {target}")
        manifest = dict(manifest)
        manifest.pop("snapshot_sha256", None)
        document = {**document, "manifest": manifest}
        recomputed = tkg_sha256(tkg_canonical(document))
    except json.JSONDecodeError as exc:
        raise ForecastValidationError(f"snapshot.path is not valid JSON: {target}") from exc
    if recomputed != digest:
        raise ForecastValidationError(
            f"snapshot.sha256 does not match the content of {target} (declared {digest[:12]}..., recomputed {recomputed[:12]}...)"
        )
    return "verified_local", str(target.resolve())


# ---------------------------------------------------------------------- store
class ForecastRegistry:
    """Immutable forecast store + append-only outcome ledger (SQLite).

    ``clock`` is an optional callable returning a timezone-aware UTC datetime.
    It exists **only** so tests can build deterministic histories on the
    in-memory store (``":memory:"``); passing a clock for a persistent
    (file-backed) path is rejected, so production writes always use the real
    system clock. Single writer per store file (documented; not enforced).
    """

    def __init__(
        self,
        path: str | Path = ":memory:",
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.path = str(path)
        if clock is not None and self.path != ":memory:":
            raise ForecastRegistryError("injected test clock is only allowed on the in-memory store (':memory:')")
        self._clock = clock
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.path, timeout=60)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys=ON")
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    # ------------------------------------------------------------------ clock
    def _read_now(self) -> str:
        """Current store time without consuming the monotonic write clock."""
        raw = self._clock() if self._clock is not None else datetime.now(timezone.utc)
        rendered, _ = normalize_moment(raw, "clock")
        return rendered

    def _next_write_at(self) -> str:
        candidate = self._read_now()
        row = self.conn.execute("SELECT last_at FROM clock_guard WHERE id = 1").fetchone()
        last = row[0] if row else None
        if last is not None and candidate < last:
            raise ClockRegressionError(f"store clock regressed: {candidate} < {last}")
        if last != candidate:
            self.conn.execute(
                "INSERT INTO clock_guard (id, last_at) VALUES (1, ?)"
                " ON CONFLICT(id) DO UPDATE SET last_at = excluded.last_at",
                (candidate,),
            )
        return candidate

    # -------------------------------------------------------------- validation
    def _prepare_forecast(self, spec: Mapping[str, Any]) -> dict[str, Any]:
        """Validate a registration spec *before* any clock read or write."""
        if not isinstance(spec, Mapping):
            raise ForecastValidationError("forecast spec must be an object")
        key = str(spec.get("idempotency_key") or "").strip()
        if not key:
            raise ForecastValidationError("idempotency_key is required")

        record_kind = str(spec.get("record_kind") or "forecast").strip()
        if record_kind not in RECORD_KINDS:
            raise ForecastValidationError(f"record_kind must be one of {RECORD_KINDS}, got {record_kind!r}")

        p = _validate_probability(spec.get("p"))
        horizon = spec.get("horizon_months")
        if isinstance(horizon, bool) or not isinstance(horizon, int) or horizon not in HORIZON_MONTHS:
            raise ForecastValidationError(f"horizon_months must be one of {HORIZON_MONTHS}, got {horizon!r}")

        cutoff, cutoff_precision = normalize_moment(spec.get("information_cutoff"), "information_cutoff")
        target_type, target_id, target_attrs = _validate_target(spec.get("target"))
        model_version = str(spec.get("model_version") or "").strip()
        feature_version = str(spec.get("feature_version") or "").strip()
        if not model_version:
            raise ForecastValidationError("model_version is required")
        if not feature_version:
            raise ForecastValidationError("feature_version is required")

        snapshot_sha256, snapshot_path = spec.get("snapshot_sha256"), None
        snapshot_verification = "declared"
        if "snapshot" in spec and spec["snapshot"] is not None:
            snapshot_verification, snapshot_path = _verify_snapshot(spec["snapshot"])
            snapshot_sha256 = spec["snapshot"].get("sha256")
        snapshot_sha256 = _validate_sha256(snapshot_sha256, "snapshot_sha256")

        evidence = spec.get("evidence")
        locator, evidence_sha256, evidence_kind = _validate_evidence(evidence)
        provenance = _validate_provenance(evidence.get("provenance") if isinstance(evidence, Mapping) else None)
        try:
            provenance_text = canonical_json(provenance)
        except ValueError as exc:  # pragma: no cover - guarded above
            raise ForecastValidationError(f"provenance is not canonically serializable: {exc}") from exc

        content = {
            "record_kind": record_kind,
            "target": {"type": target_type, "id": target_id, "attrs": json.loads(target_attrs)},
            "horizon_months": horizon,
            "information_cutoff": cutoff,
            "window_start": (normalize_moment(spec["window_start"], "window_start")[0]
                             if spec.get("window_start") is not None else None),
            "window_end": (normalize_moment(spec["window_end"], "window_end")[0]
                           if spec.get("window_end") is not None else None),
            "model_version": model_version,
            "feature_version": feature_version,
            "snapshot_sha256": snapshot_sha256,
            "snapshot_verification": snapshot_verification,
            "evidence": {"source_locator": locator, "evidence_sha256": evidence_sha256, "evidence_kind": evidence_kind},
            "provenance": provenance,
            "p": p,
        }
        prediction_id = "sha256:" + sha256_hex(canonical_json(content))
        return {
            "key": key, "prediction_id": prediction_id, "record_kind": record_kind, "p": p,
            "horizon_months": horizon, "cutoff": cutoff, "cutoff_precision": cutoff_precision,
            "target_type": target_type, "target_id": target_id, "target_attrs": target_attrs,
            "model_version": model_version, "feature_version": feature_version,
            "snapshot_sha256": snapshot_sha256, "snapshot_verification": snapshot_verification,
            "locator": locator, "evidence_sha256": evidence_sha256, "evidence_kind": evidence_kind,
            "provenance_text": provenance_text,
        }

    def _finalize_window(
        self, prepared: dict[str, Any], spec: Mapping[str, Any], generated_at: str
    ) -> tuple[str, str]:
        """Resolve the target window *after* the store clock is known.

        The window must be genuinely future: ``window_start`` equals
        ``generated_at`` by default (never an implicit event-date fallback)
        or is explicitly ``>= generated_at``. ``window_end`` is **always**
        derived from the start plus the declared horizon
        (``add_months_clamped(window_start, horizon_months)``) so the
        ``horizon_months`` label always denotes the actual calendar duration
        of the window - an arbitrary or shortened end can never be silently
        mislabeled (e.g. a one-day window tagged ``horizon=24``). An explicit
        ``window_end`` is accepted only when it exactly equals the derived
        end; anything else is rejected.
        """
        if spec.get("window_start") is None:
            window_start = generated_at
        else:
            window_start, _ = normalize_moment(spec["window_start"], "window_start")
            if window_start < generated_at:
                raise ForecastValidationError(
                    f"window_start {window_start} must not be before generated_at {generated_at}"
                )
        start_dt = datetime.strptime(window_start, "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=timezone.utc)
        window_end = _render_moment(add_months_clamped(start_dt, prepared["horizon_months"]))
        explicit_end = spec.get("window_end")
        if explicit_end is not None:
            stated_end, _ = normalize_moment(explicit_end, "window_end")
            if stated_end != window_end:
                raise ForecastValidationError(
                    f"window_end {stated_end} does not match the horizon-derived end {window_end}"
                    f" (window_start {window_start} + {prepared['horizon_months']} calendar months);"
                    " horizon labels must denote the actual window duration"
                )
        if window_end <= window_start:
            raise ForecastValidationError(
                f"target window must be non-empty half-open [start, end) with end > start; got [{window_start}, {window_end})"
            )
        if window_end <= generated_at:
            raise ForecastValidationError(
                f"target window must be genuinely future at registration: window_end {window_end} <= generated_at {generated_at}"
            )
        return window_start, window_end

    # ----------------------------------------------------------------- writes
    def register(self, spec: Mapping[str, Any]) -> dict[str, Any]:
        """Register an immutable forecast (single transaction).

        ``generated_at`` is assigned inside the store. Idempotency: an exact
        retry (same key, same content) or identical content under a new key
        returns the original record without consuming the write clock; a
        conflicting reuse of the key raises :class:`IdempotencyConflict`.
        """
        prepared = self._prepare_forecast(spec)
        existing = self.conn.execute(
            "SELECT prediction_id FROM forecast_idempotency WHERE idempotency_key = ?", (prepared["key"],)
        ).fetchone()
        if existing is not None:
            if existing["prediction_id"] == prepared["prediction_id"]:
                return {**self.get_forecast(prepared["prediction_id"]), "status": "duplicate"}
            raise IdempotencyConflict(
                f"idempotency key {prepared['key']!r} already used for prediction {existing['prediction_id']}"
                f" (new content hashes to {prepared['prediction_id']})"
            )
        original = self.conn.execute(
            "SELECT prediction_id FROM forecasts WHERE prediction_id = ?", (prepared["prediction_id"],)
        ).fetchone()
        if original is not None:
            # Same content under a new key is the same immutable forecast.
            self.conn.execute(
                "INSERT INTO forecast_idempotency (idempotency_key, prediction_id) VALUES (?, ?)",
                (prepared["key"], prepared["prediction_id"]),
            )
            self.conn.commit()
            return {**self.get_forecast(prepared["prediction_id"]), "status": "duplicate"}

        try:
            self.conn.execute("BEGIN")
            generated_at = self._next_write_at()
            window_start, window_end = self._finalize_window(prepared, spec, generated_at)
            if prepared["cutoff"] > generated_at:
                raise ForecastValidationError(
                    f"information_cutoff {prepared['cutoff']} must not be after generated_at {generated_at}"
                )
            self.conn.execute(
                "INSERT INTO forecasts ("
                " prediction_id, generated_at, record_kind, information_cutoff, information_cutoff_precision,"
                " target_type, target_id, target_attrs, horizon_months, window_start, window_end,"
                " model_version, feature_version, snapshot_sha256, snapshot_verification, provenance,"
                " source_locator, evidence_sha256, evidence_kind, p, idempotency_key"
                ") VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    prepared["prediction_id"], generated_at, prepared["record_kind"],
                    prepared["cutoff"], prepared["cutoff_precision"],
                    prepared["target_type"], prepared["target_id"], prepared["target_attrs"],
                    prepared["horizon_months"], window_start, window_end,
                    prepared["model_version"], prepared["feature_version"],
                    prepared["snapshot_sha256"], prepared["snapshot_verification"], prepared["provenance_text"],
                    prepared["locator"], prepared["evidence_sha256"], prepared["evidence_kind"],
                    prepared["p"], prepared["key"],
                ),
            )
            self.conn.execute(
                "INSERT INTO forecast_idempotency (idempotency_key, prediction_id) VALUES (?, ?)",
                (prepared["key"], prepared["prediction_id"]),
            )
            self.conn.commit()
        except Exception:
            self.conn.rollback()
            raise
        return {**self.get_forecast(prepared["prediction_id"]), "status": "created"}

    def resolve(self, spec: Mapping[str, Any]) -> dict[str, Any]:
        """Append one outcome/censor record to the resolution ledger.

        Outcomes are 0/1 only and reference an existing ``prediction_id``.
        A positive outcome may be recorded as soon as the event is observed
        (``event_time`` required, must lie inside the target window); a
        negative outcome is only accepted after the full window has matured
        (store clock >= ``window_end``). Corrections are new
        ``resolution_version`` rows that preserve the original; ``reason``
        is mandatory for every version past the first. ``resolved_at`` is
        assigned by the store and can never be backdated (evidence metadata
        may predate the resolution). Unknown/censored targets are recorded
        with ``kind='censor'`` and stay explicitly unscored.
        """
        if not isinstance(spec, Mapping):
            raise ForecastValidationError("resolution spec must be an object")
        prediction_id = str(spec.get("prediction_id") or "").strip()
        row = self.conn.execute(
            "SELECT window_start, window_end FROM forecasts WHERE prediction_id = ?", (prediction_id,)
        ).fetchone()
        if row is None:
            raise ForecastValidationError(f"unknown prediction_id {prediction_id!r}")

        kind = spec.get("kind")
        outcome = spec.get("outcome")
        if kind is None:
            kind = "outcome" if outcome is not None else "censor"
        if kind not in RESOLUTION_KINDS:
            raise ForecastValidationError(f"kind must be one of {RESOLUTION_KINDS}, got {kind!r}")
        if kind == "censor":
            if outcome is not None:
                raise ForecastValidationError("a censor record must not carry an outcome")
            event_time, event_precision = None, None
        else:
            if outcome in (True, False):
                outcome = int(outcome)
            if outcome not in (0, 1):
                raise ForecastValidationError(f"outcome must be 0 or 1, got {outcome!r}")
            raw_event = spec.get("event_time")
            if outcome == 1:
                # Positive outcome: the actual observed event time is required
                # and must lie inside the target window (pre-forecast and
                # post-window events are rejected - no after-the-fact entries).
                if raw_event is None:
                    raise ForecastValidationError("event_time is required for a positive outcome (actual observed event time)")
                event_time, event_precision = normalize_moment(raw_event, "event_time")
                if not (row["window_start"] <= event_time < row["window_end"]):
                    raise ForecastValidationError(
                        f"event_time {event_time} is outside the target window [{row['window_start']}, {row['window_end']});"
                        " pre-forecast and post-window events are rejected"
                    )
            else:
                # Negative outcome: no event was observed inside the window.
                if raw_event is not None:
                    raise ForecastValidationError("a negative outcome must not carry an event_time")
                event_time, event_precision = None, None

        locator, evidence_sha256, evidence_kind = _validate_evidence(spec.get("evidence"))
        reason = spec.get("reason")
        reason = str(reason).strip() if reason is not None else None

        previous = self.conn.execute(
            "SELECT COUNT(*) AS n, MAX(resolution_version) AS v FROM resolutions WHERE prediction_id = ?",
            (prediction_id,),
        ).fetchone()
        version = int(previous["v"] or 0) + 1
        if version > 1 and not reason:
            raise ForecastValidationError("a correction (resolution_version > 1) requires a reason")

        try:
            self.conn.execute("BEGIN")
            resolved_at = self._next_write_at()
            if kind == "outcome" and outcome == 0 and resolved_at < row["window_end"]:
                raise ForecastValidationError(
                    f"negative resolution before the target window matured: resolved_at {resolved_at} < window_end {row['window_end']}"
                )
            if kind == "outcome" and outcome == 1 and event_time > resolved_at:
                # No advance knowledge of future events: a positive outcome may
                # only record an event that has already happened by resolution
                # time. Both stamps are fixed-microsecond UTC, so the lexical
                # comparison is chronological. Raising here rolls the whole
                # transaction back, including the clock-guard advance.
                raise ForecastValidationError(
                    f"positive resolution cannot record a future event: event_time {event_time} > resolved_at {resolved_at}"
                )
            seq_row = self.conn.execute(
                "SELECT COALESCE(MAX(seq), 0) + 1 AS n FROM resolutions WHERE prediction_id = ? AND resolved_at = ?",
                (prediction_id, resolved_at),
            ).fetchone()
            self.conn.execute(
                "INSERT INTO resolutions ("
                " prediction_id, resolution_version, kind, outcome, event_time, event_time_precision,"
                " resolved_at, seq, source_locator, evidence_sha256, evidence_kind, reason"
                ") VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    prediction_id, version, kind, outcome, event_time, event_precision,
                    resolved_at, int(seq_row[0]), locator, evidence_sha256, evidence_kind, reason,
                ),
            )
            self.conn.commit()
        except sqlite3.IntegrityError as exc:
            self.conn.rollback()
            raise ForecastValidationError(f"resolution insert failed integrity checks: {exc}") from exc
        except Exception:
            self.conn.rollback()
            raise
        return {
            "status": "created", "prediction_id": prediction_id,
            "resolution_version": version, "kind": kind, "outcome": outcome,
            "event_time": event_time, "resolved_at": resolved_at,
        }

    # ------------------------------------------------------------------- reads
    def get_forecast(self, prediction_id: str) -> dict[str, Any]:
        row = self.conn.execute(
            "SELECT * FROM forecasts WHERE prediction_id = ?", (prediction_id,)
        ).fetchone()
        if row is None:
            raise ForecastValidationError(f"unknown prediction_id {prediction_id!r}")
        return self._project_forecast(dict(row))

    @staticmethod
    def _project_forecast(row: dict[str, Any]) -> dict[str, Any]:
        row["target"] = {"type": row.pop("target_type"), "id": row.pop("target_id"),
                         "attrs": json.loads(row.pop("target_attrs"))}
        row["provenance"] = json.loads(row.pop("provenance"))
        row["evidence"] = {
            "source_locator": row.pop("source_locator"),
            "evidence_sha256": row.pop("evidence_sha256"),
            "evidence_kind": row.pop("evidence_kind"),
        }
        row["snapshot"] = {"sha256": row.pop("snapshot_sha256"),
                           "verification": row.pop("snapshot_verification")}
        row["p"] = float(row["p"])
        return row

    def raw(self, sql: str, params: Iterable = ()) -> list[dict[str, Any]]:  # noqa: D401 - test/CLI escape hatch
        return [dict(r) for r in self.conn.execute(sql, tuple(params)).fetchall()]

    def count(self, table: str) -> int:
        if table not in {"forecasts", "resolutions", "forecast_idempotency"}:
            raise ValueError(f"unknown table {table!r}")
        return int(self.conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])

    def _forecasts_as_of(self, as_of: str) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT * FROM forecasts WHERE generated_at <= ? ORDER BY prediction_id", (as_of,)
        ).fetchall()
        return [self._project_forecast(dict(r)) for r in rows]

    def _resolutions_as_of(self, as_of: str) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT * FROM resolutions WHERE resolved_at <= ?"
            " ORDER BY prediction_id, resolved_at, seq, resolution_version",
            (as_of,),
        ).fetchall()
        return [dict(r) for r in rows]

    # -------------------------------------------------------------- evaluation
    def evaluate(self, as_of: Any) -> dict[str, Any]:
        """Deterministic scoring of the binary forecasts known by ``as_of``.

        Only forecasts with ``generated_at <= as_of`` are considered, and for
        each only the latest resolution ``resolved_at <= as_of`` (a correction
        therefore cannot leak into an earlier as-of view; the original is
        preserved). Eligible cohort = latest resolution is a 0/1 outcome and,
        for negatives, the window has matured by ``as_of`` - unresolved or
        immature/censored forecasts are counted, never silently scored as
        zero. Metrics are stratified by (horizon_months, model_version); the
        headline aggregates all eligible *prospective* forecasts and carries
        explicit scope metadata so strata are never mixed silently.

        ``record_kind='retrospective_fixture'`` rows (prior backtests) are
        **never** silently mixed into the prospective headline metrics or
        denominators: they are reported only in the explicitly labeled
        ``retrospective`` block with their own counts and metrics.
        """
        as_of_text, _ = normalize_moment(as_of, "as_of")
        if as_of_text > self._read_now():
            raise ForecastValidationError(f"as_of {as_of_text} is after the current store clock")
        forecasts = self._forecasts_as_of(as_of_text)
        resolutions = self._resolutions_as_of(as_of_text)
        prospective = [f for f in forecasts if f["record_kind"] == "forecast"]
        fixtures = [f for f in forecasts if f["record_kind"] == "retrospective_fixture"]

        counts, headline, strata_block = self._evaluate_cohort(prospective, resolutions, as_of_text)
        retro_counts, retro_headline, retro_strata = self._evaluate_cohort(fixtures, resolutions, as_of_text)
        return {
            "scoring_version": SCORING_VERSION,
            "as_of": as_of_text,
            "counts": counts,
            "headline": headline,
            "strata": strata_block,
            "retrospective": {
                "label": "explicitly separated retrospective_fixture cohort (prior backtests);"
                         " never mixed into prospective headline metrics or denominators",
                "counts": retro_counts,
                "headline": retro_headline,
                "strata": retro_strata,
            },
        }

    @staticmethod
    def _evaluate_cohort(
        forecasts: list[dict[str, Any]],
        resolutions: list[dict[str, Any]],
        as_of_text: str,
    ) -> tuple[dict[str, int], dict[str, Any], dict[str, Any]]:
        """Score one record-kind cohort; returns (counts, headline, strata).

        Latest-resolution selection is per ``prediction_id``, so resolutions
        of forecasts outside this cohort are simply never looked up.
        """
        latest: dict[str, dict[str, Any]] = {}
        for resolution in resolutions:
            latest[resolution["prediction_id"]] = resolution

        eligible: list[tuple[str, float, int, str, int]] = []  # (prediction_id, p, y, model, horizon)
        unresolved = 0
        censored = 0
        for forecast in forecasts:
            resolution = latest.get(forecast["prediction_id"])
            if resolution is None:
                unresolved += 1
                continue
            if resolution["kind"] == "censor":
                censored += 1
                continue
            if resolution["outcome"] == 0 and forecast["window_end"] > as_of_text:
                unresolved += 1  # immature negative: not scored, not zero
                continue
            eligible.append(
                (forecast["prediction_id"], forecast["p"], int(resolution["outcome"]), forecast["model_version"],
                 forecast["horizon_months"])
            )

        def cohort_metrics(rows: list[tuple[str, float, int, str, int]]) -> dict[str, Any] | None:
            if not rows:
                return None
            n = len(rows)
            brier = sum((p - y) ** 2 for _, p, y, *_ in rows) / n
            log_loss = -sum(
                y * math.log(min(max(p, LOG_LOSS_EPSILON), 1.0 - LOG_LOSS_EPSILON))
                + (1 - y) * math.log(1.0 - min(max(p, LOG_LOSS_EPSILON), 1.0 - LOG_LOSS_EPSILON))
                for _, p, y, *_ in rows
            ) / n
            bins: list[dict[str, Any]] = []
            ece = 0.0
            for index in range(CALIBRATION_BIN_COUNT):
                lower = CALIBRATION_BOUNDARIES[index]
                upper = CALIBRATION_BOUNDARIES[index + 1]
                members = [row for row in rows if (lower <= row[1] < upper) or (index == CALIBRATION_BIN_COUNT - 1 and row[1] == 1.0)]
                if not members:
                    bins.append({"lower": lower, "upper": upper, "count": 0,
                                 "accuracy": None, "avg_confidence": None})
                    continue
                count = len(members)
                accuracy = sum(row[2] for row in members) / count
                avg_confidence = sum(row[1] for row in members) / count
                ece += (count / n) * abs(accuracy - avg_confidence)
                bins.append({"lower": lower, "upper": upper, "count": count,
                             "accuracy": accuracy, "avg_confidence": avg_confidence})
            for value in (brier, log_loss, ece):
                if not math.isfinite(value):
                    raise ForecastRegistryError(f"non-finite metric value {value!r}")
            return {
                "n": n,
                "brier": brier,
                "log_loss": log_loss,
                "calibration": {
                    "bin_count": CALIBRATION_BIN_COUNT,
                    "boundaries": CALIBRATION_BOUNDARIES,
                    "ece": ece,
                    "bins": bins,
                },
            }

        strata: dict[tuple[int, str], list[tuple[str, float, int, str, int]]] = {}
        for item in eligible:
            strata.setdefault((item[4], item[3]), []).append(item)
        strata_block: dict[str, Any] = {}
        for (horizon, model) in sorted(strata, key=lambda k: (k[0], k[1])):
            rows = sorted(strata[(horizon, model)], key=lambda item: item[0])
            strata_block[f"horizon={horizon}m|model={model}"] = {
                "scope": {"horizon_months": horizon, "model_version": model},
                **(cohort_metrics(rows) or {"n": 0, "brier": None, "log_loss": None, "calibration": None}),
            }

        counts = {
            "total_forecasts": len(forecasts),
            "eligible": len(eligible),
            "unresolved": unresolved,
            "censored": censored,
        }
        headline = {
            "scope": {
                "stratified_by": ["horizon_months", "model_version"],
                "mixed_targets": True,
                "note": "headline mixes all eligible targets; per-cohort scope is authoritative",
            },
            **(cohort_metrics(sorted(eligible, key=lambda item: item[0])) or {
                "n": 0, "brier": None, "log_loss": None, "calibration": None,
            }),
        }
        return counts, headline, strata_block

    # ------------------------------------------------------------------ export
    def build_artifact(self, as_of: Any) -> dict[str, Any]:
        """Deterministic evaluation artifact for ``as_of``.

        Contains the forecast and resolution versions visible at ``as_of``,
        the evaluation, the scoring version and provenance metadata, sorted
        canonical UTF-8 JSON hashed with SHA256. Prospective forecasts and
        ``retrospective_fixture`` rows are stored in separate, explicitly
        labeled lists. No wall-clock report timestamp is included: writes
        after ``as_of`` cannot change the hash.
        """
        as_of_text, _ = normalize_moment(as_of, "as_of")
        evaluation = self.evaluate(as_of_text)
        forecasts = self._forecasts_as_of(as_of_text)
        resolutions = self._resolutions_as_of(as_of_text)
        prospective = [f for f in forecasts if f["record_kind"] == "forecast"]
        fixtures = [f for f in forecasts if f["record_kind"] == "retrospective_fixture"]
        verifications = sorted({f["snapshot"]["verification"] for f in forecasts})
        document: dict[str, Any] = {
            "format": FORMAT,
            "format_version": FORMAT_VERSION,
            "manifest": {
                "as_of": as_of_text,
                "scoring_version": SCORING_VERSION,
                "schema_version": SCHEMA_VERSION,
                "code_version": code_version(),
                "counts": evaluation["counts"],
                "provenance": {
                    "snapshot_verification": verifications,
                    "note": "'declared' hashes are caller-supplied provenance, not cryptographically validated;"
                            " 'verified_local' was recomputed against a local TKG snapshot via medradar.tkg APIs",
                },
            },
            "forecasts": prospective,
            "retrospective_fixtures": fixtures,
            "resolutions": resolutions,
            "evaluation": evaluation,
        }
        document["manifest"]["artifact_sha256"] = sha256_hex(canonical_json(document))
        return document

    def close(self) -> None:
        self.conn.close()

    def __enter__(self) -> "ForecastRegistry":
        return self

    def __exit__(self, *exc_info: Any) -> None:
        self.close()


def render_json(document: dict[str, Any]) -> str:
    """Stable pretty JSON: sorted keys, two-space indent, trailing newline."""
    return json.dumps(document, sort_keys=True, indent=2, ensure_ascii=False, allow_nan=False) + "\n"


def write_artifact(document: dict[str, Any], out_dir: str | Path) -> dict[str, Path]:
    """Write the evaluation artifact to ``out_dir/evaluation.json``."""
    target = Path(out_dir)
    target.mkdir(parents=True, exist_ok=True)
    path = target / "evaluation.json"
    path.write_text(render_json(document), encoding="utf-8", newline="\n")
    return {"evaluation.json": path}


# ------------------------------------------------------------------------ CLI
# ``python -m medradar.forecast_registry ...`` - fully offline; ``demo`` uses
# in-memory synthetic records only and never masquerades as history.


def _emit(payload: object) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=1, default=str))


def _load_spec(path: str) -> dict[str, Any]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ForecastValidationError(f"spec file {path} must contain a JSON object")
    return data


def cmd_register(args: argparse.Namespace) -> int:
    with ForecastRegistry(args.db) as registry:
        result = registry.register(_load_spec(args.spec))
    _emit(result)
    return 0


def cmd_resolve(args: argparse.Namespace) -> int:
    with ForecastRegistry(args.db) as registry:
        result = registry.resolve(_load_spec(args.spec))
    _emit(result)
    return 0


def cmd_evaluate(args: argparse.Namespace) -> int:
    with ForecastRegistry(args.db) as registry:
        evaluation = registry.evaluate(args.as_of)
    _emit(evaluation)
    return 0


def cmd_export(args: argparse.Namespace) -> int:
    with ForecastRegistry(args.db) as registry:
        document = registry.build_artifact(args.as_of)
    written = write_artifact(document, args.out_dir)
    _emit(
        {
            "files": {name: str(path) for name, path in written.items()},
            "artifact_sha256": document["manifest"]["artifact_sha256"],
            "counts": document["manifest"]["counts"],
            "as_of": document["manifest"]["as_of"],
        }
    )
    return 0


def _demo_spec(key: str, target_id: str, horizon: int, p: float,
               model: str) -> dict[str, Any]:
    return {
        "idempotency_key": f"demo:{key}",
        "record_kind": "forecast",
        "target": {"type": "nmpa_acceptance", "id": target_id,
                   "attrs": {"synthetic": True}},
        "horizon_months": horizon,
        "p": p,
        "information_cutoff": "2024-01-14T00:00:00Z",
        "model_version": model,
        "feature_version": "features-demo-1",
        "snapshot": {"sha256": "0" * 64},  # declared provenance, explicitly unverified
        "evidence": {
            "source_locator": "synthetic://forecast-demo",
            "evidence_kind": "source_observed",
            "evidence_sha256": "1" * 64,
            "provenance": [{"source_locator": "synthetic://forecast-demo/source",
                            "evidence_sha256": "2" * 64}],
        },
    }


def cmd_demo(args: argparse.Namespace) -> int:
    """Offline demo on **synthetic in-memory records only**.

    Registers three forecasts at a fixed synthetic time, resolves one
    positively inside its window, censors one as unknown, leaves one
    unresolved, then evaluates and exports a deterministic artifact.
    """
    state = {"t": datetime(2024, 1, 15, tzinfo=timezone.utc)}

    def step_clock() -> datetime:
        value = state["t"]
        state["t"] = value + timedelta(days=1)
        return value

    registry = ForecastRegistry(":memory:", clock=step_clock)
    registered = [
        registry.register(_demo_spec("f1", "DEV-ALPHA", 3, 0.7, "model-demo-a")),
        registry.register(_demo_spec("f2", "DEV-BETA", 6, 0.3, "model-demo-a")),
        registry.register(_demo_spec("f3", "DEV-GAMMA", 12, 0.55, "model-demo-b")),
    ]
    evidence = {
        "source_locator": "synthetic://forecast-demo/resolution",
        "evidence_kind": "source_observed",
        "evidence_sha256": "3" * 64,
    }
    # No advance knowledge of future events: jump the synthetic clock to the
    # event day before recording the positive outcome (event_time must be <=
    # the store-assigned resolved_at).
    state["t"] = max(state["t"], datetime(2024, 3, 20, tzinfo=timezone.utc))
    resolutions = [
        registry.resolve({
            "prediction_id": registered[0]["prediction_id"], "outcome": 1,
            "event_time": "2024-03-20T00:00:00Z", "evidence": evidence,
        }),
        registry.resolve({
            "prediction_id": registered[1]["prediction_id"], "kind": "censor",
            "reason": "synthetic demo: target lost to follow-up (explicitly unscored)",
            "evidence": evidence,
        }),
    ]
    as_of = state["t"]
    evaluation = registry.evaluate(as_of)
    document = registry.build_artifact(as_of)
    registry.close()

    written: dict[str, str] = {}
    if args.out_dir:
        written = {name: str(path) for name, path in write_artifact(document, args.out_dir).items()}
    summary: dict[str, Any] = {
        "label": "SYNTHETIC DEMO - in-memory synthetic records only, not historical forecasts",
        "synthetic": True,
        "registered": [{"prediction_id": r["prediction_id"], "status": r["status"],
                        "window": [r["window_start"], r["window_end"]]} for r in registered],
        "resolutions": [{"prediction_id": r["prediction_id"], "kind": r["kind"],
                         "resolution_version": r["resolution_version"]} for r in resolutions],
        "as_of": evaluation["as_of"],
        "counts": evaluation["counts"],
        "headline": {k: v for k, v in evaluation["headline"].items() if k != "scope"},
        "artifact_sha256": document["manifest"]["artifact_sha256"],
        "files": written,
    }
    _emit(summary)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="medradar.forecast_registry",
        description="Immutable forecast registry + deterministic binary-outcome evaluation (offline).",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    demo = sub.add_parser("demo", help="offline demo on in-memory synthetic records")
    demo.add_argument("--out-dir", default=None, help="also write the evaluation artifact here")
    demo.set_defaults(func=cmd_demo)

    reg = sub.add_parser("register", help="register an immutable forecast from a JSON spec")
    reg.add_argument("--db", required=True, help="registry SQLite store")
    reg.add_argument("--spec", required=True, help="path to the forecast spec JSON")
    reg.set_defaults(func=cmd_register)

    res = sub.add_parser("resolve", help="append an outcome/censor resolution from a JSON spec")
    res.add_argument("--db", required=True)
    res.add_argument("--spec", required=True)
    res.set_defaults(func=cmd_resolve)

    ev = sub.add_parser("evaluate", help="deterministic scoring at an as-of cutoff")
    ev.add_argument("--db", required=True)
    ev.add_argument("--as-of", required=True, help="knowledge cutoff (tz-aware ISO)")
    ev.set_defaults(func=cmd_evaluate)

    exp = sub.add_parser("export", help="write the deterministic evaluation artifact")
    exp.add_argument("--db", required=True)
    exp.add_argument("--as-of", required=True)
    exp.add_argument("--out-dir", required=True)
    exp.set_defaults(func=cmd_export)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return int(args.func(args) or 0)
    except KeyboardInterrupt:
        print("interrupted")
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
