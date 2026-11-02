"""Tests for b100: promoting the owner-authorised AI review to the study's final adjudication.

The boundary under test: the promotion is only legal because the owner authorised it, the labels stay
`human_truth = false`, no human column is ever filled, and the script refuses to run without the authorisation record
or with a fabricated `Confirmed Shift`.
"""
from __future__ import annotations

import importlib.util
import json
import shutil
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "experiments" / "b100" / "finalise_ai_adjudication.py"
STUDY = ROOT / "research" / "studies" / "early_signal_5firms"
FINAL = STUDY / "ADJUDICATION_FINAL_V1.json"
PACKETS = STUDY / "CASE_PACKETS_FINAL_V1.json"
CANDIDATES = STUDY / "CASE_CANDIDATES_FINAL_V1.json"
AI = STUDY / "AI_REVIEW_ADJUDICATION_V1.json"
AUTH = STUDY / "OWNER_AUTHORISATION_2026-11-03.md"


def load_module():
    spec = importlib.util.spec_from_file_location("b100_finalise", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class FinalAdjudicationTests(unittest.TestCase):
    def setUp(self):
        self.module = load_module()
        self.tmp = Path(tempfile.mkdtemp(prefix="b100-"))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def run_script(self, ai: Path = AI, auth: Path = AUTH) -> int:
        return self.module.main([
            "--ai-adjudication", str(ai),
            "--authorisation", str(auth),
            "--out-final", str(self.tmp / "final.json"),
            "--out-packets", str(self.tmp / "packets.json"),
            "--out-candidates", str(self.tmp / "candidates.json"),
            "--out-md", str(self.tmp / "results.md"),
        ])

    def write_mutated_ai(self, mutate) -> Path:
        payload = json.loads(AI.read_text(encoding="utf-8"))
        mutate(payload)
        path = self.tmp / "ai_mutated.json"
        path.write_text(json.dumps(payload), encoding="utf-8")
        return path

    def test_artifact_carries_the_authorisation_and_the_non_human_status(self):
        data = json.loads(FINAL.read_text(encoding="utf-8"))
        self.assertEqual(data["tier"], "FINAL_ADJUDICATION_AI_OWNER_AUTHORISED")
        self.assertTrue(data["is_final_for_this_study"])
        self.assertFalse(data["human_truth"])
        self.assertTrue(data["human_signoff_waived"])
        self.assertTrue(data["eligible_for_target_b_scoring"])
        self.assertEqual(data["n_packets"], 69)
        self.assertTrue(all(p["human_label"] is None for p in data["packets"]))
        self.assertTrue(all(p["human_truth"] is False for p in data["packets"]))

    def test_target_b_is_negative_with_an_upper_bound(self):
        data = json.loads(FINAL.read_text(encoding="utf-8"))
        result = data["target_b_result"]
        self.assertEqual(result["confirmed_shift_count"], 0)
        self.assertEqual(result["confirmed_shift_rate"], 0.0)
        self.assertGreater(result["confirmed_rate_wilson_upper_95"], 0.04)
        self.assertLess(result["confirmed_rate_wilson_upper_95"], 0.07)
        self.assertEqual(result["false_signal_count"], 8)
        self.assertEqual(len(result["small_sample_false_signals"]), 8)

    def test_merged_files_are_additive_and_labelled(self):
        packets = json.loads(PACKETS.read_text(encoding="utf-8"))
        cases = json.loads(CANDIDATES.read_text(encoding="utf-8"))
        self.assertEqual(packets["packets_with_final_label"], 9)
        self.assertEqual(cases["cases_with_final_label"], 60)
        self.assertEqual(packets["final_adjudication"]["tier"], "FINAL_ADJUDICATION_AI_OWNER_AUTHORISED")
        for packet in packets["packets"]:
            self.assertIsNotNone(packet.get("final_label"))
            self.assertFalse(packet.get("final_label_human_truth"))

    def test_runs_and_writes_all_outputs(self):
        self.assertEqual(self.run_script(), 0)
        for name in ("final.json", "packets.json", "candidates.json", "results.md"):
            self.assertTrue((self.tmp / name).exists(), name)

    def test_refuses_without_authorisation_record(self):
        bad = self.tmp / "no_authorisation.md"
        bad.write_text("some other note without the required phrases", encoding="utf-8")
        self.assertEqual(self.run_script(auth=bad), 2)
        self.assertFalse((self.tmp / "final.json").exists())

    def test_refuses_a_fabricated_confirmed_shift(self):
        def mutate(payload):
            payload["packets"][0]["ai_label"] = "Confirmed Shift"

        self.assertEqual(self.run_script(ai=self.write_mutated_ai(mutate)), 2)
        self.assertFalse((self.tmp / "final.json").exists())

    def test_refuses_to_overwrite_an_existing_human_or_final_label(self):
        def mutate(payload):
            payload["packets"][0]["human_label"] = "Routine Iteration"

        self.assertEqual(self.run_script(ai=self.write_mutated_ai(mutate)), 2)
        self.assertFalse((self.tmp / "final.json").exists())


if __name__ == "__main__":
    unittest.main()
