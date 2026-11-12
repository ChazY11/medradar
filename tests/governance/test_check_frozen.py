"""Unit tests for freeze protection: per-file digests and audited re-baselines."""

from __future__ import annotations

import hashlib
import tempfile
import unittest
from pathlib import Path

from . import gitfix
from tools.governance import check_frozen, yamlmini

STUDY = "research/studies/s"
FORECASTS = "research/forecasts"
CLAIMS = "papers/CLAIMS.json"
FROZEN_REL = "docs/governance/FROZEN.yaml"


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_frozen(root: Path, entries: list[dict], rebalances: list[dict] | None = None) -> None:
    document = {
        "schema": "medradar.frozen.v2",
        "frozen_at": "2026-11-13",
        "decisions_file": "research/DECISIONS.md",
        "decision_log_file": "docs/governance/DECISION_LOG.yaml",
        "policy": {"rebalance": "test fixture"},
        "entries": entries,
        "rebalances": rebalances or [],
    }
    gitfix.write(root / FROZEN_REL, yamlmini.dumps(document))


def _manifest(root: Path, directory: str) -> list[dict]:
    base = root / directory
    return [
        {"path": path.relative_to(base).as_posix(), "sha256": _sha(path)}
        for path in sorted(base.rglob("*"))
        if path.is_file()
    ]


def _entries(root: Path) -> list[dict]:
    return [
        {
            "freeze_id": "FZ-001",
            "study": "s",
            "kind": "file",
            "path": "%s/PROTOCOL.md" % STUDY,
            "sha256": _sha(root / STUDY / "PROTOCOL.md"),
            "rationale": "fixture protocol",
        },
        {
            "freeze_id": "FZ-002",
            "study": "s",
            "kind": "directory",
            "path": STUDY,
            "no_new_files": True,
            "files": _manifest(root, STUDY),
            "rationale": "fixture study directory",
        },
        {
            "freeze_id": "FZ-003",
            "study": "prospective_forecasts",
            "kind": "directory",
            "path": FORECASTS,
            "no_new_files": True,
            "files": _manifest(root, FORECASTS),
            "rationale": "fixture forecast directory",
        },
        {
            "freeze_id": "FZ-004",
            "study": "papers",
            "kind": "file",
            "path": CLAIMS,
            "sha256": _sha(root / CLAIMS),
            "rationale": "fixture claim map",
        },
    ]


def _seed(root: Path) -> Path:
    gitfix.init_repo(root)
    gitfix.write(root / "research/DECISIONS.md", "# Decisions\n\n## D-001 — fixture\n")
    gitfix.write(
        root / "docs/governance/DECISION_LOG.yaml",
        "schema: medradar.decision_log.v1\ndecisions:\n"
        "  - id: GOV-0001\n    approved_by: test\n    date: '2026-11-13'\n",
    )
    gitfix.write(root / STUDY / "PROTOCOL.md", "protocol fixture\n")
    gitfix.write(root / STUDY / "CASE.md", "case fixture\n")
    gitfix.write(root / FORECASTS / "F1.json", '{"fixture": 1}')
    gitfix.write(root / CLAIMS, '{"claims": 1}')
    _write_frozen(root, _entries(root))
    gitfix.commit(root, "frozen baseline")
    return root


class FreezeBypassTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = _seed(Path(self._tmp.name))

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _report(self):
        return check_frozen.build_report(
            self.root, self.root / FROZEN_REL, base="HEAD"
        )

    def _assert_fails(self, *needles: str) -> None:
        report = self._report()
        self.assertFalse(report.ok, report.render())
        text = report.render()
        for needle in needles:
            self.assertIn(needle, text)

    def reactivate(self) -> None:  # pragma: no cover - readability helper
        pass

    def test_name_only_content_edit_is_caught(self):
        gitfix.write(self.root / STUDY / "CASE.md", "case fixture edited\n")
        self._assert_fails("files[CASE.md].sha256", "expected")

    def test_added_file_in_frozen_directory_is_caught(self):
        gitfix.write(self.root / STUDY / "NEW.md", "unreviewed\n")
        self._assert_fails("no_new_files")

    def test_removed_file_in_frozen_directory_is_caught(self):
        (self.root / STUDY / "CASE.md").unlink()
        self._assert_fails("no_removed_files")

    def test_renamed_file_in_frozen_directory_is_caught(self):
        (self.root / STUDY / "CASE.md").rename(self.root / STUDY / "CASE_V2.md")
        self._assert_fails("no_new_files", "no_removed_files")

    def test_new_forecast_set_is_caught(self):
        gitfix.write(self.root / FORECASTS / "F2.json", '{"fixture": 2}')
        self._assert_fails("no_new_files")

    def test_claim_map_edit_is_caught(self):
        gitfix.write(self.root / CLAIMS, '{"claims": 2}')
        self._assert_fails("sha256")

    def _rebaseline_protocol(self, rebalances: list[dict]) -> None:
        protocol = self.root / STUDY / "PROTOCOL.md"
        previous = _sha(protocol)
        gitfix.write(protocol, "protocol fixture edited\n")
        new = _sha(protocol)
        entries = _entries(self.root)  # recomputed hashes (new protocol)
        _write_frozen(self.root, entries, rebalances)
        return previous, new

    def test_unapproved_rebaseline_is_caught(self):
        self._rebaseline_protocol([])
        self._assert_fails("rebalance.unapproved")

    def test_approved_rebaseline_passes(self):
        previous, new = self._rebaseline_protocol([])
        _write_frozen(
            self.root,
            _entries(self.root),
            [
                {
                    "path": "%s/PROTOCOL.md" % STUDY,
                    "previous_sha256": previous,
                    "new_sha256": new,
                    "decision_id": "D-001",
                    "date": "2026-11-13",
                    "reason": "fixture re-baseline authorised by D-001",
                    "approved_by": "ChazY11",
                }
            ],
        )
        report = self._report()
        self.assertTrue(report.ok, report.render())

    def test_rebaseline_with_unknown_decision_fails(self):
        previous, new = self._rebaseline_protocol([])
        _write_frozen(
            self.root,
            _entries(self.root),
            [
                {
                    "path": "%s/PROTOCOL.md" % STUDY,
                    "previous_sha256": previous,
                    "new_sha256": new,
                    "decision_id": "D-999",
                    "date": "2026-11-13",
                    "reason": "unknown decision",
                    "approved_by": "ChazY11",
                }
            ],
        )
        self._assert_fails("decision_id.exists")

    def test_rebaseline_with_decision_log_id_passes(self):
        previous, new = self._rebaseline_protocol([])
        _write_frozen(
            self.root,
            _entries(self.root),
            [
                {
                    "path": "%s/PROTOCOL.md" % STUDY,
                    "previous_sha256": previous,
                    "new_sha256": new,
                    "decision_id": "GOV-0001",
                    "date": "2026-11-13",
                    "reason": "governance-log approval",
                    "approved_by": "ChazY11",
                }
            ],
        )
        report = self._report()
        self.assertTrue(report.ok, report.render())

    def test_unapproved_new_freeze_entry_removal_is_caught(self):
        entries = [entry for entry in _entries(self.root) if entry["freeze_id"] != "FZ-004"]
        _write_frozen(self.root, entries)
        self._assert_fails("rebalance.unapproved")


class RealRepositoryFreezeTests(unittest.TestCase):
    def test_current_repository_freeze_is_clean(self):
        report = check_frozen.build_report(
            gitfix.REPO_ROOT,
            gitfix.REPO_ROOT / FROZEN_REL,
            base=None,
        )
        self.assertTrue(report.ok, report.render())


if __name__ == "__main__":
    unittest.main()
