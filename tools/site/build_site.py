#!/usr/bin/env python3
"""Build the five hand-authored MedRadar site pages under ``docs/``.

The Pages site is served from the repository's ``docs/`` folder, so every URL in
these pages is **relative** (the site root is ``.../medradar/``): no root-absolute
paths, no CDN, no webfont, no analytics. Header and footer markup is defined once
in this file and injected into all five pages so the chrome cannot drift between
them; the page bodies are hand-written HTML with the facts from the repository.

This module is a build helper, not a generator of the research artefacts:
``docs/report.html`` and ``docs/dashboard.html`` are produced by ``medradar
report`` / ``medradar dashboard`` and only linked from here.

Output (all committed):

    docs/index.html                 landing page
    docs/research/index.html        research: method, results, limits
    docs/platform/index.html        platform: sources, coverage, capability matrix
    docs/explore/index.html         generated artefacts (dashboard/report/replay)
    docs/documentation/index.html   start-here cards, quickstart, reading map

Usage:
    python tools/site/build_site.py            # write the pages
    python tools/site/build_site.py --check    # verify they are up to date

Every fact on these pages is sourced to a repository file in a visible note.
Do not add a number here that is not in the repository.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DOCS = ROOT / "docs"

GITHUB = "https://github.com/ChazY11/medradar"
BLOB = GITHUB + "/blob/main/"
PAGES_URL = "https://chazy11.github.io/medradar/"

#: Primary navigation, in the order the brief fixes. ``key`` is the nav identity
#: used for ``aria-current``; the landing page has no primary-nav item of its own.
NAV = (
    ("research", "Research", "research/index.html"),
    ("platform", "Platform", "platform/index.html"),
    ("explore", "Explore", "explore/index.html"),
    ("documentation", "Documentation", "documentation/index.html"),
)

#: Secondary links used by the shared footer (four columns, per the brief).
FOOTER_COLS = (
    (
        "Platform",
        (
            ("Overview", "platform/index.html"),
            ("Architecture", "platform/index.html#architecture"),
            ("Data sources", "platform/index.html#sources"),
            ("Capability matrix", "platform/index.html#capabilities"),
        ),
    ),
    (
        "Research",
        (
            ("Research overview", "research/index.html"),
            ("Method", "research/index.html#method"),
            ("Event study", "research/index.html#event-study"),
            ("Limitations", "research/index.html#limitations"),
        ),
    ),
    (
        "Resources",
        (
            ("Explore artefacts", "explore/index.html"),
            ("Documentation", "documentation/index.html"),
            ("Dashboard", "dashboard.html"),
            ("Static report", "report.html"),
            ("Metrics JSON", "metrics.json"),
        ),
    ),
    (
        "Repository",
        (
            ("GitHub", GITHUB),
            ("Changelog", BLOB + "CHANGELOG.md"),
            ("Roadmap", BLOB + "ROADMAP.md"),
            ("Contributing", BLOB + "CONTRIBUTING.md"),
        ),
    ),
)


# --------------------------------------------------------------------- helpers
def status(kind: str, label: str | None = None) -> str:
    """Status mark + mandatory text label (implemented/limited/draft/planned)."""
    text = label or kind
    return (
        f'<span class="status status--{kind}">'
        f'<span class="status-dot" aria-hidden="true"></span>{text}</span>'
    )


def src(text: str) -> str:
    """Provenance note rendered under a number or block."""
    return f'<p class="src">{text}</p>'


def section_head(eyebrow: str, title: str, lede: str = "") -> str:
    lede_html = f'\n      <p class="lede">{lede}</p>' if lede else ""
    return (
        '  <div class="section-head">\n'
        f'    <p class="eyebrow">{eyebrow}</p>\n'
        f'    <h2 class="section-title">{title}</h2>{lede_html}\n'
        "  </div>"
    )


def page_head(eyebrow: str, title: str, lede: str, meta: str = "") -> str:
    meta_html = f'\n      <p class="page-meta">{meta}</p>' if meta else ""
    return (
        '  <section class="page-head">\n'
        '    <div class="wrap">\n'
        f'      <p class="eyebrow">{eyebrow}</p>\n'
        f'      <h1 class="h1">{title}</h1>\n'
        f'      <p class="lede">{lede}</p>{meta_html}\n'
        "    </div>\n"
        "  </section>"
    )


def header(nav_key: str, prefix: str = "", home: bool = False) -> str:
    """Sticky header: brand → site root, primary nav, version pill, GitHub.

    ``prefix`` is ``""`` for the landing page and ``"../"`` for the four pages in
    subfolders, because the site is served from a subpath and must stay relative.
    ``aria-current="page"`` is set on the matching nav item; on the landing page
    it is set on the brand link, which is the only current-page link there.
    """
    brand_current = ' aria-current="page"' if home else ""
    items = []
    for key, label, href in NAV:
        current = ' aria-current="page"' if key == nav_key else ""
        items.append(f'        <li><a href="{prefix}{href}"{current}>{label}</a></li>')
    nav_items = "\n".join(items)
    return f"""<a class="skip" href="#main">Skip to content</a>
<header class="site-header">
  <div class="wrap header-inner">
    <a class="brand" href="{prefix}index.html"{brand_current}>
      <img src="{prefix}assets/brand/mark.svg" alt="" width="26" height="26">
      <span>MedRadar</span>
    </a>
    <button class="nav-toggle" type="button" aria-expanded="true" aria-controls="site-nav">
      <span class="nav-toggle-bars" aria-hidden="true"></span> Menu
    </button>
    <nav class="nav" id="site-nav" aria-label="Primary">
      <ul>
{nav_items}
      </ul>
    </nav>
    <div class="header-actions">
      <a class="pill" href="{BLOB}CHANGELOG.md">v0.5.0</a>
      <a class="gh" href="{GITHUB}">GitHub <span aria-hidden="true">&#8599;</span></a>
    </div>
  </div>
</header>"""


def footer(prefix: str = "") -> str:
    """Shared dark footer: mission line, four link columns, provenance line."""
    columns = []
    for title, links in FOOTER_COLS:
        anchor = "f-" + title.lower()
        lis = "\n".join(
            f'          <li><a href="{href if href.startswith("http") else prefix + href}">{label}</a></li>'
            for label, href in links
        )
        columns.append(
            f'      <nav aria-labelledby="{anchor}">\n'
            f'        <p class="footer-h" id="{anchor}">{title}</p>\n'
            f"        <ul>\n{lis}\n        </ul>\n"
            f"      </nav>"
        )
    cols = "\n".join(columns)
    return f"""<footer class="site-footer">
  <div class="wrap">
    <div class="footer-top">
      <div>
        <a class="footer-brand" href="{prefix}index.html">
          <img src="{prefix}assets/brand/mark.svg" alt="" width="26" height="26">
          <span>MedRadar</span>
        </a>
        <p class="footer-mission">Research infrastructure for public medical-technology evidence: one
        auditable event store, frozen experiments with named baselines, and negative results published
        at the same size as the positive ones. Not a validated predictive product.</p>
      </div>
      <div class="footer-cols">
{cols}
      </div>
    </div>
    <div class="footer-base">
      <p>Data snapshot <b>2026-10-31</b> &middot; package <b>v0.5.0</b> &middot; MIT</p>
      <p><a href="{BLOB}docs/INDEX.md">Documentation index</a> &middot;
      <a href="{BLOB}CHANGELOG.md">Changelog</a> &middot;
      research and education, not investment advice.</p>
    </div>
  </div>
</footer>"""


def document(
    title: str, description: str, nav_key: str, body: str, prefix: str = "", home: bool = False
) -> str:
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title} &middot; MedRadar</title>
<meta name="description" content="{description}">
<meta name="color-scheme" content="light dark">
<meta name="theme-color" content="#081120">
<link rel="icon" href="{prefix}assets/brand/favicon.svg" type="image/svg+xml">
<link rel="stylesheet" href="{prefix}assets/css/site.css">
<script src="{prefix}assets/js/site.js" defer></script>
</head>
<body>
{header(nav_key, prefix=prefix, home=home)}
{body}
{footer(prefix=prefix)}
</body>
</html>
"""


