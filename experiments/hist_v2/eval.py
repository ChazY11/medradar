"""hist_v2: domain-level walk-forward evaluation harness.

Pre-registered in ``research/protocols/hist_v2_preregistration.md`` (frozen 2026-11-03,
before any hist_v2 model was fitted).  Standard library only, deterministic, no network.

What this script does
---------------------
Reads the domain panel produced by ``experiments/hist_v2/build_domain_panel.py`` (schema
``hist_v2.domain_panel.v1``), builds the pre-registered (company, technology-domain) risk
sets, computes the 15 point-in-time features of protocol section 6 at domain level, fits the
pre-declared baselines B0-B3 and the L2-regularised logistic models M1A / M1B / M1C at every
annual evaluation origin 1995-Q1 .. 2015-Q1, and reports:

* primary estimand ``R_dom`` at h=8 (24 months): mean per-origin average precision, the
  company-clustered paired bootstrap (2,000 resamples, seed 20261103) with the hist_v1
  reliability gate, ΔAP(M1C-B1) and the decisive ΔAP(M1C-B3);
* the pre-declared power target (MDE <= 0.05 AP points, else the result is declared
  underpowered in advance);
* secondary risk set ``R_dom_adj`` and the h=4 secondary horizon;
* ERA split 1995-2004 / 2005-2015;
* feature-group ablation A / B / C and the 200-permutation label null (seed 20261103,
  labels shuffled among cells sharing (origin, domain));
* the lead-time frontier at 1/5/10/20 % alert budgets with missed entries;
* the descriptive holdout on origins 2016-Q1 .. 2024-Q1 (no inference);
* the ``pairs_no_acquired`` attribution sensitivity inherited from hist_v1 amendment A5.

Frozen decisions implemented literally
--------------------------------------
* label only from events with ``t < qidx <= t+h``; a cell is mature iff ``t+h <= last_qidx``;
* features only from events with ``qidx <= t`` (availability quarters);
* training cells at origin ``t``: candidate cells at every quarter ``t'`` from the panel
  start through ``t-h`` (quarterly grid), labels mature strictly before ``t`` (purge
  asserted per origin, ``t' + h <= t``);
* A2 sampler: all positive training cells + a seeded random sample of negatives so that the
  training set has at most 12,000 rows; sampled negatives carry weight ``1/p_neg``;
* primary metric = mean of per-origin average precision (never pooled AP).

Usage::

    python experiments/hist_v2/eval.py --panel out/hist_v2/domain_panel.json \\
        --out experiments/hist_v2/results.json [--quick] [--workers N] [--max-origins N]
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
PANEL_SCHEMA = "hist_v2.domain_panel.v1"
RESULTS_SCHEMA = "hist_v2.results.v1"
PROTOCOL_PATH = "research/protocols/hist_v2_preregistration.md"
PANEL_BUILDER = "experiments/hist_v2/build_domain_panel.py"

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
HORIZONS = (("h8", 8), ("h4", 4))                    # h8 primary
ORIGIN_YEARS = (1995, 2015)                         # 21 annual origins, entry-rich era
HOLDOUT_ORIGIN_YEARS = (2016, 2024)                 # descriptive only, no inference
ERA_BANDS = (("1995-2004", 1995, 2004),
             ("2005-2015", 2005, 2015))
PRIMARY_RISK_SET = "R_dom"
SECONDARY_RISK_SET = "R_dom_adj"
MDE_TARGET_AP_POINTS = 0.05                         # pre-declared power target
DEEP_CASE_KEYS = ("medtronic", "ge_healthcare", "philips", "draeger", "mindray")

# protocol section 6, same 15 features as hist_v1 re-defined at domain level
FEATURE_NAMES_C = (
    "firm_act_4", "firm_act_8", "firm_growth", "firm_domains", "firm_tenure",
    "firm_entry_rate", "adj_act_8", "adj_share", "domain_act_8", "domain_growth",
    "domain_entrants", "domain_recent_entries", "domain_age", "domain_share", "firm_size",
)
_GROUP_A_NAMES = {"firm_act_4", "firm_act_8", "firm_growth", "firm_domains",
                  "firm_tenure", "firm_entry_rate", "firm_size"}
_GROUP_B_NAMES = _GROUP_A_NAMES | {"domain_act_8", "domain_growth", "domain_entrants",
                                   "domain_recent_entries", "domain_age"}
_GROUP_C_NAMES = _GROUP_B_NAMES | {"adj_act_8", "adj_share", "domain_share"}
# group membership is a set, but the column order is always the protocol table order
GROUP_A = tuple(name for name in FEATURE_NAMES_C if name in _GROUP_A_NAMES)
GROUP_B = tuple(name for name in FEATURE_NAMES_C if name in _GROUP_B_NAMES)
GROUP_C = tuple(name for name in FEATURE_NAMES_C if name in _GROUP_C_NAMES)
FEATURE_GROUPS = {"A": GROUP_A, "B": GROUP_B, "C": GROUP_C}

FEATURE_DEFINITIONS = {
    "firm_act_4": "log1p(count of company material events, all domains, t-4 < qidx <= t)",
    "firm_act_8": "log1p(count of company material events, all domains, t-8 < qidx <= t)",
    "firm_growth": "raw_count_4 / (raw_count_8 - raw_count_4 + 0.5); last year vs prior year",
    "firm_domains": "number of distinct technology domains the company has any material event in by t",
    "firm_tenure": "(t - first observed company event qidx) / 4.0",
    "firm_entry_rate": "company first-domain-entry events in (t-32, t] divided by 8.0",
    "adj_act_8": "log1p(count of company events in the candidate domain's sibling domains, t-8 < qidx <= t)",
    "adj_share": "sibling-domain share of the company's events in (t-8, t] (raw ratio); None when the denominator is 0",
    "domain_act_8": "log1p(count of industry material events in the domain, t-8 < qidx <= t)",
    "domain_growth": "industry raw_count_4 / (raw_count_8 - raw_count_4 + 0.5)",
    "domain_entrants": "number of distinct companies that have entered the domain (first event) by t",
    "domain_recent_entries": "log1p(count of first entries into the domain in (t-8, t])",
    "domain_age": "(t - first observed industry event in the domain) / 4.0; None if none yet",
    "domain_share": "share of the company's ever events (qidx <= t) in the domain's sibling domains; the domain-level analog of hist_v1 cat_share (own-domain share is identically 0 on candidate cells)",
    "firm_size": "log1p(count of company material events, all domains, with qidx <= t)",
}

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
def rank_order(scores: list[float], company_keys: list[str],
               domain_ids: list[str]) -> list[int]:
    """Deterministic ranking: score descending, then company key, then domain id ascending."""
    return sorted(range(len(scores)),
                  key=lambda i: (-scores[i], company_keys[i], domain_ids[i]))


def average_precision(labels: list[int], scores: list[float],
                      company_keys: list[str] | None = None,
                      domain_ids: list[str] | None = None,
                      order: list[int] | None = None) -> float | None:
    """Tie-aware average precision (same step formula as medradar's ``pr_auc``).

    Equal scores are evaluated as one threshold, so the value does not depend on the
    order of tied rows; the (score, company, domain) ordering is only used to make the
    alert list deterministic.
    """
    n = len(labels)
    positives = sum(labels)
    if n == 0 or positives == 0 or positives == n:
        return None
    if order is None:
        if company_keys is None or domain_ids is None:
            order = sorted(range(n), key=lambda i: -scores[i])
        else:
            order = rank_order(scores, company_keys, domain_ids)
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


def _sigmoid(z: float) -> float:
    if z >= 0.0:
        return 1.0 / (1.0 + math.exp(-z))
    exponential = math.exp(z)
    return exponential / (1.0 + exponential)


# ===================================================================== panel object
class Panel:
    """Indexed view of a ``hist_v2.domain_panel.v1`` domain panel.

    ``event_qidx`` entries are quarter indices into ``panel["quarters"]`` (the quarter in
    which the event became available); ``last_qidx`` is 2026-Q2 for the frozen grid.

    Domain-level adjacency (protocol section 5/6, "adjacency at domain level") is
    operationalised over *sibling domains*: two domains are adjacent when their config
    ``category`` bands intersect (``config/tracks_device.json`` track ``category`` fields).
    This is the domain-level translation of hist_v1's "another track of the same category";
    the literal reading of "a different domain" would be implied by firm establishment for
    every unentered candidate domain and would make ``R_dom_adj`` identical to ``R_dom``.
    """

    def __init__(self, data: dict, *, path: Path | None = None, sha256: str | None = None,
                 pairs_key: str = "pairs", variant: str | None = None):
        _require(isinstance(data, dict), "panel JSON must be an object")
        schema = data.get("schema")
        _require(schema == PANEL_SCHEMA,
                 f"panel schema {schema!r} does not match expected {PANEL_SCHEMA!r}; "
                 "report the deviation instead of adapting silently")
        for key in ("quarter_start", "quarter_end", "quarters", "companies", "domains",
                    "pairs"):
            _require(key in data, f"panel is missing required key {key!r}")
        self.data = data
        self.path = path
        self.sha256 = sha256
        self.pairs_key = pairs_key
        self.variant = variant or ("primary" if pairs_key == "pairs" else pairs_key)
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

        domain_records = data["domains"]
        _require(isinstance(domain_records, list) and domain_records,
                 "panel domains must be a non-empty list")
        self.domains = {}
        for record in domain_records:
            domain_id = record.get("id")
            _require(isinstance(domain_id, str) and domain_id, "domain record without an id")
            _require(domain_id not in self.domains, f"duplicate domain id {domain_id!r}")
            _require("categories" in record, f"domain {domain_id!r} has no categories")
            self.domains[domain_id] = record
        self.domain_keys = sorted(self.domains)
        self.domain_index = {key: index for index, key in enumerate(self.domain_keys)}
        self.domain_count = len(self.domain_keys)
        self.domain_categories = {key: set(self.domains[key].get("categories") or [])
                                  for key in self.domain_keys}
        self.sibling_domains = {
            domain: sorted(other for other in self.domain_keys
                           if other != domain
                           and self.domain_categories[domain] & self.domain_categories[other])
            for domain in self.domain_keys}

        # ---- pair event indexes -------------------------------------------------
        self.pair_events: dict[tuple[str, str], list[int]] = {}
        self.pair_counts: dict[tuple[str, str], list[int]] = {}
        pairs_missing_counts = 0
        pair_records = data[pairs_key]
        _require(isinstance(pair_records, list), f"panel {pairs_key} must be a list")
        for record in pair_records:
            company = record.get("company_key")
            domain = record.get("domain_id")
            _require(company in self.companies,
                     f"pair references unknown company {company!r}")
            _require(domain in self.domains, f"pair references unknown domain {domain!r}")
            qidx_values = record.get("event_qidx")
            _require(isinstance(qidx_values, list),
                     f"pair {company}/{domain} has no event_qidx list")
            counts_values = record.get("event_counts")
            values = []
            for position, value in enumerate(qidx_values):
                _require(isinstance(value, int) and 0 <= value <= self.last_qidx,
                         f"pair {company}/{domain} has out-of-range event_qidx {value!r}")
                if position and value < qidx_values[position - 1]:
                    raise ValueError(f"pair {company}/{domain} event_qidx is not sorted")
                values.append(value)
            if counts_values is None:
                pairs_missing_counts += 1
                counts = [1] * len(values)
            else:
                _require(isinstance(counts_values, list) and len(counts_values) == len(values),
                         f"pair {company}/{domain} event_counts length mismatch")
                counts = []
                for value in counts_values:
                    _require(isinstance(value, int) and value >= 1,
                             f"pair {company}/{domain} event_counts entry {value!r} is not >= 1")
                    counts.append(value)
            _require((company, domain) not in self.pair_events,
                     f"duplicate pair record {company}/{domain}")
            self.pair_events[(company, domain)] = values
            self.pair_counts[(company, domain)] = counts
        self.pairs_missing_event_counts = pairs_missing_counts
        self.feature_source = ("event_counts" if pairs_missing_counts == 0
                               else "presence_only_underestimate")
        self.total_event_count = sum(sum(counts) for counts in self.pair_counts.values())

        # ---- flat event indexes (event multiset: a quarter with n events is n entries)
        self.company_q: dict[str, list[int]] = {key: [] for key in self.company_keys}
        self.company_events: dict[str, list[tuple[int, str]]] = {key: [] for key in self.company_keys}
        self.company_domain_first: dict[str, dict[str, int]] = {key: {} for key in self.company_keys}
        self.company_domain_first_q: dict[str, list[int]] = {key: [] for key in self.company_keys}
        self.company_entries: dict[str, list[int]] = {key: [] for key in self.company_keys}
        self.company_sibling_q: dict[tuple[str, str], list[int]] = {}
        self.industry_events: dict[str, list[tuple[int, str]]] = {
            key: [] for key in self.domain_keys}
        for (company, domain), values in self.pair_events.items():
            if not values:
                continue
            counts = self.pair_counts[(company, domain)]
            self.company_domain_first[company][domain] = values[0]
            self.company_domain_first_q[company].append(values[0])
            self.company_entries[company].append(values[0])
            for value, count in zip(values, counts):
                for _ in range(count):
                    self.company_q[company].append(value)
                    self.company_events[company].append((value, domain))
                    self.industry_events[domain].append((value, company))
        for company in self.company_keys:
            self.company_q[company].sort()
            self.company_events[company].sort()
            self.company_domain_first_q[company].sort()
            self.company_entries[company].sort()
        for domain in self.domain_keys:
            self.industry_events[domain].sort()
        # company events restricted to the sibling domains of every domain (adjacency)
        for company in self.company_keys:
            own = self.company_events[company]
            for domain in self.domain_keys:
                siblings = set(self.sibling_domains[domain])
                self.company_sibling_q[(company, domain)] = (
                    sorted(qidx for qidx, event_domain in own if event_domain in siblings)
                    if siblings else [])
        # per-domain sorted first-entry quarters (one per company that ever entered)
        self.domain_entry_q: dict[str, list[int]] = {
            domain: sorted(self.company_domain_first[company][domain]
                           for company in self.company_keys
                           if domain in self.company_domain_first[company])
            for domain in self.domain_keys}
        self.domain_q: dict[str, list[int]] = {
            domain: [q for q, _company in self.industry_events[domain]]
            for domain in self.domain_keys}
        self.total_events = self.total_event_count
        self.pairs_observed = sum(1 for values in self.pair_events.values() if values)
        audit_summary = (data.get("audits") or {}).get("panel_summary") or {}
        audit_total = audit_summary.get("n_material_events")
        if self.variant == "primary":
            self.event_count_audit = {
                "sum_pair_event_counts": self.total_event_count,
                "audits_panel_summary_n_material_events": audit_total,
                "matches": (audit_total is None or int(audit_total) == self.total_event_count),
                "pairs_missing_event_counts": pairs_missing_counts,
                "feature_source": self.feature_source,
            }
        else:
            self.event_count_audit = {
                "variant": self.variant,
                "sum_pair_event_counts": self.total_event_count,
                "audits_panel_summary_n_material_events": audit_total,
                "matches_primary_panel": (audit_total is not None
                                          and int(audit_total) == self.total_event_count),
                "note": "attribution sensitivity variant; not expected to equal the primary count",
                "pairs_missing_event_counts": pairs_missing_counts,
                "feature_source": self.feature_source,
            }

    # ---- point-in-time primitives ------------------------------------------
    def established(self, company: str, t: int) -> bool:
        """Condition 1: the company has >= 1 material event with qidx <= t."""
        firm = self.company_q[company]
        return bool(firm) and firm[0] <= t

    def pair_entered(self, company: str, domain: str, t: int) -> bool:
        """Condition 2 (negated): the pair has no material event with qidx <= t."""
        values = self.pair_events.get((company, domain))
        return bool(values) and values[0] <= t

    def sibling_active(self, company: str, domain: str, t: int) -> bool:
        """The firm already has a material event in a sibling domain strictly before t."""
        values = self.company_sibling_q.get((company, domain), [])
        index = bisect.bisect_left(values, t)
        return index > 0

    def risk_set(self, t: int, adjacency: bool) -> list[tuple[str, str]]:
        """Candidate (company, domain) pairs at the end of quarter ``t``.

        ``adjacency=False`` is the pre-registered primary risk set ``R_dom``;
        ``adjacency=True`` is the secondary risk set ``R_dom_adj``.
        """
        candidates: list[tuple[str, str]] = []
        for company in self.company_keys:
            firm = self.company_q[company]
            if not firm or firm[0] > t:      # condition 1
                continue
            first_by_domain = self.company_domain_first[company]
            for domain in self.domain_keys:
                first = first_by_domain.get(domain)
                if first is not None and first <= t:
                    continue
                if adjacency and not self.sibling_active(company, domain, t):
                    continue
                candidates.append((company, domain))
        return candidates

    def mature(self, t: int, horizon: int) -> bool:
        return t + horizon <= self.last_qidx

    def label(self, company: str, domain: str, t: int, horizon: int) -> int:
        """Y_h = 1 iff the pair has an event with ``t < qidx <= t + h``."""
        values = self.pair_events.get((company, domain))
        if not values:
            return 0
        index = bisect.bisect_right(values, t)
        return 1 if index < len(values) and values[index] <= t + horizon else 0

    # ---- features (protocol section 6) -------------------------------------
    def features(self, company: str, domain: str, t: int) -> dict[str, float | None]:
        """Raw (pre-imputation) point-in-time features for a candidate cell at ``t``."""
        firm = self.company_q[company]
        sibling_q = self.company_sibling_q.get((company, domain), [])

        def count(values: list[int], low: int, high: int) -> int:
            return bisect.bisect_right(values, high) - bisect.bisect_right(values, low)

        firm_4 = count(firm, t - 4, t)
        firm_8 = count(firm, t - 8, t)
        sibling_8 = count(sibling_q, t - 8, t)
        industry_q = self.domain_q[domain]
        industry_4 = count(industry_q, t - 4, t)
        industry_8 = count(industry_q, t - 8, t)
        firm_ever = bisect.bisect_right(firm, t)
        sibling_ever = bisect.bisect_right(sibling_q, t)
        entries_last_8y = (bisect.bisect_right(self.company_entries[company], t)
                           - bisect.bisect_right(self.company_entries[company], t - 32))
        entrants = bisect.bisect_right(self.domain_entry_q[domain], t)
        recent_entries = entrants - bisect.bisect_right(self.domain_entry_q[domain], t - 8)
        first_industry = industry_q[0] if industry_q and industry_q[0] <= t else None
        return {
            "firm_act_4": _log1p(firm_4),
            "firm_act_8": _log1p(firm_8),
            "firm_growth": firm_4 / (firm_8 - firm_4 + 0.5),
            "firm_domains": float(bisect.bisect_right(self.company_domain_first_q[company], t)),
            "firm_tenure": (t - firm[0]) / 4.0,
            "firm_entry_rate": entries_last_8y / 8.0,
            "adj_act_8": _log1p(sibling_8),
            "adj_share": (sibling_8 / firm_8) if firm_8 else None,
            "domain_act_8": _log1p(industry_8),
            "domain_growth": industry_4 / (industry_8 - industry_4 + 0.5),
            "domain_entrants": float(entrants),
            "domain_recent_entries": _log1p(recent_entries),
            "domain_age": ((t - first_industry) / 4.0) if first_industry is not None else None,
            "domain_share": (sibling_ever / firm_ever) if firm_ever else None,
            "firm_size": _log1p(firm_ever),
        }

    def feature_vector(self, company: str, domain: str, t: int,
                       names: tuple[str, ...] = FEATURE_NAMES_C) -> tuple[float, ...]:
        raw = self.features(company, domain, t)
        return tuple(math.nan if raw[name] is None else raw[name] for name in names)

    # ---- independent replay (hist_v1 protocol section 12.3) ----------------
    def features_bruteforce(self, company: str, domain: str, t: int) -> dict[str, float | None]:
        """Straight linear-scan re-implementation of ``features`` for the leak audit.

        Deliberately does not use any of the bisect indexes built above: it scans the
        raw event index of the panel.  Must match ``features`` exactly.
        """
        sibling_domains = set(self.sibling_domains[domain])
        events = self.company_events[company]
        industry = self.industry_events[domain]
        firm_4 = firm_8 = firm_ever = sibling_8 = sibling_ever = 0
        industry_4 = industry_8 = 0
        first_industry = None
        for qidx, event_domain in events:
            if qidx > t:
                continue
            firm_ever += 1
            if t - 4 < qidx:
                firm_4 += 1
            if t - 8 < qidx:
                firm_8 += 1
            if event_domain in sibling_domains:
                sibling_ever += 1
                if t - 8 < qidx:
                    sibling_8 += 1
        for qidx, _company in industry:
            if qidx > t:
                continue
            if t - 4 < qidx:
                industry_4 += 1
            if t - 8 < qidx:
                industry_8 += 1
            if first_industry is None:
                first_industry = qidx
        entries_last_8y = sum(1 for qidx in self.company_entries[company]
                              if t - 32 < qidx <= t)
        entrants = sum(1 for qidx in self.domain_entry_q[domain] if qidx <= t)
        recent_entries = sum(1 for qidx in self.domain_entry_q[domain] if t - 8 < qidx <= t)
        firm_domains = sum(1 for qidx in self.company_domain_first_q[company] if qidx <= t)
        return {
            "firm_act_4": _log1p(firm_4),
            "firm_act_8": _log1p(firm_8),
            "firm_growth": firm_4 / (firm_8 - firm_4 + 0.5),
            "firm_domains": float(firm_domains),
            "firm_tenure": (t - self.company_q[company][0]) / 4.0,
            "firm_entry_rate": entries_last_8y / 8.0,
            "adj_act_8": _log1p(sibling_8),
            "adj_share": (sibling_8 / firm_8) if firm_8 else None,
            "domain_act_8": _log1p(industry_8),
            "domain_growth": industry_4 / (industry_8 - industry_4 + 0.5),
            "domain_entrants": float(entrants),
            "domain_recent_entries": _log1p(recent_entries),
            "domain_age": ((t - first_industry) / 4.0) if first_industry is not None else None,
            "domain_share": (sibling_ever / firm_ever) if firm_ever else None,
            "firm_size": _log1p(firm_ever),
        }


def load_panel(path: Path, *, pairs_key: str = "pairs", variant: str | None = None) -> Panel:
    _require(path.is_file(), f"panel not found: {path}")
    with open(path, "r", encoding="utf-8") as handle:
        data = json.load(handle)
    return Panel(data, path=path, sha256=sha256_file(path), pairs_key=pairs_key, variant=variant)


# ============================================================ training / models
def evaluation_origins(panel: Panel, horizon: int,
                       years: tuple[int, int] = ORIGIN_YEARS) -> list[int]:
    """Q1 of every calendar year in the requested origin span (mature cells only)."""
    origins = []
    for year in range(years[0], years[1] + 1):
        quarter = f"{year}-Q1"
        if quarter not in panel.qidx:
            continue
        origin = panel.qidx[quarter]
        if not panel.mature(origin, horizon):
            continue
        origins.append(origin)
    return origins


class RiskHorizonData:
    """Quarterly candidate cells plus the annual test cells for one (risk set, horizon)."""

    def __init__(self, panel: Panel, adjacency: bool, horizon: int,
                 origins: list[int] | None = None, max_origins: int | None = None):
        self.panel = panel
        self.adjacency = adjacency
        self.risk_set_name = SECONDARY_RISK_SET if adjacency else PRIMARY_RISK_SET
        self.horizon = horizon
        self.horizon_key = "h8" if horizon == 8 else "h4"
        self.feature_names: tuple[str, ...] = FEATURE_NAMES_C
        self.column_of = {name: index for index, name in enumerate(self.feature_names)}
        self.test_origins = evaluation_origins(panel, horizon) if origins is None else list(origins)
        if max_origins is not None:
            self.test_origins = self.test_origins[:max(1, int(max_origins))]
        if not self.test_origins:
            raise ValueError(f"no mature evaluation origins for h={horizon}")
        self.max_train_t = max(self.test_origins) - horizon

        # ---- quarterly training pool (every quarter from the panel start to t_max - h)
        company: list[str] = []
        domain: list[str] = []
        quarter: list[int] = []
        label: list[int] = []
        features: list[tuple[float, ...]] = []
        for t in range(0, self.max_train_t + 1):
            for company_key, domain_id in panel.risk_set(t, adjacency):
                company.append(company_key)
                domain.append(domain_id)
                quarter.append(t)
                label.append(panel.label(company_key, domain_id, t, horizon))
                features.append(panel.feature_vector(company_key, domain_id, t))
        self.pool_company = company
        self.pool_domain = domain
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
        for origin in self.test_origins:
            candidates = panel.risk_set(origin, adjacency)
            rows = {"company": [], "domain": [], "label": [], "features": []}
            for company_key, domain_id in candidates:
                rows["company"].append(company_key)
                rows["domain"].append(domain_id)
                rows["label"].append(panel.label(company_key, domain_id, origin, horizon))
                rows["features"].append(panel.feature_vector(company_key, domain_id, origin))
            rows["n_immature_excluded"] = 0
            self.test_cells[origin] = rows

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
                                    f"{'adj' if self.adjacency else 'dom'}|{origin}")
                population = self.negative_indices[:negative_cut]
                sampled_negatives = (rng.sample(population, keep_negatives)
                                     if keep_negatives else [])
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
            "risk_set": self.risk_set_name,
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
def fit_logistic_regression(raw_rows: list[list[float]], labels: list[int],
                            weights: list[float], *, lam: float = LAMBDA,
                            lr: float = LEARNING_RATE, epochs: int = EPOCHS) -> dict:
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
        variance = sum(map(mul, weights,
                           [(value - mean) ** 2 for value in column])) / total_weight
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
    for _epoch in range(epochs):
        probabilities = linear_and_probabilities(coefficients, intercept)
        errors = [(probability - label) * weight
                  for probability, label, weight in zip(probabilities, labels, weights)]
        gradient_intercept = sum(errors) / total_weight
        gradient = [sum(map(mul, errors, column)) / total_weight + lam * value
                    for column, value in zip(transposed, coefficients)]
        coefficients = [value - lr * slope for value, slope in zip(coefficients, gradient)]
        intercept -= lr * gradient_intercept
    # final loss and gradient norm (convergence report)
    probabilities = linear_and_probabilities(coefficients, intercept)
    loss_end = log_loss(probabilities)
    errors = [(probability - label) * weight
              for probability, label, weight in zip(probabilities, labels, weights)]
    gradient = [sum(map(mul, errors, column)) / total_weight + lam * value
                for column, value in zip(transposed, coefficients)]
    gradient_intercept = sum(errors) / total_weight
    gradient_norm = math.sqrt(sum(value * value for value in gradient)
                              + gradient_intercept ** 2)
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
    """Fit B0-B3 on the same weighted training sample as M1."""
    total = sum(sample["weights"])
    prevalence = sum(map(mul, sample["weights"], sample["labels"])) / total
    company_positive: dict[str, float] = defaultdict(float)
    company_total: dict[str, float] = defaultdict(float)
    domain_positive: dict[str, float] = defaultdict(float)
    domain_total: dict[str, float] = defaultdict(float)
    for index, weight, label in zip(sample["indices"], sample["weights"], sample["labels"]):
        company = data.pool_company[index]
        domain = data.pool_domain[index]
        company_total[company] += weight
        domain_total[domain] += weight
        if label:
            company_positive[company] += weight
            domain_positive[domain] += weight
    prior = BASELINE_PRIOR_STRENGTH
    company_rate = {company: (company_positive.get(company, 0.0) + prior * prevalence) /
                             (company_total[company] + prior)
                    for company in company_total}
    domain_rate = {domain: (domain_positive.get(domain, 0.0) + prior * prevalence) /
                           (domain_total[domain] + prior)
                   for domain in domain_total}
    # B3 = B1 x B2 renormalised to the training prevalence
    weighted_raw = 0.0
    for index, weight in zip(sample["indices"], sample["weights"]):
        raw = (company_rate.get(data.pool_company[index], prevalence) *
               domain_rate.get(data.pool_domain[index], prevalence))
        weighted_raw += weight * raw
    mean_raw = weighted_raw / total
    return {
        "prevalence": prevalence,
        "company_rate": company_rate,
        "domain_rate": domain_rate,
        "prior_strength": prior,
        "b3_scale": (prevalence / mean_raw) if mean_raw > 0 else 0.0,
    }


def predict_baselines(fit: dict, company_keys: list[str], domain_ids: list[str],
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
            predictions[model] = [fit["domain_rate"].get(domain, prevalence)
                                  for domain in domain_ids]
        elif model == "B3":
            predictions[model] = [
                min(1.0, max(1e-9, fit["b3_scale"] *
                            fit["company_rate"].get(company, prevalence) *
                            fit["domain_rate"].get(domain, prevalence)))
                for company, domain in zip(company_keys, domain_ids)]
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
    domains = record["domains"]
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
        order = rank_order(scores, companies, domains)
        entry = {
            "average_precision": average_precision(labels, scores, companies, domains, order),
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
    domains: list[str] = []
    for record in records:
        if model not in record["scores"]:
            continue
        labels.extend(record["labels"])
        scores.extend(record["scores"][model])
        companies.extend(record["companies"])
        domains.extend(record["domains"])
    return average_precision(labels, scores, companies, domains) if labels else None


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
    (paired).  For a resample and an origin, AP is computed only when that origin has at
    least one positive and one negative row; the per-origin mean is taken over the
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
    return {record["origin"]: set(zip(record["companies"], record["domains"]))
            for record in records}


def incident_entries(panel: Panel, records: list[dict], horizon: int) -> dict:
    """Entry events in the evaluation window and the origins at which they were candidates.

    The evaluation window is the union over evaluation origins of ``(t, t+h]``.  For an
    entry at quarter ``f`` the alert window is ``[f-8, f-1]`` (protocol section 9).
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
    for (company, domain), values in panel.pair_events.items():
        if not values:
            continue
        first = values[0]
        if first <= first_origin or first > last_origin + horizon:
            continue
        window = [origin for origin in origins if first - 8 <= origin <= first - 1]
        candidate_origins = [origin for origin in window
                             if (company, domain) in membership.get(origin, ())]
        if not candidate_origins:
            if (company, domain) not in ever_in_risk_set:
                excluded += 1
                continue
            without_candidate_origin += 1
        entries.append({"company_key": company, "domain_id": domain,
                        "entry_qidx": first,
                        "candidate_origins": sorted(candidate_origins)})
    entries.sort(key=lambda entry: (entry["entry_qidx"], entry["company_key"],
                                    entry["domain_id"]))
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
        for company, domain, label, score in zip(record["companies"], record["domains"],
                                                 record["labels"], record["scores"][model]):
            lookup[(company, domain)] = score
            total_cells += 1
            if label:
                positive_cells += 1
            if score >= threshold:
                if label:
                    true_positives += 1
                else:
                    false_positives += 1
        scores_by_origin[record["origin"]] = lookup
    thresholds = {record["origin"]: record["thresholds"][model][budget]
                  for record in records}
    leads: list[int] = []
    alerted = missed = 0
    for entry in entries["entries"]:
        first_alert = None
        for origin in entry["candidate_origins"]:
            score = scores_by_origin.get(origin, {}).get(
                (entry["company_key"], entry["domain_id"]))
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
            false_positives / (total_cells - positive_cells))
        if (total_cells - positive_cells) else None,
        "entries_in_scope": len(entries["entries"]),
        "entries_alerted": alerted,
        "entries_missed": missed,
        "lead_quarters": median_iqr(leads),
    }


