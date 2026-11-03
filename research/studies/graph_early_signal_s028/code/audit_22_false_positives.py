"""S-028 correction round 1, audit 22: per-case false-positive failure analysis.

The round-1 study (LIMITATIONS.md L14 / B-NEXT-2) explicitly did *not* perform the
pre-registered narrative per-case review of the highest-ranked negative rows.  This
script does it, deterministically and read-only, on the stored per-row predictions.

WHAT IS DONE
------------
1. Selection rule (fixed, stated in the artifact and the report):
       for each H=4q holdout origin, rank every row by G1_graph predicted probability
       (descending, stable); take the first k rows with label == 0, where
       k = max(30, ceil(0.01 * n_origin))  ->  k = 30 for all three holdout origins
       (n = 1722 / 1721 / 1716; 1% = 17.2/17.2/17.2, so the floor 30 binds).
   The same rule is applied to B2_frozen_spec16 to mark each case
   ``shared_with_b2`` (already a top-k false positive of the strong non-graph
   baseline) or ``graph_specific`` (only the graph model puts it in the top-k).

2. For every selected case the raw records are pulled from the frozen DB:
   applicant_raw -> company_key variants, the company's DB-wide event history, the
   track's DB identity (name/category/keywords) and the pair's prior / in-window /
   after-window filings with event_id, kind, event_date, available_at, device_name,
   clearance_type, supplement_type/supplement_number.

3. The four reliability checks requested by the correction-round brief are run per
   case: entity attribution (same applicant under another company key, ambiguous
   applicant strings, acquired-alias hindsight), track attribution (product-code ->
   track reproducibility against the shipped config map, single undated taxonomy),
   database left truncation (does the DB cover the whole 36-month dormancy window),
   and a metric-level check of whether the graph features merely restate historical
   activity counts.

4. The graph-restatement check is quantitative, not hand-wavy: the script rebuilds
   the exact S-028 feature matrix from the DB (panel + SnapshotSeries, identical to
   the experiment), re-fits the G1 and B2 logistic models at each holdout origin and
   proves bit-level parity against the stored probabilities.  It then decomposes
   each case's G1 logit into B3 / graph / intercept contributions with the model's
   own training means and scales, and reports, for each graph feature, its maximum
   |Pearson r| against the 16 B3 history features over all holdout rows.  Features
   with |r| >= 0.7 are thereby proven to be approximate restatements of activity
   counts (this reproduces NEGATIVE_RESULTS N4: g_twohop_reach r=0.84,
   g_company_eigenvector r=0.80).

5. Each case is assigned exactly one primary category, in this fixed priority:
       LABEL_FAILURE                - a raw in-window filing of the same (company,
                                      track) exists but is not a qualifying event
                                      (Special/Abbreviated/Direct/Dual/Post-NSE
                                      510(k) or a PMA supplement), so the pre-
                                      registered label rule calls the row negative.
       DATA_FAILURE                 - the label would be / should be different because
                                      of data attribution or coverage: entity swap,
                                      track-assignment conflict, lane-unobservable
                                      pair premise, or DB truncation.
       RELATIONAL_CONSTRUCT_FAILURE - no label/data artifact, and the row is in the
                                      top-k only because of the graph increment
                                      (graph_specific and dlogit > 0): the relational
                                      reasoning encoded by the graph features is the
                                      cause of the false positive.
       MODEL_FAILURE                - everything else: a false positive shared with
                                      the non-graph baseline, explained by activity
                                      counts, with no label/data/relational artifact.
       UNVERIFIABLE                 - the DB has no evidence at all: company has no
                                      post-cutoff record and no other frozen source
                                      can establish what happened.
   The priority is fixed in ``classify_case`` and documented in the report.

OUTPUTS
-------
``artifacts/correction_round_1/false_positive_cases.json``:
    selection rule, reproduction/parity record, graph-redundancy table, the 90
    per-case evidence records, and the aggregate category distribution.

Usage:  python audit_22_false_positives.py
Runtime is a few seconds; the DB is verified by size + SHA-256 first.  The script
re-execs itself once with ``PYTHONHASHSEED=0`` and rounds output floats to 1e-10, so
repeated runs write a byte-identical ``false_positive_cases.json``.
"""
from __future__ import annotations

import gzip
import json
import math
import os
import re
import sqlite3
import subprocess
import sys
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path
from typing import Any

# Determinism: the original SnapshotSeries power iteration accumulates over Python
# sets, whose iteration order depends on the interpreter's string-hash seed, so the
# last bits of the eigenvector features (and the stored-prediction parity residue)
# differ between processes.  Re-exec once with PYTHONHASHSEED=0 so repeated runs of
# this script produce byte-identical output.
if os.environ.get("PYTHONHASHSEED") != "0":
    _ENV = dict(os.environ)
    _ENV["PYTHONHASHSEED"] = "0"
    raise SystemExit(subprocess.call(
        [sys.executable, os.path.abspath(__file__), *sys.argv[1:]], env=_ENV))

import numpy as np

STUDY = Path(__file__).resolve().parents[1]
CODE = Path(__file__).resolve().parent
REPO_ROOT = STUDY.parents[2]
for _path in (str(CODE), str(REPO_ROOT)):
    if _path not in sys.path:
        sys.path.insert(0, _path)

from s028_lib import (  # noqa: E402
    B3_FEATURES,
    G1_FEATURES,
    SnapshotSeries,
    FastLogisticRegression,
    build_entry_panel,
    load_events,
    verify_frozen_db,
)
import s028_experiment as experiment  # noqa: E402  (original driver; imported read-only)

DB = Path(r"D:\DEPPSKK\worktrees\integration-v2\data\research.sqlite")
PREDICTIONS = STUDY / "artifacts" / "predictions_H4q.json.gz"
OUT = STUDY / "artifacts" / "correction_round_1" / "false_positive_cases.json"
CONFIG = Path(r"D:\DEPPSKK\medradar\config")

HORIZON_MONTHS = 12          # H = 4 quarters, pre-registered primary analysis
HORIZON_QUARTERS = 4
TOP_K_MIN = 30               # at least 30 per origin (the "top 1%" rule is 17-18)
TOP_FRACTION = 0.01
GRAPH_SPECIFIC_RULE = ("graph_specific := row is NOT in the B2_frozen_spec16 top-k "
                       "label==0 set of the same origin")
REDUNDANCY_THRESHOLD = 0.70  # |r| >= .7 with a B3 count => activity-count restatement
G1_ALL = list(B3_FEATURES) + list(G1_FEATURES)