# ------------------------------------------------------------------ page bodies
def landing_body() -> str:
    return """<main id="main">
  <section class="hero">
    <div class="wrap hero-inner">
      <div>
        <p class="eyebrow">Research infrastructure &middot; MIT &middot; v0.5.0</p>
        <h1 class="display">Public evidence of <span class="nowrap">medical-technology</span> change, made auditable.</h1>
        <p class="hero-copy">MedRadar collects free public regulatory, clinical-trial and
        corporate-filing evidence about device and drug makers into one event store &mdash; then
        tests, with frozen experiments, named baselines and published negative results, whether that
        evidence carries signal before the market notices.</p>
        <div class="btn-row mt-m">
          <a class="btn btn--light" href="research/index.html">Read the research</a>
          <a class="btn btn--outline-light" href="documentation/index.html#quickstart">Reproduce it</a>
        </div>
        <p class="hero-meta">
          <span class="hero-status">Research infrastructure, not a validated predictive product</span>
          <span>1,160 offline tests &middot; no network, no API key</span>
        </p>
      </div>
      <aside class="snap" aria-labelledby="snapshot-title">
        <div class="snap-head">
          <h2 class="snap-title" id="snapshot-title">Event store snapshot</h2>
          <span class="snap-flag">2026-10-31</span>
        </div>
        <div class="snap-row"><span>openFDA device 510(k)</span><b>176,466</b></div>
        <div class="snap-row"><span>openFDA device recall</span><b>59,646</b></div>
        <div class="snap-row"><span>openFDA device PMA</span><b>57,372</b></div>
        <div class="snap-row"><span>ClinicalTrials.gov v2</span><b>55,592</b></div>
        <div class="snap-row"><span>SEC EDGAR 8-K corpus</span><b>20,976</b></div>
        <div class="snap-row"><span>openFDA drugsfda</span><b>5,326</b></div>
        <p class="snap-foot"><b>375,378 events</b> &middot; six public sources &middot; 1.3 GiB SQLite<br>
        source: docs/metrics.json &rarr; meta.counts</p>
      </aside>
    </div>
  </section>

  <section class="section section--flush" aria-label="Dataset at a glance">
    <div class="wrap">
      <div class="stats">
        <div class="stat">
          <span class="stat-num">375,378</span>
          <span class="stat-label">events in the store</span>
          <p class="src">docs/metrics.json &rarr; meta.event_total</p>
        </div>
        <div class="stat">
          <span class="stat-num">6</span>
          <span class="stat-label">free public sources, no credentials</span>
          <p class="src">docs/DATA.md &rarr; sources</p>
        </div>
        <div class="stat">
          <span class="stat-num">1966&ndash;2026</span>
          <span class="stat-label">event-date coverage</span>
          <p class="src">docs/DATA.md &rarr; coverage window</p>
        </div>
        <div class="stat">
          <span class="stat-num">1,160</span>
          <span class="stat-label">offline tests (1,157 passed, 3 skipped)</span>
          <p class="src">PROJECT_STATE.yaml &rarr; tests</p>
        </div>
      </div>
    </div>
  </section>

  <section class="section" id="mission">
    <div class="wrap split split--wide-left">
      <div>
        <p class="eyebrow">What MedRadar is</p>
        <h2 class="section-title">Research infrastructure first. Claims last.</h2>
        <p class="lede mt-s">The deliverable is the engineering and the honest record: an auditable
        event store, frozen experiment artefacts with named baselines, and negative results published
        at the same size as the positive ones.</p>
        <div class="grid grid--2 mt-m">
          <article class="card">
            <h3 class="card-title">Frozen artefacts</h3>
            <p>Experiments are immutable inputs. A rerun that changes a number produces a new artefact;
            the old one stays and is cited by path.</p>
          </article>
          <article class="card">
            <h3 class="card-title">Named baselines</h3>
            <p>Every model is scored against a stated base rate &mdash; not against an unnamed default
            &mdash; so &ldquo;better&rdquo; has a definition.</p>
          </article>
          <article class="card">
            <h3 class="card-title">Explicit negative results</h3>
            <p>&ldquo;No detectable gain&rdquo; is published as the result, with its measurement, next
            to the positive table.</p>
          </article>
          <article class="card">
            <h3 class="card-title">Limitations stay visible</h3>
            <p>Nine limitations are on the repository front page; this site repeats the ones that
            change how a number may be read.</p>
          </article>
        </div>
        <p class="mt-m"><a class="link-arrow" href="research/index.html#method">How the method is fixed</a></p>
      </div>
      <aside class="callout callout--warn">
        <h3>What it is not</h3>
        <ul>
          <li><strong>Not a validated predictive product.</strong> No method in the repository has
          shown out-of-sample predictive ability.</li>
          <li><strong>Not point-in-time.</strong> All 375,378 rows carry
          <code>published_at = available_at = event_date</code>; independent public time is 0 rows.</li>
          <li><strong>Not causal and not investment advice.</strong> Difference-in-differences and
          synthetic control are roadmap items, not results.</li>
          <li><strong>Not a live service.</strong> Every page and screenshot here is a generated
          artefact from the committed snapshot.</li>
        </ul>
        <p class="src">source: README.md &rarr; Validation status and Limitations; docs/DATA.md</p>
      </aside>
    </div>
  </section>

  <section class="section section--soft" id="architecture">
    <div class="wrap">
      <div class="section-head">
        <p class="eyebrow">Platform</p>
        <h2 class="section-title">One event store, explicit boundaries.</h2>
        <p class="lede">Six sources feed one SQLite event store behind a rate-limited HTTP layer.
        Registries, analysis, statistics, the bitemporal store and the forecast registry read from it;
        reports and the dashboard publish from it. Dashed nodes are roadmap drafts and are not wired
        in.</p>
      </div>
      <figure class="figure">
        <div class="fig-media fig-media--scroll">
          <picture>
            <source media="(prefers-color-scheme: dark)" srcset="assets/architecture/architecture-en-dark.svg">
            <img src="assets/architecture/architecture-en-light.svg"
                 alt="MedRadar architecture: six public sources feed a rate-limited HTTP layer and one SQLite event store with an append-only revision ledger; company, track and product-code registries, analysis, statistics, the bitemporal store and the forecast registry read from it; generated reports and the dashboard publish from it. Roadmap drafts are drawn as unconnected dashed nodes."
                 width="1000" height="590" loading="lazy" decoding="async">
          </picture>
        </div>
        <figcaption class="figcaption">Full architecture. Light and dark variants ship together; the
        page selects one by colour scheme, and the figure can be panned horizontally on narrow screens.
        <p class="src">source: docs/assets/architecture/architecture-en-light.svg &middot; generated from the repository tree, not a mock-up</p>
        </figcaption>
      </figure>
      <p class="mt-m"><a class="link-arrow" href="platform/index.html">Platform detail: source inventory, coverage and capability matrix</a></p>
    </div>
  </section>

  <section class="section" id="capabilities">
    <div class="wrap">
      <div class="section-head">
        <p class="eyebrow">Capabilities</p>
        <h2 class="section-title">Six capabilities, each with its validation status.</h2>
        <p class="lede"><strong>implemented</strong> runs on main and is exercised by the offline
        suite; <strong>limited</strong> works with a measured, named gap; <strong>draft</strong> and
        <strong>planned</strong> are not shipped.</p>
      </div>
      <div class="grid grid--3">
        <article class="card">
          <div class="card-head"><span class="status status--implemented"><span class="status-dot" aria-hidden="true"></span>implemented</span><span class="badge">ingest</span></div>
          <h3 class="card-title">Multi-source ingest</h3>
          <p>openFDA device 510(k) / PMA / recall / classification, openFDA drug approvals,
          ClinicalTrials.gov v2 and the SEC EDGAR 8-K corpus land in one event schema; counts
          reproduce from live sources.</p>
          <span class="card-path">medradar/collect_device.py &middot; collect_drug.py &middot; clinical.py &middot; corpus.py</span>
          <div class="card-foot"><a class="link-arrow" href="platform/index.html#sources">Source inventory</a></div>
        </article>
        <article class="card">
          <div class="card-head"><span class="status status--implemented"><span class="status-dot" aria-hidden="true"></span>implemented</span><span class="badge">store</span></div>
          <h3 class="card-title">Bitemporal event store</h3>
          <p><code>event_date</code>, <code>available_at</code> and <code>timestamp_quality</code> on
          every row, plus an append-only revision ledger behind <code>events</code> &mdash; explicitly
          not tamper-proofing.</p>
          <span class="card-path">medradar/db.py &middot; medradar/evidence_core/</span>
          <div class="card-foot"><a class="link-arrow" href="research/index.html#limitations">What the ledger does not prove</a></div>
        </article>
        <article class="card">
          <div class="card-head"><span class="status status--limited"><span class="status-dot" aria-hidden="true"></span>limited</span><span class="badge">resolution</span></div>
          <h3 class="card-title">Entity resolution</h3>
          <p>35.2&nbsp;% of events carry a company key and 52.4&nbsp;% a technology track. Unmatched
          events are counted and reported, never guessed.</p>
          <span class="card-path">medradar/config.py &middot; config/*.json</span>
          <div class="card-foot"><a class="link-arrow" href="platform/index.html#coverage">Coverage quality</a></div>
        </article>
        <article class="card">
          <div class="card-head"><span class="status status--limited"><span class="status-dot" aria-hidden="true"></span>limited</span><span class="badge">analytics</span></div>
          <h3 class="card-title">Descriptive analytics</h3>
          <p>Track heat (shrinkage-adjusted rate), mix shift (Jensen&ndash;Shannon) and novelty (first
          occurrence) are descriptive, in-sample scores &mdash; not validated signals.</p>
          <span class="card-path">medradar/analyze.py</span>
          <div class="card-foot"><a class="link-arrow" href="research/index.html#event-study">Research results</a></div>
        </article>
        <article class="card">
          <div class="card-head"><span class="status status--implemented"><span class="status-dot" aria-hidden="true"></span>implemented</span><span class="badge">simulation</span></div>
          <h3 class="card-title">Event study, replay and simulated book</h3>
          <p>Direction-aligned abnormal returns with a block bootstrap, an event replay and a
          long-only simulated book. Simulation lane: in-sample, 38 trades, no out-of-sample claim.</p>
          <span class="card-path">medradar/eventstudy.py &middot; replay.py &middot; paper.py</span>
          <div class="card-foot"><a class="link-arrow" href="research/index.html#event-study">Event-study table</a></div>
        </article>
        <article class="card">
          <div class="card-head"><span class="status status--implemented"><span class="status-dot" aria-hidden="true"></span>implemented</span><span class="badge">publish</span></div>
          <h3 class="card-title">Reports and zero-dependency dashboard</h3>
          <p>A Chinese report, an English one-pager, a CSV and a self-contained dashboard are
          generated from one <code>metrics.json</code>. Generated artefacts, not a live service.</p>
          <span class="card-path">medradar/report.py &middot; docs/dashboard.html</span>
          <div class="card-foot"><a class="link-arrow" href="explore/index.html">Browse the artefacts</a></div>
        </article>
      </div>
      <p class="src">source: README.md &rarr; What is implemented, and how far it is validated;
      PROJECT_STATE.yaml &rarr; capabilities; docs/DATA.md</p>
    </div>
  </section>

  <section class="section section--soft" id="research">
    <div class="wrap">
      <div class="section-head">
        <p class="eyebrow">Research</p>
        <h2 class="section-title">What the research found &mdash; including what it failed to find.</h2>
        <p class="lede">All results are descriptive and in-sample. The negative results are the
        deliverable, not a footnote.</p>
      </div>
      <div class="grid grid--3">
        <article class="finding">
          <div class="finding-head"><span class="badge">event study</span><span class="finding-num">+5.65&nbsp;% at +60&nbsp;d</span></div>
          <h3>Only the 60-day horizon survives</h3>
          <p>n = 61, t = 2.45, 95&nbsp;% CI [+1.35&nbsp;%, +10.32&nbsp;%], Holm-corrected over the
          full category &times; horizon family. In-sample simulation, long-only, 38 simulated trades
          over ~11 months.</p>
          <p class="src">docs/metrics.json &rarr; trading.event_study; README table</p>
          <div class="card-foot"><a class="link-arrow" href="research/index.html#event-study">Read the caveat</a></div>
        </article>
        <article class="finding">
          <div class="finding-head"><span class="badge">negative result</span><span class="finding-num">&Delta; AP +0.0022</span></div>
          <h3>No added data source produced a ranking gain</h3>
          <p>Marginal PR-AUC on continuation: financial &minus;0.0013, market &minus;0.0015,
          publication &minus;0.0001, all sources &minus;0.0068. Model AP 0.7935 against a per-pair
          base rate of 0.7913. More data improved calibration (ECE 0.0811 &rarr; 0.0628), not
          ordering.</p>
          <p class="src">experiments/reverse_rd_v1/, reverse_rd_v2/; README table</p>
          <div class="card-foot"><a class="link-arrow" href="research/index.html#negative">Negative results</a></div>
        </article>
        <article class="finding">
          <div class="finding-head"><span class="badge">NO-GO</span><span class="finding-num">5 firms</span></div>
          <h3>The lead-time gate is NO-GO</h3>
          <p>The five-firm early-signal study returned CONDITIONAL-GO at Phase 0; the gate that
          matters &mdash; was the change detectable earlier &mdash; did not pass. S-028 / S-029 are
          branch-only drafts and are not presented as shipped.</p>
          <p class="src">research/<wbr>studies/<wbr>early_signal_5firms/<wbr>PHASE0_REPORT.md</p>
          <div class="card-foot"><a class="link-arrow" href="research/index.html#no-go">Read the NO-GO</a></div>
        </article>
      </div>
      <p class="src mt-m">Caveat carried with every return number: the snapshot has no independent
      public time (0 of 375,378 rows), so these are not point-in-time results and not investment
      advice.</p>
    </div>
  </section>

  <section class="section" id="artefacts">
    <div class="wrap">
      <div class="section-head">
        <p class="eyebrow">Artefacts</p>
        <h2 class="section-title">Generated from the committed snapshot, not a live service.</h2>
        <p class="lede">Every screenshot on this site is a capture of an artefact the repository
        generates; none is a mock-up and none is fabricated UI.</p>
      </div>
      <figure class="figure">
        <div class="frame">
          <div class="frame-bar">
            <span class="frame-dots" aria-hidden="true"><span></span><span></span><span></span></span>
            <span class="frame-url">dashboard.html &middot; generated from metrics.json &middot; dataset 2026-10-31 &middot; package v0.5.0</span>
          </div>
          <div class="frame-body">
            <img src="assets/screenshots/dashboard-desktop.png"
                 alt="MedRadar interactive dashboard, overview view: KPI cards, track heat and company momentum tables, generated from metrics.json, package v0.5.0, dataset snapshot 2026-10-31."
                 width="1440" height="900" loading="lazy" decoding="async">
          </div>
        </div>
        <figcaption class="figcaption">Committed snapshot &mdash; dataset 2026-10-31, package v0.5.0.
        It shows the demo views of the generated report; it is not a live service and not a forecast.
        Rebuild with <code>medradar dashboard</code>.
        <p class="src">capture: docs/assets/screenshots/dashboard-desktop.png &middot; 1440 &times; 900</p>
        </figcaption>
      </figure>
      <div class="grid grid--3 mt-m">
        <a class="card card--link" href="explore/index.html">
          <h3 class="card-title">Explore every artefact</h3>
          <p>Dashboard, static report, event replay and the research figures, with a note on how to
          read each one.</p>
          <span class="link-arrow">Open Explore</span>
        </a>
        <a class="card card--link" href="dashboard.html">
          <h3 class="card-title">Interactive dashboard</h3>
          <p>Self-contained HTML with all data inlined: tracks, companies, products, cases, replay and
          the data audit. Opens offline.</p>
          <span class="link-arrow">Open dashboard.html</span>
        </a>
        <a class="card card--link" href="report.html">
          <h3 class="card-title">Static report</h3>
          <p>The generated Chinese research report and its English one-pager, rendered as one
          self-contained page.</p>
          <span class="link-arrow">Open report.html</span>
        </a>
      </div>
    </div>
  </section>

  <section class="section section--soft" id="quickstart">
    <div class="wrap split">
      <div>
        <p class="eyebrow">Reproduce</p>
        <h2 class="section-title">Offline in under a minute.</h2>
        <p class="lede mt-s">The package installs with the standard library only. The test suite needs
        no network connection and no API key.</p>
        <ul class="steps mt-m">
          <li>
            <h3>Clone and install</h3>
            <p>Python 3.10, 3.11 and 3.12 are the CI targets.</p>
          </li>
          <li>
            <h3>Run the offline suite</h3>
            <p>1,160 collected: 1,157 passed, 3 skipped. No network, no credentials.</p>
          </li>
          <li>
            <h3>Build the demo artefact</h3>
            <p><code>medradar demo</code> writes <code>out/demo/index.html</code> from the committed
            snapshot in under 60&nbsp;s.</p>
          </li>
          <li>
            <h3>Optional live run</h3>
            <p><code>medradar run</code> needs network and takes about three minutes; still no API
            key.</p>
          </li>
        </ul>
        <p class="src">source: README.md &rarr; Reproduce; PROJECT_STATE.yaml &rarr; tests</p>
        <p class="mt-m"><a class="link-arrow" href="documentation/index.html#quickstart">Full quickstart in Documentation</a></p>
      </div>
      <div class="code-wrap">
        <div class="code-head"><span>shell</span><span>verified commands</span></div>
        <pre class="code"><code>git clone https://github.com/ChazY11/medradar.git
cd medradar &amp;&amp; pip install -e .

<span class="c-comment"># 1,160 offline tests &middot; no network &middot; no API key</span>
<span class="c-cmd">python -m pytest -q -o addopts=""</span>

<span class="c-comment"># offline demo from the committed snapshot</span>
<span class="c-cmd">medradar demo</span>

<span class="c-comment"># live radar run: network needed, ~3 minutes</span>
<span class="c-cmd">medradar run --months 24 --with-trade --with-dashboard</span></code></pre>
      </div>
    </div>
  </section>

  <section class="section" id="roadmap">
    <div class="wrap split split--wide-left">
      <div>
        <p class="eyebrow">Roadmap</p>
        <h2 class="section-title">Next, and explicitly not done.</h2>
        <p class="lede mt-s">Each open item carries the blocker that makes it open, so &ldquo;planned&rdquo;
        cannot be mistaken for &ldquo;shipped&rdquo;.</p>
        <ol class="steps mt-m">
          <li>
            <h3>Re-acquire independent public timestamps</h3>
            <p>EDGAR first: its acceptance timestamp can carry a true public instant today. Without
            this, no point-in-time claim is possible.</p>
          </li>
          <li>
            <h3>Mature enough forecast windows</h3>
            <p>The registry holds registered forecasts with no matured windows, so no calibration
            claim can be made at all.</p>
          </li>
          <li>
            <h3>Feed graph features into the models</h3>
            <p>The relation graph currently informs the research agent only, not the scoring models.</p>
          </li>
          <li>
            <h3>Patent features, once a USPTO Open Data Portal key exists</h3>
            <p>Patents were not evaluated. Procurement is excluded: its snapshot is not
            point-in-time usable.</p>
          </li>
          <li>
            <h3>NMPA CSV importer and AdCom parsing</h3>
            <p>NMPA is deliberately not scraped; the AdCom collector parses zero rows because the
            calendar is rendered client-side.</p>
          </li>
        </ol>
        <p class="src">source: README.md &rarr; Roadmap; ROADMAP.md; PROJECT_STATE.yaml</p>
      </div>
      <aside class="callout callout--warn">
        <h3>Nothing draft is presented as shipped</h3>
        <p>MedRadar 2.0 (#12), Live Observatory (#13/#14), S-028/S-029 (#15/#16), PHOENIX (#23&ndash;#26)
        and DATA-EXPANSION / ATLAS / HORIZON / CONVERGENCE (#27&ndash;#30) exist only on draft branches
        or PRs. They are not wired into this site, the dashboard, or any claim made here.</p>
        <p class="src">source: README.md &rarr; Not in main, not claimed; PROJECT_STATE.yaml &rarr; capabilities</p>
      </aside>
    </div>
  </section>

  <section class="closing" aria-labelledby="closing-title">
    <div class="wrap closing-inner">
      <div>
        <p class="eyebrow">Start here</p>
        <h2 id="closing-title">Read the method before the numbers.</h2>
        <p>The method contract, the schema and the limitation list explain what each number may be
        used for. Everything else in the repository follows from them.</p>
      </div>
      <div class="btn-row">
        <a class="btn btn--light" href="research/index.html#method">Method</a>
        <a class="btn btn--outline-light" href="platform/index.html#capabilities">Capability matrix</a>
        <a class="btn btn--outline-light" href="documentation/index.html">Documentation</a>
      </div>
    </div>
  </section>
</main>
"""


