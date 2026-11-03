"""Tests for b104 publication knowledge-lag sensitivity (pure helpers only)."""
from __future__ import annotations

import importlib.util
import math
import unittest
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "experiments" / "b104_publag" / "publag.py"


def load_module():
    spec = importlib.util.spec_from_file_location("b104_publag", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class QuarterAndLagTests(unittest.TestCase):
    def setUp(self):
        self.module = load_module()

    def test_quarter_end_dates(self):
        self.assertEqual(self.module.quarter_end(2024, 1), date(2024, 3, 31))
        self.assertEqual(self.module.quarter_end(2024, 2), date(2024, 6, 30))
        self.assertEqual(self.module.quarter_end(2024, 3), date(2024, 9, 30))
        self.assertEqual(self.module.quarter_end(2024, 4), date(2024, 12, 31))

    def test_zero_lag_uses_previous_year_from_q1(self):
        usable = self.module.usable_years(2024, 1, 0)
        self.assertIn(2023, usable)
        self.assertNotIn(2024, usable)

    def test_ninety_day_lag_depends_on_leap_year(self):
        # leap year: knowledge(2023) = 2024-01-01 + 90 days = 2024-03-31 = Q1 end -> usable (boundary)
        self.assertIn(2023, self.module.usable_years(2024, 1, 90))
        # non-leap year: knowledge(2024) = 2025-01-01 + 90 days = 2025-04-01 > 2025-03-31 -> not usable
        self.assertNotIn(2024, self.module.usable_years(2025, 1, 90))
        # one more day is never usable at Q1
        self.assertNotIn(2023, self.module.usable_years(2024, 1, 91))

    def test_publication_features_use_the_most_recent_usable_year(self):
        works = {2020: 5, 2021: 10, 2022: 20}
        prev, three, growth = self.module.publication_features(works, 2022)
        self.assertAlmostEqual(prev, math.log1p(20))
        self.assertAlmostEqual(three, math.log1p(5 + 10 + 20))
        self.assertAlmostEqual(growth, 20 / (10 + 0.5))

    def test_missing_previous_year_returns_none_for_three_year_sum_and_growth(self):
        works = {2022: 20}
        prev, three, growth = self.module.publication_features(works, 2022)
        self.assertIsNotNone(prev)
        self.assertIsNone(three)                # 2021 and 2020 are absent
        self.assertIsNone(growth)

    def test_no_usable_year_returns_all_none(self):
        self.assertEqual(self.module.publication_features({}, None), (None, None, None))

    def test_no_numpy_pandas_scipy_import(self):
        text = SCRIPT.read_text(encoding="utf-8")
        for banned in ("import numpy", "import pandas", "import scipy", "from numpy", "from pandas", "from scipy"):
            self.assertNotIn(banned, text)


if __name__ == "__main__":
    unittest.main()
