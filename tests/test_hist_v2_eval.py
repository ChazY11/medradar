"""Unit tests for the hist_v2 domain panel builder and walk-forward evaluation harness.

Standard library only; no network, no repository data files, no models fitted outside the
tiny synthetic fixtures.  Run with::

    python -m unittest tests.test_hist_v2_eval -v
"""
from __future__ import annotations

import copy
import importlib.util
import json
import random
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
EVAL_PATH = REPO_ROOT / "experiments" / "hist_v2" / "eval.py"
BUILDER_PATH = REPO_ROOT / "experiments" / "hist_v2" / "build_domain_panel.py"


def _load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


H = _load_module(EVAL_PATH, "hist_v2_eval")
B = _load_module(BUILDER_PATH, "hist_v2_build_domain_panel")

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


def iso_date(qidx: int) -> str:
    label = QUARTERS[qidx]
    year_text, part_text = label.split("-Q", 1)
    month = (int(part_text) - 1) * 3 + 1
    return f"{year_text}-{month:02d}-15"


# four domains; dom_surg and dom_robot share the `surgery` category band
DOMAINS = [
    {"id": "dom_cardio", "name_en": "Cardio", "categories": ["cardiovascular"],
     "n_tracks": 2, "track_ids": ["t_cardio_a", "t_cardio_b"],
     "first_industry_qidx": 0, "n_firms_ever": 1, "total_material_events": 1},
    {"id": "dom_img", "name_en": "Imaging", "categories": ["imaging"],
     "n_tracks": 1, "track_ids": ["t_img"], "first_industry_qidx": 0,
     "n_firms_ever": 1, "total_material_events": 1},
    {"id": "dom_robot", "name_en": "Robotics", "categories": ["surgery"],
     "n_tracks": 1, "track_ids": ["t_robot"], "first_industry_qidx": 0,
     "n_firms_ever": 1, "total_material_events": 1},
    {"id": "dom_surg", "name_en": "Surgery", "categories": ["surgery"],
     "n_tracks": 1, "track_ids": ["t_surg"], "first_industry_qidx": 0,
     "n_firms_ever": 1, "total_material_events": 1},
]


def make_panel(events: dict[tuple[str, str], list[int]], *, domains=None,
               event_counts: dict[tuple[str, str], list[int]] | None = None,
               with_counts: bool = True, audits: dict | None = None) -> dict:
    """Build a minimal ``hist_v2.domain_panel.v1`` panel from ``{(company, domain): [qidx]}``."""
    domains = domains or DOMAINS
    companies = sorted({company for company, _domain in events})
    pairs = []
    for (company, domain), values in sorted(events.items()):
        values = sorted(values)
        counts = (event_counts.get((company, domain), [1] * len(values))
                  if event_counts else [1] * len(values))
        record = {
            "company_key": company,
            "domain_id": domain,
            "event_qidx": values,
            "event_iso": [iso_date(value) for value in values],
            "n_510k": sum(counts),
            "n_pma": 0,
        }
        if with_counts:
            record["event_counts"] = counts
        pairs.append(record)
    company_records = []
    for company in companies:
        own = [value for (key, _domain), values in events.items() if key == company
               for value in values]
        company_records.append({
            "key": company,
            "display_name": company.title(),
            "cohort": "fixture",
            "total_material_events": len(own),
            "first_event_qidx": min(own),
            "last_event_qidx": max(own),
        })
    domain_records = []
    for domain in domains:
        industry = [value for (company, key), values in events.items() if key == domain["id"]
                    for value in values]
        firms = {company for (company, key) in events if key == domain["id"]}
        record = dict(domain)
        record["first_industry_qidx"] = min(industry) if industry else None
        record["n_firms_ever"] = len(firms)
        record["total_material_events"] = len(industry)
        domain_records.append(record)
    panel = {
        "schema": "hist_v2.domain_panel.v1",
        "quarter_start": QUARTERS[0],
        "quarter_end": QUARTERS[-1],
        "quarters": list(QUARTERS),
        "companies": company_records,
        "domains": domain_records,
        "pairs": pairs,
        "pairs_no_acquired": copy.deepcopy(pairs),
    }
    if audits is not None:
        panel["audits"] = audits
    elif with_counts:
        panel["audits"] = {"panel_summary": {
            "n_material_events": sum(sum(pair["event_counts"]) for pair in pairs)}}
    return panel


def golden_panel() -> dict:
    """Tiny deterministic domain panel used by the golden end-to-end test.

    Entries with --max-origins 2 (origins 1995-Q1, 1996-Q1): alpha -> dom_robot at
    1995-Q1+4, beta -> dom_img at 1996-Q1+4, gamma -> dom_surg at 1996-Q1+6.
    """
    events = {
        ("alpha", "dom_cardio"): [40, 60, 100, 140],
        ("alpha", "dom_robot"): [80],
        ("beta", "dom_surg"): [30, 70, 120],
        ("beta", "dom_img"): [84],
        ("gamma", "dom_cardio"): [50, 90],
        ("gamma", "dom_surg"): [86],
        ("delta", "dom_surg"): [20, 60, 110],
    }
    return make_panel(events, with_counts=True)