def research_body() -> str:
    return """<main id="main">
  <section class="page-head">
    <div class="wrap">
      <p class="eyebrow">Research</p>
      <h1 class="h1">What the evidence can and cannot support</h1>
      <p class="lede">One question, one event store, and a record of what the store failed to
      support. Every number below is in-sample and carries its artefact path.</p>
      <p class="page-meta"><span>package v0.5.0</span><span>dataset 2026-10-31</span><span>375,378 events</span><span>no out-of-sample claim</span></p>
    </div>
  </section>

  <section class="section section--tight">
    <div class="wrap">
      <div class="callout callout--plain">
        <h3>The question</h3>
        <p>Can publicly observable evidence give reliable early warning of meaningful change in
        medical-technology development?</p>
        <p class="src">source: README.md; research/MISSION.md</p>
      </div>
    </div>
  </section>

  <section class="section" id="method">
    <div class="wrap">
      <div class="section-head">
        <p class="eyebrow">Method</p>
        <h2 class="section-title">The method is fixed before the result is known.</h2>
        <p class="lede">Three commitments make a number quotable, and a fourth makes it honest: the
        limitation it inherits.</p>
      </div>
      <div class="grid grid--3">
        <article class="card">
          <h3 class="card-title">Frozen artefacts</h3>
          <p>Experiments are immutable inputs. A rerun that changes a number produces a new artefact;
          the old one stays and is cited by path, never edited.</p>
          <span class="card-path">experiments/reverse_rd_v1/ &middot; experiments/reverse_rd_v2/</span>
        </article>
        <article class="card">
          <h3 class="card-title">Named baselines</h3>
          <p>Every model is scored against a stated base rate &mdash; for the market-to-R&amp;D
          continuation target, a per-pair base rate of 0.7913 &mdash; never against an unnamed
          default.</p>
          <span class="card-path">docs/METHODS.md &middot; docs/SCHEMA.md</span>
        </article>
        <article class="card">
          <h3 class="card-title">Holm-corrected block bootstrap</h3>
          <p>Direction-aligned abnormal returns are bootstrapped in blocks; Holm correction runs over
          the full category &times; horizon family, so no horizon can be quoted without its
          correction.</p>
          <span class="card-path">medradar/stats.py &middot; docs/METHODS.md</span>
        </article>
      </div>
      <div class="callout callout--warn mt-m">
        <h3>The limitation the method cannot remove</h3>
        <p>The snapshot has no independent public time: <code>published_at = available_at =
        event_date</code> on 375,378 / 375,378 rows, and <code>timestamp_quality = 'date'</code>.
        Return studies therefore rest on a same-day-public-time assumption and are <strong>not</strong>
        point-in-time results.</p>
        <p class="src">source: docs/DATA.md &rarr; 时间戳质量; README.md &rarr; Limitations 1&ndash;2</p>
      </div>
    </div>
  </section>

  <section class="section section--soft" id="event-study">
    <div class="wrap">
      <div class="section-head">
        <p class="eyebrow">Result 01 &middot; event study</p>
        <h2 class="section-title">Only the 60-day horizon survives.</h2>
        <p class="lede">Direction-aligned abnormal returns over the simulated event study, block
        bootstrap, Holm-corrected over the full category &times; horizon family.</p>
      </div>
      <div class="split split--wide-left">
        <div class="table-wrap">
          <table class="data">
            <caption>Abnormal returns by horizon &mdash; in-sample simulation</caption>
            <thead>
              <tr><th scope="col">Horizon</th><th scope="col" class="num">n</th><th scope="col" class="num">Mean abnormal return</th><th scope="col" class="num">t</th><th scope="col" class="num">95&nbsp;% CI</th></tr>
            </thead>
            <tbody>
              <tr><td>+1&nbsp;d</td><td class="num">122</td><td class="num">+0.15&nbsp;%</td><td class="num">0.57</td><td class="num">[&minus;0.33&nbsp;%, +0.65&nbsp;%]</td></tr>
              <tr><td>+5&nbsp;d</td><td class="num">109</td><td class="num">&minus;0.37&nbsp;%</td><td class="num">&minus;0.92</td><td class="num">[&minus;1.17&nbsp;%, +0.42&nbsp;%]</td></tr>
              <tr><td>+20&nbsp;d</td><td class="num">89</td><td class="num">+1.14&nbsp;%</td><td class="num">1.17</td><td class="num">[&minus;0.65&nbsp;%, +3.13&nbsp;%]</td></tr>
              <tr class="is-key"><td><strong>+60&nbsp;d</strong></td><td class="num"><strong>61</strong></td><td class="num"><strong>+5.65&nbsp;%</strong></td><td class="num"><strong>2.45</strong></td><td class="num"><strong>[+1.35&nbsp;%, +10.32&nbsp;%]</strong></td></tr>
            </tbody>
          </table>
        </div>
        <div>
          <div class="callout callout--warn">
            <h3>Read this with the table</h3>
            <p>In-sample simulation, long-only, 38 simulated trades over about eleven months. No
            independent public time in the snapshot, so this is <strong>not a point-in-time
            result</strong> and not investment advice.</p>
            <p class="src">source: docs/metrics.json &rarr; trading.event_study; README table</p>
          </div>
          <p class="mt-m"><a class="link-arrow" href="../metrics.json">metrics.json (machine-readable)</a></p>
        </div>
      </div>
      <figure class="figure mt-l">
        <div class="fig-media">
          <img src="../assets/figures/event-study-en.svg"
               alt="Event-study figure: mean direction-aligned abnormal return by horizon at +1, +5, +20 and +60 days with 95 percent confidence intervals; only the +60-day interval excludes zero. In-sample simulation, package v0.5.0, dataset snapshot 2026-10-31."
               width="860" height="460" loading="lazy" decoding="async">
        </div>
        <figcaption class="figcaption">Committed snapshot &mdash; dataset 2026-10-31, package v0.5.0.
        Plot of the table above; it is not a live series and not a forecast.
        <p class="src">source: docs/assets/figures/event-study-en.svg; docs/metrics.json &rarr; trading.event_study</p>
        </figcaption>
      </figure>
    </div>
  </section>

  <section class="section" id="negative">
    <div class="wrap">
      <div class="section-head">
        <p class="eyebrow">Result 02 &middot; negative results</p>
        <h2 class="section-title">The negative results are the deliverable.</h2>
        <p class="lede">Market-to-R&amp;D lane, 12-month horizon. Frozen artefacts:
        <code>experiments/reverse_rd_v1/</code> and <code>experiments/reverse_rd_v2/</code>.</p>
      </div>
      <div class="table-wrap">
        <table class="data">
          <caption>Market-to-R&amp;D lane &mdash; what was tested and what it measured</caption>
          <thead>
            <tr><th scope="col">Tested</th><th scope="col">Measurement</th><th scope="col">Verdict</th></tr>
          </thead>
          <tbody>
            <tr>
              <td>Does any added source produce a detectable ranking gain?</td>
              <td>Marginal PR-AUC on continuation: financial &minus;0.0013, market &minus;0.0015,
              publication &minus;0.0001, all sources &minus;0.0068</td>
              <td><strong>No detectable gain</strong></td>
            </tr>
            <tr>
              <td>Does the model beat a per-pair base rate?</td>
              <td>AP 0.7935 (model) vs 0.7913 (base rate), &Delta; +0.0022, 95&nbsp;% CI
              [&minus;0.032, +0.037]</td>
              <td><strong>Barely, and not beyond the interval</strong></td>
            </tr>
            <tr>
              <td>Does more data improve ordering?</td>
              <td>ECE 0.0811 &rarr; 0.0628, FPR 0.2753 &rarr; 0.2472</td>
              <td><strong>Calibration only, not ordering</strong></td>
            </tr>
            <tr>
              <td>Is the entry target stable across windows?</td>
              <td>Differences sit inside the 0.014&ndash;0.026 window standard deviation</td>
              <td><strong>Unstable, so not claimed</strong></td>
            </tr>
            <tr class="is-muted">
              <td>Patents</td>
              <td>USPTO Open Data Portal requires an API key</td>
              <td>Not evaluated</td>
            </tr>
            <tr class="is-muted">
              <td>Procurement</td>
              <td>Snapshot is not point-in-time usable</td>
              <td>Excluded</td>
            </tr>
          </tbody>
        </table>
      </div>
      <p class="src">source: README.md &rarr; The negative results; experiments/reverse_rd_v1/,
      experiments/reverse_rd_v2/; docs/REVERSE_RD.md</p>

      <h3 class="card-title mt-l" id="e1b">Can the missing public timestamp be recovered?</h3>
      <p class="lede mt-s">The E1b source-recovery experiment tested each source for a retrospective
      public instant. This is a shape test &mdash; 28 requests, 5 records per source &mdash; not a
      population estimate.</p>
      <div class="table-wrap mt-s">
        <table class="data">
          <caption>E1b source recovery &mdash; public time by source</caption>
          <thead>
            <tr><th scope="col">Source</th><th scope="col">Retrospective public time</th><th scope="col">Verdict</th></tr>
          </thead>
          <tbody>
            <tr>
              <td>SEC EDGAR</td>
              <td><strong>Yes</strong> &mdash; <code>acceptanceDateTime</code>, immutable archive,
              amendments arrive as new accessions</td>
              <td><strong>STRONG</strong></td>
            </tr>
            <tr>
              <td>ClinicalTrials.gov</td>
              <td><strong>Partial</strong> &mdash; first-post date only, date granularity,
              <code>ACTUAL</code> records only; historical content state is not recoverable</td>
              <td><strong>MEDIUM</strong></td>
            </tr>
            <tr>
              <td>openFDA 510(k) / PMA</td>
              <td><strong>No</strong> &mdash; no public-posting field exists;
              <code>decision_date</code> is the event date, not the publication date</td>
              <td>Prospective observation only</td>
            </tr>
          </tbody>
        </table>
      </div>
      <p class="src">source: docs/refoundation/phase2/E1B_SOURCE_RECOVERY.md; README.md</p>
    </div>
  </section>

  <section class="section section--soft" id="no-go">
    <div class="wrap split split--wide-left">
      <div>
        <p class="eyebrow">Result 03 &middot; early signal</p>
        <h2 class="section-title">Five firms, and a lead-time gate that did not pass.</h2>
        <div class="findings mt-m">
          <article class="finding">
            <div class="finding-head"><span class="badge">5 firms</span><span class="finding-num">Phase 0 &middot; CONDITIONAL-GO</span></div>
            <h3>Early detection of corporate technology shifts</h3>
            <p>Phase 0 is CONDITIONAL-GO: the deep-case study can continue, but only under the
            stated conditions (sustained positive, earlier source, human adjudication).</p>
          </article>
          <article class="finding mt-s">
            <div class="finding-head"><span class="badge">lead-time gate</span><span class="finding-num">Phase 1 &middot; NO-GO</span></div>
            <h3>The change was not shown to be detectable earlier than the market</h3>
            <p>The gate that matters is the lead time. It did not pass, so the study is recorded as a
            NO-GO rather than reported as an early-warning capability.</p>
          </article>
        </div>
        <p class="src mt-m">source: research/studies/early_signal_5firms/PHASE0_REPORT.md;
        PROJECT_STATE.yaml &rarr; research_studies; docs/RESEARCH_INDEX.md</p>
      </div>
      <aside class="callout callout--warn">
        <h3>Not shipped</h3>
        <p>S-028 and S-029 are relation studies recorded as <strong>NO-GO</strong> and exist only as
        draft branches (PR #15/#16). They are not presented here as capabilities or results.</p>
        <p class="src">source: README.md &rarr; Not in main, not claimed; FACTS-level honesty rule</p>
      </aside>
    </div>
  </section>

  <section class="section" id="limitations">
    <div class="wrap split split--wide-left">
      <div>
        <p class="eyebrow">Limitations</p>
        <h2 class="section-title">Nine limitations, none of them decorative.</h2>
        <p class="lede mt-s">These change how every number on this page may be read.</p>
        <ol class="steps mt-m">
          <li><h3>Event time only</h3><p><code>published_at = available_at = event_date</code> for
          375,378 / 375,378 rows; independent public time = 0 rows.</p></li>
          <li><h3>No genuine point-in-time claim</h3><p>Unsupported until source publication
          timestamps are re-acquired.</p></li>
          <li><h3>Partial entity resolution</h3><p>35.2&nbsp;% company key, 52.4&nbsp;% track;
          unmatched events are counted, never guessed.</p></li>
          <li><h3>The revision ledger is not tamper-proofing</h3><p>It records the application write
          path; a database owner can still replace the file.</p></li>
          <li><h3>510(k)/PMA rows carry no public timestamp</h3><p>They enter industry counts and
          never return studies &mdash; a deliberate loss of sample.</p></li>
          <li><h3>The AdCom collector parses zero rows</h3><p>The calendar is rendered client-side; it
          returns <code>empty</code> / <code>source_changed</code>, never a silent
          <code>ok</code>.</p></li>
          <li><h3>The simulated book is in-sample and long-only</h3><p>38 trades; shorts are alerted
          but never traded; fees, squeeze-outs and delisting are unmodelled.</p></li>
          <li><h3>No causal claims</h3><p>Difference-in-differences and synthetic control are roadmap
          items, not results.</p></li>
          <li><h3>NMPA is deliberately not scraped</h3><p>Without a user-supplied CSV every China
          value is <code>null</code>, never zero.</p></li>
        </ol>
        <p class="src">source: README.md &rarr; Limitations; docs/ASSUMPTIONS.md; docs/METHODS.md</p>
      </div>
      <aside>
        <div class="callout callout--plain">
          <h3>Where the record lives</h3>
          <ul>
            <li><a href="https://github.com/ChazY11/medradar/blob/main/docs/RESEARCH.md">docs/RESEARCH.md</a> &mdash; current research protocol</li>
            <li><a href="https://github.com/ChazY11/medradar/blob/main/docs/RESEARCH_INDEX.md">docs/RESEARCH_INDEX.md</a> &mdash; generated study and decision index</li>
            <li><a href="https://github.com/ChazY11/medradar/blob/main/docs/METHODS.md">docs/METHODS.md</a> &mdash; metric definitions and threats to validity</li>
            <li><a href="https://github.com/ChazY11/medradar/blob/main/research/RESULTS/README.md">research/RESULTS/</a> &mdash; per-cycle result notes, append-only</li>
            <li><a href="https://github.com/ChazY11/medradar/blob/main/papers/README.md">papers/</a> &mdash; drafts, not submitted or peer reviewed</li>
            <li><a href="../metrics.json">metrics.json</a> &mdash; the machine-readable contract behind this page</li>
          </ul>
        </div>
        <div class="callout callout--plain mt-m">
          <h3>Canonical-claims rule</h3>
          <p>A number is quotable only if it appears in a frozen artefact and has evidence for its
          timestamp basis. Otherwise it is a descriptive statistic and is labelled as one.</p>
          <p class="src">source: docs/INDEX.md &rarr; 2.2 Canonical-claims rule</p>
        </div>
      </aside>
    </div>
  </section>
</main>
"""


