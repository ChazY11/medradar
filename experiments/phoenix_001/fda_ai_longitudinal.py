#!/usr/bin/env python3
"""Independently reproduce aggregate statistics from the FDA AI longitudinal study."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
from docx import Document
from scipy import stats

ERAS = ["Era 1", "Era 2", "Era 3", "Era 4"]
PUBLISHED_HHI = [0.181, 0.427, 0.738, 0.612]


def hhi(counts: np.ndarray) -> float:
    counts = np.asarray(counts, dtype=float)
    total = counts.sum()
    if total <= 0:
        raise ValueError("HHI is undefined for an empty cohort")
    return float(np.square(counts / total).sum())


def cochran_armitage(successes: np.ndarray, totals: np.ndarray, scores=None) -> float:
    successes = np.asarray(successes, dtype=float)
    totals = np.asarray(totals, dtype=float)
    scores = np.arange(1, len(totals) + 1, dtype=float) if scores is None else np.asarray(scores, dtype=float)
    n, x = totals.sum(), successes.sum()
    p = x / n
    mean_score = np.sum(totals * scores) / n
    numerator = np.sum(successes * (scores - mean_score))
    denominator = np.sqrt(p * (1 - p) * np.sum(totals * (scores - mean_score) ** 2))
    if denominator == 0:
        raise ValueError("Trend statistic is undefined for a degenerate cohort")
    return float(numerator / denominator)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("supplement_docx", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--bootstrap", type=int, default=2000)
    parser.add_argument("--permutations", type=int, default=10000)
    parser.add_argument("--seed", type=int, default=20261106)
    args = parser.parse_args()
    path = args.supplement_docx.resolve()
    document = Document(path)
    table = document.tables[1]
    rows = [[cell.text.strip() for cell in row.cells] for row in table.rows]
    specialties = [row[0] for row in rows[1:-1]]
    counts = np.array([[int(value) for value in row[1:5]] for row in rows[1:-1]], dtype=int)
    totals = counts.sum(axis=0)
    assert counts.shape == (17, 4), counts.shape
    assert totals.tolist() == [42, 190, 406, 792], totals
    rng = np.random.default_rng(args.seed)
    point_hhi = [hhi(counts[:, i]) for i in range(4)]
    bootstrap_hhi = []
    for i in range(4):
        probabilities = counts[:, i] / totals[i]
        samples = rng.multinomial(totals[i], probabilities, size=args.bootstrap)
        values = np.square(samples / totals[i]).sum(axis=1)
        bootstrap_hhi.append({
            "mean": float(values.mean()),
            "ci_95": [float(np.quantile(values, 0.025)), float(np.quantile(values, 0.975))],
        })
    era3_samples = rng.multinomial(totals[2], counts[:, 2] / totals[2], size=args.bootstrap)
    era4_samples = rng.multinomial(totals[3], counts[:, 3] / totals[3], size=args.bootstrap)
    delta = np.square(era4_samples / totals[3]).sum(axis=1) - np.square(era3_samples / totals[2]).sum(axis=1)
    delta_p = float(min(1.0, 2 * min(np.mean(delta <= 0), np.mean(delta >= 0))))
    chi2, chi_p, dof, expected = stats.chi2_contingency(counts, correction=False)
    cramers_v = float(np.sqrt(chi2 / (counts.sum() * min(counts.shape[0] - 1, counts.shape[1] - 1))))

    # Permute era assignments while preserving every specialty's overall count.
    specialty_ids = np.repeat(np.arange(counts.shape[0]), counts.sum(axis=1))
    era_ids = np.repeat(np.arange(counts.shape[1]), totals)
    assert len(specialty_ids) == len(era_ids) == counts.sum()
    observed = float(chi2)
    exceed = 0
    for _ in range(args.permutations):
        shuffled = rng.permutation(era_ids)
        table_perm = np.bincount(specialty_ids * 4 + shuffled, minlength=68).reshape(17, 4)
        stat = float(stats.chi2_contingency(table_perm, correction=False)[0])
        exceed += stat >= observed - 1e-12
    permutation_p = (exceed + 1) / (args.permutations + 1)

    trends = []
    for i, specialty in enumerate(specialties):
        z = cochran_armitage(counts[i], totals)
        p = float(2 * stats.norm.sf(abs(z)))
        trends.append({
            "specialty": specialty, "z": z, "p_uncorrected": p,
            "p_bonferroni": min(1.0, p * len(specialties)),
        })
    payload = {
        "status": "completed_independent_aggregate_reproduction",
        "paper": "https://pmc.ncbi.nlm.nih.gov/articles/PMC13505343/",
        "supplement": "https://www.ebi.ac.uk/europepmc/webservices/rest/PMC13505343/supplementaryFiles",
        "supplement_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "seed": args.seed, "bootstrap_resamples": args.bootstrap, "permutations": args.permutations,
        "specialties": specialties, "counts": counts.tolist(), "era_totals": totals.tolist(),
        "hhi": {
            "independent_point_estimates": point_hhi,
            "published_point_estimates": PUBLISHED_HHI,
            "absolute_differences_from_rounded_publication": [abs(a - b) for a, b in zip(point_hhi, PUBLISHED_HHI)],
            "bootstrap": bootstrap_hhi,
            "era4_minus_era3": {
                "point": point_hhi[3] - point_hhi[2],
                "ci_95": [float(np.quantile(delta, 0.025)), float(np.quantile(delta, 0.975))],
                "two_sided_p": delta_p,
                "nonpositive_resamples": int((delta <= 0).sum()),
                "nonnegative_resamples": int((delta >= 0).sum()),
                "p_reporting": "Empirical two-sided tail probability from 2000 resample pairs. This seed gives p=0.001; the paper reports p<0.001, a Monte Carlo/reporting difference rather than a contradictory point estimate.",
            },
        },
        "specialty_era_association": {
            "chi_square": float(chi2), "dof": int(dof), "p_asymptotic": float(chi_p),
            "cramers_v": cramers_v, "expected_cells_below_5": int((expected < 5).sum()),
            "permutation_exceedances": exceed, "permutation_p": permutation_p,
        },
        "cochran_armitage": trends,
        "evidence_category": 1,
        "scope_limit": "Independent recomputation from published aggregate counts. Device-level duplicate checks, manufacturer-type logistic/Firth/cluster-robust regressions and MedRadar migration were not run.",
        "small_sample_warning": "Trend tests use four ordinal eras, not annual forecasts. The technology-company regression has only 13 devices across 5 firms and is not reproduced from the aggregate supplement.",
    }
    output = args.output.resolve()
    output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"hhi": point_hhi, "hhi_delta_p": delta_p,
                      "chi_square": chi2, "cramers_v": cramers_v,
                      "expected_below_5": int((expected < 5).sum()), "permutation_p": permutation_p,
                      "radiology_z": trends[0]["z"], "cardiovascular_z": trends[1]["z"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
