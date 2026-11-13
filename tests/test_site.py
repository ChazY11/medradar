"""Offline checks for the redesigned GitHub Pages site under ``docs/``.

The five site pages are hand-authored HTML (built from the shared chrome in
``tools/site/build_site.py``) and are served from a repository subpath, so the
suite enforces the rules that keep that safe and honest:

* every page exists and is well formed enough to parse;
* every local ``href``/``src`` resolves relative to the page's own folder — the
  site must work when served from ``.../medradar/`` with no root-absolute paths;
* there are no external requests at all: no CDN, no webfont, no analytics, no
  remote script and no ``@import``;
* every page carries a viewport meta, one ``<h1>``, a skip link, a header with
  ``aria-current``, a mobile nav toggle with ``aria-expanded``, and a footer with
  the provenance line;
* images carry ``alt`` plus explicit dimensions;
* the landing page references the real dashboard screenshot and the architecture
  diagram (light + dark through ``<picture>``);
* ``docs/index.html`` is the landing page and the generated report moved to
  ``docs/report.html`` (the rename this change introduces).

Nothing here reads the network or executes JavaScript.
"""

from __future__ import annotations

import html as html_module
import re
import unittest
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"

PAGES = (
    DOCS / "index.html",
    DOCS / "research" / "index.html",
    DOCS / "platform" / "index.html",
    DOCS / "explore" / "index.html",
    DOCS / "documentation" / "index.html",
)

VOID_TAGS = {
    "area", "base", "br", "col", "embed", "hr", "img", "input", "link",
    "meta", "param", "source", "track", "wbr",
}
EXTERNAL_RE = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*:")
REMOTE_RE = re.compile(r"^https?://", re.IGNORECASE)


