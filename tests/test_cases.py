"""Offline tests for the case library: price reactions, evidence, outcomes."""

from __future__ import annotations

import json
import tempfile
import unittest
from datetime import date
from pathlib import Path

from medradar.cases import (
    build_cases,
    extract_evidence,
    load_corpus,
    price_reaction,
    render_markdown,
    _load_price_cache,
    _outcome,
)
from medradar.db import DB


def _series(closes, opens=None, start="2024-01-01"):
    """Business-day series starting 2024-01-01 (a Monday)."""
    from datetime import timedelta

    opens = opens or closes
    rows = []
    day = date.fromisoformat(start)
    index = 0
    while index < len(closes):
        if day.weekday() < 5:
            rows.append({"date": day.isoformat(), "open": opens[index], "close": closes[index]})
            index += 1
        day += timedelta(days=1)
    return rows


class PriceReactionTests(unittest.TestCase):
    def test_entry_is_next_open_and_returns_are_correct(self) -> None:
        stock = _series([100, 101, 102, 103, 104, 110, 111], opens=[100, 100, 101, 102, 103, 104, 110])
        bench = _series([100, 100, 100, 100, 100, 100, 100], opens=[100] * 7)
        result = price_reaction(stock, date(2024, 1, 1), benchmark_series=bench, horizons=(1, 5))
        # entry = 2024-01-02 open (100); +1 session close 102 -> +2%; +5 sessions close 111 -> +11%
        self.assertEqual(result["entry_date"], "2024-01-02")
        self.assertAlmostEqual(result["raw_1d"], 0.02, places=6)
        self.assertAlmostEqual(result["raw_5d"], 0.11, places=6)
        self.assertAlmostEqual(result["abnormal_5d"], 0.11, places=6)

    def test_missing_forward_window_returns_none(self) -> None:
        stock = _series([100, 101], opens=[100, 100])
        result = price_reaction(stock, date(2024, 1, 1), horizons=(20,))
        self.assertIsNone(result.get("raw_20d"))

    def test_no_session_after_signal_returns_empty(self) -> None:
        stock = _series([100], opens=[100])
        self.assertEqual(price_reaction(stock, date(2024, 6, 1)), {})


def _split_price_rows(*, split: bool) -> list[dict[str, object]]:
    """25 business days from 2024-01-01; a 2:1 split is effective 2024-01-03.

    Pre-split raw quotes are 2x the post-split basis and ``adj_close`` is
    split-adjusted (raw 100 -> adjusted 50), which is exactly how Yahoo ships
    history. The true post-entry return is +10% (adjusted 50 -> 55) with or
    without the split.
    """
    rows: list[dict[str, object]] = []
    day = date(2024, 1, 1)
    index = 0
    while index < 25:
        if day.weekday() < 5:
            pre_split = split and day < date(2024, 1, 3)
            adjusted_close = 50.0 if index <= 1 else 55.0
            raw_close = adjusted_close * 2 if pre_split else adjusted_close
            rows.append({
                "ticker": "ACME", "date": day.isoformat(), "open": raw_close,
                "high": raw_close, "low": raw_close, "close": raw_close,
                "adj_close": adjusted_close, "volume": 1000,
            })
            index += 1
        day = date.fromordinal(day.toordinal() + 1)
    return rows


def _benchmark_rows() -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    day = date(2024, 1, 1)
    index = 0
    while index < 25:
        if day.weekday() < 5:
            rows.append({
                "ticker": "SPY", "date": day.isoformat(), "open": 100.0,
                "high": 100.0, "low": 100.0, "close": 100.0,
                "adj_close": 100.0, "volume": 1000,
            })
            index += 1
        day = date.fromordinal(day.toordinal() + 1)
    return rows


