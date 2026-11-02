"""Offline acceptance tests for the immutable Forecast Registry + evaluation.

Covers the FORECAST-REGISTRY-006 contract: finite p in [0,1], supported
horizons only, store-assigned monotonic UTC clocks (test clock in-memory
only), future-only target windows with documented month-end clamping, strict
evidence/provenance validation, explicit idempotency (exact retry vs
conflict), physical append-only SQL guards (incl. INSERT OR REPLACE),
append-only outcome ledger with corrections preserved, no future-info leakage
into as-of evaluations, immature negatives never scored as zero, explicit
censor/unknown denominators, deterministic canonical artifacts whose hash
survives later writes, and independent known-value scoring fixtures. All data
is synthetic; no network, no production databases, no accuracy claims.
"""

from __future__ import annotations

import json
import math
import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from medradar.forecast_registry import (
    CALIBRATION_BIN_COUNT,
    LOG_LOSS_EPSILON,
    SCORING_VERSION,
    ClockRegressionError,
    ForecastRegistry,
    ForecastRegistryError,
    ForecastValidationError,
    IdempotencyConflict,
    add_months_clamped,
    canonical_json,
    normalize_moment,
    sha256_hex,
)

T0 = datetime(2024, 1, 15, tzinfo=timezone.utc)
SHA_A = "a" * 64
SHA_B = "b" * 64
SHA_C = "c" * 64


def step_clock(start: datetime = T0, step: timedelta = timedelta(days=1)):
    """Unbounded monotonic clock for tests that write an unknown number of rows."""
    state = {"t": start}

    def tick() -> datetime:
        value = state["t"]
        state["t"] = value + step
        return value

    return tick


def stamp(moment: datetime) -> str:
    return f"{moment:%Y-%m-%dT%H:%M:%S}.{moment.microsecond:06d}Z"


def forecast_spec(key: str = "k1", p: float = 0.7, horizon: int = 3, **extra) -> dict:
    spec = {
        "idempotency_key": key,
        "record_kind": "forecast",
        "target": {"type": "nmpa_acceptance", "id": f"DEV-{key}", "attrs": {"synthetic": True}},
        "horizon_months": horizon,
        "p": p,
        "information_cutoff": "2024-01-10T00:00:00Z",
        "model_version": "model-test-1",
        "feature_version": "features-test-1",
        "snapshot_sha256": SHA_A,
        "evidence": {
            "source_locator": "synthetic://forecast-test",
            "evidence_kind": "source_observed",
            "evidence_sha256": SHA_B,
            "provenance": [{"source_locator": "synthetic://forecast-test/src", "evidence_sha256": SHA_C}],
        },
    }
    spec.update(extra)
    return spec


def nowcast_spec(key: str = "n1", p: float = 0.6, horizon: int = 3, **extra) -> dict:
    """A nowcast registered at T0 (2024-01-15) with an already-open window.

    ``window_start`` is before ``generated_at`` and the horizon-derived
    ``window_end`` is after it, i.e. exactly the quarterly-cutoff Horizon case.
    """
    spec = forecast_spec(key, p=p, horizon=horizon, record_kind="nowcast", **extra)
    spec["window_start"] = "2024-01-01T00:00:00Z"
    spec["information_cutoff"] = "2024-01-01T00:00:00Z"
    spec.pop("snapshot_sha256", None)  # no TKG snapshot declared for nowcasts
    return spec


def advance_past(clock, moment: datetime) -> None:
    while clock() < moment:
        pass


def resolution_spec(prediction_id: str, outcome: int | None = 1,
                    event_time: str = "2024-02-01T00:00:00Z", **extra) -> dict:
    spec = {
        "prediction_id": prediction_id,
        "outcome": outcome,
        "event_time": event_time,
        "evidence": {
            "source_locator": "synthetic://forecast-test/resolution",
            "evidence_kind": "source_observed",
            "evidence_sha256": SHA_C,
        },
    }
    spec.update(extra)
    return spec


# ------------------------------------------------------------------ validation
class RegisterValidationTests(unittest.TestCase):
    def test_p_must_be_finite_number_in_unit_interval(self) -> None:
        registry = ForecastRegistry(":memory:", clock=step_clock())
        for bad in (float("nan"), float("inf"), float("-inf"), -0.01, 1.01, True, "0.5", None):
            with self.assertRaises(ForecastValidationError, msg=f"p={bad!r}"):
                registry.register(forecast_spec(f"bad-{bad!r}", p=bad))
        # boundary values are legal
        for edge in (0.0, 1.0):
            result = registry.register(forecast_spec(f"edge-{edge}", p=edge))
            self.assertEqual(result["status"], "created")
        self.assertEqual(registry.count("forecasts"), 2)

    def test_horizon_must_be_supported(self) -> None:
        registry = ForecastRegistry(":memory:", clock=step_clock())
        for bad in (1, 2, 4, 5, 13, 36, -3, 0, "6", None, True):
            with self.assertRaises(ForecastValidationError, msg=f"horizon={bad!r}"):
                registry.register(forecast_spec(f"bad-h-{bad!r}", horizon=bad))
        for good in (3, 6, 12, 24):
            result = registry.register(forecast_spec(f"good-h-{good}", horizon=good))
            self.assertEqual(result["status"], "created")

    def test_information_cutoff_must_not_exceed_generated_at(self) -> None:
        registry = ForecastRegistry(":memory:", clock=step_clock())
        with self.assertRaises(ForecastValidationError):
            registry.register(forecast_spec("future-cutoff", information_cutoff="2030-01-01T00:00:00Z"))
        with self.assertRaises(ForecastValidationError):
            registry.register(forecast_spec("future-cutoff-dt", information_cutoff=T0 + timedelta(days=370)))
        # equality and earlier cutoffs are fine
        registry.register(forecast_spec("eq-cutoff", information_cutoff=T0))
        registry.register(forecast_spec("past-cutoff", information_cutoff="2020-01-01"))
        self.assertEqual(registry.count("forecasts"), 2)

    def test_fractional_seconds_parse_on_python_310(self) -> None:
        # py3.10's fromisoformat accepts only 3 or 6 fractional digits, so the
        # registry must normalise 1-9 digit fractions itself (F1).
        for fraction in ("5", "50", "5000", "50000", "500000"):
            self.assertEqual(
                normalize_moment(f"2024-01-10T00:00:00.{fraction}Z", "t")[0],
                "2024-01-10T00:00:00.500000Z",
                msg=fraction,
            )
        # sub-microsecond digits are truncated, not rounded
        self.assertEqual(normalize_moment("2024-01-10T00:00:00.5000009Z", "t")[0],
                         "2024-01-10T00:00:00.500000Z")
        self.assertEqual(normalize_moment("2024-01-10T08:00:00.2+08:00", "t")[0],
                         "2024-01-10T00:00:00.200000Z")
        # end-to-end: a 1-digit fractional cutoff is accepted and canonicalised
        registry = ForecastRegistry(":memory:", clock=step_clock())
        result = registry.register(forecast_spec("frac", information_cutoff="2024-01-10T00:00:00.5Z"))
        self.assertEqual(result["information_cutoff"], "2024-01-10T00:00:00.500000Z")

    def test_evidence_and_provenance_are_required_and_shaped(self) -> None:
        registry = ForecastRegistry(":memory:", clock=step_clock())
        cases = [
            {"evidence": None},
            {"evidence": {}},
            {"evidence": {"source_locator": "", "evidence_kind": "source_observed", "evidence_sha256": SHA_B}},
            {"evidence": {"source_locator": "x", "evidence_kind": "opinion", "evidence_sha256": SHA_B}},
            {"evidence": {"source_locator": "x", "evidence_kind": "source_observed", "evidence_sha256": "zzz"}},
            {"evidence": {"source_locator": "x", "evidence_kind": "source_observed", "evidence_sha256": SHA_B,
                          "provenance": []}},
            {"evidence": {"source_locator": "x", "evidence_kind": "source_observed", "evidence_sha256": SHA_B,
                          "provenance": [{"source_locator": "", "evidence_sha256": SHA_B}]}},
            {"evidence": {"source_locator": "x", "evidence_kind": "source_observed", "evidence_sha256": SHA_B,
                          "provenance": "not-a-list"}},
        ]
        for index, extra in enumerate(cases):
            with self.assertRaises(ForecastValidationError, msg=f"case {index}"):
                registry.register(forecast_spec(f"ev-{index}", **extra))
        # snapshot hash must look like SHA256 too (declared provenance still needs shape)
        with self.assertRaises(ForecastValidationError):
            registry.register(forecast_spec("ev-snap", snapshot_sha256="not-a-hash"))
        self.assertEqual(registry.count("forecasts"), 0)

    def test_target_identity_and_model_versions_are_required(self) -> None:
        registry = ForecastRegistry(":memory:", clock=step_clock())
        for index, extra in enumerate((
            {"target": {"type": "", "id": "X"}},
            {"target": {"id": "X"}},
            {"target": None},
            {"model_version": ""},
            {"feature_version": ""},
        )):
            with self.assertRaises(ForecastValidationError, msg=f"case {index}"):
                registry.register(forecast_spec(f"req-{index}", **extra))

    def test_naive_timestamps_rejected_offsets_normalized(self) -> None:
        registry = ForecastRegistry(":memory:", clock=step_clock())
        with self.assertRaises(ForecastValidationError):
            registry.register(forecast_spec("naive", information_cutoff="2024-01-10T10:00:00"))
        result = registry.register(
            forecast_spec("offset", information_cutoff="2024-01-10T20:00:00+08:00")
        )
        self.assertEqual(result["information_cutoff"], "2024-01-10T12:00:00.000000Z")
        # date-only input is widened explicitly, precision recorded
        dated = registry.register(forecast_spec("date-only", information_cutoff="2024-01-10"))
        self.assertEqual(dated["information_cutoff"], "2024-01-10T00:00:00.000000Z")
        self.assertEqual(dated["information_cutoff_precision"], "date")

    def test_non_finite_target_attrs_rejected(self) -> None:
        registry = ForecastRegistry(":memory:", clock=step_clock())
        with self.assertRaises(ForecastValidationError):
            registry.register(forecast_spec("nan-attrs", target={"type": "t", "id": "x", "attrs": {"v": float("nan")}}))