def era_strata(config: dict, panel: Panel) -> dict:
    result = {}
    for name, first_year, last_year in ERA_BANDS:
        origins = [origin for origin in config["origins"]
                   if first_year <= panel.quarter_year[origin] <= last_year]
        subset = [origin for origin in config["per_origin"]
                  if origin["origin"] in origins]
        entry = {"origins": [panel.quarters[origin] for origin in origins], "models": {}}
        for model in config["models"]:
            entry["models"][model] = ap_summary(
                [row["models"][model]["average_precision"]
                 for row in subset if model in row["models"]])
        left = entry["models"].get("M1C", {}).get("mean")
        right = entry["models"].get("B1", {}).get("mean")
        entry["delta_ap_M1C_minus_B1"] = (
            left - right) if left is not None and right is not None else None
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
    """Seeded replay audit over risk-set cells (hist_v1 protocol section 12.3 method)."""
    rng = random.Random(f"{SEED}|leak-audit")
    cells = [(record["origin"], record["companies"][index], record["domains"][index])
             for record in config["records"]
             for index in range(len(record["labels"]))]
    sample = rng.sample(cells, min(sample_size, len(cells)))
    mismatches = 0
    tolerance = 1e-12
    for origin, company, domain in sample:
        _require(not panel.pair_entered(company, domain, origin),
                 f"leak audit sampled a non-risk-set cell: {company}/{domain} at "
                 f"{panel.quarters[origin]} is already entered")
        fast = panel.features(company, domain, origin)
        slow = panel.features_bruteforce(company, domain, origin)
        for name in FEATURE_NAMES_C:
            first, second = fast[name], slow[name]
            if (first is None) != (second is None):
                mismatches += 1
            elif first is not None and abs(first - second) > tolerance:
                mismatches += 1
    return {"cells_sampled": len(sample), "mismatches": mismatches,
            "tolerance_absolute": tolerance,
            "risk_set_cells_only": True,
            "method": ("independent linear-scan replay of the 15 domain-level features"),
            "reference_implementation": "features_bruteforce"}


