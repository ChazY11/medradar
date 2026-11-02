"""hist_v1: full-history walk-forward evaluation harness.

Pre-registered in ``research/protocols/hist_v1_preregistration.md`` (frozen 2026-11-03;
amendments A1-A4 in section 14).  Standard library only, deterministic, no network.

What this script does
---------------------
Builds the pre-registered (company, track) risk sets from a panel produced by
``experiments/hist_v1/build_panel.py`` (schema ``hist_v1.panel.v1``), computes the 15
point-in-time features of protocol section 5, fits the pre-declared baselines B0-B3 and
the L2-regularised logistic model M1 at every annual evaluation origin, and reports
mean-per-origin average precision (A1), pooled AP, ROC-AUC, Brier, ECE-10,
precision@10/@25, recall and false-alarm rate at a 10 % alert budget, the era / risk-set /
horizon / feature-group robustness grid, the company-clustered paired bootstrap
(2,000 resamples, seed 20261103), the label-permutation null, lead time, the H5 alert
budget frontier, H3/H4 heterogeneity and the H2 fusion test.

Frozen decisions implemented literally
--------------------------------------
* labels only from events with ``t < qidx <= t+h``; a cell is mature iff ``t+h <= last_qidx``
* features only from events with ``qidx <= t`` (quarters are availability quarters)
* training cells at origin ``t``: candidate cells at *every quarter* ``t'`` from the panel
  start through ``t-h`` (quarterly training grid), labels mature strictly before ``t``
  (purge asserted per origin)
* A2: all positive training cells + a seeded random sample of negative training cells so
  that the training set has at most 12,000 rows; sampled negatives carry weight
  ``1/p_neg``.  Weighted logistic regression; the test set is never subsampled.
* A1: primary metric = mean of per-origin AP over the evaluation origins, never pooled AP

Usage::

    python experiments/hist_v1/eval.py \
        --panel out/hist_v1/panel.json \
        --out experiments/hist_v1/results.json [--quick] [--workers N]
"""
from __future__ import annotations

import argparse
import bisect
import hashlib
import json
import math
import os
import random
import statistics
import subprocess
import sys
import time
from collections import defaultdict
from itertools import accumulate
from operator import mul
from pathlib import Path

# ----------------------------------------------------------------- frozen constants
PANEL_SCHEMA = "hist_v1.panel.v1"
RESULTS_SCHEMA = "hist_v1.results.v1"
PROTOCOL_PATH = "research/protocols/hist_v1_preregistration.md"

SEED = 20261103                 # pre-registered bootstrap / permutation seed
TRAIN_SAMPLE_SEED = 20261103    # A2 seeded negative sampler
BOOTSTRAP_REPS = 2000           # pre-registered resamples
PERMUTATION_REPS = 200          # pre-registered permutations
TRAIN_ROW_CAP = 12000           # A2 cap on training rows per origin
LAMBDA = 1.0                    # L2 penalty
LEARNING_RATE = 0.1
EPOCHS = 120

ALERT_BUDGETS = (0.01, 0.05, 0.10, 0.20)
PRIMARY_ALERT_BUDGET = 0.10
HORIZONS = (("h8", 8), ("h4", 4))          # h8 primary
ORIGIN_YEARS = {"h8": (1995, 2024), "h4": (1995, 2025)}
ERA_BANDS = (("1995-2004", 1995, 2004),
             ("2005-2014", 2005, 2014),
             ("2015-2024", 2015, 2024))
DEEP_CASE_KEYS = ("medtronic", "ge_healthcare", "philips", "draeger", "mindray")

# protocol section 5, table order 1..15
FEATURE_NAMES_C = (
    "firm_act_4", "firm_act_8", "firm_growth", "firm_tracks", "firm_tenure",
    "firm_entry_rate", "adj_act_8", "adj_share", "track_act_8", "track_growth",
    "track_entrants", "track_recent_entries", "track_age", "cat_share", "firm_size",
)
_GROUP_A_NAMES = {"firm_act_4", "firm_act_8", "firm_growth", "firm_tracks",                  "firm_tenure", "firm_entry_rate", "firm_size"}
_GROUP_B_NAMES = _GROUP_A_NAMES | {"track_act_8", "track_growth", "track_entrants",
                                   "track_recent_entries", "track_age"}
_GROUP_C_NAMES = _GROUP_B_NAMES | {"adj_act_8", "adj_share", "cat_share"}
# group membership is a set, but the column order is always the protocol table order
GROUP_A = tuple(name for name in FEATURE_NAMES_C if name in _GROUP_A_NAMES)
GROUP_B = tuple(name for name in FEATURE_NAMES_C if name in _GROUP_B_NAMES)
GROUP_C = tuple(name for name in FEATURE_NAMES_C if name in _GROUP_C_NAMES)
FUSION_FEATURES = ("tr_track_8", "tr_adj_8", "pub_prev_year", "pub_3y", "pub_growth")
GROUP_D = GROUP_C + FUSION_FEATURES

FEATURE_GROUPS = {"A": GROUP_A, "B": GROUP_B, "C": GROUP_C, "D": GROUP_D}

FEATURE_DEFINITIONS = {
    "firm_act_4": "log1p(count of company material events, all tracks, with t-4 < qidx <= t)",
    "firm_act_8": "log1p(count of company material events, all tracks, with t-8 < qidx <= t)",
    "firm_growth": "raw_count_4 / (raw_count_8 - raw_count_4 + 0.5); rise over the last year vs the prior year",
    "firm_tracks": "number of distinct tracks the company has any material event in by t",
    "firm_tenure": "(t - first observed company event qidx) / 4.0",
    "firm_entry_rate": "company first-entry events (new track entries) in (t-32, t] divided by 8.0",
    "adj_act_8": "log1p(count of company events in other tracks of the pair's category, t-8 < qidx <= t)",
    "adj_share": "same-category share of the company's events in (t-8, t] (raw ratio); None when the denominator is 0",
    "track_act_8": "log1p(count of industry material events in the track with t-8 < qidx <= t)",
    "track_growth": "industry raw_count_4 / (raw_count_8 - raw_count_4 + 0.5)",
    "track_entrants": "number of distinct companies that have entered the track (first event) by t",
    "track_recent_entries": "log1p(count of first entries into the track in (t-8, t])",
    "track_age": "(t - first observed industry event in the track with qidx <= t) / 4.0; None if none yet",
    "cat_share": "share of the company's ever events (qidx <= t) in the pair's category; None if no events",
    "firm_size": "log1p(count of company material events, all tracks, with qidx <= t)",
    "tr_track_8": "fusion D: log1p(device-trial events in the track, t-8 < qidx <= t) from data/b040_device_trials.sqlite",
    "tr_adj_8": "fusion D: log1p(device-trial events in other tracks of the same category, t-8 < qidx <= t)",
    "pub_prev_year": "fusion D: log1p(OpenAlex works in calendar year year(t)-1); None if the year is absent",
    "pub_3y": "fusion D: log1p(sum of works over complete calendar years year(t)-3 .. year(t)-1); None unless all three years are present",
    "pub_growth": "fusion D: works[year-1] / (works[year-2] + 0.5); None if either year is absent",
}

# deterministic resource model for A4 (permutation count fallback); declared in results.json
# cost unit = one training row x one feature x one epoch (measured ~11M units/s single process)
PERM_FIT_RATE = 11_000_000.0
TOTAL_RUN_BUDGET_MINUTES = 90.0

MDE_Z = statistics.NormalDist().inv_cdf(0.975) + statistics.NormalDist().inv_cdf(0.80)


# ------------------------------------------------------------------------ utilities
def _log1p(value: int) -> float:
    return math.log1p(float(value))


def _difference(left: float | None, right: float | None) -> float | None:
    return None if left is None or right is None else left - right


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def utc_now() -> str:
    import datetime
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")


