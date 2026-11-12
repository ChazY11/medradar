"""Tests for the five-concept state scheme and its ancestry rules.

Covers the regression the scheme exists for: a merge advances main, the state's
``git.head`` becomes stale but is still an ancestor — that must be a WARNING, not
a FAIL. Also covers wrong-lineage failures and the mandated three consecutive
simulated merges in a throwaway git repository.
"""

from __future__ import annotations

import datetime as dt
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from . import gitfix
from tools.governance import bump_state, check_state, common, yamlmini

STATE_FIXTURE = gitfix.FIXTURES / "state_schema_v2.yaml"
PYPROJECT_FIXTURE = gitfix.FIXTURES / "pyproject_fixture.toml"


def _seed(root: Path) -> str:
    gitfix.init_repo(root)
    gitfix.write(root / "PROJECT_STATE.yaml", STATE_FIXTURE.read_text(encoding="utf-8"))
    gitfix.write(root / "pyproject.toml", PYPROJECT_FIXTURE.read_text(encoding="utf-8"))
    gitfix.write(root / "docs/notes.md", "base\n")
    gitfix.commit(root, "base fixture")
    return gitfix.run_git(root, "rev-parse", "HEAD").stdout.strip()


def _advance(root: Path, message: str = "advance") -> str:
    gitfix.write(root / "docs" / ("%s.md" % message.replace(" ", "_")), message + "\n")
    gitfix.commit(root, message)
    return gitfix.run_git(root, "rev-parse", "HEAD").stdout.strip()


def _orphan_commit(root: Path) -> str:
    tree = subprocess.run(
        ["git", "-C", str(root), "mktree"], input="", capture_output=True, text=True
    )
    if tree.returncode != 0:
        raise AssertionError(tree.stderr)
    commit = subprocess.run(
        ["git", "-C", str(root), "commit-tree", tree.stdout.strip(), "-m", "orphan"],
        capture_output=True,
        text=True,
    )
    if commit.returncode != 0:
        raise AssertionError(commit.stderr)
    return commit.stdout.strip()


def _git_block(root: Path, ref: str) -> dict:
    facts = bump_state._ref_facts(root, ref)
    return {
        "ref": facts["ref"],
        "head": facts["head"],
        "short": facts["short"],
        "committed_at": facts["committed_at"],
        "commit_subject": facts["commit_subject"],
        "observed_at": facts["committed_at"],
        "tracked_files": facts["tracked_files"],
        "workflows": facts["workflows"],
    }


def _git_report(root: Path, block: dict, main_ref: str) -> common.Report:
    report = common.Report("check_state")
    check_state._check_git(
        report, root, {"pages_source": "docs"}, block, main_ref
    )
    return report


def _bump(root: Path, ref: str = "HEAD") -> subprocess.CompletedProcess:
    return subprocess.run(
        [
            sys.executable,
            str(gitfix.GATE_DIR / "bump_state.py"),
            "--root",
            str(root),
            "--ref",
            ref,
            "--no-views",
        ],
        capture_output=True,
        text=True,
        cwd=str(root),
    )


class GitHeadAncestryTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = gitfix.init_repo(Path(self._tmp.name))
        gitfix.write(self.root / "docs/notes.md", "base\n")
        gitfix.write(
            self.root / "pyproject.toml", PYPROJECT_FIXTURE.read_text(encoding="utf-8")
        )
        gitfix.commit(self.root, "base")
        self.base = gitfix.run_git(self.root, "rev-parse", "HEAD").stdout.strip()
        gitfix.write(self.root / "docs/next.md", "advance\n")
        gitfix.commit(self.root, "advance")
        self.head = gitfix.run_git(self.root, "rev-parse", "HEAD").stdout.strip()

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_stale_but_ancestor_is_a_warning_not_a_failure(self):
        report = _git_report(self.root, _git_block(self.root, self.base), "HEAD")
        self.assertTrue(report.ok, report.render())
        self.assertTrue(
            any("stale by design" in warning for warning in report.warnings),
            report.render(),
        )

    def test_current_head_has_no_staleness_warning(self):
        report = _git_report(self.root, _git_block(self.root, self.head), "HEAD")
        self.assertTrue(report.ok, report.render())
        self.assertFalse(any("stale by design" in warning for warning in report.warnings))

    def test_non_ancestor_head_fails(self):
        orphan = _orphan_commit(self.root)
        block = _git_block(self.root, self.head)
        block["head"] = orphan
        block["short"] = orphan[:7]
        report = _git_report(self.root, block, "HEAD")
        self.assertFalse(report.ok, report.render())
        self.assertIn("git.head.ancestor", report.render())

    def test_verified_non_ancestor_fails(self):
        orphan = _orphan_commit(self.root)
        report = common.Report("check_state")
        check_state._check_verified(
            report,
            self.root,
            {"commit": orphan, "verified_at": "2026-01-01T00:00:00+00:00"},
            self.head,
        )
        self.assertFalse(report.ok, report.render())
        self.assertIn("verified.commit.ancestor", report.render())

    def test_verified_ancestor_passes(self):
        report = common.Report("check_state")
        check_state._check_verified(
            report,
            self.root,
            {"commit": self.base, "verified_at": "2026-01-01T00:00:00+00:00"},
            self.head,
        )
        self.assertTrue(report.ok, report.render())

    def test_release_commit_rules(self):
        orphan = _orphan_commit(self.root)
        git_block = _git_block(self.root, self.head)
        report = common.Report("check_state")
        check_state._check_release(
            report, self.root, {"version": "9.9.9", "commit": None}, self.head, self.head
        )
        self.assertTrue(report.ok, report.render())
        report = common.Report("check_state")
        check_state._check_release(
            report, self.root, {"version": "9.9.9", "commit": orphan}, self.head, self.head
        )
        self.assertFalse(report.ok, report.render())
        self.assertIn("release.commit.ancestor", report.render())
        report = common.Report("check_state")
        check_state._check_release(
            report, self.root, {"version": "9.9.9", "commit": self.base}, self.head, self.head
        )
        self.assertTrue(report.ok, report.render())
        del git_block


class TestedHeadAncestryTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = gitfix.init_repo(Path(self._tmp.name))
        gitfix.write(self.root / "docs/notes.md", "base\n")
        gitfix.write(
            self.root / "pyproject.toml", PYPROJECT_FIXTURE.read_text(encoding="utf-8")
        )
        gitfix.commit(self.root, "base")
        self.base = gitfix.run_git(self.root, "rev-parse", "HEAD").stdout.strip()
        gitfix.write(self.root / "docs/next.md", "advance\n")
        gitfix.commit(self.root, "advance")
        self.head = gitfix.run_git(self.root, "rev-parse", "HEAD").stdout.strip()
        self.orphan = _orphan_commit(self.root)
        self.artifact = self.root / "docs/fixture_artifact.json"

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _artifact(self, tested_head: str) -> Path:
        self.artifact.write_text(
            json.dumps(
                {
                    "schema": "medradar.test_count.v1",
                    "collected": 3,
                    "passed": 3,
                    "skipped": 0,
                    "failed": 0,
                    "tested_head": tested_head,
                    "tests_unchanged_from_head": True,
                }
            ),
            encoding="utf-8",
            newline="\n",
        )
        return self.artifact

    def _tests(self, tested_head: str) -> dict:
        return {
            "collected": 3,
            "passed": 3,
            "skipped": 0,
            "failed": 0,
            "subtests_passed": 0,
            "command": "python -m pytest",
            "measured_at": "2026-01-01T00:00:00+00:00",
            "artifact": "docs/fixture_artifact.json",
            "tested_head": tested_head,
            "policy": "strict",
        }

    def test_lagging_tested_head_is_a_warning(self):
        report = common.Report("check_state")
        check_state._check_tests(
            report,
            self.root,
            self._tests(self.base),
            self.head,
            self.head,
            self.head,
            self._artifact(self.base),
            "strict",
            False,
        )
        self.assertTrue(report.ok, report.render())
        self.assertTrue(
            any("lags the observed head" in warning for warning in report.warnings),
            report.render(),
        )

    def test_unrelated_tested_head_fails(self):
        report = common.Report("check_state")
        check_state._check_tests(
            report,
            self.root,
            self._tests(self.orphan),
            self.head,
            self.head,
            self.head,
            self._artifact(self.orphan),
            "strict",
            False,
        )
        self.assertFalse(report.ok, report.render())
        self.assertIn("tests.tested_head.ancestry", report.render())

    def test_artifact_and_state_tested_head_must_match(self):
        report = common.Report("check_state")
        check_state._check_tests(
            report,
            self.root,
            self._tests(self.base),
            self.head,
            self.head,
            self.head,
            self._artifact(self.head),
            "strict",
            False,
        )
        self.assertFalse(report.ok, report.render())
        self.assertIn("tests.artifact.tested_head.match", report.render())


class ThreeMergeSimulationTests(unittest.TestCase):
    """Three consecutive simulated merges: stale state must pass, bump tracks it."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = gitfix.init_repo(Path(self._tmp.name))
        gitfix.write(self.root / "PROJECT_STATE.yaml", STATE_FIXTURE.read_text(encoding="utf-8"))
        gitfix.write(self.root / "pyproject.toml", PYPROJECT_FIXTURE.read_text(encoding="utf-8"))
        gitfix.write(self.root / "docs/notes.md", "base\n")
        gitfix.commit(self.root, "base")
        result = _bump(self.root, "HEAD")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        gitfix.commit(self.root, "bump to base")
        self.main = gitfix.run_git(self.root, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip()

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _state(self) -> dict:
        return yamlmini.load(str(self.root / "PROJECT_STATE.yaml"))

    def test_three_merges_pass_without_bump_then_bump_tracks_head(self):
        for round_number in range(1, 4):
            feature = "feature-%d" % round_number
            gitfix.run_git(self.root, "checkout", "-b", feature, self.main)
            gitfix.write(
                self.root / "docs" / ("round_%d.md" % round_number),
                "round %d change\n" % round_number,
            )
            gitfix.commit(self.root, "feature %d" % round_number)
            gitfix.run_git(self.root, "checkout", self.main)
            gitfix.run_git(
                self.root, "merge", "--no-ff", feature, "-m", "merge feature %d" % round_number
            )
            merge_head = gitfix.run_git(self.root, "rev-parse", "HEAD").stdout.strip()

            stale_block = self._state()["git"]
            report = _git_report(self.root, stale_block, "HEAD")
            self.assertTrue(
                report.ok,
                "merge %d: stale state must PASS/WARN, not FAIL:\n%s"
                % (round_number, report.render()),
            )
            self.assertTrue(
                any("stale by design" in warning for warning in report.warnings),
                "merge %d: expected a staleness warning:\n%s"
                % (round_number, report.render()),
            )

            result = _bump(self.root, "HEAD")
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            state = self._state()
            self.assertEqual(state["git"]["head"], merge_head)
            self.assertEqual(state["verified"]["commit"], merge_head)
            fresh = _git_report(self.root, state["git"], "HEAD")
            self.assertTrue(fresh.ok, fresh.render())
            self.assertFalse(any("stale by design" in warning for warning in fresh.warnings))
            gitfix.commit(self.root, "bump after merge %d" % round_number)


if __name__ == "__main__":
    unittest.main()
