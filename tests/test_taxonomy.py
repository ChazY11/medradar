"""Tests for the versioned taxonomy regime (B-032)."""
from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from medradar.intelligence import taxonomy


class FingerprintTest(unittest.TestCase):
    def test_fingerprint_is_a_sha256_of_the_file(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "map.json"
            path.write_text('{"A": "cardiac_rhythm"}', encoding="utf-8")
            expected = hashlib.sha256(path.read_bytes()).hexdigest()
            self.assertEqual(taxonomy.code_map_fingerprint(path), expected)

    def test_edited_map_changes_the_fingerprint(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "map.json"
            path.write_text('{"A": "cardiac_rhythm"}', encoding="utf-8")
            before = taxonomy.code_map_fingerprint(path)
            path.write_text('{"A": "coronary"}', encoding="utf-8")
            self.assertNotEqual(before, taxonomy.code_map_fingerprint(path))

    def test_committed_maps_are_present_and_hashed(self):
        regime = taxonomy.regime()
        self.assertEqual(len(regime["code_map_fingerprint"]), 64)
        self.assertEqual(len(regime["track_list_fingerprint"]), 64)


class RegimeTest(unittest.TestCase):
    def test_version_and_effective_date_are_declared(self):
        regime = taxonomy.regime()
        self.assertEqual(regime["version"], taxonomy.TAXONOMY_VERSION)
        self.assertEqual(regime["effective_from"], taxonomy.EFFECTIVE_FROM)
        self.assertRegex(regime["effective_from"], r"^\d{4}-\d{2}-\d{2}$")


class StampTest(unittest.TestCase):
    def test_stamp_adds_a_taxonomy_block_without_mutating_input(self):
        payload = {"profiles": {"a": 1}}
        stamped = taxonomy.stamp(payload)
        self.assertIn("taxonomy", stamped)
        self.assertNotIn("taxonomy", payload)
        self.assertEqual(stamped["profiles"], payload["profiles"])

    def test_stamp_is_json_serialisable(self):
        self.assertIsInstance(json.dumps(taxonomy.stamp({"x": 1})), str)


class CompareTest(unittest.TestCase):
    def test_absent_record_is_reported_as_unstated(self):
        result = taxonomy.compare(None)
        self.assertEqual(result["comparability"], "unstated")

    def test_identical_regime_is_comparable(self):
        recorded = taxonomy.regime()
        result = taxonomy.compare(recorded)
        self.assertEqual(result["comparability"], "same regime")
        self.assertFalse(taxonomy.regime_changed(recorded))

    def test_changed_code_map_is_flagged(self):
        recorded = dict(taxonomy.regime())
        recorded["code_map_fingerprint"] = "0" * 64
        self.assertTrue(taxonomy.regime_changed(recorded))
        self.assertEqual(taxonomy.compare(recorded)["comparability"], "regime changed")

    def test_changed_track_list_is_flagged(self):
        recorded = dict(taxonomy.regime())
        recorded["track_list_fingerprint"] = "f" * 64
        self.assertTrue(taxonomy.regime_changed(recorded))


if __name__ == "__main__":
    unittest.main()