def tiny_eval_panel() -> dict:
    """Company/domain layout used by the risk-set and point-in-time feature tests."""
    t = quarter(2000, 1)
    events = {
        ("alpha", "dom_cardio"): [t - 20, t - 4, t - 2],
        ("alpha", "dom_surg"): [t - 30],
        ("beta", "dom_robot"): [t - 6],
        ("gamma", "dom_img"): [t - 30],
        ("delta", "dom_cardio"): [t - 10],
        ("delta", "dom_robot"): [t - 6],
    }
    return make_panel(events, with_counts=False)


# ------------------------------------------------------------------------- metrics
class MetricTests(unittest.TestCase):
    def test_average_precision_hand_computed(self):
        # scores descending: 1, 0, 1 -> AP = 1/2 * 1 + 1/2 * 2/3 = 0.8333333
        self.assertAlmostEqual(H.average_precision([1, 0, 1], [0.9, 0.8, 0.7]),
                               0.8333333333333333, places=12)
        self.assertAlmostEqual(H.average_precision([1, 0], [0.5, 0.5]), 0.5, places=12)
        self.assertAlmostEqual(H.average_precision([1, 0, 0], [0.5, 0.5, 0.5]),
                               1.0 / 3.0, places=12)
        self.assertAlmostEqual(H.average_precision([1, 1, 0, 0], [0.9, 0.8, 0.2, 0.1]),
                               1.0, places=12)
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

    def test_rank_order_is_deterministic(self):
        labels = [1, 0, 1, 0]
        scores = [0.5, 0.5, 0.5, 0.5]
        companies = ["b", "a", "a", "b"]
        domains = ["dom_surg", "dom_surg", "dom_cardio", "dom_cardio"]
        # score desc, then company asc, then domain asc
        self.assertEqual(H.rank_order(scores, companies, domains), [2, 1, 3, 0])

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
        prepared_zero = H.prepare_ap([1, 0], [0.9, 0.1], [0, 1])
        self.assertIsNone(H.ap_weighted(prepared_zero, [1, 0]))

    def test_roc_auc_and_brier_ece(self):
        self.assertAlmostEqual(H.roc_auc([1, 0, 1, 0], [0.9, 0.3, 0.8, 0.2]), 1.0)
        self.assertAlmostEqual(H.roc_auc([1, 0], [0.5, 0.5]), 0.5)
        self.assertAlmostEqual(H.roc_auc([1, 0, 0], [0.5, 0.9, 0.3]), 0.5)
        self.assertAlmostEqual(H.roc_auc([1, 0, 0], [0.5, 0.5, 0.1]), 0.75)
        self.assertIsNone(H.roc_auc([1, 1], [0.2, 0.9]))
        self.assertAlmostEqual(H.brier_score([1, 0], [0.9, 0.2]), (0.1 ** 2 + 0.2 ** 2) / 2)
        self.assertAlmostEqual(H.expected_calibration_error([1, 0], [0.9, 0.2]),
                               0.5 * 0.1 + 0.5 * 0.2, places=12)
        self.assertAlmostEqual(H.expected_calibration_error([1], [1.0]), 0.0)
        self.assertIsNone(H.brier_score([], []))
        self.assertIsNone(H.expected_calibration_error([], []))

    def test_precision_at_k_and_weighted_quantile(self):
        labels = [1, 0, 1, 0, 0]
        order = [0, 2, 1, 3, 4]
        self.assertAlmostEqual(H.precision_at_k(labels, order, 2)["precision"], 1.0)
        self.assertAlmostEqual(H.precision_at_k(labels, order, 4)["precision"], 0.5)
        self.assertEqual(H.precision_at_k(labels, order, 25)["used"], 5)
        values = [0.1, 0.2, 0.3, 0.4]
        weights = [1, 1, 1, 1]
        self.assertAlmostEqual(H.weighted_quantile(values, weights, 0.5), 0.2)
        self.assertAlmostEqual(H.weighted_quantile(values, weights, 0.0), 0.1)
        self.assertAlmostEqual(H.weighted_quantile(values, weights, 1.0), 0.4)
        self.assertAlmostEqual(H.percentile_sorted(values, 0.025), 0.1)
        self.assertAlmostEqual(H.percentile_sorted(values, 0.975), 0.4)


