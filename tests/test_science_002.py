"""Offline tests for SCIENCE-002 (research/science_002).

No network. Every fixture is synthetic, so a failure here is a failure of our own
logic, never of FDA, SEC or today's internet.

The tests pin the invariants the study depends on:

* a cross-source match is never made from name *similarity* - only from string
  identity after a documented normalisation, at a named tier;
* an applicant string claimed by two registrants is dropped from both;
* a filing accepted after the prediction instant can never enter a feature;
* a clearance whose decision date falls inside the outcome window can never enter
  a historical-count feature;
* XBRL facts are visible only from their filing day, and a restatement is never
  backfilled;
* the firm-conditional estimator is identified from within-firm variation, so a
  constant-within-firm feature cannot change a within-firm ranking;
* the pre-registered decision rule returns NO-GO when a control fails and NULL
  when the experiment is valid but the effect is absent.

Run:  python -m pytest tests/test_science_002.py -q
"""

from __future__ import annotations

import datetime as dt
import json
import math
import tempfile
import unittest
import zipfile
from pathlib import Path

from research.science_002 import audit, entity, experiment, fda, panel, sec, universe
from research.science_002.entity import SecRegistrant

UTC = dt.timezone.utc


def filing(day: str, form: str = "8-K", items: tuple[str, ...] = (), hour: int = 16,
           accession: str = "0000000000-24-000001") -> sec.Filing:
    stamp = dt.datetime.fromisoformat(day + "T%02d:00:00+00:00" % hour)
    return sec.Filing(accession=accession, form=form,
                      filing_date=stamp.date(), acceptance_utc=stamp, items=items)


def fact(start: str, end: str, value: float, filed: str) -> sec.Fact:
    return sec.Fact(tag="ResearchAndDevelopmentExpense",
                    start=dt.date.fromisoformat(start), end=dt.date.fromisoformat(end),
                    value=value, filed=dt.date.fromisoformat(filed), form="10-Q")


def row(key: str, month_end: str, label: int, **features: float) -> panel.PanelRow:
    return panel.PanelRow(key=key, ticker=key.upper(), cik="0000000000",
                          month_end=dt.date.fromisoformat(month_end),
                          split="train", label=label, n_events_in_window=label,
                          features=dict(features))


class NameNormalisationTests(unittest.TestCase):
    def test_legal_suffixes_and_state_tokens_are_dropped(self):
        self.assertEqual(entity.normalise_name("Medtronic plc"), "MEDTRONIC")
        self.assertEqual(entity.normalise_name("Medtronic, Inc."), "MEDTRONIC")
        self.assertEqual(entity.normalise_name("LIFECORE BIOMEDICAL, INC. \\DE\\"),
                         "LIFECORE BIOMEDICAL")

    def test_ampersand_becomes_and(self):
        self.assertEqual(entity.normalise_name("Smith & Nephew, Inc."), "SMITH AND NEPHEW")

    def test_similar_but_different_names_do_not_match(self):
        # the exact pair that a fuzzy matcher would collapse and this study will not
        self.assertNotEqual(entity.normalise_name("Baxter Healthcare Corp"),
                            entity.normalise_name("BAXTER INTERNATIONAL INC"))

    def test_empty_and_punctuation_only_inputs(self):
        self.assertEqual(entity.normalise_name(""), "")
        self.assertEqual(entity.normalise_name("..."), "")


