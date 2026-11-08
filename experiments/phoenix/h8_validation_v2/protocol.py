"""PHOENIX-002 frozen protocol constants and the maturity / risk-set rules.

FROZEN before any PHOENIX-002 experiment was run. See
docs/phoenix/PHOENIX_002_PROTOCOL.md for the prose version of this contract.
Any change to a value in this file requires bumping PROTOCOL_VERSION, editing the
markdown, and re-running every affected experiment.

Design stance (stated up front, per task brief):
  PHOENIX-002 was designed AFTER the PHOENIX-001 results were published. It is an
  adversarial re-validation of a known result, NOT a pre-registered study of an
  untouched question. Everything below was fixed before any v2 number was looked
  at, but the choice of what to test was informed by the v1 result.
"""
from __future__ import annotations

import math
from pathlib import Path

import pandas as pd

PROTOCOL_VERSION = "phoenix-002/v1"
FROZEN_AT = "2026-11-09"
FROZEN_BY = "PHOENIX-002 lead (research role: chief methodology auditor)"

# ------------------------------------------------------------------ data contract
REPO = Path(__file__).resolve().parents[3]
DB_PATH = REPO / "data" / "medradar.sqlite"
DB_SHA256 = "445807CAB60DF66E0F0853C973AAF0DAE6065E72B6C9807D5DD5265097002C92"

PANEL_START = "2004-01-01"
PANEL_END = "2026-10-30"          # last fetched_at day in the frozen snapshot
ORIGIN_START = pd.Period("2004Q1", freq="Q")
ORIGIN_END = pd.Period("2025Q2", freq="Q")   # last origin with a complete forward window
LABEL_GRID_END = pd.Period("2026Q2", freq="Q")  # end of the newest label window

HORIZON_Q = 4                      # forward label window, quarters
HISTORY_Q = 8                      # trailing window used by the growth label
HISTORY_LONG_Q = 16                # long-history window used by target Y3
MIN_DEVICE_HISTORY_Q = 8           # PIT eligibility: >= 8 quarters of observed device history

# Event kinds that can carry a track_id (verified on the frozen DB):
TRACK_KINDS = ("510k", "pma", "device_recall", "trial")
DEVICE_KINDS = ("510k", "pma")
ALL_KINDS = ("510k", "pma", "device_recall", "trial", "8k_catalyst", "drug_approval")

# --------------------------------------------------------------------- clocks
# Feature clock: available_at + feature_lag_days.  Label clock: event_date.
FEATURE_LAGS = (0, 90, 180, 270)
HEADLINE_FEATURE_LAG = 90
LAG_TAG = {v: f"L{v:03d}" for v in FEATURE_LAGS}

# Declared label publication delay: the forward window ends at end of quarter q+4;
# the label is not observable until that moment PLUS this delay.
LABEL_LAGS = (0, 90, 180)
HEADLINE_LABEL_LAG = 90

# ------------------------------------------------------------------ maturity rules
# A train row at origin q_train has label window quarters q_train+1 .. q_train+HORIZON_Q.
# label_observable_quarter = q_train + HORIZON_Q + ceil(label_lag_days / 91)
# A test origin q_test is decided at the END of quarter q_test, so the label must be
# observable by the end of quarter (q_test - 1). Conservative fold-level rule: use the
# FIRST test origin of the fold for every training row in that fold.
#   q_train + HORIZON_Q + ceil(L/91) <= q_test_first - 1
#   => q_train <= q_test_first - (HORIZON_Q + ceil(L/91) + 1)
QUARTER_DAYS = 91.0


def label_lag_quarters(label_lag_days: int) -> int:
    """Conservative whole-quarter rounding of the declared publication delay."""
    return int(math.ceil(float(label_lag_days) / QUARTER_DAYS))


def purge_quarters(label_lag_days: int) -> int:
    """Number of trailing quarters to remove from each fold's training window."""
    return HORIZON_Q + label_lag_quarters(label_lag_days) + 1


def train_latest_origin(test_first_origin: pd.Period, label_lag_days: int) -> pd.Period:
    return test_first_origin - purge_quarters(label_lag_days)


def label_observable_quarter(origin: pd.Period, label_lag_days: int) -> pd.Period:
    return origin + HORIZON_Q + label_lag_quarters(label_lag_days)


def decision_time_is_end_of(origin: pd.Period) -> pd.Period:
    """Predictions at origin q use data available up to the end of quarter q."""
    return origin


# --------------------------------------------------------------------- universes
# Retrospective track lists (full-sample membership; a documented limitation).
#   attr38  : 38 tracks with >= 1 device event that carries BOTH company_key and track_id
#   track38 : 38 tracks with >= 1 device event that carries track_id (company optional)
#   attr59  : all 59 tracks with >= 1 attributed event of any kind (v1 T-TRACK universe)
UNIVERSES = ("attr38", "track38", "attr59")
PRIMARY_UNIVERSE = "attr38"