# ------------------------------------------------------------------- panel / PIT
class PanelTests(unittest.TestCase):
    def test_schema_deviation_raises(self):
        panel = make_panel({("alpha", "dom_cardio"): [76]})
        panel["schema"] = "hist_v1.panel.v1"
        with self.assertRaises(ValueError) as context:
            H.Panel(panel)
        self.assertIn("hist_v2.domain_panel.v1", str(context.exception))

    def test_sibling_domains_from_category_bands(self):
        panel = H.Panel(tiny_eval_panel())
        self.assertEqual(panel.sibling_domains["dom_surg"], ["dom_robot"])
        self.assertEqual(panel.sibling_domains["dom_robot"], ["dom_surg"])
        self.assertEqual(panel.sibling_domains["dom_cardio"], [])
        self.assertEqual(panel.sibling_domains["dom_img"], [])

    def test_risk_sets_hand_computed(self):
        panel = H.Panel(tiny_eval_panel())
        t = quarter(2000, 1)
        risk_dom = set(panel.risk_set(t, adjacency=False))
        expected = {
            ("alpha", "dom_img"), ("alpha", "dom_robot"),
            ("beta", "dom_cardio"), ("beta", "dom_img"), ("beta", "dom_surg"),
            ("gamma", "dom_cardio"), ("gamma", "dom_surg"), ("gamma", "dom_robot"),
            ("delta", "dom_img"), ("delta", "dom_surg"),
        }
        self.assertEqual(risk_dom, expected)
        # only cells whose firm already has a sibling-domain event strictly before t
        risk_adj = set(panel.risk_set(t, adjacency=True))
        self.assertEqual(risk_adj,
                         {("alpha", "dom_robot"), ("beta", "dom_surg"),
                          ("delta", "dom_surg")})

    def test_establishment_and_labels(self):
        t = quarter(2000, 1)
        events = {
            ("alpha", "dom_cardio"): [t - 20],
            ("alpha", "dom_robot"): [t + 1],
            ("beta", "dom_img"): [t + 4],
            ("gamma", "dom_surg"): [t + 20],
        }
        panel = H.Panel(make_panel(events, with_counts=False))
        self.assertTrue(panel.established("alpha", t))
        self.assertFalse(panel.established("gamma", t))
        self.assertFalse(panel.pair_entered("alpha", "dom_robot", t))
        self.assertTrue(panel.pair_entered("alpha", "dom_robot", t + 1))
        self.assertEqual(panel.label("alpha", "dom_robot", t, 8), 1)
        self.assertEqual(panel.label("beta", "dom_img", t, 8), 1)
        self.assertEqual(panel.label("gamma", "dom_surg", t, 8), 0)     # outside horizon
        self.assertEqual(panel.label("gamma", "dom_surg", t, 20), 1)
        self.assertTrue(panel.mature(t, 8))
        self.assertFalse(panel.mature(LAST_QIDX - 2, 8))

    def test_features_hand_checked(self):
        t = quarter(2000, 1)
        panel = H.Panel(tiny_eval_panel())
        raw = panel.features("alpha", "dom_robot", t)
        self.assertAlmostEqual(raw["firm_act_4"], H._log1p(1))
        self.assertAlmostEqual(raw["firm_act_8"], H._log1p(2))
        self.assertAlmostEqual(raw["firm_growth"], 1 / (2 - 1 + 0.5))
        self.assertEqual(raw["firm_domains"], 2.0)
        self.assertAlmostEqual(raw["firm_tenure"], (t - (t - 30)) / 4.0)   # first event t-30
        self.assertAlmostEqual(raw["firm_entry_rate"], 2 / 8.0)
        self.assertAlmostEqual(raw["adj_act_8"], 0.0)          # sibling event outside window
        self.assertAlmostEqual(raw["adj_share"], 0.0)
        self.assertAlmostEqual(raw["domain_act_8"], H._log1p(2))   # beta + delta at t-6
        self.assertAlmostEqual(raw["domain_growth"], 0.0)
        self.assertEqual(raw["domain_entrants"], 2.0)
        self.assertAlmostEqual(raw["domain_recent_entries"], H._log1p(2))
        self.assertAlmostEqual(raw["domain_age"], 6 / 4.0)
        self.assertAlmostEqual(raw["domain_share"], 1 / 4.0)   # alpha events in dom_surg / ever
        self.assertAlmostEqual(raw["firm_size"], H._log1p(4))

    def test_features_use_per_quarter_event_counts(self):
        t = quarter(2000, 1)
        panel = H.Panel(make_panel({("alpha", "dom_cardio"): [t - 2, t - 1]},
                                   event_counts={("alpha", "dom_cardio"): [2, 1]}))
        raw = panel.features("alpha", "dom_robot", t)
        self.assertAlmostEqual(raw["firm_act_4"], H._log1p(3))
        self.assertAlmostEqual(raw["firm_act_8"], H._log1p(3))
        self.assertAlmostEqual(raw["firm_size"], H._log1p(3))

    def test_features_ignore_events_after_t(self):
        t = quarter(2000, 1)
        events = {("alpha", "dom_cardio"): [t - 2, t + 1], ("beta", "dom_robot"): [t + 2]}
        panel = H.Panel(make_panel(events, with_counts=False))
        raw = panel.features("alpha", "dom_robot", t)
        self.assertAlmostEqual(raw["firm_size"], H._log1p(1))
        self.assertAlmostEqual(raw["domain_entrants"], 0.0)
        self.assertAlmostEqual(raw["domain_act_8"], 0.0)

    def test_features_bruteforce_matches_indexed_features(self):
        panel = H.Panel(tiny_eval_panel())
        for t in (quarter(2000, 1), quarter(2000, 2)):
            for company, domain in panel.risk_set(t, adjacency=False):
                fast = panel.features(company, domain, t)
                slow = panel.features_bruteforce(company, domain, t)
                for name in H.FEATURE_NAMES_C:
                    if fast[name] is None:
                        self.assertIsNone(slow[name])
                    else:
                        self.assertAlmostEqual(fast[name], slow[name], places=12,
                                               msg=f"{name} at {company}/{domain} t={t}")

    def test_feature_groups_match_protocol(self):
        self.assertEqual(len(H.FEATURE_NAMES_C), 15)
        self.assertEqual(set(H.FEATURE_DEFINITIONS), set(H.FEATURE_NAMES_C))
        self.assertEqual(set(H.GROUP_A) | {"domain_act_8"},
                         set(H.GROUP_B) - {"domain_growth", "domain_entrants",
                                           "domain_recent_entries", "domain_age"})
        self.assertEqual(H.GROUP_C, H.FEATURE_NAMES_C)
        self.assertEqual(len(H.GROUP_A), 7)
        self.assertEqual(len(H.GROUP_B), 12)

    def test_all_bisect_indexes_are_sorted(self):
        panel = H.Panel(tiny_eval_panel())
        for company in panel.company_keys:
            self.assertEqual(panel.company_q[company], sorted(panel.company_q[company]))
            self.assertEqual(panel.company_domain_first_q[company],
                             sorted(panel.company_domain_first_q[company]))
            self.assertEqual(panel.company_entries[company],
                             sorted(panel.company_entries[company]))
            for domain in panel.domain_keys:
                self.assertEqual(panel.company_sibling_q[(company, domain)],
                                 sorted(panel.company_sibling_q[(company, domain)]))
        for domain in panel.domain_keys:
            self.assertEqual(panel.domain_entry_q[domain], sorted(panel.domain_entry_q[domain]))
            self.assertEqual(panel.domain_q[domain], sorted(panel.domain_q[domain]))


