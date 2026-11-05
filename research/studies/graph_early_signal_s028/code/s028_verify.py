"""Verify the numbers stated in the S-028 reports against the committed artifacts.

Every claim is a (description, expected, observed, tolerance) tuple. The script fails if
any expected value cannot be re-derived from the artifacts. This is the mechanism that
prevents a number in the prose from drifting away from the evidence.
"""
from __future__ import annotations

import gzip
import json
import sys
from pathlib import Path

ART = Path(__file__).resolve().parents[1] / "artifacts"
FAILURES: list[str] = []
CHECKS = 0


def load_predictions(label: str):
    path = ART / f"predictions_{label}.json.gz"
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        return json.load(handle)


def load(name: str):
    return json.loads((ART / name).read_text(encoding="utf-8"))


def check(description: str, expected, observed, tol: float = 0.0) -> None:
    global CHECKS
    CHECKS += 1
    if isinstance(expected, (int, float)) and isinstance(observed, (int, float)):
        ok = abs(float(expected) - float(observed)) <= tol
    else:
        ok = expected == observed
    if not ok:
        FAILURES.append(f"{description}: expected {expected!r}, observed {observed!r}")
    print(f"{'ok  ' if ok else 'FAIL'} {description}: {observed!r}")


def main() -> int:
    feasibility = load("feasibility.json")
    validation = load("frozen_validation.json")
    summary = load("experiment_summary.json")
    stats = load("statistical_validation.json")

    print("== feasibility ==")
    check("material events", 31802, feasibility["event_counts"]["material_events_total"])
    check("qualifying events", 25947, feasibility["event_counts"]["qualifying_events_total"])
    check("qualifying share", 0.8159, feasibility["event_counts"]["qualifying_share"], 5e-5)
    check("events with both keys", 3833, feasibility["coverage"]["events_with_both"])
    check("share with both", 0.1205, feasibility["coverage"]["share_with_both"], 5e-5)
    check("companies", 51, feasibility["coverage"]["distinct_companies"])
    check("tracks", 38, feasibility["coverage"]["distinct_tracks"])
    check("H4q rows", 41003, feasibility["panels"]["primary_H4q_qualifying"]["n_examples"])
    check("H4q positives", 418, feasibility["panels"]["primary_H4q_qualifying"]["n_positives"])
    check("H4q base rate", 0.01019, feasibility["panels"]["primary_H4q_qualifying"]["base_rate"], 5e-6)
    check("H2q positives", 239, feasibility["panels"]["secondary_H2q_qualifying"]["n_positives"])
    check("fidelity overall", True, feasibility["fidelity_self_check"]["ok"])
    check("18 - available_at minus event_date keys", ["14"],
          list(feasibility["knowledge_clock"]["available_at_minus_event_date_days"].keys()))
    check("left truncation share A", 0.7143,
          feasibility["left_truncation"]["share_already_active_at_first_origin"], 5e-5)
    check("two-hop redundancy", 0.849,
          feasibility["graph_feature_redundancy"]["novelty"]["g_twohop_reach"]["max_abs_corr_with_B3"],
          5e-4)
    check("eigenvector redundancy", 0.779,
          feasibility["graph_feature_redundancy"]["novelty"]["g_company_eigenvector"]["max_abs_corr_with_B3"],
          5e-4)

    print("\n== frozen harness validation ==")
    check("overall pass", True, validation["overall_ok"])
    check("learner parity", True, validation["learner_parity"]["ok"])
    check("AP parity", True, validation["ap_parity"]["ok"])
    check("frozen pooled rows", 5159, validation["pooled"]["rows"])
    check("frozen pooled positives", 78, validation["pooled"]["positives"])
    check("frozen pooled AP", 0.101060, validation["pooled"]["ap"], 5e-6)
    check("frozen persistence AP", 0.044614, validation["pooled"]["persistence_ap"], 5e-6)
    check("frozen window AP 2025-04-01", 0.137085,
          validation["per_window"]["2025-04-01"]["ap"], 5e-6)

    print("\n== H4q results ==")
    h4 = summary["horizons"]["H4q"]
    check("H4q rows", 41003, h4["panel"]["n_examples"])
    check("H4q positives", 418, h4["panel"]["n_positives"])
    check("H4q holdouts", ["2025-04-01", "2025-07-01", "2025-10-01"], h4["panel"]["holdouts"])
    check("B2 pooled AP", 0.0751, h4["specs"]["B2_frozen_spec16"]["pooled"]["pr_auc"], 5e-5)
    check("G1 pooled AP", 0.0690, h4["specs"]["G1_graph"]["pooled"]["pr_auc"], 5e-5)
    check("B1 pooled AP", 0.0690, h4["specs"]["B1_history10"]["pooled"]["pr_auc"], 5e-5)
    check("HGB spec16 pooled AP", 0.0567,
          h4["specs"]["B2g_hgb_spec16"]["pooled"]["pr_auc"], 5e-5)
    for name, expected in (("G3_no_peer_entry", 0.0730), ("G3_no_similarity", 0.0734),
                           ("G3_no_twohop", 0.0698), ("G3_no_centrality", 0.0699),
                           ("G3_no_decay", 0.0695), ("G3_no_cooccurrence", 0.0673)):
        check(f"{name} pooled AP", expected, h4["specs"][name]["pooled"]["pr_auc"], 5e-5)

    g1_h4 = h4["comparisons"]["G1_graph_minus_B2"]
    check("H4q dAP G1-B2", -0.00609, g1_h4["company"]["delta"], 5e-5)
    check("H4q CI low", -0.02219, g1_h4["company"]["ci_low"], 5e-5)
    check("H4q CI high", 0.00450, g1_h4["company"]["ci_high"], 5e-5)
    check("H4q MDE", 0.01943, g1_h4["company"]["mde_80"], 5e-5)
    check("H4q pair CI low", -0.03347, g1_h4["pair"]["ci_low"], 5e-5)

    g2 = h4["g2"]
    check("H4q G2 real pooled AP", 0.06900, g2["real_pooled_ap"], 5e-5)
    random_ap = sorted(row["pooled_ap"] for row in g2["randomisations"])
    check("H4q G2 randomisation count", 40, len(random_ap))
    check("H4q G2 min", 0.06919, random_ap[0], 5e-5)
    check("H4q G2 median", 0.07432, random_ap[len(random_ap) // 2], 5e-5)
    check("H4q G2 max", 0.08198, random_ap[-1], 5e-5)
    check("H4q randomisations beating real", 40,
          sum(1 for value in random_ap if value >= g2["real_pooled_ap"]))

    print("\n== H2q results ==")
    h2 = summary["horizons"]["H2q"]
    check("H2q rows", 44433, h2["panel"]["n_examples"])
    check("H2q positives", 239, h2["panel"]["n_positives"])
    check("H2q B2 pooled AP", 0.0674, h2["specs"]["B2_frozen_spec16"]["pooled"]["pr_auc"], 5e-5)
    check("H2q G1 pooled AP", 0.0670, h2["specs"]["G1_graph"]["pooled"]["pr_auc"], 5e-5)
    check("H2q HGB pooled AP", 0.0354, h2["specs"]["B2g_hgb_spec16"]["pooled"]["pr_auc"], 5e-5)
    g1_h2 = h2["comparisons"]["G1_graph_minus_B2"]
    check("H2q dAP G1-B2", -0.00031, g1_h2["company"]["delta"], 5e-5)
    check("H2q MDE", 0.04366, g1_h2["company"]["mde_80"], 5e-5)
    hgb_h2 = h2["comparisons"]["B2g_hgb_spec16_minus_B2"]["company"]
    check("H2q HGB CI high (excludes zero)", -0.000465, hgb_h2["ci_high"], 5e-5)
    random_h2 = sorted(row["pooled_ap"] for row in h2["g2"]["randomisations"])
    check("H2q G2 real pooled AP", 0.06704, h2["g2"]["real_pooled_ap"], 5e-5)
    check("H2q randomisations beating real", 30,
          sum(1 for value in random_h2 if value >= h2["g2"]["real_pooled_ap"]))

    print("\n== decisions ==")
    for label in ("H4q", "H2q"):
        decision = stats["horizons"][label]["decision"]
        check(f"{label} H1 status", "NULL (well-powered: |delta| below MDE)",
              decision["h1_status"])
        check(f"{label} outcome", "B (no additional information beyond strong non-graph baselines)",
              decision["outcome"])
        check(f"{label} H2 supported", False, decision["h2_supported"])
        check(f"{label} windows excluding zero", 0,
              decision["criteria"]["windows_excluding_zero"])
    family = stats["multiplicity"]["family"]
    check("BH family size", 8, len(family))
    check("BH rejections", 0, sum(1 for row in family if row["reject"]))

    print("\n== stability ==")
    check("H4q reportable tracks", 6, len(stats["horizons"]["H4q"]["stability"]["by_track"]))
    check("H4q reportable companies", 5, len(stats["horizons"]["H4q"]["stability"]["by_company"]))
    check("H2q reportable tracks", 1, len(stats["horizons"]["H2q"]["stability"]["by_track"]))

    print("\n" + "=" * 60)
    print(f"checks run: {CHECKS}, failures: {len(FAILURES)}")
    for failure in FAILURES:
        print("  FAILED:", failure)
    return 1 if FAILURES else 0


if __name__ == "__main__":
    raise SystemExit(main())
