"""P0 audit: does universe inclusion depend on post-training FDA events?

The frozen rule admits a registrant with at least 8 attributable cleared 510(k)s in
2015-01-01..2026-08-31. Training ends 2024-12-31 and the holdout starts 2025-01-01,
so a firm can be admitted because of clearances that happen *after* the data the
model is trained on - and, for a 2021 row, after the prediction instant itself.

Direction of the bias is knowable without any model: for any cutoff C inside the
window, the pre-cutoff count is <= the full-window count, so the strict rule can
only *remove* firms. It cannot add any. The audit therefore measures how much of
the 48-firm sample survives when eligibility is decided only on information that
existed before the panel (2020-12-31) or before the holdout (2024-12-31), and
whether the primary statistic moves.

The frozen artifacts are untouched: this module rebuilds a UniverseBuild in memory
with a restricted "included" list and reuses the frozen panel and experiment code.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import replace
from datetime import date
from typing import Any, Mapping, Sequence

from research.science_002 import experiment, fda, panel, pipeline, universe
from research.science_002.entity import normalise_name
from research.science_002.sources import Cache

from . import common

WINDOW_START = "2015-01-01"
WINDOW_END = "2026-08-31"
CUTOFFS = {
    "full_window_2026_08_31": "2026-08-31",
    "pre_panel_2020_12_31": "2020-12-31",
    "pre_holdout_2024_12_31": "2024-12-31",
}


def _clearance_dates_for_all(build: Any) -> dict[str, list[date]]:
    """cik -> sorted decision dates, for every attributed firm (not only included)."""
    records = fda.read_records_csv(common.raw("fda_510k_records.csv"))
    root_to_cik: dict[str, str] = {}
    for firm in build.firms.values():
        for match in firm.applicants:
            root_to_cik[str(match["applicant_root"])] = firm.cik
    out: dict[str, list[date]] = defaultdict(list)
    for row in records:
        if (row.get("decision_code") or "") not in fda.CLEARED_DECISION_CODES:
            continue
        day = row.get("decision_date") or ""
        if not day:
            continue
        cik = root_to_cik.get(normalise_name(row.get("applicant") or ""))
        if cik is None:
            continue
        out[cik].append(date.fromisoformat(day))
    for cik in out:
        out[cik].sort()
    return out


def counts_at(dates: Sequence[date], cutoff: str) -> int:
    """Clearances inside the eligibility window up to the cutoff.

    The index itself keeps the whole history, exactly like the frozen
    pipeline.clearance_index, so the panel is identical for the base scenario; only
    the *count* that decides eligibility is windowed here.
    """
    return sum(1 for d in dates if WINDOW_START <= d.isoformat() <= cutoff)


def restricted_build(build: Any, dates: Mapping[str, Sequence[date]], cutoff: str,
                     min_clearances: int = universe.MIN_WINDOW_CLEARANCES) -> tuple[Any, list[dict[str, Any]]]:
    """Return a build whose included list satisfies the strict, pre-cutoff rule."""
    ledger: list[dict[str, Any]] = []
    included = []
    for firm in build.firms.values():
        n_full = firm.n_window_clearances
        n_cut = counts_at(dates.get(firm.cik, ()), cutoff)
        strict = replace(firm, n_window_clearances=n_cut)
        ok, reason = universe.eligibility(strict, build.submissions.get(firm.cik),
                                          build.facts.get(firm.cik), universe.DEVICE_SIC,
                                          min_clearances=min_clearances)
        ledger.append({"key": firm.key, "ticker": firm.ticker, "cik": firm.cik,
                       "n_full_window": n_full, "n_before_cutoff": n_cut,
                       "cutoff": cutoff,
                       "included_original": firm.cik in {f.cik for f in build.included},
                       "included_strict": ok, "reason": reason})
        if ok:
            included.append(strict)
    return replace(build, included=included), ledger


def run(cache: Cache, seed: int = 20261114, n_perm: int = 2000, n_boot: int = 2000,
        verbose: bool = True) -> dict[str, Any]:
    build = pipeline.build_universe(cache, verbose=False, cache_dir=common.CACHE_RAW)
    dates = _clearance_dates_for_all(build)
    original = {f.key for f in build.included}

    out: dict[str, Any] = {
        "meta": {
            "n_attributed_firms": len(build.firms),
            "n_included_original": len(build.included),
            "original_rule": ">=8 attributable clearances in " + WINDOW_START + ".." + WINDOW_END,
            "seed": seed, "n_perm": n_perm, "n_boot": n_boot,
        },
        "scenarios": {},
    }

    for name, cutoff in CUTOFFS.items():
        strict_build, ledger = restricted_build(build, dates, cutoff)
        strictly_included = {f.key for f in strict_build.included}
        dropped_rows = [row for row in ledger
                        if row["included_original"] and not row["included_strict"]]
        index = {firm.cik: dates.get(firm.cik, []) for firm in strict_build.included}
        p = panel.build_panel(strict_build, index)
        result = experiment.run(p, seed=seed, n_perm=n_perm, n_boot=n_boot,
                                placebo_features=(name == "full_window_2026_08_31"))
        ci = result["bootstrap"]["delta_B3c_minus_B2c"]
        out["scenarios"][name] = {
            "cutoff": cutoff,
            "n_firms": len(strict_build.included),
            "n_firms_dropped_vs_original": len(original - strictly_included),
            "dropped": [{"key": r["key"], "ticker": r["ticker"],
                         "n_full_window": r["n_full_window"],
                         "n_before_cutoff": r["n_before_cutoff"]} for r in dropped_rows],
            "n_rows": len(p.rows),
            "n_complete_case": result["meta"]["n_rows_complete_case"],
            "n_holdout": result["meta"]["n_holdout"],
            "prevalence_holdout": result["meta"]["prevalence_holdout"],
            "n_firms_stratified": result["conditional"]["B2c"]["n_firms"],
            "delta": result["primary"]["delta_stratified_auc_B3c_minus_B2c"],
            "p_two_sided": result["permutation"]["p_two_sided"],
            "ci_lo": ci.get("lo"), "ci_hi": ci.get("hi"),
            "pooled_B1": result["pooled"]["B1"], "pooled_B3": result["pooled"]["B3"],
            "lofo_delta": result["lofo"]["delta_B3_minus_B2"]["mean"],
            "verdict": result["verdict"]["verdict"],
            "checks": result["verdict"]["checks"],
        }
        if verbose:
            row = out["scenarios"][name]
            print(" ", name, "firms", row["n_firms"], "delta", row["delta"],
                  "p", row["p_two_sided"], flush=True)
        if name == "pre_panel_2020_12_31":
            out["ledger_2020"] = ledger
        if name == "pre_holdout_2024_12_31":
            out["ledger_2024"] = ledger

    base = out["scenarios"]["full_window_2026_08_31"]
    strict = out["scenarios"]["pre_panel_2020_12_31"]
    out["summary"] = {
        "base_delta": base["delta"], "pre_panel_delta": strict["delta"],
        "sign_reversal": (base["delta"] is not None and strict["delta"] is not None
                          and (base["delta"] > 0) != (strict["delta"] > 0)),
        "inside_original_ci": (strict["delta"] is not None and base["ci_lo"] is not None
                               and base["ci_lo"] <= strict["delta"] <= base["ci_hi"]),
        "any_go": any(s["verdict"] == "GO" for s in out["scenarios"].values()),
    }
    return out