def platform_body() -> str:
    return """<main id="main">
  <section class="page-head">
    <div class="wrap">
      <p class="eyebrow">Platform</p>
      <h1 class="h1">The machinery behind the numbers</h1>
      <p class="lede">One event store, six free sources, a rate-limited HTTP layer and generated
      artefacts. Every boundary below is deliberate, including the parts that are absent.</p>
      <p class="page-meta"><span>375,378 events</span><span>6 sources</span><span>1.3 GiB SQLite</span><span>dataset 2026-10-31</span></p>
    </div>
  </section>

  <section class="section" id="architecture">
    <div class="wrap">
      <div class="section-head">
        <p class="eyebrow">Architecture</p>
        <h2 class="section-title">Solid edges ship. Dashed nodes do not.</h2>
        <p class="lede">Sources &rarr; HTTP layer &rarr; event store &rarr; registries, analysis,
        statistics, bitemporal store, forecast registry &rarr; reports and dashboard. Roadmap drafts
        are drawn as unconnected dashed nodes and are not wired in.</p>
      </div>
      <figure class="figure">
        <div class="fig-media fig-media--scroll">
          <picture>
            <source media="(prefers-color-scheme: dark)" srcset="../assets/architecture/architecture-en-dark.svg">
            <img src="../assets/architecture/architecture-en-light.svg"
                 alt="MedRadar platform architecture: six public sources feed a rate-limited HTTP layer and one SQLite event store with an append-only revision ledger; company, track and product-code registries, analysis, statistics, the bitemporal store and the forecast registry read from it; generated reports and the dashboard publish from it. Roadmap drafts are drawn as unconnected dashed nodes."
                 width="1000" height="590" loading="lazy" decoding="async">
          </picture>
        </div>
        <figcaption class="figcaption">Light and dark variants ship together; the page selects one by
        colour scheme. The figure can be panned horizontally on narrow screens.
        <p class="src">source: docs/assets/architecture/architecture-en-light.svg; README.md &rarr; Architecture</p>
        </figcaption>
      </figure>
    </div>
  </section>

  <section class="section section--soft" id="sources">
    <div class="wrap">
      <div class="section-head">
        <p class="eyebrow">Sources</p>
        <h2 class="section-title">Six free public sources, no credentials.</h2>
        <p class="lede">Row counts and event-date windows are from the committed data audit for the
        2026-10-31 snapshot. The SQLite snapshot itself is not committed.</p>
      </div>
      <div class="table-wrap">
        <table class="data">
          <caption>Source inventory &mdash; dataset snapshot 2026-10-31</caption>
          <thead>
            <tr><th scope="col">Source</th><th scope="col">Kind</th><th scope="col" class="num">Rows</th><th scope="col">Event-date window</th></tr>
          </thead>
          <tbody>
            <tr><td>openFDA device 510(k)</td><td><code>510k</code></td><td class="num">176,466</td><td>1976-07-15 &rarr; 2026-10-18</td></tr>
            <tr><td>openFDA device recall</td><td><code>device_recall</code></td><td class="num">59,646</td><td>2002-11-01 &rarr; 2026-10-28</td></tr>
            <tr><td>openFDA device PMA</td><td><code>pma</code></td><td class="num">57,372</td><td>1968-10-09 &rarr; 2026-10-16</td></tr>
            <tr><td>ClinicalTrials.gov v2</td><td><code>trial</code></td><td class="num">55,592</td><td>1999-10-19 &rarr; 2026-10-30</td></tr>
            <tr><td>SEC EDGAR 8-K corpus</td><td><code>8k_catalyst</code></td><td class="num">20,976</td><td>2015-01-02 &rarr; 2026-10-30</td></tr>
            <tr><td>openFDA drugsfda</td><td><code>drug_approval</code></td><td class="num">5,326</td><td>1966-12-14 &rarr; 2026-10-22</td></tr>
            <tr class="is-key"><td><strong>Total</strong></td><td>&mdash;</td><td class="num"><strong>375,378</strong></td><td>1966-12-14 &rarr; 2026-10-30</td></tr>
          </tbody>
        </table>
      </div>
      <p class="src">source: docs/DATA.md &rarr; sources and coverage windows; docs/metrics.json
      &rarr; meta.counts (source counts sum to the event total)</p>
      <figure class="figure mt-l">
        <div class="fig-media">
          <img src="../assets/figures/sources-en.svg"
               alt="Source inventory figure: rows per source for the 2026-10-31 snapshot, with openFDA device 510(k) the largest at 176,466 rows and openFDA drugsfda the smallest at 5,326."
               width="860" height="420" loading="lazy" decoding="async">
        </div>
        <figcaption class="figcaption">Committed snapshot &mdash; dataset 2026-10-31, package v0.5.0.
        Generated from the same counts as the table.
        <p class="src">source: docs/assets/figures/sources-en.svg; docs/DATA.md</p>
        </figcaption>
      </figure>
    </div>
  </section>

  <section class="section" id="coverage">
    <div class="wrap">
      <div class="section-head">
        <p class="eyebrow">Coverage quality</p>
        <h2 class="section-title">What is joined, and what is honestly missing.</h2>
        <p class="lede">Coverage is reported as a share of events with the plain-language meaning next
        to it. Missing is reported as missing, never as zero.</p>
      </div>
      <div class="table-wrap">
        <table class="data">
          <caption>Coverage quality &mdash; dataset snapshot 2026-10-31</caption>
          <thead>
            <tr><th scope="col">Signal</th><th scope="col" class="num">Rows</th><th scope="col" class="num">Share</th><th scope="col">What it means</th></tr>
          </thead>
          <tbody>
            <tr><td>Company key resolved</td><td class="num">132,293</td><td class="num">35.2&nbsp;%</td><td>About one event in three can be tied to a company. The rest are counted as unmatched.</td></tr>
            <tr><td>Technology track resolved</td><td class="num">196,542</td><td class="num">52.4&nbsp;%</td><td>About half of events carry a track. Track-level aggregates are therefore half-blind.</td></tr>
            <tr><td>Product code present</td><td class="num">290,909</td><td class="num">77.5&nbsp;%</td><td>Most device rows carry a product code, which is what the product families are built from.</td></tr>
            <tr><td>Timestamp quality <code>date</code></td><td class="num">375,378</td><td class="num">100&nbsp;%</td><td>Day resolution everywhere; no row carries a time-of-day publication instant.</td></tr>
            <tr class="is-key"><td><strong>Independent public time</strong></td><td class="num"><strong>0</strong></td><td class="num"><strong>0&nbsp;%</strong></td><td><code>published_at = available_at = event_date</code> on every row. This is the constraint behind every return caveat.</td></tr>
          </tbody>
        </table>
      </div>
      <p class="src">source: docs/DATA.md &rarr; 覆盖质量; docs/metrics.json</p>
      <div class="split mt-l">
        <figure class="figure">
          <div class="fig-media">
            <img src="../assets/figures/coverage-en.svg"
                 alt="Coverage figure: company key resolved on 35.2 percent of events, technology track on 52.4 percent, product code on 77.5 percent, and independent public time on 0 rows out of 375,378."
                 width="860" height="420" loading="lazy" decoding="async">
          </div>
          <figcaption class="figcaption">Coverage shares, including the zero. Dataset 2026-10-31,
          package v0.5.0.
          <p class="src">source: docs/assets/figures/coverage-en.svg; docs/DATA.md</p>
          </figcaption>
        </figure>
        <div>
          <h3 class="card-title">Registry and price layers</h3>
          <dl class="kv mt-s">
            <div><dt>Companies</dt><dd><strong>89</strong> &mdash; 81 with a ticker, 43 in the focus set</dd></div>
            <div><dt>Technology tracks</dt><dd><strong>60</strong></dd></div>
            <div><dt>Product codes</dt><dd><strong>7,097</strong> &mdash; 1,958 mapped to a track (27.6&nbsp;%)</dd></div>
            <div><dt>Prices</dt><dd><strong>1,898,409</strong> rows &middot; 1,017 tickers &middot; 2016-10-31 &rarr; 2026-10-30</dd></div>
            <div><dt>Signals</dt><dd><strong>127</strong></dd></div>
          </dl>
          <p class="src">source: docs/DATA.md; docs/metrics.json</p>
        </div>
      </div>
    </div>
  </section>

  <section class="section section--soft" id="capabilities">
    <div class="wrap">
      <div class="section-head">
        <p class="eyebrow">Capability matrix</p>
        <h2 class="section-title">Status, evidence path, and the caveat that travels with it.</h2>
        <p class="lede">The site vocabulary maps to the repository's generated one:
        <strong>implemented</strong> = <em>working</em>; <strong>limited</strong> = working with a
        measured gap or mechanism only; <strong>draft</strong> = branch-only; <strong>planned</strong>
        = not started.</p>
      </div>
      <ul class="legend">
        <li>""" + status("implemented") + """<span class="legend-note">Runs on main and is exercised by the offline test suite.</span></li>
        <li>""" + status("limited") + """<span class="legend-note">Works, but a named gap limits what it can support (partial resolution, descriptive only, mechanism only).</span></li>
        <li>""" + status("draft") + """<span class="legend-note">Exists only on a draft branch or PR. Not shipped and not wired in.</span></li>
        <li>""" + status("planned") + """<span class="legend-note">Roadmap item with an explicit blocker. No code path claimed.</span></li>
      </ul>
      <div class="table-wrap mt-l">
        <table class="data">
          <caption>Capability matrix &mdash; repository evidence and validation note</caption>
          <thead>
            <tr><th scope="col">Capability</th><th scope="col">Status</th><th scope="col">Evidence</th><th scope="col">Validation note</th></tr>
          </thead>
          <tbody>
            <tr><td>Ingest: openFDA device/drug, ClinicalTrials.gov, SEC 8-K</td><td>""" + status("implemented") + """</td><td><code>medradar/collect_*.py</code>, <code>intelligence/</code></td><td>Counts reproduce from live sources.</td></tr>
            <tr><td>Event store with bitemporal fields</td><td>""" + status("implemented") + """</td><td><code>medradar/db.py</code></td><td>Every row carries event date, availability and quality; 0 rows of independent public time.</td></tr>
            <tr><td>Append-only revision ledger</td><td>""" + status("implemented") + """</td><td><code>medradar/evidence_core/</code></td><td>Records the application write path; explicitly <strong>not</strong> tamper-proofing.</td></tr>
            <tr><td>Company / track / product-code resolution</td><td>""" + status("limited") + """</td><td><code>medradar/config.py</code>, <code>config/*.json</code></td><td>35.2&nbsp;% company key, 52.4&nbsp;% track; unmatched counted, never guessed.</td></tr>
            <tr><td>Descriptive analytics: heat, mix shift, novelty</td><td>""" + status("limited") + """</td><td><code>medradar/analyze.py</code></td><td>Descriptive, in-sample scores; no out-of-sample validation.</td></tr>
            <tr><td>Event study, replay, simulated long-only book</td><td>""" + status("implemented") + """</td><td><code>medradar/eventstudy.py</code>, <code>replay.py</code>, <code>paper.py</code></td><td>Working <em>as simulation</em>: in-sample, 38 trades, not investment advice.</td></tr>
            <tr><td>Bitemporal knowledge store</td><td>""" + status("limited") + """</td><td><code>medradar/tkg/</code></td><td>Mechanism only: the imported history has no independent public clock.</td></tr>
            <tr><td>Forecast registry with as-of scoring</td><td>""" + status("limited") + """</td><td><code>medradar/forecast_registry.py</code></td><td>Mechanism only: 25 registered forecasts, 0 matured; calibration state <code>insufficient_matured_forecasts</code>.</td></tr>
            <tr><td>Deterministic evidence-grounded research agent</td><td>""" + status("implemented") + """</td><td><code>medradar/research_agent.py</code></td><td>Retrieval-and-citation workflow; establishes no causality.</td></tr>
            <tr><td>Reports and zero-dependency dashboard</td><td>""" + status("implemented") + """</td><td><code>medradar/report.py</code>, <code>docs/dashboard.html</code></td><td>Generated artefacts, not a live service.</td></tr>
            <tr><td>FDA AdCom collector</td><td>""" + status("limited") + """</td><td><code>medradar/adcom.py</code></td><td>Parses zero rows (client-side calendar); returns <code>empty</code> / <code>source_changed</code>.</td></tr>
            <tr><td>CLI, offline demo and selftest</td><td>""" + status("implemented") + """</td><td><code>medradar/__main__.py</code></td><td>1,160 offline tests, no network, no API key.</td></tr>
            <tr class="is-muted"><td>Market-to-R&amp;D lane</td><td>""" + status("draft") + """</td><td><code>docs/MARKET_DATA.md</code>, <code>experiments/</code></td><td>Recorded as a draft capability; its frozen artefacts and negative result are public.</td></tr>
            <tr class="is-muted"><td>Publication / patent lane</td><td>""" + status("draft") + """</td><td><code>docs/PUBLICATION_PATENT_DATA.md</code></td><td>OpenAlex counts evaluated; the US patent path is key-gated and not evaluated.</td></tr>
            <tr class="is-muted"><td>Early-signal study (5 firms)</td><td>""" + status("draft") + """</td><td><code>research/studies/early_signal_5firms/</code></td><td>Phase 0 CONDITIONAL-GO; lead-time gate NO-GO; no public claim.</td></tr>
            <tr class="is-muted"><td>Paper drafts with claim maps</td><td>""" + status("draft") + """</td><td><code>papers/</code></td><td>Not submitted, not peer reviewed.</td></tr>
            <tr class="is-muted"><td>Weekly forecast-cycle workflow</td><td>""" + status("draft") + """</td><td><code>.github/workflows/forecast-cycle.yml</code></td><td>Committed; not executed in the authoring environment.</td></tr>
            <tr class="is-muted"><td>Live observatory lane</td><td>""" + status("draft") + """</td><td><code>medradar/live.py</code></td><td>Paper trading only; not investment advice.</td></tr>
            <tr class="is-muted"><td>Re-acquire independent public timestamps</td><td>""" + status("planned") + """</td><td>README.md &rarr; Roadmap</td><td>The prerequisite for any point-in-time claim. EDGAR first.</td></tr>
            <tr class="is-muted"><td>Graph features in the scoring models</td><td>""" + status("planned") + """</td><td>README.md &rarr; Roadmap</td><td>The relation graph informs the agent only, not the models.</td></tr>
            <tr class="is-muted"><td>Difference-in-differences / synthetic control</td><td>""" + status("planned") + """</td><td>README.md &rarr; Roadmap</td><td>No causal claim is made anywhere in the repository.</td></tr>
          </tbody>
        </table>
      </div>
      <p class="src">source: README.md &rarr; What is implemented; PROJECT_STATE.yaml &rarr;
      capabilities (7 working &middot; 6 draft &middot; 1 retired); docs/DATA.md</p>
    </div>
  </section>

  <section class="section" id="absent">
    <div class="wrap">
      <div class="section-head">
        <p class="eyebrow">Deliberately absent</p>
        <h2 class="section-title">The most important part of the matrix is the hole.</h2>
        <p class="lede">A capability that is missing because the data cannot support it is a design
        decision. Each hole below has a stated reason.</p>
      </div>
      <div class="grid grid--2">
        <div class="callout callout--warn">
          <h3>Drafts, not features</h3>
          <p>Six capabilities are recorded as <em>draft</em> in <code>PROJECT_STATE.yaml</code>, and the
          lanes tracked in PRs #12&ndash;#30 are branch-only. None is served by this site and none is
          presented as a capability.</p>
          <p class="src">source: PROJECT_STATE.yaml; README.md &rarr; Not in main, not claimed</p>
        </div>
        <div class="callout callout--plain">
          <h3>Retired on purpose</h3>
          <p>The monthly-resolution deployment detector was retired by decision D-045: at roughly 0.2
          events per cell-month, a monthly detector cannot resolve a change. The deployment resolution
          is quarterly.</p>
          <p class="src">source: PROJECT_STATE.yaml &rarr; capabilities (retired); research/DECISIONS.md</p>
        </div>
        <div class="callout callout--plain">
          <h3>Not evaluated or excluded</h3>
          <ul>
            <li><strong>Patents</strong> &mdash; USPTO Open Data Portal requires a key; not evaluated.</li>
            <li><strong>Procurement</strong> &mdash; excluded: the snapshot is not point-in-time usable.</li>
            <li><strong>NMPA (China)</strong> &mdash; deliberately not scraped; values are <code>null</code>, never zero.</li>
            <li><strong>AdCom</strong> &mdash; parses zero rows because the calendar is client-side.</li>
          </ul>
          <p class="src">source: README.md &rarr; Limitations 5, 6, 9; docs/PUBLICATION_PATENT_DATA.md</p>
        </div>
        <div class="callout callout--ok">
          <h3>What does work, end to end</h3>
          <p>The offline path works from a clean clone with no network: install, run 1,160 tests, build
          the demo artefact, and read the generated report and dashboard. That is the reproducible
          claim this project stands behind.</p>
          <p class="src">source: README.md &rarr; Reproduce; PROJECT_STATE.yaml &rarr; tests</p>
        </div>
      </div>
    </div>
  </section>

  <section class="section section--soft" id="reproduction">
    <div class="wrap split">
      <div>
        <p class="eyebrow">Reproduction</p>
        <h2 class="section-title">Reproduce the procedure, not the numbers.</h2>
        <p class="lede mt-s">The 1.3&nbsp;GiB SQLite snapshot is intentionally not committed, so a clean
        clone rebuilds the pipeline and the artefact formats, not the exact counts.</p>
        <p class="src">source: README.md &rarr; Reproduce; PROJECT_STATE.yaml &rarr; tests</p>
        <div class="note mt-m">
          <strong>Frozen studies</strong> rebuild with the artefacts in
          <code>experiments/reverse_rd_v1/</code> and <code>experiments/reverse_rd_v2/</code>. Every
          metric definition is in <code>docs/METHODS.md</code> and the data contract is
          <code>docs/SCHEMA.md</code>; change those before changing a number.
        </div>
      </div>
      <div class="code-wrap">
        <div class="code-head"><span>shell</span><span>verified commands</span></div>
        <pre class="code"><code>git clone https://github.com/ChazY11/medradar.git
cd medradar &amp;&amp; pip install -e .

<span class="c-comment"># offline: no network, no API key</span>
<span class="c-cmd">python -m pytest -q -o addopts=""</span>
<span class="c-cmd">medradar demo</span>

<span class="c-comment"># live radar run: network needed, no API key</span>
<span class="c-cmd">medradar run --months 24 --with-trade --with-dashboard</span>

<span class="c-comment"># frozen market-to-R&amp;D study</span>
<span class="c-cmd">python experiments/reverse_rd_v2/run_v2.py \
  --db data/medradar.sqlite --holdouts 3</span></code></pre>
      </div>
    </div>
  </section>
</main>
"""


