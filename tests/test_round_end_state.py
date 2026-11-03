"""Tests for the round-end gate's repository-state classification (independent-audit defects 3 and 10)."""
from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools" / "round_end.py"


def load_module():
    spec = importlib.util.spec_from_file_location("round_end", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class DirtyClassificationTests(unittest.TestCase):
    def setUp(self):
        self.module = load_module()

    def test_gate_outputs_are_excluded_from_the_uncommitted_count(self):
        lines = [
            " M research/DECISIONS.md",
            " M tools/round_end.json",
            " M tools/round_end.log",
            " M research/AUDIT.json",
            " M research/AUDIT.md",
            " M research/FINAL_AUDIT.json",
            "?? new_file.py",
        ]
        real, self_generated = self.module.split_dirty(lines)
        self.assertEqual(len(real), 2)
        self.assertEqual(len(self_generated), 5)
        self.assertIn("new_file.py", "\n".join(real))

    def test_clean_tree_has_no_dirty_lines(self):
        self.assertEqual(self.module.split_dirty([]), ([], []))

    def test_paths_with_spaces_and_quotes_are_matched(self):
        lines = ['?? "research/studies/early_signal_5firms/README_审查结论.md"']
        real, self_generated = self.module.split_dirty(lines)
        self.assertEqual(len(real), 1)
        self.assertEqual(self_generated, [])

    def test_self_outputs_set_covers_the_documented_verifiers(self):
        for path in ("tools/round_end.json", "tools/round_end.log", "research/AUDIT.json",
                     "research/AUDIT.md", "research/FINAL_AUDIT.json"):
            self.assertIn(path, self.module.SELF_OUTPUTS)


if __name__ == "__main__":
    unittest.main()