# ------------------------------------------------------------------ windows
class WindowTests(unittest.TestCase):
    def test_month_end_clamping(self) -> None:
        base = datetime(2024, 1, 31, tzinfo=timezone.utc)
        self.assertEqual(add_months_clamped(base, 3), datetime(2024, 4, 30, tzinfo=timezone.utc))
        self.assertEqual(add_months_clamped(base, 1), datetime(2024, 2, 29, tzinfo=timezone.utc))  # leap
        self.assertEqual(add_months_clamped(base, 12), datetime(2025, 1, 31, tzinfo=timezone.utc))
        leap_day = datetime(2024, 2, 29, tzinfo=timezone.utc)
        self.assertEqual(add_months_clamped(leap_day, 12), datetime(2025, 2, 28, tzinfo=timezone.utc))  # clamped

    def test_default_window_is_generated_at_plus_horizon(self) -> None:
        registry = ForecastRegistry(":memory:", clock=step_clock())
        result = registry.register(forecast_spec("w-default", horizon=3))
        # Jan 15 + 3 months -> Apr 15
        self.assertEqual(result["window_start"], "2024-01-15T00:00:00.000000Z")
        self.assertEqual(result["window_end"], "2024-04-15T00:00:00.000000Z")

    def test_window_must_be_genuinely_future(self) -> None:
        registry = ForecastRegistry(":memory:", clock=step_clock())
        with self.assertRaises(ForecastValidationError):
            registry.register(forecast_spec("w-past-end", window_end="2023-01-01T00:00:00Z"))
        with self.assertRaises(ForecastValidationError):
            registry.register(forecast_spec("w-past-start", window_start="2023-01-01T00:00:00Z"))
        with self.assertRaises(ForecastValidationError):
            registry.register(forecast_spec("w-empty", window_start="2025-01-01T00:00:00Z",
                                            window_end="2025-01-01T00:00:00Z"))
        # explicit start == generated_at is allowed (fresh store: first tick is T0)
        fresh = ForecastRegistry(":memory:", clock=step_clock())
        ok_start = fresh.register(forecast_spec("w-ok-start", window_start=T0))
        self.assertEqual(ok_start["window_start"], stamp(T0))
        # explicit future window too - end must match the horizon-derived end
        registry.register(forecast_spec("w-ok-explicit", window_start="2024-02-01T00:00:00Z",
                                        window_end="2024-05-01T00:00:00Z"))
        self.assertEqual(registry.count("forecasts"), 1)

    def test_window_end_must_match_horizon_duration(self) -> None:
        # horizon labels must denote the ACTUAL window duration: any explicit
        # end differing from add_months_clamped(window_start, horizon) is
        # rejected (no mislabeled 24-month one-day windows).
        registry = ForecastRegistry(":memory:", clock=step_clock())
        with self.assertRaises(ForecastValidationError):  # shortened override
            registry.register(forecast_spec("w-short", horizon=24,
                                            window_end="2024-01-16T00:00:00Z"))
        with self.assertRaises(ForecastValidationError):  # lengthened override
            registry.register(forecast_spec("w-long", window_end="2025-02-01T00:00:00Z"))
        self.assertEqual(registry.count("forecasts"), 0)
        # an explicit end exactly equal to the derived end is accepted
        fresh = ForecastRegistry(":memory:", clock=step_clock())  # first tick is T0
        ok = fresh.register(forecast_spec("w-exact", window_end="2024-04-15T00:00:00Z"))
        self.assertEqual(ok["window_end"], "2024-04-15T00:00:00.000000Z")

    def test_derived_window_calendar_boundaries(self) -> None:
        # month-end clamping applies to explicit future starts too
        registry = ForecastRegistry(":memory:", clock=step_clock())
        jan31 = registry.register(forecast_spec("w-jan31", horizon=3,
                                                window_start="2024-01-31T00:00:00Z"))
        self.assertEqual(jan31["window_end"], "2024-04-30T00:00:00.000000Z")
        leap = registry.register(forecast_spec("w-leap", horizon=12,
                                               window_start="2024-02-29T00:00:00Z"))
        self.assertEqual(leap["window_end"], "2025-02-28T00:00:00.000000Z")
        # a far-future start keeps the full horizon duration (24 months = 2 years)
        far = registry.register(forecast_spec("w-far", horizon=24,
                                              window_start="2026-01-31T00:00:00Z"))
        self.assertEqual(far["window_start"], "2026-01-31T00:00:00.000000Z")
        self.assertEqual(far["window_end"], "2028-01-31T00:00:00.000000Z")
        # the window always spans exactly the declared calendar months
        self.assertEqual(add_months_clamped(datetime(2026, 1, 31, tzinfo=timezone.utc), 24),
                         datetime(2028, 1, 31, tzinfo=timezone.utc))

    def test_no_implicit_event_date_fallback(self) -> None:
        # window_start defaults to generated_at, never to anything derived
        # from the target or evidence metadata.
        registry = ForecastRegistry(":memory:", clock=step_clock())
        result = registry.register(forecast_spec(
            "w-no-fallback", target={"type": "t", "id": "x", "attrs": {"event_date": "2023-06-01"}},
        ))
        self.assertEqual(result["window_start"], result["generated_at"])

    def test_retrospective_fixture_may_hold_historical_prior_backtest_window(self) -> None:
        # F4: docs say record_kind='retrospective_fixture' is for prior
        # backtests, so a historical window must be registrable (prospective
        # forecasts stay future-only) and such rows still never enter the
        # prospective headline metrics/denominators.
        registry = ForecastRegistry(":memory:", clock=step_clock())
        fixture = registry.register(forecast_spec(
            "prior-backtest", record_kind="retrospective_fixture", horizon=3,
            information_cutoff="2020-01-01T00:00:00Z",
            window_start="2020-01-01T00:00:00Z",
        ))
        self.assertEqual(fixture["window_start"], "2020-01-01T00:00:00.000000Z")
        self.assertEqual(fixture["window_end"], "2020-04-01T00:00:00.000000Z")  # derived
        with self.assertRaises(ForecastValidationError):
            registry.register(forecast_spec(
                "prospective-past", horizon=3,
                information_cutoff="2020-01-01T00:00:00Z",
                window_start="2020-01-01T00:00:00Z",
            ))
        evaluation = registry.evaluate("2024-01-15T00:00:00Z")
        self.assertEqual(evaluation["counts"]["total_forecasts"], 0)  # headline untouched
        self.assertEqual(evaluation["retrospective"]["counts"]["total_forecasts"], 1)
        artifact = registry.build_artifact("2024-01-15T00:00:00Z")
        self.assertEqual(len(artifact["forecasts"]), 0)
        self.assertEqual(len(artifact["retrospective_fixtures"]), 1)
        self.assertEqual(artifact["retrospective_fixtures"][0]["window_start"],
                         "2020-01-01T00:00:00.000000Z")