def explore_body() -> str:
    return """<main id="main">
  <section class="page-head">
    <div class="wrap">
      <p class="eyebrow">Explore</p>
      <h1 class="h1">Generated artefacts, not a live service</h1>
      <p class="lede">Everything here was generated from the committed 2026-10-31 snapshot with package
      v0.5.0. Open the interactive pages, or read the machine-readable contract behind them.</p>
      <p class="page-meta"><span>dataset 2026-10-31</span><span>package v0.5.0</span><span>built offline</span></p>
    </div>
  </section>

  <section class="section section--tight">
    <div class="wrap">
      <figure class="figure">
        <div class="frame">
          <div class="frame-bar">
            <span class="frame-dots" aria-hidden="true"><span></span><span></span><span></span></span>
            <span class="frame-url">dashboard.html &middot; overview view &middot; dataset 2026-10-31 &middot; package v0.5.0</span>
          </div>
          <div class="frame-body">
            <img src="../assets/screenshots/dashboard-desktop.png"
                 alt="MedRadar interactive dashboard, overview view: KPI cards, track heat and company momentum tables, generated from metrics.json, package v0.5.0, dataset snapshot 2026-10-31."
                 width="1440" height="900" loading="lazy" decoding="async">
          </div>
        </div>
        <figcaption class="figcaption">Committed snapshot &mdash; dataset 2026-10-31, package v0.5.0.
        Demo views of the generated dashboard; not a live service and not a forecast. Rebuild with
        <code>medradar dashboard</code>.
        <p class="src">capture: docs/assets/screenshots/dashboard-desktop.png &middot; 1440 &times; 900</p>
        </figcaption>
      </figure>
    </div>
  </section>

  <section class="section" id="artefacts">
    <div class="wrap">
      <div class="section-head">
        <p class="eyebrow">Artefact index</p>
        <h2 class="section-title">Five artefacts, one contract.</h2>
        <p class="lede">All five are generated from the same <code>metrics.json</code>, so they cannot
        disagree with each other by construction.</p>
      </div>
      <div class="grid grid--cards">
        <a class="card card--link" href="../dashboard.html">
          <div class="card-head"><span class="badge">interactive</span><span class="badge">self-contained</span></div>
          <h3 class="card-title">Dashboard</h3>
          <p>Single-page app with all data inlined: overview KPIs, track heat, company momentum,
          product families, cases, replay and the data audit. Works offline in a browser.</p>
          <span class="link-arrow">dashboard.html</span>
        </a>
        <a class="card card--link" href="../report.html">
          <div class="card-head"><span class="badge">generated report</span></div>
          <h3 class="card-title">Static report</h3>
          <p>The Chinese research report and the English one-pager as one self-contained page, with the
          data-status, heat, structural-migration, cases and method chapters.</p>
          <span class="link-arrow">report.html</span>
        </a>
        <a class="card card--link" href="../replay.html">
          <div class="card-head"><span class="badge">replay</span></div>
          <h3 class="card-title">Event replay</h3>
          <p>Step-by-step replay of the research window: what the store knew at each step, and what the
          simulated book did with it.</p>
          <span class="link-arrow">replay.html</span>
        </a>
        <a class="card card--link" href="../metrics.json">
          <div class="card-head"><span class="badge">contract</span></div>
          <h3 class="card-title">metrics.json</h3>
          <p>The machine-readable data contract every artefact is rendered from. Change the definitions
          in <code>docs/SCHEMA.md</code> before changing a metric.</p>
          <span class="link-arrow">metrics.json</span>
        </a>
        <a class="card card--link" href="https://github.com/ChazY11/medradar/blob/main/docs/CASES.md">
          <div class="card-head"><span class="badge">case library</span></div>
          <h3 class="card-title">Cases</h3>
          <p>The case-library definition and the extreme-return audit behind the selected and negative
          example cards in the dashboard.</p>
          <span class="link-arrow">docs/CASES.md</span>
        </a>
        <a class="card card--link" href="https://github.com/ChazY11/medradar/blob/main/docs/DATA.md">
          <div class="card-head"><span class="badge">audit</span></div>
          <h3 class="card-title">Data audit</h3>
          <p>Generated counts, timestamps, freshness and database size for the snapshot behind every
          artefact on this page.</p>
          <span class="link-arrow">docs/DATA.md</span>
        </a>
      </div>
    </div>
  </section>

  <section class="section section--soft" id="mobile">
    <div class="wrap">
      <div class="section-head">
        <p class="eyebrow">Responsive artefact</p>
        <h2 class="section-title">The dashboard on a 390&nbsp;px screen.</h2>
        <p class="lede">The same generated artefact, captured at mobile width. No separate mobile build
        exists, so this is the real layout, not a mock-up.</p>
      </div>
      <div class="shots">
        <figure class="figure">
          <div class="frame">
            <div class="frame-bar">
              <span class="frame-dots" aria-hidden="true"><span></span><span></span><span></span></span>
              <span class="frame-url">report.html &middot; static report &middot; dataset 2026-10-31</span>
            </div>
            <div class="frame-body">
              <img src="../assets/screenshots/report-desktop.png"
                   alt="MedRadar static report, desktop capture: chapter navigation with the data-status, track-heat and structural-migration sections, package v0.5.0, dataset snapshot 2026-10-31."
                   width="1440" height="900" loading="lazy" decoding="async">
            </div>
          </div>
          <figcaption class="figcaption">Static report capture &mdash; dataset 2026-10-31, package
          v0.5.0. Rebuild with <code>medradar report</code>.
          <p class="src">capture: docs/assets/screenshots/report-desktop.png &middot; 1440 &times; 900</p>
          </figcaption>
        </figure>
        <figure class="figure shots-side">
          <div class="frame">
            <div class="frame-bar">
              <span class="frame-dots" aria-hidden="true"><span></span><span></span><span></span></span>
              <span class="frame-url">dashboard.html &middot; 390&nbsp;px</span>
            </div>
            <div class="frame-body">
              <img src="../assets/screenshots/dashboard-mobile.png"
                   alt="MedRadar dashboard captured at 390 by 844 pixels: stacked KPI cards and a single-column track table, package v0.5.0, dataset snapshot 2026-10-31."
                   width="390" height="844" loading="lazy" decoding="async">
            </div>
          </div>
          <figcaption class="figcaption">Mobile capture &mdash; same artefact, 390 &times; 844.
          <p class="src">capture: docs/assets/screenshots/dashboard-mobile.png</p>
          </figcaption>
        </figure>
      </div>
    </div>
  </section>

  <section class="section" id="figures">
    <div class="wrap">
      <div class="section-head">
        <p class="eyebrow">Research figures</p>
        <h2 class="section-title">The same facts, drawn once.</h2>
        <p class="lede">Versioned SVG figures generated from the committed metrics, used on the research
        and platform pages.</p>
      </div>
      <div class="grid grid--3">
        <figure class="figure">
          <div class="fig-media">
            <img src="../assets/figures/event-study-en.svg"
                 alt="Event-study figure: mean direction-aligned abnormal return at +1, +5, +20 and +60 days with 95 percent confidence intervals; only the +60-day interval excludes zero."
                 width="860" height="460" loading="lazy" decoding="async">
          </div>
          <figcaption class="figcaption">Event study &mdash; in-sample simulation.
          <p class="src">source: docs/metrics.json &rarr; trading.event_study</p>
          </figcaption>
        </figure>
        <figure class="figure">
          <div class="fig-media">
            <img src="../assets/figures/coverage-en.svg"
                 alt="Coverage figure: company key resolved on 35.2 percent of events, technology track on 52.4 percent, product code on 77.5 percent, independent public time on 0 rows."
                 width="860" height="460" loading="lazy" decoding="async">
          </div>
          <figcaption class="figcaption">Coverage quality &mdash; including the zero.
          <p class="src">source: docs/DATA.md</p>
          </figcaption>
        </figure>
        <figure class="figure">
          <div class="fig-media">
            <img src="../assets/figures/sources-en.svg"
                 alt="Source inventory figure: rows per source for the 2026-10-31 snapshot, 510(k) largest at 176,466 rows."
                 width="860" height="420" loading="lazy" decoding="async">
          </div>
          <figcaption class="figcaption">Source inventory &mdash; six free public sources.
          <p class="src">source: docs/DATA.md; docs/metrics.json</p>
          </figcaption>
        </figure>
      </div>
    </div>
  </section>

  <section class="section section--tight">
    <div class="wrap">
      <div class="callout callout--plain">
        <h3>How to read these artefacts</h3>
        <ul>
          <li><strong>They are generated, not live.</strong> Each page was written by a command against
          the committed snapshot; nothing on this site is a live feed or a forecast.</li>
          <li><strong>The snapshot is not committed.</strong> <code>data/</code> is gitignored (1.3&nbsp;GiB
          SQLite), so a clean clone reproduces the procedure and the formats, not the exact numbers.</li>
          <li><strong>Every figure carries its unit and window.</strong> Event-date windows are on the
          Platform page; return numbers stay in-sample and inherit the no-public-time caveat.</li>
          <li><strong>Rebuild:</strong> <code>medradar dashboard</code>, <code>medradar report</code>,
          <code>medradar replay</code> &mdash; all offline, all from <code>metrics.json</code>.</li>
        </ul>
        <p class="src">source: README.md &rarr; The dashboard snapshot, Reproduce; docs/DATA.md</p>
      </div>
    </div>
  </section>
</main>
"""


