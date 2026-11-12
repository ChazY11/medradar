"""Unit tests for the governance rule-change audit."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from . import gitfix
from tools.governance import check_rule_audit, yamlmini

RULES_REL = "docs/governance/RULE_CHANGES.yaml"
DECISION_LOG_REL = "docs/governance/DECISION_LOG.yaml"


def _write_rules(root: Path, changes: list[dict]) -> None:
    gitfix.write(
        root / RULES_REL,
        yamlmini.dumps(
            {"schema": "medradar.rule_changes.v1", "updated": "2026-11-13", "changes": changes}
        ),
    )


def _record(**overrides) -> dict:
    record = {
        "change_id": "RC-0001",
        "date": "2026-11-13",
        "decision_id": "D-001",
        "approved_by": "ChazY11",
        "reason": "fixture rule change",
        "paths": ["tools/governance/**"],
    }
    record.update(overrides)
    return record


def _seed(root: Path) -> Path:
    gitfix.init_repo(root)
    gitfix.write(root / "research/DECISIONS.md", "# Decisions\n\n## D-001 — fixture\n")
    gitfix.write(
        root / DECISION_LOG_REL,
        "schema: medradar.decision_log.v1\ndecisions:\n"
        "  - id: GOV-0001\n    approved_by: test\n    date: '2026-11-13'\n",
    )
    _write_rules(root, [])
    gitfix.write(root / "tools/governance/check_state.py", "# fixture gate\n")
    gitfix.commit(root, "baseline")
    return root


class RuleAuditTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = _seed(Path(self._tmp.name))

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _report(self):
        return check_rule_audit.build_report(
            self.root,
            base="HEAD",
            rules_path=self.root / RULES_REL,
            decision_log=self.root / DECISION_LOG_REL,
        )

    def test_protected_change_without_record_fails(self):
        gitfix.write(self.root / "tools/governance/check_state.py", "# weakened gate\n")
        report = self._report()
        self.assertFalse(report.ok, report.render())
        self.assertIn("rules.uncovered_change", report.render())

    def test_protected_change_with_new_record_passes(self):
        gitfix.write(self.root / "tools/governance/check_state.py", "# hardened gate\n")
        _write_rules(self.root, [_record()])
        report = self._report()
        self.assertTrue(report.ok, report.render())

    def test_untracked_new_gate_file_requires_record(self):
        gitfix.write(self.root / "tools/governance/new_gate.py", "# new gate\n")
        report = self._report()
        self.assertFalse(report.ok, report.render())
        self.assertIn("rules.uncovered_change", report.render())

    def test_unknown_decision_id_fails(self):
        gitfix.write(self.root / "tools/governance/check_state.py", "# hardened gate\n")
        _write_rules(self.root, [_record(decision_id="D-999")])
        report = self._report()
        self.assertFalse(report.ok, report.render())
        self.assertIn("decision_id", report.render())

    def test_decision_log_id_is_accepted(self):
        gitfix.write(self.root / "tools/governance/check_state.py", "# hardened gate\n")
        _write_rules(self.root, [_record(decision_id="GOV-0001")])
        report = self._report()
        self.assertTrue(report.ok, report.render())

    def test_unprotected_change_does_not_need_record(self):
        gitfix.write(self.root / "docs/notes.md", "documentation only\n")
        report = self._report()
        self.assertTrue(report.ok, report.render())

    def test_record_covering_unprotected_path_fails(self):
        gitfix.write(self.root / "tools/governance/check_state.py", "# hardened gate\n")
        _write_rules(self.root, [_record(paths=["docs/notes.md"])])
        report = self._report()
        self.assertFalse(report.ok, report.render())
        self.assertIn("paths.protected", report.render())

    def test_workflow_change_requires_record(self):
        gitfix.write(
            self.root / ".github/workflows/governance.yml",
            "name: governance\non:\n  pull_request:\n",
        )
        report = self._report()
        self.assertFalse(report.ok, report.render())
        self.assertIn(".github/workflows/governance.yml", report.render())


if __name__ == "__main__":
    unittest.main()
