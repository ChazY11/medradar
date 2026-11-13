"""Exploratory experiment: does technology/R&D disclosure precede a discrete event?

Pre-registered protocol: research/science_001/PROTOCOL.md (hashed into the
results file). The order of operations in this module is fixed by that protocol;
nothing here is tuned after seeing an outcome.

Hypothesis under test (H1)
--------------------------
Within a time-ordered split, an 8-K whose own prose is more R&D/technology
intensive is followed, within 90 days, by a materially more likely *technology
transaction disclosure* (SEC item 1.01 material definitive agreement or 2.01
completed acquisition/disposition) than the firm-activity baseline explains.

Nothing here is a prediction claim: the split is chronological, the sample is
small, and the result is labelled exploratory in the output.

Statistical machinery is deliberately stdlib-only (AUC, ridge logistic via IRLS,
cluster bootstrap, circular-shift permutation, Hanley-McNeil power). No third
party numeric stack is required to reproduce a number in this file.
"""

from __future__ import annotations

import csv
import hashlib
import json
import math
import random
from pathlib import Path
from typing import Any, Iterable, Sequence

HORIZON_DAYS = 90
RIDGE = 1.0
TRAIN_END_DEFAULT = "2024-12-31"

#: Model ladder, fixed before the run. Each entry is the ordered feature list.
MODELS: dict[str, list[str]] = {
    "B0_prevalence": [],
    "B1_firm_mean": [],
    "B2_activity": ["n_prior_events", "is_earnings"],
    "B3_activity_plus_dev_prose": ["n_prior_events", "is_earnings", "rd_per_1k", "tech_per_1k"],
}

PRIMARY_MODEL = "B3_activity_plus_dev_prose"
BASELINE_MODEL = "B2_activity"
TARGET = "label_tech_event"
PLACEBO_TARGET = "label_placebo"
POSITIVE_CONTROL_TARGET = "label_any_8k"

NUMERIC_COLUMNS = {
    "n_prior_events": int, "n_forward_events": int, "is_earnings": int,
    "label_tech_event": int, "label_placebo": int, "label_any_8k": int,
    "words": int, "n_documents": int, "rd_hits": int, "tech_hits": int,
    "exhibit_share": float, "rd_per_1k": float, "tech_per_1k": float,
    "dev_per_1k": float, "acceptance_offset_hours": int,
}


# --------------------------------------------------------------------------- #
# metrics
# --------------------------------------------------------------------------- #
def auc(scores: Sequence[float], labels: Sequence[int]) -> float | None:
    """Rank-based AUC with correct handling of tied scores."""
    pairs = list(zip(scores, labels))
    positives = sum(1 for _, label in pairs if label == 1)
    negatives = len(pairs) - positives
    if positives == 0 or negatives == 0:
        return None
    ordered = sorted(pairs, key=lambda pair: pair[0])
    ranks = [0.0] * len(ordered)
    index = 0
    while index < len(ordered):
        end = index
        while end + 1 < len(ordered) and ordered[end + 1][0] == ordered[index][0]:
            end += 1
        average_rank = (index + end) / 2.0 + 1.0
        for position in range(index, end + 1):
            ranks[position] = average_rank
        index = end + 1
    rank_sum = sum(rank for rank, (_, label) in zip(ranks, ordered) if label == 1)
    return (rank_sum - positives * (positives + 1) / 2.0) / (positives * negatives)


def brier(scores: Sequence[float], labels: Sequence[int]) -> float | None:
    if not labels:
        return None
    return sum((score - label) ** 2 for score, label in zip(scores, labels)) / len(labels)


def log_loss(scores: Sequence[float], labels: Sequence[int], eps: float = 1e-12) -> float | None:
    if not labels:
        return None
    total = 0.0
    for score, label in zip(scores, labels):
        clipped = min(1 - eps, max(eps, score))
        total += label * math.log(clipped) + (1 - label) * math.log(1 - clipped)
    return -total / len(labels)


def prevalence(labels: Sequence[int]) -> float | None:
    return (sum(labels) / len(labels)) if labels else None