def documentation_body() -> str:
    return """<main id="main">
  <section class="page-head">
    <div class="wrap">
      <p class="eyebrow">Documentation</p>
      <h1 class="h1">Read the record, not a summary of it</h1>
      <p class="lede">The canonical documents live in the repository. This page only routes to them
      &mdash; it deliberately does not copy them, so a number cannot drift between two pages.</p>
      <p class="page-meta"><span>package v0.5.0</span><span>MIT</span><span>1,160 offline tests</span></p>
    </div>
  </section>

  <section class="section" id="start-here">
    <div class="wrap">
      <div class="section-head">
        <p class="eyebrow">Start here</p>
        <h2 class="section-title">Six documents that fix the contract.</h2>
        <p class="lede">Read them in this order if you intend to quote a number.</p>
      </div>
      <div class="grid grid--3">
        <a class="card card--link" href="https://github.com/ChazY11/medradar/blob/main/README.md">
          <div class="card-head"><span class="badge">01</span><span class="badge">front page</span></div>
          <h3 class="card-title">README</h3>
          <p>Mission, validation status, what is implemented, the results including the negative ones,
          the nine limitations and the reproduce commands.</p>
          <span class="link-arrow">README.md</span>
        </a>
        <a class="card card--link" href="https://github.com/ChazY11/medradar/blob/main/docs/INDEX.md">
          <div class="card-head"><span class="badge">02</span><span class="badge">navigation</span></div>
          <h3 class="card-title">INDEX</h3>
          <p>Where the canonical version of each thing lives, what state it is in, and what has been
          superseded. It links; it does not copy.</p>
          <span class="link-arrow">docs/INDEX.md</span>
        </a>
        <a class="card card--link" href="https://github.com/ChazY11/medradar/blob/main/docs/METHODS.md">
          <div class="card-head"><span class="badge">03</span><span class="badge">method</span></div>
          <h3 class="card-title">METHODS</h3>
          <p>Metric definitions, estimators, multiple-testing correction and threats to validity. A new
          metric updates this file before it updates any output.</p>
          <span class="link-arrow">docs/METHODS.md</span>
        </a>
        <a class="card card--link" href="https://github.com/ChazY11/medradar/blob/main/docs/DATA.md">
          <div class="card-head"><span class="badge">04</span><span class="badge">generated</span></div>
          <h3 class="card-title">DATA</h3>
          <p>The generated data audit: counts per source, coverage by year, timestamp quality,
          freshness and database size.</p>
          <span class="link-arrow">docs/DATA.md</span>
        </a>
        <a class="card card--link" href="https://github.com/ChazY11/medradar/blob/main/docs/SCHEMA.md">
          <div class="card-head"><span class="badge">05</span><span class="badge">contract</span></div>
          <h3 class="card-title">SCHEMA</h3>
          <p>The <code>metrics.json</code> and report contract. Change this file before changing a
          metric, or the artefacts will disagree.</p>
          <span class="link-arrow">docs/SCHEMA.md</span>
        </a>
        <a class="card card--link" href="https://github.com/ChazY11/medradar/blob/main/docs/governance/GOVERNANCE.md">
          <div class="card-head"><span class="badge">06</span><span class="badge">gates</span></div>
          <h3 class="card-title">GOVERNANCE</h3>
          <p>The state source, the local gates and the freeze register. Note what is <em>not</em>
          applied: branch protection is still off.</p>
          <span class="link-arrow">docs/governance/GOVERNANCE.md</span>
        </a>
      </div>
    </div>
  </section>

  <section class="section section--soft" id="quickstart">
    <div class="wrap split">
      <div>
        <p class="eyebrow">Quickstart</p>
        <h2 class="section-title">Install, test, demo, then optionally go live.</h2>
        <ul class="steps mt-m">
          <li>
            <h3>Install</h3>
            <p>Standard library only; Python 3.10, 3.11 and 3.12 are tested in CI.</p>
          </li>
          <li>
            <h3>Test</h3>
            <p>1,160 collected, 1,157 passed, 3 skipped. No network, no API key.</p>
          </li>
          <li>
            <h3>Demo</h3>
            <p>Offline build from the committed snapshot in under 60&nbsp;s:
            <code>out/demo/index.html</code>.</p>
          </li>
          <li>
            <h3>Live run</h3>
            <p>Needs network, about three minutes, still no API key. Writes the report, the dashboard
            and the CSV.</p>
          </li>
        </ul>
        <p class="src">source: README.md &rarr; Reproduce; PROJECT_STATE.yaml &rarr; tests;
        .github/workflows/ci.yml</p>
      </div>
      <div class="code-wrap">
        <div class="code-head"><span>shell</span><span>verified commands</span></div>
        <pre class="code"><code>git clone https://github.com/ChazY11/medradar.git
cd medradar &amp;&amp; pip install -e .

<span class="c-comment"># 1,160 offline tests &middot; no network &middot; no API key</span>
<span class="c-cmd">python -m pytest -q -o addopts=""</span>

<span class="c-comment"># offline demo &rarr; out/demo/index.html (&lt; 60 s)</span>
<span class="c-cmd">medradar demo</span>

<span class="c-comment"># live run &rarr; report, dashboard, summary.csv (~3 min)</span>
<span class="c-cmd">medradar run --months 24 --with-trade --with-dashboard</span></code></pre>
      </div>
    </div>
  </section>

  <section class="section" id="roles">
    <div class="wrap">
      <div class="section-head">
        <p class="eyebrow">Reading map</p>
        <h2 class="section-title">Four readers, four routes.</h2>
        <p class="lede">Pick the route that matches why you are here; each ends at the document that
        owns the explanation.</p>
      </div>
      <div class="grid grid--2">
        <article class="card">
          <div class="card-head"><span class="badge">evaluator</span></div>
          <h3 class="card-title">Is any of this true?</h3>
          <p>Start with the validation status and the limitations, then read the results with their
          artefacts.</p>
          <ul class="small">
            <li><a href="https://github.com/ChazY11/medradar/blob/main/README.md#what-is-implemented-and-how-far-it-is-validated">README &rarr; Validation status</a></li>
            <li><a href="../research/index.html">Research page &rarr; results and limitations</a></li>
            <li><a href="https://github.com/ChazY11/medradar/blob/main/docs/CASES.md">docs/CASES.md</a></li>
          </ul>
        </article>
        <article class="card">
          <div class="card-head"><span class="badge">reproducer</span></div>
          <h3 class="card-title">Can I rebuild it?</h3>
          <p>The procedure is reproducible offline; the 1.3&nbsp;GiB snapshot is not committed, so exact
          counts are not.</p>
          <ul class="small">
            <li><a href="https://github.com/ChazY11/medradar/blob/main/README.md#reproduce">README &rarr; Reproduce</a></li>
            <li><a href="https://github.com/ChazY11/medradar/blob/main/docs/METHODS.md">docs/METHODS.md</a></li>
            <li><a href="https://github.com/ChazY11/medradar/blob/main/docs/SCHEMA.md">docs/SCHEMA.md</a></li>
          </ul>
        </article>
        <article class="card">
          <div class="card-head"><span class="badge">contributor</span></div>
          <h3 class="card-title">Where do I start?</h3>
          <p>The highest-value contributions are curated knowledge files &mdash; company aliases, track
          dictionaries, product-code mappings &mdash; not code.</p>
          <ul class="small">
            <li><a href="https://github.com/ChazY11/medradar/blob/main/CONTRIBUTING.md">CONTRIBUTING.md</a></li>
            <li><a href="https://github.com/ChazY11/medradar/blob/main/docs/GOOD_FIRST_ISSUES.md">docs/GOOD_FIRST_ISSUES.md</a></li>
            <li><a href="https://github.com/ChazY11/medradar/blob/main/docs/METHODS.md">docs/METHODS.md</a></li>
          </ul>
        </article>
        <article class="card">
          <div class="card-head"><span class="badge">auditor</span></div>
          <h3 class="card-title">What is actually merged?</h3>
          <p>The state file is the single source of truth; the research index and the status blocks are
          generated from it. Branch protection is not applied.</p>
          <ul class="small">
            <li><a href="https://github.com/ChazY11/medradar/blob/main/PROJECT_STATE.yaml">PROJECT_STATE.yaml</a></li>
            <li><a href="https://github.com/ChazY11/medradar/blob/main/docs/RESEARCH_INDEX.md">docs/RESEARCH_INDEX.md</a></li>
            <li><a href="https://github.com/ChazY11/medradar/blob/main/docs/governance/FROZEN.yaml">docs/governance/FROZEN.yaml</a></li>
          </ul>
        </article>
      </div>
      <p class="src">source: docs/INDEX.md &rarr; How to read this repository; README.md</p>
    </div>
  </section>

  <section class="section section--soft" id="contributing">
    <div class="wrap split">
      <div>
        <p class="eyebrow">Contributing</p>
        <h2 class="section-title">Curated knowledge before code.</h2>
        <p class="mt-s">The core package stays standard-library-only. Every new metric updates
        <code>docs/METHODS.md</code> and <code>docs/SCHEMA.md</code> first, so a metric cannot enter the
        codebase without a definition.</p>
        <p class="src">source: README.md &rarr; Contributing; CONTRIBUTING.md</p>
        <div class="btn-row mt-m">
          <a class="btn btn--primary" href="https://github.com/ChazY11/medradar/blob/main/CONTRIBUTING.md">Contributing guide</a>
          <a class="btn btn--ghost" href="https://github.com/ChazY11/medradar/blob/main/docs/GOOD_FIRST_ISSUES.md">Good first issues</a>
        </div>
      </div>
      <div>
        <p class="eyebrow">Licence and citation</p>
        <h2 class="section-title">MIT, with the publishers' terms intact.</h2>
        <dl class="kv mt-m">
          <div><dt>Licence</dt><dd><strong>MIT</strong> &mdash; see <a href="https://github.com/ChazY11/medradar/blob/main/LICENSE">LICENSE</a></dd></div>
          <div><dt>Source data</dt><dd>Belongs to its publishers: openFDA is public domain; ClinicalTrials.gov and SEC EDGAR have their own terms.</dd></div>
          <div><dt>Version</dt><dd><strong>v0.5.0</strong> &mdash; <a href="https://github.com/ChazY11/medradar/blob/main/CHANGELOG.md">CHANGELOG.md</a> is the record</dd></div>
          <div><dt>Dataset</dt><dd>Snapshot <strong>2026-10-31</strong>, generated 2026-10-31T05:33:25Z (not committed)</dd></div>
        </dl>
        <div class="callout callout--plain mt-m">
          <h3>Citation</h3>
          <p>Cite the repository and the version, not a published paper: no paper here is submitted or
          peer reviewed. Paper drafts and their claim maps live in
          <a href="https://github.com/ChazY11/medradar/blob/main/papers/README.md">papers/</a>.</p>
          <p class="mono small">MedRadar (2026). Research infrastructure for public medical-technology
          evidence, v0.5.0, dataset snapshot 2026-10-31. https://github.com/ChazY11/medradar</p>
          <p class="src">source: README.md &rarr; Licence; papers/README.md</p>
        </div>
      </div>
    </div>
  </section>

  <section class="section section--tight">
    <div class="wrap">
      <div class="callout callout--warn">
        <h3>One rule for every document</h3>
        <p>A fact is stated once, in its canonical file, and linked everywhere else. If you find the same
        number in two places without a pointer, one of them is already drifting &mdash; report it rather
        than copy it.</p>
        <p class="src">source: docs/INDEX.md &rarr; Maintenance rules for this page</p>
      </div>
    </div>
  </section>
</main>
"""


