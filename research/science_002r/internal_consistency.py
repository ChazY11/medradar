"""P1: recompute every number SCIENCE-002 reports, from its own committed artifacts.

Nothing here re-runs the model. It reads artifacts/universe.csv, entity_matches.csv,
entity_exclusions.csv, panel.csv, panel_summary.json, universe_summary.json and
experiment_results.json and derives each published claim with an explicit numerator
and denominator. Any claim whose recomputation differs is written to mismatches.
"""

from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from . import common

FROZEN = common.REPO / "research" / "science_002" / "artifacts"


def _rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def run(artifacts: Path = FROZEN) -> dict[str, Any]:
    universe = _rows(artifacts / "universe.csv")
    matches = _rows(artifacts / "entity_matches.csv")
    exclusions = _rows(artifacts / "entity_exclusions.csv")
    panel_rows = _rows(artifacts / "panel.csv")
    universe_summary = _json(artifacts / "universe_summary.json")
    panel_summary = _json(artifacts / "panel_summary.json")
    experiment = _json(artifacts / "experiment_results.json")

    claims: list[dict[str, Any]] = []

    def claim(name: str, reported: Any, recomputed: Any, note: str = "") -> None:
        equal = reported == recomputed
        claims.append({"claim": name, "reported": reported, "recomputed": recomputed,
                       "match": equal, "note": note})

    # ---- universe -------------------------------------------------------
    claim("universe firms", 48, len(universe))
    claim("universe summary n_included", universe_summary["n_included"], len(universe))
    claim("candidate registrants", 62, universe_summary["n_candidate_ciks"])
    claim("accepted links (all candidates)", 189, len(matches))
    claim("excluded candidates", 14, len(exclusions))
    tiers = Counter(row["tier"] for row in matches)
    for tier, expected in (("T_A", 59), ("T_A2", 4), ("T_B", 126)):
        claim("links tier " + tier, expected, tiers[tier])
    link_sum = sum(int(float(row["n_window_clearances"])) for row in matches)
    claim("clearances summed over accepted links", 3143, max(
        universe_summary.get("n_clearances_total", 0), 0),
        "artifact: " + str(link_sum))
    # links belonging to the 48 universe firms only
    included_ciks = {row["cik"] for row in universe}
    links_in_universe = [row for row in matches if row["cik"] in included_ciks]
    claims.append({"claim": "links among the 48 universe firms", "reported": None,
                   "recomputed": len(links_in_universe), "match": None,
                   "note": "not reported separately by SCIENCE-002"})

    # ---- panel ----------------------------------------------------------
    claim("panel rows", 2771, len(panel_rows))
    claim("panel summary n_rows", panel_summary["n_rows"], len(panel_rows))
    counts = Counter(row["split"] for row in panel_rows)
    claim("train rows", 1956, counts["train"])
    claim("holdout rows", 815, counts["holdout"])
    pos = Counter()
    for row in panel_rows:
        pos[row["split"]] += int(row["label"])
    claim("positive rows (all)", 1413, pos["train"] + pos["holdout"])
    complete = [row for row in panel_rows
                if all(row.get(k, "") not in ("", "None", "nan")
                       for k in ("rd_ttm_log", "rd_yoy", "rd_to_sales", "rd_growth_vol"))]
    claim("complete-case rows (B0..B3 features present)", 2554, len(complete))
    claim("experiment n_rows_complete_case", experiment["meta"]["n_rows_complete_case"], len(complete))
    csplit = Counter(row["split"] for row in complete)
    claim("experiment n_train", experiment["meta"]["n_train"], csplit["train"])
    claim("experiment n_holdout", experiment["meta"]["n_holdout"], csplit["holdout"])
    claim("documented rows dropped for missing R&D (panel_summary)", 78,
          panel_summary.get("n_missing_rd_feature_rows"),
          "suspected undercount: this counts rows with NO rd feature at all")
    claims.append({"claim": "rows dropped from 2,771 to 2,554", "reported": 78,
                   "recomputed": len(panel_rows) - len(complete), "match": False,
                   "note": "2,771 - 2,554 = 217, not 78; DATASET_CARD/RESULTS quote 78"})
    claim("rows dropped for SEC coverage", 397,
          panel_summary.get("n_rows_dropped_sec_coverage"))

    firms_all = {row["key"] for row in panel_rows}
    firms_hold = {row["key"] for row in panel_rows if row["split"] == "holdout"}
    firms_hold_c = {row["key"] for row in complete if row["split"] == "holdout"}
    claim("firms with any panel row", 48, len(firms_all))
    claims.append({"claim": "firms in holdout panel", "reported": 46,
                   "recomputed": len(firms_hold), "match": len(firms_hold) == 46})
    claims.append({"claim": "firms in holdout complete case", "reported": 44,
                   "recomputed": len(firms_hold_c), "match": len(firms_hold_c) == 44})
    by_firm_labels: dict[str, list[int]] = defaultdict(list)
    for row in complete:
        if row["split"] == "holdout":
            by_firm_labels[row["key"]].append(int(row["label"]))
    strat = sum(1 for values in by_firm_labels.values() if len(set(values)) == 2)
    claim("firms entering the stratified AUC", 31, strat)
    claim("experiment n_firms_stratified", experiment["conditional"]["B2c"]["n_firms"], strat)
    single = sum(1 for values in by_firm_labels.values() if len(set(values)) == 1)
    claims.append({"claim": "single-class holdout firms", "reported": 15,
                   "recomputed": single, "match": single == 15,
                   "note": f"{len(firms_hold_c)} holdout firms - {strat} stratified"})

    prevalence = sum(int(r["label"]) for r in complete if r["split"] == "holdout") / len(complete and [r for r in complete if r["split"] == "holdout"])
    claim("holdout prevalence (complete case)",
          round(experiment["meta"]["prevalence_holdout"], 4), round(prevalence, 4))

    # firms whose entire panel is single class (the audit A5 claim of 6)
    panel_single = 0
    by_firm_panel: dict[str, list[int]] = defaultdict(list)
    for row in panel_rows:
        by_firm_panel[row["key"]].append(int(row["label"]))
    panel_single = sum(1 for v in by_firm_panel.values() if len(set(v)) == 1)
    claims.append({"claim": "single-class firms in the whole panel", "reported": 6,
                   "recomputed": panel_single, "match": panel_single == 6,
                   "note": "audit A5 reported 6; the holdout-only count is different"})

    # ---- experiment -----------------------------------------------------
    claim("pooled B1 AUC", 0.8292209710777716, experiment["pooled"]["B1"])
    claim("pooled B3 AUC", 0.8333147303108893, experiment["pooled"]["B3"])
    claim("stratified B3c", 0.452689209378014, experiment["conditional"]["B3c"]["value"])
    claim("delta B3c - B2c", -0.033663969385031994,
          experiment["primary"]["delta_stratified_auc_B3c_minus_B2c"])
    claim("permutation p", 0.095952023988006, experiment["permutation"]["p_two_sided"])

    mismatches = [c for c in claims if c["match"] is False]
    return {
        "meta": {"source": str(artifacts), "n_claims": len(claims),
                 "n_mismatch": len(mismatches)},
        "claims": claims,
        "mismatches": mismatches,
    }