#!/usr/bin/env python3
"""Check the static MedRadar site under ``docs/`` against the build contract.

The site must look and behave like a mature product page *and* stay honest about
the repository's engineering rules. This check enforces the mechanical ones:

* the five pages exist and parse as balanced-enough HTML;
* every local ``href`` / ``src`` resolves relative to the page's own folder
  (the site is served from ``.../medradar/``, so root-absolute URLs are banned);
* there are zero external requests: no ``http(s)://`` in ``src``/``link``, no
  ``@import`` and no remote ``url()`` in the stylesheet, no external script;
* each page has a viewport meta, exactly one ``<h1>``, a skip link to ``#main``,
  ``aria-current`` on the header, and a nav toggle wired with
  ``aria-expanded`` + ``aria-controls``;
* every ``<img>`` has ``alt`` and explicit ``width``/``height``;
* no ``style=`` attributes and no inline ``<style>`` blocks;
* the stylesheet is hand-readable (table of contents, tokens, focus-visible,
  reduced-motion branch) and the navigation script stays under 6 KB;
* the landing page references the real screenshot and architecture assets, and
  the generated artefacts it links (``report.html``, ``dashboard.html``) exist.

Exit codes: 0 pass, 1 check failed, 2 usage error.

Usage:
    python tools/site/check_site.py
    python tools/site/check_site.py --allow-missing-assets   # assets still landing
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

PAGES = (
    "docs/index.html",
    "docs/research/index.html",
    "docs/platform/index.html",
    "docs/explore/index.html",
    "docs/documentation/index.html",
)

#: Files the landing page must reference (real screenshots + real diagrams).
LANDING_REQUIRED_REFS = (
    "assets/screenshots/dashboard-desktop.png",
    "assets/architecture/architecture-en-light.svg",
    "assets/architecture/architecture-en-dark.svg",
)

#: Generated artefacts the site links; produced by `medradar report` / `dashboard`.
GENERATED_ARTEFACTS = ("docs/report.html", "docs/dashboard.html", "docs/replay.html", "docs/metrics.json")

VOID_TAGS = {
    "area", "base", "br", "col", "embed", "hr", "img", "input", "link",
    "meta", "param", "source", "track", "wbr",
}
EXTERNAL_SCHEME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*:")
CSS_FORBIDDEN_RE = re.compile(r"@import|url\(\s*['\"]?https?:", re.IGNORECASE)


class PageParser(HTMLParser):
    """Collect everything the checks need from one page."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.errors: list[str] = []
        self.stack: list[str] = []
        self.tags: list[str] = []
        self.h1 = 0
        self.h2 = 0
        self.inline_styles = 0
        self.style_blocks = 0
        self.scripts: list[str] = []
        self.images: list[dict[str, str | None]] = []
        self.links: list[dict[str, str | None]] = []
        self.anchors: list[dict[str, str | None]] = []
        self.sources: list[dict[str, str | None]] = []
        self.meta_viewport = False
        self.has_doctype = False
        self.html_lang = ""
        self._in_head = False
        self._in_style = False
        self._in_header = 0
        self._header_aria_current = 0
        self._nav_button: dict[str, dict[str, str | None]] = {}
        self._ids: set[str] = set()
        self._skip_href: str | None = None
        self._skip_is_first_anchor = False
        self._first_anchor_seen = False

    # ------------------------------------------------------------------ parse
    def handle_decl(self, decl: str) -> None:  # noqa: D401 - HTMLParser API
        if decl.lower().startswith("doctype html"):
            self.has_doctype = True

    def handle_starttag(self, tag: str, attrs_list) -> None:  # noqa: D401
        attrs = {name.lower(): (value if value is not None else "") for name, value in attrs_list}
        self.tags.append(tag)
        if tag not in VOID_TAGS:
            self.stack.append(tag)
        if tag == "html":
            self.html_lang = attrs.get("lang", "")
        if "style" in attrs:
            self.inline_styles += 1
        if tag == "style":
            self.style_blocks += 1
        if tag == "main" and "id" in attrs:
            self._ids.add(attrs["id"])
        if "id" in attrs:
            self._ids.add(attrs["id"])
        if tag == "h1":
            self.h1 += 1
        if tag == "h2":
            self.h2 += 1
        if tag == "meta":
            if attrs.get("name", "").lower() == "viewport" and "width=device-width" in attrs.get(
                "content", ""
            ):
                self.meta_viewport = True
        if tag == "link":
            self.links.append(attrs)
        if tag == "a":
            self.anchors.append(attrs)
            if "skip" in attrs.get("class", "").split() and "href" in attrs:
                self._skip_href = attrs["href"]
        if tag == "header":
            self._in_header += 1
        if tag == "img":
            self.images.append(attrs)
        if tag == "source":
            self.sources.append(attrs)
        if tag == "script":
            self.scripts.append(attrs.get("src", ""))
        if tag == "button" and "aria-controls" in attrs:
            self._nav_button = attrs
        if tag == "head":
            self._in_head = True

    def handle_endtag(self, tag: str) -> None:  # noqa: D401
        if tag in VOID_TAGS:
            return
        if tag == "header":
            self._in_header = max(0, self._in_header - 1)
        if tag == "head":
            self._in_head = False
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

    # ----------------------------------------------------------------- report
    @property
    def nav_button(self) -> dict[str, str | None]:
        return self._nav_button