# ------------------------------------------------------------------ idempotency
class NowcastTests(unittest.TestCase):
    """``record_kind='nowcast'``: prospective forecast with an already-open window."""

    def test_nowcast_accepts_an_already_open_window(self) -> None:
        registry = ForecastRegistry(":memory:", clock=step_clock())
        result = registry.register(nowcast_spec("nc-ok", horizon=3))
        self.assertEqual(result["status"], "created")
        self.assertEqual(result["record_kind"], "nowcast")
        self.assertEqual(result["window_start"], "2024-01-01T00:00:00.000000Z")
        self.assertEqual(result["window_end"], "2024-04-01T00:00:00.000000Z")  # derived
        self.assertEqual(result["generated_at"], stamp(T0))
        # generated_at is inside the window: that is the whole point
        self.assertLess(result["window_start"], result["generated_at"])
        self.assertLess(result["generated_at"], result["window_end"])
        self.assertEqual(result["snapshot"]["verification"], "none")  # no snapshot declared

    def test_nowcast_requires_an_explicit_window_start(self) -> None:
        registry = ForecastRegistry(":memory:", clock=step_clock())
        spec = forecast_spec("nc-no-start", record_kind="nowcast")
        spec["information_cutoff"] = "2024-01-01"
        with self.assertRaises(ForecastValidationError):
            registry.register(spec)
        self.assertEqual(registry.count("forecasts"), 0)

    def test_nowcast_window_must_already_be_open(self) -> None:
        registry = ForecastRegistry(":memory:", clock=step_clock())
        # window_start after generated_at is a pure-future forecast, not a nowcast
        spec = nowcast_spec("nc-future-start")
        spec["window_start"] = "2024-02-01T00:00:00Z"
        with self.assertRaises(ForecastValidationError):
            registry.register(spec)
        # information_cutoff after window_start is rejected too
        spec = nowcast_spec("nc-cutoff-after-start")
        spec["information_cutoff"] = "2024-01-10T00:00:00Z"
        with self.assertRaises(ForecastValidationError):
            registry.register(spec)
        self.assertEqual(registry.count("forecasts"), 0)

    def test_nowcast_window_must_not_already_be_closed(self) -> None:
        registry = ForecastRegistry(":memory:", clock=step_clock())
        spec = nowcast_spec("nc-closed", horizon=3)
        spec["window_start"] = "2023-01-01T00:00:00Z"  # window_end 2023-04-01 <= T0
        with self.assertRaises(ForecastValidationError):
            registry.register(spec)
        self.assertEqual(registry.count("forecasts"), 0)

    def test_nowcast_window_end_must_match_horizon(self) -> None:
        registry = ForecastRegistry(":memory:", clock=step_clock())
        with self.assertRaises(ForecastValidationError):
            registry.register(nowcast_spec("nc-bad-end", window_end="2024-05-01T00:00:00Z"))
        self.assertEqual(registry.count("forecasts"), 0)

    def test_nowcast_cohort_is_scored_separately_from_pure_forecast(self) -> None:
        clock = step_clock(start=T0, step=timedelta(days=30))
        registry = ForecastRegistry(":memory:", clock=clock)
        pure = registry.register(forecast_spec("pure", p=0.9, horizon=3))
        now = registry.register(nowcast_spec("now", p=0.2, horizon=3))
        fixture = registry.register(forecast_spec(
            "fixture", p=0.5, horizon=3, record_kind="retrospective_fixture"))
        # resolve all three with outcome 1 (in-window event times)
        registry.resolve(resolution_spec(pure["prediction_id"], event_time=pure["window_start"]))
        registry.resolve(resolution_spec(now["prediction_id"], event_time=now["window_start"]))
        registry.resolve(resolution_spec(fixture["prediction_id"], event_time=fixture["window_start"]))
        advance_past(clock, datetime(2024, 7, 1, tzinfo=timezone.utc))
        evaluation = registry.evaluate("2024-07-01T00:00:00Z")

        # pure-future headline counts only record_kind='forecast'
        self.assertEqual(evaluation["counts"],
                         {"total_forecasts": 1, "eligible": 1, "unresolved": 0, "censored": 0})
        self.assertAlmostEqual(evaluation["headline"]["brier"], (0.9 - 1) ** 2)
        # nowcast is its own prospective cohort - no contamination
        nowcast = evaluation["nowcast"]
        self.assertIn("nowcast", nowcast["label"])
        self.assertEqual(nowcast["counts"],
                         {"total_forecasts": 1, "eligible": 1, "unresolved": 0, "censored": 0})
        self.assertAlmostEqual(nowcast["headline"]["brier"], (0.2 - 1) ** 2)
        # descriptive union is explicit, not the pure-future headline
        self.assertEqual(evaluation["prospective"]["counts"]["total_forecasts"], 2)
        self.assertIn("NOT the pure-future", evaluation["prospective"]["label"])
        self.assertEqual(evaluation["record_kind_breakdown"]["forecast"]["total_forecasts"], 1)
        self.assertEqual(evaluation["record_kind_breakdown"]["nowcast"]["total_forecasts"], 1)
        self.assertEqual(
            evaluation["record_kind_breakdown"]["retrospective_fixture"]["total_forecasts"], 1)
        # retrospective cohort is unchanged
        self.assertEqual(evaluation["retrospective"]["counts"]["total_forecasts"], 1)

        artifact = registry.build_artifact("2024-07-01T00:00:00Z")
        self.assertEqual([f["prediction_id"] for f in artifact["forecasts"]], [pure["prediction_id"]])
        self.assertEqual([f["prediction_id"] for f in artifact["nowcasts"]], [now["prediction_id"]])
        self.assertEqual([f["prediction_id"] for f in artifact["retrospective_fixtures"]],
                         [fixture["prediction_id"]])
        self.assertEqual(artifact["manifest"]["counts_by_record_kind"],
                         {"forecast": 1, "nowcast": 1, "retrospective_fixture": 1})
        # nowcast manifest identity: schema-2, and "none" present because the
        # nowcast declared no snapshot while the other two declared a hash
        self.assertEqual(artifact["manifest"]["schema_version"], "forecast-registry-2")
        self.assertIn("none", artifact["manifest"]["provenance"]["snapshot_verification"])

    def test_nowcast_is_append_only_like_forecast(self) -> None:
        registry = ForecastRegistry(":memory:", clock=step_clock())
        result = registry.register(nowcast_spec("nc-guard"))
        with self.assertRaises(sqlite3.IntegrityError):
            registry.conn.execute("UPDATE forecasts SET p = 0.99 WHERE prediction_id = ?",
                                  (result["prediction_id"],))
        with self.assertRaises(sqlite3.IntegrityError):
            registry.conn.execute("DELETE FROM forecasts WHERE prediction_id = ?",
                                  (result["prediction_id"],))
        self.assertEqual(registry.get_forecast(result["prediction_id"])["p"], 0.6)