# ---------------------------------------------------------------------- registry
PAGES = (
    (
        "index.html",
        "",
        "Public evidence of medical-technology change, made auditable",
        "MedRadar is research infrastructure for public medical-technology evidence: 375,378 events "
        "from six free sources, frozen experiments, named baselines and published negative results. "
        "Not a validated predictive product.",
        landing_body,
        True,
    ),
    (
        "research/index.html",
        "research",
        "Research — what the evidence can and cannot support",
        "MedRadar research: the method contract, the event study with its caveat, the negative results, "
        "the E1b source-recovery verdict and the nine limitations that stay visible.",
        research_body,
        False,
    ),
    (
        "platform/index.html",
        "platform",
        "Platform — sources, coverage and capability matrix",
        "The MedRadar platform: six free public sources, event-date windows, coverage quality, the "
        "capability matrix with evidence paths, and what is deliberately absent.",
        platform_body,
        False,
    ),
    (
        "explore/index.html",
        "explore",
        "Explore — generated artefacts, not a live service",
        "Explore the generated MedRadar artefacts: the interactive dashboard, the static report, the "
        "event replay and the research figures, all from the committed 2026-10-31 snapshot.",
        explore_body,
        False,
    ),
    (
        "documentation/index.html",
        "documentation",
        "Documentation — start here, quickstart, reading map",
        "MedRadar documentation routes: README, INDEX, METHODS, DATA, SCHEMA and GOVERNANCE, the "
        "offline quickstart, and a reading map for evaluators, reproducers, contributors and auditors.",
        documentation_body,
        False,
    ),
)


def render_all() -> dict[Path, str]:
    rendered: dict[Path, str] = {}
    for rel_path, nav_key, title, description, body, home in PAGES:
        target = DOCS / rel_path
        # Pages live one folder below docs/, so their chrome must step up one level.
        prefix = "" if "/" not in rel_path else "../"
        rendered[target] = document(
            title, description, nav_key, body(), prefix=prefix, home=home
        )
    return rendered


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build the MedRadar static site pages.")
    parser.add_argument(
        "--check",
        action="store_true",
        help="verify the committed pages match what this builder would write",
    )
    args = parser.parse_args(argv)

    rendered = render_all()
    stale: list[str] = []
    for target, text in rendered.items():
        if args.check:
            current = target.read_text(encoding="utf-8") if target.is_file() else ""
            if current != text:
                stale.append(str(target.relative_to(ROOT)))
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8", newline="\n")
        print(f"wrote {target.relative_to(ROOT)}  ({len(text.encode('utf-8')):,} bytes)")

    if args.check:
        if stale:
            print("stale pages: " + ", ".join(stale))
            return 1
        print(f"{len(rendered)} pages up to date")
    return 0


if __name__ == "__main__":
    sys.exit(main())