@dataclass
class Report:
    failures: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    checks: int = 0

    def fail(self, message: str) -> None:
        self.failures.append(message)

    def warn(self, message: str) -> None:
        self.warnings.append(message)

    def ok(self) -> None:
        self.checks += 1


def _local_targets(page: Path) -> list[tuple[str, str]]:
    """Return (kind, raw url) for every local href/src/source on the page."""
    text = page.read_text(encoding="utf-8")
    parser = PageParser()
    parser.feed(text)
    parser.close()
    found: list[tuple[str, str]] = []
    for attrs in parser.anchors + parser.links:
        href = attrs.get("href")
        if href:
            found.append(("href", href))
    for attrs in parser.images + parser.sources:
        src = attrs.get("src") or attrs.get("srcset")
        if src:
            found.append(("src", src))
    for src in parser.scripts:
        if src:
            found.append(("script", src))
    return found


def _resolve(page: Path, raw: str) -> Path | None:
    target = raw.split("#", 1)[0].split("?", 1)[0].strip()
    if not target:
        return None
    if EXTERNAL_SCHEME_RE.match(target) or target.startswith("//"):
        return None
    if target.startswith("/") or re.match(r"^[A-Za-z]:[\\/]", target):
        return Path("__absolute__")
    if target.endswith("/"):
        target += "index.html"
    return (page.parent / target).resolve()


