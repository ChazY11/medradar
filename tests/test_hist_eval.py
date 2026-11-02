"""Unit tests for the hist_v1 walk-forward evaluation harness.

Standard library only; no network, no repository data files, no models fitted outside
the tiny synthetic fixtures.  Run with::

    python -m unittest tests.test_hist_eval -v
"""
from __future__ import annotations

import importlib.util
import json
import math
import random
import re
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
EVAL_PATH = REPO_ROOT / "experiments" / "hist_v1" / "eval.py"


def _load_eval_module():
    spec = importlib.util.spec_from_file_location("hist_v1_eval", EVAL_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


H = _load_eval_module()

# --------------------------------------------------------------- fixture utilities
QUARTERS: list[str] = []
for _year in range(1976, 2026):
    for _quarter in range(1, 5):
        QUARTERS.append(f"{_year}-Q{_quarter}")
QUARTERS.extend(["2026-Q1", "2026-Q2"])
QIDX = {label: index for index, label in enumerate(QUARTERS)}
LAST_QIDX = len(QUARTERS) - 1


def quarter(year: int, number: int) -> int:
    return QIDX[f"{year}-Q{number}"]


TRACKS = [
    {"id": "t_cardio_a", "name_en": "Cardio A", "category": "cardiovascular",
     "domain": "cardiovascular"},
    {"id": "t_cardio_b", "name_en": "Cardio B", "category": "cardiovascular",
     "domain": "cardiovascular"},
    {"id": "t_img_a", "name_en": "Imaging A", "category": "imaging", "domain": "imaging"},
    {"id": "t_img_b", "name_en": "Imaging B", "category": "imaging", "domain": "imaging"},
]


def make_panel(events: dict[tuple[str, str], list[int]], *, tracks=None,
               event_counts: dict[tuple[str, str], list[int]] | None = None,
               with_counts: bool = True, audits: dict | None = None) -> dict:
    """Build a minimal ``hist_v1.panel.v1`` panel from ``{(company, track): [qidx]}``."""
    tracks = tracks or TRACKS
    companies = sorted({company for company, _track in events})
    pairs = []
    for (company, track), values in sorted(events.items()):
        values = sorted(values)
        counts = event_counts.get((company, track), [1] * len(values)) if event_counts else [1] * len(values)
        record = {
            "company_key": company,
            "track_id": track,
            "event_qidx": values,
            "event_iso": [QUARTERS[value] for value in values],
            "n_510k": sum(counts),
            "n_pma": 0,
        }
        if with_counts:
            record["event_counts"] = counts
        pairs.append(record)
    company_records = []
    for company in companies:
        own = [value for (key, _track), values in events.items() if key == company
               for value in values]
        company_records.append({
            "key": company,
            "display_name": company.title(),
            "cohort": "fixture",
            "total_material_events": len(own),
            "first_event_qidx": min(own),
            "last_event_qidx": max(own),
        })
    track_records = []
    for track in tracks:
        industry = [value for (company, key), values in events.items()
                    if key == track["id"] for value in values]
        firms = {company for (company, key) in events if key == track["id"]}
        record = dict(track)
        record["first_industry_qidx"] = min(industry) if industry else None
        record["n_firms_ever"] = len(firms)
        track_records.append(record)
    panel = {
        "schema": "hist_v1.panel.v1",
        "quarter_start": QUARTERS[0],
        "quarter_end": QUARTERS[-1],
        "quarters": list(QUARTERS),
        "companies": company_records,
        "tracks": track_records,
        "pairs": pairs,
    }
    if audits is not None:
        panel["audits"] = audits
    if with_counts and event_counts is None:
        panel["audits"] = {"panel_summary": {
            "n_material_events": sum(sum(pair["event_counts"]) for pair in pairs)}}
    return panel


def golden_panel() -> dict:
    """Tiny deterministic panel used by the golden end-to-end test.

    Entries: alpha -> t_cardio_b at 1996-Q1, gamma -> t_cardio_b at 1997-Q2,
    beta -> t_img_b at 1997-Q1, delta never enters.  With ``--max-origins 2`` the
    evaluation origins are 1995-Q1 and 1996-Q1.
    """
    events = {
        ("alpha", "t_cardio_a"): [40, 60, 100, 140],
        ("alpha", "t_cardio_b"): [80],
        ("beta", "t_img_a"): [30, 70, 120],
        ("beta", "t_img_b"): [84],
        ("gamma", "t_cardio_a"): [50, 90],
        ("gamma", "t_cardio_b"): [86],
        ("delta", "t_img_a"): [20, 60, 110],
    }
    return make_panel(events, with_counts=True)


def tiny_eval_panel() -> dict:
    """Company/track layout for the risk-set and product-feature tests."""
    events = {
        ("alpha", "t_cardio_a"): [76],
        ("beta", "t_img_a"): [80],
        ("gamma", "t_img_a"): [97],
        ("delta", "t_cardio_a"): [90],
        ("delta", "t_img_a"): [95],
        ("eps", "t_cardio_a"): [96],
    }
    return make_panel(events, with_counts=False)


# ------------------------------------------------------------------------- metrics
class MetricTests(unittest.TestCase):
    def test_average_precision_hand_computed(self):
        # scores descending: 1 (tp), 0, 1 -> 1*1/2 + ... standard AP = 0.8333333
        self.assertAlmostEqual(H.average_precision([1, 0, 1], [0.9, 0.8, 0.7]),
                               0.8333333333333333, places=12)
        # single tie block of two rows, one positive -> AP = 0.5
        self.assertAlmostEqual(H.average_precision([1, 0], [0.5, 0.5]), 0.5, places=12)
        # one tie block, one positive out of three -> AP = 1/3
        self.assertAlmostEqual(H.average_precision([1, 0, 0], [0.5, 0.5, 0.5]),
                               1.0 / 3.0, places=12)
        # perfect ranking
        self.assertAlmostEqual(H.average_precision([1, 1, 0, 0], [0.9, 0.8, 0.2, 0.1]),
                               1.0, places=12)
        # worst ranking: positives ranked last -> AP = 0.5 * (1/3 + 2/4) = 0.416666
        self.assertAlmostEqual(H.average_precision([0, 0, 1, 1], [0.9, 0.8, 0.2, 0.1]),
                               0.5 * (1 / 3 + 2 / 4), places=12)
        self.assertIsNone(H.average_precision([1, 1], [0.4, 0.6]))
        self.assertIsNone(H.average_precision([0, 0], [0.4, 0.6]))

    def test_average_precision_tie_order_invariance(self):
        labels = [1, 0, 1, 0, 1]
        scores = [0.5, 0.5, 0.4, 0.4, 0.9]
        base = H.average_precision(labels, scores)
        permutation = list(range(len(labels)))
        random.Random(3).shuffle(permutation)
        shuffled_labels = [labels[index] for index in permutation]
        shuffled_scores = [scores[index] for index in permutation]
        self.assertAlmostEqual(base, H.average_precision(shuffled_labels, shuffled_scores),
                               places=12)

    def test_average_precision_matches_rank_order_and_keys(self):
        labels = [1, 0, 1, 0]
        scores = [0.5, 0.5, 0.5, 0.5]
        companies = ["b", "a", "a", "b"]
        tracks = ["t1", "t2", "t1", "t2"]
        order = H.rank_order(scores, companies, tracks)
        self.assertEqual(order, [2, 1, 0, 3])   # score desc, company asc, track asc

    def test_weighted_ap_matches_materialised_duplicates(self):
        labels = [1, 0, 0, 1, 0]
        scores = [0.9, 0.7, 0.7, 0.4, 0.2]
        multiplicities = [2, 0, 1, 3, 1]
        material_labels: list[int] = []
        material_scores: list[float] = []
        for label, score, weight in zip(labels, scores, multiplicities):
            material_labels.extend([label] * weight)
            material_scores.extend([score] * weight)
        prepared = H.prepare_ap(labels, scores, list(range(len(labels))))
        self.assertAlmostEqual(H.ap_weighted(prepared, multiplicities),
                               H.average_precision(material_labels, material_scores),
                               places=12)
        # one positive cluster absent from the resample -> undefined AP
        prepared_zero = H.prepare_ap([1, 0], [0.9, 0.1], [0, 1])
        self.assertIsNone(H.ap_weighted(prepared_zero, [1, 0]))

    def test_roc_auc_hand_computed(self):
        self.assertAlmostEqual(H.roc_auc([1, 0, 1, 0], [0.9, 0.3, 0.8, 0.2]), 1.0)
        self.assertAlmostEqual(H.roc_auc([1, 0], [0.5, 0.5]), 0.5)
        # positive at 0.5 against negatives 0.9 and 0.3: one loss, one win -> 0.5
        self.assertAlmostEqual(H.roc_auc([1, 0, 0], [0.5, 0.9, 0.3]), 0.5)
        # tie group with one positive, one negative plus one negative below -> 0.75
        self.assertAlmostEqual(H.roc_auc([1, 0, 0], [0.5, 0.5, 0.1]), 0.75)
        self.assertIsNone(H.roc_auc([1, 1], [0.2, 0.9]))
        self.assertIsNone(H.roc_auc([0, 0], [0.2, 0.9]))

    def test_brier_and_ece_hand_computed(self):
        self.assertAlmostEqual(H.brier_score([1, 0], [0.9, 0.2]), (0.1 ** 2 + 0.2 ** 2) / 2)
        # 0.9 is in bin 9 (confidence .9, accuracy 1); 0.2 in bin 2 (.2, 0)
        self.assertAlmostEqual(H.expected_calibration_error([1, 0], [0.9, 0.2]),
                               0.5 * 0.1 + 0.5 * 0.2, places=12)
        self.assertAlmostEqual(H.expected_calibration_error([1], [1.0]), 0.0)
        self.assertIsNone(H.brier_score([], []))
        self.assertIsNone(H.expected_calibration_error([], []))

    def test_precision_at_k_hand_computed(self):
        labels = [1, 0, 1, 0, 0]
        order = [0, 2, 1, 3, 4]
        self.assertAlmostEqual(H.precision_at_k(labels, order, 2)["precision"], 1.0)
        self.assertAlmostEqual(H.precision_at_k(labels, order, 4)["precision"], 0.5)
        self.assertEqual(H.precision_at_k(labels, order, 25)["used"], 5)

    def test_weighted_quantile_and_percentile(self):
        values = [0.1, 0.2, 0.3, 0.4]
        weights = [1, 1, 1, 1]
        self.assertAlmostEqual(H.weighted_quantile(values, weights, 0.5), 0.2)
        self.assertAlmostEqual(H.weighted_quantile(values, weights, 0.0), 0.1)
        self.assertAlmostEqual(H.weighted_quantile(values, weights, 1.0), 0.4)
        self.assertAlmostEqual(H.percentile_sorted(values, 0.025), 0.1)
        self.assertAlmostEqual(H.percentile_sorted(values, 0.975), 0.4)

    def test_kendall_tau(self):
        self.assertAlmostEqual(H.kendall_tau([1, 2, 3], [1, 2, 3]), 1.0)
        self.assertAlmostEqual(H.kendall_tau([1, 2, 3], [3, 2, 1]), -1.0)


# ------------------------------------------------------------------- panel / PIT
class PanelTests(unittest.TestCase):
    def test_schema_deviation_raises(self):
        panel = make_panel({("alpha", "t_cardio_a"): [76]})
        panel["schema"] = "hist_v1.panel.v0"
        with self.assertRaises(ValueError) as context:
            H.Panel(panel)
        self.assertIn("hist_v1.panel.v1", str(context.exception))

    def test_risk_sets_hand_computed(self):
        panel = H.Panel(tiny_eval_panel())
        t = quarter(2000, 1)
        risk_adj = set(panel.risk_set(t, adjacency=True))
        risk_full = set(panel.risk_set(t, adjacency=False))
        self.assertEqual(risk_adj, {
            ("alpha", "t_cardio_b"),
            ("beta", "t_img_b"),
            ("delta", "t_cardio_b"),
            ("delta", "t_img_b"),
        })
        self.assertEqual(risk_full, risk_adj | {
            ("alpha", "t_img_a"),
            ("alpha", "t_img_b"),
            ("beta", "t_cardio_a"),
            ("beta", "t_cardio_b"),
            ("eps", "t_cardio_b"),
            ("eps", "t_img_a"),
            ("eps", "t_img_b"),
        })
        # gamma's first event is after the origin: never a candidate
        self.assertFalse(any(company == "gamma" for company, _track in risk_full))
        # eps is established exactly at t (condition 1 uses <= t) but its only track
        # started at t, so adjacency (strictly before t) excludes it from R_adj
        self.assertIn(("eps", "t_cardio_b"), risk_full)
        self.assertNotIn(("eps", "t_cardio_b"), risk_adj)
        # delta has an imaging event strictly before t, so it is adjacency-eligible there
        self.assertIn(("delta", "t_img_b"), risk_adj)

    def test_labels_and_maturity(self):
        panel = H.Panel(make_panel({("alpha", "t_cardio_a"): [76],
                                    ("alpha", "t_cardio_b"): [98, 105]}))
        t = quarter(2000, 1)   # qidx 96
        self.assertEqual(panel.label("alpha", "t_cardio_b", t, 4), 1)     # 98 in (96,100]
        self.assertEqual(panel.label("alpha", "t_cardio_b", t, 8), 1)     # 98 in (96,104]
        # an event at exactly t is NOT in the label window (t, t+h]
        panel_at_t = H.Panel(make_panel({("alpha", "t_cardio_a"): [76],
                                         ("alpha", "t_cardio_b"): [t]}))
        self.assertEqual(panel_at_t.label("alpha", "t_cardio_b", t, 4), 0)
        panel2 = H.Panel(make_panel({("alpha", "t_cardio_a"): [76],
                                     ("alpha", "t_cardio_b"): [105]}))
        self.assertEqual(panel2.label("alpha", "t_cardio_b", t, 8), 0)     # 105 > 104
        self.assertEqual(panel2.label("alpha", "t_cardio_b", t, 4), 0)
        panel3 = H.Panel(make_panel({("alpha", "t_cardio_a"): [76],
                                     ("alpha", "t_cardio_b"): [104]}))
        self.assertEqual(panel3.label("alpha", "t_cardio_b", t, 8), 1)     # boundary inclusive
        self.assertTrue(panel3.mature(quarter(2024, 1), 8))                # 192 + 8 <= 201
        self.assertFalse(panel3.mature(LAST_QIDX, 1))

    def test_features_hand_checked(self):
        t = quarter(2000, 1)   # 96
        panel = H.Panel(make_panel({
            ("alpha", "t_cardio_a"): [t - 20, t - 6, t - 2, t - 1],
            ("alpha", "t_img_a"): [t - 3],
            ("beta", "t_cardio_a"): [t - 4],
            ("gamma", "t_img_a"): [t - 10],
        }))
        features = panel.features("alpha", "t_cardio_b", t)
        expected = {
            "firm_act_4": math.log1p(3),        # t-3, t-2, t-1
            "firm_act_8": math.log1p(4),        # t-6, t-3, t-2, t-1
            "firm_growth": 3 / (4 - 3 + 0.5),
            "firm_tracks": 2.0,
            "firm_tenure": (t - (t - 20)) / 4.0,
            "firm_entry_rate": 2 / 8.0,         # two track entries, both in the last 8 years
            "adj_act_8": math.log1p(3),         # cardiovascular tracks other than the pair's
            "adj_share": 3 / 4.0,
            "track_act_8": math.log1p(0),
            "track_growth": 0 / (0 - 0 + 0.5),
            "track_entrants": 0.0,
            "track_recent_entries": math.log1p(0),
            "track_age": None,                  # no industry event in this track by t
            "cat_share": 4 / 5.0,
            "firm_size": math.log1p(5),
        }
        for name, value in expected.items():
            if value is None:
                self.assertIsNone(features[name], name)
            else:
                self.assertAlmostEqual(features[name], value, places=12, msg=name)
        # independent replay must match exactly
        replay = panel.features_bruteforce("alpha", "t_cardio_b", t)
        for name in H.FEATURE_NAMES_C:
            self.assertEqual(features[name], replay[name], name)

        # a track with industry activity: entrant / growth / age features (gamma has one
        # imaging event, so it is a company with no cardiovascular history)
        features = panel.features("gamma", "t_cardio_a", t)
        self.assertAlmostEqual(features["track_act_8"], math.log1p(4))      # beta t-4, alpha x3
        self.assertAlmostEqual(features["track_growth"], 2 / (4 - 2 + 0.5))
        self.assertAlmostEqual(features["track_entrants"], 2.0)
        self.assertAlmostEqual(features["track_recent_entries"], math.log1p(1))
        self.assertAlmostEqual(features["track_age"], (t - (t - 20)) / 4.0)
        self.assertAlmostEqual(features["adj_act_8"], 0.0)
        self.assertIsNone(features["adj_share"])   # no events in the last 8 quarters
        self.assertAlmostEqual(features["cat_share"], 0.0)
        self.assertAlmostEqual(features["firm_act_4"], 0.0)
        self.assertAlmostEqual(features["firm_act_8"], 0.0)

    def test_features_use_per_quarter_event_counts(self):
        t = quarter(2000, 1)
        events = {("solo", "t_cardio_a"): [t - 1]}
        counts = {("solo", "t_cardio_a"): [3]}   # three events in that single quarter
        panel = H.Panel(make_panel(events, event_counts=counts))
        features = panel.features("solo", "t_cardio_b", t)
        self.assertAlmostEqual(features["firm_act_4"], math.log1p(3))
        self.assertAlmostEqual(features["firm_act_8"], math.log1p(3))
        self.assertAlmostEqual(features["firm_size"], math.log1p(3))
        self.assertAlmostEqual(features["adj_act_8"], math.log1p(3))
        self.assertAlmostEqual(features["adj_share"], 1.0)
        self.assertEqual(panel.feature_source, "event_counts")
        self.assertEqual(panel.event_count_audit["sum_pair_event_counts"], 3)
        # without event_counts the fallback is presence-only and is flagged
        fallback = H.Panel(make_panel(events, with_counts=False))
        self.assertEqual(fallback.feature_source, "presence_only_underestimate")
        self.assertAlmostEqual(fallback.features("solo", "t_cardio_b", t)["firm_act_4"],
                               math.log1p(1))

    def test_features_ignore_events_after_t(self):
        t = quarter(2000, 1)
        events = {
            ("alpha", "t_cardio_a"): [t - 20, t - 6, t - 2, t - 1],
            ("alpha", "t_img_a"): [t - 3, t + 5, t + 9],
            ("beta", "t_cardio_a"): [t - 4, t + 2],
            ("delta", "t_cardio_a"): [t - 15],
        }
        full = H.Panel(make_panel(events))
        truncated = H.Panel(make_panel({
            (company, track): [value for value in values if value <= t]
            for (company, track), values in events.items()}))
        for company, track in (("alpha", "t_cardio_b"), ("alpha", "t_img_b"),
                               ("beta", "t_cardio_b"), ("delta", "t_cardio_b")):
            first = full.features(company, track, t)
            second = truncated.features(company, track, t)
            for name in H.FEATURE_NAMES_C:
                self.assertEqual(first[name], second[name], f"{company}/{track}/{name}")

    def test_feature_groups_match_protocol(self):
        self.assertEqual(len(H.FEATURE_NAMES_C), 15)
        self.assertEqual(len(H.GROUP_A), 7)
        self.assertEqual(len(H.GROUP_B), 12)
        self.assertEqual(len(H.GROUP_C), 15)
        self.assertEqual(H.GROUP_C, H.FEATURE_NAMES_C)   # protocol table order
        self.assertEqual(set(H.GROUP_B), set(H.GROUP_A) | {
            "track_act_8", "track_growth", "track_entrants", "track_recent_entries",
            "track_age"})
        self.assertEqual(set(H.GROUP_C), set(H.GROUP_B) | {
            "adj_act_8", "adj_share", "cat_share"})
        self.assertEqual(H.GROUP_D, H.GROUP_C + H.FUSION_FEATURES)


# ------------------------------------------------------------- training / sampling
class FakeData:
    def __init__(self, pool_t, labels, positives, negatives, negative_q, positive_q,
                 horizon=8, adjacency=True):
        self.pool_t = pool_t
        self.pool_label = labels
        self.positive_indices = positives
        self.negative_indices = negatives
        self.pool_positive_q = positive_q
        self.pool_negative_q = negative_q
        self.horizon = horizon
        self.adjacency = adjacency


class TrainingSampleTests(unittest.TestCase):
    def test_training_sample_cap_and_weights(self):
        row_count = 20000
        data = H.RiskHorizonData.__new__(H.RiskHorizonData)
        data.pool_t = list(range(row_count))
        data.pool_label = [1] + [0] * (row_count - 1)
        data.positive_indices = [0]
        data.negative_indices = list(range(1, row_count))
        data.pool_positive_q = [0]
        data.pool_negative_q = list(range(1, row_count))
        data.horizon = 8
        data.adjacency = True
        sample = data.training_sample(row_count + 8)   # cutoff = row_count
        self.assertEqual(sample["rows_before_sampling"], row_count)
        self.assertEqual(sample["rows_before_sampling"], row_count)
        self.assertEqual(sample["rows_after_sampling"], H.TRAIN_ROW_CAP)
        self.assertEqual(sample["positives"], 1)
        self.assertEqual(sample["negatives_sampled"], H.TRAIN_ROW_CAP - 1)
        self.assertTrue(sample["subsampled"])
        self.assertAlmostEqual(sample["negative_sampling_fraction"],
                               (H.TRAIN_ROW_CAP - 1) / (row_count - 1))
        self.assertAlmostEqual(sample["negative_weight"],
                               1.0 / sample["negative_sampling_fraction"])
        self.assertEqual(sample["weights"][0], 1.0)
        self.assertTrue(all(weight == sample["negative_weight"]
                            for weight in sample["weights"][1:]))
        self.assertTrue(sample["purge_ok"])
        self.assertLessEqual(sample["max_training_origin_qidx"],
                             sample["max_allowed_training_qidx"])

    def test_purge_assertion_catches_leaky_cell(self):
        # the index lists are deliberately inconsistent: a "positive" cell is claimed to
        # lie at q95 (<= cutoff) by pool_positive_q but the pool row is really at q95
        # beyond the cutoff, which is exactly the leak the assertion must catch
        data = H.RiskHorizonData.__new__(H.RiskHorizonData)
        data.pool_t = [0, 95, 120]
        data.pool_label = [0, 1, 1]
        data.positive_indices = [1, 2]
        data.negative_indices = [0]
        data.pool_positive_q = [80, 100]        # inconsistent with pool_t on purpose
        data.pool_negative_q = [0]
        data.horizon = 8
        data.adjacency = True
        with self.assertRaises(ValueError) as context:
            data.training_sample(96)
        self.assertIn("purge violated", str(context.exception))

    def test_purge_holds_for_every_origin(self):
        panel = H.Panel(golden_panel())
        data = H.RiskHorizonData(panel, True, 8, max_origins=4)
        for origin in data.test_origins:
            sample = data.training_sample(origin)
            self.assertTrue(sample["purge_ok"])
            self.assertEqual(sample["max_allowed_training_qidx"], origin - 8)
            self.assertLessEqual(sample["max_training_origin_qidx"],
                                 sample["max_allowed_training_qidx"])

    def test_training_grid_is_quarterly(self):
        panel = H.Panel(golden_panel())
        data = H.RiskHorizonData(panel, True, 8, max_origins=2)
        first_origin = data.test_origins[0]
        sample = data.training_sample(first_origin)
        trained_quarters = {data.pool_t[index] for index in sample["indices"]}
        eval_origins = set(data.test_origins)
        self.assertTrue(trained_quarters - eval_origins)      # many non-annual quarters
        self.assertLessEqual(max(trained_quarters), first_origin - 8)


# ------------------------------------------------------------------- models / loss
class ModelTests(unittest.TestCase):
    def test_weighted_logistic_is_deterministic_and_directional(self):
        rows = [[0.0, 0.0], [0.1, 0.2], [0.9, 0.8], [1.0, 1.0]]
        labels = [0, 0, 1, 1]
        weights = [1.0, 1.0, 1.0, 1.0]
        first = H.fit_logistic_regression(rows, labels, weights)
        second = H.fit_logistic_regression(rows, labels, weights)
        self.assertEqual(first["coefficients"], second["coefficients"])
        predictions = H.predict_logistic(first, rows)
        self.assertLess(predictions[0], predictions[3])
        self.assertTrue(0.0 < predictions[0] < 1.0)

    def test_logistic_handles_missing_feature_with_training_median(self):
        rows = [[1.0, float("nan")], [2.0, float("nan")], [3.0, 5.0]]
        labels = [0, 0, 1]
        weights = [1.0, 1.0, 1.0]
        model = H.fit_logistic_regression(rows, labels, weights)
        self.assertIsNotNone(model["medians"][1])
        self.assertAlmostEqual(model["medians"][1], 5.0)   # only observed value
        self.assertTrue(model["loss_end"] <= model["loss_start"])

    def test_baselines_rank_companies_and_tracks(self):
        panel = H.Panel(golden_panel())
        data = H.RiskHorizonData(panel, True, 8)
        origin = data.test_origins[10]      # late enough that matured positives exist
        sample = data.training_sample(origin)
        fit = H.fit_baselines(data, sample)
        self.assertGreater(fit["prevalence"], 0.0)
        predictions = H.predict_baselines(fit, ["alpha", "delta"], ["t_cardio_b", "t_cardio_b"])
        for model in ("B0", "B1", "B2", "B3"):
            self.assertEqual(len(predictions[model]), 2)
            self.assertTrue(all(0.0 <= value <= 1.0 for value in predictions[model]))


# --------------------------------------------------------------- bootstrap / lead
class BootstrapTests(unittest.TestCase):
    def _records(self, seed=11, identical=False):
        rng = random.Random(seed)
        records = []
        for origin in range(8):
            companies = [f"c{rng.randrange(10)}" for _ in range(60)]
            labels = [1 if rng.random() < 0.15 else 0 for _ in range(60)]
            tracks = [f"t{rng.randrange(5)}" for _ in range(60)]
            scores = {"B1": [rng.random() for _ in range(60)]}
            scores["M1C"] = list(scores["B1"]) if identical else [rng.random() for _ in range(60)]
            records.append({"origin": origin, "companies": companies, "tracks": tracks,
                            "labels": labels, "scores": scores,
                            "thresholds": {model: {budget: 0.5 for budget in H.ALERT_BUDGETS}
                                           for model in scores}})
        return records

    def test_bootstrap_determinism_and_pairing(self):
        index = {f"c{i}": i for i in range(10)}
        models = ("B1", "M1C")
        prepared = H.prepare_bootstrap_origins(self._records(), models, index)
        first = H.clustered_bootstrap_mean_ap(prepared, models, 10, 50, 7,
                                              comparisons=(("M1C", "B1"),))
        second = H.clustered_bootstrap_mean_ap(prepared, models, 10, 50, 7,
                                               comparisons=(("M1C", "B1"),))
        self.assertEqual(json.dumps(first, sort_keys=True), json.dumps(second, sort_keys=True))
        prepared_identical = H.prepare_bootstrap_origins(self._records(identical=True),
                                                         models, index)
        paired = H.clustered_bootstrap_mean_ap(prepared_identical, models, 10, 50, 7,
                                               comparisons=(("M1C", "B1"),))
        delta = paired["comparisons"]["M1C-B1"]
        self.assertEqual(delta["mean"], 0.0)
        self.assertEqual(delta["ci_low"], 0.0)
        self.assertEqual(delta["ci_high"], 0.0)
        self.assertEqual(delta["mde_80pct_power_alpha_0.05"], 0.0)

    def test_bootstrap_reports_degenerate_origins(self):
        # every origin has one positive cell only, so company resampling frequently
        # drops it; the status must flag an unreliable interval rather than hide it
        prepared = [{"B1": H.prepare_ap([1, 0], [0.9, 0.1], [0, 1]),
                     "M1C": H.prepare_ap([1, 0], [0.8, 0.2], [0, 1]), "n_rows": 2}
                    for _ in range(30)]
        result = H.clustered_bootstrap_mean_ap(prepared, ("B1", "M1C"), 2, 40, 3)
        self.assertIn(result["status"], ("OK", "UNRELIABLE"))
        self.assertGreaterEqual(result["contributing_origins_min"], 0)
        self.assertIn("min_contributing_origins_required", result)

    def test_bootstrap_reliability_gate_flags_unreliable(self):
        # 30 origins whose only positive row belongs to company 0; a resample that drops
        # company 0 loses every origin, so the pre-declared gate must fire
        prepared = [{"B1": H.prepare_ap([1, 0, 0], [0.9, 0.5, 0.1], [0, 1, 1]),
                     "M1C": H.prepare_ap([1, 0, 0], [0.8, 0.4, 0.2], [0, 1, 1]),
                     "n_rows": 3} for _ in range(30)]
        result = H.clustered_bootstrap_mean_ap(prepared, ("B1", "M1C"), 2, 60, 5,
                                               comparisons=(("M1C", "B1"),))
        self.assertEqual(result["status"], "UNRELIABLE")
        self.assertGreater(result["share_resamples_below_min_contributing_origins"], 0.05)
        self.assertIsNone(result["comparisons"]["M1C-B1"]["ci_low"])
        self.assertIsNotNone(result["comparisons"]["M1C-B1"]["mde_80pct_power_alpha_0.05"])
        self.assertIn("descriptive_interval_not_a_ci", result["comparisons"]["M1C-B1"])

    def test_alert_analysis_lead_time_and_missed_entries(self):
        records = [{
            "origin": 0,
            "companies": ["a", "b", "c", "d"],
            "tracks": ["t1", "t2", "t3", "t4"],
            "labels": [0, 0, 0, 0],
            "scores": {"M1C": [0.1, 0.1, 0.9, 0.3]},
            "thresholds": {"M1C": {budget: 0.5 for budget in H.ALERT_BUDGETS}},
        }, {
            "origin": 4,
            "companies": ["a", "b", "c", "d"],
            "tracks": ["t1", "t2", "t3", "t4"],
            "labels": [1, 0, 1, 0],
            "scores": {"M1C": [0.9, 0.1, 0.2, 0.3]},
            "thresholds": {"M1C": {budget: 0.5 for budget in H.ALERT_BUDGETS}},
        }]
        entries = {"entries": [
            {"company_key": "a", "track_id": "t1", "entry_qidx": 8,
             "candidate_origins": [0, 4]},          # first alert at origin 4 -> lead 4
            {"company_key": "b", "track_id": "t2", "entry_qidx": 8,
             "candidate_origins": [0, 4]},          # never alerted -> missed
        ], "n_entries": 2, "excluded_never_in_risk_set": 0, "evaluation_window": [1, 12]}
        result = H.alert_analysis(records, entries, "M1C", 0.10)
        self.assertEqual(result["entries_in_scope"], 2)
        self.assertEqual(result["entries_alerted"], 1)
        self.assertEqual(result["entries_missed"], 1)
        self.assertEqual(result["lead_quarters"]["median"], 4)
        # pooled alerts: origin 0 cell c (label 0, FP) and origin 4 cell a (label 1, TP)
        self.assertEqual(result["alerts"], 2)
        self.assertAlmostEqual(result["precision"], 0.5)
        self.assertAlmostEqual(result["recall"], 0.5)   # 2 positive cells in total
        self.assertAlmostEqual(result["false_alarms_per_1000_candidate_quarters"],
                               1000.0 * 1 / 8)


# ---------------------------------------------------------------- end-to-end golden
class GoldenEndToEndTests(unittest.TestCase):
    EXPECTED_MEAN_AP = {}   # filled by the first observed run; see test below

    @classmethod
    def setUpClass(cls):
        cls._directory = tempfile.TemporaryDirectory()
        root = Path(cls._directory.name)
        cls.panel_path = root / "panel.json"
        cls.results_path = root / "results.json"
        cls.panel_path.write_text(json.dumps(golden_panel()), encoding="utf-8")
        exit_code = H.main([
            "--panel", str(cls.panel_path),
            "--out", str(cls.results_path),
            "--quick",
            "--skip-fusion",
            "--max-origins", "2",
        ])
        assert exit_code == 0
        cls.results = json.loads(cls.results_path.read_text(encoding="utf-8"))

    @classmethod
    def tearDownClass(cls):
        cls._directory.cleanup()

    def test_results_top_level_contract(self):
        for key in ("schema", "generated_at", "panel_sha256", "git_commit", "seed",
                    "config", "dataset", "primary", "secondary", "robustness",
                    "lead_time", "heterogeneity", "fusion_h2", "leakage_controls",
                    "decision"):
            self.assertIn(key, self.results)
        self.assertEqual(self.results["schema"], "hist_v1.results.v1")
        self.assertEqual(len(self.results["panel_sha256"]), 64)
        self.assertEqual(self.results["config"]["amendments_applied"],
                         ["A1", "A2", "A3", "A4"])
        self.assertEqual(self.results["config"]["feature_source"], "event_counts")
        self.assertEqual(self.results["dataset"]["panel"]["feature_source"], "event_counts")

    def test_golden_origin_counts_and_ap(self):
        primary = self.results["primary"]
        self.assertEqual(primary["n_origins"], 2)
        self.assertEqual(primary["origin_labels"], ["1995-Q1", "1996-Q1"])
        candidates = [row["n_candidates"] for row in primary["per_origin"]]
        positives = [row["n_positives"] for row in primary["per_origin"]]
        self.assertEqual(candidates, [4, 3])
        self.assertEqual(positives, [2, 2])
        mean_ap = primary["mean_per_origin_ap"]
        self.assertEqual(mean_ap["M1C"]["n"], 2)
        self.assertEqual(set(primary["models"]), {"B0", "B1", "B2", "B3", "M1A", "M1B", "M1C"})
        for model in ("B0", "B1", "B2", "B3", "M1A", "M1B", "M1C"):
            self.assertIn(model, mean_ap)
            self.assertIsNotNone(mean_ap[model]["mean"])
        self.assertEqual(primary["bootstrap"]["reps_requested"], 200)
        self.assertEqual(primary["bootstrap"]["seed"], H.SEED)
        self.assertEqual(set(primary["deltas_vs_baselines"]), {"M1C-B1", "M1C-B2", "M1C-B3"})

    def test_golden_dataset_purge_and_sampling(self):
        totals = self.results["dataset"]["totals"]["R_adj|h8"]
        self.assertEqual(totals["candidate_cells"], 7)
        self.assertEqual(totals["positive_cells"], 4)
        self.assertEqual(totals["immature_excluded"], 0)
        self.assertEqual(totals["negative_sampling_fractions"], [1.0])
        for row in self.results["dataset"]["configs"]["R_adj|h8"]:
            training = row["training"]
            self.assertTrue(training["purge_ok"])
            self.assertLessEqual(training["max_training_origin_qidx"],
                                 training["max_allowed_training_qidx"])
            self.assertLessEqual(training["rows_after_sampling"], H.TRAIN_ROW_CAP)
        self.assertEqual(self.results["leakage_controls"]["label_purge"]["violations"], 0)

    def test_golden_robustness_and_secondary_blocks(self):
        robustness = self.results["robustness"]
        self.assertEqual(set(robustness["eras"]), {"1995-2004", "2005-2014", "2015-2024"})
        self.assertEqual(set(robustness["feature_groups"]), {"A", "B", "C"})
        permutation = robustness["permutation_null"]
        self.assertEqual(permutation["n_permutations_achieved"], 5)
        self.assertIsNotNone(permutation["empirical_p_value_one_sided"])
        self.assertAlmostEqual(permutation["resolution_floor"], 1.0 / 6.0)
        secondary = self.results["secondary"]
        for name in ("R_full|h8", "R_adj|h4", "R_full|h4"):
            self.assertIn(name, secondary)
            self.assertIn("bootstrap", secondary[name])
            self.assertIn("pooled_ap", secondary[name])
        lead = self.results["lead_time"]
        self.assertEqual(len(lead["h5_frontier"]), 4)
        self.assertEqual([row["budget"] for row in lead["h5_frontier"]],
                         list(H.ALERT_BUDGETS))
        self.assertEqual(self.results["fusion_h2"]["status"], "NOT_EVALUABLE")
        self.assertIn("reasons", self.results["fusion_h2"])
        self.assertEqual(self.results["heterogeneity"]["h3_companies"]["minimum_positives"], 10)
        self.assertIn("per_category", self.results["heterogeneity"]["h4_categories"])
        self.assertEqual(self.results["leakage_controls"]["independent_replay"]["mismatches"], 0)
        self.assertIn(self.results["decision"]["H1"]["h8_primary"]["status"],
                      ("SUPPORTED", "NOT_SUPPORTED", "UNRELIABLE",
                       "UNRELIABLE (no pre-registered CI quotable)"))
        self.assertFalse(self.results["decision"]["H1"]["supported"])
        self.assertEqual(
            self.results["decision"]["H1"]["multiple_testing"]["status"],
            "NOT_APPLICABLE_TO_H1")
        self.assertEqual(
            self.results["decision"]["H1"]["robustness_estimand_R_full_h8"]["risk_set"],
            "R_full")
        self.assertIn("overall_verdict", self.results["decision"]["H1"])

    def test_golden_fixed_numbers(self):
        """Fixed regression numbers for the tiny golden run (2 origins, --quick)."""
        primary = self.results["primary"]
        self.assertAlmostEqual(primary["mean_per_origin_ap"]["M1C"]["mean"],
                               0.5416666666666666, places=9)
        self.assertAlmostEqual(primary["mean_per_origin_ap"]["B1"]["mean"], 0.75, places=9)
        self.assertAlmostEqual(primary["mean_per_origin_ap"]["B2"]["mean"],
                               0.6666666666666666, places=9)
        self.assertAlmostEqual(primary["pooled_ap"]["M1C"], 0.5773809523809523, places=9)
        self.assertAlmostEqual(primary["deltas_vs_baselines"]["M1C-B1"]["point_delta"],
                               -0.20833333333333337, places=9)
        self.assertAlmostEqual(primary["deltas_vs_baselines"]["M1C-B2"]["point_delta"],
                               -0.125, places=9)
        per_origin_ap = [row["models"]["M1C"]["average_precision"]
                         for row in primary["per_origin"]]
        self.assertEqual(len(per_origin_ap), 2)
        self.assertAlmostEqual(per_origin_ap[0], 0.5, places=9)
        self.assertAlmostEqual(per_origin_ap[1], 0.5833333333333333, places=9)
        bootstrap = primary["deltas_vs_baselines"]["M1C-B1"]["bootstrap"]
        self.assertAlmostEqual(bootstrap["mean"], -0.15972222222222224, places=9)
        self.assertAlmostEqual(bootstrap["sd"], 0.13825579705374044, places=9)
        self.assertEqual(primary["bootstrap"]["status"], "UNRELIABLE")
        self.assertIsNone(bootstrap["ci_low"])
        lead = self.results["lead_time"]["primary_budget"]
        self.assertEqual(lead["entries_in_scope"], 3)
        self.assertEqual(lead["entries_alerted"], 2)
        self.assertEqual(lead["entries_missed"], 1)
        self.assertAlmostEqual(lead["lead_quarters"]["median"], 6.0)
        self.assertAlmostEqual(lead["false_alarms_per_1000_candidate_quarters"],
                               1000.0 * 3 / 7.0, places=9)
        self.assertAlmostEqual(lead["recall"], 0.75)
        self.assertAlmostEqual(lead["precision"], 0.5)
        secondary = self.results["secondary"]
        self.assertAlmostEqual(secondary["R_full|h8"]["delta_ap_M1C_minus_B1"],
                               0.0625, places=9)
        self.assertAlmostEqual(secondary["R_adj|h4"]["delta_ap_M1C_minus_B1"], 0.0, places=9)
        self.assertAlmostEqual(secondary["R_full|h4"]["delta_ap_M1C_minus_B1"],
                               0.1875, places=9)
        permutation = self.results["robustness"]["permutation_null"]
        self.assertAlmostEqual(permutation["observed_delta_ap"], -0.20833333333333337,
                               places=9)
        self.assertEqual(permutation["empirical_p_value_one_sided"], 1.0)
        self.assertAlmostEqual(permutation["resolution_floor"], 1.0 / 6.0, places=9)
        era = self.results["robustness"]["eras"]["1995-2004"]
        self.assertAlmostEqual(era["models"]["B1"]["mean"], 0.75, places=9)
        self.assertAlmostEqual(era["delta_ap_M1C_minus_B1"], -0.20833333333333337,
                               places=9)

    def test_results_json_is_nan_free(self):
        text = self.results_path.read_text(encoding="utf-8")
        self.assertNotIn("NaN", text)
        json.loads(text, parse_constant=lambda value: (_ for _ in ()).throw(
            AssertionError(f"non-finite JSON constant {value}")))

    def test_h1_multiple_testing_states(self):
        permutation_block = {"empirical_p_value_one_sided": 0.03,
                             "n_permutations_achieved": 200,
                             "resolution_floor": 1.0 / 201.0}
        both = {"ci_low": 0.01, "ci_high": 0.1, "p_two_sided": 0.01,
                "supported": True, "delta_ap": 0.05}
        none = {"ci_low": None, "ci_high": None, "p_two_sided": 0.06,
                "supported": False, "delta_ap": 0.05}
        applied = H.build_h1_multiple_testing(both, both, permutation_block)
        self.assertEqual(applied["status"], "APPLIED")
        self.assertTrue(applied["reject"]["h8_primary_M1C_minus_B1"])
        partial = H.build_h1_multiple_testing(both, none, permutation_block)
        self.assertEqual(partial["status"], "INCOMPLETE")
        self.assertTrue(partial["h1_supported"])
        self.assertIn("uncorrected_p_values", partial)
        self.assertNotIn("reject", partial)
        not_applicable = H.build_h1_multiple_testing(none, none, permutation_block)
        self.assertEqual(not_applicable["status"], "NOT_APPLICABLE_TO_H1")
        self.assertFalse(not_applicable["h1_supported"])

    def test_overall_verdict_matches_supported_flag(self):
        supported = {"ci_low": 0.01, "ci_high": 0.1, "p_two_sided": 0.04,
                     "supported": True, "delta_ap": 0.05}
        unreliable = {"ci_low": None, "ci_high": None, "p_two_sided": 0.06,
                      "supported": False, "delta_ap": 0.05}
        r_full = {"supported": True, "delta_ap": 0.03, "ci_low": 0.01, "ci_high": 0.06}
        text = H.build_overall_verdict(supported, r_full, unreliable)
        self.assertIn("SUPPORTED on the primary estimand", text)
        self.assertIn("confirmed on the primary estimand", text)
        self.assertIn("UNRELIABLE", text)          # h4 caveat present
        text = H.build_overall_verdict(unreliable, r_full, unreliable)
        self.assertIn("NOT CONFIRMED", text)
        self.assertNotIn("SUPPORTED on the primary estimand", text)

    def test_atomic_json_write_leaves_no_tmp(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "nested" / "results.json"
            H.write_json_atomic(path, {"schema": "x", "value": 1})
            self.assertTrue(path.is_file())
            self.assertFalse(path.with_name(path.name + ".tmp").exists())
            self.assertEqual(json.loads(path.read_text(encoding="utf-8"))["value"], 1)

    def test_eval_module_has_no_forbidden_imports(self):
        source = EVAL_PATH.read_text(encoding="utf-8")
        for package in ("numpy", "pandas", "scipy", "sklearn", "torch"):
            self.assertNotRegex(source, rf"(?m)^\s*(?:import|from)\s+{package}\b")


# ------------------------------------------------------- index integrity / lead scope
class IndexAndLeadTests(unittest.TestCase):
    def test_all_bisect_indexes_are_sorted(self):
        # bisect is only correct on sorted lists; company_cat_q used to be built in pair
        # order and silently corrupted adj_act_8 / adj_share / cat_share
        t = quarter(2000, 1)
        tracks = TRACKS + [{"id": "t_cardio_c", "name_en": "Cardio C",
                            "category": "cardiovascular", "domain": "cardiovascular"}]
        panel = H.Panel(make_panel({
            ("alpha", "t_cardio_a"): [t - 20, t - 2],
            ("alpha", "t_cardio_b"): [t - 30, t - 6],
            ("beta", "t_img_a"): [t - 25, t - 4],
            ("gamma", "t_img_b"): [t - 10],
        }, tracks=tracks))
        for values in panel.company_cat_q.values():
            self.assertEqual(values, sorted(values))
        for company in panel.company_keys:
            self.assertEqual(panel.company_q[company], sorted(panel.company_q[company]))
            self.assertEqual(panel.company_events[company],
                             sorted(panel.company_events[company]))
            self.assertEqual(panel.company_track_first_q[company],
                             sorted(panel.company_track_first_q[company]))
            self.assertEqual(panel.company_entries[company],
                             sorted(panel.company_entries[company]))
        for track in panel.track_keys:
            self.assertEqual(panel.industry_events[track],
                             sorted(panel.industry_events[track]))
            self.assertEqual(panel.track_q[track], sorted(panel.track_q[track]))
            self.assertEqual(panel.track_entry_q[track], sorted(panel.track_entry_q[track]))
        # interleaved same-category pairs must give the same answer in both code paths;
        # the pair under test is unentered, so adjacency counts the two cardiovascular
        # events in (t-8, t] that lie in the *other* tracks
        self.assertIsNone(panel.pair_events.get(("alpha", "t_cardio_c")))
        features = panel.features("alpha", "t_cardio_c", t)
        replay = panel.features_bruteforce("alpha", "t_cardio_c", t)
        for name in H.FEATURE_NAMES_C:
            self.assertEqual(features[name], replay[name], name)
        self.assertAlmostEqual(features["adj_act_8"], math.log1p(2))
        # the replay must also match for an *entered* pair, where adjacency must subtract
        # the pair's own-track events in the window (t-6 is in (t-8, t])
        entered = panel.features("alpha", "t_cardio_b", t)
        replay_entered = panel.features_bruteforce("alpha", "t_cardio_b", t)
        for name in H.FEATURE_NAMES_C:
            self.assertEqual(entered[name], replay_entered[name], name)
        self.assertAlmostEqual(entered["adj_act_8"], math.log1p(1))

    def test_event_count_audit_matches_panel_summary(self):
        t = quarter(2000, 1)
        panel = H.Panel(make_panel({("solo", "t_cardio_a"): [t - 1]},
                                   event_counts={("solo", "t_cardio_a"): [3]}))
        self.assertEqual(panel.total_events, 3)
        self.assertTrue(panel.event_count_audit["matches"])
        panel_plain = H.Panel(make_panel({("solo", "t_cardio_a"): [t - 1]}))
        self.assertTrue(panel_plain.event_count_audit["matches"])
        self.assertEqual(panel_plain.event_count_audit["pairs_missing_event_counts"], 0)

    def test_era_strata_tolerates_partially_fitted_models(self):
        # the fusion D model is fitted only on 2016+ origins; an era block without it
        # must not raise (and must simply report n = 0 for that model)
        panel = H.Panel(golden_panel())
        data = H.RiskHorizonData(panel, True, 8, max_origins=3)
        records = []
        for origin in data.test_origins:
            cells = data.test_cells[origin]
            scores = {model: [0.5] * len(cells["label"]) for model in ("B1", "M1C")}
            if origin >= quarter(2016, 1):
                scores["M1D"] = [0.5] * len(cells["label"])
            records.append({"origin": origin, "companies": cells["company"],
                            "tracks": cells["track"], "labels": cells["label"],
                            "scores": scores, "thresholds": {}})
        per_origin = [{"origin": record["origin"], "models": {
            model: {"average_precision": 0.5} for model in record["scores"]}}
            for record in records]
        config = {"origins": data.test_origins, "models": ["B1", "M1C", "M1D"],
                  "per_origin": per_origin}
        eras = H.era_strata(config, panel)
        self.assertIn("1995-2004", eras)
        self.assertEqual(eras["1995-2004"]["models"]["M1D"]["n"], 0)

    def test_incident_entries_scope_and_missing_window(self):
        panel = H.Panel(make_panel({
            ("alpha", "t_cardio_a"): [quarter(1976, 1)],
            ("alpha", "t_cardio_b"): [quarter(1997, 1)],
            ("beta", "t_cardio_a"): [quarter(1978, 1)],
            ("beta", "t_cardio_b"): [quarter(1997, 1)],
            ("gamma", "t_cardio_a"): [quarter(1979, 1)],
            ("gamma", "t_cardio_b"): [quarter(1995, 2)],
            ("delta", "t_cardio_a"): [quarter(1979, 1)],
            ("delta", "t_cardio_b"): [quarter(1997, 1)],
        }))
        records = [
            {"origin": quarter(1995, 1), "companies": ["alpha"],
             "tracks": ["t_cardio_b"], "labels": [0], "scores": {}},
            {"origin": quarter(1996, 1), "companies": ["alpha", "beta", "gamma"],
             "tracks": ["t_cardio_b", "t_cardio_b", "t_cardio_b"],
             "labels": [0, 0, 0], "scores": {}},
        ]
        entries = H.incident_entries(panel, records, horizon=8)
        # alpha enters at 1997-Q1: both annual origins (1995-Q1, 1996-Q1) fall in its
        # [tau-8, tau-1] alert window.  beta enters at 1997-Q1 and is a candidate at
        # 1996-Q1.  gamma enters at 1995-Q2: only 1995-Q1 is in its window, where it is not
        # a candidate -> recorded as a missed entry (it is on the risk set elsewhere).
        # delta never appears on the risk set -> excluded from the R_adj lead analysis.
        by_pair = {(entry["company_key"], entry["track_id"]): entry
                   for entry in entries["entries"]}
        self.assertIn(("alpha", "t_cardio_b"), by_pair)
        self.assertEqual(by_pair[("alpha", "t_cardio_b")]["candidate_origins"],
                         [quarter(1995, 1), quarter(1996, 1)])
        self.assertEqual(by_pair[("beta", "t_cardio_b")]["candidate_origins"],
                         [quarter(1996, 1)])
        self.assertIn(("gamma", "t_cardio_b"), by_pair)
        self.assertEqual(by_pair[("gamma", "t_cardio_b")]["candidate_origins"], [])
        self.assertNotIn(("delta", "t_cardio_b"), by_pair)
        self.assertEqual(entries["n_entries_without_candidate_origin_in_alert_window"], 1)
        self.assertEqual(entries["excluded_never_in_risk_set"], 1)
        # an entry with no candidate origin can never be alerted, so it is a MISS
        records_with_scores = [dict(record, scores={"M1C": [0.9] * len(record["labels"])},
                                    thresholds={"M1C": {budget: 0.5
                                                        for budget in H.ALERT_BUDGETS}})
                               for record in records]
        result = H.alert_analysis(records_with_scores, entries, "M1C", 0.10)
        self.assertEqual(result["entries_in_scope"], 3)
        self.assertEqual(result["entries_alerted"], 2)
        self.assertEqual(result["entries_missed"], 1)


# --------------------------------------------------------------------- fusion lanes
class FusionLaneTests(unittest.TestCase):
    def test_missing_lanes_are_not_evaluable(self):
        panel = H.Panel(make_panel({("alpha", "t_cardio_a"): [76]}))
        lanes = H.FusionLanes(Path(tempfile.gettempdir()) / "hist_v1_absent_data_dir", panel)
        self.assertFalse(lanes.available)
        self.assertTrue(lanes.reason)

    def test_fusion_values_and_undefined_publication_years(self):
        panel = H.Panel(make_panel({("alpha", "t_cardio_a"): [76]}))
        lanes = H.FusionLanes.__new__(H.FusionLanes)
        lanes.panel = panel
        lanes.available = True
        lanes.trial_track_q = {"t_cardio_a": [quarter(1999, 4)]}
        lanes.trial_category_q = {"cardiovascular": [quarter(1999, 4), quarter(2000, 1)]}
        lanes.publications = {"alpha": {1998: 4, 1999: 6}}
        t = quarter(2000, 1)
        values = lanes.values("alpha", "t_cardio_a", t)
        self.assertAlmostEqual(values[0], math.log1p(1))   # track trial within 8 quarters
        self.assertAlmostEqual(values[1], math.log1p(1))   # adjacent trial event
        self.assertAlmostEqual(values[2], math.log1p(6))   # works in year-1
        self.assertIsNone(values[3])                       # 3 complete years unavailable
        self.assertAlmostEqual(values[4], 6 / (4 + 0.5))


if __name__ == "__main__":
    unittest.main()
