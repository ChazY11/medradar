"""Tests for snapshot manifests (point-in-time artifact discipline)."""
from __future__ import annotations

import copy
import json
import unittest

from medradar.intelligence.snapshot import (
    MANIFEST_SCHEMA,
    build_manifest,
    canonical_json,
    content_hash,
    hash_bytes,
    is_iso_date,
    verify_manifest,
)

ARTIFACTS = {"profiles": {"a": 1, "b": [1, 2, 3]},
             "summary": {"companies": 5}}


def _manifest(**overrides):
    kwargs = {"as_of": "2026-11-03", "window": ("2016-11", "2026-09"),
              "artifacts": ARTIFACTS,
              "sources": {"data/research.sqlite": "abc123"},
              "notes": ("frozen for B-049",)}
    kwargs.update(overrides)
    return build_manifest(**kwargs)


class CanonicalJsonTest(unittest.TestCase):
    def test_key_order_is_irrelevant(self):
        self.assertEqual(canonical_json({"b": 1, "a": 2}),
                         canonical_json({"a": 2, "b": 1}))

    def test_no_whitespace(self):
        self.assertNotIn(" ", canonical_json({"a": [1, 2]}))

    def test_hash_is_stable_across_key_order(self):
        self.assertEqual(content_hash({"b": 1, "a": 2}), content_hash({"a": 2, "b": 1}))

    def test_different_content_gives_different_hash(self):
        self.assertNotEqual(content_hash({"a": 1}), content_hash({"a": 2}))

    def test_hash_is_hex_sha256(self):
        digest = content_hash({"a": 1})
        self.assertEqual(len(digest), 64)
        int(digest, 16)

    def test_hash_bytes_matches_hashlib_length(self):
        self.assertEqual(len(hash_bytes(b"hello")), 64)


class BuildManifestTest(unittest.TestCase):
    def test_records_every_artifact(self):
        manifest = _manifest()
        self.assertEqual(set(manifest["artifacts"]), set(ARTIFACTS))
        self.assertEqual(manifest["artifact_count"], len(ARTIFACTS))

    def test_records_sources_and_notes(self):
        manifest = _manifest()
        self.assertIn("data/research.sqlite", manifest["sources"])
        self.assertEqual(manifest["notes"], ["frozen for B-049"])

    def test_schema_and_as_of(self):
        manifest = _manifest()
        self.assertEqual(manifest["schema"], MANIFEST_SCHEMA)
        self.assertEqual(manifest["as_of"], "2026-11-03")
        self.assertEqual(manifest["window"], {"start": "2016-11", "end": "2026-09"})

    def test_manifest_hash_present(self):
        manifest = _manifest()
        self.assertEqual(len(manifest["manifest_hash"]), 64)

    def test_bad_as_of_rejected(self):
        with self.assertRaises(ValueError):
            _manifest(as_of="November")

    def test_bad_window_rejected(self):
        with self.assertRaises(ValueError):
            _manifest(window=("2016-11",))

    def test_no_artifacts_rejected(self):
        with self.assertRaises(ValueError):
            _manifest(artifacts={})

    def test_sizes_are_recorded(self):
        manifest = _manifest()
        for name in ARTIFACTS:
            self.assertGreater(manifest["artifact_sizes"][name], 0)


class VerifyManifestTest(unittest.TestCase):
    def test_unchanged_artifacts_verify(self):
        manifest = _manifest()
        self.assertEqual(verify_manifest(manifest, artifacts=ARTIFACTS), [])

    def test_changed_artifact_is_detected(self):
        manifest = _manifest()
        tampered = copy.deepcopy(ARTIFACTS)
        tampered["profiles"]["a"] = 999
        problems = verify_manifest(manifest, artifacts=tampered)
        self.assertTrue(any("hash mismatch for profiles" in problem for problem in problems))

    def test_missing_artifact_is_detected(self):
        manifest = _manifest()
        problems = verify_manifest(manifest, artifacts={"profiles": ARTIFACTS["profiles"]})
        self.assertTrue(any("missing: summary" in problem for problem in problems))

    def test_unrecorded_artifact_is_detected(self):
        manifest = _manifest()
        extra = dict(ARTIFACTS)
        extra["unexpected"] = {"x": 1}
        problems = verify_manifest(manifest, artifacts=extra)
        self.assertTrue(any("not recorded" in problem for problem in problems))

    def test_tampered_manifest_hash_is_detected(self):
        manifest = _manifest()
        manifest["as_of"] = "2027-01-01"
        problems = verify_manifest(manifest, artifacts=ARTIFACTS)
        self.assertTrue(any("manifest hash" in problem for problem in problems))

    def test_manifest_without_sources_is_rejected(self):
        manifest = _manifest()
        manifest["sources"] = {}
        body = {key: value for key, value in manifest.items() if key != "manifest_hash"}
        manifest["manifest_hash"] = content_hash(body)
        problems = verify_manifest(manifest, artifacts=ARTIFACTS)
        self.assertTrue(any("source hashes" in problem for problem in problems))


class IsoDateTest(unittest.TestCase):
    def test_valid(self):
        self.assertTrue(is_iso_date("2026-11-03"))

    def test_rejects_loose_formats(self):
        for value in ("2026-1-3", "26-11-03", "2026/11/03", "", "2026-11-0x"):
            self.assertFalse(is_iso_date(value), value)


class SerialisationTest(unittest.TestCase):
    def test_manifest_is_json_serialisable(self):
        manifest = _manifest()
        round_tripped = json.loads(json.dumps(manifest, sort_keys=True))
        self.assertEqual(verify_manifest(round_tripped, artifacts=ARTIFACTS), [])


if __name__ == "__main__":
    unittest.main()