class IdempotencyTests(unittest.TestCase):
    def test_exact_retry_returns_original_without_new_history_even_if_clock_moves(self) -> None:
        clock = step_clock()
        registry = ForecastRegistry(":memory:", clock=clock)
        first = registry.register(forecast_spec("retry"))
        clock()  # the injected clock moves on before the retry arrives
        second = registry.register(forecast_spec("retry"))
        self.assertEqual(first["status"], "created")
        self.assertEqual(second["status"], "duplicate")
        self.assertEqual(second["prediction_id"], first["prediction_id"])
        self.assertEqual(second["generated_at"], first["generated_at"])
        self.assertEqual(registry.count("forecasts"), 1)
        self.assertEqual(registry.count("forecast_idempotency"), 1)
        # the clock moved, yet the guard still holds the original stamp:
        # the duplicate retry consumed nothing
        self.assertEqual(registry.raw("SELECT last_at FROM clock_guard")[0]["last_at"], first["generated_at"])

    def test_conflicting_reuse_of_key_fails(self) -> None:
        registry = ForecastRegistry(":memory:", clock=step_clock())
        registry.register(forecast_spec("conflict", p=0.7))
        with self.assertRaises(IdempotencyConflict):
            registry.register(forecast_spec("conflict", p=0.8))
        self.assertEqual(registry.count("forecasts"), 1)

    def test_same_content_under_new_key_is_same_immutable_forecast(self) -> None:
        registry = ForecastRegistry(":memory:", clock=step_clock())
        same_target = {"type": "nmpa_acceptance", "id": "DEV-SAME", "attrs": {"synthetic": True}}
        first = registry.register(forecast_spec("key-a", p=0.7, target=same_target))
        second = registry.register(forecast_spec("key-b", p=0.7, target=same_target))
        self.assertEqual(second["status"], "duplicate")
        self.assertEqual(second["prediction_id"], first["prediction_id"])
        self.assertEqual(registry.count("forecasts"), 1)
        self.assertEqual(registry.count("forecast_idempotency"), 2)

    def test_failed_registration_consumes_nothing(self) -> None:
        registry = ForecastRegistry(":memory:", clock=step_clock())
        with self.assertRaises(ForecastValidationError):
            registry.register(forecast_spec("atomic", p=2.0))
        self.assertEqual(registry.count("forecasts"), 0)
        self.assertEqual(registry.count("forecast_idempotency"), 0)
        self.assertEqual(registry.raw("SELECT COUNT(*) AS n FROM clock_guard")[0]["n"], 0)


# ------------------------------------------------------------------ clock
class ClockTests(unittest.TestCase):
    def test_generated_at_assigned_by_store_and_monotonic(self) -> None:
        clock = step_clock()
        registry = ForecastRegistry(":memory:", clock=clock)
        first = registry.register(forecast_spec("c1"))
        second = registry.register(forecast_spec("c2"))
        self.assertEqual(first["generated_at"], stamp(T0))
        self.assertGreater(second["generated_at"], first["generated_at"])

    def test_clock_regression_rejected(self) -> None:
        times = iter([T0, T0 - timedelta(seconds=1)])
        registry = ForecastRegistry(":memory:", clock=lambda: next(times))
        registry.register(forecast_spec("r1"))
        with self.assertRaises(ClockRegressionError):
            registry.register(forecast_spec("r2"))

    def test_test_clock_rejected_on_persistent_store(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ForecastRegistryError):
                ForecastRegistry(Path(tmp) / "reg.sqlite", clock=step_clock())


