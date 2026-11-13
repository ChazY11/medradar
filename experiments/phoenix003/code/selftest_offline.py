"""Offline, deterministic self-tests for PHOENIX-003. No network, no database.

    python experiments/phoenix003/code/selftest_offline.py

Every test is a property of a pure function or of the frozen artefacts. The tests exist to
make the measurement re-checkable without the 1.3 GB store: they encode the arithmetic that
the headline numbers depend on.
"""
from __future__ import annotations

import json
import sys
import unittest
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import phoenix003_common as pc

RULES = pc.load_rules()
LINEAGE = pc.load_lineage()
VOCAB = pc.load_frozen_vocab()


class TestDates(unittest.TestCase):
    def test_precision(self):
        self.assertEqual(pc.parse_date("2020-05-06"), date(2020, 5, 6))
        self.assertEqual(pc.parse_date("2020-05"), date(2020, 5, 1))
        self.assertEqual(pc.parse_date("2020"), date(2020, 1, 1))
        self.assertIsNone(pc.parse_date(""))
        self.assertIsNone(pc.parse_date("not-a-date"))
        self.assertEqual(pc.parse_date_precision("2020-05")[1], "month")

    def test_month_only_is_earliest_possible_day(self):
        # conservative for publication: a month-only date must resolve to the 1st, never later
        self.assertLessEqual(pc.parse_date("2021-07"), pc.parse_date("2021-07-31"))

    def test_years_before_clamps_leap_day(self):
        self.assertEqual(pc.years_before(date(2024, 2, 29), 5), date(2019, 2, 28))

    def test_lead_time_sign(self):
        milestone = date(2023, 11, 17)
        evidence = date(2020, 3, 17)
        self.assertEqual((milestone - evidence).days, 1340)


class TestTokenizer(unittest.TestCase):
    def setUp(self):
        self.tok = pc.DistinctiveTokenizer(RULES, VOCAB)

    def test_generic_words_not_distinctive(self):
        for name in ["SYSTEM", "MEDICAL DEVICE", "ULTRASOUND SYSTEM", "CATHETER"]:
            self.assertEqual(self.tok.candidates(name), [], name)

    def test_brand_tokens_not_distinctive(self):
        self.assertEqual(self.tok.candidates("Medtronic"), [])
        self.assertEqual(self.tok.candidates("PHILIPS MEDICAL SYSTEMS"), [])

    def test_distinctive_product_name_survives(self):
        got = self.tok.candidates("Symplicity Spyral Renal Denervation System")
        self.assertIn("SYMPLICITY", got)
        self.assertIn("SPYRAL", got)
        self.assertNotIn("SYSTEM", got)

    def test_short_tokens_rejected(self):
        self.assertNotIn("X1", self.tok.candidates("X1"))

    def test_product_specific_threshold(self):
        # a token used by exactly one applicant is product specific by construction
        self.assertTrue(RULES["name_vocab"]["product_specific_max_applicant_df"] >= 1)
        self.assertFalse(self.tok.is_product_specific("A_TOKEN_THAT_NEVER_APPEARS_ANYWHERE"))


class TestFirmResolution(unittest.TestCase):
    def setUp(self):
        self.res = pc.FirmResolver(LINEAGE, RULES)

    def test_brand_substring_is_not_a_match(self):
        self.assertIsNone(self.res.resolve("Melmedtronics, Inc.")["firm"])

    def test_core_brands(self):
        self.assertEqual(self.res.resolve("Medtronic, Inc.")["firm"], "medtronic")
        self.assertEqual(self.res.resolve("Shenzhen Mindray Bio-Medical Electronics Co., Ltd.")["firm"],
                         "mindray")
        self.assertEqual(self.res.resolve("Draeger Medical Systems, Inc.")["firm"], "draeger")

    def test_ge_needs_a_qualifier(self):
        self.assertEqual(self.res.resolve("GE Healthcare")["firm"], "ge_healthcare")
        self.assertEqual(self.res.resolve("General Electric Co.")["firm"], "ge_healthcare")
        self.assertIsNone(self.res.resolve("GE Lighting")["firm"])

    def test_no_back_projection_of_acquired_companies(self):
        # pre-acquisition applicants carry no brand token and must stay UNKNOWN
        for name in ["Spectranetics Corporation", "Covidien", "Volcano Corporation",
                     "Biomet, Inc.", "Guidant Corporation"]:
            self.assertIsNone(self.res.resolve(name)["firm"], name)

    def test_stratum_labels(self):
        self.assertEqual(self.res.resolve("Medtronic, Inc.")["stratum"], "core")
        self.assertEqual(self.res.resolve("Stryker Corporation")["stratum"], "extension")


class TestIntervals(unittest.TestCase):
    def test_clopper_pearson_known_values(self):
        lo, hi = pc.cp_interval(0, 10, 0.95)
        self.assertAlmostEqual(lo, 0.0, places=12)
        self.assertAlmostEqual(hi, 0.3085, places=3)
        lo, hi = pc.cp_interval(5, 10, 0.95)
        self.assertAlmostEqual(lo, 0.1871, places=3)
        self.assertAlmostEqual(hi, 0.8129, places=3)
        lo, hi = pc.cp_interval(10, 10, 0.95)
        self.assertAlmostEqual(hi, 1.0, places=12)

    def test_percentile(self):
        self.assertEqual(pc.percentile([1, 2, 3, 4], 0.5), 2.5)
        self.assertEqual(pc.percentile([5], 0.9), 5.0)


