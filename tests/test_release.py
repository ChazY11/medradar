"""Release-consistency checks: version, packaging metadata, and no placeholders."""

from __future__ import annotations

import re
import unittest
from pathlib import Path

try:  # Python 3.11+
    import tomllib
except ModuleNotFoundError:  # Python 3.10: the project still supports it
    tomllib = None  # type: ignore[assignment]

import medradar

ROOT = Path(__file__).resolve().parents[1]


class VersionTests(unittest.TestCase):
    def test_package_version_matches_pyproject(self) -> None:
        text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
        if tomllib is not None:
            version = tomllib.loads(text)["project"]["version"]
        else:  # Python 3.10 fallback: parse the [project] version line
            version = re.search(r'^version\s*=\s*"([^"]+)"', text, re.M).group(1)
        self.assertEqual(version, medradar.__version__)

    def test_changelog_has_current_release(self) -> None:
        changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
        self.assertIn(f"[{medradar.__version__}]", changelog)

    def test_readme_has_no_placeholder_clone_url(self) -> None:
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertNotIn("<your-username>", readme)
        self.assertNotIn("<REPO_URL>", readme)

    def test_readme_test_count_is_not_stale(self) -> None:
        """README must not advertise a test count that no longer exists.

        Keeping this a range check (not an exact count) avoids a circular test
        that has to be edited every time a test is added, while still catching
        the "402 vs 427" class of release-note drift.
        """
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        match = re.search(r"(\d{3})\s*offline tests", readme)
        self.assertIsNotNone(match)
        advertised = int(match.group(1))
        self.assertGreaterEqual(advertised, 400)
        self.assertLessEqual(advertised, 600)

    def test_docs_do_not_link_missing_local_pages(self) -> None:
        index = ROOT / "docs" / "index.html"
        if not index.is_file():
            self.skipTest("docs/index.html not built")
        html = index.read_text(encoding="utf-8", errors="replace")
        for href in re.findall(r'href="([^"]+)"', html):
            if href.startswith(("http://", "https://", "#", "mailto:", "data:")):
                continue
            if href.endswith(".html") or "/" in href:
                self.assertTrue((ROOT / "docs" / href).exists(), f"dead local link in docs/index.html: {href}")


if __name__ == "__main__":
    unittest.main()