# ------------------------------------------------------------------------ targets
# All labels are computed on the EVENT clock from attributed (attr*) or tracked (track*)
# device events. Y1 is the PHOENIX-001 target and stays the primary target even if other
# targets look better (task brief section 3).
TARGETS = {
    # PHOENIX-001 target, definition unchanged.
    "Y1_growth_ratio": "fwd4_total >= 3 AND fwd4_mean >= 1.5 * trail8_mean",
    # Absolute count increase: next 4 quarters exceed the trailing annualised rate.
    "Y2_abs_increase": "fwd4_total > trail8_total / 2",
    # New stage: grow 1.5x versus the maximum of the 8/12/16-quarter trailing means.
    "Y3_new_plateau": "fwd4_total >= 3 AND fwd4_mean >= 1.5 * max(trail8_mean, trail12_mean, trail16_mean)",
    # Dormant-track emergence: only defined where trail8_total == 0.
    "Y4_dormant_emergence": "trail8_total == 0 AND fwd4_total >= 3",
}
PRIMARY_TARGET = "Y1_growth_ratio"
SECONDARY_TARGETS = ("Y2_abs_increase", "Y3_new_plateau", "Y4_dormant_emergence")

# ------------------------------------------------------------------------- folds
FIRST_TEST_YEAR = 2014
LAST_TEST_YEAR = 2025
FOLD_RULES = ("v1_naive", "purged")
PRIMARY_FOLD_RULE = "purged"

# ------------------------------------------------------------------------- models
ARMS = (
    "M0_prevalence",      # training incidence
    "M1_persistence",     # B1: own device history (logit)  <- the H8 comparator
    "M2_ma_level",        # moving average / historical level (logit)
    "M3_trend",           # historical trend (logit on slope/acceleration)
    "M4_h8_growth",       # B1 + SciTrends-style growth features (logit)  <- H8
    "M5_full_regularised",  # all-source history + growth (L2 logit)
    "M6_hgb",             # lightweight non-linear reference
    "M7_mean_reversion",  # level-only channel (mean-reversion control)
)
PRIMARY_CONTRAST = ("M4_h8_growth", "M1_persistence")
TAU_AP = 0.03                 # pre-registered minimum practically meaningful dAP
TAU_AP_SECONDARY = 0.02

# --------------------------------------------------------------------- inference
SEED = 20261109
B_BOOT = 1000
B_BOOT_SECONDARY = 500
P_PLACEBO_ALPHA = 0.05
N_PLACEBO_PERM = 200
PLACEBO_SHIFT_Q = 8           # time-shifted placebo: growth features from t-8
ALERT_BUDGET_TOP = 10         # fixed per-quarter alert budget (units)

# Verdict gates (mechanical; see PHOENIX_002_PROTOCOL.md section 8)
GATE_PRIMARY = {"dap_min": TAU_AP, "ci_low_strictly_positive": True, "p_max": 0.05}
GATE_CROSS_UNIVERSE = {"dap_min": 0.02, "must_hold_in": ("attr38", "track38")}
GATE_PLACEBO = {"p_placebo_max": P_PLACEBO_ALPHA}
GATE_ACTIVE_STRATUM = {"dap_min": 0.02}
GATE_MIN_POSITIVES = 100
INCONCLUSIVE_CI_WIDTH_FACTOR = 2.0   # CI width > 2*tau => cannot resolve tau

# --------------------------------------------------------------------- provenance
def spec() -> dict:
    return {
        "protocol_version": PROTOCOL_VERSION,
        "frozen_at": FROZEN_AT,
        "db_sha256": DB_SHA256,
        "horizon_q": HORIZON_Q,
        "history_q": HISTORY_Q,
        "history_long_q": HISTORY_LONG_Q,
        "min_device_history_q": MIN_DEVICE_HISTORY_Q,
        "origin_start": str(ORIGIN_START),
        "origin_end": str(ORIGIN_END),
        "label_grid_end": str(LABEL_GRID_END),
        "feature_lags": list(FEATURE_LAGS),
        "headline_feature_lag": HEADLINE_FEATURE_LAG,
        "label_lags": list(LABEL_LAGS),
        "purge_quarters": {str(v): purge_quarters(v) for v in LABEL_LAGS},
        "universes": list(UNIVERSES),
        "primary_universe": PRIMARY_UNIVERSE,
        "targets": dict(TARGETS),
        "primary_target": PRIMARY_TARGET,
        "first_test_year": FIRST_TEST_YEAR,
        "last_test_year": LAST_TEST_YEAR,
        "fold_rules": list(FOLD_RULES),
        "primary_fold_rule": PRIMARY_FOLD_RULE,
        "arms": list(ARMS),
        "primary_contrast": list(PRIMARY_CONTRAST),
        "tau_ap": TAU_AP,
        "bootstrap": {"B": B_BOOT, "cluster": "track_id", "seed": SEED},
        "placebo": {"n_perm": N_PLACEBO_PERM, "shift_q": PLACEBO_SHIFT_Q,
                    "alpha": P_PLACEBO_ALPHA},
        "verdict_gates": {
            "primary": GATE_PRIMARY,
            "cross_universe": GATE_CROSS_UNIVERSE,
            "placebo": GATE_PLACEBO,
            "active_stratum": GATE_ACTIVE_STRATUM,
            "min_positives": GATE_MIN_POSITIVES,
            "inconclusive_ci_width_factor": INCONCLUSIVE_CI_WIDTH_FACTOR,
        },
    }


if __name__ == "__main__":
    import json

    print(json.dumps(spec(), indent=2))