# ------------------------------------------------------------- label-permutation null
def _group_indices(keys: list[tuple[int, str]]) -> dict[tuple[int, str], list[int]]:
    groups: dict[tuple[int, str], list[int]] = defaultdict(list)
    for index, key in enumerate(keys):
        groups[key].append(index)
    return dict(groups)


def permutation_delta(panel: Panel, data: RiskHorizonData, perm_index: int,
                      seed: int) -> dict:
    """One label-permutation replicate of ΔAP (M1C - B1) on the primary configuration.

    Labels are shuffled among cells that share (origin quarter, domain), which preserves
    every origin's prevalence and every (origin, domain) entry count exactly; per-company
    total entries are **not** preserved (that constraint is infeasible within the frozen
    risk sets).  Both the training labels and the evaluation labels are permuted, and M1C
    and B1 are refitted on the permuted training labels.
    """
    rng = random.Random(f"{seed}|permutation|{data.horizon}|"
                        f"{'adj' if data.adjacency else 'dom'}|{perm_index}")
    pool_group_keys = list(zip(data.pool_t, data.pool_domain))
    pool_groups = _group_indices(pool_group_keys)
    permuted_pool_labels = list(data.pool_label)
    for group in pool_groups.values():
        values = [data.pool_label[index] for index in group]
        rng.shuffle(values)
        for position, index in enumerate(group):
            permuted_pool_labels[index] = values[position]
    permuted_test_labels: dict[int, list[int]] = {}
    for origin in data.test_origins:
        cells = data.test_cells[origin]
        groups = _group_indices([(origin, domain) for domain in cells["domain"]])
        labels = list(cells["label"])
        for group in groups.values():
            values = [cells["label"][index] for index in group]
            rng.shuffle(values)
            for position, index in enumerate(group):
                labels[index] = values[position]
        permuted_test_labels[origin] = labels
    ap_m1c: list[float] = []
    ap_b1: list[float] = []
    for origin in data.test_origins:
        sample = data.training_sample(origin)
        permuted_sample = dict(sample)
        permuted_sample["labels"] = [permuted_pool_labels[index] for index in sample["indices"]]
        names = FEATURE_GROUPS["C"]
        raw_train = data.feature_matrix(sample["indices"], names)
        fit = fit_logistic_regression(raw_train, permuted_sample["labels"], sample["weights"])
        baselines = fit_baselines(data, permuted_sample)
        cells = data.test_cells[origin]
        permuted_labels = permuted_test_labels[origin]
        raw_test = data.test_matrix(origin, names)
        scores_m1c = predict_logistic(fit, raw_test)
        scores_b1 = predict_baselines(baselines, cells["company"], cells["domain"],
                                      models=("B1",))["B1"]
        order_m1c = rank_order(scores_m1c, cells["company"], cells["domain"])
        order_b1 = rank_order(scores_b1, cells["company"], cells["domain"])
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
    _WORKER_STATE["data"] = RiskHorizonData(panel, adjacency, horizon,
                                            max_origins=max_origins)