def check_page(page: Path, report: Report, allow_missing_assets: bool = False) -> PageParser:
    if not page.is_file():
        report.fail(f"{page.relative_to(ROOT)} does not exist")
        return PageParser()

    text = page.read_text(encoding="utf-8")
    parser = PageParser()
    parser.feed(text)
    parser.close()

    name = page.relative_to(ROOT).as_posix()
    report.ok()

    if not text.lstrip().lower().startswith("<!doctype html>"):
        report.fail(f"{name}: missing <!DOCTYPE html>")
    if parser.html_lang != "en":
        report.fail(f"{name}: <html lang> must be 'en'")
    if not parser.meta_viewport:
        report.fail(f"{name}: missing viewport meta with width=device-width")
    if parser.h1 != 1:
        report.fail(f"{name}: expected exactly one <h1>, found {parser.h1}")
    if parser.h2 < 2:
        report.fail(f"{name}: expected section headings (<h2>), found {parser.h2}")
    if parser.errors:
        for error in parser.errors:
            report.fail(f"{name}: unbalanced markup: {error}")

    # Skip link, landmarks, main target.
    if not parser._skip_href:
        report.fail(f"{name}: missing skip link (class='skip')")
    elif parser._skip_href != "#main":
        report.fail(f"{name}: skip link must target '#main', got {parser._skip_href!r}")
    if "main" not in parser.tags:
        report.fail(f"{name}: missing <main> landmark")
    if "main" in parser.tags and "main" not in parser._ids:
        report.fail(f"{name}: <main> needs id='main' for the skip link")
    for landmark in ("header", "footer", "nav"):
        if landmark not in parser.tags:
            report.fail(f"{name}: missing <{landmark}> landmark")

    # aria-current on the header, exactly once.
    header_slice = re.search(r"<header\b.*?</header>", text, re.DOTALL)
    if not header_slice:
        report.fail(f"{name}: no <header> block")
    else:
        current = header_slice.group(0).count('aria-current="page"')
        if current != 1:
            report.fail(f"{name}: expected exactly one aria-current=\"page\" in the header, found {current}")

    # Mobile nav toggle.
    button = parser.nav_button
    if not button:
        report.fail(f"{name}: no nav toggle <button aria-controls=...>")
    else:
        if button.get("aria-expanded") is None:
            report.fail(f"{name}: nav toggle missing aria-expanded")
        controls = button.get("aria-controls", "")
        if not controls or f'id="{controls}"' not in text:
            report.fail(f"{name}: nav toggle aria-controls={controls!r} does not match an element id")

    # Images: alt + dimensions.
    for index, attrs in enumerate(parser.images, start=1):
        if attrs.get("alt") is None:
            report.fail(f"{name}: image #{index} ({attrs.get('src')}) has no alt attribute")
        if not (attrs.get("width") and attrs.get("height")):
            report.fail(
                f"{name}: image #{index} ({attrs.get('src')}) needs explicit width and height"
            )

    # Local references must resolve; no external requests.
    for kind, raw in _local_targets(page):
        lowered = raw.lower()
        if EXTERNAL_SCHEME_RE.match(raw) or raw.startswith("//"):
            if kind in {"src", "script", "link"} and lowered.startswith(("http://", "https://")):
                report.fail(f"{name}: external {kind} request {raw!r} is banned")
            continue
        if raw.startswith("#") or lowered.startswith(("mailto:", "data:", "tel:")):
            continue
        resolved = _resolve(page, raw)
        if resolved is None:
            continue
        if resolved == Path("__absolute__"):
            report.fail(f"{name}: root-absolute or filesystem URL {raw!r} (site is served from a subpath)")
            continue
        if not resolved.exists():
            under_assets = (ROOT / "docs" / "assets") in resolved.parents
            if under_assets and allow_missing_assets:
                report.warn(f"{name}: {kind} {raw!r} is still missing ({resolved})")
            else:
                report.fail(f"{name}: {kind} {raw!r} does not resolve to a file ({resolved})")
        else:
            report.ok()

    # No inline styles.
    if parser.inline_styles:
        report.fail(f"{name}: {parser.inline_styles} inline style attribute(s); use the stylesheet")
    if parser.style_blocks:
        report.fail(f"{name}: {parser.style_blocks} inline <style> block(s)")

    # Scripts: local only.
    for src in parser.scripts:
        if not src:
            report.fail(f"{name}: inline <script> block; page JS must live in docs/assets/js/")
        elif src.startswith(("http://", "https://")):
            report.fail(f"{name}: external script {src!r}")
    report.ok()
    return parser