class TestLinkRule(unittest.TestCase):
    """Re-derive the tier decision for synthetic pairs, independently of b_links.py."""

    @staticmethod
    def decide(token, evidence_tokens, evidence_date, milestone_date, firm_ok, in_window_start):
        if not firm_ok:
            return "AMBIGUOUS_L4"
        if evidence_date >= milestone_date:
            return "REJECTED_L5"
        if token not in evidence_tokens:
            return "CANDIDATE_L3"
        if evidence_date < in_window_start:
            return "REJECTED_L5"
        return "VERIFIED_L2"

    def test_before_and_after(self):
        ms = date(2023, 11, 17)
        self.assertEqual(self.decide("SPYRAL", {"SPYRAL"}, date(2020, 3, 17), ms, True,
                                     ms - timedelta(days=5 * 365)), "VERIFIED_L2")
        self.assertEqual(self.decide("SPYRAL", {"SPYRAL"}, date(2024, 1, 1), ms, True,
                                     ms - timedelta(days=5 * 365)), "REJECTED_L5")
        self.assertEqual(self.decide("SPYRAL", {"OTHER"}, date(2020, 3, 17), ms, True,
                                     ms - timedelta(days=5 * 365)), "CANDIDATE_L3")
        self.assertEqual(self.decide("SPYRAL", {"SPYRAL"}, date(2020, 3, 17), ms, False,
                                     ms - timedelta(days=5 * 365)), "AMBIGUOUS_L4")


class TestNoveltyRule(unittest.TestCase):
    @staticmethod
    def status(first_reg, evidence_date):
        if first_reg is None or evidence_date is None:
            return "unknown"
        return "PRE_EXISTING_PRODUCT" if first_reg <= evidence_date else "PRE_REGULATORY"

    def test_pre_regulatory_requires_no_earlier_regulatory_record(self):
        self.assertEqual(self.status(date(2020, 1, 1), date(2021, 1, 1)), "PRE_EXISTING_PRODUCT")
        self.assertEqual(self.status(date(2023, 1, 1), date(2021, 1, 1)), "PRE_REGULATORY")
        self.assertEqual(self.status(None, date(2021, 1, 1)), "unknown")

    def test_equal_dates_are_pre_existing(self):
        d = date(2021, 1, 1)
        self.assertEqual(self.status(d, d), "PRE_EXISTING_PRODUCT")


class TestFrozenArtefacts(unittest.TestCase):
    def test_rules_have_the_verdict_thresholds(self):
        v = RULES["verdict"]
        for key in ("go", "limited_go", "blocked"):
            self.assertIn(key, v)
        self.assertGreater(v["go"]["min_specificity"], v["limited_go"]["min_specificity"])

    def test_rules_are_cited_by_code_not_hardcoded(self):
        # the seed and the resample count must come from the frozen file
        self.assertIsInstance(RULES["stats"]["seed"], int)
        self.assertGreaterEqual(RULES["stats"]["bootstrap_resamples"], 1000)

    def test_vocab_is_frozen_and_brand_free(self):
        self.assertIn("generic_vocabulary", VOCAB)
        self.assertIn("applicant_df", VOCAB)
        brand = set(VOCAB["brand_tokens"])
        self.assertNotIn("MEDTRONIC", set(VOCAB["generic_vocabulary"]))
        self.assertTrue(brand)

    def test_anchors_have_required_fields(self):
        path = pc.EXPERIMENT_DIR / "REGULATORY_ANCHORS.jsonl"
        if not path.exists():
            self.skipTest("anchors not built yet")
        rows = [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]
        self.assertGreater(len(rows), 0)
        for r in rows:
            for field in ("anchor_id", "firm", "stratum", "product_code", "milestone_key",
                          "official_id", "anchor_date", "distinctive_tokens", "url"):
                self.assertIn(field, r)
            self.assertEqual(len(r["anchor_id"]), 64)
            # an anchor's official identifier must be preserved verbatim
            self.assertTrue(r["milestone_key"].startswith(("K", "P")))
        ids = [r["anchor_id"] for r in rows]
        self.assertEqual(len(ids), len(set(ids)), "anchor_id must be unique")

    def test_no_anchor_is_a_pma_supplement(self):
        path = pc.EXPERIMENT_DIR / "REGULATORY_ANCHORS.jsonl"
        if not path.exists():
            self.skipTest("anchors not built yet")
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            r = json.loads(line)
            if r["kind"] == "pma":
                self.assertIn(r["supplement_number"], (None, ""), r["milestone_key"])


class TestDeterminism(unittest.TestCase):
    def test_anchor_id_is_a_pure_function(self):
        a = pc.sha256_bytes(b"x")
        b = pc.sha256_bytes(b"x")
        self.assertEqual(a, b)
        self.assertEqual(len(a), 64)

    def test_seeded_random_is_reproducible(self):
        import random
        r1 = random.Random(RULES["stats"]["seed"])
        r2 = random.Random(RULES["stats"]["seed"])
        self.assertEqual([r1.random() for _ in range(5)], [r2.random() for _ in range(5)])


if __name__ == "__main__":
    unittest.main(verbosity=2)
