"""S-028 statistical validation and pre-registered decision rules.

Reads ONLY the stored prediction artifacts (no model is refitted) and re-derives:

* paired AP differences with two clustering choices (company and company-track pair);
* bootstrap standard errors and MDE at 80% power;
* Benjamini-Hochberg correction over the pre-registered hypothesis family;
* stability by track, company and year;
* the H1 / H2 / outcome-A..D verdicts exactly as written in PRE_REGISTRATION.md §11.

Usage: python s028_stats.py [--horizons 4,2]
"""
from __future__ import annotations

import argparse
import json
import math
import random
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[4]))

from s028_lib import fast_ap, paired_cluster_bootstrap  # noqa: E402

STUDY = Path(__file__).resolve().parents[1]
ARTIFACTS = STUDY / "artifacts"
RESAMPLES = 2000
SEED = 7
MDE_Z = 1.959964 + 0.841621
Q_FDR = 0.10


def load(label: str) -> dict[str, Any] | None:
    """Load a stored prediction artifact (gzip-compressed in the repository)."""
    import gzip
    for name in (f"predictions_{label}.json.gz", f"predictions_{label}.json"):
        path = ARTIFACTS / name
        if not path.exists():
            continue
        if name.endswith(".gz"):
            with gzip.open(path, "rt", encoding="utf-8") as handle:
                return json.load(handle)
        return json.loads(path.read_text(encoding="utf-8"))
    return None


def _ap(labels: list[int], probs: list[float]) -> float | None:
    return fast_ap(labels, probs)


def collect(predictions: dict[str, Any], spec: str, windows: list[str]) -> dict[str, Any]:
    block = predictions["specs"][spec]["predictions"]
    labels, probs, company, pair, tracks, cutoff = [], [], [], [], [], []
    for window in windows:
        row = block.get(window)
        if row is None:
            continue
        labels.extend(row["labels"])
        probs.extend(row["probs"])
        company.extend(row["companies"])
        pair.extend(row["pairs"])
        tracks.extend(row["tracks"])
        cutoff.extend([window] * len(row["labels"]))
    year = [str(value)[:4] for value in cutoff]
    return {"labels": labels, "probs": probs, "company": company, "pair": pair,
            "companies": company, "tracks": tracks, "cutoff": cutoff, "year": year}


def bootstrap_delta(a: dict[str, Any], b: dict[str, Any], unit: str, *,
                    resamples: int = RESAMPLES, seed: int = SEED) -> dict[str, Any]:
    """Paired cluster bootstrap of AP(a) - AP(b) on already-collected flat rows.

    Delegates to the shared vectorised implementation so every CI in this study is
    computed by exactly one code path.
    """
    if not a["labels"] or a["labels"] != b["labels"]:
        return {"delta": None, "ci_low": None, "ci_high": None, "se": None,
                "mde_80": None, "p_one_sided": None, "rows": 0}
    block_a = {"pooled": {"labels": a["labels"], "probs": a["probs"],
                          "companies": a["company"], "pairs": a["pair"]}}
    block_b = {"pooled": {"labels": b["labels"], "probs": b["probs"],
                          "companies": b["company"], "pairs": b["pair"]}}
    return paired_cluster_bootstrap(block_a, block_b, ["pooled"], unit,
                                    resamples=resamples, seed=seed)


def _window_p(a: dict[str, Any], b: dict[str, Any]) -> float:
    result = bootstrap_delta(a, b, "company")
    value = result.get("p_one_sided")
    return value if value is not None else 1.0


def strata(predictions: dict[str, Any], spec_a: str, spec_b: str, windows: list[str],
           field: str) -> dict[str, Any]:
    a = collect(predictions, spec_a, windows)
    b = collect(predictions, spec_b, windows)
    keys = a[field] if field in a else predictions["specs"][spec_a]["predictions"]
    out: dict[str, Any] = {}
    values = sorted({key for key in keys})
    for value in values:
        index = [i for i, key in enumerate(keys) if key == value]
        labels = [a["labels"][i] for i in index]
        if len(labels) < 10 or sum(labels) < 5:
            continue
        ap_a = _ap(labels, [a["probs"][i] for i in index])
        ap_b = _ap(labels, [b["probs"][i] for i in index])
        out[str(value)] = {"n": len(labels), "positives": sum(labels), "ap_a": ap_a,
                           "ap_b": ap_b,
                           "delta": (ap_a - ap_b) if ap_a is not None and ap_b is not None else None}
    return out


