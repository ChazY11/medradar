"""Tests for the static figure layout checker (the defects it exists to catch)."""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "papers"))

import check_layout  # noqa: E402


def svg(body: str, width: int = 200, height: int = 100) -> str:
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
            f'viewBox="0 0 {width} {height}">{body}</svg>')


class CheckLayoutTest(unittest.TestCase):
    def check(self, markup: str) -> list[str]:
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "figure.svg"
            path.write_text(markup, encoding="utf-8")
            return check_layout.check(path)

    def test_clean_figure_passes(self):
        problems = self.check(svg('<text x="10" y="20" font-size="10">fine</text>'))
        self.assertEqual(problems, [])

    def test_missing_viewbox_is_reported(self):
        problems = self.check('<svg xmlns="http://www.w3.org/2000/svg"><text x="1">a</text></svg>')
        self.assertTrue(any("viewBox" in problem for problem in problems))

    def test_text_running_off_the_canvas_is_reported(self):
        markup = svg('<text x="150" y="50" font-size="10">a label far too long for this canvas</text>')
        problems = self.check(markup)
        self.assertTrue(any("outside the canvas" in problem for problem in problems))

    def test_text_painted_over_by_a_later_shape_is_reported(self):
        markup = svg('<text x="10" y="50" font-size="10">hidden</text>'
                     '<rect x="0" y="30" width="200" height="40" fill="#c0392b"/>')
        problems = self.check(markup)
        self.assertTrue(any("painted over" in problem for problem in problems))

    def test_a_background_shape_over_text_is_not_reported(self):
        markup = svg('<text x="10" y="50" font-size="10">visible</text>'
                     '<rect x="0" y="0" width="200" height="100" fill="#ffffff"/>')
        self.assertEqual(self.check(markup), [])

    def test_rotated_axis_label_is_measured_vertically(self):
        markup = svg('<text x="12" y="200" font-size="10" text-anchor="middle" '
                     'transform="rotate(-90 12 200)">sensitivity (detection probability)</text>',
                     width=200, height=400)
        self.assertEqual(self.check(markup), [])

    def test_rotated_label_off_the_canvas_is_still_reported(self):
        markup = svg('<text x="0" y="50" font-size="10" text-anchor="middle" '
                     'transform="rotate(-90 0 50)">sensitivity (detection probability)</text>')
        problems = self.check(markup)
        self.assertTrue(any("outside the canvas" in problem for problem in problems))


class RepositoryFiguresTest(unittest.TestCase):
    def test_committed_figures_have_no_layout_problems(self):
        root = Path(__file__).resolve().parents[1] / "papers" / "figures"
        problems = []
        for path in sorted(root.glob("*.svg")):
            problems.extend(check_layout.check(path))
        self.assertEqual(problems, [], f"layout problems in committed figures: {problems}")


if __name__ == "__main__":
    unittest.main()
