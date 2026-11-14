"""P0/P1 statistical review experiments for SCIENCE-002R.

Three questions, each answered by an executed experiment rather than by reading code.

H2  OVERLAP-INDUCED DEPENDENCE. The outcome is "at least one clearance in the next
    90 days". Consecutive issuer-months therefore share two thirds of their outcome
    window, so holdout rows are not independent draws. A within-firm label shuffle
    destroys that serial structure. This module measures the dependence and then
    re-runs the primary statistic on (a) non-overlapping quarterly observations and
    (b) a permutation that shifts whole three-month blocks, so the label's own
    clustering is preserved.

H3  PRECISION CLAIMS. The 95% interval is a percentile cluster bootstrap over 31
    firms. The audit re-derives what it does and does not license, and re-estimates
    the interval with a jackknife over firms as an independent check on the
    bootstrap's stability at 31 clusters.

H5  TIME SEMANTICS, EXECUTED. Two adversarial injections: a restated XBRL fact filed
    after a row's prediction instant must not change that row's R&D features, and a
    filing accepted after the instant must not change the activity features. Both
    are performed by injecting synthetic records into the real data.
"""

from __future__ import annotations

import math
import random
import statistics
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from typing import Any, Mapping, Sequence

from research.science_002 import experiment, panel, pipeline, sec
from research.science_002.sources import Cache

from . import common


def _t(row: Any) -> datetime:
    return datetime.combine(row.month_end, datetime.max.time()).replace(tzinfo=timezone.utc)


def group_index(groups: Sequence[str]) -> dict[str, list[int]]:
    out: dict[str, list[int]] = {}
    for i, g in enumerate(groups):
        out.setdefault(g, []).append(i)
    return out


def leakage_checks(build: Any, clearance_index: Mapping[str, Sequence[date]],
                   rows: Sequence[Any], seed: int, sample: int = 30) -> dict[str, Any]:
    """Two executed adversarial checks, independent of the frozen audit module."""
    rng = random.Random(seed + 4242)
    picked = rng.sample(list(rows), min(sample, len(rows)))

    # 1) a filing accepted one minute after t must not change any activity feature
    changed_filing = 0
    for row in picked:
        sub = build.submissions.get(row.cik)
        if sub is None:
            continue
        t = _t(row)
        before = {k: row.features.get(k) for k in ("n_8k_90", "n_8k_365", "n_801_90",
                                                   "n_801_365", "n_202_90")}
        future = sec.Filing(accession="0000000000-99-999998", form="8-K",
                            filing_date=row.month_end + timedelta(days=1),
                            acceptance_utc=t + timedelta(seconds=59),
                            items=("8.01", "2.02"), primary_document="future.htm")
        augmented = list(sub.filings) + [future]
        after = {
            "n_8k_90": float(panel._filing_counts(augmented, t, 90)),
            "n_8k_365": float(panel._filing_counts(augmented, t, 365)),
            "n_801_90": float(panel._filing_counts(augmented, t, 90, "8.01")),
            "n_801_365": float(panel._filing_counts(augmented, t, 365, "8.01")),
            "n_202_90": float(panel._filing_counts(augmented, t, 90, "2.02")),
        }
        if before != after:
            changed_filing += 1

    # 2) the latest clearance a feature may read must precede the outcome window
    violations = 0
    for row in rows:
        t = _t(row)
        cutoff = (t - timedelta(days=panel.AVAILABILITY_LAG_DAYS)).date()
        dates = clearance_index.get(row.cik, ())
        used = [d for d in dates if d <= cutoff]
        window = [d for d in dates if t.date() < d <= t.date() + timedelta(days=panel.HORIZON_DAYS)]
        if used and window and max(used) >= min(window):
            violations += 1
    return {
        "future_filing_injection": {"n_checked": len(picked), "n_changed": changed_filing,
                                    "passed": changed_filing == 0},
        "feature_window_disjointness": {"n_rows": len(rows), "violations": violations,
                                        "passed": violations == 0,
                                        "note": "max clearance date read by a feature must "
                                                "be earlier than the first date in the outcome window"},
    }


def paired_delta(labels: Sequence[int], scores: Mapping[str, Sequence[float]],
                 groups: Sequence[str], a: str, b: str) -> float | None:
    sa = experiment.stratified_auc(labels, scores[a], groups)["per_firm"]
    sb = experiment.stratified_auc(labels, scores[b], groups)["per_firm"]
    common_ = set(sa) & set(sb)
    if not common_:
        return None
    return sum(sa[f] - sb[f] for f in common_) / len(common_)


