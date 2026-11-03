"""Release-consistency checks: version, packaging metadata, and no placeholders."""

from __future__ import annotations

import re
import tempfile
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
        """README must advertise a test count that still resembles the real suite.

        The check is deliberately a tolerance band rather than an exact count, so
        adding a test does not force a README edit, while a stale release-note
        count (the "402 vs 427" class of drift) still fails. The reference is the
        static number of ``def test_`` functions in ``tests/`` — cheap, offline,
        and close enough to the runtime count for a drift guard.

        History: the band used to be 400–900, which stopped being satisfiable once
        the suite passed 900 checks; the README then advertised 678 and this test
        kept passing a stale number. Both the band and the reference are now
        relative to the tree instead of to a snapshot.
        """
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        match = re.search(r"([\d,]+)\s+(?:offline\s+)?(?:unittest\s+)?(?:tests|checks)", readme)
        self.assertIsNotNone(match, "README must state the offline test count")
        advertised = int(match.group(1).replace(",", ""))
        defined = sum(
            len(re.findall(r"^\s+def test_", path.read_text(encoding="utf-8", errors="replace"), re.M))
            for path in sorted((ROOT / "tests").glob("test_*.py"))
        )
        self.assertGreaterEqual(defined, 400)
        self.assertGreaterEqual(advertised, int(defined * 0.75), "README test count looks stale (too low)")
        self.assertLessEqual(advertised, int(defined * 1.25) + 10, "README test count looks stale (too high)")

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


class PublishLinkTests(unittest.TestCase):
    """No docs/docs/ASSUMPTIONS.md duplicate: publish rewrites the link instead."""

    def test_published_assumptions_link_points_to_sibling(self) -> None:
        from medradar.__main__ import _rewrite_published_links

        with tempfile.TemporaryDirectory() as tmp:
            page = Path(tmp) / "index.html"
            page.write_text('<a href="docs/ASSUMPTIONS.md">docs/ASSUMPTIONS.md</a>', encoding="utf-8")
            _rewrite_published_links(page)
            text = page.read_text(encoding="utf-8")
            self.assertIn('href="ASSUMPTIONS.md"', text)
            self.assertNotIn("docs/ASSUMPTIONS.md", text)

    def test_replay_page_link_is_rewritten(self) -> None:
        from medradar.__main__ import _rewrite_published_links

        with tempfile.TemporaryDirectory() as tmp:
            page = Path(tmp) / "replay.html"
            page.write_text('<a href="../../docs/ASSUMPTIONS.md">x</a>', encoding="utf-8")
            _rewrite_published_links(page)
            self.assertIn('href="ASSUMPTIONS.md"', page.read_text(encoding="utf-8"))

    def test_ship_assumptions_does_not_recreate_docs_duplicate(self) -> None:
        from medradar.__main__ import _ship_assumptions

        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp) / "out"
            docs_dir = Path(tmp) / "docs"
            copied = _ship_assumptions(out_dir, docs_dir)
            self.assertTrue((out_dir / "docs" / "ASSUMPTIONS.md").is_file())
            self.assertTrue((out_dir / "replay" / "docs" / "ASSUMPTIONS.md").is_file())
            self.assertFalse((docs_dir / "docs" / "ASSUMPTIONS.md").exists())
            self.assertTrue(copied)


if __name__ == "__main__":
    unittest.main()
