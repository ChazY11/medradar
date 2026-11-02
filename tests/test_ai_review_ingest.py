"""Tests for the external-AI-review ingester (b099).

The ingester is the boundary that keeps a non-human labelling out of the study's human tier.  These tests assert the
boundary: it accepts the delivered review only while every human field is empty and the review says it is non-human,
and it refuses (exit 2, no output written) when the boundary is violated or the review is malformed.
"""
from __future__ import annotations

import csv
import importlib.util
import json
import shutil
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "experiments" / "b099" / "ingest_external_ai_review.py"
STUDY = ROOT / "research" / "studies" / "early_signal_5firms"
WORKSHEET = STUDY / "external_ai_review_2026-11-03" / "AI_REVIEW_WORKSHEET.csv"
REVIEW_JSON = STUDY / "external_ai_review_2026-11-03" / "AI_REVIEW_69.json"
HUMAN = STUDY / "HUMAN_REVIEW_WORKSHEET.csv"
AGENT = STUDY / "ADJUDICATION_AGENT_V1.json"
ARTIFACT = STUDY / "AI_REVIEW_ADJUDICATION_V1.json"


def load_module():
    spec = importlib.util.spec_from_file_location("b099_ingest", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class IngesterBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.module = load_module()
        self.tmp = Path(tempfile.mkdtemp(prefix="b099-"))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def run_ingester(self, worksheet: Path, out: Path, review: Path = REVIEW_JSON) -> int:
        return self.module.main([
            "--worksheet", str(worksheet),
            "--review-json", str(review),
            "--human-worksheet", str(HUMAN),
            "--agent", str(AGENT),
            "--out", str(out),
        ])

    def mutated_worksheet(self, mutate) -> Path:
        rows = list(csv.DictReader(open(WORKSHEET, encoding="utf-8-sig", newline="")))
        mutate(rows)
        target = self.tmp / "mutated.csv"
        with open(target, "w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
        return target

    def test_artifact_records_non_human_boundary(self):
        data = json.loads(ARTIFACT.read_text(encoding="utf-8"))
        self.assertEqual(data["tier"], "EXTERNAL_AI_REVIEW")
        self.assertFalse(data["can_count_as_human_truth"])
        self.assertFalse(data["eligible_for_target_b_scoring"])
        self.assertEqual(data["authority"], "AI_ONLY_NOT_HUMAN_GOLD_STANDARD")
        self.assertEqual(len(data["packets"]), 69)
        self.assertTrue(all(row["human_label"] is None for row in data["packets"]))
        self.assertTrue(all(row["final_label"] is None for row in data["packets"]))
        self.assertEqual(sum(data["label_distribution"].values()), 69)
        self.assertNotIn("Confirmed Shift", data["label_distribution"])

    def test_halt_rule_fires_and_lead_time_withdrawn(self):
        data = json.loads(ARTIFACT.read_text(encoding="utf-8"))
        decision = data["decision"]
        self.assertTrue(decision["halt_rule"]["triggered"])
        self.assertEqual(decision["halt_rule"]["confirmed_shift_labels"], 0)
        self.assertEqual(len(decision["small_sample_lead_time"]["false_signal_pairs"]), 8)
        self.assertEqual(decision["small_sample_lead_time"]["uncertain_pairs"], ["LT-01"])

    def test_accepts_the_delivered_review_and_writes(self):
        out = self.tmp / "artifact.json"
        self.assertEqual(self.run_ingester(WORKSHEET, out), 0)
        written = json.loads(out.read_text(encoding="utf-8"))
        self.assertEqual(len(written["packets"]), 69)

    def test_refuses_when_a_human_field_is_filled(self):
        def mutate(rows):
            rows[0]["reviewer"] = "Some Person"

        out = self.tmp / "artifact.json"
        self.assertEqual(self.run_ingester(self.mutated_worksheet(mutate), out), 2)
        self.assertFalse(out.exists())

    def test_refuses_out_of_vocabulary_label(self):
        def mutate(rows):
            rows[0]["ai_label"] = "Definitely A Shift"

        out = self.tmp / "artifact.json"
        self.assertEqual(self.run_ingester(self.mutated_worksheet(mutate), out), 2)
        self.assertFalse(out.exists())

    def test_refuses_label_disagreement_between_csv_and_json(self):
        review = json.loads(REVIEW_JSON.read_text(encoding="utf-8"))
        review["rows"][0]["ai_label"] = "False Signal / No Confirmed Shift"
        mutated_review = self.tmp / "review.json"
        mutated_review.write_text(json.dumps(review), encoding="utf-8")

        out = self.tmp / "artifact.json"
        self.assertEqual(self.run_ingester(WORKSHEET, out, review=mutated_review), 2)
        self.assertFalse(out.exists())

    def test_refuses_when_reviewer_is_human(self):
        def mutate(rows):
            rows[0]["ai_reviewer"] = "Dr. Real Person"

        out = self.tmp / "artifact.json"
        self.assertEqual(self.run_ingester(self.mutated_worksheet(mutate), out), 2)
        self.assertFalse(out.exists())


if __name__ == "__main__":
    unittest.main()