# ------------------------------------------------------------------ SQL guards
class ImmutabilityGuardTests(unittest.TestCase):
    def _guarded(self, registry: ForecastRegistry, prediction_id: str) -> None:
        with self.assertRaises(sqlite3.IntegrityError):
            registry.conn.execute(
                "UPDATE forecasts SET p = 0.99 WHERE prediction_id = ?", (prediction_id,)
            )
        with self.assertRaises(sqlite3.IntegrityError):
            registry.conn.execute("DELETE FROM forecasts WHERE prediction_id = ?", (prediction_id,))
        with self.assertRaises(sqlite3.IntegrityError):
            registry.conn.execute(
                "INSERT OR REPLACE INTO forecasts (prediction_id, generated_at, information_cutoff,"
                " target_type, target_id, target_attrs, horizon_months, window_start, window_end,"
                " model_version, feature_version, snapshot_sha256, provenance, source_locator,"
                " evidence_sha256, evidence_kind, p, idempotency_key)"
                " VALUES (?, '2024-01-01T00:00:00.000000Z', '2024-01-01T00:00:00.000000Z',"
                " 't', 'id', '{}', 3, '2024-01-01T00:00:00.000000Z', '2025-01-01T00:00:00.000000Z',"
                " 'm', 'f', ?, '[]', 'loc', ?, 'source_observed', 0.5, ?)",
                (prediction_id, SHA_A, SHA_B, "other-key"),
            )
        with self.assertRaises(sqlite3.IntegrityError):
            registry.conn.execute(
                "UPDATE resolutions SET outcome = 1 - outcome WHERE prediction_id = ?", (prediction_id,)
            )
        with self.assertRaises(sqlite3.IntegrityError):
            registry.conn.execute("DELETE FROM resolutions WHERE prediction_id = ?", (prediction_id,))

    def test_update_delete_and_insert_or_replace_are_physically_rejected(self) -> None:
        clock = step_clock()
        registry = ForecastRegistry(":memory:", clock=clock)
        result = registry.register(forecast_spec("guard"))
        advance_past(clock, datetime(2024, 2, 1, tzinfo=timezone.utc))  # so the positive event is not future-dated
        registry.resolve(resolution_spec(result["prediction_id"]))
        self._guarded(registry, result["prediction_id"])
        # p is still the registered value - no silent rewrite to improve scores
        self.assertEqual(registry.get_forecast(result["prediction_id"])["p"], 0.7)
        self.assertEqual(registry.count("resolutions"), 1)

    def test_resolution_fk_rejects_unknown_prediction(self) -> None:
        registry = ForecastRegistry(":memory:", clock=step_clock())
        with self.assertRaises(ForecastValidationError):
            registry.resolve(resolution_spec("sha256:" + "0" * 64))

    def test_insert_or_replace_with_reused_idempotency_key_is_rejected(self) -> None:
        # F3: REPLACE keyed on a reused idempotency_key but a NEW prediction_id
        # does not hit the primary-key guard; SQLite would resolve the UNIQUE
        # conflict by deleting the unresolved original below the DELETE trigger
        # layer. The dedicated idempotency-key guard must abort first.
        registry = ForecastRegistry(":memory:", clock=step_clock())
        original = registry.register(forecast_spec("reuse-key", p=0.7))
        row = registry.raw("SELECT * FROM forecasts")[0]
        cols = tuple(row)
        forged = dict(row)
        forged["prediction_id"] = "sha256:" + "f" * 64
        forged["p"] = 0.99
        with self.assertRaises(sqlite3.IntegrityError):
            registry.conn.execute(
                f"INSERT OR REPLACE INTO forecasts ({','.join(cols)}) VALUES ({','.join('?' * len(cols))})",
                tuple(forged[c] for c in cols),
            )
        registry.conn.rollback()
        self.assertEqual(registry.count("forecasts"), 1)
        survivor = registry.raw("SELECT prediction_id, p, idempotency_key FROM forecasts")[0]
        self.assertEqual(survivor["prediction_id"], original["prediction_id"])
        self.assertEqual(survivor["p"], 0.7)
        self.assertEqual(survivor["idempotency_key"], "reuse-key")
        # the legitimate retry still replays as a duplicate of the real row
        self.assertEqual(registry.register(forecast_spec("reuse-key", p=0.7))["status"], "duplicate")

    def test_idempotency_ledger_cannot_be_rebound_deleted_or_replaced(self) -> None:
        registry = ForecastRegistry(":memory:", clock=step_clock())
        original = registry.register(forecast_spec("ledger-key"))
        forged = "sha256:" + "e" * 64
        for sql, params in (
            ("UPDATE forecast_idempotency SET prediction_id = ? WHERE idempotency_key = ?",
             (forged, "ledger-key")),
            ("DELETE FROM forecast_idempotency WHERE idempotency_key = ?", ("ledger-key",)),
            ("INSERT OR REPLACE INTO forecast_idempotency (idempotency_key, prediction_id) VALUES (?, ?)",
             ("ledger-key", forged)),
        ):
            with self.assertRaises(sqlite3.IntegrityError, msg=sql):
                registry.conn.execute(sql, params)
            registry.conn.rollback()
        # The key -> prediction_id mapping survived: exact retry is a duplicate
        # and conflicting content still fails loudly (it cannot ride the key).
        retry = registry.register(forecast_spec("ledger-key"))
        self.assertEqual(retry["status"], "duplicate")
        self.assertEqual(retry["prediction_id"], original["prediction_id"])
        with self.assertRaises(IdempotencyConflict):
            registry.register(forecast_spec("ledger-key", p=0.2))
        self.assertEqual(registry.count("forecast_idempotency"), 1)

    def test_existing_database_gets_new_guards_when_reopened(self) -> None:
        # CREATE TRIGGER IF NOT EXISTS runs on every open, so a database
        # created by an earlier build must gain the F3 guards automatically.
        new_triggers = (
            "forecasts_no_key_rebind",
            "forecast_idempotency_no_update",
            "forecast_idempotency_no_delete",
            "forecast_idempotency_no_resubmit",
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "registry.sqlite"
            with ForecastRegistry(path) as legacy:
                legacy.register(forecast_spec("legacy-db", information_cutoff="2020-01-01T00:00:00Z"))
                for trigger in new_triggers:  # simulate a pre-F3 database file
                    legacy.conn.execute(f"DROP TRIGGER IF EXISTS {trigger}")
                legacy.conn.commit()
                self.assertEqual(legacy.raw(
                    "SELECT name FROM sqlite_master WHERE type = 'trigger' AND name = 'forecasts_no_key_rebind'"), [])
            with ForecastRegistry(path) as reopened:
                names = {r["name"] for r in reopened.raw("SELECT name FROM sqlite_master WHERE type = 'trigger'")}
                for trigger in new_triggers:
                    self.assertIn(trigger, names)
                row = reopened.raw("SELECT * FROM forecasts")[0]
                cols = tuple(row)
                forged = dict(row)
                forged["prediction_id"] = "sha256:" + "a" * 64
                with self.assertRaises(sqlite3.IntegrityError):
                    reopened.conn.execute(
                        f"INSERT OR REPLACE INTO forecasts ({','.join(cols)}) VALUES ({','.join('?' * len(cols))})",
                        tuple(forged[c] for c in cols),
                    )
                reopened.conn.rollback()
                self.assertEqual(reopened.count("forecasts"), 1)


# ------------------------------------------------------------------ resolution
class ResolutionTests(unittest.TestCase):
    def test_positive_out_of_window_and_pre_forecast_events_rejected(self) -> None:
        registry = ForecastRegistry(":memory:", clock=step_clock())
        result = registry.register(forecast_spec("win", horizon=3))  # [Jan15, Apr15)
        pid = result["prediction_id"]
        with self.assertRaises(ForecastValidationError):  # before forecast existed
            registry.resolve(resolution_spec(pid, event_time="2024-01-10T00:00:00Z"))
        with self.assertRaises(ForecastValidationError):  # after window end
            registry.resolve(resolution_spec(pid, event_time="2024-04-15T00:00:00Z"))
        with self.assertRaises(ForecastValidationError):  # missing event time
            registry.resolve(resolution_spec(pid, event_time=None))
        ok = registry.resolve(resolution_spec(pid, event_time="2024-01-15T00:00:00Z"))
        self.assertEqual(ok["resolution_version"], 1)

    def test_premature_negative_rejected_until_window_matures(self) -> None:
        clock = step_clock(start=T0, step=timedelta(days=10))
        registry = ForecastRegistry(":memory:", clock=clock)
        result = registry.register(forecast_spec("neg", horizon=3))  # ends Apr 15
        pid = result["prediction_id"]
        with self.assertRaises(ForecastValidationError):
            registry.resolve(resolution_spec(pid, outcome=0))
        with self.assertRaises(ForecastValidationError):
            registry.resolve({**resolution_spec(pid, outcome=0), "event_time": None})
        # negative outcomes must not carry an event time
        while clock() < datetime(2024, 4, 15, tzinfo=timezone.utc):
            pass
        with self.assertRaises(ForecastValidationError):
            registry.resolve({**resolution_spec(pid, outcome=0), "event_time": "2024-02-01T00:00:00Z"})
        ok = registry.resolve({**resolution_spec(pid, outcome=0), "event_time": None})
        self.assertEqual(ok["status"], "created")

    def test_resolution_not_backdated_and_evidence_may_predate(self) -> None:
        clock = step_clock(start=T0, step=timedelta(days=30))
        registry = ForecastRegistry(":memory:", clock=clock)
        result = registry.register(forecast_spec("backdate", horizon=3))
        pid = result["prediction_id"]
        while clock() < datetime(2024, 4, 15, tzinfo=timezone.utc):
            pass
        resolved = registry.resolve(resolution_spec(pid, outcome=0, event_time=None))
        # resolved_at comes from the store clock even though the evidence locator predates it
        self.assertGreaterEqual(resolved["resolved_at"], "2024-04-15T00:00:00.000000Z")
        self.assertGreater(resolved["resolved_at"], result["generated_at"])

    def test_future_dated_positive_rejected_and_valid_resolution_still_works(self) -> None:
        # No advance knowledge of future events: a positive outcome whose
        # event_time is still in the future at resolution time must fail, the
        # failed attempt must roll back cleanly (no resolution row, no clock
        # consumption), and a later valid resolution must still work.
        clock = step_clock()
        registry = ForecastRegistry(":memory:", clock=clock)
        result = registry.register(forecast_spec("no-future", horizon=3))  # [Jan15, Apr15)
        pid = result["prediction_id"]
        with self.assertRaises(ForecastValidationError) as ctx:
            registry.resolve(resolution_spec(pid, event_time="2024-03-20T00:00:00Z"))
        self.assertIn("future event", str(ctx.exception))
        self.assertEqual(registry.count("resolutions"), 0)  # rolled back
        self.assertEqual(registry.raw("SELECT last_at FROM clock_guard")[0]["last_at"],
                         result["generated_at"])  # clock not consumed by the failed attempt
        # once the event has actually happened, the same resolution succeeds;
        # the event may predate the observation (evidence can lag the event)
        advance_past(clock, datetime(2024, 3, 20, tzinfo=timezone.utc))
        ok = registry.resolve(resolution_spec(pid, event_time="2024-03-20T00:00:00Z"))
        self.assertEqual(ok["status"], "created")
        self.assertGreaterEqual(ok["resolved_at"], ok["event_time"])
        self.assertEqual(registry.count("resolutions"), 1)

    def test_correction_preserves_original_and_requires_reason(self) -> None:
        clock = step_clock(start=T0, step=timedelta(days=30))
        registry = ForecastRegistry(":memory:", clock=clock)
        result = registry.register(forecast_spec("corr", horizon=3))
        pid = result["prediction_id"]
        advance_past(clock, datetime(2024, 4, 16, tzinfo=timezone.utc))
        v1 = registry.resolve({**resolution_spec(pid, outcome=0), "event_time": None})
        self.assertEqual(v1["resolution_version"], 1)
        with self.assertRaises(ForecastValidationError):
            registry.resolve(resolution_spec(pid, outcome=1))  # correction without reason
        v2 = registry.resolve({**resolution_spec(pid, outcome=1), "reason": "primary source confirmed the event"})
        self.assertEqual(v2["resolution_version"], 2)
        self.assertEqual(registry.count("resolutions"), 2)  # original preserved

    def test_censor_record_unscored_and_outcome_must_be_binary(self) -> None:
        registry = ForecastRegistry(":memory:", clock=step_clock())
        result = registry.register(forecast_spec("censor"))
        pid = result["prediction_id"]
        with self.assertRaises(ForecastValidationError):
            registry.resolve({**resolution_spec(pid), "outcome": 2})
        with self.assertRaises(ForecastValidationError):
            registry.resolve({"prediction_id": pid, "kind": "censor", "outcome": 1})
        ok = registry.resolve({"prediction_id": pid, "kind": "censor", "reason": "unknown: regulator record lost",
                               "evidence": {"source_locator": "synthetic://censor", "evidence_kind": "source_observed",
                                            "evidence_sha256": SHA_B}})
        self.assertEqual(ok["kind"], "censor")


# ------------------------------------------------------------------ evaluation
class EvaluationTests(unittest.TestCase):
    def _registry_with_known_values(self) -> tuple[ForecastRegistry, list[str], Any]:
        """Four eligible forecasts with hand-checkable expected metrics."""
        clock = step_clock(start=T0, step=timedelta(days=30))
        registry = ForecastRegistry(":memory:", clock=clock)
        rows = []
        specs = [
            ("kv1", 0.9, 1), ("kv2", 0.2, 0), ("kv3", 0.4, 0), ("kv4", 0.7, 1),
        ]
        for key, p, _ in specs:
            rows.append(registry.register(forecast_spec(key, p=p)))
        # move past every 3-month window before resolving negatives
        advance_past(clock, datetime(2024, 4, 16, tzinfo=timezone.utc))
        for row, (_, p, y) in zip(rows, specs):
            registry.resolve({**resolution_spec(row["prediction_id"], outcome=y),
                              "event_time": row["window_start"] if y else None})
        return registry, [r["prediction_id"] for r in rows], clock

    def test_known_value_scoring_independently_computed(self) -> None:
        registry, _, clock = self._registry_with_known_values()
        advance_past(clock, datetime(2025, 1, 1, tzinfo=timezone.utc))
        evaluation = registry.evaluate("2025-01-01T00:00:00Z")
        headline = evaluation["headline"]
        self.assertEqual(headline["n"], 4)
        # independent expectations written out, not copied from the implementation
        p = [0.9, 0.2, 0.4, 0.7]
        y = [1, 0, 0, 1]
        expected_brier = sum((pi - yi) ** 2 for pi, yi in zip(p, y)) / 4
        expected_log_loss = -sum(
            yi * math.log(max(pi, LOG_LOSS_EPSILON)) + (1 - yi) * math.log(1.0 - min(pi, 1.0 - LOG_LOSS_EPSILON))
            for pi, yi in zip(p, y)
        ) / 4
        self.assertAlmostEqual(headline["brier"], expected_brier)
        self.assertAlmostEqual(headline["brier"], 0.075)
        self.assertAlmostEqual(headline["log_loss"], expected_log_loss)
        self.assertTrue(all(math.isfinite(v) for v in (headline["brier"], headline["log_loss"])))
        # ECE: bins 9, 2, 4, 7 each hold one forecast
        expected_ece = (1 / 4) * (abs(1 - 0.9) + abs(0 - 0.2) + abs(0 - 0.4) + abs(1 - 0.7))
        self.assertAlmostEqual(headline["calibration"]["ece"], expected_ece)
        self.assertAlmostEqual(headline["calibration"]["ece"], 0.25)
        self.assertEqual(headline["calibration"]["bin_count"], CALIBRATION_BIN_COUNT)
        self.assertEqual(headline["calibration"]["boundaries"], [i / 10 for i in range(11)])
        populated = [b for b in headline["calibration"]["bins"] if b["count"]]
        self.assertEqual({b["lower"] for b in populated}, {0.2, 0.4, 0.7, 0.9})

    def test_empty_cohort_has_explicit_null_metrics(self) -> None:
        clock = step_clock()
        registry = ForecastRegistry(":memory:", clock=clock)
        clock()  # advance the injected clock to the evaluation moment
        evaluation = registry.evaluate("2024-01-16T00:00:00Z")
        self.assertEqual(evaluation["counts"]["total_forecasts"], 0)
        self.assertIsNone(evaluation["headline"]["brier"])
        self.assertIsNone(evaluation["headline"]["log_loss"])
        self.assertEqual(evaluation["headline"]["n"], 0)

    def test_unresolved_and_censored_denominators(self) -> None:
        clock = step_clock(start=T0, step=timedelta(days=30))
        registry = ForecastRegistry(":memory:", clock=clock)
        pids = [
            registry.register(forecast_spec("d1", p=0.9))["prediction_id"],
            registry.register(forecast_spec("d2", p=0.1))["prediction_id"],
            registry.register(forecast_spec("d3", p=0.5))["prediction_id"],
        ]
        registry.resolve(resolution_spec(pids[0], outcome=1))  # eligible
        registry.resolve({"prediction_id": pids[1], "kind": "censor", "reason": "unknown: record censored",
                          "evidence": {"source_locator": "synthetic://censor", "evidence_kind": "source_observed",
                                       "evidence_sha256": SHA_B}})
        # pids[2] stays unresolved
        advance_past(clock, datetime(2025, 1, 1, tzinfo=timezone.utc))
        evaluation = registry.evaluate("2025-01-01T00:00:00Z")
        self.assertEqual(evaluation["counts"], {
            "total_forecasts": 3, "eligible": 1, "unresolved": 1, "censored": 1,
        })
        self.assertEqual(evaluation["headline"]["n"], 1)

    def test_immature_negative_is_not_silently_scored_as_zero(self) -> None:
        # Simulate a corrupt early negative (bypassing the write guard) and
        # verify the evaluator still refuses to score it before maturity.
        clock = step_clock()
        registry = ForecastRegistry(":memory:", clock=clock)
        result = registry.register(forecast_spec("immature", horizon=12))  # ends 2025-01-15
        pid = result["prediction_id"]
        registry.conn.execute(
            "INSERT INTO resolutions (prediction_id, resolution_version, kind, outcome, event_time,"
            " resolved_at, seq, source_locator, evidence_sha256, evidence_kind, reason)"
            " VALUES (?, 1, 'outcome', 0, NULL, '2024-06-01T00:00:00.000000Z', 1, 'x', ?, 'source_observed', NULL)",
            (pid, SHA_B),
        )
        evaluation = registry.evaluate("2024-01-16T00:00:00Z")
        self.assertEqual(evaluation["counts"]["eligible"], 0)
        self.assertEqual(evaluation["counts"]["unresolved"], 1)
        # after the window matures the same negative becomes eligible
        advance_past(clock, datetime(2025, 2, 1, tzinfo=timezone.utc))
        evaluation = registry.evaluate("2025-02-01T00:00:00Z")
        self.assertEqual(evaluation["counts"]["eligible"], 1)
        self.assertEqual(evaluation["headline"]["n"], 1)

    def test_correction_as_of_semantics(self) -> None:
        clock = step_clock(start=T0, step=timedelta(days=30))
        registry = ForecastRegistry(":memory:", clock=clock)
        result = registry.register(forecast_spec("asof", p=0.6, horizon=3))
        pid = result["prediction_id"]
        while clock() < datetime(2024, 4, 16, tzinfo=timezone.utc):
            pass
        v1 = registry.resolve({**resolution_spec(pid, outcome=0), "event_time": None})
        mid = clock()  # strictly after v1, before the correction
        v2 = registry.resolve({**resolution_spec(pid, outcome=1), "reason": "appeal upheld"})
        before = registry.evaluate(mid)
        self.assertEqual(before["counts"]["eligible"], 1)
        self.assertAlmostEqual(before["headline"]["brier"], (0.6 - 0) ** 2)  # sees v1 only
        after = registry.evaluate(clock())
        self.assertAlmostEqual(after["headline"]["brier"], (0.6 - 1) ** 2)  # sees v2
        # both versions are preserved in the artifact
        artifact = registry.build_artifact(clock())
        versions = [r["resolution_version"] for r in artifact["resolutions"] if r["prediction_id"] == pid]
        self.assertEqual(sorted(versions), [1, 2])

    def test_forecasts_after_as_of_do_not_leak_into_evaluation(self) -> None:
        clock = step_clock(start=T0, step=timedelta(days=30))
        registry = ForecastRegistry(":memory:", clock=clock)
        early = registry.register(forecast_spec("early", p=0.5, horizon=3))
        as_of = clock()  # after registration, before the second forecast exists
        late = registry.register(forecast_spec("late", p=0.9, horizon=3))
        self.assertNotEqual(early["prediction_id"], late["prediction_id"])
        evaluation = registry.evaluate(as_of)
        self.assertEqual(evaluation["counts"]["total_forecasts"], 1)
        artifact = registry.build_artifact(as_of)
        self.assertEqual(len(artifact["forecasts"]), 1)

    def test_as_of_after_current_clock_rejected(self) -> None:
        registry = ForecastRegistry(":memory:", clock=step_clock())
        with self.assertRaises(ForecastValidationError):
            registry.evaluate("2999-01-01T00:00:00Z")

    def test_stratification_by_horizon_and_model_version(self) -> None:
        clock = step_clock(start=T0, step=timedelta(days=30))
        registry = ForecastRegistry(":memory:", clock=clock)
        pids = [
            registry.register(forecast_spec("s1", p=0.9, horizon=3))["prediction_id"],
            registry.register(forecast_spec("s2", p=0.1, horizon=6, model_version="model-other"))["prediction_id"],
        ]
        while clock() < datetime(2024, 7, 16, tzinfo=timezone.utc):
            pass
        registry.resolve(resolution_spec(pids[0], outcome=1))
        registry.resolve({**resolution_spec(pids[1], outcome=0), "event_time": None})
        advance_past(clock, datetime(2025, 1, 1, tzinfo=timezone.utc))
        evaluation = registry.evaluate("2025-01-01T00:00:00Z")
        self.assertEqual(set(evaluation["strata"]), {"horizon=3m|model=model-test-1", "horizon=6m|model=model-other"})
        self.assertAlmostEqual(
            evaluation["strata"]["horizon=3m|model=model-test-1"]["brier"], (0.9 - 1) ** 2
        )
        # headline exists but is explicitly marked as mixed-target scope
        self.assertTrue(evaluation["headline"]["scope"]["mixed_targets"])
        self.assertEqual(evaluation["headline"]["n"], 2)

    def test_retrospective_fixtures_never_contaminate_headline_metrics(self) -> None:
        # record_kind='retrospective_fixture' (prior backtests) must not enter
        # prospective headline metrics or denominators: it is reported only in
        # the explicitly labeled retrospective cohort.
        clock = step_clock(start=T0, step=timedelta(days=30))
        registry = ForecastRegistry(":memory:", clock=clock)
        fixture = registry.register(forecast_spec(
            "retro", p=0.1, horizon=24, model_version="model-backtest",
            record_kind="retrospective_fixture"))
        real = registry.register(forecast_spec("real", p=0.9, horizon=3))
        registry.resolve(resolution_spec(fixture["prediction_id"], event_time=fixture["window_start"]))
        registry.resolve(resolution_spec(real["prediction_id"], event_time=real["window_start"]))
        advance_past(clock, datetime(2025, 1, 1, tzinfo=timezone.utc))
        evaluation = registry.evaluate("2025-01-01T00:00:00Z")
        # prospective headline sees only the real forecast
        self.assertEqual(evaluation["counts"], {
            "total_forecasts": 1, "eligible": 1, "unresolved": 0, "censored": 0,
        })
        self.assertAlmostEqual(evaluation["headline"]["brier"], (0.9 - 1) ** 2)
        self.assertEqual(set(evaluation["strata"]), {"horizon=3m|model=model-test-1"})
        # the fixture lives in its own explicitly labeled cohort
        retro = evaluation["retrospective"]
        self.assertIn("retrospective_fixture", retro["label"])
        self.assertEqual(retro["counts"]["total_forecasts"], 1)
        self.assertAlmostEqual(retro["headline"]["brier"], (0.1 - 1) ** 2)
        self.assertEqual(set(retro["strata"]), {"horizon=24m|model=model-backtest"})
        # and the artifact keeps the two record kinds in separate lists
        artifact = registry.build_artifact("2025-01-01T00:00:00Z")
        self.assertEqual(len(artifact["forecasts"]), 1)
        self.assertEqual(len(artifact["retrospective_fixtures"]), 1)
        self.assertEqual(artifact["retrospective_fixtures"][0]["prediction_id"],
                         fixture["prediction_id"])

    def test_snapshot_verification_modes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            snap = Path(tmp) / "snapshot.json"
            document = {
                "format": "medradar-tkg-snapshot",
                "format_version": 1,
                "manifest": {
                    "known_at": "2024-01-01T00:00:00.000000Z",
                    "valid_at": None,
                    "schema_version": "tkg-schema-1",
                    "code_version": "medradar-test",
                    "adapter_version": None,
                    "counts": {"nodes": 0, "edges": 0},
                    "evidence_provenance": [],
                },
                "nodes": [],
                "edges": [],
            }
            digest = sha256_hex(canonical_json(document))
            document["manifest"]["snapshot_sha256"] = digest
            snap.write_text(json.dumps(document), encoding="utf-8")

            registry = ForecastRegistry(":memory:", clock=step_clock())
            ok = registry.register(forecast_spec("verified", snapshot={"sha256": digest, "path": str(snap)}))
            self.assertEqual(ok["snapshot"]["verification"], "verified_local")
            with self.assertRaises(ForecastValidationError):
                registry.register(forecast_spec("mismatch", snapshot={"sha256": SHA_A, "path": str(snap)}))
            declared = registry.register(forecast_spec("declared-only", snapshot_sha256=SHA_A))
            self.assertEqual(declared["snapshot"]["verification"], "declared")


# ------------------------------------------------------------------ artifacts
class ArtifactTests(unittest.TestCase):
    def test_artifact_hash_stable_after_later_writes(self) -> None:
        clock = step_clock(start=T0, step=timedelta(days=30))
        registry = ForecastRegistry(":memory:", clock=clock)
        first = registry.register(forecast_spec("a1", p=0.8, horizon=3))
        registry.resolve(resolution_spec(first["prediction_id"], outcome=1))
        as_of = clock()
        artifact = registry.build_artifact(as_of)
        digest = artifact["manifest"]["artifact_sha256"]

        # later forecasts and resolutions must not change the historical artifact
        later = registry.register(forecast_spec("a2", p=0.2, horizon=6))
        advance_past(clock, datetime(2024, 11, 15, tzinfo=timezone.utc))  # past a2's window end
        registry.resolve(resolution_spec(later["prediction_id"], outcome=0, event_time=None))
        repeat = registry.build_artifact(as_of)
        self.assertEqual(repeat["manifest"]["artifact_sha256"], digest)
        self.assertEqual(len(repeat["forecasts"]), 1)
        self.assertEqual(canonical_json(repeat), canonical_json(artifact))

    def test_artifact_has_no_wall_clock_and_carries_provenance(self) -> None:
        clock = step_clock()
        registry = ForecastRegistry(":memory:", clock=clock)
        registry.register(forecast_spec("prov"))
        advance_past(clock, datetime(2024, 1, 20, tzinfo=timezone.utc))
        artifact = registry.build_artifact("2024-01-20T00:00:00.000000Z")
        self.assertEqual(artifact["format"], "medradar-forecast-evaluation")
        self.assertEqual(artifact["manifest"]["scoring_version"], SCORING_VERSION)
        self.assertEqual(artifact["manifest"]["provenance"]["snapshot_verification"], ["declared"])
        self.assertNotIn("generated_at_report", artifact["manifest"])
        # hash recomputes over the canonical document without the hash field
        copy = json.loads(canonical_json(artifact))
        stored = copy["manifest"].pop("artifact_sha256")
        self.assertEqual(sha256_hex(canonical_json(copy)), stored)

    def test_export_to_disk_roundtrip(self) -> None:
        from medradar.forecast_registry import write_artifact

        clock = step_clock()
        registry = ForecastRegistry(":memory:", clock=clock)
        registry.register(forecast_spec("disk"))
        advance_past(clock, datetime(2024, 1, 20, tzinfo=timezone.utc))
        artifact = registry.build_artifact("2024-01-20T00:00:00.000000Z")
        with tempfile.TemporaryDirectory() as tmp:
            written = write_artifact(artifact, tmp)
            loaded = json.loads(written["evaluation.json"].read_text(encoding="utf-8"))
            self.assertEqual(loaded["manifest"]["artifact_sha256"], artifact["manifest"]["artifact_sha256"])


# ------------------------------------------------------------------ CLI
class CliTests(unittest.TestCase):
    def _run(self, *argv: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, "-m", "medradar.forecast_registry", *argv],
            capture_output=True, text=True, timeout=120,
        )

    def test_demo_is_synthetic_and_self_contained(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            result = self._run("demo", "--out-dir", tmp)
            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(result.stdout)
            self.assertTrue(payload["synthetic"])
            self.assertIn("SYNTHETIC", payload["label"])
            self.assertEqual(payload["counts"], {"total_forecasts": 3, "eligible": 1, "unresolved": 1, "censored": 1})
            self.assertTrue((Path(tmp) / "evaluation.json").is_file())

    def test_register_resolve_evaluate_export_via_cli(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = str(Path(tmp) / "reg.sqlite")
            spec = forecast_spec("cli1", p=0.8)
            spec["information_cutoff"] = "2020-01-01T00:00:00Z"  # any past cutoff works with the real clock
            spec_path = Path(tmp) / "forecast.json"
            spec_path.write_text(json.dumps(spec), encoding="utf-8")
            result = self._run("register", "--db", db, "--spec", str(spec_path))
            self.assertEqual(result.returncode, 0, result.stderr)
            registered = json.loads(result.stdout)
            self.assertEqual(registered["status"], "created")
            # exact retry via CLI is idempotent
            retry = self._run("register", "--db", db, "--spec", str(spec_path))
            self.assertEqual(json.loads(retry.stdout)["status"], "duplicate")

            resolve_path = Path(tmp) / "resolution.json"
            resolve_path.write_text(json.dumps({
                "prediction_id": registered["prediction_id"], "outcome": 1,
                "event_time": registered["window_start"],
                "evidence": {"source_locator": "synthetic://cli", "evidence_kind": "source_observed",
                             "evidence_sha256": SHA_B},
            }), encoding="utf-8")
            result = self._run("resolve", "--db", db, "--spec", str(resolve_path))
            self.assertEqual(result.returncode, 0, result.stderr)

            result = self._run("evaluate", "--db", db, "--as-of", "2999-01-01T00:00:00Z")
            self.assertNotEqual(result.returncode, 0)  # as-of beyond the real clock is rejected
            result = self._run("evaluate", "--db", db, "--as-of", registered["generated_at"])
            self.assertEqual(result.returncode, 0, result.stderr)
            evaluation = json.loads(result.stdout)
            self.assertEqual(evaluation["counts"]["eligible"], 0)  # resolution not yet known at that as-of

            result = self._run("export", "--db", db, "--as-of", registered["generated_at"], "--out-dir", tmp)
            self.assertEqual(result.returncode, 0, result.stderr)
            exported = json.loads(result.stdout)
            self.assertTrue((Path(tmp) / "evaluation.json").is_file())
            self.assertEqual(len(exported["artifact_sha256"]), 64)


if __name__ == "__main__":
    unittest.main()
