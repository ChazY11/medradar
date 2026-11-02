"""Tests for the deterministic therapy-area -> device-track crosswalk."""
from __future__ import annotations

import json
import unittest

from medradar.studies.crosswalk import (
    assign_device_track,
    coverage,
    load_keywords,
    normalise,
)

KEYWORDS = {
    "imaging_us": ["ULTRASOUND", "ECHOCARDIOGRAPHY", "DOPPLER"],
    "cardiac_rhythm": ["PACEMAKER", "DEFIBRILLATOR", "CARDIAC RESYNCHRONIZATION"],
    "respiratory": ["MECHANICAL VENTILATION", "RESPIRATORY FAILURE", "VENTILATOR"],
}


class NormaliseTest(unittest.TestCase):
    def test_punctuation_is_collapsed(self):
        self.assertEqual(normalise("Heart-failure, device (implant)").strip(),
                         "HEART FAILURE DEVICE IMPLANT")

    def test_none_is_empty(self):
        self.assertEqual(normalise(None), "")


class LoadKeywordsTest(unittest.TestCase):
    def test_short_keywords_are_dropped(self):
        rows = [("t", json.dumps(["COIL", "ULTRASOUND"]))]
        self.assertEqual(load_keywords(rows), {"t": ["ULTRASOUND"]})

    def test_bad_json_is_tolerated(self):
        self.assertEqual(load_keywords([("t", "not json")]), {})


class AssignTest(unittest.TestCase):
    def test_single_track_wins(self):
        result = assign_device_track("Ultrasound imaging of the heart", KEYWORDS)
        self.assertEqual(result["status"], "assigned")
        self.assertEqual(result["track"], "imaging_us")
        self.assertIn("ULTRASOUND", result["matched"])

    def test_tie_is_ambiguous_and_unassigned(self):
        keywords = {"a": ["SHARED TERM"], "b": ["SHARED TERM"]}
        result = assign_device_track("shared term in text", keywords)
        self.assertEqual(result["status"], "ambiguous")
        self.assertIsNone(result["track"])
        self.assertEqual(set(result["tied"]), {"a", "b"})

    def test_more_matches_beats_a_tie(self):
        keywords = {"a": ["ULTRASOUND", "DOPPLER"], "b": ["ULTRASOUND"]}
        result = assign_device_track("ultrasound with doppler flow", keywords)
        self.assertEqual(result["track"], "a")

    def test_no_match(self):
        self.assertEqual(assign_device_track("oncology chemotherapy", KEYWORDS)["status"], "no_match")

    def test_empty_text(self):
        self.assertEqual(assign_device_track("", KEYWORDS)["status"], "no_match")


class CoverageTest(unittest.TestCase):
    def test_shares_and_denominators(self):
        summary = coverage([{"status": "assigned"}, {"status": "no_match"},
                            {"status": "ambiguous"}, {"status": "assigned"}])
        self.assertEqual(summary["total"], 4)
        self.assertEqual(summary["assigned"], 2)
        self.assertEqual(summary["assigned_share"], 0.5)

    def test_empty_input(self):
        self.assertIsNone(coverage([])["assigned_share"])


if __name__ == "__main__":
    unittest.main()