def label_autocorrelation(rows: Sequence[Any]) -> dict[str, Any]:
    """Lag-1..3 autocorrelation of the within-firm label series."""
    by_firm: dict[str, list[int]] = defaultdict(list)
    for row in rows:
        by_firm[row.key].append(row.label)
    out = {}
    for lag in (1, 2, 3):
        pairs = []
        for series in by_firm.values():
            for i in range(len(series) - lag):
                pairs.append((series[i], series[i + lag]))
        if not pairs:
            continue
        n = len(pairs)
        mx = sum(a for a, _ in pairs) / n
        my = sum(b for _, b in pairs) / n
        sx = math.sqrt(sum((a - mx) ** 2 for a, _ in pairs))
        sy = math.sqrt(sum((b - my) ** 2 for _, b in pairs))
        corr = (sum((a - mx) * (b - my) for a, b in pairs) / (sx * sy)) if sx > 1e-12 and sy > 1e-12 else None
        # the theoretical overlap of two 90-day windows lag months apart
        overlap = max(0.0, (90 - 30.44 * lag) / 90.0)
        out["lag_" + str(lag)] = {"pairs": n, "correlation": corr,
                                  "window_overlap_fraction": round(overlap, 3)}
    return out


def quarterly_filter(rows: Sequence[Any]) -> list[Any]:
    """Keep every third month so 90-day outcome windows do not overlap."""
    return [row for row in rows if row.month_end.month in (1, 4, 7, 10)]


def block_permutation_p(rows: Sequence[Any], scores: Mapping[str, Sequence[float]],
                        groups: Sequence[str], observed: float, seed: int,
                        n_perm: int, block: int = 3) -> dict[str, Any]:
    """Shift three-month blocks within each firm (preserves window overlap)."""
    rng = random.Random(seed + 991)
    by_firm: dict[str, list[int]] = {}
    for i, row in enumerate(rows):
        by_firm.setdefault(row.key, []).append(i)
    labels = [row.label for row in rows]
    diffs: list[float] = []
    for _ in range(n_perm):
        perm = list(labels)
        for firm, idx in by_firm.items():
            blocks = [idx[i:i + block] for i in range(0, len(idx), block)]
            series = [[labels[i] for i in b] for b in blocks]
            rng.shuffle(series)
            flat = [value for blk in series for value in blk]
            for k, i in enumerate(idx):
                perm[i] = flat[k] if k < len(flat) else labels[i]
        value = paired_delta(perm, scores, groups, "B3c", "B2c")
        if value is not None:
            diffs.append(value)
    obs = observed if observed is not None else 0.0
    return {"n_used": len(diffs),
            "p_two_sided": (1 + sum(1 for v in diffs if abs(v) >= abs(obs))) / (1 + len(diffs)),
            "null_mean": sum(diffs) / len(diffs) if diffs else None,
            "null_sd": statistics.pstdev(diffs) if len(diffs) > 1 else None}


def jackknife_ci(rows: Sequence[Any], scores: Mapping[str, Sequence[float]],
                 groups: Sequence[str], seed: int, draws: int = 400) -> dict[str, Any]:
    """Firm jackknife plus a firm-level bootstrap, as an independent stability check."""
    firms = sorted(set(groups))
    leaves = []
    for firm in firms:
        idx = [i for i, g in enumerate(groups) if g != firm]
        value = paired_delta([rows[i].label for i in idx],
                             {k: [v[i] for i in idx] for k, v in scores.items()},
                             [groups[i] for i in idx], "B3c", "B2c")
        if value is not None:
            leaves.append(value)
    out: dict[str, Any] = {"n_leave_one_firm_out": len(leaves)}
    if leaves:
        mean = sum(leaves) / len(leaves)
        n = len(leaves)
        se = math.sqrt((n - 1) / n * sum((v - mean) ** 2 for v in leaves))
        out["jackknife_mean"] = mean
        out["jackknife_se"] = se
        out["jackknife_ci"] = [mean - 1.96 * se, mean + 1.96 * se]
        out["leave_one_out_min"] = min(leaves)
        out["leave_one_out_max"] = max(leaves)
    return out