# --------------------------------------------------------------------------- #
# ridge logistic regression (IRLS, stdlib)
# --------------------------------------------------------------------------- #
def standardize_fit(xs: Sequence[Sequence[float]]) -> tuple[list[float], list[float]]:
    if not xs:
        return [], []
    width = len(xs[0])
    means = [0.0] * width
    stds = [1.0] * width
    for column in range(width):
        values = [row[column] for row in xs]
        mean = sum(values) / len(values)
        variance = sum((value - mean) ** 2 for value in values) / len(values)
        std = math.sqrt(variance)
        means[column] = mean
        stds[column] = std if std > 1e-12 else 1.0
    return means, stds


def standardize_apply(xs: Sequence[Sequence[float]], means: Sequence[float],
                      stds: Sequence[float]) -> list[list[float]]:
    return [[(value - mean) / std for value, mean, std in zip(row, means, stds)]
            for row in xs]


def fit_logistic(xs: Sequence[Sequence[float]], labels: Sequence[int],
                 ridge: float = RIDGE, iterations: int = 60) -> list[float]:
    """Ridge-penalised logistic regression by Newton/IRLS. Returns [intercept, ...]."""
    if not xs:
        return [0.0]
    width = len(xs[0])
    beta = [0.0] * (width + 1)
    for _ in range(iterations):
        gradient = [0.0] * (width + 1)
        hessian = [[0.0] * (width + 1) for _ in range(width + 1)]
        for row, label in zip(xs, labels):
            linear = beta[0] + sum(b * x for b, x in zip(beta[1:], row))
            prob = 1.0 / (1.0 + math.exp(-max(-35.0, min(35.0, linear))))
            residual = label - prob
            weight = prob * (1.0 - prob)
            gradient[0] += residual
            hessian[0][0] += weight
            for j in range(width):
                gradient[j + 1] += residual * row[j]
                hessian[0][j + 1] += weight * row[j]
                hessian[j + 1][0] += weight * row[j]
                for k in range(width):
                    hessian[j + 1][k + 1] += weight * row[j] * row[k]
        for j in range(1, width + 1):
            gradient[j] -= ridge * beta[j]
            hessian[j][j] += ridge
        try:
            step = _solve(hessian, gradient)
        except ZeroDivisionError:
            break
        beta = [b + s for b, s in zip(beta, step)]
        if max((abs(s) for s in step), default=0.0) < 1e-9:
            break
    return beta


def _solve(matrix: Sequence[Sequence[float]], vector: Sequence[float]) -> list[float]:
    """Gaussian elimination with partial pivoting (small, dense systems)."""
    size = len(matrix)
    augmented = [list(row) + [value] for row, value in zip(matrix, vector)]
    for column in range(size):
        pivot = max(range(column, size), key=lambda r: abs(augmented[r][column]))
        if abs(augmented[pivot][column]) < 1e-12:
            raise ZeroDivisionError("singular system")
        augmented[column], augmented[pivot] = augmented[pivot], augmented[column]
        divisor = augmented[column][column]
        for j in range(column, size + 1):
            augmented[column][j] /= divisor
        for row in range(size):
            if row == column:
                continue
            factor = augmented[row][column]
            if factor == 0.0:
                continue
            for j in range(column, size + 1):
                augmented[row][j] -= factor * augmented[column][j]
    return [augmented[i][size] for i in range(size)]


def predict_proba(xs: Sequence[Sequence[float]], beta: Sequence[float]) -> list[float]:
    scores: list[float] = []
    for row in xs:
        linear = beta[0] + sum(b * x for b, x in zip(beta[1:], row))
        scores.append(1.0 / (1.0 + math.exp(-max(-35.0, min(35.0, linear)))))
    return scores