# Acquisition close dates are external facts imported from audit_13_entity_mapping.py
# (each row there carries its source URL); they are used only to flag acquired-alias
# hindsight in company histories, never to relabel an event.
ACQUISITIONS = [
    {"alias": "COVIDIEN", "parent": "medtronic", "close": "2015-01"},
    {"alias": "C R BARD", "parent": "bd", "close": "2017-12"},
    {"alias": "BARD ACCESS SYSTEMS", "parent": "bd", "close": "2017-12"},
    {"alias": "CAREFUSION", "parent": "bd", "close": "2015-03"},
    {"alias": "ST JUDE MEDICAL", "parent": "abbott", "close": "2017-01"},
    {"alias": "WRIGHT MEDICAL", "parent": "stryker", "close": "2020-11"},
    {"alias": "MAKO SURGICAL", "parent": "stryker", "close": "2013-12"},
    {"alias": "VARIAN MEDICAL SYSTEMS", "parent": "siemens_healthineers", "close": "2021-04"},
    {"alias": "SHOCKWAVE MEDICAL", "parent": "johnson_johnson_medtech", "close": "2024-05"},
    {"alias": "TOSHIBA MEDICAL", "parent": "canon_medical", "close": "2016-12"},
    {"alias": "AXONICS", "parent": "boston_scientific", "close": "2024-11"},
]

# Generic words that must not count as evidence that two applicant strings name the
# same firm (they occur in track names / company suffixes, not as brand tokens).
GENERIC_TOKENS = {
    "CORPORATION", "COMPANY", "MEDICAL", "HEALTH", "HEALTHCARE", "SYSTEMS", "TECHNOLOGY",
    "PRODUCTS", "INCORPORATED", "HOLDINGS", "INTERNATIONAL", "SCIENTIFIC", "LIFESCIENCES",
    "GROUP", "DEVICES", "SURGICAL", "SURGERY", "NEUROVASCULAR", "CARDIOVASCULAR",
    "ORTHOPEDIC", "ORTHOPAEDIC", "DIAGNOSTICS", "THERAPEUTICS", "SOLUTIONS", "SERVICES",
    "INDUSTRIES", "LABORATORIES", "PHARMACEUTICAL", "BIOTECHNOLOGY", "CLINICAL",
}


# --------------------------------------------------------------------------- utils
def add_months(day: str, months: int) -> str:
    """Month-start arithmetic on an ISO date string (all origins are month starts)."""
    year, month = int(day[:4]), int(day[5:7])
    index = month - 1 + months
    year += index // 12
    month = index % 12 + 1
    return f"{year:04d}-{month:02d}-01"


