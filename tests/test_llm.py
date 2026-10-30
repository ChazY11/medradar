"""Offline tests for the LLM judge: prompt, parsing, caching, budget, sizing."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from medradar.db import DB
from medradar.llm import (
    CachedJudge,
    HeuristicJudge,
    HttpJudge,
    JudgeConfig,
    build_prompt,
    parse_verdict,
)
from medradar.live import LiveParams, size_order

VALID = {
    "direction": 1,
    "materiality": 0.82,
    "confidence": 0.9,
    "catalyst_type": "approval",
    "asset": "Keytruda",
    "indication": "first-line NSCLC",
    "is_pivotal": True,
    "revenue_relevance": "high",
    "evidence_quotes": ["the FDA approved KEYTRUDA for the first-line treatment"],
    "rationale_zh": "一线适应症扩展，商业价值高",
}


class PromptTests(unittest.TestCase):
    def test_prompt_contains_schema_and_is_truncated(self) -> None:
        system, user = build_prompt("headline", "x" * 50_000)
        self.assertIn("evidence_quotes", system)
        self.assertIn("materiality", system)
        self.assertLessEqual(len(user), 24_100)
        self.assertTrue(user.startswith("Headline: headline"))


class ParseTests(unittest.TestCase):
    def test_valid_json(self) -> None:
        verdict = parse_verdict(json.dumps(VALID))
        self.assertEqual(verdict["direction"], 1)
        self.assertEqual(verdict["materiality"], 0.82)
        self.assertEqual(verdict["catalyst_type"], "approval")
        self.assertTrue(verdict["is_pivotal"])

    def test_markdown_fence_is_tolerated(self) -> None:
        verdict = parse_verdict("```json\n" + json.dumps(VALID) + "\n```")
        self.assertEqual(verdict["direction"], 1)

    def test_values_are_clamped_and_unknown_types_normalised(self) -> None:
        payload = dict(VALID, materiality=7, confidence=-3, catalyst_type="moon_landing")
        verdict = parse_verdict(json.dumps(payload))
        self.assertEqual(verdict["materiality"], 1.0)
        self.assertEqual(verdict["confidence"], 0.0)
        self.assertEqual(verdict["catalyst_type"], "other")

    def test_missing_evidence_halves_confidence(self) -> None:
        payload = dict(VALID, evidence_quotes=[])
        verdict = parse_verdict(json.dumps(payload))
        self.assertTrue(verdict["unverified"])
        self.assertAlmostEqual(verdict["confidence"], 0.45)

    def test_garbage_raises(self) -> None:
        with self.assertRaises(ValueError):
            parse_verdict("I think this is probably good.")


class HeuristicTests(unittest.TestCase):
    def test_crl_is_negative(self) -> None:
        verdict = HeuristicJudge().judge("x", "The company received a Complete Response Letter.")
        self.assertEqual(verdict["direction"], -1)
        self.assertEqual(verdict["catalyst_type"], "crl")

    def test_earnings_is_neutral_and_immaterial(self) -> None:
        verdict = HeuristicJudge().judge("x", "Quarterly financial results and earnings call.")
        self.assertEqual(verdict["direction"], 0)
        self.assertLessEqual(verdict["materiality"], 0.2)


class CacheTests(unittest.TestCase):
    class CountingJudge:
        name = "counting"

        def __init__(self) -> None:
            self.calls = 0

        def judge(self, headline: str, text: str) -> dict:
            self.calls += 1
            return dict(VALID)

    def test_second_identical_filing_hits_cache(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with DB(Path(tmp) / "j.sqlite") as db:
                inner = self.CountingJudge()
                judge = CachedJudge(db, inner, budget=5, model="test")
                judge.judge_filing("h", "same text")
                judge.judge_filing("h", "same text")
                self.assertEqual(inner.calls, 1)
                self.assertEqual(judge.cache_hits, 1)

    def test_budget_exhaustion_falls_back_to_heuristic(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with DB(Path(tmp) / "j.sqlite") as db:
                inner = self.CountingJudge()
                judge = CachedJudge(db, inner, budget=1, model="test")
                judge.judge_filing("h", "text one")
                verdict = judge.judge_filing("h", "text two")
                self.assertEqual(inner.calls, 1)
                self.assertIn("budget", verdict["judge"])


class HttpJudgeTests(unittest.TestCase):
    def test_parses_openai_compatible_response(self) -> None:
        response = {
            "choices": [{"message": {"content": json.dumps(VALID)}}]
        }

        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

            def read(self):
                return json.dumps(response).encode()

        with mock.patch("urllib.request.urlopen", return_value=FakeResponse()):
            judge = HttpJudge(JudgeConfig(api_key="k", model="m"))
            verdict = judge.judge("h", "text")
        self.assertEqual(verdict["direction"], 1)
        self.assertEqual(verdict["judge"], "llm:m")


class SizingTests(unittest.TestCase):
    def test_materiality_scales_position(self) -> None:
        params = LiveParams(max_position=0.05, max_track=1.0)
        full = size_order(100_000, 100_000, 100.0, 0.0, params, materiality=1.0)
        half = size_order(100_000, 100_000, 100.0, 0.0, params, materiality=0.5)
        floor = size_order(100_000, 100_000, 100.0, 0.0, params, materiality=0.01)
        self.assertAlmostEqual(full, 50.0)
        self.assertAlmostEqual(half, 25.0)
        self.assertAlmostEqual(floor, 10.0)  # 20% floor, never zero-sized


if __name__ == "__main__":
    unittest.main()