class EntityResolutionTests(unittest.TestCase):
    def setUp(self):
        self.applicants = {
            "MEDTRONIC VASCULAR": {"applicant": "Medtronic Vascular", "n": 10,
                                   "first_decision": "2001-01-01",
                                   "last_decision": "2020-01-01"},
            "MEDTRONIC": {"applicant": "Medtronic, Inc.", "n": 5,
                          "first_decision": "2002-01-01", "last_decision": "2019-01-01"},
            "INARI MEDICAL": {"applicant": "Inari Medical", "n": 7,
                              "first_decision": "2018-01-01", "last_decision": "2021-01-01"},
        }
        self.owners = {"MEDTRONIC VASCULAR": {"MEDTRONIC"},
                       "INARI MEDICAL": {"STRYKER"}}

    def test_tier_a_and_tier_b_and_former_names(self):
        reg = SecRegistrant(cik="0001", title="Medtronic plc")
        proposals = universe.propose_matches([reg], {"MEDTRONIC": 5}, {})
        self.assertEqual([p["tier"] for p in proposals], ["T_A"])
        proposals = universe.propose_matches([reg], {"MEDTRONIC VASCULAR": 10}, self.owners)
        self.assertEqual([p["tier"] for p in proposals], ["T_B"])
        reg2 = SecRegistrant(cik="0002", title="New Name Corp",
                             former_names=(("Old Device Co", "2010-01-01", "2015-01-01"),))
        proposals = universe.propose_matches([reg2], {"OLD DEVICE": 4}, {})
        self.assertEqual([p["tier"] for p in proposals], ["T_A2"])

    def test_shared_applicant_is_dropped_from_every_claimant(self):
        a = SecRegistrant(cik="0001", title="Alpha Medical Inc")
        b = SecRegistrant(cik="0002", title="Alpha Medical Corp")
        proposals = universe.propose_matches([a, b], {"ALPHA MEDICAL": 9}, {})
        accepted, ledger = universe.resolve_ambiguity(proposals)
        self.assertEqual(accepted, [])
        self.assertTrue(all(entry["status"] == "ambiguous_applicant" for entry in ledger))
        self.assertEqual({entry["cik"] for entry in ledger}, {"0001", "0002"})

    def test_window_counts_ignore_uncleared_and_out_of_window_decisions(self):
        records = [
            {"applicant": "Medtronic, Inc.", "decision_date": "2022-01-01", "decision_code": "SESE"},
            {"applicant": "Medtronic, Inc.", "decision_date": "2022-02-01", "decision_code": "SN"},
            {"applicant": "Medtronic, Inc.", "decision_date": "2014-01-01", "decision_code": "SESE"},
        ]
        counts = universe.window_clearance_counts(records)
        self.assertEqual(counts["MEDTRONIC"], 1)