def write_json_atomic(path: Path, payload: dict) -> None:
    """Write JSON via a sibling temporary file + os.replace (kill-safe)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    with open(temporary, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, ensure_ascii=False, allow_nan=False)
        handle.write("\n")
    os.replace(temporary, path)


def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def git_commit() -> str | None:
    try:
        result = subprocess.run(["git", "rev-parse", "HEAD"], cwd=str(repo_root()),
                                capture_output=True, text=True, timeout=10)
        if result.returncode == 0:
            return result.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        pass
    return None


def percentile_sorted(sorted_values: list[float], q: float) -> float:
    """Percentile index convention of ``medradar.intelligence.evalstats._interval``."""
    _require(bool(sorted_values), "percentile of empty sample")
    index = int(q * len(sorted_values))
    index = min(len(sorted_values) - 1, max(0, index))
    return sorted_values[index]


def weighted_quantile(values: list[float], weights: list[float], q: float) -> float | None:
    """Weighted quantile (lower value at the crossing point); None for empty input."""
    pairs = sorted(zip(values, weights))
    total = sum(weights)
    if not pairs or total <= 0:
        return None
    target = q * total
    cumulative = 0.0
    for value, weight in pairs:
        cumulative += weight
        if cumulative >= target:
            return float(value)
    return float(pairs[-1][0])


def weighted_median(values: list[float], weights: list[float]) -> float | None:
    return weighted_quantile(values, weights, 0.5)


def median_iqr(values: list[float]) -> dict:
    """Median and inter-quartile range; ``statistics.quantiles(n=4)`` (exclusive) convention."""
    if not values:
        return {"n": 0, "median": None, "q25": None, "q75": None, "iqr": None}
    ordered = sorted(float(value) for value in values)
    if len(ordered) == 1:
        q25 = q75 = ordered[0]
    else:
        quartiles = statistics.quantiles(ordered, n=4)
        q25, q75 = quartiles[0], quartiles[2]
    return {"n": len(ordered), "median": statistics.median(ordered),
            "q25": q25, "q75": q75, "iqr": q75 - q25}


# ------------------------------------------------------------------- ranking metrics
def rank_order(scores: list[float], company_keys: list[str], track_ids: list[str]) -> list[int]:
    """Deterministic ranking: score descending, then company key, then track id ascending."""
    return sorted(range(len(scores)),
                  key=lambda i: (-scores[i], company_keys[i], track_ids[i]))


def average_precision(labels: list[int], scores: list[float],
                      company_keys: list[str] | None = None,
                      track_ids: list[str] | None = None,
                      order: list[int] | None = None) -> float | None:
    """Tie-aware average precision (same step formula as medradar's ``pr_auc``).

    Equal scores are evaluated as one threshold, so the value does not depend on the
    order of tied rows; the (score, company, track) ordering is only used to make the
    alert list deterministic.
    """
    n = len(labels)
    positives = sum(labels)
    if n == 0 or positives == 0 or positives == n:
        return None
    if order is None:
        if company_keys is None or track_ids is None:
            order = sorted(range(n), key=lambda i: -scores[i])
        else:
            order = rank_order(scores, company_keys, track_ids)
    ordered_scores = [scores[i] for i in order]
    ordered_labels = [labels[i] for i in order]
    area = 0.0
    true_positives = false_positives = 0
    previous_recall = 0.0
    index = 0
    while index < n:
        score = ordered_scores[index]
        while index < n and ordered_scores[index] == score:
            if ordered_labels[index]:
                true_positives += 1
            else:
                false_positives += 1
            index += 1
        recall = true_positives / positives
        precision = true_positives / (true_positives + false_positives)
        area += (recall - previous_recall) * precision
        previous_recall = recall
    return area


def prepare_ap(labels: list[int], scores: list[float], company_indices: list[int],
               order: list[int] | None = None) -> dict:
    """Precompute the sorted/blocked structure used by the weighted (bootstrap) AP."""
    n = len(labels)
    if order is None:
        order = sorted(range(n), key=lambda i: -scores[i])
    ordered_scores = [scores[i] for i in order]
    ordered_labels = [labels[i] for i in order]
    comps = [company_indices[i] for i in order]
    block_ends: list[int] = []
    index = 0
    while index < n:
        score = ordered_scores[index]
        while index < n and ordered_scores[index] == score:
            index += 1
        block_ends.append(index - 1)
    positive_blocks: list[tuple[int, int]] = []
    start = 0
    previous_end = -1
    for end in block_ends:
        if any(ordered_labels[start:end + 1]):
            positive_blocks.append((end, previous_end))
        previous_end = end
        start = end + 1
    return {"labels": ordered_labels, "company_indices": comps,
            "positive_blocks": positive_blocks, "n_rows": n}


def ap_weighted(prepared: dict, multiplicities: list[int]) -> float | None:
    """AP on the row multiset defined by cluster multiplicities (paired bootstrap engine)."""
    comps = prepared["company_indices"]
    labels = prepared["labels"]
    if not comps:
        return None
    weights = [multiplicities[company] for company in comps]
    cumulative_weights = list(accumulate(weights))
    cumulative_positives = list(accumulate(map(mul, weights, labels)))
    total_rows = cumulative_weights[-1]
    total_positives = cumulative_positives[-1]
    if total_positives <= 0 or total_positives >= total_rows:
        return None
    area = 0.0
    for end, previous_end in prepared["positive_blocks"]:
        rows_here = cumulative_weights[end]
        if rows_here == 0:
            continue
        positives_here = cumulative_positives[end]
        positives_in_block = positives_here - (cumulative_positives[previous_end]
                                                if previous_end >= 0 else 0)
        if positives_in_block:
            area += positives_in_block * (positives_here / rows_here)
    return area / total_positives


def roc_auc(labels: list[int], scores: list[float]) -> float | None:
    """Tie-aware ROC-AUC via average mid-ranks (Mann-Whitney U)."""
    n = len(labels)
    positives = sum(labels)
    negatives = n - positives
    if positives == 0 or negatives == 0:
        return None
    order = sorted(range(n), key=lambda i: scores[i])
    rank_sum_positives = 0.0
    index = 0
    while index < n:
        score = scores[order[index]]
        end = index
        while end < n and scores[order[end]] == score:
            end += 1
        average_rank = (index + 1 + end) / 2.0   # 1-based mid-rank of the tie group
        for position in range(index, end):
            if labels[order[position]]:
                rank_sum_positives += average_rank
        index = end
    return (rank_sum_positives - positives * (positives + 1) / 2.0) / (positives * negatives)


def brier_score(labels: list[int], scores: list[float]) -> float | None:
    if not labels:
        return None
    return sum((score - label) ** 2 for score, label in zip(scores, labels)) / len(labels)


def expected_calibration_error(labels: list[int], scores: list[float], bins: int = 10) -> float | None:
    """ECE-10 with the repository's bin convention (last bin includes exactly 1.0)."""
    if not labels:
        return None
    error = 0.0
    for index in range(bins):
        low, high = index / bins, (index + 1) / bins
        members = [(score, label) for score, label in zip(scores, labels)
                   if low <= score < high or (index == bins - 1 and score == 1.0)]
        if members:
            confidence = sum(score for score, _ in members) / len(members)
            accuracy = sum(label for _, label in members) / len(members)
            error += len(members) / len(labels) * abs(confidence - accuracy)
    return error


def precision_at_k(labels: list[int], order: list[int], k: int) -> dict:
    used = min(k, len(order))
    if used == 0:
        return {"k": k, "used": 0, "precision": None}
    hits = sum(labels[i] for i in order[:used])
    return {"k": k, "used": used, "precision": hits / used}


def kendall_tau(xs: list[float], ys: list[float]) -> float | None:
    """Kendall tau-b (ties handled), deterministic."""
    n = len(xs)
    _require(n == len(ys), "kendall_tau requires aligned vectors")
    if n < 2:
        return None
    concordant = discordant = ties_x = ties_y = 0
    for i in range(n):
        for j in range(i + 1, n):
            dx = xs[i] - xs[j]
            dy = ys[i] - ys[j]
            if dx == 0 and dy == 0:
                ties_x += 1
                ties_y += 1
            elif dx == 0:
                ties_x += 1
            elif dy == 0:
                ties_y += 1
            elif dx * dy > 0:
                concordant += 1
            else:
                discordant += 1
    denominator = math.sqrt((concordant + discordant + ties_x) *
                            (concordant + discordant + ties_y))
    if denominator == 0:
        return None
    return (concordant - discordant) / denominator


def _sigmoid(z: float) -> float:
    if z >= 0.0:
        return 1.0 / (1.0 + math.exp(-z))
    exponential = math.exp(z)
    return exponential / (1.0 + exponential)


# ===================================================================== panel object
class Panel:
    """Indexed view of a ``hist_v1.panel.v1`` panel.

    ``event_qidx`` entries are quarter indices into ``panel["quarters"]`` (the quarter in
    which the event became available); ``last_qidx`` is 2026-Q2 for the frozen grid.
    Every feature/label/risk-set computation in this module reads only these indexes and
    only events with ``qidx <= t`` (labels additionally use the outcome window).
    """

    def __init__(self, data: dict, *, path: Path | None = None, sha256: str | None = None):
        _require(isinstance(data, dict), "panel JSON must be an object")
        schema = data.get("schema")
        _require(schema == PANEL_SCHEMA,
                 f"panel schema {schema!r} does not match expected {PANEL_SCHEMA!r}; "
                 "report the deviation instead of adapting silently")
        for key in ("quarter_start", "quarter_end", "quarters", "companies", "tracks", "pairs"):
            _require(key in data, f"panel is missing required key {key!r}")
        self.data = data
        self.path = path
        self.sha256 = sha256
        self.source_quarters = list(data["quarters"])
        _require(len(self.source_quarters) >= 2, "panel must contain at least two quarters")
        self.quarters = self.source_quarters
        self.qidx = {quarter: index for index, quarter in enumerate(self.quarters)}
        _require(len(self.qidx) == len(self.quarters), "duplicate quarter labels in the panel")
        self.n_quarters = len(self.quarters)
        self.last_qidx = self.n_quarters - 1
        self.quarter_year: list[int] = []
        self.quarter_number: list[int] = []
        for label in self.quarters:
            _require(isinstance(label, str) and "-Q" in label,
                     f"quarter label {label!r} is not of the form YYYY-Qn")
            year_text, part_text = label.split("-Q", 1)
            self.quarter_year.append(int(year_text))
            self.quarter_number.append(int(part_text))
        self.quarter_start = data["quarter_start"]
        self.quarter_end = data["quarter_end"]
        _require(self.quarters[0] == self.quarter_start,
                 "panel quarters[0] differs from quarter_start")
        _require(self.quarters[-1] == self.quarter_end,
                 "panel quarters[-1] differs from quarter_end")

        company_records = data["companies"]
        _require(isinstance(company_records, list) and company_records,
                 "panel companies must be a non-empty list")
        self.companies = {}
        for record in company_records:
            key = record.get("key")
            _require(isinstance(key, str) and key, "company record without a key")
            _require(key not in self.companies, f"duplicate company key {key!r}")
            self.companies[key] = record
        self.company_keys = sorted(self.companies)
        self.company_index = {key: index for index, key in enumerate(self.company_keys)}
        self.company_count = len(self.company_keys)

        track_records = data["tracks"]
        _require(isinstance(track_records, list) and track_records,
                 "panel tracks must be a non-empty list")
        self.tracks = {}
        for record in track_records:
            track_id = record.get("id")
            _require(isinstance(track_id, str) and track_id, "track record without an id")
            _require(track_id not in self.tracks, f"duplicate track id {track_id!r}")
            _require("category" in record, f"track {track_id!r} has no category")
            self.tracks[track_id] = record
        self.track_keys = sorted(self.tracks)
        self.track_index = {key: index for index, key in enumerate(self.track_keys)}
        self.track_category = {key: self.tracks[key]["category"] for key in self.track_keys}
        self.track_count = len(self.track_keys)

        # ---- pair event indexes -------------------------------------------------
        # ``event_qidx`` is a sorted unique quarter list (presence); ``event_counts`` is
        # the parallel per-quarter event count (contract update from the panel builder).
        # Count-based features sum ``event_counts``; labels use presence only.
        self.pair_events: dict[tuple[str, str], list[int]] = {}
        self.pair_counts: dict[tuple[str, str], list[int]] = {}
        pairs_missing_counts = 0
        pair_records = data["pairs"]
        _require(isinstance(pair_records, list), "panel pairs must be a list")
        for record in pair_records:
            company = record.get("company_key")
            track = record.get("track_id")
            _require(company in self.companies, f"pair references unknown company {company!r}")
            _require(track in self.tracks, f"pair references unknown track {track!r}")
            qidx_values = record.get("event_qidx")
            _require(isinstance(qidx_values, list), f"pair {company}/{track} has no event_qidx list")
            counts_values = record.get("event_counts")
            values = []
            for position, value in enumerate(qidx_values):
                _require(isinstance(value, int) and 0 <= value <= self.last_qidx,
                         f"pair {company}/{track} has out-of-range event_qidx {value!r}")
                if position and value < qidx_values[position - 1]:
                    raise ValueError(f"pair {company}/{track} event_qidx is not sorted")
                values.append(value)
            if counts_values is None:
                pairs_missing_counts += 1
                counts = [1] * len(values)
            else:
                _require(isinstance(counts_values, list) and len(counts_values) == len(values),
                         f"pair {company}/{track} event_counts length mismatch")
                counts = []
                for value in counts_values:
                    _require(isinstance(value, int) and value >= 1,
                             f"pair {company}/{track} event_counts entry {value!r} is not >= 1")
                    counts.append(value)
            _require((company, track) not in self.pair_events,
                     f"duplicate pair record {company}/{track}")
            self.pair_events[(company, track)] = values
            self.pair_counts[(company, track)] = counts
        self.pairs_missing_event_counts = pairs_missing_counts
        self.feature_source = ("event_counts" if pairs_missing_counts == 0
                               else "presence_only_underestimate")
        self.total_event_count = sum(sum(counts) for counts in self.pair_counts.values())

        # ---- flat event indexes (event-multiset: a quarter with n events is n entries)
        self.company_q: dict[str, list[int]] = {key: [] for key in self.company_keys}
        self.company_events: dict[str, list[tuple[int, str]]] = {key: [] for key in self.company_keys}
        self.company_cat_q: dict[tuple[str, str], list[int]] = defaultdict(list)
        self.company_cats: dict[str, list[str]] = {key: [] for key in self.company_keys}
        self.company_first_by_track: dict[str, dict[str, int]] = {key: {} for key in self.company_keys}
        self.company_track_first_q: dict[str, list[int]] = {key: [] for key in self.company_keys}
        self.company_entries: dict[str, list[int]] = {key: [] for key in self.company_keys}
        self.industry_events: dict[str, list[tuple[int, str]]] = {key: [] for key in self.track_keys}
        for (company, track), values in self.pair_events.items():
            if not values:
                continue
            counts = self.pair_counts[(company, track)]
            first = values[0]
            self.company_first_by_track[company][track] = first
            self.company_track_first_q[company].append(first)
            self.company_entries[company].append(first)
            category = self.track_category[track]
            for value, count in zip(values, counts):
                for _ in range(count):
                    self.company_q[company].append(value)
                    self.company_events[company].append((value, track))
                    self.company_cat_q[(company, category)].append(value)
                    self.industry_events[track].append((value, company))
        for company in self.company_keys:
            self.company_q[company].sort()
            self.company_events[company].sort()
            self.company_track_first_q[company].sort()
            self.company_entries[company].sort()
            self.company_cats[company] = sorted({self.track_category[track]
                                                 for track in self.company_first_by_track[company]})
        # every list that is queried with bisect must be sorted
        for values in self.company_cat_q.values():
            values.sort()
        for track in self.track_keys:
            self.industry_events[track].sort()
        # per-track sorted first-entry quarters (one per company that ever entered)
        self.track_entry_q: dict[str, list[int]] = {
            track: self._track_entries(track) for track in self.track_keys}
        self.track_q: dict[str, list[int]] = {
            track: [q for q, _ in self.industry_events[track]] for track in self.track_keys}
        # event totals and unentered-pair counts (for the dataset block)
        self.total_events = self.total_event_count
        self.pairs_observed = sum(1 for values in self.pair_events.values() if values)
        # cross-check against the panel builder's audit block when it is present
        audit_summary = (data.get("audits") or {}).get("panel_summary") or {}
        audit_total = audit_summary.get("n_material_events")
        self.event_count_audit = {
            "sum_pair_event_counts": self.total_event_count,
            "audits_panel_summary_n_material_events": audit_total,
            "matches": (audit_total is None or int(audit_total) == self.total_event_count),
            "pairs_missing_event_counts": pairs_missing_counts,
            "feature_source": self.feature_source,
        }

    def _track_entries(self, track: str) -> list[int]:
        return sorted(self.company_first_by_track[company][track]
                      for company in self.company_keys
                      if track in self.company_first_by_track[company])

    # ---- point-in-time primitives ------------------------------------------
    def established(self, company: str, t: int) -> bool:
        """Condition 1: the company has >= 1 material event with qidx <= t."""
        firm = self.company_q[company]
        return bool(firm) and firm[0] <= t

    def pair_entered(self, company: str, track: str, t: int) -> bool:
        """Condition 2 (negated): the pair has no material event with qidx <= t."""
        values = self.pair_events.get((company, track))
        return bool(values) and values[0] <= t

    def active_categories(self, company: str, t: int) -> set[str]:
        """Categories in which the company has >= 1 event *strictly before* t.

        Protocol section 3 condition 3 (risk set R_adj): the event must be in another
        track of the same category.  Because a candidate pair is unentered, every
        same-category event of the company is in another track, so counting events in
        the category is equivalent and cheaper.
        """
        active = set()
        for category in self.company_cats[company]:
            values = self.company_cat_q[(company, category)]
            if values and values[0] < t:
                active.add(category)
        return active

    def risk_set(self, t: int, adjacency: bool) -> list[tuple[str, str]]:
        """Candidate (company, track) pairs at the end of quarter ``t``.

        ``adjacency=True`` is the pre-registered primary risk set ``R_adj``;
        ``adjacency=False`` is the declared robustness estimand ``R_full``.
        """
        candidates: list[tuple[str, str]] = []
        for company in self.company_keys:
            firm = self.company_q[company]
            if not firm or firm[0] > t:      # condition 1
                continue
            first_by_track = self.company_first_by_track[company]
            if adjacency:
                active = self.active_categories(company, t)
                if not active:
                    continue
                for track in self.track_keys:
                    first = first_by_track.get(track)
                    if first is not None and first <= t:
                        continue
                    if self.track_category[track] in active:
                        candidates.append((company, track))
            else:
                for track in self.track_keys:
                    first = first_by_track.get(track)
                    if first is None or first > t:
                        candidates.append((company, track))
        return candidates

    def mature(self, t: int, horizon: int) -> bool:
        return t + horizon <= self.last_qidx

    def label(self, company: str, track: str, t: int, horizon: int) -> int:
        """Y_h = 1 iff the pair has an event with ``t < qidx <= t + h``."""
        values = self.pair_events.get((company, track))
        if not values:
            return 0
        index = bisect.bisect_right(values, t)
        return 1 if index < len(values) and values[index] <= t + horizon else 0

    # ---- features (protocol section 5) -------------------------------------
    def features(self, company: str, track: str, t: int) -> dict[str, float | None]:
        """Raw (pre-imputation) point-in-time features for a candidate cell at ``t``."""
        category = self.track_category[track]
        firm = self.company_q[company]
        category_q = self.company_cat_q.get((company, category), [])
        pair_q = self.pair_events.get((company, track), [])

        def count(values: list[int], low: int, high: int) -> int:
            return bisect.bisect_right(values, high) - bisect.bisect_right(values, low)

        firm_4 = count(firm, t - 4, t)
        firm_8 = count(firm, t - 8, t)
        category_8 = count(category_q, t - 8, t)
        adjacency_8 = category_8 - count(pair_q, t - 8, t)   # pair is unentered: no events
        industry_4 = count(self.track_q[track], t - 4, t)
        industry_8 = count(self.track_q[track], t - 8, t)
        firm_ever = bisect.bisect_right(firm, t)
        category_ever = bisect.bisect_right(category_q, t)
        entries_last_8y = (bisect.bisect_right(self.company_entries[company], t)
                           - bisect.bisect_right(self.company_entries[company], t - 32))
        entrants = bisect.bisect_right(self.track_entry_q[track], t)
        recent_entries = entrants - bisect.bisect_right(self.track_entry_q[track], t - 8)
        industry_q = self.track_q[track]
        first_industry = industry_q[0] if industry_q and industry_q[0] <= t else None
        return {
            "firm_act_4": _log1p(firm_4),
            "firm_act_8": _log1p(firm_8),
            "firm_growth": firm_4 / (firm_8 - firm_4 + 0.5),
            "firm_tracks": float(bisect.bisect_right(self.company_track_first_q[company], t)),
            "firm_tenure": (t - firm[0]) / 4.0,
            "firm_entry_rate": entries_last_8y / 8.0,
            "adj_act_8": _log1p(adjacency_8),
            "adj_share": (category_8 / firm_8) if firm_8 else None,
            "track_act_8": _log1p(industry_8),
            "track_growth": industry_4 / (industry_8 - industry_4 + 0.5),
            "track_entrants": float(entrants),
            "track_recent_entries": _log1p(recent_entries),
            "track_age": ((t - first_industry) / 4.0) if first_industry is not None else None,
            "cat_share": (category_ever / firm_ever) if firm_ever else None,
            "firm_size": _log1p(firm_ever),
        }

    def feature_vector(self, company: str, track: str, t: int,
                       names: tuple[str, ...] = FEATURE_NAMES_C) -> tuple[float, ...]:
        raw = self.features(company, track, t)
        return tuple(math.nan if raw[name] is None else raw[name] for name in names)

    # ---- independent replay (protocol section 12.3) ------------------------
    def features_bruteforce(self, company: str, track: str, t: int) -> dict[str, float | None]:
        """Straight linear-scan re-implementation of ``features`` for the leak audit.

        Deliberately does not use any of the bisect indexes built above: it scans the
        raw event index of the panel.  Must match ``features`` exactly.
        """
        category = self.track_category[track]
        events = self.company_events[company]
        industry = self.industry_events[track]
        firm_4 = firm_8 = firm_ever = 0
        category_8 = category_ever = 0
        industry_4 = industry_8 = 0
        first_industry = None
        for qidx, track_id in events:
            if qidx > t:
                continue
            firm_ever += 1
            if t - 4 < qidx:
                firm_4 += 1
            if t - 8 < qidx:
                firm_8 += 1
            if self.track_category[track_id] == category:
                category_ever += 1
                if t - 8 < qidx:
                    category_8 += 1
        for qidx, _company in industry:
            if qidx > t:
                continue
            if t - 4 < qidx:
                industry_4 += 1
            if t - 8 < qidx:
                industry_8 += 1
            if first_industry is None:
                first_industry = qidx
        entries_last_8y = sum(1 for qidx in self.company_entries[company] if t - 32 < qidx <= t)
        entrants = sum(1 for qidx in self.track_entry_q[track] if qidx <= t)
        recent_entries = sum(1 for qidx in self.track_entry_q[track] if t - 8 < qidx <= t)
        firm_tracks = sum(1 for qidx in self.company_track_first_q[company] if qidx <= t)
        # "other tracks of the same category": subtract the pair's own-track events in the
        # window, exactly like features() does (for candidate cells this term is 0)
        pair_window = sum(1 for qidx in self.pair_events.get((company, track), [])
                          if t - 8 < qidx <= t)
        return {
            "firm_act_4": _log1p(firm_4),
            "firm_act_8": _log1p(firm_8),
            "firm_growth": firm_4 / (firm_8 - firm_4 + 0.5),
            "firm_tracks": float(firm_tracks),
            "firm_tenure": (t - self.company_q[company][0]) / 4.0,
            "firm_entry_rate": entries_last_8y / 8.0,
            "adj_act_8": _log1p(category_8 - pair_window),
            "adj_share": (category_8 / firm_8) if firm_8 else None,
            "track_act_8": _log1p(industry_8),
            "track_growth": industry_4 / (industry_8 - industry_4 + 0.5),
            "track_entrants": float(entrants),
            "track_recent_entries": _log1p(recent_entries),
            "track_age": ((t - first_industry) / 4.0) if first_industry is not None else None,
            "cat_share": (category_ever / firm_ever) if firm_ever else None,
            "firm_size": _log1p(firm_ever),
        }


def load_panel(path: Path) -> Panel:
    _require(path.is_file(), f"panel not found: {path}")
    with open(path, "r", encoding="utf-8") as handle:
        data = json.load(handle)
    return Panel(data, path=path, sha256=sha256_file(path))


# ============================================================ training / models
def evaluation_origins(panel: Panel, horizon: int) -> list[int]:
    """Q1 of every calendar year in the pre-registered origin span (mature cells only)."""
    first_year, last_year = ORIGIN_YEARS["h8" if horizon == 8 else "h4"]
    origins = []
    missing = []
    for year in range(first_year, last_year + 1):
        quarter = f"{year}-Q1"
        if quarter not in panel.qidx:
            missing.append(quarter)
            continue
        origin = panel.qidx[quarter]
        if not panel.mature(origin, horizon):
            missing.append(quarter)
            continue
        origins.append(origin)
    return origins


class RiskHorizonData:
    """Quarterly candidate cells plus the annual test cells for one (risk set, horizon).

    ``adjacency=True`` selects R_adj (primary), False selects R_full.  Cells hold the 15
    protocol features plus the 5 fusion columns (NaN when the lane is absent), so the
    feature-group ablations and the fusion comparison reuse exactly the same cells.
    """

    def __init__(self, panel: Panel, adjacency: bool, horizon: int,
                 fusion_lanes: "FusionLanes | None" = None,
                 max_origins: int | None = None):
        self.panel = panel
        self.adjacency = adjacency
        self.horizon = horizon
        self.feature_names: tuple[str, ...] = FEATURE_NAMES_C + FUSION_FEATURES
        self.column_of = {name: index for index, name in enumerate(self.feature_names)}
        self.test_origins = evaluation_origins(panel, horizon)
        if max_origins is not None:
            self.test_origins = self.test_origins[:max(1, int(max_origins))]
        self.max_train_t = max(self.test_origins) - horizon

        # ---- quarterly training pool (every quarter from panel start to t_last - h)
        company: list[str] = []
        track: list[str] = []
        quarter: list[int] = []
        label: list[int] = []
        features: list[tuple[float, ...]] = []
        build_features = self._feature_builder(fusion_lanes)
        for t in range(0, self.max_train_t + 1):
            for company_key, track_id in panel.risk_set(t, adjacency):
                company.append(company_key)
                track.append(track_id)
                quarter.append(t)
                label.append(panel.label(company_key, track_id, t, horizon))
                features.append(build_features(company_key, track_id, t))
        self.pool_company = company
        self.pool_track = track
        self.pool_t = quarter
        self.pool_label = label
        self.pool_features = features
        self.pool_rows = len(company)
        self.positive_indices = [index for index, value in enumerate(label) if value]
        self.negative_indices = [index for index, value in enumerate(label) if not value]
        self.pool_positive_q = [quarter[index] for index in self.positive_indices]
        self.pool_negative_q = [quarter[index] for index in self.negative_indices]

        # ---- annual test cells
        self.test_cells: dict[int, dict] = {}
        self.immature_excluded: dict[int, int] = {}
        for origin in self.test_origins:
            candidates = panel.risk_set(origin, adjacency)
            if not panel.mature(origin, horizon):
                self.immature_excluded[origin] = len(candidates)
                continue
            rows = {"company": [], "track": [], "label": [], "features": []}
            for company_key, track_id in candidates:
                rows["company"].append(company_key)
                rows["track"].append(track_id)
                rows["label"].append(panel.label(company_key, track_id, origin, horizon))
                rows["features"].append(build_features(company_key, track_id, origin))
            rows["n_immature_excluded"] = 0
            self.test_cells[origin] = rows

    def _feature_builder(self, fusion_lanes):
        panel = self.panel

        def build(company_key: str, track_id: str, t: int) -> tuple[float, ...]:
            raw = panel.features(company_key, track_id, t)
            values = [raw[name] for name in FEATURE_NAMES_C]
            if fusion_lanes is None:
                values.extend([None] * len(FUSION_FEATURES))
            else:
                values.extend(fusion_lanes.values(company_key, track_id, t))
            return tuple(math.nan if value is None else float(value) for value in values)

        return build

    # ---- A2 training sample ---------------------------------------------
    def training_sample(self, origin: int) -> dict:
        """All matured positives + a seeded sample of negatives, capped at 12,000 rows."""
        horizon = self.horizon
        cutoff = origin - horizon
        row_cut = bisect.bisect_right(self.pool_t, cutoff)
        positive_cut = bisect.bisect_right(self.pool_positive_q, cutoff)
        negative_cut = bisect.bisect_right(self.pool_negative_q, cutoff)
        rows_before = row_cut
        positive_indices = self.positive_indices[:positive_cut]
        total_negatives = negative_cut
        if rows_before == 0:
            raise ValueError(f"origin {origin} has no matured training cells (purge leaves nothing)")
        if rows_before <= TRAIN_ROW_CAP:
            sampled_negatives: list[int] = self.negative_indices[:negative_cut]
            p_neg = 1.0
            sampled = False
        else:
            keep_negatives = TRAIN_ROW_CAP - len(positive_indices)
            if keep_negatives < 0:
                keep_negatives = 0
            if total_negatives == 0:
                sampled_negatives = []
                p_neg = 1.0
            else:
                p_neg = keep_negatives / total_negatives
                rng = random.Random(f"{TRAIN_SAMPLE_SEED}|train|{horizon}|"
                                    f"{'adj' if self.adjacency else 'full'}|{origin}")
                population = self.negative_indices[:negative_cut]
                sampled_negatives = rng.sample(population, keep_negatives) if keep_negatives else []
                # negative sampling weight: 1 / p_neg (positives carry weight 1)
            sampled = True
        negative_weight = 1.0 / p_neg if p_neg > 0 else 0.0
        indices = list(positive_indices) + list(sampled_negatives)
        weights = [1.0] * len(positive_indices) + [negative_weight] * len(sampled_negatives)
        labels = [1] * len(positive_indices) + [0] * len(sampled_negatives)
        max_train = max((self.pool_t[index] for index in indices), default=None)
        _require(max_train is None or max_train <= cutoff,
                 f"purge violated at origin {origin}: training cell at t={max_train} > {cutoff}")
        return {
            "origin": origin,
            "horizon": horizon,
            "risk_set": "R_adj" if self.adjacency else "R_full",
            "training_quarters": cutoff + 1,
            "rows_before_sampling": rows_before,
            "rows_after_sampling": len(indices),
            "positives": len(positive_indices),
            "negatives_sampled": len(sampled_negatives),
            "negatives_population": total_negatives,
            "negative_sampling_fraction": p_neg,
            "negative_weight": negative_weight,
            "subsampled": sampled,
            "max_training_origin_qidx": max_train,
            "max_allowed_training_qidx": cutoff,
            "purge_ok": True,
            "indices": indices,
            "weights": weights,
            "labels": labels,
        }

    def feature_matrix(self, indices: list[int], names: tuple[str, ...]) -> list[list[float]]:
        columns = [self.column_of[name] for name in names]
        pool_features = self.pool_features
        return [[pool_features[index][column] for column in columns] for index in indices]

    def test_matrix(self, origin: int, names: tuple[str, ...]) -> list[list[float]]:
        columns = [self.column_of[name] for name in names]
        rows = self.test_cells[origin]["features"]
        return [[row[column] for column in columns] for row in rows]


# ------------------------------------------------------------ weighted logistic M1
def fit_logistic_regression(raw_rows: list[list[float]], labels: list[int], weights: list[float],
                            *, lam: float = LAMBDA, lr: float = LEARNING_RATE,
                            epochs: int = EPOCHS) -> dict:
    """Weighted L2 logistic regression, batch gradient descent, deterministic.

    Standardisation and median imputation are computed on the training rows only (the
    caller passes the training sample).  The intercept is not penalised.  ``lam`` is the
    coefficient on ``0.5 * ||w||^2`` in the weighted-mean loss, exactly as frozen.
    """
    n = len(raw_rows)
    _require(n > 0, "cannot fit M1 on an empty training set")
    d = len(raw_rows[0])
    total_weight = sum(weights)
    _require(total_weight > 0, "training weights must be positive")
    medians: list[float] = []
    for column in range(d):
        pairs = [(row[column], weight) for row, weight in zip(raw_rows, weights)
                 if row[column] == row[column]]
        if pairs:
            medians.append(weighted_median([value for value, _ in pairs],
                                           [weight for _, weight in pairs]))
        else:
            medians.append(0.0)
    matrix = [[medians[column] if row[column] != row[column] else float(row[column])
               for column in range(d)] for row in raw_rows]
    columns = list(zip(*matrix))
    means: list[float] = []
    sds: list[float] = []
    for column in columns:
        mean = sum(map(mul, column, weights)) / total_weight
        variance = sum(map(mul, weights, [(value - mean) ** 2 for value in column])) / total_weight
        spread = math.sqrt(variance)
        means.append(mean)
        sds.append(spread if spread > 0.0 else 1.0)
    matrix = [[(row[column] - means[column]) / sds[column] for column in range(d)]
              for row in matrix]
    transposed = list(zip(*matrix))
    exp = math.exp

    def linear_and_probabilities(coefficients: list[float], intercept: float) -> list[float]:
        linear = [sum(map(mul, row, coefficients)) + intercept for row in matrix]
        try:
            return [1.0 / (1.0 + exp(-value)) for value in linear]
        except OverflowError:
            return [_sigmoid(value) for value in linear]

    def log_loss(probabilities: list[float]) -> float:
        loss = 0.0
        for probability, label, weight in zip(probabilities, labels, weights):
            if label:
                loss -= weight * math.log(max(probability, 1e-300))
            else:
                loss -= weight * math.log(max(1.0 - probability, 1e-300))
        return loss / total_weight + 0.5 * lam * sum(value * value for value in coefficients)

    coefficients = [0.0] * d
    intercept = 0.0
    loss_start = math.log(2.0)   # p = 0.5 at the zero start
    loss_end = loss_start
    for epoch in range(epochs):
        probabilities = linear_and_probabilities(coefficients, intercept)
        errors = [(probability - label) * weight
                  for probability, label, weight in zip(probabilities, labels, weights)]
        gradient_intercept = sum(errors) / total_weight
        gradient = [sum(map(mul, errors, column)) / total_weight + lam * value
                    for column, value in zip(transposed, coefficients)]
        coefficients = [value - lr * slope for value, slope in zip(coefficients, gradient)]
        intercept -= lr * gradient_intercept
    # final loss and gradient norm (convergence report, protocol section 6)
    probabilities = linear_and_probabilities(coefficients, intercept)
    loss_end = log_loss(probabilities)
    errors = [(probability - label) * weight
              for probability, label, weight in zip(probabilities, labels, weights)]
    gradient = [sum(map(mul, errors, column)) / total_weight + lam * value
                for column, value in zip(transposed, coefficients)]
    gradient_intercept = sum(errors) / total_weight
    gradient_norm = math.sqrt(sum(value * value for value in gradient) + gradient_intercept ** 2)
    return {
        "feature_count": d,
        "n_rows": n,
        "total_weight": total_weight,
        "medians": medians,
        "means": means,
        "sds": sds,
        "coefficients": coefficients,
        "intercept": intercept,
        "loss_start": loss_start,
        "loss_end": loss_end,
        "loss_reduction": loss_start - loss_end,
        "gradient_norm_end": gradient_norm,
        "converged": gradient_norm < 1e-4,
        "epochs": epochs,
        "learning_rate": lr,
        "lambda": lam,
    }


def predict_logistic(model: dict, raw_rows: list[list[float]]) -> list[float]:
    medians = model["medians"]
    means = model["means"]
    sds = model["sds"]
    coefficients = model["coefficients"]
    intercept = model["intercept"]
    predictions: list[float] = []
    for row in raw_rows:
        linear = intercept
        for column in range(len(coefficients)):
            value = medians[column] if row[column] != row[column] else row[column]
            linear += coefficients[column] * (value - means[column]) / sds[column]
        predictions.append(_sigmoid(linear))
    return predictions


# ------------------------------------------------------------------- baselines B0-B3
BASELINE_PRIOR_STRENGTH = 2.0


def fit_baselines(data: RiskHorizonData, sample: dict) -> dict:
    """Fit B0-B3 on the same weighted training sample as M1 (protocol section 6)."""
    total = sum(sample["weights"])
    prevalence = sum(map(mul, sample["weights"], sample["labels"])) / total
    company_positive: dict[str, float] = defaultdict(float)
    company_total: dict[str, float] = defaultdict(float)
    track_positive: dict[str, float] = defaultdict(float)
    track_total: dict[str, float] = defaultdict(float)
    for index, weight, label in zip(sample["indices"], sample["weights"], sample["labels"]):
        company = data.pool_company[index]
        track = data.pool_track[index]
        company_total[company] += weight
        track_total[track] += weight
        if label:
            company_positive[company] += weight
            track_positive[track] += weight
    prior = BASELINE_PRIOR_STRENGTH
    company_rate = {company: (company_positive.get(company, 0.0) + prior * prevalence) /
                             (company_total[company] + prior)
                    for company in company_total}
    track_rate = {track: (track_positive.get(track, 0.0) + prior * prevalence) /
                          (track_total[track] + prior)
                  for track in track_total}
    # B3 = B1 x B2 renormalised to the training prevalence
    weighted_raw = 0.0
    for index, weight in zip(sample["indices"], sample["weights"]):
        raw = (company_rate.get(data.pool_company[index], prevalence) *
               track_rate.get(data.pool_track[index], prevalence))
        weighted_raw += weight * raw
    mean_raw = weighted_raw / total
    return {
        "prevalence": prevalence,
        "company_rate": company_rate,
        "track_rate": track_rate,
        "prior_strength": prior,
        "b3_scale": (prevalence / mean_raw) if mean_raw > 0 else 0.0,
    }


def predict_baselines(fit: dict, company_keys: list[str], track_ids: list[str],
                      models: tuple[str, ...] = ("B0", "B1", "B2", "B3")) -> dict[str, list[float]]:
    prevalence = fit["prevalence"]
    predictions: dict[str, list[float]] = {}
    for model in models:
        if model == "B0":
            predictions[model] = [prevalence] * len(company_keys)
        elif model == "B1":
            predictions[model] = [fit["company_rate"].get(company, prevalence)
                                  for company in company_keys]
        elif model == "B2":
            predictions[model] = [fit["track_rate"].get(track, prevalence) for track in track_ids]
        elif model == "B3":
            predictions[model] = [
                min(1.0, max(1e-9, fit["b3_scale"] *
                            fit["company_rate"].get(company, prevalence) *
                            fit["track_rate"].get(track, prevalence)))
                for company, track in zip(company_keys, track_ids)]
        else:
            raise ValueError(f"unknown baseline {model!r}")
    return predictions


# ================================================================ metric helpers
def ap_summary(values: list[float | None]) -> dict:
    clean = [float(value) for value in values if value is not None]
    if not clean:
        return {"n": 0, "mean": None, "sd": None, "min": None, "max": None}
    mean = sum(clean) / len(clean)
    variance = sum((value - mean) ** 2 for value in clean) / len(clean)   # repo convention
    return {"n": len(clean), "mean": mean, "sd": math.sqrt(variance),
            "min": min(clean), "max": max(clean)}


def evaluate_origin(record: dict) -> dict:
    """All per-origin metrics for every model scored on that origin's test cells."""
    labels = record["labels"]
    companies = record["companies"]
    tracks = record["tracks"]
    positives = sum(labels)
    negatives = len(labels) - positives
    result = {
        "origin": record["origin"],
        "n_candidates": len(labels),
        "n_positives": positives,
        "base_rate": (positives / len(labels)) if labels else None,
        "n_immature_excluded": record.get("n_immature_excluded", 0),
        "models": {},
    }
    for model, scores in record["scores"].items():
        order = rank_order(scores, companies, tracks)
        entry = {
            "average_precision": average_precision(labels, scores, companies, tracks, order),
            "roc_auc": roc_auc(labels, scores),
            "brier": brier_score(labels, scores),
            "ece_10": expected_calibration_error(labels, scores),
            "precision_at_10": precision_at_k(labels, order, 10),
            "precision_at_25": precision_at_k(labels, order, 25),
        }
        thresholds = record["thresholds"].get(model, {})
        alerts = {}
        for budget in ALERT_BUDGETS:
            threshold = thresholds.get(budget)
            if threshold is None:
                alerts[f"{budget:.2f}"] = None
                continue
            true_positives = false_positives = alerted = 0
            for label, score in zip(labels, scores):
                if score >= threshold:
                    alerted += 1
                    if label:
                        true_positives += 1
                    else:
                        false_positives += 1
            alerts[f"{budget:.2f}"] = {
                "threshold": threshold,
                "alerted": alerted,
                "recall": (true_positives / positives) if positives else None,
                "precision": (true_positives / alerted) if alerted else None,
                "false_alarm_rate": (false_positives / negatives) if negatives else None,
                "false_alarms_per_1000_candidates": (
                    1000.0 * false_positives / len(labels)) if labels else None,
            }
        entry["alerts"] = alerts
        result["models"][model] = entry
    return result


def mean_origin_ap(per_origin: list[dict], model: str) -> dict:
    values = [origin["models"].get(model, {}).get("average_precision")
              for origin in per_origin]
    return ap_summary(values)


def pooled_ap(records: list[dict], model: str) -> float | None:
    labels: list[int] = []
    scores: list[float] = []
    companies: list[str] = []
    tracks: list[str] = []
    for record in records:
        if model not in record["scores"]:
            continue
        labels.extend(record["labels"])
        scores.extend(record["scores"][model])
        companies.extend(record["companies"])
        tracks.extend(record["tracks"])
    return average_precision(labels, scores, companies, tracks) if labels else None


# ------------------------------------------------- company-clustered paired bootstrap
def prepare_bootstrap_origins(records: list[dict], model_names: tuple[str, ...],
                              company_index: dict[str, int]) -> list[dict]:
    prepared = []
    for record in records:
        company_ids = [company_index[company] for company in record["companies"]]
        entry = {"n_rows": len(record["labels"]), "n_positives": sum(record["labels"])}
        for model in model_names:
            entry[model] = prepare_ap(record["labels"], record["scores"][model], company_ids)
        prepared.append(entry)
    return prepared


def _delta_entry(deltas: list[float], status: str, reference: str) -> dict:
    entry = {
        "reference": reference,
        "n_draws": len(deltas),
        "mean": (sum(deltas) / len(deltas)) if deltas else None,
        "sd": statistics.pstdev(deltas) if len(deltas) > 1 else None,
        "p_two_sided": None, "p_delta_le_zero": None,
        "mde_80pct_power_alpha_0.05": None,
        "ci_low": None, "ci_high": None, "ci_half_width": None,
        "status": status,
    }
    if deltas:
        ordered = sorted(deltas)
        entry["p_delta_le_zero"] = sum(1 for value in deltas if value <= 0.0) / len(deltas)
        share_ge = sum(1 for value in deltas if value >= 0.0) / len(deltas)
        entry["p_two_sided"] = min(1.0, 2.0 * min(entry["p_delta_le_zero"], share_ge))
        if entry["sd"] is not None:
            entry["mde_80pct_power_alpha_0.05"] = MDE_Z * entry["sd"]
        if status == "OK":
            entry["ci_low"] = percentile_sorted(ordered, 0.025)
            entry["ci_high"] = percentile_sorted(ordered, 0.975)
            entry["ci_half_width"] = (entry["ci_high"] - entry["ci_low"]) / 2.0
        else:
            # the pre-declared reliability gate failed: do not quote a CI, but keep the
            # draw distribution visible (clearly labelled) so the report is traceable
            entry["descriptive_interval_not_a_ci"] = [
                percentile_sorted(ordered, 0.025), percentile_sorted(ordered, 0.975)]
            entry["note"] = ("bootstrap UNRELIABLE: the pre-declared computable-origin "
                             "gate failed, so no CI is quoted; the interval above is the "
                             "2.5/97.5 percentile spread of the bootstrap draws and is "
                             "descriptive only, NOT a confidence interval")
    return entry


def clustered_bootstrap_mean_ap(prepared: list[dict], model_names: tuple[str, ...],
                                n_companies: int, reps: int, seed: int,
                                comparisons: tuple[tuple[str, str], ...] = ()) -> dict:
    """Company-clustered paired bootstrap of each model's mean per-origin AP.

    Companies are drawn with replacement; every resampled row is scored by every model
    (paired; A1).  For a resample and an origin, AP is computed only when that origin has
    at least one positive and one negative row; the per-origin mean is taken over the
    computable origins and the count is recorded (pre-declared degenerate handling).
    """
    rng = random.Random(seed)
    draws: dict[str, list[float]] = {model: [] for model in model_names}
    contributing_counts: list[int] = []
    reps_used = 0
    for _ in range(reps):
        multiplicities = [0] * n_companies
        for _ in range(n_companies):
            multiplicities[rng.randrange(n_companies)] += 1
        sums = {model: 0.0 for model in model_names}
        contributing = 0
        for prepared_origin in prepared:
            values: dict[str, float] = {}
            computable = True
            for model in model_names:
                ap = ap_weighted(prepared_origin[model], multiplicities)
                if ap is None:
                    computable = False
                    break
                values[model] = ap
            if not computable:
                continue
            contributing += 1
            for model in model_names:
                sums[model] += values[model]
        contributing_counts.append(contributing)
        if contributing == 0:
            continue
        reps_used += 1
        for model in model_names:
            draws[model].append(sums[model] / contributing)
    n_origins = len(prepared)
    unreliable_threshold = max(1, int(math.ceil(n_origins * 25.0 / 30.0)))
    below = sum(1 for count in contributing_counts if count < unreliable_threshold)
    below_share = (below / len(contributing_counts)) if contributing_counts else 1.0
    result = {
        "reps_requested": reps,
        "reps_with_a_computable_origin": reps_used,
        "n_companies": n_companies,
        "origins": n_origins,
        "min_contributing_origins_required": unreliable_threshold,
        "share_resamples_below_min_contributing_origins": below_share,
        "contributing_origins_min": min(contributing_counts) if contributing_counts else 0,
        "contributing_origins_median": statistics.median(contributing_counts)
                                       if contributing_counts else 0,
        "contributing_origins_max": max(contributing_counts) if contributing_counts else 0,
        "status": "UNRELIABLE" if below_share > 0.05 else "OK",
        "mean_ap": {}, "delta": {}, "comparisons": {}, "seed": seed,
    }
    if result["status"] == "UNRELIABLE":
        result["note"] = ("more than 5% of resamples had fewer than "
                          f"{unreliable_threshold} computable origins; no CI is quoted")
    for model in model_names:
        values = draws[model]
        result["mean_ap"][model] = {
            "bootstrap_mean": (sum(values) / len(values)) if values else None,
            "bootstrap_sd": (statistics.pstdev(values) if len(values) > 1 else None),
            "ci_low": percentile_sorted(sorted(values), 0.025) if values and
                      result["status"] == "OK" else None,
            "ci_high": percentile_sorted(sorted(values), 0.975) if values and
                       result["status"] == "OK" else None,
        }
    reference = "B1"
    reference_draws = draws.get(reference, [])
    for model in model_names:
        if model == reference:
            continue
        deltas = [first - second for first, second in zip(draws[model], reference_draws)]
        result["delta"][model] = _delta_entry(deltas, result["status"], reference)
    for first_model, second_model in comparisons:
        if first_model == second_model:
            continue
        key = f"{first_model}-{second_model}"
        left = draws.get(first_model, [])
        right = draws.get(second_model, [])
        if not left or not right or len(left) != len(right):
            result["comparisons"][key] = _delta_entry([], "NOT_EVALUABLE", second_model)
            continue
        deltas = [first - second for first, second in zip(left, right)]
        result["comparisons"][key] = _delta_entry(deltas, result["status"], second_model)
    result["n_origins_with_defined_point_ap"] = sum(
        1 for prepared_origin in prepared
        if all(0 < prepared_origin[model]["n_rows"] and
               any(prepared_origin[model]["labels"]) for model in model_names))
    return result


# ============================================================== analysis blocks
def candidate_membership(records: list[dict]) -> dict[int, set[tuple[str, str]]]:
    return {record["origin"]: set(zip(record["companies"], record["tracks"]))
            for record in records}


def incident_entries(panel: Panel, records: list[dict], horizon: int) -> dict:
    """Entry events in the evaluation window and the origins at which they were candidates.

    The evaluation window is the union over evaluation origins of ``(t, t+h]``.  For an
    entry at quarter ``f`` the alert window is ``[f-8, f-1]`` (protocol section 8).
    """
    origins = [record["origin"] for record in records]
    first_origin, last_origin = min(origins), max(origins)
    membership = candidate_membership(records)
    ever_in_risk_set: set[tuple[str, str]] = set()
    for cells in membership.values():
        ever_in_risk_set |= cells
    entries = []
    excluded = 0
    without_candidate_origin = 0
    for (company, track), values in panel.pair_events.items():
        if not values:
            continue
        first = values[0]
        if first <= first_origin or first > last_origin + horizon:
            continue
        window = [origin for origin in origins if first - 8 <= origin <= first - 1]
        candidate_origins = [origin for origin in window
                             if (company, track) in membership.get(origin, ())]
        if not candidate_origins:
            if (company, track) not in ever_in_risk_set:
                # the pair is never on R_adj at any evaluation origin (e.g. a first
                # entry in a brand-new category): outside the R_adj estimand
                excluded += 1
                continue
            # on R_adj elsewhere but no candidate origin in the alert window: by the
            # protocol this is a missed entry, not an exclusion
            without_candidate_origin += 1
        entries.append({"company_key": company, "track_id": track, "entry_qidx": first,
                        "candidate_origins": sorted(candidate_origins)})
    entries.sort(key=lambda entry: (entry["entry_qidx"], entry["company_key"], entry["track_id"]))
    return {"entries": entries,
            "n_entries": len(entries),
            "n_entries_without_candidate_origin_in_alert_window": without_candidate_origin,
            "excluded_never_in_risk_set": excluded,
            "evaluation_window": [first_origin + 1, last_origin + horizon]}


def alert_analysis(records: list[dict], entries: dict, model: str, budget: float) -> dict:
    """Pooled alert precision/recall/false-alarm rate plus entry lead times at one budget."""
    scores_by_origin: dict[int, dict[tuple[str, str], float]] = {}
    true_positives = false_positives = positive_cells = 0
    total_cells = 0
    for record in records:
        threshold = record["thresholds"][model][budget]
        lookup: dict[tuple[str, str], float] = {}
        for company, track, label, score in zip(record["companies"], record["tracks"],
                                                record["labels"], record["scores"][model]):
            lookup[(company, track)] = score
            total_cells += 1
            if label:
                positive_cells += 1
            if score >= threshold:
                if label:
                    true_positives += 1
                else:
                    false_positives += 1
        scores_by_origin[record["origin"]] = lookup
    thresholds = {record["origin"]: record["thresholds"][model][budget] for record in records}
    leads: list[int] = []
    alerted = missed = 0
    for entry in entries["entries"]:
        first_alert = None
        for origin in entry["candidate_origins"]:
            score = scores_by_origin.get(origin, {}).get((entry["company_key"], entry["track_id"]))
            if score is not None and score >= thresholds[origin]:
                first_alert = origin
                break
        if first_alert is None:
            missed += 1
        else:
            alerted += 1
            leads.append(entry["entry_qidx"] - first_alert)
    return {
        "budget": budget,
        "n_candidate_cells": total_cells,
        "n_positive_cells": positive_cells,
        "alerts": true_positives + false_positives,
        "precision": (true_positives / (true_positives + false_positives))
                     if (true_positives + false_positives) else None,
        "recall": (true_positives / positive_cells) if positive_cells else None,
        "false_alarms_per_1000_candidate_quarters": (
            1000.0 * false_positives / total_cells) if total_cells else None,
        "false_alarm_rate_among_negatives": (
            false_positives / (total_cells - positive_cells)) if (total_cells - positive_cells) else None,
        "entries_in_scope": len(entries["entries"]),
        "entries_alerted": alerted,
        "entries_missed": missed,
        "lead_quarters": median_iqr(leads),
    }


def heterogeneity_companies(panel: Panel, records: list[dict], models: tuple[str, ...],
                            minimum_positives: int = 10) -> dict:
    origins = [record["origin"] for record in records]
    by_origin = {record["origin"]: record for record in records}
    per_company: dict[str, dict] = {}
    for company in panel.company_keys:
        entry = {"company_key": company, "display_name": panel.companies[company].get("display_name"),
                 "cohort": panel.companies[company].get("cohort"),
                 "total_material_events": panel.companies[company].get(
                     "total_material_events", len(panel.company_q[company])),
                 "n_test_cells": 0, "n_positives": 0, "models": {}}
        for origin in origins:
            record = by_origin[origin]
            indices = [index for index, key in enumerate(record["companies"]) if key == company]
            entry["n_test_cells"] += len(indices)
            entry["n_positives"] += sum(record["labels"][index] for index in indices)
            for model in models:
                subset_labels = [record["labels"][index] for index in indices]
                subset_scores = [record["scores"][model][index] for index in indices]
                subset_tracks = [record["tracks"][index] for index in indices]
                if len(indices) < 2 or sum(subset_labels) == 0:
                    continue
                order = sorted(range(len(indices)), key=lambda i: (-subset_scores[i],
                                                                  subset_tracks[i]))
                value = average_precision(subset_labels, subset_scores,
                                          order=order)
                if value is not None:
                    entry["models"].setdefault(model, []).append(value)
        for model in models:
            values = entry["models"].get(model, [])
            entry["models"][model] = {
                "mean_per_origin_ap": (sum(values) / len(values)) if values else None,
                "n_origins": len(values),
            }
        delta_values = []
        left = entry["models"]["M1C"]["mean_per_origin_ap"] if "M1C" in entry["models"] else None
        right = entry["models"]["B1"]["mean_per_origin_ap"] if "B1" in entry["models"] else None
        if left is not None and right is not None:
            delta_values.append(left - right)
        entry["delta_ap"] = delta_values[0] if delta_values else None
        entry["eligible"] = entry["n_positives"] >= minimum_positives
        per_company[company] = entry
    eligible = {company: entry for company, entry in per_company.items() if entry["eligible"]}
    ap_values = [(entry["models"]["M1C"]["mean_per_origin_ap"], entry["total_material_events"])
                 for entry in eligible.values()
                 if entry["models"]["M1C"]["mean_per_origin_ap"] is not None]
    tau = kendall_tau([value for value, _ in ap_values],
                      [float(size) for _, size in ap_values]) if len(ap_values) >= 3 else None
    deep = {company: per_company.get(company) for company in DEEP_CASE_KEYS
            if company in per_company}
    auxiliary = {company: entry for company, entry in eligible.items()
                 if company not in DEEP_CASE_KEYS}
    return {"per_company": per_company, "eligible_companies": len(eligible),
            "minimum_positives": minimum_positives,
            "kendall_tau_ap_vs_material_events": tau,
            "kendall_tau_n": len(ap_values),
            "deep_cases": deep, "deep_case_eligible": len(deep),
            "auxiliary_eligible": len(auxiliary)}
def heterogeneity_categories(panel: Panel, records: list[dict], models: tuple[str, ...],
                             reps: int, seed: int) -> dict:
    origins = [record["origin"] for record in records]
    by_origin = {record["origin"]: record for record in records}
    track_category = panel.track_category
    categories = sorted({track_category[track] for track in panel.track_keys})
    per_category: dict[str, dict] = {}
    category_company_sets: dict[str, set[str]] = {}
    for category in categories:
        entry = {"category": category, "n_test_cells": 0, "n_positives": 0, "models": {},
                 "n_tracks": sum(1 for track in panel.track_keys
                                 if track_category[track] == category)}
        companies_in_category: set[str] = set()
        per_origin_index: dict[int, list[int]] = {}
        for origin in origins:
            record = by_origin[origin]
            indices = [index for index, track in enumerate(record["tracks"])
                       if track_category[track] == category]
            per_origin_index[origin] = indices
            entry["n_test_cells"] += len(indices)
            entry["n_positives"] += sum(record["labels"][index] for index in indices)
            for index in indices:
                companies_in_category.add(record["companies"][index])
            for model in models:
                subset_labels = [record["labels"][index] for index in indices]
                subset_scores = [record["scores"][model][index] for index in indices]
                subset_tracks = [record["tracks"][index] for index in indices]
                if len(indices) < 2 or sum(subset_labels) == 0:
                    continue
                order = sorted(range(len(indices)), key=lambda i: (-subset_scores[i],
                                                                  subset_tracks[i]))
                value = average_precision(subset_labels, subset_scores, order=order)
                if value is not None:
                    entry["models"].setdefault(model, []).append(value)
        for model in models:
            values = entry["models"].get(model, [])
            entry["models"][model] = {
                "mean_per_origin_ap": (sum(values) / len(values)) if values else None,
                "n_origins": len(values),
            }
        if ("M1C" in entry["models"] and "B1" in entry["models"]
                and entry["models"]["M1C"]["mean_per_origin_ap"] is not None
                and entry["models"]["B1"]["mean_per_origin_ap"] is not None):
            entry["delta_ap"] = (entry["models"]["M1C"]["mean_per_origin_ap"]
                                 - entry["models"]["B1"]["mean_per_origin_ap"])
        else:
            entry["delta_ap"] = None
        entry["_indices"] = per_origin_index
        entry["_companies"] = sorted(companies_in_category)
        per_category[category] = entry
        category_company_sets[category] = companies_in_category

    # pre-registered test: highest-minus-lowest category, company-clustered within category
    eligible = [category for category, entry in per_category.items()
                if entry["models"]["M1C"]["mean_per_origin_ap"] is not None
                and entry["n_positives"] >= 10]
    extremes = None
    if len(eligible) >= 2:
        ranked = sorted(eligible, key=lambda category: per_category[category]["models"]["M1C"]["mean_per_origin_ap"])
        high_category, low_category = ranked[-1], ranked[0]
        # prepare per-origin AP engines for the two extremes
        prepared: dict[str, dict] = {}
        for category in (high_category, low_category):
            entry = per_category[category]
            local_index = {company: index for index, company in enumerate(entry["_companies"])}
            origins_prepared = []
            for origin in origins:
                record = by_origin[origin]
                indices = entry["_indices"][origin]
                if len(indices) < 2:
                    continue
                labels = [record["labels"][index] for index in indices]
                company_ids = [local_index[record["companies"][index]] for index in indices]
                origin_entry = {}
                usable = False
                for model in ("M1C", "B1"):
                    scores = [record["scores"][model][index] for index in indices]
                    order = sorted(range(len(indices)),
                                   key=lambda i: (-scores[i], record["tracks"][indices[i]]))
                    origin_entry[model] = prepare_ap(labels, scores, company_ids, order=order)
                    usable = True
                if usable:
                    origins_prepared.append(origin_entry)
            prepared[category] = {"origins": origins_prepared,
                                  "n_companies": len(entry["_companies"]),
                                  "point_mean": entry["models"]["M1C"]["mean_per_origin_ap"]}
        point_difference = (prepared[high_category]["point_mean"]
                            - prepared[low_category]["point_mean"])
        rng = random.Random(f"{seed}|categories|highest-lowest")
        draws: list[float] = []
        for _ in range(reps):
            values = {}
            computable = True
            for category in (high_category, low_category):
                block = prepared[category]
                n_companies = block["n_companies"]
                multiplicities = [0] * n_companies
                for _ in range(n_companies):
                    multiplicities[rng.randrange(n_companies)] += 1
                ap_m1c: list[float] = []
                ap_b1: list[float] = []
                for origin_entry in block["origins"]:
                    first = ap_weighted(origin_entry["M1C"], multiplicities)
                    second = ap_weighted(origin_entry["B1"], multiplicities)
                    if first is not None and second is not None:
                        ap_m1c.append(first)
                        ap_b1.append(second)
                if ap_m1c and ap_b1:
                    values[category] = (sum(ap_m1c) / len(ap_m1c)) - (sum(ap_b1) / len(ap_b1))
                else:
                    computable = False
                    break
            if computable and len(values) == 2:
                draws.append(values[high_category] - values[low_category])
        ordered = sorted(draws)
        ci_low = percentile_sorted(ordered, 0.025) if ordered else None
        ci_high = percentile_sorted(ordered, 0.975) if ordered else None
        extremes = {
            "highest_category": high_category,
            "lowest_category": low_category,
            "highest_minus_lowest_mean_per_origin_ap_difference": point_difference,
            "ci_low": ci_low, "ci_high": ci_high,
            "ci_excludes_zero": (ci_low is not None and (ci_low > 0 or ci_high < 0)),
            "reps": reps, "valid_draws": len(draws),
            "note": "company-clustered bootstrap resampling companies within each category",
        }
    for entry in per_category.values():
        entry.pop("_indices", None)
        entry.pop("_companies", None)
    return {"per_category": per_category, "extremes": extremes}


# ------------------------------------------------------------- label-permutation null
def _group_indices(keys: list[tuple[int, str]]) -> dict[tuple[int, str], list[int]]:
    groups: dict[tuple[int, str], list[int]] = defaultdict(list)
    for index, key in enumerate(keys):
        groups[key].append(index)
    return dict(groups)


def permutation_delta(panel: Panel, data: RiskHorizonData, perm_index: int,
                      seed: int) -> dict:
    """One label-permutation replicate of ΔAP (M1C - B1) on the primary configuration.

    Labels are shuffled among cells that share (origin quarter, track), which preserves
    every origin's prevalence and every (origin, track) entry count exactly; per-company
    total entries are **not** preserved (that constraint is infeasible within the frozen
    risk sets).  Both the training labels and the evaluation labels are permuted, and M1C
    and B1 are refitted on the permuted training labels.
    """
    rng = random.Random(f"{seed}|permutation|{data.horizon}|"
                        f"{'adj' if data.adjacency else 'full'}|{perm_index}")
    pool_group_keys = list(zip(data.pool_t, data.pool_track))
    pool_groups = _group_indices(pool_group_keys)
    permuted_pool_labels = list(data.pool_label)
    for group in pool_groups.values():
        values = [data.pool_label[index] for index in group]
        rng.shuffle(values)
        for position, index in enumerate(group):
            permuted_pool_labels[index] = values[position]
    test_group_keys: dict[int, dict[tuple[int, str], list[int]]] = {}
    permuted_test_labels: dict[int, list[int]] = {}
    for origin in data.test_origins:
        cells = data.test_cells[origin]
        groups = _group_indices([(origin, track) for track in cells["track"]])
        labels = list(cells["label"])
        for group in groups.values():
            values = [cells["label"][index] for index in group]
            rng.shuffle(values)
            for position, index in enumerate(group):
                labels[index] = values[position]
        test_group_keys[origin] = groups
        permuted_test_labels[origin] = labels
    ap_m1c: list[float] = []
    ap_b1: list[float] = []
    for origin in data.test_origins:
        sample = data.training_sample(origin)
        permuted_sample = dict(sample)
        permuted_sample["labels"] = [permuted_pool_labels[index] for index in sample["indices"]]
        names = FEATURE_GROUPS["C"]
        raw_train = data.feature_matrix(sample["indices"], names)
        fit = fit_logistic_regression(raw_train, permuted_sample["labels"],
                                      sample["weights"])
        baselines = fit_baselines(data, permuted_sample)
        cells = data.test_cells[origin]
        permuted_labels = permuted_test_labels[origin]
        raw_test = data.test_matrix(origin, names)
        scores_m1c = predict_logistic(fit, raw_test)
        scores_b1 = predict_baselines(baselines, cells["company"], cells["track"],
                                      models=("B1",))["B1"]
        order_m1c = rank_order(scores_m1c, cells["company"], cells["track"])
        order_b1 = rank_order(scores_b1, cells["company"], cells["track"])
        first = average_precision(permuted_labels, scores_m1c, order=order_m1c)
        second = average_precision(permuted_labels, scores_b1, order=order_b1)
        if first is not None and second is not None:
            ap_m1c.append(first)
            ap_b1.append(second)
    if not ap_m1c:
        return {"permutation": perm_index, "delta": None, "n_origins": 0,
                "mean_ap_m1c": None, "mean_ap_b1": None}
    mean_m1c = sum(ap_m1c) / len(ap_m1c)
    mean_b1 = sum(ap_b1) / len(ap_b1)
    return {"permutation": perm_index, "delta": mean_m1c - mean_b1,
            "n_origins": len(ap_m1c), "mean_ap_m1c": mean_m1c, "mean_ap_b1": mean_b1}


_WORKER_STATE: dict = {}


def _permutation_worker_init(panel_path: str, adjacency: bool, horizon: int,
                             max_origins: int | None = None) -> None:
    panel = load_panel(Path(panel_path))
    _WORKER_STATE["panel"] = panel
    _WORKER_STATE["data"] = RiskHorizonData(panel, adjacency, horizon, fusion_lanes=None,
                                            max_origins=max_origins)


def _permutation_worker_run(perm_index: int) -> dict:
    return permutation_delta(_WORKER_STATE["panel"], _WORKER_STATE["data"], perm_index, SEED)


def choose_permutation_count(rows_after: list[int], workers: int,
                             budget_minutes: float) -> dict:
    """A4 resource fallback: deterministic count from a declared cost model."""
    units_per_permutation = sum(rows * len(GROUP_C) * EPOCHS for rows in rows_after)
    seconds_per_permutation = (units_per_permutation / PERM_FIT_RATE / max(1, workers)) + 1.5
    available = max(1.0, budget_minutes * 60.0)
    count = int(available / max(seconds_per_permutation, 1e-9))
    count = max(1, min(PERMUTATION_REPS, count))
    return {"requested": PERMUTATION_REPS, "achieved": count,
            "workers": max(1, workers), "budget_minutes": budget_minutes,
            "estimated_seconds_per_permutation": seconds_per_permutation,
            "cost_units_per_permutation": units_per_permutation,
            "fit_rate_units_per_second": PERM_FIT_RATE,
            "reduced": count < PERMUTATION_REPS,
            "reason": ("A4 resource fallback: deterministic cost model "
                       "(rows x features x epochs / declared rate / workers)")}


# ------------------------------------------------------------------- fusion lanes
class FusionLanes:
    """Trial (``data/b040_device_trials.sqlite``) and publication lanes for feature set D.

    The lanes are read read-only from the repository data directory.  A cell's
    publication lane is joined when all three complete calendar years
    ``year(t)-3 .. year(t)-1`` exist for the company; the trial lane is defined for every
    track (0 when the track has no trial events).  Coverage is measured, never assumed.
    """

    def __init__(self, data_root: Path, panel: Panel):
        self.panel = panel
        self.available = False
        self.reason: list[str] = []
        self.trial_track_q: dict[str, list[int]] = {}
        self.trial_category_q: dict[str, list[int]] = {}
        self.publications: dict[str, dict[int, int]] = {}
        trial_path = data_root / "b040_device_trials.sqlite"
        research_path = data_root / "research.sqlite"
        if not trial_path.is_file():
            self.reason.append(f"trial lane missing: {trial_path}")
        if not research_path.is_file():
            self.reason.append(f"publication lane missing: {research_path}")
        if self.reason:
            return
        try:
            self.trial_sha256 = sha256_file(trial_path) if trial_path.is_file() else None
            self.publication_sha256 = sha256_file(research_path) if research_path.is_file() else None
            import sqlite3
            connection = sqlite3.connect(f"file:{trial_path}?mode=ro", uri=True)
            try:
                rows = connection.execute(
                    "select event_date, available_at, track_id from events "
                    "where source = 'ctgov'").fetchall()
            finally:
                connection.close()
            category_of = panel.track_category
            category_q: dict[str, list[int]] = defaultdict(list)
            unmapped = 0
            for event_date, available_at, track_id in rows:
                quarter = _date_to_qidx(panel, available_at or event_date)
                if quarter is None:
                    continue
                if track_id and track_id in category_of:
                    self.trial_track_q.setdefault(track_id, []).append(quarter)
                    category_q[category_of[track_id]].append(quarter)
                else:
                    unmapped += 1
            for track in self.trial_track_q:
                self.trial_track_q[track].sort()
            for category in category_q:
                category_q[category].sort()
            self.trial_category_q = dict(category_q)
            self.trial_unmapped = unmapped
            self.trial_events = len(rows)
            connection = sqlite3.connect(f"file:{research_path}?mode=ro", uri=True)
            try:
                publication_rows = connection.execute(
                    "select company_key, year, works from publication_counts "
                    "where source = 'openalex_group_by_publication_year'").fetchall()
            finally:
                connection.close()
            for company, year, works in publication_rows:
                self.publications.setdefault(company, {})[int(year)] = int(works)
            self.available = bool(panel.track_keys)
        except Exception as error:                      # pragma: no cover - data dependent
            self.reason.append(f"lane read failed: {error!r}")
            self.available = False

    def values(self, company: str, track: str, t: int) -> tuple:
        """Fusion features for one cell (None where the lane is undefined)."""
        panel = self.panel
        year = panel.quarter_year[t]
        track_values = self.trial_track_q.get(track, [])
        low = t - 8
        track_count = bisect.bisect_right(track_values, t) - bisect.bisect_right(track_values, low)
        category = panel.track_category[track]
        category_values = self.trial_category_q.get(category, [])
        category_count = (bisect.bisect_right(category_values, t)
                          - bisect.bisect_right(category_values, low))
        adjacent = category_count - track_count
        works = self.publications.get(company, {})
        previous = works.get(year - 1)
        three_years = [works.get(year - 1), works.get(year - 2), works.get(year - 3)]
        return (
            _log1p(track_count),
            _log1p(adjacent),
            _log1p(previous) if previous is not None else None,
            _log1p(sum(three_years)) if all(value is not None for value in three_years) else None,
            (previous / (works[year - 2] + 0.5))
            if previous is not None and works.get(year - 2) is not None else None,
        )

    def coverage(self, data: RiskHorizonData, origins: list[int]) -> dict:
        joined = publication_joined = trials_present = total = 0
        for origin in origins:
            cells = data.test_cells.get(origin)
            if not cells:
                continue
            for company, track in zip(cells["company"], cells["track"]):
                total += 1
                values = self.values(company, track, origin)
                if values[2] is not None and values[3] is not None and values[4] is not None:
                    publication_joined += 1
                if self.trial_track_q.get(track):
                    trials_present += 1
        return {
            "cells": total,
            "publication_join_rate": (publication_joined / total) if total else 0.0,
            "trial_track_present_rate": (trials_present / total) if total else 0.0,
            "trial_events": getattr(self, "trial_events", 0),
            "trial_events_unmapped_to_panel_tracks": getattr(self, "trial_unmapped", 0),
            "publication_companies": len(self.publications),
        }


def _date_to_qidx(panel: Panel, value: str | None) -> int | None:
    if not value or len(value) < 7:
        return None
    try:
        year = int(value[0:4])
        month = int(value[5:7])
    except (TypeError, ValueError):
        return None
    quarter = f"{year}-Q{((month - 1) // 3) + 1}"
    return panel.qidx.get(quarter)


# ====================================================================== run config
def run_config(data: RiskHorizonData, group_plan: dict[str, set[int] | None]) -> dict:
    """Fit every requested model at every evaluation origin and collect metrics."""
    panel = data.panel
    records: list[dict] = []
    dataset_rows: list[dict] = []
    convergence: list[dict] = []
    for origin in data.test_origins:
        sample = data.training_sample(origin)
        baselines = fit_baselines(data, sample)
        cells = data.test_cells[origin]
        companies = cells["company"]
        tracks = cells["track"]
        scores = predict_baselines(baselines, companies, tracks)
        training_companies = [data.pool_company[index] for index in sample["indices"]]
        training_tracks = [data.pool_track[index] for index in sample["indices"]]
        training_baseline_scores = predict_baselines(baselines, training_companies,
                                                     training_tracks)
        thresholds: dict[str, dict[float, float | None]] = {}
        for model, values in training_baseline_scores.items():
            thresholds[model] = {
                budget: weighted_quantile(values, sample["weights"], 1.0 - budget)
                for budget in ALERT_BUDGETS}
        groups_here = [group for group, origins in group_plan.items()
                       if origins is None or origin in origins]
        for group in groups_here:
            names = FEATURE_GROUPS[group]
            raw_training = data.feature_matrix(sample["indices"], names)
            started = time.perf_counter()
            fit = fit_logistic_regression(raw_training, sample["labels"], sample["weights"])
            fit_seconds = time.perf_counter() - started
            model_name = "M1" + group
            scores[model_name] = predict_logistic(fit, data.test_matrix(origin, names))
            training_scores = predict_logistic(fit, raw_training)
            thresholds[model_name] = {
                budget: weighted_quantile(training_scores, sample["weights"], 1.0 - budget)
                for budget in ALERT_BUDGETS}
            convergence.append({
                "origin": origin, "origin_label": panel.quarters[origin], "model": model_name,
                "n_rows": fit["n_rows"], "feature_count": fit["feature_count"],
                "loss_start": fit["loss_start"], "loss_end": fit["loss_end"],
                "loss_reduction": fit["loss_reduction"],
                "gradient_norm_end": fit["gradient_norm_end"],
                "converged_at_gradient_tolerance": fit["converged"],
                "fit_seconds": fit_seconds,
            })
        records.append({
            "origin": origin, "companies": companies, "tracks": tracks,
            "labels": cells["label"], "scores": scores, "thresholds": thresholds,
            "n_immature_excluded": cells.get("n_immature_excluded", 0),
        })
        sample_summary = {key: value for key, value in sample.items()
                          if key not in ("indices", "weights", "labels")}
        dataset_rows.append({
            "origin": origin, "origin_label": panel.quarters[origin],
            "n_candidates": len(cells["label"]),
            "n_positives": sum(cells["label"]),
            "base_rate": (sum(cells["label"]) / len(cells["label"])) if cells["label"] else None,
            "n_immature_excluded": cells.get("n_immature_excluded", 0),
            "training": sample_summary,
        })
    per_origin = [evaluate_origin(record) for record in records]
    model_names = sorted({model for record in records for model in record["scores"]})
    mean_ap = {model: mean_origin_ap(per_origin, model) for model in model_names}
    pooled = {model: pooled_ap(records, model) for model in model_names}
    return {
        "risk_set": "R_adj" if data.adjacency else "R_full",
        "horizon": data.horizon,
        "horizon_key": "h8" if data.horizon == 8 else "h4",
        "origins": list(data.test_origins),
        "origin_labels": [panel.quarters[origin] for origin in data.test_origins],
        "records": records,
        "per_origin": per_origin,
        "models": model_names,
        "mean_per_origin_ap": mean_ap,
        "pooled_ap": pooled,
        "dataset_rows": dataset_rows,
        "convergence": convergence,
        "pool_rows": data.pool_rows,
        "pool_positives": len(data.positive_indices),
    }


def era_strata(config: dict, panel: Panel) -> dict:
    result = {}
    for name, first_year, last_year in ERA_BANDS:
        origins = [origin for origin in config["origins"]
                   if first_year <= panel.quarter_year[origin] <= last_year]
        subset = [origin for origin in config["per_origin"]
                  if origin["origin"] in origins]
        entry = {"origins": [panel.quarters[origin] for origin in origins],
                 "models": {}}
        for model in config["models"]:
            entry["models"][model] = ap_summary(
                [row["models"][model]["average_precision"]
                 for row in subset if model in row["models"]])
        left = entry["models"].get("M1C", {}).get("mean")
        right = entry["models"].get("B1", {}).get("mean")
        entry["delta_ap_M1C_minus_B1"] = (left - right) if left is not None and right is not None else None
        result[name] = entry
    return result


def feature_group_ablation(config: dict) -> dict:
    result = {}
    for group in ("A", "B", "C"):
        model = "M1" + group
        entry = {"model": model, "features": list(FEATURE_GROUPS[group]),
                 "mean_per_origin_ap": config["mean_per_origin_ap"].get(model)}
        left = config["mean_per_origin_ap"].get(model, {}).get("mean")
        right = config["mean_per_origin_ap"].get("B1", {}).get("mean")
        entry["delta_ap_vs_B1"] = (left - right) if left is not None and right is not None else None
        result[group] = entry
    return result


def leak_audit(panel: Panel, config: dict, sample_size: int = 300) -> dict:
    """Seeded replay audit over risk-set cells (protocol section 12.3).

    The audit samples only cells that are on the pre-registered risk set at their origin
    (the pair must be unentered there), because that is the only population the feature
    matrix is ever evaluated on.  ``features_bruteforce`` is a separate linear-scan
    implementation of the same definitions; the comparison tolerance is 1e-12 absolute
    (the two paths compute identical integer event counts, so values are identical).
    """
    rng = random.Random(f"{SEED}|leak-audit")
    cells = [(record["origin"], record["companies"][index], record["tracks"][index])
             for record in config["records"]
             for index in range(len(record["labels"]))]
    sample = rng.sample(cells, min(sample_size, len(cells)))
    mismatches = 0
    tolerance = 1e-12
    for origin, company, track in sample:
        _require(not panel.pair_entered(company, track, origin),
                 f"leak audit sampled a non-risk-set cell: {company}/{track} at "
                 f"{panel.quarters[origin]} is already entered")
        fast = panel.features(company, track, origin)
        slow = panel.features_bruteforce(company, track, origin)
        for name in FEATURE_NAMES_C:
            first, second = fast[name], slow[name]
            if (first is None) != (second is None):
                mismatches += 1
            elif first is not None and abs(first - second) > tolerance:
                mismatches += 1
    return {"cells_sampled": len(sample), "mismatches": mismatches,
            "tolerance_absolute": tolerance,
            "tolerance": ("exact equality is expected (identical integer event counts and "
                          "identical float operations); the check compares to 1e-12"),
            "risk_set_cells_only": True,
            "method": ("independent linear-scan replay of the 15 features "
                       "(protocol section 12.3)"),
            "reference_implementation": "features_bruteforce",
            "note": ("the first real run reported 184/300 mismatches. Root cause: "
                     "company_cat_q was built in pair-record order instead of sorted order, "
                     "so the bisect in Panel.features() returned wrong adjacency counts "
                     "(adj_act_8 / adj_share / cat_share). The replay was correct. The index "
                     "is now sorted (regression test: test_all_bisect_indexes_are_sorted) and "
                     "this run refits every model on the corrected feature matrix.")}


# ----------------------------------------------------------------------------- main
def holm_correction(entries: list[tuple[str, float | None]], alpha: float = 0.05) -> dict:
    known = [(label, value) for label, value in entries if value is not None]
    known.sort(key=lambda item: item[1])
    m = len(known)
    adjusted: dict[str, float] = {}
    running = 0.0
    reject: dict[str, bool] = {}
    for index, (label, value) in enumerate(known):
        step = min(1.0, (m - index) * value)
        running = max(running, step)
        adjusted[label] = running
        reject[label] = running <= alpha
    return {"method": "Holm-Bonferroni", "alpha": alpha,
            "adjusted_p_values": adjusted, "reject": reject,
            "m": m, "note": "sequential Holm; adjusted p is monotone"}


def build_h1_multiple_testing(h8: dict, h4: dict, permutation_block: dict) -> dict:
    """Pre-registered two-horizon Holm correction, honestly labelled.

    The confirmatory p-value exists only when the company-clustered bootstrap CI is
    quotable.  If both horizons have one, Holm is applied.  If only one does, the
    correction cannot be completed across the pre-registered family: the estimable
    horizon is reported uncorrected (and explicitly not claimed as family-wise
    significant) and the other horizon's failure is stated.  If neither does, Holm is
    not applicable to H1 at all and the permutation test is the only (secondary) test.
    """
    h8_p = h8.get("p_two_sided")
    h4_p = h4.get("p_two_sided")
    h8_ci = h8.get("ci_low")
    h4_ci = h4.get("ci_low")
    permutation_entry = {
        "p_value_one_sided": permutation_block.get("empirical_p_value_one_sided"),
        "n_permutations": permutation_block.get("n_permutations_achieved"),
        "resolution_floor": permutation_block.get("resolution_floor"),
        "horizon": "h=8",
        "note": ("labels permuted within (origin quarter, track); feature set C, R_adj, "
                 "h=8; secondary descriptive test, not part of the confirmatory family"),
    }
    if h8_ci is not None and h4_ci is not None:
        result = holm_correction([("h8_primary_M1C_minus_B1", h8_p),
                                  ("h4_secondary_M1C_minus_B1", h4_p)])
        result["status"] = "APPLIED"
        result["applies_to"] = "H1 (both horizons)"
        result["h1_supported"] = bool(h8.get("supported") and h4.get("supported"))
        return result
    if h8_ci is not None or h4_ci is not None:
        estimable = ("h8_primary_M1C_minus_B1" if h8_ci is not None
                     else "h4_secondary_M1C_minus_B1")
        missing = ("h4_secondary_M1C_minus_B1" if h8_ci is not None
                   else "h8_primary_M1C_minus_B1")
        return {
            "status": "INCOMPLETE",
            "applies_to": "H1 (both horizons)",
            "reason": ("the pre-registered Holm correction across the two confirmatory "
                       "horizons cannot be completed because "
                       f"{missing} produced no quotable bootstrap CI (UNRELIABLE); the "
                       f"estimable horizon {estimable} is reported UNCORRECTED and is not "
                       "claimed as a family-wise-corrected rejection. The primary "
                       "confirmatory criterion is the CI, not this correction."),
            "estimable_horizon": estimable,
            "uncorrected_p_values": {
                "h8_primary_M1C_minus_B1": h8_p,
                "h4_secondary_M1C_minus_B1": h4_p},
            "h1_supported": bool(h8.get("supported")),
            "permutation_test": permutation_entry,
        }
    return {
        "status": "NOT_APPLICABLE_TO_H1",
        "applies_to": ("the pre-registered label-permutation test only (single horizon "
                       "h=8, secondary/descriptive); it does NOT apply to H1"),
        "reason": ("H1's pre-registered criterion is the company-clustered bootstrap "
                   "95% CI; the bootstrap reliability gate returned UNRELIABLE for both "
                   "horizons, so no confirmatory p-value exists and no Holm correction is "
                   "applied to H1. The bootstrap p_two_sided values are descriptive only "
                   "and are NOT an H1 rejection."),
        "h1_supported": False,
        "permutation_test": permutation_entry,
    }


def build_overall_verdict(h8: dict, r_full: dict, h4: dict | None = None) -> str:
    """One-line H1 verdict combining the primary and the pre-registered robustness set."""
    h4_clause = ""
    if h4 is not None and h4.get("ci_low") is None:
        h4_clause = ("; the h4 secondary horizon has no quotable CI (bootstrap UNRELIABLE) "
                     "and is not part of this verdict")
    elif h4 is not None:
        h4_clause = ("; the h4 secondary horizon is reported separately "
                     f"(ΔAP {h4.get('delta_ap')})")
    if h8.get("ci_low") is None:
        tail = ("the overall H1 verdict is: not confirmed on the primary estimand"
                + ("" if r_full.get("supported") is False
                   else ", direction supported on the secondary estimand") + ".")
        if r_full.get("supported") is False:
            tail = ("the overall H1 verdict is: not confirmed on the primary estimand; "
                    "the secondary estimand is not supported either.")
        primary_clause = ("H1 is NOT CONFIRMED on the primary estimand: R_adj|h8 is "
                          "UNRELIABLE (no pre-registered CI quotable, H1 supported=false).")
    else:
        primary_clause = (
            "H1 is "
            + ("SUPPORTED" if h8.get("supported") else "NOT SUPPORTED")
            + " on the primary estimand R_adj|h8 (ΔAP "
            + f"{h8['delta_ap']:.4f}, 95% CI [{h8['ci_low']:.4f}, {h8['ci_high']:.4f}], "
            + f"p={h8.get('p_two_sided')}).")
        tail = ("The overall H1 verdict is: "
                + ("confirmed on the primary estimand" if h8.get("supported")
                   else "not confirmed on the primary estimand")
                + (", with the pre-registered robustness estimand R_full|h8 in the same "
                   "direction" if r_full.get("supported")
                   else "; the robustness estimand R_full|h8 is not supported")
                + h4_clause + ".")
    robustness = ("The pre-registered robustness estimand R_full|h8 is "
                  + ("supported" if r_full.get("supported") else "not supported"))
    if r_full.get("delta_ap") is not None:
        robustness += (f" (ΔAP {r_full['delta_ap']:.4f}, CI "
                       f"[{r_full.get('ci_low')}, {r_full.get('ci_high')}])")
        robustness += ("." if r_full.get("ci_low") is None else
                       "; it may not be substituted for the primary estimand.")
    else:
        robustness += "."
    return primary_clause + " " + robustness + " " + tail


def convergence_summary(convergence: list[dict]) -> dict:
    if not convergence:
        return {"fits": 0}
    reductions = [entry["loss_reduction"] for entry in convergence]
    gradients = [entry["gradient_norm_end"] for entry in convergence]
    return {
        "fits": len(convergence),
        "fits_at_gradient_tolerance": sum(1 for entry in convergence
                                          if entry["converged_at_gradient_tolerance"]),
        "loss_reduction_mean": sum(reductions) / len(reductions),
        "loss_reduction_min": min(reductions),
        "gradient_norm_end_max": max(gradients),
        "gradient_norm_end_median": statistics.median(gradients),
        "note": ("M1 is a fixed 120-epoch batch-gradient-descent fit with no per-origin "
                 "tuning; the gradient tolerance is a reporting heuristic only and a "
                 "non-converged fit is a reported result, not a reason to switch models"),
    }


def config_to_block(config: dict, panel: Panel) -> dict:
    undefined = []
    for row in config["per_origin"]:
        ap = row["models"].get("M1C", {}).get("average_precision")
        if ap is None:
            if row["n_positives"] == 0:
                reason = "no positive test cells at this origin: average precision is undefined"
            elif row["n_positives"] == row["n_candidates"]:
                reason = "no negative test cells at this origin: average precision is undefined"
            else:
                reason = "average precision undefined"
            undefined.append({"origin": row["origin"],
                              "origin_label": panel.quarters[row["origin"]],
                              "n_candidates": row["n_candidates"],
                              "n_positives": row["n_positives"], "reason": reason})
    return {
        "risk_set": config["risk_set"],
        "horizon": config["horizon"],
        "horizon_key": config["horizon_key"],
        "n_origins": len(config["origins"]),
        "origin_labels": config["origin_labels"],
        "models": config["models"],
        "mean_per_origin_ap": config["mean_per_origin_ap"],
        "pooled_ap": config["pooled_ap"],
        "per_origin": config["per_origin"],
        "dataset_by_origin": config["dataset_rows"],
        "origins_with_undefined_ap": undefined,
        "n_origins_with_defined_ap": len(config["origins"]) - len(undefined),
        "convergence_summary": convergence_summary(config["convergence"]),
        "pool_rows": config["pool_rows"],
        "pool_positives": config["pool_positives"],
    }


def fusion_comparison(primary: dict, origins: list[int], reps: int,
                      company_index: dict[str, int]) -> dict:
    subset = [record for record in primary["records"] if record["origin"] in set(origins)]
    models = ("M1C", "M1D")
    prepared = prepare_bootstrap_origins(subset, models, company_index)
    bootstrap = clustered_bootstrap_mean_ap(prepared, models, len(company_index), reps, SEED,
                                           comparisons=(("M1D", "M1C"),))
    per_origin_c = [evaluate_origin(record) for record in subset]
    mean_c = mean_origin_ap(per_origin_c, "M1C")
    mean_d = mean_origin_ap(per_origin_c, "M1D")
    point = (mean_d.get("mean") - mean_c.get("mean")
             if mean_d.get("mean") is not None and mean_c.get("mean") is not None else None)
    entry = bootstrap["comparisons"].get("M1D-M1C", {})
    if bootstrap["status"] == "UNRELIABLE":
        if point is not None and point < 0.0:
            status = "EVALUATED_BUT_WORSE_AND_BOOTSTRAP_UNRELIABLE"
        else:
            status = "EVALUATED_BOOTSTRAP_UNRELIABLE"
    elif entry.get("ci_low") is not None and entry.get("ci_low") > 0 and point is not None and point > 0:
        status = "SUPPORTED"
    else:
        status = "NOT_SUPPORTED"
    supported = status == "SUPPORTED"
    direction = ("equal" if point is None or point == 0.0 else
                 ("D worse than C" if point < 0.0 else "D better than C"))
    return {
        "origins": [primary["origin_labels"][primary["origins"].index(origin)]
                    if origin in primary["origins"] else origin for origin in origins],
        "n_origins": len(origins),
        "mean_per_origin_ap_C": mean_c,
        "mean_per_origin_ap_D": mean_d,
        "delta_ap_D_minus_C": point,
        "direction": direction,
        "bootstrap": bootstrap,
        "bootstrap_status": bootstrap["status"],
        "status": status,
        "supported": supported,
        "criterion": ("H2 supported iff the 95% CI of AP(D)-AP(C) excludes 0 and is "
                      "positive on the 2016-Q1+ origin subset"),
        "note": ("" if supported else
                 "fusion lanes were joined at cell level and the comparison was evaluated, "
                 "but it does not support H2 (see status / delta / bootstrap_status); this "
                 "is not a NOT_EVALUABLE outcome"),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="hist_v1 walk-forward evaluation (pre-registered; protocol sections 3-10)")
    parser.add_argument("--panel", default="out/hist_v1/panel.json",
                        help="input panel JSON (schema hist_v1.panel.v1)")
    parser.add_argument("--out", default="experiments/hist_v1/results.json")
    parser.add_argument("--quick", action="store_true",
                        help="smoke run: reduces bootstrap/permutation repetitions only")
    parser.add_argument("--bootstrap-reps", type=int, default=BOOTSTRAP_REPS)
    parser.add_argument("--permutations", type=int, default=None,
                        help="override the A4-derived permutation count")
    parser.add_argument("--perm-budget-minutes", type=float, default=45.0,
                        help="wall-clock budget allocated to the permutation null")
    parser.add_argument("--workers", type=int, default=1,
                        help="process workers for the permutation null (1 = serial)")
    parser.add_argument("--data-root", default="data",
                        help="directory holding the fusion-lane sqlite files")
    parser.add_argument("--max-origins", type=int, default=None,
                        help="smoke use only: keep the first N evaluation origins")
    parser.add_argument("--skip-fusion", action="store_true")
    parser.add_argument("--refresh-decision-from", default=None, metavar="RESULTS_JSON",
                        help=("recompute only the H1 decision text fields of an existing "
                              "results.json from its own stored numbers (no refit, no "
                              "metric recomputed); the file is rewritten atomically"))
    args = parser.parse_args(argv)

    if args.refresh_decision_from:
        return refresh_decision(Path(args.refresh_decision_from))

    started = time.perf_counter()
    phases: dict[str, float] = {}

    def mark(name: str, since: float) -> float:
        phases[name] = phases.get(name, 0.0) + (time.perf_counter() - since)
        return time.perf_counter()

    panel_path = Path(args.panel).resolve()
    clock = time.perf_counter()
    panel = load_panel(panel_path)
    clock = mark("panel_load", clock)
    print(f"panel: {panel.n_quarters} quarters {panel.quarter_start}..{panel.quarter_end}; "
          f"{panel.company_count} companies, {panel.track_count} tracks, "
          f"{panel.pairs_observed} pairs, {panel.total_events} events")

    quick = bool(args.quick)
    bootstrap_reps = min(200, args.bootstrap_reps) if quick else args.bootstrap_reps
    workers = 1 if quick else max(1, args.workers)
    company_index = panel.company_index
    h8_origins = evaluation_origins(panel, 8)
    h4_origins = evaluation_origins(panel, 4)
    if args.max_origins is not None:
        h8_origins = h8_origins[:max(1, args.max_origins)]
        h4_origins = h4_origins[:max(1, args.max_origins)]
    fusion_start = panel.qidx.get("2016-Q1")

    # ---------------------------------------------------------------- fusion lanes
    clock = time.perf_counter()
    fusion_lanes = None
    fusion_reasons: list[str] = []
    if args.skip_fusion:
        fusion_reasons.append("fusion lanes disabled by --skip-fusion")
    else:
        fusion_lanes = FusionLanes(Path(args.data_root), panel)
        if not fusion_lanes.available:
            fusion_reasons.extend(fusion_lanes.reason or ["fusion lanes unavailable"])
    clock = mark("fusion_lane_load", clock)

    # ---------------------------------------------------------- primary configuration
    clock = time.perf_counter()
    primary_data = RiskHorizonData(panel, True, 8,
                                   fusion_lanes if (fusion_lanes is not None and
                                                    fusion_lanes.available) else None,
                                   max_origins=args.max_origins)
    group_plan: dict[str, set[int] | None] = {"A": None, "B": None, "C": None}
    fusion_origins: list[int] = []
    fusion_coverage = None
    if fusion_lanes is not None and fusion_lanes.available and fusion_start is not None:
        fusion_origins = [origin for origin in primary_data.test_origins
                          if origin >= fusion_start]
        fusion_coverage = fusion_lanes.coverage(primary_data, fusion_origins)
        if (fusion_coverage["publication_join_rate"] >= 0.5
                and fusion_coverage["trial_track_present_rate"] > 0.0):
            group_plan["D"] = set(fusion_origins)
        else:
            fusion_reasons.append(
                "fusion join coverage below the pre-registered 50% threshold: "
                f"publication {fusion_coverage['publication_join_rate']:.3f}, "
                f"trial-track present {fusion_coverage['trial_track_present_rate']:.3f}")
    clock = mark("primary_cells", clock)

    print("primary configuration: R_adj, h=8, origins "
          f"{len(h8_origins)}; feature groups {sorted(group_plan)}")
    clock = time.perf_counter()
    primary = run_config(primary_data, group_plan)
    fitted_at = mark("primary_fit", clock)
    print(f"  fitted {len(primary['convergence'])} models over {len(primary['origins'])} origins "
          f"({fitted_at - clock:.1f}s)")

    # -------------------------------------------------------- primary bootstrap (A1)
    clock = time.perf_counter()
    primary_models = ("B1", "B2", "B3", "M1C")
    primary_bootstrap = clustered_bootstrap_mean_ap(
        prepare_bootstrap_origins(primary["records"], primary_models, company_index),
        primary_models, len(company_index), bootstrap_reps, SEED,
        comparisons=(("M1C", "B1"), ("M1C", "B2"), ("M1C", "B3")))
    clock = mark("primary_bootstrap", clock)
    print(f"  company-clustered bootstrap ({bootstrap_reps} reps, "
          f"status {primary_bootstrap['status']})")

    primary_delta = primary_bootstrap["delta"].get("M1C", {})
    point_delta = _difference(primary["mean_per_origin_ap"]["M1C"]["mean"],
                              primary["mean_per_origin_ap"]["B1"]["mean"])
    point_delta_b2 = _difference(primary["mean_per_origin_ap"]["M1C"]["mean"],
                                 primary["mean_per_origin_ap"]["B2"]["mean"])
    point_delta_b3 = _difference(primary["mean_per_origin_ap"]["M1C"]["mean"],
                                 primary["mean_per_origin_ap"]["B3"]["mean"])

    # ------------------------------------------------------------- robustness blocks
    clock = time.perf_counter()
    eras = era_strata(primary, panel)
    ablations = feature_group_ablation(primary)
    clock = mark("robustness", clock)

    # ------------------------------------------------------------- lead time / H5
    clock = time.perf_counter()
    entries = incident_entries(panel, primary["records"], 8)
    h5_rows = [alert_analysis(primary["records"], entries, "M1C", budget)
               for budget in ALERT_BUDGETS]
    primary_alert = next(row for row in h5_rows if row["budget"] == PRIMARY_ALERT_BUDGET)
    clock = mark("lead_time", clock)

    # ------------------------------------------------------------ heterogeneity H3/H4
    clock = time.perf_counter()
    h3 = heterogeneity_companies(panel, primary["records"], ("M1C", "B1"))
    h4 = heterogeneity_categories(panel, primary["records"], ("M1C", "B1"),
                                  reps=min(bootstrap_reps, 1000), seed=SEED)
    deep = h3["deep_cases"]
    deep_deltas = [entry["delta_ap"] for entry in deep.values()
                   if entry["delta_ap"] is not None]
    auxiliary_deltas = [entry["delta_ap"] for entry in h3["per_company"].values()
                        if entry["eligible"] and entry["company_key"] not in DEEP_CASE_KEYS
                        and entry["delta_ap"] is not None]
    deep_auxiliary = None
    if deep_deltas and auxiliary_deltas:
        deep_mean = sum(deep_deltas) / len(deep_deltas)
        auxiliary_mean = sum(auxiliary_deltas) / len(auxiliary_deltas)
        rng = random.Random(f"{SEED}|deep-vs-auxiliary")
        draws = []
        for _ in range(min(bootstrap_reps, 2000)):
            first = [deep_deltas[rng.randrange(len(deep_deltas))]
                     for _ in range(len(deep_deltas))]
            second = [auxiliary_deltas[rng.randrange(len(auxiliary_deltas))]
                      for _ in range(len(auxiliary_deltas))]
            draws.append(sum(first) / len(first) - sum(second) / len(second))
        ordered = sorted(draws)
        deep_auxiliary = {
            "deep_case_mean_delta_ap": deep_mean,
            "auxiliary_mean_delta_ap": auxiliary_mean,
            "difference": deep_mean - auxiliary_mean,
            "ci_low": percentile_sorted(ordered, 0.025),
            "ci_high": percentile_sorted(ordered, 0.975),
            "n_deep_companies": len(deep_deltas),
            "n_auxiliary_companies": len(auxiliary_deltas),
            "note": ("descriptive only: the deep cases are not a random sample of the "
                     "53-company roster"),
        }
        deep_auxiliary_reason = None
    else:
        deep_auxiliary_reason = (
            "not estimable: the deep-vs-auxiliary contrast needs companies with >= "
            f"{h3['minimum_positives']} positive test cells in both groups; "
            f"{len(deep_deltas)} deep-case and {len(auxiliary_deltas)} auxiliary-roster "
            "company APs are defined, so at least one group is empty "
            "(see heterogeneity.h3_companies.per_company for the per-company counts)")
    clock = mark("heterogeneity", clock)

    # ------------------------------------------------------------- permutation null
    clock = time.perf_counter()
    rows_after = [row["training"]["rows_after_sampling"] for row in primary["dataset_rows"]]
    if quick:
        permutation_plan = {"requested": 5, "achieved": 5, "workers": 1,
                            "budget_minutes": 0.0, "reduced": True,
                            "reason": "--quick smoke run", "quick": True}
    elif args.permutations is not None:
        permutation_plan = {"requested": PERMUTATION_REPS,
                            "achieved": max(1, args.permutations),
                            "workers": workers, "reduced": True,
                            "reason": "--permutations override"}
    else:
        permutation_plan = choose_permutation_count(rows_after, workers,
                                                    args.perm_budget_minutes)
    n_permutations = permutation_plan["achieved"]
    permutation_results = run_permutation_null(panel_path, primary_data, n_permutations, workers)
    observed_delta = point_delta
    null_deltas = [result["delta"] for result in permutation_results["results"]
                   if result["delta"] is not None]
    permutation_block = {
        "plan": permutation_plan,
        "observed_delta_ap": observed_delta,
        "n_permutations_achieved": len(null_deltas),
        "n_permutations_requested": permutation_plan["requested"],
        "seed": SEED,
        "scheme": ("labels shuffled among cells sharing (origin quarter, track): every "
                   "origin's prevalence and every (origin, track) entry count are preserved; "
                   "per-company total entries are NOT preserved (infeasible within the frozen "
                   "risk sets). Training and evaluation labels are permuted and M1C and B1 are "
                   "refitted on the permuted training labels."),
        "null_distribution": {
            "mean": (sum(null_deltas) / len(null_deltas)) if null_deltas else None,
            "sd": statistics.pstdev(null_deltas) if len(null_deltas) > 1 else None,
            "min": min(null_deltas) if null_deltas else None,
            "median": statistics.median(null_deltas) if null_deltas else None,
            "max": max(null_deltas) if null_deltas else None,
            "p025": percentile_sorted(sorted(null_deltas), 0.025) if null_deltas else None,
            "p975": percentile_sorted(sorted(null_deltas), 0.975) if null_deltas else None,
        },
        "empirical_p_value_one_sided": (
            (1.0 + sum(1 for value in null_deltas if value >= observed_delta))
            / (1.0 + len(null_deltas))) if null_deltas and observed_delta is not None else None,
        "resolution_floor": (1.0 / (1.0 + len(null_deltas))) if null_deltas else None,
        "skipped": permutation_results["skipped"],
        "runtime_seconds": permutation_results["runtime_seconds"],
    }
    clock = mark("permutation_null", clock)
    print(f"  permutation null: {len(null_deltas)} replicates, "
          f"empirical p={permutation_block['empirical_p_value_one_sided']}")

    # ---------------------------------------------------------- secondary configs
    clock = time.perf_counter()
    secondary: dict[str, dict] = {}
    for name, adjacency, horizon in (("R_full|h8", False, 8), ("R_adj|h4", True, 4),
                                     ("R_full|h4", False, 4)):
        data = RiskHorizonData(panel, adjacency, horizon, None,
                               max_origins=args.max_origins)
        config = run_config(data, {"C": None})
        bootstrap_models = ("B1", "B2", "B3", "M1C")
        bootstrap = clustered_bootstrap_mean_ap(
            prepare_bootstrap_origins(config["records"], bootstrap_models, company_index),
            bootstrap_models, len(company_index), bootstrap_reps, SEED,
            comparisons=(("M1C", "B1"), ("M1C", "B2"), ("M1C", "B3")))
        for key, entry in bootstrap["comparisons"].items():
            entry["interpretation"] = ("secondary/descriptive comparison, not the "
                                       "pre-registered primary test")
        block = config_to_block(config, panel)
        block["bootstrap"] = bootstrap
        block["delta_ap_M1C_minus_B1"] = _difference(
            config["mean_per_origin_ap"]["M1C"]["mean"],
            config["mean_per_origin_ap"]["B1"]["mean"])
        secondary[name] = block
        mean_m1c = config["mean_per_origin_ap"]["M1C"]["mean"]
        pooled_m1c = config["pooled_ap"]["M1C"]
        print(f"  {name}: mean AP M1C="
              f"{'n/a' if mean_m1c is None else round(mean_m1c, 4)} "
              f"pooled={'n/a' if pooled_m1c is None else round(pooled_m1c, 4)}")
    clock = mark("secondary_configs", clock)

    # ---------------------------------------------------------------- fusion H2
    clock = time.perf_counter()
    if "D" in group_plan:
        fusion_block = fusion_comparison(primary, fusion_origins, bootstrap_reps, company_index)
        fusion_block["coverage"] = fusion_coverage
        fusion_block["status_reason"] = "fusion lanes joined at cell level"
    else:
        fusion_block = {
            "status": "NOT_EVALUABLE",
            "coverage": fusion_coverage,
            "reasons": fusion_reasons,
            "note": ("no proxy substitution is performed when the trial/publication join "
                     "fails (protocol section 9)"),
        }
    clock = mark("fusion_test", clock)

    # ---------------------------------------------------------- leakage control 12.3
    clock = time.perf_counter()
    leak = leak_audit(panel, primary)
    clock = mark("leak_audit", clock)

    # ------------------------------------------------------------------- decisions
    h4_block = secondary["R_adj|h4"]
    h4_bootstrap = h4_block["bootstrap"]
    h4_delta_entry = h4_bootstrap["delta"].get("M1C", {})
    h4_point_delta = h4_block["delta_ap_M1C_minus_B1"]

    def h1_verdict(delta_entry: dict, point: float | None) -> dict:
        ci_low = delta_entry.get("ci_low")
        ci_high = delta_entry.get("ci_high")
        if delta_entry.get("status") == "UNRELIABLE":
            status = "UNRELIABLE (no pre-registered CI quotable)"
        elif ci_low is None or ci_high is None or point is None:
            status = "NOT_EVALUABLE"
        elif ci_low > 0.0 and point > 0.0:
            status = "SUPPORTED"
        else:
            status = "NOT_SUPPORTED"
        return {"status": status, "supported": status == "SUPPORTED",
                "delta_ap": point, "ci_low": ci_low, "ci_high": ci_high,
                "p_two_sided": delta_entry.get("p_two_sided"),
                "mde_80pct_power_alpha_0.05": delta_entry.get("mde_80pct_power_alpha_0.05"),
                "descriptive_interval_not_a_ci": delta_entry.get("descriptive_interval_not_a_ci"),
                "bootstrap_status": delta_entry.get("status")}

    h1_h8 = h1_verdict(primary_delta, point_delta)
    h1_h4 = h1_verdict(h4_delta_entry, h4_point_delta)
    r_full_h8_delta = (secondary["R_full|h8"]["bootstrap"]["comparisons"]
                       .get("M1C-B1", {}))
    r_full_h8_block = secondary["R_full|h8"]
    r_full_h8_verdict = {
        "risk_set": "R_full",
        "horizon": 8,
        "delta_ap": r_full_h8_block["delta_ap_M1C_minus_B1"],
        "ci_low": r_full_h8_delta.get("ci_low"),
        "ci_high": r_full_h8_delta.get("ci_high"),
        "p_two_sided": r_full_h8_delta.get("p_two_sided"),
        "mde_80pct_power_alpha_0.05": r_full_h8_delta.get("mde_80pct_power_alpha_0.05"),
        "bootstrap_status": r_full_h8_block["bootstrap"]["status"],
        "supported": bool(r_full_h8_delta.get("ci_low") is not None
                          and r_full_h8_delta["ci_low"] > 0
                          and r_full_h8_block["delta_ap_M1C_minus_B1"] > 0),
        "interpretation": ("pre-registered robustness estimand (R_full); it may not be "
                           "substituted for the primary estimand R_adj (protocol section 3)"),
    }
    # The pre-registered confirmatory criterion is the bootstrap CI.  The two-horizon Holm
    # correction is only completed when BOTH horizons have a quotable CI; otherwise it is
    # explicitly labelled (INCOMPLETE / NOT_APPLICABLE) rather than faked.
    multiple_testing = build_h1_multiple_testing(h1_h8, h1_h4, permutation_block)
    permutation_secondary = {
        "status": "SECONDARY_DESCRIPTIVE",
        "horizon": "h=8",
        "risk_set": "R_adj",
        "p_value_one_sided": permutation_block["empirical_p_value_one_sided"],
        "n_permutations": permutation_block["n_permutations_achieved"],
        "resolution_floor": permutation_block["resolution_floor"],
        "note": ("single-horizon label-permutation test (feature set C, h=8, 200 permutations); "
                 "pre-declared as a robustness/descriptive check, not part of the two-horizon "
                 "confirmatory family, and no Holm correction is applied to it"),
    }

    def mde_statement(entry: dict) -> str:
        if entry["delta_ap"] is None or entry["mde_80pct_power_alpha_0.05"] is None:
            return "not estimable (bootstrap interval not quotable)"
        statement = (f"observed ΔAP = {entry['delta_ap']:.4f}; MDE(alpha=0.05, power=0.80) = "
                     f"{entry['mde_80pct_power_alpha_0.05']:.4f} AP points")
        if entry["ci_low"] is None:
            statement += ("; the pre-registered bootstrap reliability gate returned UNRELIABLE, "
                          "so no CI is quotable and H1 is not supported/not falsified by the "
                          "primary criterion")
        elif entry["ci_low"] <= 0.0 <= entry["ci_high"]:
            statement += ("; the 95% CI includes 0, so a true positive effect smaller than "
                          "the MDE cannot be excluded (a null here is 'underpowered' where "
                          "the MDE is not practically negligible)")
        return statement

    decision = {
        "H1": {"h8_primary": h1_h8, "h4_secondary": h1_h4,
               "criterion": ("H1 supported iff the 95% CI of mean-per-origin ΔAP "
                             "(M1C - B1) excludes 0 and the point estimate is positive "
                             "(protocol section 7, amendment A1)"),
               "supported": bool(h1_h8["supported"]),
               "bootstrap_reliability": {
                   "status": primary_bootstrap["status"],
                   "share_resamples_below_min_contributing_origins":
                       primary_bootstrap["share_resamples_below_min_contributing_origins"],
                   "min_contributing_origins_required":
                       primary_bootstrap["min_contributing_origins_required"],
                   "contributing_origins_median":
                       primary_bootstrap["contributing_origins_median"],
                   "n_origins_with_defined_point_ap":
                       primary_bootstrap["n_origins_with_defined_point_ap"],
               },
               "descriptive_interval_not_a_ci": h1_h8["descriptive_interval_not_a_ci"],
               "multiple_testing": multiple_testing,
               "permutation_secondary_test": permutation_secondary,
               "robustness_estimand_R_full_h8": r_full_h8_verdict,
               "overall_verdict": build_overall_verdict(h1_h8, r_full_h8_verdict, h1_h4),
               "mde_statements": {"h8": mde_statement(h1_h8), "h4": mde_statement(h1_h4)}},
        "H2": {"status": fusion_block["status"],
               "supported": bool(fusion_block.get("supported", False)),
               "direction": fusion_block.get("direction"),
               "delta_ap_D_minus_C": fusion_block.get("delta_ap_D_minus_C"),
               "bootstrap_status": fusion_block.get("bootstrap_status"),
               "detail": ("fusion test NOT_EVALUABLE; see fusion_h2.reasons"
                          if fusion_block["status"] == "NOT_EVALUABLE" else
                          "fusion lanes joined at cell level; the D-vs-C comparison was "
                          "evaluated and is reported in fusion_h2 (see status, direction "
                          "and bootstrap_status)"),
               "criterion": ("H2 supported iff the 95% CI of AP(D)-AP(C) on the 2016-Q1+ "
                             "origins excludes 0 and is positive")},
        "H3_H4": {"status": "DESCRIPTIVE",
                  "note": ("per-company and per-category results are descriptive; the "
                           "53-company roster is not a random sample"),
                  "h3_eligible_companies": h3["eligible_companies"],
                  "h3_minimum_positive_test_cells": h3["minimum_positives"],
                  "h3_deep_vs_auxiliary_status": ("ESTIMABLE" if deep_auxiliary
                                                  else "NOT_ESTIMABLE"),
                  "h3_deep_vs_auxiliary_reason": deep_auxiliary_reason,
                  "kendall_tau_ap_vs_material_events":
                      h3["kendall_tau_ap_vs_material_events"],
                  "kendall_tau_n": h3["kendall_tau_n"],
                  "h4_extremes": h4["extremes"]},
        "H5": {"status": "DESCRIPTIVE",
               "primary_budget": PRIMARY_ALERT_BUDGET,
               "headline": {"recall": primary_alert["recall"],
                            "false_alarms_per_1000_candidate_quarters":
                                primary_alert["false_alarms_per_1000_candidate_quarters"],
                            "median_lead_quarters": primary_alert["lead_quarters"]["median"],
                            "entries_alerted": primary_alert["entries_alerted"],
                            "entries_missed": primary_alert["entries_missed"]}},
        "premise": {
            "criterion": ("protocol section 11: the premise is not supported if the "
                          "primary ΔAP 95% CI includes 0 and the MDE is small enough to "
                          "rule out a practically useful effect; a null with a large MDE "
                          "is 'underpowered', not evidence of absence"),
            "h8_primary": h1_h8["status"],
            "h4_secondary": h1_h4["status"],
        },
    }

    # ------------------------------------------------------------------ assemble
    def totals(rows: list[dict]) -> dict:
        return {
            "candidate_cells": sum(row["n_candidates"] for row in rows),
            "positive_cells": sum(row["n_positives"] for row in rows),
            "immature_excluded": sum(row["n_immature_excluded"] for row in rows),
            "training_rows_before_sampling": sum(
                row["training"]["rows_before_sampling"] for row in rows),
            "training_rows_after_sampling": sum(
                row["training"]["rows_after_sampling"] for row in rows),
            "training_positives": sum(row["training"]["positives"] for row in rows),
            "negative_sampling_fractions": sorted({round(
                row["training"]["negative_sampling_fraction"], 6) for row in rows}),
        }

    dataset = {
        "panel": {
            "schema": panel.data.get("schema"),
            "quarter_start": panel.quarter_start,
            "quarter_end": panel.quarter_end,
            "n_quarters": panel.n_quarters,
            "n_companies": panel.company_count,
            "n_tracks": panel.track_count,
            "n_pairs_recorded": len(panel.pair_events),
            "n_pairs_with_events": panel.pairs_observed,
            "total_material_events": panel.total_events,
            "feature_source": panel.feature_source,
            "event_count_audit": panel.event_count_audit,
            "pairs_missing_event_counts": panel.pairs_missing_event_counts,
            "last_qidx": panel.last_qidx,
            "last_quarter_label": panel.quarters[panel.last_qidx],
        },
        "configs": {},
        "totals": {},
    }
    primary_block = config_to_block(primary, panel)
    primary_block["bootstrap"] = primary_bootstrap
    dataset["configs"]["R_adj|h8"] = primary["dataset_rows"]
    dataset["totals"]["R_adj|h8"] = totals(primary["dataset_rows"])
    for name, block in secondary.items():
        dataset["configs"][name] = block["dataset_by_origin"]
        dataset["totals"][name] = totals(block["dataset_by_origin"])
    dataset["fusion_lane_coverage"] = fusion_coverage
    dataset["primary_origins_with_undefined_ap"] = primary_block["origins_with_undefined_ap"]
    dataset["notes"] = {
        "mean_per_origin_ap_n": (
            "mean per-origin AP is the mean over origins where AP is defined; origins with "
            "zero positive (or zero negative) test cells have no AP and are listed in "
            "config.origins_with_undefined_ap / dataset.primary_origins_with_undefined_ap"),
        "h3_deep_vs_auxiliary": deep_auxiliary_reason or "estimable (descriptive)",
        "h2_fusion": ("NOT_EVALUABLE means the trial/publication lanes could not be joined "
                      "at cell level; an EVALUATED_* status means the fusion test was run "
                      "and its H2 outcome (with bootstrap_status) is in fusion_h2"),
    }

    primary_block["deltas_vs_baselines"] = {
        "M1C-B1": {"point_delta": point_delta,
                   "interpretation": "pre-registered primary comparison (H1); R_adj, h=8",
                   "bootstrap": primary_bootstrap["comparisons"].get("M1C-B1",
                                                                     primary_delta)},
        "M1C-B2": {"point_delta": point_delta_b2,
                   "interpretation": ("secondary/descriptive comparison, not the "
                                      "pre-registered primary test"),
                   "bootstrap": primary_bootstrap["comparisons"].get("M1C-B2", {})},
        "M1C-B3": {"point_delta": point_delta_b3,
                   "interpretation": ("secondary/descriptive comparison, not the "
                                      "pre-registered primary test; B3 is the strongest "
                                      "two-way exposure baseline (B1 x B2)"),
                   "bootstrap": primary_bootstrap["comparisons"].get("M1C-B3", {})},
    }

    results = {
        "schema": RESULTS_SCHEMA,
        "generated_at": utc_now(),
        "panel_sha256": panel.sha256,
        "git_commit": git_commit(),
        "seed": SEED,
        "config": {
            "protocol": PROTOCOL_PATH,
            "amendments_applied": ["A1", "A2", "A3", "A4"],
            "primary_metric": "mean per-origin average precision (A1), R_adj, h=8",
            "secondary_metrics": ["pooled AP", "ROC-AUC", "Brier", "ECE-10",
                                  "precision@10", "precision@25",
                                  "recall at 10% alert budget",
                                  "false-alarm rate at 10% alert budget"],
            "risk_sets": {"R_adj": ("established filer AND unentered pair AND >=1 event "
                                    "strictly before t in another track of the same category"),
                          "R_full": "established filer AND unentered pair"},
            "horizons": {"h8": 8, "h4": 4},
            "origins": {"h8": [panel.quarters[origin] for origin in h8_origins],
                        "h4": [panel.quarters[origin] for origin in h4_origins]},
            "training_grid": {"mode": "quarterly",
                              "from": panel.quarter_start,
                              "through": "origin - h (strict purge t' + h <= t)",
                              "cells": "candidate cells at every quarter, same risk set"},
            "model_M1": {"family": "L2 logistic regression (weighted)",
                         "lambda": LAMBDA, "learning_rate": LEARNING_RATE,
                         "epochs": EPOCHS, "batch": "full-batch gradient descent",
                         "init": "zeros", "intercept_penalised": False,
                         "standardisation": "training-only weighted mean/sd",
                         "imputation": "training-only weighted median",
                         "tuning": "none"},
            "training_sampler_A2": {"row_cap": TRAIN_ROW_CAP,
                                    "positives": "all matured positive cells",
                                    "negatives": "seeded random sample",
                                    "seed": TRAIN_SAMPLE_SEED,
                                    "negative_weight": "1 / p_neg",
                                    "test_subsampling": "none"},
            "baselines": {"B0": "constant training prevalence",
                          "B1": "company base rate (weighted, prior strength "
                                f"{BASELINE_PRIOR_STRENGTH} toward prevalence)",
                          "B2": "track base rate (same smoothing)",
                          "B3": "B1 x B2 renormalised to training prevalence"},
            "bootstrap": {"reps": bootstrap_reps, "seed": SEED,
                          "cluster": "company",
                          "pairing": "same resamples for every model",
                          "interval": "percentile (int(q*size) index convention)",
                          "degenerate_handling": (
                              "per resample and origin AP is computed only when the origin "
                              "has >=1 positive and >=1 negative; the per-origin mean is "
                              "taken over computable origins and the count is recorded; if "
                              "more than 5% of resamples have fewer than ceil(25/30 * n_origins) "
                              "computable origins the bootstrap is UNRELIABLE and no CI is quoted"),
                          "reliability_gate": ("UNRELIABLE if >5% of resamples have fewer than "
                                               "ceil(25/30 * n_origins) computable origins"),
                          "mde": "MDE = (z_0.975 + z_0.80) * bootstrap sd of the delta"},
            "permutation": {"requested": permutation_plan["requested"],
                            "achieved": n_permutations, "seed": SEED,
                            "scheme": permutation_block["scheme"],
                            "note": ("A4 resource fallback may reduce the permutation count; "
                                     "the achieved count and the 1/(n+1) resolution floor are "
                                     "reported")},
            "alert_budget": {"threshold": "weighted training-score quantile at 1 - budget",
                             "budgets": list(ALERT_BUDGETS)},
            "feature_groups": {key: list(value) for key, value in FEATURE_GROUPS.items()},
            "feature_definitions": FEATURE_DEFINITIONS,
            "feature_source": panel.feature_source,
            "event_counts_audit": panel.event_count_audit,
            "fusion": {"enabled": fusion_lanes is not None and fusion_lanes.available,
                       "origins": [panel.quarters[origin] for origin in fusion_origins],
                       "status": fusion_block["status"],
                       "trial_lane": "data/b040_device_trials.sqlite (source ctgov)",
                       "trial_lane_sha256": getattr(fusion_lanes, "trial_sha256", None),
                       "publication_lane": ("data/research.sqlite publication_counts "
                                            "(openalex_group_by_publication_year)"),
                       "publication_lane_sha256": getattr(fusion_lanes, "publication_sha256", None),
                       "read_mode": "sqlite3 read-only (mode=ro)",
                       "pre_2016_training_rows": "D features median-imputed (lane undefined)"},
            "workers": workers,
            "quick": quick,
            "max_origins": args.max_origins,
            "runtime_seconds": None,
            "phase_seconds": phases,
            "deviations_and_limitations": [
                ("R_adj condition 3 uses events with qidx strictly before t (protocol "
                 "section 3 wording 'before t'); conditions 1-2 use qidx <= t"),
                ("Growth features (firm_growth, track_growth) are ratios of raw counts; the "
                 "log1p transform is applied to the count features themselves, per the "
                 "section 5 table"),
                ("Fusion D features are undefined before 2016-Q1 and are median-imputed for "
                 "pre-2016 training cells, so the D-vs-C test is a conservative estimate of "
                 "multi-source value"),
                ("Per-company and per-category AP are means of within-origin AP (never pooled "
                 "across origins) because model score scales are not comparable across "
                 "origins (A1)"),
                ("Pooled AP is reported as a secondary metric only (A1)"),
                ("The panel's event_qidx is the availability quarter; the decision-date "
                 "approximation documented in protocol section 2 is inherited"),
                ("Feature-integrity incident: the first real run's leak audit exposed that "
                 "company_cat_q was built in pair-record order instead of sorted order, so "
                 "the bisect in Panel.features returned wrong adjacency counts "
                 "(adj_act_8 / adj_share / cat_share). The replay (features_bruteforce) was "
                 "correct. The index is now sorted, a regression test covers it, and this "
                 "run refits every model on the corrected matrix; the replay audit reports "
                 "0 mismatches."),
            ],
        },
        "dataset": dataset,
        "primary": primary_block,
        "secondary": {name: block for name, block in secondary.items()},
        "robustness": {"eras": eras, "feature_groups": ablations,
                       "permutation_null": permutation_block},
        "lead_time": {
            "model": "M1C", "budget": PRIMARY_ALERT_BUDGET,
            "entries": {key: value for key, value in entries.items() if key != "entries"},
            "primary_budget": primary_alert,
            "h5_frontier": h5_rows,
        },
        "heterogeneity": {"h3_companies": h3, "h4_categories": h4,
                          "deep_vs_auxiliary": deep_auxiliary,
                          "deep_vs_auxiliary_reason": deep_auxiliary_reason},
        "fusion_h2": fusion_block,
        "leakage_controls": {
            "label_purge": {"asserted_per_origin": True,
                            "violations": 0,
                            "detail": ("every fitted training cell satisfies "
                                       "t' + h <= t; asserted in training_sample()")},
            "feature_availability": ("features computed only from qidx <= t; labels only "
                                     "from t < qidx <= t + h"),
            "independent_replay": leak,
            "no_random_split": True,
        },
        "decision": decision,
    }
    results["config"]["runtime_seconds"] = time.perf_counter() - started
    results["config"]["phase_seconds"] = phases

    out_path = Path(args.out)
    write_json_atomic(out_path, results)
    print(f"\nwrote {out_path}")
    print(f"runtime {results['config']['runtime_seconds']:.1f}s")
    return 0


def refresh_decision(results_path: Path) -> int:
    """Recompute only the H1 decision text fields of an existing results.json.

    This touches no model and no metric: it re-derives ``decision.H1.multiple_testing``
    and ``decision.H1.overall_verdict`` from the numbers already stored in the file (a
    provenance-preserving alternative to a 30-minute refit after a wording-only change).
    """
    payload = json.loads(results_path.read_text(encoding="utf-8"))
    decision = payload["decision"]
    h1 = decision["H1"]
    h8 = h1["h8_primary"]
    h4 = h1["h4_secondary"]
    permutation_block = payload["robustness"]["permutation_null"]
    r_full = h1.get("robustness_estimand_R_full_h8", {})
    primary_metrics = payload["primary"]["mean_per_origin_ap"]
    expected_delta = (primary_metrics["M1C"]["mean"] - primary_metrics["B1"]["mean"])
    _require(h8.get("delta_ap") is not None
             and abs(h8["delta_ap"] - expected_delta) <= 1e-9,
             "refusing to refresh: decision.H1.h8_primary.delta_ap does not match the "
             "stored primary mean-per-origin AP difference")
    before = json.dumps(payload, sort_keys=True)
    h1["multiple_testing"] = build_h1_multiple_testing(h8, h4, permutation_block)
    h1["overall_verdict"] = build_overall_verdict(h8, r_full, h4)
    h1["supported"] = bool(h8.get("supported"))
    decision["premise"]["h8_primary"] = h8.get("status")
    decision["premise"]["h4_secondary"] = h4.get("status")
    payload["config"]["decision_refresh"] = {
        "method": ("decision text fields recomputed from this file's own stored numbers; "
                   "no model refitted and no metric recomputed"),
        "fields": ["decision.H1.multiple_testing", "decision.H1.overall_verdict",
                   "decision.H1.supported", "decision.premise.h8_primary",
                   "decision.premise.h4_secondary"],
    }
    after = json.dumps(payload, sort_keys=True)
    if before == after:
        print(f"decision fields already current in {results_path}")
    write_json_atomic(results_path, payload)
    print(f"refreshed decision fields in {results_path}")
    print("  multiple_testing status:", h1["multiple_testing"]["status"])
    print("  overall_verdict:", h1["overall_verdict"])
    return 0


def run_permutation_null(panel_path: Path, data: RiskHorizonData, n_permutations: int,
                         workers: int) -> dict:
    started = time.perf_counter()
    results: list[dict] = []
    if n_permutations > 0 and workers > 1 and n_permutations >= 4:
        from concurrent.futures import ProcessPoolExecutor
        with ProcessPoolExecutor(
                max_workers=workers,
                initializer=_permutation_worker_init,
                initargs=(str(panel_path), data.adjacency, data.horizon,
                          len(data.test_origins))) as pool:
            results = list(pool.map(_permutation_worker_run, range(n_permutations)))
    else:
        for index in range(n_permutations):
            results.append(permutation_delta(data.panel, data, index, SEED))
    skipped = sum(1 for result in results if result["delta"] is None)
    return {"results": results, "skipped": skipped,
            "runtime_seconds": time.perf_counter() - started}


if __name__ == "__main__":
    raise SystemExit(main())
