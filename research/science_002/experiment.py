"""Models, uncertainty and pre-registered tests for SCIENCE-002.

Three questions, three estimators - they are never conflated:

F1  **within-firm prediction** (primary). A pooled logistic regression is
    dominated by between-firm composition: SCIENCE-001 found firm identity alone
    reached AUC 0.72 while content features reached 0.47. So the primary family
    is estimated with **firm fixed effects**: a dummy per firm is added to the
    design matrix and the slope coefficients are therefore identified only from
    within-firm variation. Because a firm dummy is constant inside a firm, it
    cannot affect a within-firm ranking, so the firm-stratified AUC of such a
    model measures exactly the within-firm signal. Statistic: the firm-stratified
    AUC (equal weight per firm, single-class firms excluded) and its difference
    between B3 and B2.

F2  **pooled discrimination** - descriptive only. Real numbers are reported, but
    a pooled AUC is never the basis of an early-signal claim, since firm identity
    produces it.

F3  **cross-firm generalisation** - leave-one-firm-out with the *pooled* models
    (no fixed effects): fit on the train years of the other firms, score the held
    out firm's holdout months, average per-firm AUC. Firm effects are deliberately
    absent here: they cannot be estimated for an unseen firm.

Uncertainty is clustered by firm everywhere. The primary null is a within-firm
label permutation, an exact conditional randomisation test: under H0 every
within-firm stratified AUC has expectation 0.5 by construction, so no centring
correction is needed. A circular-shift variant is reported because it preserves
serial correlation (the design used in SCIENCE-001).
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import Any, Callable, Mapping, Sequence

from .panel import MODEL_FEATURES

LAMBDA = 1.0
IRLS_ITERS = 30

#: firm-conditional variants reuse the same feature blocks
CONDITIONAL_OF = {"B0c": "B0", "B1c": "B1", "B2c": "B2", "B3c": "B3", "B4c": "B4"}


def sigmoid(z: float) -> float:
    if z >= 0:
        e = math.exp(-z)
        return 1.0 / (1.0 + e)
    e = math.exp(z)
    return e / (1.0 + e)


def solve(matrix: list[list[float]], vector: list[float]) -> list[float]:
    n = len(vector)
    a = [row[:] + [vector[i]] for i, row in enumerate(matrix)]
    for col in range(n):
        pivot = max(range(col, n), key=lambda r: abs(a[r][col]))
        if abs(a[pivot][col]) < 1e-12:
            continue
        a[col], a[pivot] = a[pivot], a[col]
        div = a[col][col]
        for j in range(col, n + 1):
            a[col][j] /= div
        for r in range(n):
            if r == col:
                continue
            factor = a[r][col]
            if factor == 0.0:
                continue
            for j in range(col, n + 1):
                a[r][j] -= factor * a[col][j]
    return [a[i][n] for i in range(n)]


@dataclass
class RidgeLogit:
    features: tuple[str, ...]
    firm_effects: bool = False
    means: list[float] = field(default_factory=list)
    sds: list[float] = field(default_factory=list)
    beta: list[float] = field(default_factory=list)
    firms: list[str] = field(default_factory=list)
    base_rate: float = 0.5
    lambda_: float = LAMBDA

    def _design(self, rows: Sequence[Any]) -> list[list[float]]:
        d = len(self.features)
        index = {firm: i for i, firm in enumerate(self.firms)}
        out = []
        for row in rows:
            if d:
                row_features = [(float(row.features[name]) - self.means[j]) / self.sds[j]
                                for j, name in enumerate(self.features)]
            else:
                row_features = []
            if self.firm_effects:
                dummies = [0.0] * max(0, len(self.firms) - 1)
                pos = index.get(row.key, -1)
                if pos > 0:
                    dummies[pos - 1] = 1.0
                row_features = row_features + dummies
            out.append([1.0] + row_features)
        return out

    def fit(self, rows: Sequence[Any]) -> "RidgeLogit":
        y = [float(row.label) for row in rows]
        self.base_rate = sum(y) / max(1, len(y))
        if self.firm_effects:
            self.firms = sorted({row.key for row in rows})
        if self.features:
            d = len(self.features)
            self.means = [sum(float(r.features[name]) for r in rows) / len(rows)
                          for name in self.features]
            self.sds = []
            for j, name in enumerate(self.features):
                var = sum((float(r.features[name]) - self.means[j]) ** 2 for r in rows) / max(1, len(rows) - 1)
                self.sds.append(math.sqrt(var) if var > 1e-12 else 1.0)
        x = self._design(rows)
        k = len(x[0])
        # sparse view: the intercept is always present, a dummy row has one extra
        sparse = [[(j, v) for j, v in enumerate(xi) if v != 0.0] for xi in x]
        beta = [0.0] * k
        penalty = [0.0] + [self.lambda_] * (k - 1)
        for _ in range(IRLS_ITERS):
            grad = [0.0] * k
            hess = [[0.0] * k for _ in range(k)]
            for entries, yi in zip(sparse, y):
                eta = 0.0
                for j, v in entries:
                    eta += beta[j] * v
                p = sigmoid(eta)
                w = max(p * (1.0 - p), 1e-6)
                resid = yi - p
                for a, va in entries:
                    grad[a] += resid * va
                    wva = w * va
                    ha = hess[a]
                    for b, vb in entries:
                        if b >= a:
                            ha[b] += wva * vb
            for a in range(k):
                grad[a] -= penalty[a] * beta[a]
                for b in range(a):
                    hess[a][b] = hess[b][a]
                hess[a][a] += penalty[a]
            step = solve(hess, grad)
            beta = [b + s for b, s in zip(beta, step)]
            if max(abs(s) for s in step) < 1e-9:
                break
        self.beta = beta
        return self

    def score(self, rows: Sequence[Any]) -> list[float]:
        if not self.features and not self.firm_effects:
            return [self.base_rate] * len(rows)
        out = []
        for x in self._design(rows):
            out.append(sigmoid(sum(b * v for b, v in zip(self.beta, x))))
        return out


def auc(labels: Sequence[int], scores: Sequence[float]) -> float | None:
    pos = [s for y, s in zip(labels, scores) if y == 1]
    neg = [s for y, s in zip(labels, scores) if y == 0]
    if not pos or not neg:
        return None
    order = sorted(range(len(scores)), key=lambda i: scores[i])
    ranks = [0.0] * len(scores)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and scores[order[j + 1]] == scores[order[i]]:
            j += 1
        avg = (i + j) / 2.0 + 1.0
        for k in range(i, j + 1):
            ranks[order[k]] = avg
        i = j + 1
    pos_rank = sum(r for r, y in zip(ranks, labels) if y == 1)
    n1, n0 = len(pos), len(neg)
    return (pos_rank - n1 * (n1 + 1) / 2.0) / (n1 * n0)


def group_index(groups: Sequence[str]) -> dict[str, list[int]]:
    out: dict[str, list[int]] = {}
    for i, group in enumerate(groups):
        out.setdefault(group, []).append(i)
    return out


def stratified_auc(labels: Sequence[int], scores: Sequence[float],
                   groups: Sequence[str],
                   index: Mapping[str, Sequence[int]] | None = None) -> dict[str, Any]:
    by_group = index if index is not None else group_index(groups)
    per: dict[str, float] = {}
    for group, idx in by_group.items():
        value = auc([labels[i] for i in idx], [scores[i] for i in idx])
        if value is not None:
            per[group] = value
    if not per:
        return {"value": None, "n_firms": 0, "per_firm": {}}
    return {"value": sum(per.values()) / len(per), "n_firms": len(per), "per_firm": per}


def paired_delta(labels: Sequence[int], scores: Mapping[str, Sequence[float]],
                 groups: Sequence[str], a: str, b: str) -> float | None:
    sa = stratified_auc(labels, scores[a], groups)
    sb = stratified_auc(labels, scores[b], groups)
    common = set(sa["per_firm"]) & set(sb["per_firm"])
    if not common:
        return None
    return sum(sa["per_firm"][f] - sb["per_firm"][f] for f in common) / len(common)


def cluster_bootstrap(labels: Sequence[int], scores_by_model: Mapping[str, Sequence[float]],
                      groups: Sequence[str],
                      statistic: Callable[[Sequence[int], Mapping[str, Sequence[float]], Sequence[str]], float | None],
                      draws: int = 2000, seed: int = 20261114) -> dict[str, Any]:
    rng = random.Random(seed)
    firm_ids = sorted(set(groups))
    index_by_firm = {f: [i for i, g in enumerate(groups) if g == f] for f in firm_ids}
    out: list[float] = []
    for _ in range(draws):
        picked = [rng.choice(firm_ids) for _ in firm_ids]
        idx: list[int] = []
        g: list[str] = []
        for j, firm in enumerate(picked):
            rows = index_by_firm[firm]
            idx.extend(rows)
            g.extend([f"{firm}#{j}"] * len(rows))
        value = statistic([labels[i] for i in idx],
                          {k: [v[i] for i in idx] for k, v in scores_by_model.items()}, g)
        if value is not None and math.isfinite(value):
            out.append(value)
    out.sort()
    if not out:
        return {"n": 0}
    def pct(q: float) -> float:
        return out[min(len(out) - 1, max(0, int(round(q * (len(out) - 1)))))]
    return {"n": len(out), "lo": pct(0.025), "hi": pct(0.975), "median": pct(0.5),
            "mean": sum(out) / len(out)}


def _summarise(values: Sequence[float]) -> dict[str, Any]:
    out = sorted(values)
    if not out:
        return {"n": 0}
    def pct(q: float) -> float:
        return out[min(len(out) - 1, max(0, int(round(q * (len(out) - 1)))))]
    return {"n": len(out), "lo": pct(0.025), "hi": pct(0.975), "median": pct(0.5),
            "mean": sum(out) / len(out)}


def _sd(values: Sequence[float]) -> float | None:
    if len(values) < 2:
        return None
    mean = sum(values) / len(values)
    return math.sqrt(sum((v - mean) ** 2 for v in values) / (len(values) - 1))


def _quantile(values: Sequence[float], q: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, max(0, int(round(q * (len(ordered) - 1)))))]


def fit_scores(models: Sequence[tuple[str, str, bool]], train: Sequence[Any],
               eval_rows: Sequence[Any]) -> dict[str, list[float]]:
    """models = [(label, feature_block, firm_effects), ...]"""
    out: dict[str, list[float]] = {}
    for label, block, fe in models:
        model = RidgeLogit(MODEL_FEATURES[block], firm_effects=fe).fit(train)
        out[label] = model.score(eval_rows)
    return out


POOLED_MODELS = tuple((name, name, False) for name in ("B0", "B1", "B2", "B3"))
COND_MODELS = tuple((name + "c", name, True) for name in ("B0", "B1", "B2", "B3"))


def run(panel_result: Any, seed: int = 20261114, n_perm: int = 2000,
        n_boot: int = 2000, n_placebo: int = 100,
        placebo_features: bool = True) -> dict[str, Any]:
    rng = random.Random(seed)
    rows = panel_result.complete_case(("B0", "B1", "B2", "B3"))
    train = [r for r in rows if r.split == "train"]
    hold = [r for r in rows if r.split == "holdout"]
    labels = [r.label for r in hold]
    groups = [r.key for r in hold]

    pooled = fit_scores(POOLED_MODELS, train, hold)
    cond = fit_scores(COND_MODELS, train, hold)

    result: dict[str, Any] = {
        "meta": {
            "n_rows_complete_case": len(rows), "n_train": len(train),
            "n_holdout": len(hold), "n_firms_holdout": len(set(groups)),
            "prevalence_holdout": sum(labels) / len(labels) if labels else None,
            "prevalence_train": sum(r.label for r in train) / len(train) if train else None,
            "features": {name: list(MODEL_FEATURES[name]) for name in MODEL_FEATURES},
            "seed": seed, "n_perm": n_perm, "n_boot": n_boot, "lambda": LAMBDA,
            "estimator_primary": "ridge logistic with firm fixed effects",
            "statistic_primary": "firm-stratified AUC difference B3c - B2c",
        },
        "pooled": {}, "pooled_bootstrap": {}, "conditional": {}, "per_firm": {},
    }
    for name, key in (("B0", "B0"), ("B1", "B1"), ("B2", "B2"), ("B3", "B3")):
        result["pooled"][key] = auc(labels, pooled[key])
    for name in ("B1c", "B2c", "B3c"):
        strat = stratified_auc(labels, cond[name], groups)
        result["conditional"][name] = {"value": strat["value"], "n_firms": strat["n_firms"]}
        result["per_firm"][name] = strat["per_firm"]
    result["conditional"]["B0c"] = {"value": 0.5, "n_firms": len(set(groups)),
                                    "note": "constant within firm by construction"}

    observed = paired_delta(labels, cond, groups, "B3c", "B2c")
    result["primary"] = {
        "delta_stratified_auc_B3c_minus_B2c": observed,
        "delta_stratified_auc_B3c_minus_B1c": paired_delta(labels, cond, groups, "B3c", "B1c"),
        "pooled_delta_B3_minus_B2": None if (result["pooled"]["B3"] is None or result["pooled"]["B2"] is None)
        else result["pooled"]["B3"] - result["pooled"]["B2"],
    }

    by_firm: dict[str, list[int]] = {}
    for i, row_ in enumerate(hold):
        by_firm.setdefault(row_.key, []).append(i)

    def perm_test(shift_only: bool) -> dict[str, Any]:
        diffs: list[float] = []
        for _ in range(n_perm):
            perm = list(labels)
            for firm, idx in by_firm.items():
                series = [labels[i] for i in idx]
                if shift_only and len(series) > 1:
                    shift = rng.randrange(1, len(series))
                    series = series[shift:] + series[:shift]
                else:
                    rng.shuffle(series)
                for k, i in enumerate(idx):
                    perm[i] = series[k]
            value = paired_delta(perm, cond, groups, "B3c", "B2c")
            if value is not None:
                diffs.append(value)
        obs = observed if observed is not None else 0.0
        return {
            "n_used": len(diffs),
            "p_two_sided": (1 + sum(1 for v in diffs if abs(v) >= abs(obs))) / (1 + len(diffs)),
            "p_positive_tail": (1 + sum(1 for v in diffs if v >= obs)) / (1 + len(diffs)),
            "null_mean": sum(diffs) / len(diffs) if diffs else None,
            "null_sd": _sd(diffs),
            "null_q025": _quantile(diffs, 0.025),
            "null_q975": _quantile(diffs, 0.975),
        }

    result["permutation"] = perm_test(shift_only=False)
    result["permutation_circular"] = perm_test(shift_only=True)

    firm_ids = sorted({r.key for r in hold})
    index_by_firm = {f: [i for i, r in enumerate(hold) if r.key == f] for f in firm_ids}

    def draw_index(rng_: random.Random) -> tuple[list[int], list[str]]:
        picked = [rng_.choice(firm_ids) for _ in firm_ids]
        idx: list[int] = []
        g: list[str] = []
        for j, firm in enumerate(picked):
            rows_ = index_by_firm[firm]
            idx.extend(rows_)
            g.extend([firm + "#" + str(j)] * len(rows_))
        return idx, g

    def auc_on(idx: Sequence[int], scores_subset: Sequence[float]) -> float | None:
        return auc([labels[i] for i in idx], [scores_subset[i] for i in idx])

    def strat_on(idx: Sequence[int], scores_subset: Sequence[float]) -> float | None:
        local = group_index([groups[i] for i in idx])
        return stratified_auc([labels[i] for i in idx],
                              [scores_subset[i] for i in idx], [], index=local)["value"]

    def delta_on(idx: Sequence[int], a_key: str, b_key: str,
                 table: Mapping[str, Sequence[float]]) -> float | None:
        local = group_index([groups[i] for i in idx])
        lab = [labels[i] for i in idx]
        sa = stratified_auc(lab, [table[a_key][i] for i in idx], [], index=local)["per_firm"]
        sb = stratified_auc(lab, [table[b_key][i] for i in idx], [], index=local)["per_firm"]
        common_ = set(sa) & set(sb)
        if not common_:
            return None
        return sum(sa[f] - sb[f] for f in common_) / len(common_)

    def pooled_delta_on(idx: Sequence[int]) -> float | None:
        lab = [labels[i] for i in idx]
        a_ = auc(lab, [pooled["B3"][i] for i in idx])
        b_ = auc(lab, [pooled["B2"][i] for i in idx])
        if a_ is None or b_ is None:
            return None
        return a_ - b_

    rng_boot = random.Random(seed)
    collected: dict[str, list[float]] = {
        "pooled_B1": [], "pooled_B2": [], "pooled_B3": [],
        "B1c": [], "B2c": [], "B3c": [],
        "delta_B3c_minus_B2c": [], "delta_B3c_minus_B1c": [],
        "pooled_delta_B3_minus_B2": [],
    }
    for _ in range(n_boot):
        idx, _g = draw_index(rng_boot)
        for name in ("B1", "B2", "B3"):
            value = auc_on(idx, pooled[name])
            if value is not None:
                collected["pooled_" + name].append(value)
        for name in ("B1c", "B2c", "B3c"):
            value = strat_on(idx, cond[name])
            if value is not None:
                collected[name].append(value)
        for key, a_key, b_key in (("delta_B3c_minus_B2c", "B3c", "B2c"),
                                  ("delta_B3c_minus_B1c", "B3c", "B1c")):
            value = delta_on(idx, a_key, b_key, cond)
            if value is not None:
                collected[key].append(value)
        value = pooled_delta_on(idx)
        if value is not None:
            collected["pooled_delta_B3_minus_B2"].append(value)

    result["pooled_bootstrap"] = {}
    for name in ("B1", "B2", "B3"):
        result["pooled_bootstrap"][name] = _summarise(collected["pooled_" + name])
    result["bootstrap"] = {}
    for name in ("B1c", "B2c", "B3c"):
        result["bootstrap"][name] = _summarise(collected[name])
    for key in ("delta_B3c_minus_B2c", "delta_B3c_minus_B1c"):
        result["bootstrap"][key] = _summarise(collected[key])
    result["bootstrap_pooled_delta_B3_minus_B2"] = _summarise(
        collected["pooled_delta_B3_minus_B2"])

    by_firm: dict[str, list[int]] = {}
    for i, row_ in enumerate(hold):
        by_firm.setdefault(row_.key, []).append(i)

    # ---- cross-firm generalisation (pooled models, no fixed effects) ------
    lofo: dict[str, Any] = {}
    for name in ("B2", "B3"):
        per: dict[str, float] = {}
        for firm in sorted({r.key for r in hold}):
            fit_rows = [r for r in train if r.key != firm]
            eval_rows = [r for r in hold if r.key == firm]
            if len(eval_rows) < 2 or len({r.label for r in eval_rows}) < 2:
                continue
            model = RidgeLogit(MODEL_FEATURES[name]).fit(fit_rows)
            value = auc([r.label for r in eval_rows], model.score(eval_rows))
            if value is not None:
                per[firm] = value
        lofo[name] = {"mean_auc": sum(per.values()) / len(per) if per else None,
                      "n_firms": len(per), "per_firm": per}
    common = set(lofo["B2"]["per_firm"]) & set(lofo["B3"]["per_firm"])
    lofo["delta_B3_minus_B2"] = {
        "mean": (sum(lofo["B3"]["per_firm"][f] - lofo["B2"]["per_firm"][f] for f in common)
                 / len(common)) if common else None,
        "n_firms": len(common),
        "n_firms_positive": sum(1 for f in common
                                if lofo["B3"]["per_firm"][f] > lofo["B2"]["per_firm"][f]),
    }
    result["lofo"] = lofo

    result["controls"] = {
        "history_conditional": result["conditional"]["B1c"],
        "activity_conditional": result["conditional"]["B2c"],
    }
    result["controls"].update(_placebo_outcome(train, hold, models_cond=True))
    if placebo_features:
        result["controls"].update(_placebo_features(rows, train, hold, labels, groups,
                                                    seed, n_placebo))
    else:
        result["controls"]["placebo_features"] = {"skipped": "not requested"}
    result["controls"]["label_transplant_pooled"] = _label_transplant(labels, pooled, groups)

    result["secondary_B4"] = _secondary_b4(train, hold, labels, groups)
    result["power"] = {
        "min_detectable_auc_hanley": _min_detectable_auc(sum(labels), len(labels) - sum(labels)),
        "permutation_sd": result["permutation"]["null_sd"],
        "mde_delta_80pct": 2.8 * (result["permutation"]["null_sd"] or 0.0),
        "n_firms_used_stratified": result["conditional"]["B2c"]["n_firms"],
    }
    result["verdict"] = decide(result)
    return result


def _min_detectable_auc(n_pos: int, n_neg: int) -> float | None:
    if n_pos < 2 or n_neg < 2:
        return None
    se = math.sqrt((0.5 + (n_pos - 1) * 0.5 + (n_neg - 1) * 0.5) / (n_pos * n_neg))
    return 0.5 + 2.8 * se


def _placebo_outcome(train: Sequence[Any], hold: Sequence[Any],
                     models_cond: bool = True) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for label_name, tag in (("label_507", "placebo_outcome_507"),
                            ("label_any8k", "positive_control_any8k")):
        labels = [int(getattr(r, label_name)) for r in hold]
        if len(set(labels)) < 2:
            out[tag] = {"skipped": "single class"}
            continue
        groups = [r.key for r in hold]
        if models_cond:
            scores = fit_scores((("B2c", "B2", True), ("B3c", "B3", True)), train, hold)
        else:
            scores = fit_scores((("B2", "B2", False), ("B3", "B3", False)), train, hold)
        key2, key3 = ("B2c", "B3c") if models_cond else ("B2", "B3")
        out[tag] = {
            "prevalence": sum(labels) / len(labels),
            "stratified_B2": stratified_auc(labels, scores[key2], groups)["value"],
            "stratified_B3": stratified_auc(labels, scores[key3], groups)["value"],
            "delta": paired_delta(labels, scores, groups, key3, key2),
            "n_firms": stratified_auc(labels, scores[key3], groups)["n_firms"],
            "pooled_B2": auc(labels, scores[key2]),
            "pooled_B3": auc(labels, scores[key3]),
        }
    return out


def _placebo_features(rows: Sequence[Any], train: Sequence[Any], hold: Sequence[Any],
                      labels: Sequence[int], groups: Sequence[str], seed: int,
                      n_placebo: int) -> dict[str, Any]:
    rd_cols = [c for c in MODEL_FEATURES["B3"] if c.startswith("rd_")]
    if not rd_cols:
        return {"placebo_features": {"skipped": "no rd columns"}}
    rng = random.Random(seed + 7)
    by_firm: dict[str, list[Any]] = {}
    for row in rows:
        by_firm.setdefault(row.key, []).append(row)
    cond = (("B2c", "B2", True), ("B3c", "B3", True))
    observed = paired_delta(labels, fit_scores(cond, train, hold), groups, "B3c", "B2c")
    draws: list[float] = []
    for _ in range(n_placebo):
        saved: list[tuple[Any, dict[str, float]]] = []
        for firm, group_rows in by_firm.items():
            values = [[r.features.get(c) for c in rd_cols] for r in group_rows]
            order = list(range(len(group_rows)))
            rng.shuffle(order)
            for target, source in enumerate(order):
                row = group_rows[target]
                original = {}
                for c, v in zip(rd_cols, values[source]):
                    original[c] = row.features.get(c)
                    if v is None:
                        row.features.pop(c, None)
                    else:
                        row.features[c] = v
                saved.append((row, original))
        value = paired_delta(labels, fit_scores(cond, train, hold), groups, "B3c", "B2c")
        for row, original in saved:
            for c, v in original.items():
                if v is None:
                    row.features.pop(c, None)
                else:
                    row.features[c] = v
        if value is not None:
            draws.append(value)
    ge = sum(1 for v in draws if abs(v) >= abs(observed)) if observed is not None else None
    return {"placebo_features": {
        "n": len(draws), "observed_delta": observed,
        "null_mean": sum(draws) / len(draws) if draws else None,
        "null_q025": _quantile(draws, 0.025),
        "null_q975": _quantile(draws, 0.975),
        "p_two_sided": ((1 + ge) / (1 + len(draws))) if ge is not None and draws else None,
    }}


def _label_transplant(labels: Sequence[int], scores: Mapping[str, Sequence[float]],
                      groups: Sequence[str]) -> dict[str, Any]:
    firms = sorted(set(groups))
    if len(firms) < 3:
        return {"skipped": "too few firms"}
    mapping = {firm: firms[(i + 1) % len(firms)] for i, firm in enumerate(firms)}
    by_firm: dict[str, list[int]] = {}
    for i, g in enumerate(groups):
        by_firm.setdefault(g, []).append(i)
    new_labels = list(labels)
    for firm in firms:
        donor = mapping[firm]
        donor_labels = [labels[i] for i in by_firm[donor]]
        if len(donor_labels) != len(by_firm[firm]):
            continue
        for k, i in enumerate(by_firm[firm]):
            new_labels[i] = donor_labels[k]
    keys = sorted(scores)
    return {"pooled": {k: auc(new_labels, scores[k]) for k in keys},
            "stratified": {k: stratified_auc(new_labels, scores[k], groups)["value"]
                           for k in keys}}


def decide(result: Mapping[str, Any]) -> dict[str, Any]:
    meta = result["meta"]
    checks = {
        "min_holdout_rows": meta["n_holdout"] >= 300,
        "prevalence_band": 0.05 <= (meta["prevalence_holdout"] or 0) <= 0.95,
        "min_firms_stratified": result["conditional"]["B2c"]["n_firms"] >= 20,
        "positive_control_firm_history": (result["pooled"]["B1"] or 0) >= 0.60,
        "positive_control_activity_any8k": (result["controls"].get("positive_control_any8k", {})
                                            .get("pooled_B2") or 0) >= 0.55,
    }
    if not all(checks.values()):
        return {"verdict": "NO-GO", "checks": checks,
                "reason": "feasibility or control check failed"}
    primary = result["primary"]["delta_stratified_auc_B3c_minus_B2c"] or 0.0
    p = result["permutation"]["p_two_sided"]
    ci = result["bootstrap"]["delta_B3c_minus_B2c"]
    lofo = result["lofo"]["delta_B3_minus_B2"]["mean"] or 0.0
    placebo_p = (result["controls"].get("placebo_features") or {}).get("p_two_sided")
    go = (primary > 0 and p < 0.05 and ci.get("lo") is not None and ci["lo"] > 0
          and lofo > 0)
    effect = {"delta": primary, "p": p, "ci": [ci.get("lo"), ci.get("hi")],
              "lofo_delta": lofo, "placebo_p": placebo_p}
    if go:
        return {"verdict": "GO", "checks": checks,
                "reason": "pre-registered criteria met", "effect": effect}
    return {"verdict": "NULL", "checks": checks,
            "reason": "experiment valid; no incremental signal meets the pre-registered threshold",
            "effect": effect}

def _secondary_b4(train: Sequence[Any], hold: Sequence[Any], labels: Sequence[int],
                  groups: Sequence[str]) -> dict[str, Any]:
    """Declared secondary: does the longer-horizon R&D block add on top of B3?"""
    rows = train + hold
    complete = [r for r in rows if all(
        isinstance(r.features.get(name), (int, float))
        for name in MODEL_FEATURES["B4"])]
    train_b4 = [r for r in complete if r.split == "train"]
    hold_b4 = [r for r in complete if r.split == "holdout"]
    if len(hold_b4) < 100:
        return {"skipped": "insufficient complete B4 rows", "n": len(hold_b4)}
    scores = fit_scores((("B3c", "B3", True), ("B4c", "B4", True)), train_b4, hold_b4)
    lab = [r.label for r in hold_b4]
    grp = [r.key for r in hold_b4]
    return {
        "n_holdout": len(hold_b4),
        "stratified_B3c": stratified_auc(lab, scores["B3c"], grp)["value"],
        "stratified_B4c": stratified_auc(lab, scores["B4c"], grp)["value"],
        "delta_B4c_minus_B3c": paired_delta(lab, scores, grp, "B4c", "B3c"),
    }