# --------------------------------------------------------- training sample / purge
class FakeData(H.RiskHorizonData):
    """Minimal stand-in for RiskHorizonData so training_sample() can be unit-tested."""

    def __init__(self, pool_t, labels, horizon=8, adjacency=False):
        self.pool_t = list(pool_t)
        self.horizon = horizon
        self.adjacency = adjacency
        self.risk_set_name = "R_dom_adj" if adjacency else "R_dom"
        self.pool_label = list(labels)
        self.positive_indices = [i for i, value in enumerate(labels) if value]
        self.negative_indices = [i for i, value in enumerate(labels) if not value]
        self.pool_positive_q = [self.pool_t[i] for i in self.positive_indices]
        self.pool_negative_q = [self.pool_t[i] for i in self.negative_indices]


class TrainingSampleTests(unittest.TestCase):
    def test_training_sample_cap_weights_and_purge(self):
        rows = 15000
        labels = [1] * 500 + [0] * (rows - 500)
        pool_t = list(range(rows))
        data = FakeData(pool_t, labels)
        sample = data.training_sample(origin=14000)
        self.assertEqual(sample["rows_before_sampling"], 13993)
        self.assertEqual(sample["rows_after_sampling"], H.TRAIN_ROW_CAP)
        self.assertEqual(sample["positives"], 500)
        self.assertEqual(sample["negatives_sampled"], H.TRAIN_ROW_CAP - 500)
        self.assertAlmostEqual(sample["negative_weight"],
                               1.0 / sample["negative_sampling_fraction"], places=12)
        self.assertLessEqual(sample["max_training_origin_qidx"],
                             sample["max_allowed_training_qidx"])
        self.assertTrue(sample["purge_ok"])

    def test_small_training_pool_not_subsampled(self):
        data = FakeData([0, 0, 1, 1], [1, 0, 1, 0])
        sample = data.training_sample(origin=9)      # cutoff = 1
        self.assertFalse(sample["subsampled"])
        self.assertEqual(sample["negative_weight"], 1.0)
        self.assertEqual(sample["rows_after_sampling"], 4)

    def test_purge_assertion_catches_leaky_cell(self):
        # deliberately inconsistent index lists: the pool row is really at q95, beyond the
        # cutoff, while the matching pool_positive_q claims q80 (<= cutoff)
        data = H.RiskHorizonData.__new__(H.RiskHorizonData)
        data.pool_t = [0, 95, 120]
        data.pool_label = [0, 1, 1]
        data.positive_indices = [1, 2]
        data.negative_indices = [0]
        data.pool_positive_q = [80, 100]        # inconsistent with pool_t on purpose
        data.pool_negative_q = [0]
        data.horizon = 8
        data.adjacency = False
        data.risk_set_name = "R_dom"
        with self.assertRaises(ValueError) as context:
            data.training_sample(origin=95)      # cutoff = 87; the claimed q95 cell leaks
        self.assertIn("purge violated", str(context.exception))

    def test_purge_holds_for_every_origin_of_the_golden_panel(self):
        panel = H.Panel(golden_panel())
        data = H.RiskHorizonData(panel, False, 8, max_origins=2)
        self.assertGreater(data.pool_rows, 0)
        for origin in data.test_origins:
            sample = data.training_sample(origin)
            self.assertTrue(sample["purge_ok"])
            self.assertLessEqual(sample["max_training_origin_qidx"],
                                 sample["max_allowed_training_qidx"])
            self.assertLessEqual(sample["rows_after_sampling"], H.TRAIN_ROW_CAP)

    def test_training_grid_is_quarterly(self):
        panel = H.Panel(golden_panel())
        data = H.RiskHorizonData(panel, False, 8, max_origins=2)
        self.assertEqual(sorted(set(data.pool_t)),
                         list(range(min(data.pool_t), data.max_train_t + 1)))
        self.assertEqual(data.pool_t, sorted(data.pool_t))