def _permutation_worker_run(perm_index: int) -> dict:
    return permutation_delta(_WORKER_STATE["panel"], _WORKER_STATE["data"], perm_index, SEED)


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
                          len(data.test_origins) if data.test_origins else None)) as pool:
            results = list(pool.map(_permutation_worker_run, range(n_permutations)))
    else:
        for index in range(n_permutations):
            results.append(permutation_delta(data.panel, data, index, SEED))
    skipped = sum(1 for result in results if result["delta"] is None)
    return {"results": results, "skipped": skipped,
            "runtime_seconds": time.perf_counter() - started}


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
        domains = cells["domain"]
        scores = predict_baselines(baselines, companies, domains)
        training_companies = [data.pool_company[index] for index in sample["indices"]]
        training_domains = [data.pool_domain[index] for index in sample["indices"]]
        training_baseline_scores = predict_baselines(baselines, training_companies,
                                                     training_domains)
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
            "origin": origin, "companies": companies, "domains": domains,
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
        "risk_set": data.risk_set_name,
        "horizon": data.horizon,
        "horizon_key": data.horizon_key,
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


# ----------------------------------------------------------------------------- main
def mde_statement(entry: dict) -> str:
    if entry.get("delta_ap") is None or entry.get("mde_80pct_power_alpha_0.05") is None:
        return "not estimable (bootstrap dispersion not quotable)"
    statement = (f"observed ΔAP = {entry['delta_ap']:.4f}; MDE(alpha=0.05, power=0.80) = "
                 f"{entry['mde_80pct_power_alpha_0.05']:.4f} AP points "
                 f"(pre-declared target <= {MDE_TARGET_AP_POINTS:.2f})")
    if entry.get("mde_80pct_power_alpha_0.05") > MDE_TARGET_AP_POINTS:
        statement += "; the pre-declared power target FAILS, so the result is declared underpowered in advance"
    if entry.get("ci_low") is None:
        statement += "; the bootstrap reliability gate returned UNRELIABLE, so no CI is quotable"
    elif entry["ci_low"] <= 0.0 <= entry["ci_high"]:
        statement += ("; the 95% CI includes 0, so a true positive effect smaller than the "
                      "MDE cannot be excluded")
    return statement


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="hist_v2 domain-level walk-forward evaluation (pre-registered)")
    parser.add_argument("--panel", default="out/hist_v2/domain_panel.json",
                        help="input domain panel (schema hist_v2.domain_panel.v1)")
    parser.add_argument("--out", default="experiments/hist_v2/results.json")
    parser.add_argument("--quick", action="store_true",
                        help="smoke run: reduces bootstrap/permutation repetitions only")
    parser.add_argument("--bootstrap-reps", type=int, default=BOOTSTRAP_REPS)
    parser.add_argument("--permutations", type=int, default=PERMUTATION_REPS,
                        help="label-permutation replicates (default 200)")
    parser.add_argument("--workers", type=int, default=1,
                        help="process workers for the permutation null (1 = serial)")
    parser.add_argument("--max-origins", type=int, default=None,
                        help="smoke use only: keep the first N evaluation origins")
    args = parser.parse_args(argv)

    started = time.perf_counter()
    phases: dict[str, float] = {}

    def mark(name: str, since: float) -> float:
        phases[name] = phases.get(name, 0.0) + (time.perf_counter() - since)
        return time.perf_counter()

    panel_path = Path(args.panel).resolve()
    clock = time.perf_counter()
    panel = load_panel(panel_path)
    clock = mark("panel_load", clock)
    quick = bool(args.quick)
    bootstrap_reps = min(200, args.bootstrap_reps) if quick else args.bootstrap_reps
    n_permutations = min(5, args.permutations) if quick else max(1, args.permutations)
    workers = 1 if quick else max(1, args.workers)
    company_index = panel.company_index
    print(f"panel: {panel.n_quarters} quarters {panel.quarter_start}..{panel.quarter_end}; "
          f"{panel.company_count} companies, {panel.domain_count} domains, "
          f"{panel.pairs_observed} pairs, {panel.total_events} events")

    # ---------------------------------------------------------- primary configuration
    clock = time.perf_counter()
    primary_data = RiskHorizonData(panel, False, 8, max_origins=args.max_origins)
    clock = mark("primary_cells", clock)
    print(f"primary configuration: {PRIMARY_RISK_SET}, h=8, origins "
          f"{len(primary_data.test_origins)}; models B0-B3, M1A, M1B, M1C")
    clock = time.perf_counter()
    primary = run_config(primary_data, {"A": None, "B": None, "C": None})
    clock = mark("primary_fit", clock)
    print(f"  fitted {len(primary['convergence'])} models over {len(primary['origins'])} "
          f"origins")

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

    point_delta = _difference(primary["mean_per_origin_ap"]["M1C"]["mean"],
                              primary["mean_per_origin_ap"]["B1"]["mean"])
    point_delta_b2 = _difference(primary["mean_per_origin_ap"]["M1C"]["mean"],
                                 primary["mean_per_origin_ap"]["B2"]["mean"])
    point_delta_b3 = _difference(primary["mean_per_origin_ap"]["M1C"]["mean"],
                                 primary["mean_per_origin_ap"]["B3"]["mean"])
    primary_delta = primary_bootstrap["delta"].get("M1C", {})
    delta_b3 = primary_bootstrap["comparisons"].get("M1C-B3", {})

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

    # ------------------------------------------------------------- secondary configs
    clock = time.perf_counter()
    secondary: dict[str, dict] = {}
    for name, adjacency, horizon, years in (
            (f"{SECONDARY_RISK_SET}|h8", True, 8, None),
            (f"{PRIMARY_RISK_SET}|h4", False, 4, None),
            (f"{SECONDARY_RISK_SET}|h4", True, 4, None)):
        origins = evaluation_origins(panel, horizon, years) if years else None
        data = RiskHorizonData(panel, adjacency, horizon, origins=origins,
                               max_origins=args.max_origins)
        config = run_config(data, {"C": None})
        bootstrap_models = ("B1", "B2", "B3", "M1C")
        bootstrap = clustered_bootstrap_mean_ap(
            prepare_bootstrap_origins(config["records"], bootstrap_models, company_index),
            bootstrap_models, len(company_index), bootstrap_reps, SEED,
            comparisons=(("M1C", "B1"), ("M1C", "B2"), ("M1C", "B3")))
        for entry in bootstrap["comparisons"].values():
            entry["interpretation"] = ("secondary/descriptive comparison, not the "
                                       "pre-registered primary test")
        block = config_to_block(config, panel)
        block["bootstrap"] = bootstrap
        block["delta_ap_M1C_minus_B1"] = _difference(
            config["mean_per_origin_ap"]["M1C"]["mean"],
            config["mean_per_origin_ap"]["B1"]["mean"])
        block["delta_ap_M1C_minus_B3"] = _difference(
            config["mean_per_origin_ap"]["M1C"]["mean"],
            config["mean_per_origin_ap"]["B3"]["mean"])
        block["delta_ap_M1C_minus_B2"] = _difference(
            config["mean_per_origin_ap"]["M1C"]["mean"],
            config["mean_per_origin_ap"]["B2"]["mean"])
        secondary[name] = block
        mean_m1c = config["mean_per_origin_ap"]["M1C"]["mean"]
        print(f"  {name}: mean AP M1C="
              f"{'n/a' if mean_m1c is None else round(mean_m1c, 4)}")
    clock = mark("secondary_configs", clock)

    # ------------------------------------------------------------- descriptive holdout
    clock = time.perf_counter()
    holdout_origins = evaluation_origins(panel, 8, HOLDOUT_ORIGIN_YEARS)
    if args.max_origins is not None:
        holdout_origins = holdout_origins[:max(1, args.max_origins)]
    holdout_data = RiskHorizonData(panel, False, 8, origins=holdout_origins)
    holdout_config = run_config(holdout_data, {"C": None})
    holdout = {
        "status": "DESCRIPTIVE_NO_INFERENCE",
        "note": ("post-2015 origins are never used for the primary test; no CI, no "
                 "bootstrap and no p-value is reported for this block (protocol section 3)"),
        "years": list(HOLDOUT_ORIGIN_YEARS),
        "origins": holdout_config["origin_labels"],
        "dataset_by_origin": holdout_config["dataset_rows"],
        "mean_per_origin_ap": holdout_config["mean_per_origin_ap"],
        "pooled_ap": holdout_config["pooled_ap"],
        "per_origin": holdout_config["per_origin"],
        "delta_ap_M1C_minus_B1": _difference(
            holdout_config["mean_per_origin_ap"]["M1C"]["mean"],
            holdout_config["mean_per_origin_ap"]["B1"]["mean"]),
    }
    clock = mark("holdout", clock)

    # ---------------------------------------- attribution sensitivity (hist_v1 A5)
    clock = time.perf_counter()
    if "pairs_no_acquired" not in panel.data:
        attribution_sensitivity = {
            "variant": "pairs_no_acquired",
            "status": "NOT_EVALUABLE",
            "reason": ("the input panel has no `pairs_no_acquired` variant; the canonical "
                       "domain panel built by experiments/hist_v2/build_domain_panel.py "
                       "always carries it"),
            "definition": ("identical to the primary configuration but with the hist_v1 "
                           "attribution sensitivity variant (hist_v1 protocol amendment A5)"),
        }
    else:
        sensitivity_panel = load_panel(panel_path, pairs_key="pairs_no_acquired",
                                       variant="pairs_no_acquired")
        sensitivity_data = RiskHorizonData(sensitivity_panel, False, 8,
                                           max_origins=args.max_origins)
        sensitivity_config = run_config(sensitivity_data, {"C": None})
        sensitivity_bootstrap = clustered_bootstrap_mean_ap(
            prepare_bootstrap_origins(sensitivity_config["records"],
                                      ("B1", "M1C"), company_index),
            ("B1", "M1C"), len(company_index), bootstrap_reps, SEED,
            comparisons=(("M1C", "B1"),))
        attribution_sensitivity = {
            "variant": "pairs_no_acquired",
            "status": "DESCRIPTIVE_SENSITIVITY",
            "definition": (
                "identical to the primary configuration but with the hist_v1 attribution "
                "sensitivity variant: deep-case events whose applicant string is neither a "
                "registry-accepted exact alias nor parent-branded are removed before domain "
                "aggregation (hist_v1 protocol amendment A5)"),
            "n_events_retained": sensitivity_panel.total_events,
            "n_events_primary": panel.total_events,
            "n_pairs_retained": sensitivity_panel.pairs_observed,
            "mean_per_origin_ap": sensitivity_config["mean_per_origin_ap"],
            "pooled_ap": sensitivity_config["pooled_ap"],
            "delta_ap_M1C_minus_B1": _difference(
                sensitivity_config["mean_per_origin_ap"]["M1C"]["mean"],
                sensitivity_config["mean_per_origin_ap"]["B1"]["mean"]),
            "bootstrap": sensitivity_bootstrap,
            "interpretation": ("descriptive attribution sensitivity; the primary analysis "
                               "uses the full frozen panel"),
        }
    clock = mark("attribution_sensitivity", clock)

    # ------------------------------------------------------------- permutation null
    clock = time.perf_counter()
    permutation_results = run_permutation_null(panel_path, primary_data, n_permutations,
                                               workers)
    observed_delta = point_delta
    null_deltas = [result["delta"] for result in permutation_results["results"]
                   if result["delta"] is not None]
    permutation_block = {
        "plan": {"requested": PERMUTATION_REPS,
                 "achieved": n_permutations,
                 "workers": workers,
                 "quick": quick,
                 "reduced": quick or n_permutations < PERMUTATION_REPS},
        "observed_delta_ap": observed_delta,
        "n_permutations_achieved": len(null_deltas),
        "n_permutations_requested": n_permutations,
        "seed": SEED,
        "scheme": ("labels shuffled among cells sharing (origin quarter, domain): every "
                   "origin's prevalence and every (origin, domain) entry count are "
                   "preserved; per-company total entries are NOT preserved (infeasible "
                   "within the frozen risk sets). Training and evaluation labels are "
                   "permuted and M1C and B1 are refitted on the permuted training labels."),
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
        "interpretation": ("secondary descriptive robustness test, not the pre-registered "
                           "confirmatory criterion"),
    }
    clock = mark("permutation_null", clock)
    print(f"  permutation null: {len(null_deltas)} replicates, empirical p="
          f"{permutation_block['empirical_p_value_one_sided']}")

    # ---------------------------------------------------------- leakage control 12.3
    clock = time.perf_counter()
    leak = leak_audit(panel, primary)
    clock = mark("leak_audit", clock)

    # ------------------------------------------------------------------- decisions
    def verdict(delta_entry: dict, point: float | None) -> dict:
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

    h1_h8 = verdict(primary_delta, point_delta)
    b3_verdict = {
        "delta_ap": point_delta_b3,
        "ci_low": delta_b3.get("ci_low"),
        "ci_high": delta_b3.get("ci_high"),
        "p_two_sided": delta_b3.get("p_two_sided"),
        "mde_80pct_power_alpha_0.05": delta_b3.get("mde_80pct_power_alpha_0.05"),
        "bootstrap_status": delta_b3.get("status"),
        "point_positive": (point_delta_b3 is not None and point_delta_b3 > 0.0),
        "interpretation": ("decisive secondary comparison of the frozen protocol: M1C must "
                           "beat the two-way exposure baseline B3 for incremental value"),
    }
    b2_verdict = {
        "delta_ap": point_delta_b2,
        "ci_low": primary_bootstrap["comparisons"].get("M1C-B2", {}).get("ci_low"),
        "ci_high": primary_bootstrap["comparisons"].get("M1C-B2", {}).get("ci_high"),
        "p_two_sided": primary_bootstrap["comparisons"].get("M1C-B2", {}).get("p_two_sided"),
        "bootstrap_status": primary_bootstrap["comparisons"].get("M1C-B2", {}).get("status"),
    }
    # share of origins with a positive paired ΔAP (M1C - B1)
    origin_deltas = []
    for row in primary["per_origin"]:
        left = row["models"].get("M1C", {}).get("average_precision")
        right = row["models"].get("B1", {}).get("average_precision")
        if left is not None and right is not None:
            origin_deltas.append(left - right)
    share_positive = (sum(1 for value in origin_deltas if value > 0) / len(origin_deltas)
                      if origin_deltas else None)
    mde_primary = h1_h8["mde_80pct_power_alpha_0.05"]
    powered = (mde_primary is not None and mde_primary <= MDE_TARGET_AP_POINTS)
    ci_positive = (h1_h8["ci_low"] is not None and h1_h8["ci_low"] > 0.0
                   and point_delta is not None and point_delta > 0.0)
    b3_positive = bool(b3_verdict["point_positive"])
    share_ok = share_positive is not None and share_positive >= 0.60
    criterion_met = bool(ci_positive and b3_positive and share_ok)
    supported = bool(criterion_met and powered)
    criterion_components = {
        "ci_excludes_zero_and_positive": bool(ci_positive),
        "delta_vs_B3_point_positive": b3_positive,
        "share_origins_positive_ge_0.60": bool(share_ok),
        "share_origins_positive": share_positive,
        "n_origins_with_defined_delta": len(origin_deltas),
        "mde_le_pre_declared_target_0.05": bool(powered),
        "mde_80pct_power_alpha_0.05": mde_primary,
    }
    if supported:
        verdict_text = ("H1 SUPPORTED: the 95% CI of ΔAP(M1C-B1) excludes 0 and is positive, "
                        "ΔAP(M1C-B3) is positive, at least 60% of origins have positive "
                        "ΔAP(M1C-B1), and the measured MDE meets the pre-declared target")
    elif criterion_met and not powered:
        verdict_text = ("H1 criterion met but the pre-declared power target FAILS "
                        f"(MDE {mde_primary:.4f} > {MDE_TARGET_AP_POINTS:.2f}): the result "
                        "is declared UNDERPOWERED in advance, whatever its p-value")
    elif ci_positive and not b3_positive:
        verdict_text = ("persistence beaten, incremental value not established: ΔAP(M1C-B1) "
                        "is positive but M1C does not beat the two-way exposure baseline B3 "
                        "(the hist_v1 outcome)")
    elif h1_h8["status"].startswith("UNRELIABLE"):
        verdict_text = ("NOT CONFIRMED: the company-clustered bootstrap reliability gate "
                        "returned UNRELIABLE, so no pre-registered CI is quotable")
    else:
        verdict_text = ("H1 NOT SUPPORTED: the pre-registered CI of ΔAP(M1C-B1) does not "
                        "exclude 0 with a positive point estimate")
    decision = {
        "H1": {
            "primary_estimand": f"{PRIMARY_RISK_SET}|h8",
            "h8_primary": h1_h8,
            "decisive_secondary_M1C_minus_B3": b3_verdict,
            "secondary_M1C_minus_B2": b2_verdict,
            "criterion": ("H1 supported iff (a) the 95% CI of mean-per-origin ΔAP(M1C-B1) "
                          "excludes 0 and the point estimate is positive, (b) the ΔAP(M1C-B3) "
                          "point estimate is positive, (c) at least 60% of origins have a "
                          "positive ΔAP(M1C-B1), and (d) the measured MDE meets the "
                          f"pre-declared target <= {MDE_TARGET_AP_POINTS:.2f} AP points "
                          "(else declared underpowered in advance)"),
            "criterion_components": criterion_components,
            "criterion_met": criterion_met,
            "powered": powered,
            "underpowered": not powered,
            "supported": supported,
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
            "overall_verdict": verdict_text,
            "mde_statements": {"h8_primary": mde_statement(h1_h8),
                               "decisive_M1C_minus_B3": mde_statement(
                                   {"delta_ap": point_delta_b3,
                                    "mde_80pct_power_alpha_0.05":
                                        b3_verdict["mde_80pct_power_alpha_0.05"],
                                    "ci_low": b3_verdict["ci_low"],
                                    "ci_high": b3_verdict["ci_high"]})},
        },
        "secondary_risk_set": {
            "name": SECONDARY_RISK_SET,
            "status": "DESCRIPTIVE",
            "delta_ap_M1C_minus_B1": secondary[f"{SECONDARY_RISK_SET}|h8"]["delta_ap_M1C_minus_B1"],
            "note": ("the frozen protocol defines R_dom_adj as R_dom plus activity in a "
                     "different domain; at domain granularity that literal condition is "
                     "implied by firm establishment, so it is operationalised over sibling "
                     "domains sharing a category band (see config implementation notes)"),
        },
        "h4_secondary": {
            "delta_ap_M1C_minus_B1": secondary[f"{PRIMARY_RISK_SET}|h4"]["delta_ap_M1C_minus_B1"],
            "bootstrap_status": secondary[f"{PRIMARY_RISK_SET}|h4"]["bootstrap"]["status"],
            "note": "h=4 (12 month) secondary horizon, descriptive",
        },
        "holdout": {"status": holdout["status"],
                    "delta_ap_M1C_minus_B1": holdout["delta_ap_M1C_minus_B1"]},
        "premise": {
            "criterion": ("the premise is not supported if the primary ΔAP 95% CI includes 0 "
                          "and the MDE is small enough to rule out a practically useful "
                          "effect; a null with a large MDE is 'underpowered', not evidence "
                          "of absence"),
            "h8_primary": h1_h8["status"],
            "power_status": "POWERED" if powered else "UNDERPOWERED",
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
            "n_domains": panel.domain_count,
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
    primary_block["deltas_vs_baselines"] = {
        "M1C-B1": {"point_delta": point_delta,
                   "interpretation": "pre-registered primary comparison (H1); R_dom, h=8",
                   "bootstrap": primary_bootstrap["comparisons"].get("M1C-B1", {})},
        "M1C-B2": {"point_delta": point_delta_b2,
                   "interpretation": "secondary/descriptive comparison, not the primary test",
                   "bootstrap": primary_bootstrap["comparisons"].get("M1C-B2", {})},
        "M1C-B3": {"point_delta": point_delta_b3,
                   "interpretation": ("decisive secondary comparison; B3 is the strongest "
                                      "two-way exposure baseline (B1 x B2)"),
                   "bootstrap": primary_bootstrap["comparisons"].get("M1C-B3", {})},
    }
    dataset["configs"][f"{PRIMARY_RISK_SET}|h8"] = primary["dataset_rows"]
    dataset["totals"][f"{PRIMARY_RISK_SET}|h8"] = totals(primary["dataset_rows"])
    for name, block in secondary.items():
        dataset["configs"][name] = block["dataset_by_origin"]
        dataset["totals"][name] = totals(block["dataset_by_origin"])
    dataset["holdout_configs"] = holdout["dataset_by_origin"]
    dataset["holdout_totals"] = totals(holdout["dataset_by_origin"])
    dataset["primary_origins_with_undefined_ap"] = primary_block["origins_with_undefined_ap"]
    dataset["notes"] = {
        "mean_per_origin_ap_n": (
            "mean per-origin AP is the mean over origins where AP is defined; origins with "
            "zero positive (or zero negative) test cells have no AP and are listed in "
            "config.origins_with_undefined_ap"),
        "holdout": ("post-2015 origins are descriptive only and never enter the primary "
                    "test or any bootstrap"),
        "adjacency": ("R_dom_adj and the adjacency features use sibling domains sharing a "
                      "config category band; see config.implementation_interpretations"),
    }

    results = {
        "schema": RESULTS_SCHEMA,
        "generated_at": utc_now(),
        "panel_sha256": panel.sha256,
        "git_commit": git_commit(),
        "seed": SEED,
        "config": {
            "protocol": PROTOCOL_PATH,
            "protocol_panel_builder": PANEL_BUILDER,
            "amendments_applied": [],
            "amendment_log_note": (
                "the frozen protocol's amendment log is empty; this implementation adds no "
                "protocol amendment, only the interpretation notes listed in "
                "implementation_interpretations below"),
            "freeze_statement": (
                "the hist_v2 pre-registration was frozen on 2026-11-03 before any hist_v2 "
                "model was fitted and before any hist_v2 outcome metric was produced; no "
                "hist_v2 model had been fitted before the freeze"),
            "primary_metric": ("mean per-origin average precision, R_dom, h=8 (24 months), "
                               "ΔAP(M1C-B1) with the decisive ΔAP(M1C-B3) secondary"),
            "secondary_metrics": ["pooled AP", "ROC-AUC", "Brier", "ECE-10",
                                  "precision@10", "precision@25",
                                  "recall at 10% alert budget",
                                  "false-alarm rate at 10% alert budget"],
            "risk_sets": {
                PRIMARY_RISK_SET: ("established filer (>=1 material event by t) AND pair "
                                   "has no domain event by t; no adjacency restriction"),
                SECONDARY_RISK_SET: ("R_dom AND the firm already has a material event in a "
                                     "different domain of the same category band"),
            },
            "adjacency_definition": (
                "sibling domains = domains whose config `category` bands intersect; "
                "R_dom_adj = R_dom restricted to firms active in a sibling domain strictly "
                "before t. The literal 'different domain' reading is implied by firm "
                "establishment at domain granularity, so the category-band operationalisation "
                "is used to preserve hist_v1's adjacency estimand"),
            "horizons": {"h8": 8, "h4": 4},
            "origins": {
                "h8": [panel.quarters[origin] for origin in
                       evaluation_origins(panel, 8)][:args.max_origins or None],
                "h4": [panel.quarters[origin] for origin in
                       evaluation_origins(panel, 4)][:args.max_origins or None],
                "holdout_h8": holdout["origins"],
            },
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
                          "B2": "domain base rate (same smoothing)",
                          "B3": "B1 x B2 renormalised to training prevalence"},
            "bootstrap": {"reps": bootstrap_reps, "seed": SEED, "cluster": "company",
                          "pairing": "same resamples for every model",
                          "interval": "percentile (int(q*size) index convention)",
                          "degenerate_handling": (
                              "per resample and origin AP is computed only when the origin "
                              "has >=1 positive and >=1 negative; the per-origin mean is "
                              "taken over computable origins and the count is recorded; if "
                              "more than 5% of resamples have fewer than ceil(25/30 * "
                              "n_origins) computable origins the bootstrap is UNRELIABLE and "
                              "no CI is quoted"),
                          "reliability_gate": ("UNRELIABLE if >5% of resamples have fewer than "
                                               "ceil(25/30 * n_origins) computable origins"),
                          "mde": "MDE = (z_0.975 + z_0.80) * bootstrap sd of the delta"},
            "permutation": {"requested": PERMUTATION_REPS, "achieved": n_permutations,
                            "seed": SEED, "scheme": permutation_block["scheme"]},
            "alert_budget": {"threshold": "weighted training-score quantile at 1 - budget",
                             "budgets": list(ALERT_BUDGETS),
                             "primary": PRIMARY_ALERT_BUDGET},
            "feature_groups": {key: list(value) for key, value in FEATURE_GROUPS.items()},
            "feature_definitions": FEATURE_DEFINITIONS,
            "feature_source": panel.feature_source,
            "event_counts_audit": panel.event_count_audit,
            "power_target": {"mde_80pct_power_alpha_0.05_max_ap_points": MDE_TARGET_AP_POINTS,
                             "rule": ("if the measured MDE exceeds the target the result is "
                                      "declared underpowered in advance, whatever its "
                                      "p-value (protocol section 8)")},
            "implementation_interpretations": [
                ("domain-level adjacency is operationalised over sibling domains sharing a "
                 "config `category` band. Rationale: the literal protocol condition 'the firm "
                 "already has an activity in a different domain' is implied by firm "
                 "establishment for every unentered candidate domain, so R_dom_adj would be "
                 "identical to R_dom and adj_act_8 would duplicate firm_act_8 (adj_share "
                 "would be identically 1.0). The category-band translation preserves "
                 "hist_v1's adjacency estimand and the protocol's stated comparison purpose."),
                ("the 15th feature is `domain_share` (the domain-level analog of hist_v1 "
                 "`cat_share`): the share of the company's ever events in the candidate "
                 "domain's sibling domains. The literal own-domain share is identically 0 on "
                 "candidate cells because any own-domain event removes the cell from the "
                 "risk set."),
                ("h=4 secondary origins are the same 21 annual Q1 origins 1995..2015 as the "
                 "primary horizon (both mature inside the frozen 2026-Q2 grid)."),
                ("no fusion lanes are used: hist_v2 sections 9-10 contain no trial/publication "
                 "fusion test and make no Target B claims."),
                ("--quick reduces bootstrap reps to 200 and permutation reps to 5 only; the "
                 "full run uses the pre-registered 2,000 / 200."),
            ],
            "workers": workers,
            "quick": quick,
            "max_origins": args.max_origins,
            "runtime_seconds": None,
            "phase_seconds": phases,
            "deviations_and_limitations": [
                ("the panel's event_qidx is the availability quarter inherited from hist_v1 "
                 "(decision date); the hist_v1 availability approximation is inherited"),
                ("the domain taxonomy is the current, unversioned config mapping applied to "
                 "history (hist_v1 protocol section 12.4 limitation, inherited unchanged)"),
                ("the domain event aggregation sums per-quarter event_counts from the hist_v1 "
                 "panel; 14,704 material events collapse into 7,538 domain pair-quarters"),
                ("per-company/post-hoc heterogeneity blocks are not part of the frozen hist_v2 "
                 "protocol and are not reported"),
                ("the 200-permutation null shuffles labels within (origin, domain): it "
                 "preserves origin prevalence and domain entry counts but not per-company "
                 "entry totals (infeasible within the frozen risk sets)"),
            ],
        },
        "dataset": dataset,
        "primary": primary_block,
        "secondary": secondary,
        "robustness": {
            "eras": eras,
            "feature_groups": ablations,
            "permutation_null": permutation_block,
            "attribution_sensitivity_no_acquired": attribution_sensitivity,
        },
        "holdout": holdout,
        "lead_time": {
            "model": "M1C", "budget": PRIMARY_ALERT_BUDGET,
            "entries": {key: value for key, value in entries.items() if key != "entries"},
            "primary_budget": primary_alert,
            "h5_frontier": h5_rows,
        },
        "power": {
            "mde_target_ap_points": MDE_TARGET_AP_POINTS,
            "status": "POWERED" if powered else "UNDERPOWERED",
            "smoke_estimate": bool(quick),
            "smoke_estimate_note": (
                "computed from a --quick bootstrap (200 resamples); this is a smoke estimate, "
                "not the pre-registered result, which uses 2,000 resamples" if quick else
                "computed from the pre-registered 2,000-resample bootstrap"),
            "primary_M1C_minus_B1": {
                "mde_80pct_power_alpha_0.05": mde_primary,
                "bootstrap_sd": primary_delta.get("sd"),
                "meets_target": bool(powered),
            },
            "decisive_M1C_minus_B3": {
                "mde_80pct_power_alpha_0.05": b3_verdict["mde_80pct_power_alpha_0.05"],
                "bootstrap_sd": delta_b3.get("sd"),
                "meets_target": bool(b3_verdict["mde_80pct_power_alpha_0.05"] is not None
                                     and b3_verdict["mde_80pct_power_alpha_0.05"]
                                     <= MDE_TARGET_AP_POINTS),
            },
        },
        "leakage_controls": {
            "label_purge": {"asserted_per_origin": True, "violations": 0,
                            "detail": "every fitted training cell satisfies t' + h <= t; "
                                      "asserted in training_sample()"},
            "feature_availability": "features computed only from qidx <= t; labels only from "
                                    "t < qidx <= t + h",
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
    print(f"primary mean AP M1C={primary['mean_per_origin_ap']['M1C']['mean']} "
          f"B1={primary['mean_per_origin_ap']['B1']['mean']} "
          f"B3={primary['mean_per_origin_ap']['B3']['mean']}")
    print(f"ΔAP(M1C-B1)={point_delta} ΔAP(M1C-B3)={point_delta_b3} "
          f"bootstrap={primary_bootstrap['status']} power={results['power']['status']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