def norm(text: str) -> str:
    """Normalise an applicant/alias string for substring matching (audit_13 rule)."""
    text = (text or "").upper()
    text = re.sub(r"[^A-Z0-9 ]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def brand_tokens(company: dict[str, Any]) -> set[str]:
    """Distinctive name/alias tokens of a roster company (no generic words)."""
    text = " ".join([company.get("name_en") or ""] + json.loads(company.get("aliases") or "[]"))
    tokens = set()
    for token in re.findall(r"[A-Za-z0-9&]+", text.upper()):
        if len(token) >= 6 and token not in GENERIC_TOKENS:
            tokens.add(token)
    tokens.discard(norm(company.get("name_en") or ""))
    return tokens


def percentile_from_rank(rank: int, n: int) -> float:
    """Percentile of a rank (1 = highest): share of rows ranked below this one."""
    return round(100.0 * (n - rank) / n, 2)


def payload_fields(payload: str) -> dict[str, str]:
    try:
        row = json.loads(payload or "{}")
    except (TypeError, ValueError):
        row = {}
    return {
        "device_name": str(row.get("device_name") or row.get("generic_name") or
                           row.get("trade_name") or "")[:160],
        "clearance_type": str(row.get("clearance_type") or ""),
        "supplement_number": str(row.get("supplement_number") or ""),
        "supplement_type": str(row.get("supplement_type") or ""),
        "decision_date": str(row.get("decision_date") or ""),
    }


def is_qualifying(kind: str, kind_fields: dict[str, str]) -> bool:
    """S-028 qualifying rule (identical to s028_lib.is_qualifying)."""
    if kind == "510k":
        return kind_fields["clearance_type"].strip().lower() == "traditional"
    if kind == "pma":
        return kind_fields["supplement_number"].strip().upper() in ("", "0", "S0")
    return False


def is_material_pma(kind: str, kind_fields: dict[str, str]) -> bool:
    """Study-lane material rule: original PMA or a PANEL TRACK supplement."""
    if kind != "pma":
        return True
    supplement = kind_fields["supplement_number"].strip().upper()
    return supplement in ("", "0", "S0") or "PANEL TRACK" in kind_fields["supplement_type"].upper()


def summarise_event(row: dict[str, Any]) -> dict[str, Any]:
    """One raw regulatory event in the evidence shape used by the report."""
    kind = row["kind"]
    fields = payload_fields(row.get("payload") or "")
    return {
        "event_id": row["event_id"],
        "kind": kind,
        "event_date": (row.get("event_date") or "")[:10],
        "available_at": (row.get("available_at") or "")[:10],
        "applicant_raw": row.get("applicant_raw"),
        "company_key": row.get("company_key"),
        "track_id": row.get("track_id"),
        "product_code": row.get("product_code"),
        "device_name": fields["device_name"],
        "clearance_type": fields["clearance_type"],
        "supplement_number": fields["supplement_number"],
        "supplement_type": fields["supplement_type"],
        "qualifying": is_qualifying(kind, fields),
        "material_in_study_lane": is_material_pma(kind, fields),
    }


# --------------------------------------------------------------------------- model
def build_graph_model():
    """Rebuild the exact S-028 H=4q panel/features and re-fit G1 + B2.

    Returns the panel rows (with and without graph features), the fitted models per
    holdout origin, and the parity record against the stored predictions.
    """
    events = load_events(DB)
    panel = build_entry_panel(events, entity_field="company_key",
                              horizon_months=HORIZON_MONTHS, label_kind="qualifying",
                              dataset_version="s028_H4q")
    rows = panel["examples"]
    origins = panel["cutoffs"]
    series = SnapshotSeries(events, origins)
    rows_graph = experiment.attach_graph(rows, series)

    with gzip.open(PREDICTIONS, "rt", encoding="utf-8") as handle:
        stored = json.load(handle)
    holdouts = stored["panel"]["holdouts"]

    models = {}
    parity = {"per_origin": {}, "ok": True, "checked_at": "rebuild-from-frozen-db"}
    for origin in holdouts:
        train_g = experiment.eligible_training_rows(rows_graph, origin, HORIZON_MONTHS)
        train_b = experiment.eligible_training_rows(rows, origin, HORIZON_MONTHS)
        model_g = FastLogisticRegression(G1_ALL).fit(
            [row["features"] for row in train_g], [int(row["label"]) for row in train_g])
        model_b = FastLogisticRegression(list(B3_FEATURES)).fit(
            [row["features"] for row in train_b], [int(row["label"]) for row in train_b])
        test_index = [i for i, row in enumerate(rows) if row["cutoff"] == origin]
        probs_g = model_g.predict_proba([rows_graph[i]["features"] for i in test_index])
        probs_b = model_b.predict_proba([rows[i]["features"] for i in test_index])
        stored_g = stored["specs"]["G1_graph"]["predictions"][origin]["probs"]
        stored_b = stored["specs"]["B2_frozen_spec16"]["predictions"][origin]["probs"]
        diff_g = max(abs(a - b) for a, b in zip(probs_g, stored_g))
        diff_b = max(abs(a - b) for a, b in zip(probs_b, stored_b))
        parity["per_origin"][origin] = {
            "n_test_rows": len(test_index),
            "n_train_rows_G1": len(train_g), "n_train_rows_B2": len(train_b),
            # formatted as strings: the JSON writer rounds floats to 1e-10 for
            # reproducibility, which would otherwise erase the 1e-16 parity residue.
            "max_abs_prob_diff_G1": f"{diff_g:.3e}",
            "max_abs_prob_diff_B2": f"{diff_b:.3e}",
            "parity_threshold": 1e-9,
            "ok": diff_g < 1e-9 and diff_b < 1e-9,
        }
        parity["ok"] = parity["ok"] and parity["per_origin"][origin]["ok"]
        models[origin] = (model_g, model_b)
    if not parity["ok"]:
        raise RuntimeError(f"reconstructed predictions do not match stored artifact: {parity}")
    return events, rows, rows_graph, stored, holdouts, models, parity


def decompose(model: FastLogisticRegression, row_features: dict[str, Any]) -> dict[str, Any]:
    """Split a row's logit into per-feature contributions plus the intercept."""
    names = list(model.feature_names)
    raw = np.array([float(row_features.get(name, np.nan)) for name in names])
    medians = np.array([model.medians[name] for name in names])
    raw = np.where(np.isfinite(raw), raw, medians)
    z = (raw - model.means) / model.scales
    contributions = model.weights * z
    return {"logit": float(contributions.sum() + model.intercept),
            "contributions": dict(zip(names, contributions)),
            "intercept": float(model.intercept),
            "z": dict(zip(names, z))}


# ----------------------------------------------------------------------- selection
def select_cases(stored: dict[str, Any], holdouts: list[str]) -> list[dict[str, Any]]:
    """Apply the fixed top-k label==0 selection rule to G1 and the B2 comparison."""
    cases = []
    for origin in holdouts:
        g1_block = stored["specs"]["G1_graph"]["predictions"][origin]
        b2_block = stored["specs"]["B2_frozen_spec16"]["predictions"][origin]
        labels = np.asarray(g1_block["labels"], dtype=int)
        probs_g1 = np.asarray(g1_block["probs"], dtype=float)
        probs_b2 = np.asarray(b2_block["probs"], dtype=float)
        if list(labels) != list(b2_block["labels"]) or list(g1_block["pairs"]) != list(b2_block["pairs"]):
            raise RuntimeError(f"G1/B2 rows are not aligned at origin {origin}")
        n = len(labels)
        k = max(TOP_K_MIN, int(math.ceil(TOP_FRACTION * n)))
        order_g1 = np.argsort(-probs_g1, kind="stable")
        order_b2 = np.argsort(-probs_b2, kind="stable")
        rank_g1 = np.empty(n, dtype=int)
        rank_b2 = np.empty(n, dtype=int)
        rank_g1[order_g1] = np.arange(1, n + 1)
        rank_b2[order_b2] = np.arange(1, n + 1)
        fp_order_g1 = [int(i) for i in order_g1 if labels[i] == 0]
        fp_order_b2 = [int(i) for i in order_b2 if labels[i] == 0]
        selected = fp_order_g1[:k]
        b2_set = set(fp_order_b2[:k])
        for rank, index in enumerate(selected, start=1):
            cases.append({
                "origin": origin, "row_index": int(index),
                "company_key": g1_block["companies"][index],
                "track_id": g1_block["tracks"][index],
                "pair": g1_block["pairs"][index],
                "g1_prob": float(probs_g1[index]),
                "b2_prob": float(probs_b2[index]),
                "g1_rank_all": int(rank_g1[index]),
                "g1_fp_rank": rank,
                "b2_rank_all": int(rank_b2[index]),
                "b2_fp_rank": fp_order_b2.index(index) + 1 if index in b2_set else None,
                "b2_percentile": percentile_from_rank(int(rank_b2[index]), n),
                "shared_with_b2": index in b2_set,
                "n_origin_rows": n,
                "k": k,
                "selection_threshold_g1_prob": float(probs_g1[fp_order_g1[k - 1]]),
            })
    cases.sort(key=lambda c: (c["origin"], -c["g1_prob"], c["company_key"], c["track_id"]))
    return cases


# ------------------------------------------------------------------------ raw data
def load_raw(db_path: Path) -> tuple[list[dict[str, Any]], dict[str, Any], dict[str, Any]]:
    """Load every 510(k)/PMA row with parsed payload, plus the roster and taxonomy."""
    connection = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        raw = [dict(row) for row in connection.execute(
            "SELECT event_id, kind, event_date, available_at, company_key, applicant_raw, "
            "track_id, product_code, payload FROM events")]
        companies = {row["key"]: dict(row) for row in connection.execute("SELECT * FROM companies")}
        tracks = {row["id"]: dict(row) for row in connection.execute("SELECT * FROM tracks")}
    finally:
        connection.close()
    for row in raw:
        fields = payload_fields(row.get("payload") or "")
        row["_fields"] = fields
        row["_day"] = (row.get("event_date") or "")[:10]
        row["_qualifying"] = is_qualifying(row["kind"], fields)
        row["_material"] = is_material_pma(row["kind"], fields)
    raw.sort(key=lambda row: (row["_day"], row["event_id"]))
    return raw, companies, tracks


# ------------------------------------------------------------------ case evidence
def build_case_record(case: dict[str, Any], *, raw: list[dict[str, Any]],
                      by_company: dict[str, list[dict[str, Any]]],
                      by_pair: dict[tuple[str, str], list[dict[str, Any]]],
                      by_applicant: dict[str, set[str]],
                      companies: dict[str, Any], tracks: dict[str, Any],
                      config_map: dict[str, str], redundancy: dict[str, Any],
                      models: dict[str, tuple[FastLogisticRegression, FastLogisticRegression]],
                      row_features: dict[str, Any]) -> dict[str, Any]:
    """Build the full evidence record for one selected false positive."""
    origin = case["origin"]
    window_end = add_months(origin, HORIZON_MONTHS)
    company_key, track_id = case["company_key"], case["track_id"]
    company = companies.get(company_key, {})
    track = tracks.get(track_id, {})
    pair_events = by_pair.get((company_key, track_id), [])
    company_events = by_company.get(company_key, [])

    prior_pair = [row for row in pair_events if row["_day"] <= origin]
    window_pair = [row for row in pair_events if origin < row["_day"] <= window_end]
    post_pair = [row for row in pair_events if row["_day"] > window_end]
    company_window = [row for row in company_events if origin < row["_day"] <= window_end]
    company_post = [row for row in company_events if row["_day"] > window_end]
    window_pair_qual = [row for row in window_pair if row["_qualifying"]]
    window_pair_nonqual = [row for row in window_pair if not row["_qualifying"]]
    # Events whose decision date is before the origin but whose estimated knowledge clock
    # (available_at = event_date + 14 days, L1) is after it: they are invisible to the
    # model at the origin even though the filing already existed.
    pair_in_clock_lag = [row for row in prior_pair if (row.get("available_at") or "")[:10] > origin]
    material_clock_lag = [row for row in pair_in_clock_lag if row["_material"]]

    other_tracks: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in company_window:
        if row["track_id"] != track_id:
            other_tracks[row["track_id"]].append(row)
    other_track_summary = []
    for other_id, rows in sorted(other_tracks.items(), key=lambda item: -len(item[1])):
        other_track_summary.append({
            "track_id": other_id,
            "n_events": len(rows),
            "n_qualifying": sum(1 for row in rows if row["_qualifying"]),
            "first_event_date": rows[0]["_day"], "last_event_date": rows[-1]["_day"],
        })

    # ---- attribution checks ------------------------------------------------
    # (a) entity: a window filing by one of the company's own applicant strings
    #     recorded under a different company_key, or an ambiguous raw string.
    applicant_variants = sorted({row["applicant_raw"] for row in company_events})
    applicant_set = set(applicant_variants)
    entity_switch = []
    for row in raw:
        if (row["company_key"] and row["company_key"] != company_key
                and row["applicant_raw"] in applicant_set
                and origin < row["_day"] <= window_end):
            entity_switch.append(summarise_event(row))
    ambiguous = {}
    for applicant in applicant_variants:
        keys = {key for key in by_applicant.get(applicant, set()) if key}
        if len(keys) > 1:
            ambiguous[applicant] = sorted(keys)
    acquired_aliases = []
    via_acquired = 0
    for acquisition in ACQUISITIONS:
        if acquisition["parent"] != company_key:
            continue
        alias_events = [row for row in company_events
                        if norm(acquisition["alias"]) in norm(row["applicant_raw"] or "")]
        acquired_aliases.append({"alias": acquisition["alias"], "close": acquisition["close"],
                                 "n_events": len(alias_events)})
        via_acquired += len(alias_events)
    # (b) track: product-code -> track mapping provenance for the pair's prior filings.
    pair_codes = sorted({row["product_code"] for row in prior_pair if row["product_code"]})
    code_map = {code: config_map.get(code) for code in pair_codes}
    unmapped_codes = [code for code in pair_codes if code not in config_map]
    conflict_codes = [code for code, mapped in code_map.items()
                      if mapped is not None and mapped != track_id]
    track_conflicts = []
    for row in company_window:
        if row["track_id"] == track_id or not row["_qualifying"]:
            continue
        mapped = config_map.get(row["product_code"])
        if mapped == track_id:
            track_conflicts.append({**summarise_event(row), "config_track": mapped})
    # (c) database truncation: the 36-month dormancy window before the origin, and the
    #     label window itself, must sit inside the frozen DB's coverage.
    coverage_start = min(row["_day"] for row in raw)
    coverage_end = max(row["_day"] for row in raw)
    dormancy_start = add_months(origin, -36)
    truncation = {
        "coverage_start": coverage_start, "coverage_end": coverage_end,
        "dormancy_window_start": dormancy_start, "window_end": window_end,
        "db_covers_dormancy_window": dormancy_start > coverage_start,
        "db_covers_label_window": window_end <= coverage_end,
        "company_first_event_in_db": company_events[0]["_day"] if company_events else None,
        "company_last_event_in_db": company_events[-1]["_day"] if company_events else None,
        "pair_first_event_in_db": pair_events[0]["_day"] if pair_events else None,
        "pair_last_event_before_cutoff": prior_pair[-1]["_day"] if prior_pair else None,
    }
    # (d) graph restatement / score decomposition.
    model_g, model_b = models[origin]
    split_g = decompose(model_g, row_features)
    split_b = decompose(model_b, row_features)
    contributions = split_g["contributions"]
    b3_contrib = sum(value for name, value in contributions.items() if name in B3_FEATURES)
    graph_contrib = sum(value for name, value in contributions.items() if name in G1_FEATURES)
    denominator = abs(b3_contrib) + abs(graph_contrib) + abs(split_g["intercept"])
    graph_share = abs(graph_contrib) / denominator if denominator else 0.0
    contributors = sorted(((name, value) for name, value in contributions.items()
                           if name in G1_FEATURES), key=lambda item: -abs(item[1]))
    top_graph = [{"feature": name, "contribution": value,
                  "max_abs_r_with_b3": redundancy[name]["max_abs_r"],
                  "b3_partner": redundancy[name]["b3_partner"]}
                 for name, value in contributors[:4]]
    redundant_contrib = sum(value for name, value in contributors
                            if abs(redundancy[name]["max_abs_r"]) >= REDUNDANCY_THRESHOLD)
    redundant_graph_share = abs(redundant_contrib) / abs(graph_contrib) if abs(graph_contrib) > 1e-12 else 0.0
    delta_logit = split_g["logit"] - split_b["logit"]
    top = top_graph[0] if top_graph else None
    graph_driver_type = ("count_restatement"
                         if top and abs(top["max_abs_r_with_b3"]) >= REDUNDANCY_THRESHOLD
                         else "relational_analogy")

    # ---- primary classification -------------------------------------------
    if window_pair_nonqual:
        category = "LABEL_FAILURE"
        reason = ("in-window filings of the same (company, track) exist but are non-qualifying "
                  f"(n={len(window_pair_nonqual)}); the pre-registered label rule marks the row 0")
    elif entity_switch or track_conflicts or material_clock_lag \
            or truncation["db_covers_dormancy_window"] is False \
            or truncation["db_covers_label_window"] is False \
            or (prior_pair and not any(row["_material"] for row in prior_pair)):
        category = "DATA_FAILURE"
        if material_clock_lag:
            reason = ("the pair's dormant premise is a knowledge-clock artifact: a material filing "
                      f"is dated {material_clock_lag[0]['_day']} (before the origin) but has "
                      f"available_at={material_clock_lag[0]['available_at'][:10]}, i.e. the frozen "
                      "DB's estimated clock hides it from the model")
        else:
            reason = "the label is contradicted/made unreliable by attribution or DB coverage evidence"
    elif (not case["shared_with_b2"]) and delta_logit > 0:
        category = "RELATIONAL_CONSTRUCT_FAILURE"
        reason = ("graph-specific top false positive: the row enters the top-k only because of the "
                  f"graph increment (delta_logit={delta_logit:+.3f}), driven by {graph_driver_type}")
    elif company_window or company_post:
        category = "MODEL_FAILURE"
        reason = ("false positive shared with the non-graph baseline; the company stayed active but "
                  "did not file in the predicted track (no label/data/relational artifact)")
    else:
        category = "UNVERIFIABLE"
        reason = "no post-cutoff record and no frozen source can establish what the company did"

    late_entry = [summarise_event(row) for row in post_pair if row["_qualifying"]]
    if company_window and any(row["track_id"] == track_id for row in company_window):
        company_activity = "active_in_predicted_track"
    elif company_window:
        company_activity = "active_elsewhere"
    elif company_post:
        company_activity = "dormant_in_window_active_after"
    else:
        company_activity = "dormant_after_cutoff"

    record = {
        "case_id": f"H{HORIZON_QUARTERS}q|{origin}|{company_key}|{track_id}",
        "origin": origin, "window": {"start": origin, "end": window_end},
        "company_key": company_key, "track_id": track_id, "pair": case["pair"],
        "rank": {key: case[key] for key in (
            "g1_rank_all", "g1_fp_rank", "b2_rank_all", "b2_fp_rank", "b2_percentile",
            "shared_with_b2", "n_origin_rows", "k")},
        "scores": {
            "g1_prob": round(case["g1_prob"], 8), "b2_prob": round(case["b2_prob"], 8),
            "delta_prob": round(case["g1_prob"] - case["b2_prob"], 8),
            "g1_logit": round(split_g["logit"], 6), "b2_logit": round(split_b["logit"], 6),
            "delta_logit_graph_increment": round(delta_logit, 6),
        },
        "graph_specific": not case["shared_with_b2"],
        "graph_driver_type": graph_driver_type,
        "company": {
            "name_en": company.get("name_en"), "name_zh": company.get("name_zh"),
            "ticker": company.get("ticker"), "sector": company.get("sector"),
            "aliases": json.loads(company.get("aliases") or "[]"),
            "n_events_in_db": len(company_events),
            "applicant_raw_variants": [
                {"applicant_raw": applicant,
                 "n_events": sum(1 for row in company_events if row["applicant_raw"] == applicant)}
                for applicant in applicant_variants],
        },
        "track": {
            "name_en": track.get("name_en"), "name_zh": track.get("name_zh"),
            "category": track.get("category"),
            "keywords": json.loads(track.get("keywords") or "[]"),
            "n_events_in_db": sum(1 for row in raw if row["track_id"] == track_id),
            "n_companies_in_db": len({row["company_key"] for row in raw
                                      if row["track_id"] == track_id and row["company_key"]}),
            "pair_product_codes_before_cutoff": pair_codes[:20],
            "sample_device_names_before_cutoff": [row["_fields"]["device_name"]
                                                  for row in prior_pair[-4:] if row["_fields"]["device_name"]],
        },
        "prior_history": {
            "n_raw_events": len(prior_pair),
            "n_material_events": sum(1 for row in prior_pair if row["_material"]),
            "n_qualifying_events": sum(1 for row in prior_pair if row["_qualifying"]),
            "n_events_visible_at_origin": sum(1 for row in prior_pair
                                              if (row.get("available_at") or "")[:10] <= origin),
            "n_events_in_knowledge_clock_lag": len(pair_in_clock_lag),
            "knowledge_clock_lag_events": [summarise_event(row) for row in pair_in_clock_lag[:4]],
            "first_event_date": prior_pair[0]["_day"] if prior_pair else None,
            "last_event_date": prior_pair[-1]["_day"] if prior_pair else None,
            "last_4_events": [summarise_event(row) for row in prior_pair[-4:]],
        },
        "future_window": {
            "n_pair_events_all": len(window_pair),
            "n_pair_qualifying": len(window_pair_qual),
            "n_pair_nonqualifying": len(window_pair_nonqual),
            "pair_nonqualifying_events": [summarise_event(row) for row in window_pair_nonqual[:8]],
            "pair_nonqualifying_type_counts": dict(Counter(
                f"{row['kind']}|{row['_fields']['clearance_type'] or row['_fields']['supplement_type']}"
                for row in window_pair_nonqual).most_common(6)),
            "n_company_events": len(company_window),
            "n_company_events_in_predicted_track": sum(1 for row in company_window
                                                       if row["track_id"] == track_id),
            "n_company_events_other_tracks": sum(1 for row in company_window
                                                 if row["track_id"] != track_id),
            "company_activity_status": company_activity,
            "company_other_track_activity": other_track_summary,
            "company_other_track_qualifying_events_sample": [
                summarise_event(row) for row in company_window
                if row["track_id"] != track_id and row["_qualifying"]][:5],
            "pair_qualifying_after_horizon": late_entry[:6],
            "n_company_events_after_horizon": len(company_post),
        },
        "attribution_checks": {
            "entity": {
                "applicant_raw_variants": applicant_variants,
                "same_applicant_in_window_under_other_company_key": entity_switch,
                "ambiguous_applicant_strings": ambiguous,
                "acquired_alias_hindsight": {
                    "verified_acquired_aliases": acquired_aliases,
                    "events_via_acquired_aliases": via_acquired,
                    "share_of_company_events_pct": (round(100.0 * via_acquired / len(company_events), 2)
                                                    if company_events else None),
                },
            },
            "track": {
                "product_code_to_track": code_map,
                "codes_absent_from_shipped_config_map": unmapped_codes,
                "codes_whose_config_mapping_disagrees_with_db": conflict_codes,
                "in_window_qualifying_events_whose_code_maps_to_this_track": track_conflicts,
                "taxonomy_note": ("single undated 38-track taxonomy (tracks.updated_at="
                                  f"{max((track_row.get('updated_at') or '') for track_row in tracks.values())}); "
                                  "code->track mapping carries no effective date"),
            },
            "database_truncation": truncation,
            "coverage_impact": {
                "left_truncation_affects_this_case": not truncation["db_covers_dormancy_window"],
                "right_censoring_affects_this_case": not truncation["db_covers_label_window"],
                "post_window_observability_days": (
                    (date.fromisoformat(coverage_end) - date.fromisoformat(window_end)).days
                    if window_end <= coverage_end else None),
            },
        },
        "graph_restatement_check": {
            "graph_contribution_logit": round(graph_contrib, 6),
            "b3_contribution_logit": round(b3_contrib, 6),
            "intercept": round(split_g["intercept"], 6),
            "graph_share_of_logit": round(graph_share, 4),
            "redundant_graph_share": round(redundant_graph_share, 4),
            "top_graph_contributors": top_graph,
            "graph_redundancy_threshold": REDUNDANCY_THRESHOLD,
            "note": ("contribution = model weight x standardised feature value, using the "
                     "model's own training means/scales; redundancy = max |Pearson r| of the "
                     "graph feature against the 16 B3 history features over all holdout rows"),
            "b3_values": {name: round(float(row_features.get(name) or 0.0), 6) for name in B3_FEATURES},
            "g1_values": {name: round(float(row_features.get(name) or 0.0), 6) for name in G1_FEATURES},
        },
        "raw_records": {
            "prior_pair_events_sample": [summarise_event(row) for row in prior_pair[-4:]],
            "window_pair_events": [summarise_event(row) for row in window_pair[:6]],
            "post_window_pair_events": [summarise_event(row) for row in post_pair[:4]],
        },
        "category": category,
        "category_reason": reason,
        "sub_tags": sorted(tag for tag, flag in (
            ("graph_specific", not case["shared_with_b2"]),
            ("shared_with_baseline", case["shared_with_b2"]),
            ("late_entry_after_horizon", bool(late_entry)),
            ("nonqualifying_in_window", bool(window_pair_nonqual)),
            ("count_restatement_driver", graph_driver_type == "count_restatement"),
            ("knowledge_clock_lag", bool(material_clock_lag)),
        ) if flag),
        "evidence_summary": _evidence_summary(case, category, prior_pair, window_pair_nonqual,
                                              company_window, other_track_summary, late_entry,
                                              delta_logit, top, material_clock_lag),
    }
    return record


def _evidence_summary(case, category, prior_pair, window_nonqual, company_window,
                      other_tracks, late_entry, delta_logit, top_graph,
                      clock_lag_events=()) -> str:
    """One-line, record-citing evidence line for the markdown table."""
    company = case["company_key"]
    track = case["track_id"]
    if category == "LABEL_FAILURE":
        types = Counter(f"{row['kind']}|{row['_fields']['clearance_type'] or row['_fields']['supplement_type']}"
                        for row in window_nonqual)
        return (f"in-window non-qualifying filings n={len(window_nonqual)} "
                f"({', '.join(f'{k} x{v}' for k, v in types.most_common(3))}); "
                f"e.g. event_id={window_nonqual[0]['event_id']} date={window_nonqual[0]['_day']}")
    if category == "DATA_FAILURE":
        if clock_lag_events:
            event = clock_lag_events[0]
            qual = summarise_event(event)
            return (f"knowledge-clock artifact: material filing event_id={qual['event_id']} "
                    f"event_date={qual['event_date']} available_at={qual['available_at']} "
                    f"(before origin, invisible to the model); pair is not dormant in real time")
        return ("attribution/coverage evidence contradicts or blinds the label "
                "(see attribution_checks)")
    if category == "RELATIONAL_CONSTRUCT_FAILURE":
        driver = (f"{top_graph['feature']} (contrib {top_graph['contribution']:+.3f}, "
                  f"r={top_graph['max_abs_r_with_b3']:+.2f})") if top_graph else "n/a"
        return (f"graph-specific: delta_logit={delta_logit:+.3f} from {driver}; no in-window filing "
                f"of ({company},{track}); prior files n={len(prior_pair)}")
    if category == "UNVERIFIABLE":
        return "no post-cutoff record in the frozen DB for this company"
    top = other_tracks[0] if other_tracks else None
    extra = (f"; late qualifying filing on {late_entry[0]['event_date']} after horizon" if late_entry else "")
    return (f"shared top-k FP with B2; delta_logit={delta_logit:+.3f}; no in-window filing of "
            f"({company},{track}); company filed in {len(other_tracks)} other track(s) in window"
            + (f", largest {top['track_id']} n={top['n_events']} (q={top['n_qualifying']})" if top else "")
            + extra)


# ----------------------------------------------------------------------- aggregate
def aggregate(cases: list[dict[str, Any]], stored: dict[str, Any],
              holdouts: list[str], redundancy: dict[str, Any], parity: dict[str, Any],
              rows: list[dict[str, Any]], panel: dict[str, Any]) -> dict[str, Any]:
    by_category = Counter(case["category"] for case in cases)
    by_category_by_origin = {origin: dict(Counter(case["category"] for case in cases
                                                  if case["origin"] == origin))
                             for origin in holdouts}
    graph_specific = [case for case in cases if not case["rank"]["shared_with_b2"]]
    shared = [case for case in cases if case["rank"]["shared_with_b2"]]
    label_types = Counter()
    for case in cases:
        if case["category"] != "LABEL_FAILURE":
            continue
        for key, count in case["future_window"]["pair_nonqualifying_type_counts"].items():
            label_types[key] += count
    active = Counter(case["future_window"]["company_activity_status"] for case in cases)
    late = [case["case_id"] for case in cases if "late_entry_after_horizon" in case["sub_tags"]]
    selected_by_origin = {origin: sum(1 for case in cases if case["origin"] == origin) for origin in holdouts}
    selection_by_origin = {}
    for origin in holdouts:
        origin_cases = [case for case in cases if case["origin"] == origin]
        g1_block = stored["specs"]["G1_graph"]["predictions"][origin]
        labels = g1_block["labels"]
        probs = g1_block["probs"]
        order = sorted(range(len(labels)), key=lambda index: (-probs[index], index))
        kth_rank = max(case["rank"]["g1_rank_all"] for case in origin_cases)
        selection_by_origin[origin] = {
            "n_origin_rows": len(labels),
            "k": origin_cases[0]["rank"]["k"],
            "positives_total": sum(labels),
            "kth_selected_fp_g1_rank": kth_rank,
            "kth_selected_fp_g1_prob": round(min(case["scores"]["g1_prob"] for case in origin_cases), 8),
            "positives_ranked_above_kth_fp": sum(labels[index] for index in order[:kth_rank]),
            "b2_topk_fp_overlap": sum(1 for case in origin_cases if case["rank"]["shared_with_b2"]),
        }
    comparisons = stored["comparisons"]["G1_graph_minus_B2"]["company"]
    verdict = {
        "g1_pooled_ap": stored["specs"]["G1_graph"]["summary"]["pooled"]["pr_auc"],
        "b2_pooled_ap": stored["specs"]["B2_frozen_spec16"]["summary"]["pooled"]["pr_auc"],
        "delta_ap": round(comparisons["delta"], 8),
        "delta_ap_ci_low": comparisons["ci_low"], "delta_ap_ci_high": comparisons["ci_high"],
        "mde_80": comparisons["mde_80"],
        "delta_ap_over_mde": round(abs(comparisons["delta"]) / comparisons["mde_80"], 3),
        "note": "AP context is quoted unchanged from the round-1 artifact; this audit classifies "
                "the top of the ranking, it does not re-estimate AP.",
    }
    return {
        "n_cases": len(cases),
        "selected_per_origin": selected_by_origin,
        "selection_by_origin": selection_by_origin,
        "by_category": {key: by_category.get(key, 0) for key in
                        ("MODEL_FAILURE", "LABEL_FAILURE", "DATA_FAILURE",
                         "RELATIONAL_CONSTRUCT_FAILURE", "UNVERIFIABLE")},
        "by_category_pct": {key: round(100.0 * by_category.get(key, 0) / len(cases), 2) for key in
                            ("MODEL_FAILURE", "LABEL_FAILURE", "DATA_FAILURE",
                             "RELATIONAL_CONSTRUCT_FAILURE", "UNVERIFIABLE")},
        "by_category_by_origin": by_category_by_origin,
        "graph_specific_vs_shared": {
            "shared_with_b2_topk": len(shared),
            "graph_specific": len(graph_specific),
            "shared_pct": round(100.0 * len(shared) / len(cases), 2),
            "graph_specific_pct": round(100.0 * len(graph_specific) / len(cases), 2),
            "by_category": {
                "shared": dict(Counter(case["category"] for case in shared)),
                "graph_specific": dict(Counter(case["category"] for case in graph_specific)),
            },
            "mean_delta_logit_shared": round(float(np.mean([case["scores"]["delta_logit_graph_increment"]
                                                            for case in shared])), 4),
            "mean_delta_logit_graph_specific": round(float(np.mean(
                [case["scores"]["delta_logit_graph_increment"] for case in graph_specific])), 4),
        },
        "label_failure_evidence_types": dict(label_types.most_common()),
        "company_activity_status_counts": dict(active),
        "late_entry_after_horizon_cases": late,
        "redundancy_highlights": {
            feature: redundancy[feature] for feature in G1_FEATURES
            if abs(redundancy[feature]["max_abs_r"]) >= REDUNDANCY_THRESHOLD},
        "graph_increment_distribution": {
            "n_positive": sum(1 for case in cases if case["scores"]["delta_logit_graph_increment"] > 0),
            "mean": round(float(np.mean([case["scores"]["delta_logit_graph_increment"] for case in cases])), 4),
            "median": round(float(np.median([case["scores"]["delta_logit_graph_increment"] for case in cases])), 4),
            "min": round(min(case["scores"]["delta_logit_graph_increment"] for case in cases), 4),
            "max": round(max(case["scores"]["delta_logit_graph_increment"] for case in cases), 4),
        },
        "ap_context": verdict,
        "checks": {
            "entity_attribution_failures": sum(
                1 for case in cases
                if case["attribution_checks"]["entity"]["same_applicant_in_window_under_other_company_key"]),
            "ambiguous_applicant_cases": sum(
                1 for case in cases if case["attribution_checks"]["entity"]["ambiguous_applicant_strings"]),
            "cases_with_acquired_alias_history": sum(
                1 for case in cases if case["attribution_checks"]["entity"]["acquired_alias_hindsight"][
                    "events_via_acquired_aliases"] > 0),
            "cases_with_pair_event_in_knowledge_clock_lag": sum(
                1 for case in cases if case["prior_history"]["n_events_in_knowledge_clock_lag"] > 0),
            "cases_with_material_pair_event_in_knowledge_clock_lag": sum(
                1 for case in cases
                if any(event["material_in_study_lane"]
                       for event in case["prior_history"]["knowledge_clock_lag_events"])),
            "track_code_mapping_unreproducible_cases": sum(
                1 for case in cases if case["attribution_checks"]["track"][
                    "codes_absent_from_shipped_config_map"]),
            "left_truncation_affected_cases": sum(
                1 for case in cases if case["attribution_checks"]["coverage_impact"][
                    "left_truncation_affects_this_case"]),
            "right_censoring_affected_cases": sum(
                1 for case in cases if case["attribution_checks"]["coverage_impact"][
                    "right_censoring_affects_this_case"]),
        },
        "panel_context": {
            "n_examples": panel["n_examples"], "n_positives": panel["n_positives"],
            "base_rate": panel["n_positives"] / panel["n_examples"],
            "coverage_start": panel["coverage_start"], "coverage_end": panel["coverage_end"],
            "holdouts": holdouts,
        },
        "parity": parity,
    }


def compute_redundancy(rows_graph: list[dict[str, Any]], holdouts: list[str]) -> dict[str, Any]:
    """Max |Pearson r| of every graph feature against every B3 history feature."""
    feature_rows = [row["features"] for row in rows_graph if row["cutoff"] in set(holdouts)]
    names = list(B3_FEATURES) + list(G1_FEATURES)
    matrix = np.array([[float(row.get(name, np.nan)) for name in names] for row in feature_rows])
    matrix = np.nan_to_num(matrix)
    out = {}
    for offset, graph_name in enumerate(G1_FEATURES):
        column = matrix[:, len(B3_FEATURES) + offset]
        best = {"max_abs_r": 0.0, "r": 0.0, "b3_partner": None}
        for index, b3_name in enumerate(B3_FEATURES):
            other = matrix[:, index]
            if column.std() > 1e-12 and other.std() > 1e-12:
                r = float(np.corrcoef(column, other)[0, 1])
                if abs(r) > abs(best["r"]):
                    best = {"max_abs_r": round(abs(r), 3), "r": round(r, 3), "b3_partner": b3_name}
        out[graph_name] = best
    return out


def canonicalise(value: Any, digits: int = 10) -> Any:
    """Round every float so repeated runs are byte-identical.

    The original SnapshotSeries power iteration accumulates over Python sets, whose
    iteration order depends on the interpreter's string-hash seed; the resulting
    last-bit differences (~1e-16) are irrelevant to every claim but would make the
    JSON serialisation non-reproducible.  Rounding to 10 decimals removes them.
    """
    if isinstance(value, float):
        return round(value, digits)
    if isinstance(value, dict):
        return {key: canonicalise(item, digits) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [canonicalise(item, digits) for item in value]
    return value


# ---------------------------------------------------------------------------- main
def main() -> int:
    print("== S-028 audit 22: per-case false-positive review ==")
    verification = verify_frozen_db(DB)
    print(f"frozen DB verified: sha256={verification['sha256'][:16]}... size={verification['size_bytes']}")

    events, rows, rows_graph, stored, holdouts, models, parity = build_graph_model()
    print(f"panel rebuilt: {len(rows)} rows, origins={len(set(row['cutoff'] for row in rows))}, "
          f"holdouts={holdouts}")
    print(f"stored-prediction parity: {'OK' if parity['ok'] else 'FAILED'} "
          f"(max|diff| G1={max(float(v['max_abs_prob_diff_G1']) for v in parity['per_origin'].values()):.2e})")

    cases = select_cases(stored, holdouts)
    k_by_origin = {case["origin"]: case["k"] for case in cases}
    print(f"selected {len(cases)} top-k false positives "
          f"({', '.join(f'{origin}: k={k}' for origin, k in k_by_origin.items())})")
    raw, companies, tracks = load_raw(DB)
    by_company = defaultdict(list)
    by_pair = defaultdict(list)
    by_applicant = defaultdict(set)
    for row in raw:
        if row["company_key"]:
            by_company[row["company_key"]].append(row)
        if row["company_key"] and row["track_id"]:
            by_pair[(row["company_key"], row["track_id"])].append(row)
        if row["applicant_raw"]:
            by_applicant[row["applicant_raw"]].add(row["company_key"])
    for value in by_company.values():
        value.sort(key=lambda row: (row["_day"], row["event_id"]))
    print(f"raw lane loaded: {len(raw)} events; companies={len(companies)}; tracks={len(tracks)}")

    config_map = json.load(open(CONFIG / "product_code_tracks.json", encoding="utf-8"))
    redundancy = compute_redundancy(rows_graph, holdouts)
    feature_by_key = {(row["cutoff"], row["company_key"], row["track_id"]): row["features"]
                      for row in rows_graph}

    records = []
    for case in cases:
        features = feature_by_key[(case["origin"], case["company_key"], case["track_id"])]
        records.append(build_case_record(
            case, raw=raw, by_company=by_company, by_pair=by_pair,
            by_applicant=by_applicant, companies=companies, tracks=tracks,
            config_map=config_map, redundancy=redundancy, models=models,
            row_features=features))

    # panel metadata for context (same build as the experiment)
    panel_meta = {
        "n_examples": len(rows), "n_positives": sum(int(row["label"]) for row in rows),
        "coverage_start": min(row["day"] for row in events).isoformat(),
        "coverage_end": max(row["day"] for row in events).isoformat(),
        "holdouts": holdouts,
    }
    aggregates = aggregate(records, stored, holdouts, redundancy, parity, rows, panel_meta)

    payload = {
        "study": "S-028", "audit": "22_per_case_false_positives",
        "horizon": {"quarters": HORIZON_QUARTERS, "months": HORIZON_MONTHS},
        "inputs": {
            "db": str(DB), "db_sha256": verification["sha256"],
            "db_size_bytes": verification["size_bytes"],
            "predictions": str(PREDICTIONS),
            "config_product_code_tracks": str(CONFIG / "product_code_tracks.json"),
        },
        "selection_rule": {
            "rule": ("per holdout origin, stable-descending sort by G1_graph predicted "
                     "probability; take the first k rows with label==0, k=max(30, ceil(0.01*n))"),
            "k_rule": f"k = max({TOP_K_MIN}, ceil({TOP_FRACTION} * n_origin))",
            "k_per_origin": {origin: next(case["k"] for case in cases if case["origin"] == origin)
                             for origin in holdouts},
            "n_rows_per_origin": {origin: next(case["n_origin_rows"] for case in cases
                                               if case["origin"] == origin) for origin in holdouts},
            "selection_is_fixed_before_inspection": True,
            "tie_handling": "stable sort; no exact ties observed in the stored probabilities",
            "b2_comparison_rule": ("the identical top-k label==0 rule is applied to "
                                   "B2_frozen_spec16; a G1-selected case is 'shared_with_b2' "
                                   "iff it is also in that B2 set, 'graph_specific' otherwise"),
        },
        "classification_rules": {
            "priority": ["LABEL_FAILURE", "DATA_FAILURE", "RELATIONAL_CONSTRUCT_FAILURE",
                         "MODEL_FAILURE", "UNVERIFIABLE"],
            "LABEL_FAILURE": ("in-window raw filing of the same (company_key, track_id) that is "
                              "not a qualifying event: Special/Abbreviated/Direct/Dual/Post-NSE "
                              "510(k) or a PMA supplement"),
            "DATA_FAILURE": ("entity swap (same applicant_raw under another company_key in the "
                             "window), track-mapping conflict (code maps to the predicted track "
                             "but the event is filed under another track), a material pair filing "
                             "hidden by the estimated +14-day knowledge clock just before the "
                             "origin, lane-unobservable pair premise, or DB coverage that cannot "
                             "see the 36-month dormancy window or the label window"),
            "RELATIONAL_CONSTRUCT_FAILURE": ("no label/data artifact, row is graph_specific and "
                                            "the graph increment is positive (delta_logit>0): the "
                                            "relational features are the cause of the false positive"),
            "MODEL_FAILURE": ("false positive already present in the non-graph baseline, explained "
                              "by company/track activity counts, with no label/data/relational artifact"),
            "UNVERIFIABLE": "no post-cutoff record and no frozen source to establish what happened",
            "graph_driver_type": ("count_restatement if the largest graph contribution is a feature "
                                  f"with max|r|>={REDUNDANCY_THRESHOLD} against some B3 history "
                                  "feature, else relational_analogy"),
        },
        "graph_redundancy": redundancy,
        "cases": records,
        "aggregate": aggregates,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(canonicalise(payload), handle, ensure_ascii=False, indent=1, sort_keys=False)
        handle.write("\n")
    print(f"\nwrote {OUT} ({OUT.stat().st_size / 1e6:.2f} MB)")
    print("\ncategory distribution:")
    for category, count in aggregates["by_category"].items():
        print(f"  {category:28s} {count:3d}  ({aggregates['by_category_pct'][category]:5.1f}%)")
    print(f"\nshared with B2 top-k: {aggregates['graph_specific_vs_shared']['shared_with_b2_topk']} / "
          f"{len(cases)}; graph-specific: {aggregates['graph_specific_vs_shared']['graph_specific']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