# --------------------------------------------------------------- model / baseline
class ModelTests(unittest.TestCase):
    def test_weighted_logistic_is_deterministic_and_directional(self):
        rows = [[0.0], [0.0], [1.0], [1.0], [1.0], [0.0]]
        labels = [0, 0, 1, 1, 1, 0]
        weights = [1.0] * 6
        first = H.fit_logistic_regression(rows, labels, weights)
        second = H.fit_logistic_regression(rows, labels, weights)
        self.assertEqual(json.dumps(first, sort_keys=True),
                         json.dumps(second, sort_keys=True))
        self.assertGreater(first["loss_start"], first["loss_end"])
        positive = H.predict_logistic(first, [[1.0]])
        negative = H.predict_logistic(first, [[0.0]])
        self.assertGreater(positive[0], negative[0])

    def test_logistic_handles_missing_feature_with_training_median(self):
        rows = [[1.0, 2.0], [float("nan"), 2.0], [3.0, float("nan")]]
        labels = [1, 0, 1]
        model = H.fit_logistic_regression(rows, labels, [1.0, 1.0, 1.0], epochs=5)
        self.assertEqual(model["medians"][0], 1.0)
        self.assertEqual(model["medians"][1], 2.0)
        self.assertTrue(all(0.0 <= value <= 1.0
                            for value in H.predict_logistic(model, rows)))

    def test_baselines_rank_companies_and_domains(self):
        panel = H.Panel(golden_panel())
        data = H.RiskHorizonData(panel, False, 8, max_origins=2)
        origin = data.test_origins[-1]
        sample = data.training_sample(origin)
        fit = H.fit_baselines(data, sample)
        self.assertGreater(fit["prevalence"], 0.0)
        predictions = H.predict_baselines(fit, ["alpha", "delta"],
                                          ["dom_cardio", "dom_surg"])
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
            domains = [f"d{rng.randrange(5)}" for _ in range(60)]
            scores = {"B1": [rng.random() for _ in range(60)]}
            scores["M1C"] = (list(scores["B1"]) if identical
                             else [rng.random() for _ in range(60)])
            records.append({"origin": origin, "companies": companies, "domains": domains,
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
            "domains": ["dom_cardio", "dom_surg", "dom_img", "dom_robot"],
            "labels": [0, 0, 0, 0],
            "scores": {"M1C": [0.1, 0.1, 0.9, 0.3]},
            "thresholds": {"M1C": {budget: 0.5 for budget in H.ALERT_BUDGETS}},
        }, {
            "origin": 4,
            "companies": ["a", "b", "c", "d"],
            "domains": ["dom_cardio", "dom_surg", "dom_img", "dom_robot"],
            "labels": [1, 0, 1, 0],
            "scores": {"M1C": [0.9, 0.1, 0.2, 0.3]},
            "thresholds": {"M1C": {budget: 0.5 for budget in H.ALERT_BUDGETS}},
        }]
        entries = {"entries": [
            {"company_key": "a", "domain_id": "dom_cardio", "entry_qidx": 8,
             "candidate_origins": [0, 4]},          # first alert at origin 4 -> lead 4
            {"company_key": "b", "domain_id": "dom_surg", "entry_qidx": 8,
             "candidate_origins": [0, 4]},          # never alerted -> missed
        ], "n_entries": 2, "excluded_never_in_risk_set": 0, "evaluation_window": [1, 12]}
        result = H.alert_analysis(records, entries, "M1C", 0.10)
        self.assertEqual(result["entries_in_scope"], 2)
        self.assertEqual(result["entries_alerted"], 1)
        self.assertEqual(result["entries_missed"], 1)
        self.assertEqual(result["lead_quarters"]["median"], 4)
        self.assertEqual(result["alerts"], 2)
        self.assertAlmostEqual(result["precision"], 0.5)
        self.assertAlmostEqual(result["recall"], 0.5)
        self.assertAlmostEqual(result["false_alarms_per_1000_candidate_quarters"],
                               1000.0 * 1 / 8)