class PriceBasisSplitTests(unittest.TestCase):
    """Regression: entry uses adjusted_open, not the raw open (audit B4)."""

    def _cache(self, tmp: str, *, split: bool) -> dict:
        name = "split.sqlite" if split else "plain.sqlite"
        with DB(Path(tmp) / name) as db:
            db.upsert_prices(_split_price_rows(split=split) + _benchmark_rows())
            return _load_price_cache(db, "SPY")

    def test_two_for_one_split_is_not_fake_alpha(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            split_cache = self._cache(tmp, split=True)
            plain_cache = self._cache(tmp, split=False)
        split_result = price_reaction(
            split_cache["ACME"], date(2024, 1, 1),
            benchmark_series=split_cache["SPY"], horizons=(1, 5),
        )
        plain_result = price_reaction(
            plain_cache["ACME"], date(2024, 1, 1),
            benchmark_series=plain_cache["SPY"], horizons=(1, 5),
        )
        # Entry day raw open is 100 pre-split -> 50 on the adjusted-close basis.
        self.assertAlmostEqual(split_result["entry_price"], 50.0, places=4)
        self.assertAlmostEqual(split_result["raw_1d"], 0.10, places=6)
        self.assertAlmostEqual(split_result["abnormal_1d"], 0.10, places=6)
        # The same price path with and without a 2:1 split must give the same alpha.
        self.assertAlmostEqual(split_result["raw_1d"], plain_result["raw_1d"], places=6)
        self.assertAlmostEqual(split_result["abnormal_1d"], plain_result["abnormal_1d"], places=6)
        self.assertAlmostEqual(split_result["abnormal_5d"], plain_result["abnormal_5d"], places=6)


class OutcomeTests(unittest.TestCase):
    def test_outcome_thresholds(self) -> None:
        self.assertEqual(_outcome(1, 0.05), "hit")
        self.assertEqual(_outcome(1, -0.05), "miss")
        self.assertEqual(_outcome(1, 0.0), "mixed")
        self.assertEqual(_outcome(-1, -0.05), "hit")
        self.assertEqual(_outcome(-1, 0.05), "miss")
        self.assertEqual(_outcome(1, None), "unknown")


class EvidenceTests(unittest.TestCase):
    def test_evidence_is_verbatim(self) -> None:
        text = "Item 8.01. The FDA approved Ohtuvayre for COPD. Revenue rose 12%. Approved."
        quotes = extract_evidence(text, (r"fda approved",))
        self.assertEqual(len(quotes), 1)
        self.assertIn("FDA approved Ohtuvayre", quotes[0])

    def test_empty_text(self) -> None:
        self.assertEqual(extract_evidence("", (r"x",)), [])


class CorpusTests(unittest.TestCase):
    def test_load_corpus_skips_bad_lines(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "corpus.jsonl"
            path.write_text(
                json.dumps({"accession": "a", "text": "abc"}) + "\n"
                + "not json\n"
                + json.dumps({"accession": "b"}) + "\n",
                encoding="utf-8",
            )
            items = load_corpus(path)
            self.assertEqual(len(items), 1)
            self.assertEqual(items[0]["accession"], "a")

    def test_build_cases_end_to_end(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "cases.sqlite"
            db = DB(db_path)
            # prices: signal on 2024-01-01, entry 01-02 open 100, 20d close 112
            closes = [100] * 2 + [100, 101, 102, 103, 104, 105, 106, 107, 108, 109,
                                  110, 111, 112, 113, 114, 115, 116, 117, 118, 119]
            rows = []
            day = date(2024, 1, 1)
            index = 0
            while index < len(closes):
                if day.weekday() < 5:
                    rows.append({"ticker": "ACME", "date": day.isoformat(), "open": 100.0,
                                 "high": 100.0, "low": 100.0, "close": closes[index],
                                 "adj_close": closes[index], "volume": 1000})
                    index += 1
                day = date.fromordinal(day.toordinal() + 1)
            bench = []
            day = date(2024, 1, 1)
            for _ in range(25):
                if day.weekday() < 5:
                    bench.append({"ticker": "SPY", "date": day.isoformat(), "open": 100.0,
                                  "high": 100.0, "low": 100.0, "close": 100.0,
                                  "adj_close": 100.0, "volume": 1000})
                day = date.fromordinal(day.toordinal() + 1)
            db.upsert_prices(rows + bench)
            db.upsert_companies([{"key": "acme", "name_zh": "Acme", "ticker": "ACME", "sector": "device"}])
            db.close()

            corpus = Path(tmp) / "corpus.jsonl"
            corpus.write_text(
                json.dumps(
                    {
                        "accession": "0001", "ticker": "ACME", "company": "Acme",
                        "company_zh": "Acme", "company_key": "acme", "filed": "2024-01-01",
                        "category": "approval", "headline": "FDA approves drug",
                        "url": "https://www.sec.gov/x", "text": "The FDA approved the product in January.",
                    }
                ) + "\n",
                encoding="utf-8",
            )
            with DB(db_path) as db:
                result = build_cases(db, corpus_path=corpus, max_cases=10)
            self.assertEqual(result["status"], "ok")
            self.assertEqual(len(result["selected"]), 1)
            case = result["selected"][0]
            self.assertEqual(case["ticker"], "ACME")
            self.assertTrue(case["evidence_quotes"])
            self.assertIsNotNone(case["price_20d"])
            self.assertIn("案例库", render_markdown(result))

    def test_empty_corpus_returns_insufficient(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with DB(Path(tmp) / "empty.sqlite") as db:
                result = build_cases(db, corpus_path=Path(tmp) / "missing.jsonl")
            self.assertEqual(result["status"], "insufficient_data")


class EventStudySummaryTests(unittest.TestCase):
    def test_aggregates_by_category_with_ci(self) -> None:
        from medradar.cases import event_study_summary

        cases = {
            "selected": [
                {"category": "approval", "date": f"2024-0{month}-01", "price_20d": value}
                for month, value in zip(range(1, 7), (0.02, 0.03, 0.05, 0.01, 0.04, 0.06))
            ]
        }
        summary = event_study_summary(cases, horizons=(20,))
        block = summary["by_horizon"]["20"]["categories"]["approval"]
        self.assertEqual(block["n"], 6)
        # winsorised at the 2.5/97.5 percentile; median is the robust centre
        self.assertAlmostEqual(block["median"], 0.035, places=6)
        self.assertGreater(block["mean"], 0.02)
        self.assertLess(block["median"], block["p90"])
        self.assertLess(block["ci95"][0], block["ci95"][1])
        self.assertIn("multiple_testing", summary["by_horizon"]["20"])

    def test_small_category_is_skipped(self) -> None:
        from medradar.cases import event_study_summary

        cases = {"selected": [{"category": "crl", "date": "2024-01-01", "price_20d": -0.1}]}
        summary = event_study_summary(cases, horizons=(20,))
        self.assertNotIn("crl", summary["by_horizon"]["20"]["categories"])

    def test_empty_cases(self) -> None:
        from medradar.cases import event_study_summary

        self.assertEqual(event_study_summary({"selected": []}), {})


if __name__ == "__main__":
    unittest.main()
