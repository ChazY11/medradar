"""Deterministic synthetic SQLite fixture for MedRadar product tests (Tier B).

The fixture is generated on the fly in a temporary directory, explicitly named
``synthetic``. It is never part of the product database and never presented as
real FDA data. Its expected counts are constructed here by hand so tests can
assert against independent arithmetic instead of re-calling the functions under
test.

Coverage of the fixture:

* multiple companies (roster keys + a roster-absent firm via exact alias);
* mapped and unmapped track records;
* 510(k) Traditional/Special and PMA original/supplement records;
* one malformed PMA payload (``classification_unavailable`` path);
* complete periods plus clipped start/end quarter, year and month boundaries;
* records that cannot be attributed to any company;
* evidence source/date/url fields.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import date, timedelta
from pathlib import Path
from typing import Any

EDGE = "2026-10-15"
WINDOW_START = "2021-10-16"  # 5 rolling years before EDGE (resolve_window(5))
ANALYSIS_START = "2022-01-01"
ANALYSIS_END = "2026-09-30"
PRIOR_ANALYSIS_START = "2017-04-01"
PRIOR_ANALYSIS_END = "2021-12-31"
PRIOR_EVENTS_END = "2021-09-30"  # inside the prior complete window, no overlap with exact recent window
PARTIAL_START_EVENT = "2021-11-15"
PARTIAL_END_EVENT = "2026-10-10"

SCHEMA = """
CREATE TABLE companies (key TEXT PRIMARY KEY, name_en TEXT, name_zh TEXT, ticker TEXT,
 cik TEXT, sector TEXT, country TEXT DEFAULT 'US', is_major INTEGER DEFAULT 0,
 aliases TEXT DEFAULT '[]', updated_at TEXT);
CREATE TABLE events (event_id TEXT PRIMARY KEY, source TEXT NOT NULL, kind TEXT NOT NULL,
 event_date TEXT, as_of TEXT, company_key TEXT, applicant_raw TEXT, country TEXT DEFAULT 'US',
 track_id TEXT, product_code TEXT, title TEXT, summary TEXT, url TEXT, payload TEXT,
 fetched_at TEXT, published_at TEXT, first_seen_at TEXT, available_at TEXT,
 timestamp_quality TEXT DEFAULT 'date');
CREATE TABLE tracks (id TEXT PRIMARY KEY, name_zh TEXT, name_en TEXT, category TEXT,
 keywords TEXT DEFAULT '[]', updated_at TEXT);
CREATE TABLE product_codes (product_code TEXT PRIMARY KEY, track_id TEXT, device_name TEXT,
 definition TEXT, specialty TEXT, regulation_number TEXT, updated_at TEXT);
CREATE TABLE signals (signal_id TEXT PRIMARY KEY, event_id TEXT, company_key TEXT, ticker TEXT,
 signal_date TEXT, kind TEXT, direction INTEGER, score REAL, track_id TEXT, reason_zh TEXT,
 created_at TEXT, available_at TEXT, timestamp_quality TEXT DEFAULT 'date');
