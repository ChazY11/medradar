"""MedRadar - an open-source radar for FDA device & drug industry direction.

Layout
------
config/     curated knowledge: company/subsidiary aliases, Chinese track
            dictionary, source definitions (JSON so the core needs no YAML).
medradar/   standard-library-only package:
    util.py     dates, text, JSON, and the statistics used everywhere
    http.py     polite HTTP with retries, response cache, offline replay
    db.py       SQLite schema and helpers (one unified event table)
    config.py   paths + CompanyRegistry / TrackRegistry matching
    collect_*   source collectors -> events table
    analyze.py  metrics engine -> out/metrics.json (see docs/SCHEMA.md)
    report.py   Chinese markdown report + self-contained HTML dashboard
    prices.py / eventstudy.py / paper.py   simulated US-equity research
docs/       schema contract, methodology, GitHub Pages demo site
tests/      offline unit tests (no network required)
"""

__version__ = "0.1.0"
__all__ = ["__version__"]