# --------------------------------------------------------------------------- #
# data loading
# --------------------------------------------------------------------------- #
def load_rows(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8", newline="") as handle:
        for raw in csv.DictReader(handle):
            row: dict[str, Any] = dict(raw)
            for column, coerce in NUMERIC_COLUMNS.items():
                value = row.get(column)
                row[column] = coerce(float(value)) if value not in (None, "") else 0
            rows.append(row)
    rows.sort(key=lambda r: (r["issuer"], r["acceptance_utc"]))
    return rows


def split_rows(rows: Sequence[dict[str, Any]], train_end: str) -> tuple[list[dict[str, Any]],
                                                                        list[dict[str, Any]]]:
    train = [row for row in rows if row["acceptance_utc"][:10] <= train_end]
    test = [row for row in rows if row["acceptance_utc"][:10] > train_end]
    return train, test


# --------------------------------------------------------------------------- #
# model ladder
# --------------------------------------------------------------------------- #
def score_models(train: Sequence[dict[str, Any]], test: Sequence[dict[str, Any]],
                 target: str) -> dict[str, dict[str, Any]]:
    """Fit each pre-registered model on train and score test. Returns test scores."""
    global_prevalence = prevalence([row[target] for row in train]) or 0.5
    firm_means: dict[str, float] = {}
    for row in train:
        firm_means.setdefault(row["issuer"], [0, 0])  # type: ignore[arg-type]
        firm_means[row["issuer"]][0] += row[target]
        firm_means[row["issuer"]][1] += 1
    smoothed = {key: (value[0] + 1.0) / (value[1] + 2.0) for key, value in firm_means.items()}

    scores: dict[str, dict[str, Any]] = {}
    for name, features in MODELS.items():
        if name == "B0_prevalence":
            scores[name] = {"scores": [global_prevalence] * len(test), "beta": None,
                            "features": []}
            continue
        if name == "B1_firm_mean":
            scores[name] = {
                "scores": [smoothed.get(row["issuer"], global_prevalence) for row in test],
                "beta": None, "features": [],
            }
            continue
        train_x = [[float(row[column]) for column in features] for row in train]
        test_x = [[float(row[column]) for column in features] for row in test]
        means, stds = standardize_fit(train_x)
        beta = fit_logistic(standardize_apply(train_x, means, stds),
                            [row[target] for row in train])
        scores[name] = {
            "scores": predict_proba(standardize_apply(test_x, means, stds), beta),
            "beta": beta, "means": means, "stds": stds, "features": features,
        }
    return scores


def evaluate(scores: dict[str, dict[str, Any]], test: Sequence[dict[str, Any]],
             target: str) -> dict[str, dict[str, Any]]:
    labels = [row[target] for row in test]
    table: dict[str, dict[str, Any]] = {}
    for name, payload in scores.items():
        model_scores = payload["scores"]
        table[name] = {
            "auc": auc(model_scores, labels),
            "brier": brier(model_scores, labels),
            "log_loss": log_loss(model_scores, labels),
            "n": len(labels),
            "positives": sum(labels),
            "features": payload.get("features", []),
            "beta": payload.get("beta"),
        }
    return table


# --------------------------------------------------------------------------- #
# uncertainty: cluster bootstrap over issuers
# --------------------------------------------------------------------------- #
def _issuer_labels(rows: Sequence[dict[str, Any]], labels: Sequence[int]) -> dict[str, list[int]]:
    grouped: dict[str, list[int]] = {}
    for row, label in zip(rows, labels):
        grouped.setdefault(row["issuer"], []).append(label)
    return grouped


def cluster_bootstrap(rows: Sequence[dict[str, Any]],
                      scores: dict[str, dict[str, Any]], target: str,
                      draws: int = 2000, seed: int = 20261114) -> dict[str, Any]:
    """Percentile CI for AUC by resampling issuers (the dependence unit)."""
    issuers = sorted({row["issuer"] for row in rows})
    if len(issuers) < 3:
        return {"draws": 0, "note": "too few clusters for a bootstrap"}
    index_by_issuer: dict[str, list[int]] = {}
    for position, row in enumerate(rows):
        index_by_issuer.setdefault(row["issuer"], []).append(position)
    rng = random.Random(seed)
    samples: dict[str, list[float]] = {name: [] for name in scores}
    delta_samples: list[float] = []
    for _ in range(draws):
        chosen = [rng.choice(issuers) for _ in issuers]
        positions: list[int] = []
        for issuer in chosen:
            positions.extend(index_by_issuer[issuer])
        labels = [rows[p][target] for p in positions]
        for name, payload in scores.items():
            value = auc([payload["scores"][p] for p in positions], labels)
            if value is not None:
                samples[name].append(value)
        primary = auc([scores[PRIMARY_MODEL]["scores"][p] for p in positions], labels)
        baseline = auc([scores[BASELINE_MODEL]["scores"][p] for p in positions], labels)
        if primary is not None and baseline is not None:
            delta_samples.append(primary - baseline)
    intervals = {name: _percentile_interval(values) for name, values in samples.items()}
    intervals["delta_" + PRIMARY_MODEL + "_minus_" + BASELINE_MODEL] = \
        _percentile_interval(delta_samples)
    return {"draws": draws, "clusters": len(issuers), "ci95": intervals}


def _percentile_interval(values: Sequence[float]) -> dict[str, Any]:
    if not values:
        return {"n": 0}
    ordered = sorted(values)
    count = len(ordered)

    def quantile(q: float) -> float:
        index = min(count - 1, max(0, int(round(q * (count - 1)))))
        return float(ordered[index])

    return {"n": count, "mean": float(sum(ordered) / count),
            "p025": quantile(0.025), "p50": quantile(0.5), "p975": quantile(0.975)}


# --------------------------------------------------------------------------- #
# permutation test: circular shift of the label series within each issuer
# --------------------------------------------------------------------------- #
def permute_delta_auc(rows: Sequence[dict[str, Any]],
                      scores: dict[str, dict[str, Any]], target: str,
                      permutations: int, seed: int) -> dict[str, Any]:
    """Null distribution of AUC(primary) and of delta-AUC.

    A circular shift inside each issuer keeps that issuer's exact label
    multiset and its serial ordering, and destroys only the alignment between
    prose features and the following events. That is the right null for "does
    the prose carry information about what happens next".
    """
    issuers = sorted({row["issuer"] for row in rows})
    positions_by_issuer: dict[str, list[int]] = {}
    for position, row in enumerate(rows):
        positions_by_issuer.setdefault(row["issuer"], []).append(position)
    observed_labels = [row[target] for row in rows]
    observed_primary = auc(scores[PRIMARY_MODEL]["scores"], observed_labels)
    observed_baseline = auc(scores[BASELINE_MODEL]["scores"], observed_labels)
    observed_delta = (observed_primary - observed_baseline
                      if observed_primary is not None and observed_baseline is not None
                      else None)
    rng = random.Random(seed)
    primary_null: list[float] = []
    delta_null: list[float] = []
    for _ in range(permutations):
        shifted = list(observed_labels)
        for issuer in issuers:
            positions = positions_by_issuer[issuer]
            if len(positions) < 2:
                continue
            offset = rng.randrange(len(positions))
            rotated = [observed_labels[positions[(i + offset) % len(positions)]]
                       for i in range(len(positions))]
            for position, label in zip(positions, rotated):
                shifted[position] = label
        value = auc(scores[PRIMARY_MODEL]["scores"], shifted)
        baseline = auc(scores[BASELINE_MODEL]["scores"], shifted)
        if value is not None:
            primary_null.append(value)
        if value is not None and baseline is not None:
            delta_null.append(value - baseline)

    def tail(values: Sequence[float], observed: float | None, two_sided: bool) -> float | None:
        if observed is None or not values:
            return None
        if two_sided:
            extreme = sum(1 for v in values if abs(v) >= abs(observed))
        else:
            extreme = sum(1 for v in values if v >= observed)
        return (extreme + 1) / (len(values) + 1)

    return {
        "permutations": permutations,
        "scheme": "circular shift of the label series within each issuer",
        "observed_auc_primary": observed_primary,
        "observed_auc_baseline": observed_baseline,
        "observed_delta_auc": observed_delta,
        "null_auc_primary": _percentile_interval(primary_null),
        "null_delta_auc": _percentile_interval(delta_null),
        "p_auc_primary_two_sided": tail(primary_null, observed_primary, True),
        "p_auc_primary_greater": tail(primary_null, observed_primary, False),
        "p_delta_auc_two_sided": tail(delta_null, observed_delta, True),
        "p_delta_auc_greater": tail(delta_null, observed_delta, False),
        "null_auc_primary_values_head": sorted(primary_null)[:5],
        "null_auc_primary_values_tail": sorted(primary_null)[-5:],
        # Full draws are kept so the figure script can redraw the null without
        # re-running the test (2000 short floats, ~20 KB).
        "null_delta_auc_draws": [round(value, 6) for value in delta_null],
    }


# --------------------------------------------------------------------------- #
# negative and positive controls
# --------------------------------------------------------------------------- #
def label_transplant_auc(rows: Sequence[dict[str, Any]],
                         scores: dict[str, dict[str, Any]],
                         target: str) -> dict[str, Any]:
    """Negative control: pair each firm's scores with a different firm's labels.

    If the machinery is measuring a firm-general artefact (size, filing habit)
    rather than an event relation, the transplant would still score above 0.5.
    """
    issuers = sorted({row["issuer"] for row in rows})
    if len(issuers) < 2:
        return {"auc": None, "note": "need at least two issuers"}
    successor = {issuers[i]: issuers[(i + 1) % len(issuers)] for i in range(len(issuers))}
    labels_by_issuer: dict[str, list[int]] = {}
    positions_by_issuer: dict[str, list[int]] = {}
    for position, row in enumerate(rows):
        labels_by_issuer.setdefault(row["issuer"], []).append(row[target])
        positions_by_issuer.setdefault(row["issuer"], []).append(position)
    cursor = {issuer: 0 for issuer in issuers}
    transplanted = [0] * len(rows)
    for position, row in enumerate(rows):
        donor = successor[row["issuer"]]
        donor_labels = labels_by_issuer[donor]
        transplanted[position] = donor_labels[cursor[row["issuer"]] % len(donor_labels)]
        cursor[row["issuer"]] += 1
    return {
        "auc": auc(scores[PRIMARY_MODEL]["scores"], transplanted),
        "prevalence": prevalence(transplanted),
        "scheme": "each issuer's scores paired with the next issuer's label series",
    }


def univariate_auc(rows: Sequence[dict[str, Any]], target: str) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for column in ("rd_per_1k", "tech_per_1k", "dev_per_1k", "words", "n_prior_events",
                   "is_earnings"):
        if not rows:
            continue
        result[column] = auc([float(row[column]) for row in rows], [row[target] for row in rows])
    return result


# --------------------------------------------------------------------------- #
# power
# --------------------------------------------------------------------------- #
def _phi(z: float) -> float:
    """Standard normal CDF."""
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


def hanley_mcneil_se(auc_value: float, n1: int, n0: int) -> float | None:
    if n1 < 2 or n0 < 2:
        return None
    q1 = auc_value / (2.0 - auc_value)
    q2 = 2.0 * auc_value * auc_value / (1.0 + auc_value)
    numerator = (auc_value * (1 - auc_value)
                 + (n1 - 1) * (q1 - auc_value ** 2)
                 + (n0 - 1) * (q2 - auc_value ** 2))
    return math.sqrt(numerator / (n1 * n0))


def power_curve(n1: int, n0: int, alpha: float = 0.05) -> dict[str, Any]:
    """Power to reject AUC=0.5 for a true AUC, plus the minimum detectable AUC."""
    z_crit = 1.959963985
    rows: list[dict[str, Any]] = []
    minimum = None
    for step in range(1, 50):
        alt = 0.5 + step * 0.01
        se = hanley_mcneil_se(alt, n1, n0)
        if se is None:
            break
        power = 1.0 - _phi(z_crit - (alt - 0.5) / se)
        rows.append({"auc": round(alt, 2), "se": round(se, 4), "power": round(power, 3)})
        if minimum is None and power >= 0.8:
            minimum = round(alt, 2)
    return {"n_positives": n1, "n_negatives": n0, "alpha": alpha,
            "min_detectable_auc_at_80pct_power": minimum, "curve": rows[:15]}


# --------------------------------------------------------------------------- #
# top level
# --------------------------------------------------------------------------- #
def _protocol_hash(path: Path) -> str | None:
    if not path.exists():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(artifacts_dir: Path, seed: int = 20261114, permutations: int = 2000,
        train_end: str = TRAIN_END_DEFAULT) -> int:
    dataset_path = artifacts_dir / "dataset.csv"
    if not dataset_path.exists():
        print("[experiment] missing dataset.csv - run build first")
        return 2
    rows = load_rows(dataset_path)
    train, test = split_rows(rows, train_end)
    print("[experiment] rows=%d train=%d test=%d (train_end=%s)"
          % (len(rows), len(train), len(test), train_end))
    if not train or not test:
        print("[experiment] empty split - stopping rather than reporting a number")
        return 2

    results: dict[str, Any] = {
        "study": "SCIENCE-001",
        "protocol_sha256": _protocol_hash(artifacts_dir.parent / "PROTOCOL.md"),
        "seed": seed,
        "train_end": train_end,
        "horizon_days": HORIZON_DAYS,
        "n_rows": len(rows),
        "n_train": len(train),
        "n_test": len(test),
        "train_period": [min(r["acceptance_utc"] for r in train),
                         max(r["acceptance_utc"] for r in train)],
        "test_period": [min(r["acceptance_utc"] for r in test),
                        max(r["acceptance_utc"] for r in test)],
        "prevalence": {
            "train": prevalence([row[TARGET] for row in train]),
            "test": prevalence([row[TARGET] for row in test]),
            "placebo_train": prevalence([row[PLACEBO_TARGET] for row in train]),
            "placebo_test": prevalence([row[PLACEBO_TARGET] for row in test]),
        },
        "per_issuer": _per_issuer(rows),
        "models": {},
        "permutation": {},
        "controls": {},
    }

    # -- primary outcome ---------------------------------------------------
    scores = score_models(train, test, TARGET)
    results["models"]["tech_event"] = evaluate(scores, test, TARGET)
    # Holdout predictions are published so every figure and every metric in the
    # paper can be recomputed from the committed artifact alone.
    results["holdout"] = {
        "issuer": [row["issuer"] for row in test],
        "accession": [row["accession"] for row in test],
        "acceptance_utc": [row["acceptance_utc"] for row in test],
        "label": [row[TARGET] for row in test],
        "label_placebo": [row[PLACEBO_TARGET] for row in test],
        "scores": {name: [round(value, 6) for value in payload["scores"]]
                   for name, payload in scores.items()},
    }
    results["permutation"]["tech_event"] = permute_delta_auc(test, scores, TARGET,
                                                             permutations, seed)
    results["controls"]["bootstrap"] = cluster_bootstrap(test, scores, TARGET,
                                                         draws=2000, seed=seed)
    results["controls"]["label_transplant"] = label_transplant_auc(test, scores, TARGET)
    results["controls"]["univariate_auc"] = univariate_auc(test, TARGET)
    results["controls"]["positive_control_any_8k"] = _positive_control(train, test)

    # -- placebo outcome (items 5.07) --------------------------------------
    placebo_scores = score_models(train, test, PLACEBO_TARGET)
    results["models"]["placebo"] = evaluate(placebo_scores, test, PLACEBO_TARGET)
    results["permutation"]["placebo"] = permute_delta_auc(test, placebo_scores,
                                                          PLACEBO_TARGET, max(200, permutations // 4),
                                                          seed + 1)

    # -- power --------------------------------------------------------------
    labels = [row[TARGET] for row in test]
    results["power"] = power_curve(sum(labels), len(labels) - sum(labels))

    # -- verdict ------------------------------------------------------------
    results["verdict"] = _verdict(results)
    (artifacts_dir / "experiment_results.json").write_text(
        json.dumps(results, indent=1, sort_keys=True), encoding="utf-8", newline="\n")
    _write_table(artifacts_dir / "experiment_table.csv", results)
    print("[experiment] AUC test: " + ", ".join(
        "%s=%.3f" % (name, payload["auc"] or float("nan"))
        for name, payload in results["models"]["tech_event"].items()))
    print("[experiment] delta AUC (B3-B2)=%.3f  p_two_sided=%s"
          % (results["permutation"]["tech_event"]["observed_delta_auc"] or 0.0,
             results["permutation"]["tech_event"]["p_delta_auc_two_sided"]))
    print("[experiment] verdict: %s" % results["verdict"]["status"])
    return 0


def _per_issuer(rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    grouped: dict[str, dict[str, Any]] = {}
    for row in rows:
        bucket = grouped.setdefault(row["issuer"], {"n": 0, "positives": 0,
                                                    "placebo_positives": 0,
                                                    "first": row["acceptance_utc"],
                                                    "last": row["acceptance_utc"]})
        bucket["n"] += 1
        bucket["positives"] += row[TARGET]
        bucket["placebo_positives"] += row[PLACEBO_TARGET]
        bucket["first"] = min(bucket["first"], row["acceptance_utc"])
        bucket["last"] = max(bucket["last"], row["acceptance_utc"])
    for bucket in grouped.values():
        bucket["prevalence"] = bucket["positives"] / bucket["n"] if bucket["n"] else None
    return dict(sorted(grouped.items()))


def _positive_control(train: Sequence[dict[str, Any]],
                      test: Sequence[dict[str, Any]]) -> dict[str, Any]:
    """Sanity check: activity should predict *some* forward 8-K. If not, the
    label machinery itself is broken and no negative result is interpretable."""
    scores = score_models(train, test, POSITIVE_CONTROL_TARGET)
    table = evaluate(scores, test, POSITIVE_CONTROL_TARGET)
    return {"target": POSITIVE_CONTROL_TARGET,
            "auc_by_model": {name: payload["auc"] for name, payload in table.items()},
            "prevalence_test": prevalence([row[POSITIVE_CONTROL_TARGET] for row in test])}


def _verdict(results: dict[str, Any]) -> dict[str, Any]:
    permutation = results["permutation"]["tech_event"]
    delta = permutation.get("observed_delta_auc")
    p_value = permutation.get("p_delta_auc_two_sided")
    auc_primary = permutation.get("observed_auc_primary")
    controls = results["controls"]
    transplant = controls.get("label_transplant", {}).get("auc")
    bootstrap_ci = controls.get("bootstrap", {}).get("ci95", {}).get(
        "delta_" + PRIMARY_MODEL + "_minus_" + BASELINE_MODEL, {})
    notes: list[str] = []
    status = "indeterminate"
    # The pre-registered decision rule is the permutation p-value. The
    # label-transplant control is a caveat attached to the verdict, never an
    # override of it: a weak-but-real relation and a firm-general artefact are
    # different failures and must not be collapsed into one label.
    if p_value is not None and delta is not None:
        if p_value < 0.05 and delta > 0:
            status = "exploratory_positive"
            notes.append("delta AUC above the circular-shift null at alpha=0.05 "
                         "(exploratory only)")
        elif p_value < 0.05 and delta <= 0:
            status = "exploratory_negative"
            notes.append("delta AUC significantly below zero at alpha=0.05")
        else:
            status = "null"
            notes.append("delta AUC is inside the circular-shift null band")
    if (auc_primary is not None and transplant is not None and auc_primary > 0.55
            and auc_primary <= transplant + 0.05):
        notes.append("caveat: the apparently positive primary AUC is not materially "
                     "above the cross-firm transplant control, so a firm-general "
                     "artefact cannot be excluded")
    if bootstrap_ci and bootstrap_ci.get("n"):
        notes.append("cluster-bootstrap 95%% CI for delta AUC: [%.3f, %.3f]"
                     % (bootstrap_ci["p025"], bootstrap_ci["p975"]))
    if not bootstrap_ci or bootstrap_ci.get("n", 0) < 100:
        notes.append("bootstrap interval unstable: few clusters")
    return {"status": status, "notes": notes,
            "exploratory": True,
            "confirmatory": False,
            "claim_limit": ("a point estimate from one chronological split of one "
                            "small issuer panel; not a prediction capability claim")}


def _write_table(path: Path, results: dict[str, Any]) -> None:
    lines = ["outcome,model,auc,brier,log_loss,n,positives"]
    for outcome, table in results["models"].items():
        for name, payload in table.items():
            lines.append("%s,%s,%s,%s,%s,%d,%d" % (
                outcome, name,
                _fmt(payload["auc"]), _fmt(payload["brier"]), _fmt(payload["log_loss"]),
                payload["n"], payload["positives"]))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")


def _fmt(value: Any) -> str:
    return "" if value is None else ("%.6f" % value)