# ---------------------------------------------------------------- golden end-to-end
class GoldenEndToEndTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._directory = tempfile.TemporaryDirectory()
        root = Path(cls._directory.name)
        cls.panel_path = root / "domain_panel.json"
        cls.results_path = root / "results.json"
        cls.panel_path.write_text(json.dumps(golden_panel()), encoding="utf-8")
        exit_code = H.main([
            "--panel", str(cls.panel_path),
            "--out", str(cls.results_path),
            "--quick",
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
                    "holdout", "lead_time", "power", "leakage_controls", "decision"):
            self.assertIn(key, self.results)
        self.assertEqual(self.results["schema"], "hist_v2.results.v1")
        self.assertEqual(len(self.results["panel_sha256"]), 64)
        self.assertEqual(self.results["config"]["protocol"],
                         "research/protocols/hist_v2_preregistration.md")
        self.assertEqual(self.results["config"]["amendments_applied"], [])
        self.assertIn("no hist_v2 model had been fitted before the freeze",
                      self.results["config"]["freeze_statement"])
        self.assertEqual(self.results["config"]["feature_source"], "event_counts")

    def test_golden_origin_counts_and_models(self):
        primary = self.results["primary"]
        self.assertEqual(primary["n_origins"], 2)
        self.assertEqual(primary["origin_labels"], ["1995-Q1", "1996-Q1"])
        candidates = [row["n_candidates"] for row in primary["per_origin"]]
        positives = [row["n_positives"] for row in primary["per_origin"]]
        self.assertEqual(candidates, [12, 11])
        self.assertEqual(positives, [2, 2])
        self.assertEqual(set(primary["models"]),
                         {"B0", "B1", "B2", "B3", "M1A", "M1B", "M1C"})
        for model in ("B0", "B1", "B2", "B3", "M1A", "M1B", "M1C"):
            self.assertIn(model, primary["mean_per_origin_ap"])
            self.assertIsNotNone(primary["mean_per_origin_ap"][model]["mean"])
        self.assertEqual(primary["bootstrap"]["reps_requested"], 200)
        self.assertEqual(primary["bootstrap"]["seed"], H.SEED)
        self.assertEqual(set(primary["deltas_vs_baselines"]),
                         {"M1C-B1", "M1C-B2", "M1C-B3"})

    def test_golden_dataset_purge_and_sampling(self):
        totals = self.results["dataset"]["totals"]["R_dom|h8"]
        self.assertEqual(totals["candidate_cells"], 23)
        self.assertEqual(totals["positive_cells"], 4)
        self.assertEqual(totals["immature_excluded"], 0)
        for row in self.results["dataset"]["configs"]["R_dom|h8"]:
            training = row["training"]
            self.assertTrue(training["purge_ok"])
            self.assertLessEqual(training["max_training_origin_qidx"],
                                 training["max_allowed_training_qidx"])
            self.assertLessEqual(training["rows_after_sampling"], H.TRAIN_ROW_CAP)
        self.assertEqual(self.results["leakage_controls"]["label_purge"]["violations"], 0)
        self.assertEqual(set(self.results["dataset"]["configs"]),
                         {"R_dom|h8", "R_dom_adj|h8", "R_dom|h4", "R_dom_adj|h4"})

    def test_golden_robustness_power_and_holdout(self):
        robustness = self.results["robustness"]
        self.assertEqual(set(robustness["eras"]), {"1995-2004", "2005-2015"})
        self.assertEqual(set(robustness["feature_groups"]), {"A", "B", "C"})
        permutation = robustness["permutation_null"]
        self.assertEqual(permutation["n_permutations_achieved"], 5)
        self.assertAlmostEqual(permutation["resolution_floor"], 1.0 / 6.0)
        self.assertIn("origin quarter, domain", permutation["scheme"])
        self.assertEqual(robustness["attribution_sensitivity_no_acquired"]["status"],
                         "DESCRIPTIVE_SENSITIVITY")
        power = self.results["power"]
        self.assertEqual(power["mde_target_ap_points"], 0.05)
        self.assertTrue(power["smoke_estimate"])
        self.assertIn(power["status"], ("POWERED", "UNDERPOWERED"))
        self.assertIsNotNone(power["primary_M1C_minus_B1"]["mde_80pct_power_alpha_0.05"])
        holdout = self.results["holdout"]
        self.assertEqual(holdout["status"], "DESCRIPTIVE_NO_INFERENCE")
        self.assertEqual(holdout["origins"], ["2016-Q1", "2017-Q1"])
        self.assertNotIn("bootstrap", holdout)
        decision = self.results["decision"]["H1"]
        for key in ("criterion_components", "criterion_met", "powered", "supported",
                    "overall_verdict", "decisive_secondary_M1C_minus_B3"):
            self.assertIn(key, decision)
        self.assertEqual(decision["primary_estimand"], "R_dom|h8")

    def test_golden_lead_time_and_leak_control(self):
        lead = self.results["lead_time"]
        self.assertEqual(len(lead["h5_frontier"]), 4)
        self.assertEqual([row["budget"] for row in lead["h5_frontier"]],
                         list(H.ALERT_BUDGETS))
        for row in lead["h5_frontier"]:
            self.assertIn("entries_missed", row)
        self.assertEqual(self.results["leakage_controls"]["independent_replay"]["mismatches"], 0)
        self.assertIn("cells_sampled", self.results["leakage_controls"]["independent_replay"])

    def test_results_json_is_nan_free(self):
        text = self.results_path.read_text(encoding="utf-8")
        self.assertNotIn("NaN", text)
        json.loads(text, parse_constant=lambda value: (_ for _ in ()).throw(
            AssertionError(f"non-finite JSON constant {value}")))

    def test_atomic_json_write_leaves_no_tmp(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "nested" / "results.json"
            H.write_json_atomic(path, {"schema": "x", "value": 1})
            self.assertTrue(path.is_file())
            self.assertFalse(path.with_name(path.name + ".tmp").exists())
            self.assertEqual(json.loads(path.read_text(encoding="utf-8"))["value"], 1)


# --------------------------------------------------------- domain panel aggregation
TRACKS_CONFIG = {
    "schema": 2,
    "tracks": [
        {"id": "t_cardio_a", "name_en": "Cardio A", "category": "cardiovascular",
         "domain": "dom_cardio"},
        {"id": "t_cardio_b", "name_en": "Cardio B", "category": "cardiovascular",
         "domain": "dom_cardio"},
        {"id": "t_surg_a", "name_en": "Surg A", "category": "surgery", "domain": "dom_surg"},
        {"id": "t_robot", "name_en": "Robot", "category": "surgery", "domain": "dom_robot"},
        {"id": "t_img", "name_en": "Imaging", "category": "imaging", "domain": "dom_img"},
        {"id": "t_orphan", "name_en": "Orphan", "category": "specialty"},
    ],
    "domains": [
        {"id": "dom_cardio", "name_en": "Cardio"},
        {"id": "dom_img", "name_en": "Imaging"},
        {"id": "dom_robot", "name_en": "Robotics"},
        {"id": "dom_surg", "name_en": "Surgery"},
    ],
}


def make_hist_v1_panel(records: dict[tuple[str, str], list[tuple[int, str, int]]],
                       tracks_config=TRACKS_CONFIG) -> dict:
    """Build a synthetic ``hist_v1.panel.v1`` panel from explicit per-quarter items."""
    grouped: dict[tuple[str, str], list[tuple[int, str, int]]] = {}
    for key, items in records.items():
        grouped[key] = sorted(items)
    pairs = []
    for (company, track), items in sorted(grouped.items()):
        iso_by_quarter: dict[int, str] = {}
        count_by_quarter: dict[int, int] = {}
        for qidx, iso, count in items:
            if qidx not in iso_by_quarter or iso < iso_by_quarter[qidx]:
                iso_by_quarter[qidx] = iso
            count_by_quarter[qidx] = count_by_quarter.get(qidx, 0) + count
        qidxs = sorted(iso_by_quarter)
        counts = [count_by_quarter[qidx] for qidx in qidxs]
        pairs.append({
            "company_key": company,
            "track_id": track,
            "event_qidx": qidxs,
            "event_iso": [iso_by_quarter[qidx] for qidx in qidxs],
            "event_counts": counts,
            "n_510k": sum(counts),
            "n_pma": 0,
        })
    companies = []
    for company in sorted({pair["company_key"] for pair in pairs}):
        own = [(q, count) for pair in pairs if pair["company_key"] == company
               for q, count in zip(pair["event_qidx"], pair["event_counts"])]
        companies.append({
            "key": company, "display_name": company.title(), "cohort": "fixture",
            "total_material_events": sum(count for _, count in own),
            "first_event_qidx": min(q for q, _ in own),
            "last_event_qidx": max(q for q, _ in own),
        })
    track_records = []
    for track in tracks_config["tracks"]:
        industry = [q for pair in pairs if pair["track_id"] == track["id"]
                    for q, count in zip(pair["event_qidx"], pair["event_counts"])
                    for _ in range(count)]
        record = dict(track)
        record["first_industry_qidx"] = min(industry) if industry else None
        record["n_firms_ever"] = len({pair["company_key"] for pair in pairs
                                      if pair["track_id"] == track["id"]})
        track_records.append(record)
    total = sum(pair["n_510k"] + pair["n_pma"] for pair in pairs)
    return {
        "schema": "hist_v1.panel.v1",
        "generated_at": "2026-10-31T03:55:55Z",
        "quarter_start": "1976-Q1",
        "quarter_end": "2026-Q2",
        "quarters": list(QUARTERS),
        "companies": companies,
        "tracks": track_records,
        "pairs": pairs,
        "pairs_no_acquired": copy.deepcopy(pairs),
        "audits": {"schema": "hist_v1.audits.v1",
                   "panel_summary": {"n_material_events": total}},
    }


class DomainAggregationTests(unittest.TestCase):
    def _source_records(self):
        rows = {
            ("alpha", "t_cardio_a"): [(40, "1986-02-10", 1), (60, iso_date(60), 2)],
            ("alpha", "t_cardio_b"): [(40, "1986-03-20", 1)],
            ("beta", "t_surg_a"): [(30, iso_date(30), 1), (70, iso_date(70), 1)],
            ("gamma", "t_robot"): [(50, iso_date(50), 1)],
            ("delta", "t_img"): [(20, iso_date(20), 1)],
            ("alpha", "t_orphan"): [(45, iso_date(45), 1)],
        }
        return rows

    def _write_inputs(self, root: Path) -> tuple[Path, Path]:
        panel = make_hist_v1_panel(self._source_records())
        # attribution sensitivity: remove alpha/t_cardio_a's 1991-Q1 event (subset)
        sensitivity = copy.deepcopy(panel["pairs"])
        for pair in sensitivity:
            if pair["company_key"] == "alpha" and pair["track_id"] == "t_cardio_a":
                pair["event_qidx"] = [40]
                pair["event_iso"] = ["1986-01-05"]
                pair["event_counts"] = [1]
                pair["n_510k"] = 1
                pair["n_pma"] = 0
        panel["pairs_no_acquired"] = sensitivity
        panel_path = root / "hist_v1_panel.json"
        tracks_path = root / "tracks_device.json"
        panel_path.write_text(json.dumps(panel), encoding="utf-8")
        tracks_path.write_text(json.dumps(TRACKS_CONFIG), encoding="utf-8")
        return panel_path, tracks_path

    def test_aggregation_counts_iso_and_unmapped_events(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            panel_path, tracks_path = self._write_inputs(root)
            result = B.build(panel_path=panel_path, tracks_config_path=tracks_path,
                             out_panel_path=root / "domain_panel.json",
                             manifest_path=root / "manifest.json")
            panel = result["panel"]
            self.assertEqual(panel["schema"], "hist_v2.domain_panel.v1")
            self.assertEqual([record["id"] for record in panel["domains"]],
                             ["dom_cardio", "dom_img", "dom_robot", "dom_surg"])
            pairs = {(pair["company_key"], pair["domain_id"]): pair
                     for pair in panel["pairs"]}
            alpha = pairs[("alpha", "dom_cardio")]
            self.assertEqual(alpha["event_qidx"], [40, 60])
            self.assertEqual(alpha["event_counts"], [2, 2])
            self.assertEqual(alpha["n_510k"] + alpha["n_pma"], 4)
            # earliest availability date in quarter 40 wins across the two tracks
            self.assertEqual(alpha["event_iso"][0], "1986-02-10")
            # the orphan track has no domain and is excluded and counted
            self.assertNotIn(("alpha", "dom_specialty"), pairs)
            self.assertEqual(result["audits"]["panel_summary"]["n_events_without_domain"], 1)
            self.assertEqual(result["audits"]["aggregation"]["n_domain_events"], 8)
            self.assertTrue(result["audits"]["aggregation"]["events_reconciled"])
            self.assertEqual(result["audits"]["per_domain"]["dom_cardio"]["pairs"], 1)
            self.assertEqual(result["audits"]["per_domain"]["dom_cardio"]["events"], 4)
            self.assertEqual(len(panel["pairs"]), 4)
            self.assertEqual(panel["companies"][0]["total_material_events"], 4)  # alpha
            # the no-acquired variant removes the 1991-Q1 alpha event (count 2)
            sensitivity = {(pair["company_key"], pair["domain_id"]): pair
                           for pair in panel["pairs_no_acquired"]}
            alpha_sensitivity = sensitivity[("alpha", "dom_cardio")]
            self.assertEqual(alpha_sensitivity["event_counts"], [2])
            self.assertEqual(panel["audits"]["pairs_no_acquired"]["n_events"], 6)

    def test_manifest_hashes_and_row_counts(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            panel_path, tracks_path = self._write_inputs(root)
            out_panel = root / "domain_panel.json"
            manifest_path = root / "manifest.json"
            result = B.build(panel_path=panel_path, tracks_config_path=tracks_path,
                             out_panel_path=out_panel, manifest_path=manifest_path)
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(manifest["schema"], "hist_v2.manifest.v1")
            self.assertEqual(manifest["row_counts"]["domain_panel"]["pairs"],
                             len(result["panel"]["pairs"]))
            self.assertEqual(manifest["row_counts"]["domain_panel"]["domains"], 4)
            self.assertEqual(result["panel_sha256"], B.sha256_file(out_panel))
            self.assertEqual(manifest["files"][
                B._rel(out_panel)]["sha256"], result["panel_sha256"])
            self.assertIn(B._rel(panel_path), manifest["files"])

    def test_two_builds_are_byte_identical_and_source_untouched(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            panel_path, tracks_path = self._write_inputs(root)
            source_before = panel_path.read_bytes()
            out_panel = root / "domain_panel.json"
            manifest_path = root / "manifest.json"
            arguments = dict(panel_path=panel_path, tracks_config_path=tracks_path,
                             out_panel_path=out_panel, manifest_path=manifest_path)
            B.build(**arguments)
            first_panel = out_panel.read_bytes()
            first_manifest = manifest_path.read_bytes()
            B.build(**arguments)
            self.assertEqual(out_panel.read_bytes(), first_panel)
            self.assertEqual(manifest_path.read_bytes(), first_manifest)
            self.assertEqual(panel_path.read_bytes(), source_before)

    def test_builder_rejects_wrong_source_schema(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            panel_path, tracks_path = self._write_inputs(root)
            panel = json.loads(panel_path.read_text(encoding="utf-8"))
            panel["schema"] = "hist_v2.domain_panel.v1"
            panel_path.write_text(json.dumps(panel), encoding="utf-8")
            with self.assertRaises(SystemExit):
                B.build(panel_path=panel_path, tracks_config_path=tracks_path,
                        out_panel_path=root / "out.json",
                        manifest_path=root / "manifest.json")


# ------------------------------------------------------- determinism / provenance
class ProvenanceTests(unittest.TestCase):
    def test_eval_and_builder_have_no_forbidden_imports(self):
        for path in (EVAL_PATH, BUILDER_PATH):
            source = path.read_text(encoding="utf-8")
            for package in ("numpy", "pandas", "scipy", "sklearn", "torch"):
                self.assertNotRegex(source, rf"(?m)^\s*(?:import|from)\s+{package}\b",
                                    msg=f"{path.name} imports {package}")

    def test_panel_loader_detects_variant_and_primary_event_audit(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "panel.json"
            path.write_text(json.dumps(golden_panel()), encoding="utf-8")
            primary = H.load_panel(path)
            self.assertEqual(primary.variant, "primary")
            self.assertTrue(primary.event_count_audit["matches"])
            panel = golden_panel()
            variant_pairs = copy.deepcopy(panel["pairs"])
            variant_pairs[0]["event_counts"] = variant_pairs[0]["event_counts"][:-1]
            variant_pairs[0]["event_qidx"] = variant_pairs[0]["event_qidx"][:-1]
            variant_pairs[0]["event_iso"] = variant_pairs[0]["event_iso"][:-1]
            variant_pairs[0]["n_510k"] = sum(variant_pairs[0]["event_counts"])
            variant_pairs[0]["n_pma"] = 0
            panel["pairs_no_acquired"] = variant_pairs
            path.write_text(json.dumps(panel), encoding="utf-8")
            variant = H.load_panel(path, pairs_key="pairs_no_acquired",
                                   variant="pairs_no_acquired")
            self.assertEqual(variant.variant, "pairs_no_acquired")
            self.assertFalse(variant.event_count_audit["matches_primary_panel"])


if __name__ == "__main__":
    unittest.main()