def check_assets(report: Report, allow_missing: bool) -> None:
    css = ROOT / "docs/assets/css/site.css"
    js = ROOT / "docs/assets/js/site.js"
    if not css.is_file():
        report.fail("docs/assets/css/site.css is missing")
        return
    css_text = css.read_text(encoding="utf-8")
    report.ok()
    if "@import" in css_text or CSS_FORBIDDEN_RE.search(css_text):
        report.fail("site.css must not @import or url() a remote resource")
    if "TABLE OF CONTENTS" not in css_text:
        report.fail("site.css needs its table-of-contents comment")
    for token in ("--accent:", "--ink:", "--warn:", "--navy:", "--w-prose:", "--w-page:", "--font-mono:"):
        if token not in css_text:
            report.fail(f"site.css is missing design token {token}")
    for rule in (":focus-visible", "prefers-reduced-motion", "prefers-color-scheme: dark"):
        if rule not in css_text:
            report.fail(f"site.css is missing {rule}")
    if "url(" in css_text and re.search(r"url\(\s*['\"]?(?!/|#)", css_text):
        report.fail("site.css must not reference remote or root-absolute resources")
    report.ok()

    if not js.is_file():
        report.fail("docs/assets/js/site.js is missing")
        return
    size = js.stat().st_size
    js_text = js.read_text(encoding="utf-8")
    report.ok()
    if size >= 6 * 1024:
        report.fail(f"site.js is {size} bytes; the budget is < 6144 bytes")
    if "http://" in js_text or "https://" in js_text:
        report.fail("site.js must not reference an external URL")

    # Contract assets. These are delivered by the Lead / figures workstream; a
    # missing one is a hard failure at commit time (they are referenced by the
    # pages), but --allow-missing-assets lets the HTML be checked before they land.
    contract_assets = (
        "docs/assets/brand/mark.svg",
        "docs/assets/brand/favicon.svg",
        "docs/assets/architecture/architecture-en-light.svg",
        "docs/assets/architecture/architecture-en-dark.svg",
        "docs/assets/figures/coverage-en.svg",
        "docs/assets/figures/sources-en.svg",
        "docs/assets/figures/event-study-en.svg",
        "docs/assets/screenshots/dashboard-desktop.png",
        "docs/assets/screenshots/dashboard-mobile.png",
        "docs/assets/screenshots/report-desktop.png",
    )
    for rel in contract_assets:
        if not (ROOT / rel).is_file():
            message = f"asset referenced by the site is missing: {rel}"
            if allow_missing:
                report.warn(message)
            else:
                report.fail(message)
        else:
            report.ok()

    for rel in GENERATED_ARTEFACTS:
        if not (ROOT / rel).is_file():
            report.fail(f"generated artefact linked by the site is missing: {rel}")
        else:
            report.ok()


def check_landing(report: Report) -> None:
    landing = ROOT / "docs/index.html"
    if not landing.is_file():
        return
    text = landing.read_text(encoding="utf-8")
    for ref in LANDING_REQUIRED_REFS:
        if ref not in text:
            report.fail(f"landing page must reference {ref}")
        else:
            report.ok()
    if 'href="report.html"' not in text:
        report.fail("landing page must link the generated report as report.html")
    if "<picture>" not in text:
        report.fail("landing page must offer the architecture diagram through <picture> (light/dark)")
    if 'aria-label="Dataset at a glance"' not in text:
        report.fail("landing page is missing the stat strip landmark label")
    for stat in ("375,378", "1,160", "1966", "6"):
        if stat not in text:
            report.fail(f"landing stat strip is missing the value {stat!r}")
    if "not a validated predictive product" not in text:
        report.fail("landing page must carry the positioning statement")
    report.ok()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--allow-missing-assets",
        action="store_true",
        help="downgrade missing contract assets to warnings (assets still being produced)",
    )
    args = parser.parse_args(argv)

    report = Report()
    for rel in PAGES:
        check_page(ROOT / rel, report, allow_missing_assets=args.allow_missing_assets)
    check_assets(report, allow_missing=args.allow_missing_assets)
    check_landing(report)

    for warning in report.warnings:
        print(f"WARN {warning}")
    for failure in report.failures:
        print(f"FAIL {failure}")
    print(
        f"\n{report.checks} check(s) passed, {len(report.failures)} failed, "
        f"{len(report.warnings)} warning(s)"
    )
    return 1 if report.failures else 0


if __name__ == "__main__":
    sys.exit(main())