class FdaParsingTests(unittest.TestCase):
    def test_streaming_reader_yields_only_result_objects(self):
        payload = {"meta": {"results": {"total": 2}},
                   "results": [{"k_number": "K1", "applicant": "A"},
                               {"k_number": "K2", "applicant": "B"}],
                   "extra": [1, 2, 3]}
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bulk.json.zip"
            with zipfile.ZipFile(path, "w") as zf:
                zf.writestr("device.json", json.dumps(payload))
            rows = list(fda.iter_json_records(path))
        self.assertEqual([r["k_number"] for r in rows], ["K1", "K2"])

    def test_records_round_trip(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "records.csv"
            info = fda.write_records_csv(
                [{"k_number": "K1", "applicant": "A", "decision_date": "2020-01-01",
                  "decision_code": "SESE"}], path)
            rows = fda.read_records_csv(path)
        self.assertEqual(info["rows"], 1)
        self.assertEqual(rows[0]["k_number"], "K1")


class SecSemanticsTests(unittest.TestCase):
    def test_acceptance_instant_is_utc_and_missing_zone_is_rejected(self):
        self.assertEqual(sec.parse_instant("2024-01-15T16:30:00.000Z"),
                         dt.datetime(2024, 1, 15, 16, 30, tzinfo=UTC))
        self.assertIsNone(sec.parse_instant("2024-01-15T16:30:00"))

    def test_recent_filings_parses_items_and_forms(self):
        payload = {"filings": {"recent": {
            "accessionNumber": ["0000000000-24-000001", "0000000000-24-000002"],
            "filingDate": ["2024-01-15", "2024-02-15"],
            "acceptanceDateTime": ["2024-01-15T16:30:00.000Z", "2024-02-15T16:30:00.000Z"],
            "form": ["8-K", "10-Q"],
            "items": ["2.02,9.01", ""],
            "primaryDocument": ["a.htm", "b.htm"],
        }}}
        filings = sec.recent_filings(payload)
        self.assertEqual(len(filings), 2)
        self.assertEqual(filings[0].items, ("2.02", "9.01"))
        only_8k = sec.recent_filings(payload, forms=("8-K",))
        self.assertEqual(len(only_8k), 1)

    def test_first_reported_fact_wins(self):
        payload = {"facts": {"us-gaap": {"ResearchAndDevelopmentExpense": {"units": {"USD": [
            {"start": "2024-01-01", "end": "2024-03-31", "val": 10, "filed": "2024-05-01"},
            {"start": "2024-01-01", "end": "2024-03-31", "val": 12, "filed": "2024-08-01"},
        ]}}}}}
        facts = sec.duration_facts(payload, sec.RD_TAGS)
        self.assertEqual(len(facts), 1)
        self.assertEqual(facts[0].value, 10)
        self.assertEqual(facts[0].filed, dt.date(2024, 5, 1))


class PanelFeatureTests(unittest.TestCase):
    def test_month_ends_are_inclusive_and_correct(self):
        ends = panel.month_ends(dt.date(2024, 1, 1), dt.date(2024, 3, 1))
        self.assertEqual([d.isoformat() for d in ends],
                         ["2024-01-31", "2024-02-29", "2024-03-31"])

    def test_historical_counts_respect_the_availability_lag(self):
        t = dt.datetime(2024, 6, 30, 23, 59, 59, tzinfo=UTC)
        dates = [dt.date(2024, 6, 20),   # inside the lag window: not knowable yet
                 dt.date(2024, 5, 1),    # before the lag cut: counted
                 dt.date(2023, 1, 1)]    # counted in the 730-day window
        out = panel.clearance_counts(dates, t)
        self.assertEqual(out["clr_365"], 1.0)
        self.assertEqual(out["clr_730"], 2.0)

    def test_outcome_window_starts_strictly_after_the_prediction_instant(self):
        t = dt.datetime(2024, 6, 30, 23, 59, 59, tzinfo=UTC)
        dates = [dt.date(2024, 6, 30), dt.date(2024, 7, 1), dt.date(2024, 9, 28)]
        window = panel.clearance_window(dates, t)
        self.assertEqual([d.isoformat() for d in window], ["2024-07-01", "2024-09-28"])

    def test_ttm_requires_four_distinct_quarters_and_ignores_annual_facts(self):
        facts = [fact("2023-01-01", "2023-03-31", 1.0, "2023-05-01"),
                 fact("2023-04-01", "2023-06-30", 1.0, "2023-08-01"),
                 fact("2023-07-01", "2023-09-30", 1.0, "2023-11-01"),
                 fact("2023-10-01", "2023-12-31", 1.0, "2024-02-01"),
                 fact("2023-01-01", "2023-12-31", 99.0, "2024-02-01")]
        ttm, values = panel._ttm(facts, dt.date(2024, 6, 30))
        self.assertEqual(ttm, 4.0)
        self.assertEqual(len(values), 4)
        ttm_early, _ = panel._ttm(facts, dt.date(2023, 12, 1))
        self.assertIsNone(ttm_early)


class EstimationTests(unittest.TestCase):
    def test_auc_matches_known_values_including_ties(self):
        self.assertEqual(experiment.auc([1, 1, 0, 0], [0.9, 0.8, 0.2, 0.1]), 1.0)
        self.assertEqual(experiment.auc([1, 1, 0, 0], [0.5, 0.5, 0.5, 0.5]), 0.5)
        self.assertIsNone(experiment.auc([1, 1], [0.2, 0.3]))

    def test_firm_effects_cannot_change_a_within_firm_ranking(self):
        rows = []
        for i, firm in enumerate(("a", "b")):
            for j, (label, score) in enumerate([(1, 0.7), (0, 0.2), (1, 0.6), (0, 0.1)]):
                rows.append(panel.PanelRow(key=firm, ticker=firm, cik=firm,
                                           month_end=dt.date(2024, 1 + j, 1), split="train",
                                           label=label, n_events_in_window=label,
                                           features={"x": score + i}))
        model = experiment.RidgeLogit(("x",), firm_effects=True).fit(rows)
        per = experiment.stratified_auc([r.label for r in rows], model.score(rows),
                                        [r.key for r in rows])
        self.assertAlmostEqual(per["value"], 1.0, places=6)

    def test_stratified_auc_excludes_single_class_firms(self):
        labels = [1, 1, 0, 0, 1, 1]
        scores = [0.9, 0.8, 0.1, 0.2, 0.4, 0.6]
        groups = ["a", "a", "a", "a", "b", "b"]
        out = experiment.stratified_auc(labels, scores, groups)
        self.assertEqual(out["n_firms"], 1)
        self.assertAlmostEqual(out["value"], 1.0, places=6)

    def test_label_transplant_is_reported_not_assumed(self):
        labels = [1, 0, 1, 0, 1, 0]
        scores = {"B3c": [0.9, 0.1, 0.8, 0.2, 0.7, 0.3]}
        out = experiment._label_transplant(labels, scores, ["a", "a", "b", "b", "c", "c"])
        self.assertIn("stratified", out)
        self.assertIsInstance(out["stratified"]["B3c"], float)

    def test_future_filing_does_not_enter_a_feature(self):
        t = dt.datetime(2024, 6, 30, 23, 59, 59, tzinfo=UTC)
        past = filing("2024-05-01", items=("8.01",))
        future = filing("2024-07-01", items=("8.01",))
        self.assertEqual(panel._filing_counts([past], t, 90), 1)
        self.assertEqual(panel._filing_counts([past, future], t, 90), 1)
        self.assertEqual(panel._filing_counts([past, future], t, 90, "8.01"), 1)


class DecisionRuleTests(unittest.TestCase):
    def _base(self) -> dict:
        return {
            "meta": {"n_holdout": 800, "prevalence_holdout": 0.5},
            "conditional": {"B2c": {"n_firms": 40}},
            "pooled": {"B1": 0.83},
            "controls": {"positive_control_any8k": {"pooled_B2": 0.63},
                         "placebo_features": {"p_two_sided": 0.9}},
            "primary": {"delta_stratified_auc_B3c_minus_B2c": 0.01},
            "permutation": {"p_two_sided": 0.5},
            "bootstrap": {"delta_B3c_minus_B2c": {"lo": -0.02, "hi": 0.04}},
            "lofo": {"delta_B3_minus_B2": {"mean": 0.0}},
        }

    def test_valid_null_is_null_not_no_go(self):
        self.assertEqual(experiment.decide(self._base())["verdict"], "NULL")

    def test_failed_positive_control_is_no_go(self):
        payload = self._base()
        payload["pooled"]["B1"] = 0.51
        self.assertEqual(experiment.decide(payload)["verdict"], "NO-GO")

    def test_go_requires_positive_effect_ci_and_replication(self):
        payload = self._base()
        payload["primary"]["delta_stratified_auc_B3c_minus_B2c"] = 0.08
        payload["permutation"]["p_two_sided"] = 0.004
        payload["bootstrap"]["delta_B3c_minus_B2c"] = {"lo": 0.03, "hi": 0.13}
        payload["lofo"]["delta_B3_minus_B2"] = {"mean": 0.02}
        self.assertEqual(experiment.decide(payload)["verdict"], "GO")


class AuditTests(unittest.TestCase):
    def test_attribution_uniqueness_detects_a_shared_k_number(self):
        firm_a = universe.UniverseFirm(key="a", cik="0001", ticker="A", sec_title="A",
                                       sic="3841", sic_description="x",
                                       applicants=[{"applicant_root": "A"}])
        firm_b = universe.UniverseFirm(key="b", cik="0002", ticker="B", sec_title="B",
                                       sic="3841", sic_description="x",
                                       applicants=[{"applicant_root": "B"}])
        build = type("B", (), {"included": [firm_a, firm_b]})()
        records = [{"k_number": "K1", "applicant": "A", "decision_code": "SESE"},
                   {"k_number": "K1", "applicant": "B", "decision_code": "SESE"}]
        out = audit._a4(build, records)
        self.assertFalse(out["passed"])
        self.assertEqual(out["shared_k_numbers"], {"K1": ["0001", "0002"]})


if __name__ == "__main__":
    unittest.main()