def bh(p_values: list[float], q: float = Q_FDR) -> list[dict[str, Any]]:
    indexed = sorted(enumerate(p_values), key=lambda pair: pair[1])
    m = len(p_values)
    result = [{"index": index, "p": value, "reject": False} for index, value in enumerate(p_values)]
    previous = 1.0
    for rank, (index, value) in enumerate(reversed(indexed), start=1):
        threshold = q * (m - rank + 1) / m
        if value <= threshold and previous >= 0:
            result[index]["reject"] = True
        previous = min(previous, value)
    for entry in result:
        entry["bh_threshold"] = q * (entry["index"] + 1) / m
    return result


def decide(h1_pooled: dict[str, Any], window_results: list[dict[str, Any]],
           h2: dict[str, Any]) -> dict[str, Any]:
    """Apply PRE_REGISTRATION.md §11 literally."""
    windows_excluding = sum(1 for entry in window_results if entry.get("excludes_zero"))
    total_windows = len(window_results)
    a = total_windows > 0 and windows_excluding >= math.ceil(2 * total_windows / 3)
    b = bool(h1_pooled.get("company", {}).get("excludes_zero")
             and h1_pooled.get("pair", {}).get("excludes_zero"))
    point = h1_pooled.get("company", {}).get("delta")
    mde = h1_pooled.get("company", {}).get("mde_80")
    c = point is not None and mde is not None and point >= mde
    h1_supported = a and b and c
    if h1_supported:
        h1_status = "SUPPORTED"
    else:
        significantly_negative = any(entry.get("ci_high") is not None and entry["ci_high"] < 0
                                     for entry in window_results)
        if significantly_negative:
            h1_status = "NULL (G1 significantly worse than baseline)"
        elif mde is not None and point is not None and abs(point) < mde:
            h1_status = "NULL (well-powered: |delta| below MDE)"
        else:
            h1_status = "UNDERPOWERED (cannot distinguish from zero)"
    h2_supported = bool(h2.get("real_above_975") and h1_supported)
    if h1_status == "SUPPORTED" and not h2_supported:
        outcome = "A-weak (incremental signal but not attributable to relational structure)"
    elif h1_supported and h2_supported:
        outcome = "A (relational structure carries incremental information)"
    elif h1_status.startswith("NULL"):
        outcome = "B (no additional information beyond strong non-graph baselines)"
    else:
        outcome = "D (data cannot support a reliable judgement at this power)"
    return {"criteria": {"a_2of3_windows_ci_excludes_zero": a,
                         "b_pooled_both_clusterings_exclude_zero": b,
                         "c_point_at_or_above_mde": c,
                         "windows_excluding_zero": windows_excluding,
                         "total_windows": total_windows},
            "h1_status": h1_status, "h2_supported": h2_supported,
            "h2_criteria": h2, "outcome": outcome}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--horizons", default="4,2")
    args = parser.parse_args(argv)
    report: dict[str, Any] = {"study": "S-028", "resamples": RESAMPLES, "seed": SEED,
                              "fdr_q": Q_FDR, "horizons": {}}
    register: list[tuple[str, float]] = []
    for quarters in [int(part) for part in args.horizons.split(",") if part.strip()]:
        label = f"H{quarters}q"
        predictions = load(label)
        if predictions is None:
            report["horizons"][label] = {"error": "artifact missing"}
            continue
        windows = predictions["panel"]["holdouts"]
        entry: dict[str, Any] = {"holdouts": windows,
                                 "panel": predictions["panel"], "paired": {},
                                 "b0_pooled": {}, "g2": predictions.get("g2", {})}
        reference = "B2_frozen_spec16"
        for spec in ("B1_history10", "G1_graph", "G3_no_peer_entry", "G3_no_similarity",
                     "G3_no_twohop", "G3_no_cooccurrence", "G3_no_centrality", "G3_no_decay",
                     "B2g_hgb_spec16", "G1g_hgb_graph"):
            if spec not in predictions["specs"]:
                continue
            a = collect(predictions, spec, windows)
            b = collect(predictions, reference, windows)
            per_window = []
            for window in windows:
                block = predictions["specs"][spec]["predictions"]
                ref_block = predictions["specs"][reference]["predictions"]
                if window not in block or window not in ref_block:
                    continue
                window_ci = bootstrap_delta(collect(predictions, spec, [window]),
                                            collect(predictions, reference, [window]),
                                            "company")
                ap_a = _ap(block[window]["labels"], block[window]["probs"])
                ap_b = _ap(ref_block[window]["labels"], ref_block[window]["probs"])
                per_window.append({"window": window,
                                   "rows": len(block[window]["labels"]),
                                   "positives": sum(block[window]["labels"]),
                                   "ap": ap_a, "ap_reference": ap_b,
                                   "delta": (ap_a - ap_b)
                                   if ap_a is not None and ap_b is not None else None,
                                   "ci_low": window_ci.get("ci_low"),
                                   "ci_high": window_ci.get("ci_high"),
                                   "excludes_zero": window_ci.get("excludes_zero"),
                                   "mde_80": window_ci.get("mde_80")})
            pooled = {"company": bootstrap_delta(a, b, "company"),
                      "pair": bootstrap_delta(a, b, "pair")}
            entry["paired"][spec] = {"per_window": per_window, "pooled": pooled}
            if spec == "G1_graph":
                register.append((f"{label}:H1_G1_minus_B2_pooled_company",
                                 pooled["company"].get("p_one_sided") or 1.0))
                for row in per_window:
                    if row.get("mde_80") is not None:
                        register.append((f"{label}:H1_G1_minus_B2_{row['window']}",
                                         _window_p(collect(predictions, spec, [row["window"]]),
                                                   collect(predictions, reference, [row["window"]]))))

        # stability strata for the key comparison
        entry["stability"] = {
            "by_track": strata(predictions, "G1_graph", reference, windows, "tracks"),
            "by_company": strata(predictions, "G1_graph", reference, windows, "companies"),
            "by_origin": strata(predictions, "G1_graph", reference, windows, "cutoff"),
            "note": ("All pre-declared holdout origins fall in 2025 (H=4q) or 2025-2026 (H=2q), "
                     "so calendar-year stratification is not informative; per-origin stability is "
                     "reported instead. Strata require n>=10 and positives>=5."),
        }
        # G2 randomisation distribution
        g2 = predictions.get("g2", {})
        deltas = [row["pooled_delta_vs_real"] for row in g2.get("randomisations", [])
                  if row.get("pooled_delta_vs_real") is not None]
        real_pooled = g2.get("real_pooled_ap")
        random_pooled = [row["pooled_ap"] for row in g2.get("randomisations", [])
                         if row.get("pooled_ap") is not None]
        h2: dict[str, Any] = {"n_randomisations": len(deltas)}
        if deltas:
            ordered = sorted(deltas)
            real_minus_random = [-value for value in deltas]  # real - randomised
            ordered_real = sorted(real_minus_random)
            h2.update({
                "real_pooled_ap": real_pooled,
                "randomised_pooled_ap_median": (sorted(random_pooled)[len(random_pooled) // 2]
                                                if random_pooled else None),
                "randomised_pooled_ap_min": min(random_pooled) if random_pooled else None,
                "randomised_pooled_ap_max": max(random_pooled) if random_pooled else None,
                "delta_real_minus_randomised_median": ordered_real[len(ordered_real) // 2],
                "delta_q025": ordered_real[int(0.025 * len(ordered_real))],
                "delta_q975": ordered_real[min(len(ordered_real) - 1,
                                               int(0.975 * len(ordered_real)))],
                "real_above_975": bool(real_pooled is not None and random_pooled
                                       and real_pooled > sorted(random_pooled)[
                                           min(len(random_pooled) - 1,
                                               int(0.975 * len(random_pooled)))]),
                "fraction_randomisations_beating_real": (
                    sum(1 for value in random_pooled if real_pooled is not None and value >= real_pooled)
                    / len(random_pooled)),
            })
        entry["h2"] = h2

        window_results = entry["paired"]["G1_graph"]["per_window"]
        entry["decision"] = decide(entry["paired"]["G1_graph"]["pooled"], window_results, h2)
        report["horizons"][label] = entry
        print(f"[{label}] H1 status={entry['decision']['h1_status']} "
              f"outcome={entry['decision']['outcome']}")
        for spec, data in entry["paired"].items():
            company = data["pooled"]["company"]
            print(f"    {spec:22s} pooled dAP={company.get('delta')} "
                  f"CI=[{company.get('ci_low')},{company.get('ci_high')}] "
                  f"MDE={company.get('mde_80')}")
    if register:
        corrected = bh([value for _, value in register])
        report["multiplicity"] = {
            "family": [{"test": name, **entry} for (name, _), entry in zip(register, corrected)],
            "q": Q_FDR, "method": "Benjamini-Hochberg over the pre-registered family"}
    out = ARTIFACTS / "statistical_validation.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True, default=str) + "\n",
                   encoding="utf-8")
    print(f"\nwrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