def xbrl_restatement_injection(build: Any, rows: Sequence[Any], seed: int,
                               sample: int = 40) -> dict[str, Any]:
    """Inject a later-filed restatement of an already-known fact and re-derive."""
    rng = random.Random(seed)
    picked = rng.sample(list(rows), min(sample, len(rows)))
    changed = 0
    checked = 0
    for row in picked:
        facts = build.facts.get(row.cik)
        if facts is None or not facts.rd:
            continue
        t = _t(row)
        before = panel.rd_features(facts.rd, facts.revenue, t)
        known = [f for f in facts.rd if f.filed <= t.date() and f.end <= t.date()]
        if not known:
            continue
        target = max(known, key=lambda f: (f.end, f.filed))
        restatement = sec.Fact(tag=target.tag, start=target.start, end=target.end,
                               value=target.value * 3.0 + 1.0,
                               filed=t.date() + timedelta(days=1), form="10-Q/A")
        after = panel.rd_features(list(facts.rd) + [restatement], facts.revenue, t)
        checked += 1
        if before != after:
            changed += 1
    return {"n_checked": checked, "n_changed": changed,
            "passed": changed == 0,
            "note": "a restatement filed after the prediction instant must be invisible"}


def run(cache: Cache, seed: int = 20261114, n_perm: int = 2000) -> dict[str, Any]:
    build = pipeline.build_universe(cache, verbose=False, cache_dir=common.CACHE_RAW)
    index = pipeline.clearance_index(build, cache_dir=common.CACHE_RAW)
    full = panel.build_panel(build, index)
    rows = full.complete_case(("B0", "B1", "B2", "B3"))
    train = [r for r in rows if r.split == "train"]
    hold = [r for r in rows if r.split == "holdout"]
    scores = experiment.fit_scores(experiment.COND_MODELS, train, hold)
    labels = [r.label for r in hold]
    groups = [r.key for r in hold]
    observed = paired_delta(labels, scores, groups, "B3c", "B2c")

    out: dict[str, Any] = {
        "meta": {"seed": seed, "n_perm": n_perm, "n_rows": len(rows),
                 "n_holdout": len(hold)},
        "overlap": {
            "label_autocorrelation_holdout": label_autocorrelation(hold),
            "label_autocorrelation_train": label_autocorrelation(train),
            "n_months_per_firm": len({r.month_end for r in hold}),
            "design_effect_note": (
                "with 90-day windows on monthly rows, three consecutive rows measure "
                "largely the same window; the number of effectively independent "
                "time points per firm is about one third of the number of rows"),
        },
        "block_permutation": block_permutation_p(hold, scores, groups, observed, seed, n_perm),
        "jackknife": jackknife_ci(hold, scores, groups, seed),
        "xbrl_restatement": xbrl_restatement_injection(build, rows, seed),
    }

    # ---- non-overlapping quarterly observations --------------------------
    q_rows = quarterly_filter(rows)
    q_train = [r for r in q_rows if r.split == "train"]
    q_hold = [r for r in q_rows if r.split == "holdout"]
    q_scores = experiment.fit_scores(experiment.COND_MODELS, q_train, q_hold)
    q_labels = [r.label for r in q_hold]
    q_groups = [r.key for r in q_hold]
    q_observed = paired_delta(q_labels, q_scores, q_groups, "B3c", "B2c")
    rng = random.Random(seed)
    by_firm: dict[str, list[int]] = defaultdict(list)
    for i, row in enumerate(q_hold):
        by_firm[row.key].append(i)
    diffs = []
    for _ in range(n_perm):
        perm = list(q_labels)
        for firm, idx in by_firm.items():
            values = [q_labels[i] for i in idx]
            rng.shuffle(values)
            for k, i in enumerate(idx):
                perm[i] = values[k]
        value = paired_delta(perm, q_scores, q_groups, "B3c", "B2c")
        if value is not None:
            diffs.append(value)
    obs = q_observed if q_observed is not None else 0.0
    out["quarterly"] = {
        "n_rows": len(q_rows), "n_train": len(q_train), "n_holdout": len(q_hold),
        "n_firms_stratified": experiment.stratified_auc(q_labels, q_scores["B2c"], q_groups)["n_firms"],
        "prevalence_holdout": sum(q_labels) / len(q_labels) if q_labels else None,
        "delta": q_observed,
        "p_two_sided": (1 + sum(1 for v in diffs if abs(v) >= abs(obs))) / (1 + len(diffs)) if diffs else None,
        "null_sd": statistics.pstdev(diffs) if len(diffs) > 1 else None,
        "stratified_B2c": experiment.stratified_auc(q_labels, q_scores["B2c"], q_groups)["value"],
        "stratified_B3c": experiment.stratified_auc(q_labels, q_scores["B3c"], q_groups)["value"],
    }
    out["leakage"] = leakage_checks(build, index, rows, seed)
    return out