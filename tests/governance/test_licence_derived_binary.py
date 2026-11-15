"""Counter-example tests for the narrowed derived-binary allowlist (GOV-0005).

Each counter-example exercises the same pure judges used by
``tools/governance/check_licence.py`` (or ``check_tree`` where inventory
coverage is the subject) and asserts a hard failure whose reason names the
failed condition. Bytes are fabricated in memory; the only committed files
read are the PRODUCT-001 snapshot artifacts.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from . import gitfix
from tools.governance import check_licence

SNAPSHOT_DIR = gitfix.REPO_ROOT / "medradar/product/snapshot"
ALLOWED_PATH = "medradar/product/snapshot/events.jsonl.gz"
SNAPSHOT_FILES = ("applicants.jsonl.gz", "classifications.jsonl.gz", "events.jsonl.gz")


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _gzip(data: bytes = b'{"event_id": "synthetic"}\n') -> bytes:
    return gzip.compress(data, mtime=0)


def _policy_document(**overrides) -> dict:
    allowlist = {
        "enabled": True,
        "require_sha256": True,
        "require_may_redistribute": True,
        "allowed_source_ids": ["openfda_device"],
        "allowed_paths": ["medradar/product/snapshot/*.gz"],
        "allowed_content_kinds": ["gzip"],
        "max_bytes": 33554432,
        "reason": "test-only allowlist",
    }
    allowlist.update(overrides)
    return {
        "policy": {"derived_binary_allowlist": allowlist},
        "sources": [
            {"source_id": "openfda_device", "status": "GREEN", "may_redistribute": True},
            {
                "source_id": "medradar_derived_artifacts",
                "status": "GREEN",
                "may_redistribute": True,
            },
            {"source_id": "amber_source", "status": "AMBER", "may_redistribute": False},
            {"source_id": "red_source", "status": "RED", "may_redistribute": False},
        ],
    }


def _policy(**overrides):
    report = check_licence.common.Report("test")
    return check_licence.Policy(_policy_document(**overrides), report), report


def _entry(
    data: bytes,
    *,
    path: str = ALLOWED_PATH,
    source_id: str = "openfda_device",
    status: str = "GREEN",
    sha256: str | None = None,
) -> dict:
    return {
        "path": path,
        "source_id": source_id,
        "status": status,
        "content": "gzip",
        "synthetic": False,
        "sha256": _sha256(data) if sha256 is None else sha256,
    }


class DerivedBinaryCounterexampleTests(unittest.TestCase):
    def assert_rejected(self, data: bytes, entry: dict, policy, *needles: str) -> None:
        allowed, why = check_licence._declared_derived_binary(
            entry, data, policy, entry["path"]
        )
        self.assertFalse(allowed, why)
        for needle in needles:
            self.assertIn(needle, why)

    def test_sha256_mismatch_fails(self):
        original = _gzip(b'{"event_id": "original"}\n')
        replaced = _gzip(b'{"event_id": "replaced"}\n')
        self.assert_rejected(
            replaced, _entry(original), _policy()[0], "sha256 mismatch"
        )

    def test_gzip_attributed_to_other_green_source_fails(self):
        data = _gzip()
        self.assert_rejected(
            data,
            _entry(data, source_id="medradar_derived_artifacts"),
            _policy()[0],
            "allowed_source_ids",
        )

    def test_elf_zip_sqlite_parquet_hdf5_content_fails_even_with_sha256(self):
        cases = {
            "elf": b"\x7fELFrest",
            "zip": b"PK\x03\x04rest",
            "sqlite": b"SQLite format 3\x00rest",
            "parquet": b"PAR1rest",
            "hdf5": b"\x89HDF\r\n\x1a\nrest",
        }
        policy, _ = _policy()
        for kind, data in cases.items():
            with self.subTest(kind=kind):
                self.assert_rejected(data, _entry(data), policy, "content kind")
        # Even a policy that explicitly lists the forbidden kind cannot open it.
        for kind, data in cases.items():
            with self.subTest(kind=kind, policy_lists_kind=True):
                policy, _ = _policy(
                    allowed_content_kinds=[kind],
                    allowed_paths=["medradar/product/snapshot/*"],
                )
                self.assert_rejected(
                    data,
                    _entry(data, path="medradar/product/snapshot/sample"),
                    policy,
                    "never allowed",
                )

    def test_gzip_outside_allowed_path_fails(self):
        data = _gzip()
        self.assert_rejected(
            data,
            _entry(data, path="docs/data.gz"),
            _policy()[0],
            "allowed_paths",
        )

    def test_gzip_with_inconsistent_extension_fails(self):
        data = _gzip()
        # The path matches the allowlist glob, so only the extension/content
        # consistency rule can reject it.
        policy, _ = _policy(allowed_paths=["medradar/product/snapshot/*"])
        self.assert_rejected(
            data,
            _entry(data, path="medradar/product/snapshot/events.jsonl"),
            policy,
            "extension",
        )

    def test_oversized_gzip_fails(self):
        data = _gzip(b"x" * 1024)
        policy, _ = _policy(max_bytes=len(data) - 1)
        self.assert_rejected(data, _entry(data), policy, "max_bytes")

    def test_allowlist_disabled_fails(self):
        data = _gzip()
        policy, _ = _policy(enabled=False)
        self.assert_rejected(data, _entry(data), policy, "disabled")

    def test_missing_or_empty_scope_keys_fail_closed(self):
        data = _gzip()
        with self.subTest(key="enabled", state="missing"):
            document = _policy_document()
            document["policy"]["derived_binary_allowlist"].pop("enabled")
            policy = check_licence.Policy(
                document, check_licence.common.Report("test")
            )
            self.assert_rejected(data, _entry(data), policy, "disabled")
        for key in (
            "allowed_source_ids",
            "allowed_paths",
            "allowed_content_kinds",
            "max_bytes",
        ):
            with self.subTest(key=key, state="missing"):
                document = _policy_document()
                document["policy"]["derived_binary_allowlist"].pop(key)
                policy = check_licence.Policy(
                    document, check_licence.common.Report("test")
                )
                self.assert_rejected(data, _entry(data), policy, key)
            with self.subTest(key=key, state="empty"):
                empty = 0 if key == "max_bytes" else []
                policy, _ = _policy(**{key: empty})
                self.assert_rejected(data, _entry(data), policy, key)

    def test_amber_and_red_sources_keep_failing(self):
        data = _gzip()
        for status in ("AMBER", "RED"):
            with self.subTest(status=status):
                self.assert_rejected(
                    data, _entry(data, status=status), _policy()[0], "not GREEN"
                )
        policy, _ = _policy(
            allowed_source_ids=["openfda_device", "amber_source", "red_source"]
        )
        for source_id in ("amber_source", "red_source"):
            with self.subTest(source_id=source_id):
                self.assert_rejected(
                    data,
                    _entry(data, source_id=source_id),
                    policy,
                    "not declared redistributable",
                )


class PolicyParsingTests(unittest.TestCase):
    def test_enabled_allowlist_without_scope_key_is_a_policy_failure(self):
        document = check_licence.common.read_yaml(
            gitfix.REPO_ROOT / "docs/governance/DATA_LICENSES.yaml"
        )
        document["policy"]["derived_binary_allowlist"].pop("allowed_paths")
        report = check_licence.common.Report("test")
        check_licence._check_policy_sections(report, document, gitfix.REPO_ROOT)
        failures = {check["id"] for check in report.failures}
        self.assertIn("policy.derived_binary_allowlist.allowed_paths", failures)


class InventoryCoverageCounterexampleTests(unittest.TestCase):
    def test_new_gzip_under_allowed_path_without_inventory_entry_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            gitfix.init_repo(root)
            gitfix.write_bytes(root / ALLOWED_PATH, _gzip(b'{"event_id": "new"}\n'))
            gitfix.commit(root, "new gzip")
            policy, _ = _policy()
            inventory = {
                "schema": check_licence.SCHEMA_INVENTORY,
                "entries": [],
                "by_path": {},
            }
            report = check_licence.common.Report("test")
            check_licence.check_tree(root, policy, inventory, report)
            self.assertFalse(report.ok)
            failures = {check["id"] for check in report.failures}
            self.assertIn("inventory.coverage", failures)
            self.assertIn("content.restricted_kind", failures)

    def test_amber_and_red_inventory_entries_still_fail_check_tree(self):
        data = _gzip()
        for status in ("AMBER", "RED"):
            with self.subTest(status=status), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                gitfix.init_repo(root)
                gitfix.write_bytes(root / ALLOWED_PATH, data)
                gitfix.commit(root, status)
                policy, _ = _policy()
                entry = _entry(data, status=status)
                inventory = {
                    "schema": check_licence.SCHEMA_INVENTORY,
                    "entries": [entry],
                    "by_path": {ALLOWED_PATH: entry},
                }
                report = check_licence.common.Report("test")
                check_licence.check_tree(root, policy, inventory, report)
                self.assertFalse(report.ok)
                failures = {check["id"] for check in report.failures}
                expected = (
                    "content.red_source" if status == "RED" else "content.restricted_kind"
                )
                self.assertIn(expected, failures)


class CommittedSnapshotTests(unittest.TestCase):
    def test_committed_snapshot_gz_files_pass_and_digests_are_bound(self):
        policy_report = check_licence.common.Report("test")
        policy = check_licence.Policy(
            check_licence.common.read_yaml(
                gitfix.REPO_ROOT / "docs/governance/DATA_LICENSES.yaml"
            ),
            policy_report,
        )
        self.assertTrue(policy_report.ok, policy_report.render())
        inventory = check_licence.load_inventory(
            gitfix.REPO_ROOT / policy.inventory_file,
            check_licence.common.Report("test"),
        )
        manifest = json.loads(
            (SNAPSHOT_DIR / "snapshot.json").read_text(encoding="utf-8")
        )
        for name in SNAPSHOT_FILES:
            with self.subTest(name=name):
                path = "medradar/product/snapshot/" + name
                entry = inventory["by_path"][path]
                data = (gitfix.REPO_ROOT / path).read_bytes()
                self.assertEqual(entry["source_id"], "openfda_device")
                self.assertEqual(entry["status"], "GREEN")
                self.assertEqual(entry["content"], "gzip")
                self.assertEqual(entry["sha256"], _sha256(data))
                allowed, why = check_licence._declared_derived_binary(
                    entry, data, policy, path
                )
                self.assertTrue(allowed, why)
                declared = manifest["files"][name]
                self.assertEqual(declared["bytes"], len(data))
                # snapshot.json's "sha256" is the digest of the expanded JSONL
                # payload (scripts/product_collect.py hashes the payload before
                # gzip), while the inventory binds the rolled .gz artifact.
                # Both bindings are asserted so neither side can drift silently.
                self.assertEqual(
                    declared["sha256"], _sha256(gzip.decompress(data))
                )


if __name__ == "__main__":
    unittest.main()