class _Page(HTMLParser):
    """Collect the handful of facts each test needs from one page."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.stack: list[str] = []
        self.errors: list[str] = []
        self.tags: set[str] = set()
        self.ids: set[str] = set()
        self.h1 = 0
        self.viewport = False
        self.doctype = False
        self.lang = ""
        self.inline_styles = 0
        self.style_blocks = 0
        self.inline_scripts = 0
        self.scripts: list[str] = []
        self.anchors: list[dict[str, str]] = []
        self.links: list[dict[str, str]] = []
        self.images: list[dict[str, str]] = []
        self.sources: list[dict[str, str]] = []
        self.skip_href: str | None = None
        self.nav_button: dict[str, str] | None = None
        self.nav_labels: list[str] = []
        self._in_header = 0
        self._in_nav = 0
        self._in_primary_nav = 0
        self._in_a = 0
        self._a_text: list[str] = []
        self._a_class = ""

    def handle_decl(self, decl: str) -> None:
        if decl.lower().startswith("doctype html"):
            self.doctype = True

    def handle_starttag(self, tag: str, attrs_list) -> None:
        attrs = {name.lower(): (value if value is not None else "") for name, value in attrs_list}
        self.tags.add(tag)
        if tag not in VOID_TAGS:
            self.stack.append(tag)
        if attrs.get("id"):
            self.ids.add(attrs["id"])
        if tag == "html":
            self.lang = attrs.get("lang", "")
        if tag == "h1":
            self.h1 += 1
        if "style" in attrs:
            self.inline_styles += 1
        if tag == "style":
            self.style_blocks += 1
        if tag == "meta" and attrs.get("name", "").lower() == "viewport":
            self.viewport = "width=device-width" in attrs.get("content", "")
        if tag == "link":
            self.links.append(attrs)
        if tag == "img":
            self.images.append(attrs)
        if tag == "source":
            self.sources.append(attrs)
        if tag == "script":
            if attrs.get("src"):
                self.scripts.append(attrs["src"])
            else:
                self.inline_scripts += 1
        if tag == "header":
            self._in_header += 1
        if tag == "nav":
            self._in_nav += 1
            if attrs.get("aria-label") == "Primary":
                self._in_primary_nav += 1
        if tag == "button" and "aria-controls" in attrs:
            self.nav_button = attrs
        if tag == "a":
            self._in_a += 1
            self._a_text = []
            self._a_class = attrs.get("class", "")
            self.anchors.append(attrs)
            if "skip" in self._a_class.split() and attrs.get("href"):
                self.skip_href = attrs["href"]

    def handle_data(self, data: str) -> None:
        if self._in_a:
            self._a_text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag in VOID_TAGS:
            return
        if tag == "header":
            self._in_header = max(0, self._in_header - 1)
        if tag == "nav":
            self._in_nav = max(0, self._in_nav - 1)
            self._in_primary_nav = max(0, self._in_primary_nav - 1)
        if tag == "a":
            if self._in_primary_nav and self._in_a:
                label = " ".join("".join(self._a_text).split())
                if label:
                    self.nav_labels.append(label)
            self._in_a = max(0, self._in_a - 1)
        if not self.stack:
            self.errors.append(f"unexpected closing tag </{tag}>")
            return
        if self.stack[-1] == tag:
            self.stack.pop()
        elif tag in self.stack:
            while self.stack and self.stack[-1] != tag:
                self.errors.append(f"unclosed <{self.stack.pop()}> before </{tag}>")
            if self.stack:
                self.stack.pop()
        else:
            self.errors.append(f"unmatched closing tag </{tag}>")

    def close(self) -> None:
        super().close()
        self.errors.extend(f"unclosed <{tag}>" for tag in self.stack)


def _parse(path: Path) -> _Page:
    page = _Page()
    page.feed(path.read_text(encoding="utf-8"))
    page.close()
    return page


def _local_refs(page: _Page) -> list[tuple[str, str]]:
    refs: list[tuple[str, str]] = []
    for attrs in page.anchors + page.links:
        if attrs.get("href"):
            refs.append(("href", attrs["href"]))
    for attrs in page.images:
        if attrs.get("src"):
            refs.append(("src", attrs["src"]))
    for attrs in page.sources:
        value = attrs.get("src") or attrs.get("srcset", "")
        if value:
            refs.append(("srcset", value.split(",")[0].strip().split(" ")[0]))
    for src in page.scripts:
        refs.append(("script", src))
    return refs


def _resolve(page: Path, raw: str) -> Path | None:
    target = raw.split("#", 1)[0].split("?", 1)[0].strip()
    if not target:
        return None
    if EXTERNAL_RE.match(target) or target.startswith("//"):
        return None
    if target.startswith("/"):
        return Path("/__root_absolute__")
    if target.endswith("/"):
        target += "index.html"
    return (page.parent / target).resolve()


def _visible_text(fragment: str) -> str:
    """Strip tags, unescape entities and collapse whitespace for text assertions."""
    text = re.sub(r"<[^>]+>", " ", fragment)
    return " ".join(html_module.unescape(text).split())


class SitePagesTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.pages = {path: _parse(path) for path in PAGES if path.is_file()}

    # ------------------------------------------------------------------ files
    def test_every_site_page_exists(self) -> None:
        for path in PAGES:
            self.assertTrue(path.is_file(), f"missing site page: {path.relative_to(ROOT)}")
            self.assertGreater(path.stat().st_size, 3000, f"suspiciously small page: {path}")
            self.assertLess(path.stat().st_size, 150_000, f"page over the size budget: {path}")

    def test_each_page_is_a_document(self) -> None:
        for path, page in self.pages.items():
            name = path.relative_to(ROOT).as_posix()
            with self.subTest(page=name):
                self.assertTrue(page.doctype, f"{name}: missing <!DOCTYPE html>")
                self.assertEqual(page.lang, "en", f"{name}: <html lang> must be 'en'")
                self.assertEqual(page.errors, [], f"{name}: unbalanced markup")
                for landmark in ("header", "nav", "main", "footer"):
                    self.assertIn(landmark, page.tags, f"{name}: missing <{landmark}>")

    def test_accessibility_contract(self) -> None:
        for path, page in self.pages.items():
            name = path.relative_to(ROOT).as_posix()
            with self.subTest(page=name):
                self.assertTrue(page.viewport, f"{name}: missing viewport meta")
                self.assertEqual(page.h1, 1, f"{name}: expected exactly one <h1>")
                self.assertEqual(page.skip_href, "#main", f"{name}: skip link must target #main")
                self.assertIn("main", page.ids, f"{name}: <main> needs id='main'")
                header = re.search(r"<header\b.*?</header>", path.read_text(encoding="utf-8"), re.DOTALL)
                self.assertIsNotNone(header, f"{name}: no <header> block")
                assert header is not None
                self.assertEqual(
                    header.group(0).count('aria-current="page"'),
                    1,
                    f"{name}: header needs exactly one aria-current='page'",
                )

    def test_mobile_nav_toggle_is_wired(self) -> None:
        for path, page in self.pages.items():
            name = path.relative_to(ROOT).as_posix()
            with self.subTest(page=name):
                self.assertIsNotNone(page.nav_button, f"{name}: no nav toggle button")
                assert page.nav_button is not None
                self.assertIn("aria-expanded", page.nav_button, f"{name}: toggle needs aria-expanded")
                controls = page.nav_button.get("aria-controls", "")
                self.assertIn(controls, page.ids, f"{name}: aria-controls target missing")

    def test_primary_navigation_is_identical(self) -> None:
        for path, page in self.pages.items():
            name = path.relative_to(ROOT).as_posix()
            with self.subTest(page=name):
                self.assertEqual(
                    page.nav_labels,
                    ["Research", "Platform", "Explore", "Documentation"],
                    f"{name}: primary nav drifted",
                )

    # ----------------------------------------------------------------- links
    def test_no_external_requests(self) -> None:
        for path, page in self.pages.items():
            name = path.relative_to(ROOT).as_posix()
            with self.subTest(page=name):
                for kind, raw in _local_refs(page):
                    if kind in {"src", "srcset", "script", "link"} and REMOTE_RE.match(raw):
                        self.fail(f"{name}: external {kind} request is banned: {raw}")
                for attrs in page.links:
                    href = attrs.get("href", "")
                    self.assertNotRegex(
                        href.lower(), r"^https?://", f"{name}: remote <link> is banned: {href}"
                    )
                for attrs in page.sources:
                    value = attrs.get("srcset", "")
                    self.assertNotRegex(value.lower(), r"^https?://", f"{name}: remote srcset")

    def test_local_references_resolve(self) -> None:
        for path, page in self.pages.items():
            name = path.relative_to(ROOT).as_posix()
            with self.subTest(page=name):
                for kind, raw in _local_refs(page):
                    resolved = _resolve(path, raw)
                    if resolved is None:
                        continue
                    self.assertNotEqual(
                        resolved,
                        Path("/__root_absolute__"),
                        f"{name}: root-absolute URL is not allowed: {raw}",
                    )
                    assert resolved is not None
                    self.assertTrue(resolved.exists(), f"{name}: {kind} {raw!r} does not resolve")

    def test_scripts_are_local_and_no_inline_style(self) -> None:
        for path, page in self.pages.items():
            name = path.relative_to(ROOT).as_posix()
            with self.subTest(page=name):
                self.assertEqual(page.inline_scripts, 0, f"{name}: inline <script> block found")
                self.assertEqual(page.style_blocks, 0, f"{name}: inline <style> block found")
                self.assertEqual(page.inline_styles, 0, f"{name}: inline style= attribute found")
                for src in page.scripts:
                    self.assertFalse(
                        REMOTE_RE.match(src), f"{name}: external script is banned: {src}"
                    )
                    self.assertTrue(
                        (path.parent / src).resolve().is_file(), f"{name}: missing script {src}"
                    )

    def test_images_have_alt_and_dimensions(self) -> None:
        for path, page in self.pages.items():
            name = path.relative_to(ROOT).as_posix()
            with self.subTest(page=name):
                for index, attrs in enumerate(page.images, start=1):
                    src = attrs.get("src", f"image #{index}")
                    self.assertIn("alt", attrs, f"{name}: {src} has no alt attribute")
                    self.assertTrue(
                        attrs.get("width") and attrs.get("height"),
                        f"{name}: {src} needs explicit width and height",
                    )

    # -------------------------------------------------------------- landing
    def test_landing_references_real_artefacts(self) -> None:
        landing = (DOCS / "index.html").read_text(encoding="utf-8")
        self.assertIn("assets/screenshots/dashboard-desktop.png", landing)
        self.assertIn("assets/architecture/architecture-en-light.svg", landing)
        self.assertIn("assets/architecture/architecture-en-dark.svg", landing)
        self.assertIn("<picture>", landing)
        self.assertIn('href="report.html"', landing)
        self.assertIn('href="dashboard.html"', landing)

    def test_landing_stat_strip_uses_verified_numbers(self) -> None:
        landing = (DOCS / "index.html").read_text(encoding="utf-8")
        for value in ("375,378", "1,160", "1966", "6"):
            self.assertIn(value, landing, f"stat strip lost the value {value!r}")
        self.assertIn("not a validated predictive product", landing)

    def test_status_vocabulary_is_labelled_not_colour_only(self) -> None:
        landing = (DOCS / "index.html").read_text(encoding="utf-8")
        for label in ("implemented", "limited"):
            self.assertIn(f"status--{label}", landing)
            self.assertIn(f">{label}</span>", landing)
        platform = (DOCS / "platform" / "index.html").read_text(encoding="utf-8")
        for label in ("implemented", "limited", "draft", "planned"):
            self.assertIn(f"status--{label}", platform)
            self.assertIn(f">{label}</span>", platform)

    def test_footer_carries_provenance(self) -> None:
        for path, page in self.pages.items():
            name = path.relative_to(ROOT).as_posix()
            html = path.read_text(encoding="utf-8")
            with self.subTest(page=name):
                footer = re.search(r"<footer\b.*?</footer>", html, re.DOTALL)
                self.assertIsNotNone(footer, f"{name}: no footer")
                assert footer is not None
                block = footer.group(0)
                for token in ("Data snapshot", "2026-10-31", "v0.5.0", "MIT", "not investment advice"):
                    self.assertIn(token, block, f"{name}: footer lost {token!r}")
                self.assertIn("docs/INDEX.md", block, f"{name}: footer must link docs/INDEX.md")
                self.assertEqual(block.count("<nav"), 4, f"{name}: footer needs four link columns")
                # The provenance line must render its values, not just its labels:
                # the bold values inherit the dark-surface colour via CSS.
                self.assertIn(
                    "Data snapshot 2026-10-31 \u00b7 package v0.5.0 \u00b7 MIT",
                    _visible_text(block),
                    f"{name}: provenance line lost its values",
                )
                self.assertNotIn(
                    "Data snapshot \u00b7 package \u00b7 MIT",
                    _visible_text(block),
                    f"{name}: provenance line renders without values",
                )

    # ------------------------------------------------------- generated rename
    def test_generated_report_is_renamed_to_report_html(self) -> None:
        report = DOCS / "report.html"
        self.assertTrue(report.is_file(), "docs/report.html (the generated report) is missing")
        self.assertGreater(report.stat().st_size, 50_000)
        report_text = report.read_text(encoding="utf-8", errors="replace")
        self.assertIn("<!DOCTYPE html>", report_text)
        # The landing page must no longer be the generated report.
        landing = (DOCS / "index.html").read_text(encoding="utf-8")
        self.assertNotIn('class="statusbar', landing)
        self.assertIn('<main id="main">', landing)

    # --------------------------------------------------------------- assets
    def test_stylesheet_and_script_follow_the_budget(self) -> None:
        css = DOCS / "assets" / "css" / "site.css"
        js = DOCS / "assets" / "js" / "site.js"
        self.assertTrue(css.is_file(), "site.css is missing")
        self.assertTrue(js.is_file(), "site.js is missing")
        css_text = css.read_text(encoding="utf-8")
        self.assertLess(len(css_text.encode("utf-8")), 150_000)
        self.assertIn("TABLE OF CONTENTS", css_text)
        self.assertIn("--accent:", css_text)
        self.assertIn(":focus-visible", css_text)
        self.assertIn("prefers-reduced-motion", css_text)
        self.assertNotIn("@import", css_text)
        self.assertNotRegex(css_text, r"url\(\s*['\"]?https?:")
        self.assertLess(js.stat().st_size, 6 * 1024, "site.js exceeds the 6 KB budget")
        self.assertNotRegex(js.read_text(encoding="utf-8"), r"https?://")


if __name__ == "__main__":
    unittest.main()