CREATE TABLE runs (run_id TEXT PRIMARY KEY, started_at TEXT, finished_at TEXT, stage TEXT, stats TEXT);
CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT);
CREATE INDEX idx_events_company ON events(company_key, event_date);
CREATE INDEX idx_events_track ON events(track_id, event_date);
CREATE INDEX idx_events_kind_date ON events(kind, event_date);
"""

TRACKS = {
    "cardiac_rhythm": ("心脏节律", "Cardiac Rhythm", "cardiovascular"),
    "imaging_us": ("超声", "Ultrasound", "imaging"),
    "patient_monitoring": ("监护与生命体征", "Patient Monitoring", "monitoring"),
    "respiratory": ("呼吸与麻醉", "Respiratory", "respiratory"),
}

COMPANIES = {
    "medtronic": ("Medtronic", "美敦力", "MDT"),
    "philips": ("Philips", "飞利浦", "PHG"),
    "boston_scientific": ("Boston Scientific", "波士顿科学", "BSX"),
}


def _dates(start: str, end: str, count: int) -> list[str]:
    """Evenly spaced deterministic dates inside [start, end]."""
    begin = date.fromisoformat(start)
    finish = date.fromisoformat(end)
    span = (finish - begin).days
    if count <= 0:
        return []
    if count == 1:
        return [begin.isoformat()]
    return [(begin + timedelta(days=round(span * i / (count - 1)))).isoformat() for i in range(count)]


def _payload(kind: str, subtype: str) -> str:
    if kind == "pma":
        supplement = "" if subtype == "pma_original" else "S001"
        return json.dumps(
            {
                "pma_number": "P900001",
                "supplement_number": supplement,
                "supplement_type": "" if subtype == "pma_original" else "30-Day Notice",
                "applicant": "Synthetic",
            }
        )
    if kind == "510k":
        clearance = {"510k_traditional": "Traditional", "510k_special": "Special"}.get(
            subtype, "Traditional"
        )
        return json.dumps({"k_number": "K900001", "clearance_type": clearance, "applicant": "Synthetic"})
    return json.dumps({"note": "synthetic"})


def build_fixture(path: Path) -> dict[str, Any]:
    """Create the synthetic database and return hand-computed expectations."""
    if path.exists():
        path.unlink()
    con = sqlite3.connect(path)
    con.executescript(SCHEMA)
    con.executemany(
        "INSERT INTO companies VALUES (?,?,?,?,?,?,?,?,?,?)",
        [(key, en, zh, ticker, "", "device", "US", 1, "[]", "2026-10-15") for key, (en, zh, ticker) in COMPANIES.items()],
    )
    con.executemany(
        "INSERT INTO tracks VALUES (?,?,?,?,?,?)",
        [(key, zh, en, category, "[]", "2026-10-15") for key, (zh, en, category) in TRACKS.items()],
    )
    con.executemany(
        "INSERT INTO product_codes VALUES (?,?,?,?,?,?,?)",
        [
            ("ABC", "cardiac_rhythm", "Synthetic cardiac device", "", "Cardiovascular", "", "2026-10-15"),
            ("DEF", "imaging_us", "Synthetic ultrasound", "", "Radiology", "", "2026-10-15"),
            ("GHI", "patient_monitoring", "Synthetic monitor", "", "General Hospital", "", "2026-10-15"),
            ("JKL", "respiratory", "Synthetic ventilator", "", "Anesthesiology", "", "2026-10-15"),
        ],
    )
    con.execute("INSERT INTO runs VALUES ('run-fixture','2026-10-15','2026-10-15','fixture','{}')")
    con.commit()

    rows: list[tuple[Any, ...]] = []
    counter = 0

    def add(
        company: str | None,
        track: str | None,
        kind: str,
        event_date: str,
        subtype: str = "",
        applicant: str | None = None,
        title: str = "Synthetic record",
        source: str | None = None,
        payload_override: str | None = None,
        url: str | None = None,
    ) -> None:
        nonlocal counter
        counter += 1
        event_id = f"FX-{counter:05d}"
        source_name = source or (
            "openfda_device_pma" if kind == "pma" else "openfda_device_510k" if kind == "510k" else f"fixture_{kind}"
        )
        raw_payload = payload_override if payload_override is not None else _payload(kind, subtype)
        rows.append(
            (
                event_id,
                source_name,
                kind,
                event_date,
                None,
                company,
                applicant,
                "US",
                track,
                {"cardiac_rhythm": "ABC", "imaging_us": "DEF", "patient_monitoring": "GHI", "respiratory": "JKL"}.get(track or "", None),
                title,
                "Synthetic fixture record; not real FDA data.",
                url if url is not None else f"https://example.invalid/synthetic/{event_id}",
                raw_payload,
                "2026-10-15",
                event_date,
                "2026-10-15",
                event_date,
                "date",
            )
        )

    def add_group(
        company: str | None,
        track: str | None,
        kind: str,
        subtype_counts: dict[str, int],
        start: str,
        end: str,
        applicant: str | None = None,
    ) -> None:
        total = sum(subtype_counts.values())
        dates = _dates(start, end, total)
        index = 0
        for subtype, count in subtype_counts.items():
            for _ in range(count):
                add(company, track, kind, dates[index], subtype, applicant)
                index += 1

    # ---- recent complete window (2022-01-01 .. 2026-09-30)
    add_group("medtronic", "cardiac_rhythm", "pma", {"pma_original": 2}, ANALYSIS_START, ANALYSIS_END)
    add_group("medtronic", "cardiac_rhythm", "pma", {"pma_supplement": 20}, ANALYSIS_START, ANALYSIS_END)
    add_group("medtronic", "cardiac_rhythm", "510k", {"510k_traditional": 8}, ANALYSIS_START, ANALYSIS_END)
    add_group("medtronic", "imaging_us", "pma", {"pma_original": 1}, ANALYSIS_START, ANALYSIS_END)
    add_group("medtronic", "imaging_us", "pma", {"pma_supplement": 4}, ANALYSIS_START, ANALYSIS_END)
    add_group("medtronic", "imaging_us", "510k", {"510k_traditional": 5}, ANALYSIS_START, ANALYSIS_END)
    add_group("medtronic", None, "pma", {"pma_supplement": 10}, ANALYSIS_START, ANALYSIS_END)  # unmapped track

    add_group("philips", "cardiac_rhythm", "pma", {"pma_supplement": 1}, ANALYSIS_START, ANALYSIS_END)
    add_group("philips", "cardiac_rhythm", "510k", {"510k_traditional": 4}, ANALYSIS_START, ANALYSIS_END)
    add_group("philips", "patient_monitoring", "pma", {"pma_original": 1}, ANALYSIS_START, ANALYSIS_END)
    add_group("philips", "patient_monitoring", "pma", {"pma_supplement": 20}, ANALYSIS_START, ANALYSIS_END)
    add_group("philips", "patient_monitoring", "510k", {"510k_traditional": 14}, ANALYSIS_START, ANALYSIS_END)

    add_group(None, "respiratory", "pma", {"pma_original": 1}, ANALYSIS_START, ANALYSIS_END, applicant="Draeger Medical, Inc.")
    add_group(None, "respiratory", "pma", {"pma_supplement": 1}, ANALYSIS_START, ANALYSIS_END, applicant="Draeger Medical, Inc.")
    add_group(None, "respiratory", "510k", {"510k_traditional": 6}, ANALYSIS_START, ANALYSIS_END, applicant="Draeger Medical, Inc.")
    add_group(None, None, "510k", {"510k_traditional": 12}, ANALYSIS_START, ANALYSIS_END, applicant="Draeger Medical, Inc.")  # unmapped

    add_group("boston_scientific", "cardiac_rhythm", "510k", {"510k_traditional": 15}, ANALYSIS_START, ANALYSIS_END)
    add_group("boston_scientific", "imaging_us", "510k", {"510k_traditional": 10}, ANALYSIS_START, ANALYSIS_END)
    add_group("boston_scientific", "patient_monitoring", "510k", {"510k_traditional": 5}, ANALYSIS_START, ANALYSIS_END)
    add_group("boston_scientific", "respiratory", "510k", {"510k_traditional": 2}, ANALYSIS_START, ANALYSIS_END)

    # unattributed industry records (no company, no track): count in industry all, not mapped
    add_group(None, None, "510k", {"510k_traditional": 20}, ANALYSIS_START, ANALYSIS_END)

    # ---- prior complete window (2017-04-01 .. 2021-12-31)
    add_group("medtronic", "cardiac_rhythm", "pma", {"pma_supplement": 8}, PRIOR_ANALYSIS_START, PRIOR_EVENTS_END)
    add_group("medtronic", "cardiac_rhythm", "510k", {"510k_traditional": 2}, PRIOR_ANALYSIS_START, PRIOR_EVENTS_END)
    add_group("medtronic", "imaging_us", "510k", {"510k_traditional": 5}, PRIOR_ANALYSIS_START, PRIOR_EVENTS_END)
    add_group("medtronic", None, "pma", {"pma_supplement": 2}, PRIOR_ANALYSIS_START, PRIOR_EVENTS_END)
    add_group("philips", "cardiac_rhythm", "510k", {"510k_traditional": 20}, PRIOR_ANALYSIS_START, PRIOR_EVENTS_END)
    add_group("philips", "patient_monitoring", "510k", {"510k_traditional": 5}, PRIOR_ANALYSIS_START, PRIOR_EVENTS_END)
    add_group(None, "respiratory", "510k", {"510k_traditional": 2}, PRIOR_ANALYSIS_START, PRIOR_ANALYSIS_END, applicant="Draeger Medical, Inc.")
    add_group(None, None, "510k", {"510k_traditional": 4}, PRIOR_ANALYSIS_START, PRIOR_ANALYSIS_END, applicant="Draeger Medical, Inc.")
    add_group("boston_scientific", "cardiac_rhythm", "510k", {"510k_traditional": 10}, PRIOR_ANALYSIS_START, PRIOR_EVENTS_END)
    add_group("boston_scientific", "imaging_us", "510k", {"510k_traditional": 5}, PRIOR_ANALYSIS_START, PRIOR_EVENTS_END)
    add_group("boston_scientific", "respiratory", "510k", {"510k_traditional": 1}, PRIOR_ANALYSIS_START, PRIOR_EVENTS_END)
    add_group(None, None, "510k", {"510k_traditional": 10}, PRIOR_ANALYSIS_START, PRIOR_EVENTS_END)

    # ---- partial start / end periods: must be excluded from complete-window counts
    add("medtronic", "cardiac_rhythm", "pma", PARTIAL_START_EVENT, "pma_supplement")
    add("medtronic", "cardiac_rhythm", "pma", PARTIAL_END_EVENT, "pma_supplement")
    add("philips", "patient_monitoring", "510k", PARTIAL_END_EVENT, "510k_traditional")

    # ---- old records outside the comparison windows (all-time pathway differs)
    add("medtronic", "cardiac_rhythm", "pma", "2010-06-01", "pma_supplement")
    add("medtronic", "cardiac_rhythm", "pma", "2011-06-01", "pma_original")
    add("philips", "imaging_us", "510k", "2012-06-01", "510k_traditional")

    # ---- explicit first-entry ordering: supplement is earlier than original
    add("medtronic", "respiratory", "pma", "2015-05-01", "pma_supplement")
    add("medtronic", "respiratory", "pma", "2016-09-01", "pma_original")
    add("medtronic", "respiratory", "510k", "2017-01-01", "510k_special")  # not a first entry
    # draeger first original respiratory (roster-absent firm via exact alias)
    add("draeger", "respiratory", "510k", "2016-05-01", "510k_traditional", applicant="Draeger Medical, Inc.")
    add("draeger", "respiratory", "pma", "2015-03-01", "pma_supplement", applicant="Draeger Medical, Inc.")

    # ---- malformed payload: classification must be unavailable, never guessed
    add(
        "medtronic",
        "imaging_us",
        "pma",
        "2021-11-20",
        "",
        title="Unparsable synthetic PMA payload",
        payload_override="{not-json",
    )

    # valid JSON but missing supplement_number -> unknown, never "original"
    add(
        "medtronic",
        None,
        "pma",
        "2021-11-21",
        "",
        title="Missing supplement_number synthetic PMA payload",
        payload_override=json.dumps({"pma_number": "P900002"}),
    )

    # ---- other event kinds for company profiles / evidence
    add("medtronic", "cardiac_rhythm", "device_recall", "2023-06-01", title="Synthetic recall")
    add("medtronic", "cardiac_rhythm", "trial", "2022-06-01", title="Synthetic trial", source="ctgov")
    add("philips", "patient_monitoring", "8k_catalyst", "2023-07-01", title="Synthetic 8-K", source="sec_edgar_corpus")
    add(None, "cardiac_rhythm", "device_recall", "2023-08-01", title="Synthetic unattributed recall")

    con.executemany("INSERT INTO events VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", rows)
    con.commit()
    con.close()

    industry_mapped_recent = 30 + 5 + 15 + 10 + 10 + 35 + 5 + 8 + 2  # 120
    industry_unmapped_recent = 10 + 12 + 20  # 42
    expectations: dict[str, Any] = {
        "path": str(path),
        "edge": EDGE,
        "window": {"start": WINDOW_START, "end": EDGE},
        "analysis": {
            "start": ANALYSIS_START,
            "end": ANALYSIS_END,
            "prior_start": PRIOR_ANALYSIS_START,
            "prior_end": PRIOR_ANALYSIS_END,
            "periods": 19,
        },
        "companies": {
            "medtronic": {
                "recent_all": 50,
                "recent_mapped": 40,
                "prior_all": 20,
                "prior_mapped": 17,
                "mapping_coverage": 40 / 50,
                "tracks": {"cardiac_rhythm": 30, "imaging_us": 10},
                "pma": {"original": 3, "supplement": 34},
                "first_entry": {"respiratory": "2016-09-01"},
            },
            "philips": {
                "recent_all": 40,
                "recent_mapped": 40,
                "prior_all": 25,
                "prior_mapped": 25,
                "mapping_coverage": 1.0,
                "tracks": {"cardiac_rhythm": 5, "patient_monitoring": 35},
            },
            "draeger": {
                "recent_all": 20,
                "recent_mapped": 8,
                "prior_all": 6,
                "prior_mapped": 2,
                "mapping_coverage": 8 / 20,
                "tracks": {"respiratory": 8},
                "first_entry": {"respiratory": "2016-05-01"},
            },
        },
        "industry": {
            "recent_mapped": industry_mapped_recent,
            "recent_all": industry_mapped_recent + industry_unmapped_recent,
            "recent_unmapped": industry_unmapped_recent,
            "mapping_coverage": industry_mapped_recent / (industry_mapped_recent + industry_unmapped_recent),
            "track_counts_recent": {
                "cardiac_rhythm": 50,
                "imaging_us": 20,
                "patient_monitoring": 40,
                "respiratory": 10,
            },
        },
        "lq": {
            "medtronic_cardiac": (30 / 40) / (50 / 120),
            "medtronic_imaging": (10 / 40) / (20 / 120),
            "philips_cardiac": (5 / 40) / (50 / 120),
        },
        "old_wrong_lq": {
            # previous implementation used the company's *all* records (including
            # unmapped) as the denominator while the industry side used mapped only
            "medtronic_cardiac": (30 / 50) / (50 / 120),
        },
        "classification_unknown": 2,
        "partial": {
            "start_period": "2021-Q4",
            "end_period": "2026-Q4",
        },
    }
    return expectations
