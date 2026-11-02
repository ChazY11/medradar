#!/usr/bin/env python3
"""Build the hist_v1 full-history company x track quarterly regulatory panel.

Deterministic, standard-library only, no network.  The event store is opened
read-only (``sqlite3`` URI ``mode=ro``) and never modified.

Outputs
-------
``out/hist_v1/panel.json``            the panel consumed by ``experiments/hist_v1/eval.py``
``experiments/hist_v1/audits.json``   machine-readable entity / coverage / date / panel audits
``experiments/hist_v1/manifest.json`` provenance: SHA-256 of every input and the panel, row counts

Usage
-----
    python experiments/hist_v1/build_panel.py

Determinism
-----------
No wall-clock time, no randomness, no network, no platform-dependent formatting
is embedded: every list is sorted, JSON is dumped with ``sort_keys=True``, and
``generated_at`` is derived from the source data (the maximum ``fetched_at`` of
the panel source rows), not from the clock.  Running the same command twice on
the same inputs produces byte-identical artifacts.

Panel rules (frozen by research/protocols/hist_v1_preregistration.md sections 2-3)
----------------------------------------------------------------------------------
* Sources: ``openfda_device_510k`` (all records) and ``openfda_device_pma``.
* Material event: every 510(k); a PMA only when ``payload.supplement_number`` is
  empty/null/``0``/``S0`` or ``payload.supplement_type`` contains ``PANEL TRACK``.
* Event quarter: from ``available_at`` if present, else ``event_date``.  Events
  whose availability quarter is outside the grid are excluded and counted.
* Track: ``events.track_id`` if present; else ``config/product_code_tracks.json``
  ``[product_code]``; else the event is excluded and counted.
* Company: the store's ``company_key`` when it is one of the 51 companies in
  ``data/research.sqlite`` ``companies``; plus Dräger and Mindray resolved by
  *exact* ``applicant_raw`` string match to ``config/hist_entity_aliases.json``.
  No fuzzy matching and no substring matching anywhere.
* Grid: 1976-Q1 .. 2026-Q2 inclusive (2026-Q3 is partial and excluded).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sqlite3
import subprocess
import sys
from collections import Counter, defaultdict
from contextlib import closing
from pathlib import Path
from typing import Any, Iterable, Mapping

ROOT = Path(__file__).resolve().parents[2]

PANEL_SCHEMA = "hist_v1.panel.v1"
AUDITS_SCHEMA = "hist_v1.audits.v1"
MANIFEST_SCHEMA = "hist_v1.manifest.v1"

QUARTER_START = "1976-Q1"
QUARTER_END = "2026-Q2"
GRID_START_YEAR = 1976
GRID_END_YEAR, GRID_END_QUARTER = 2026, 2

DEVICE_SOURCES = ("openfda_device_510k", "openfda_device_pma")
DEVICE_510K = "openfda_device_510k"
DEVICE_PMA = "openfda_device_pma"

#: The five deep-case companies.  The three roster companies are resolved from
#: the store's own ``company_key``; the two roster-absent companies are resolved
#: by exact applicant string via config/hist_entity_aliases.json.
ROSTER_DEEP_CASES = ("ge_healthcare", "medtronic", "philips")
ALIAS_DEEP_CASES = ("draeger", "mindray")
DEEP_CASES = ("draeger", "ge_healthcare", "medtronic", "mindray", "philips")
#: Parent-brand tokens per deep case (upper-case substring test), used for the
#: pre-registered *attribution sensitivity* variant ``pairs_no_acquired``.
#: Dräger has two standard orthographies: the umlaut form is transliterated
#: ``Draeger`` and the unaccented form is ``Drager`` -- a single ``DRAGER`` test
#: would wrongly flag every ``Draeger ...`` string, so both are accepted.
PARENT_BRAND_TOKENS: dict[str, tuple[str, ...]] = {
    "draeger": ("DRAGER", "DRAEGER"),
    "ge_healthcare": ("GE",),
    "medtronic": ("MEDTRONIC",),
    "mindray": ("MINDRAY",),
    "philips": ("PHILIPS",),
}

#: Entity-resolution deny list applied at panel-build time: ``(company_key, raw)``.
#: ``Björn Philips`` is a clinical-trial investigator name in the ctgov lane that
#: the store's token-containment mapping assigned to Philips because it contains
#: the surname token. It is not a legal name, brand or subsidiary, so it is
#: denied; it has no panel-source (510(k)/PMA) events, so the panel loses 0
#: events -- the entry documents the mapping defect. No applicant_raw string
#: with *panel-source* events was found to belong to an unrelated company.
DENY_LIST: tuple[tuple[str, str], ...] = (("philips", "Björn Philips"),)

#: Tokens of other roster companies used only for the cross-company conflict
#: check in the entity audit (word-boundary match).
OTHER_COMPANY_TOKENS = (
    "ABBOTT", "BAXTER", "BECTON DICKINSON", "BOSTON SCIENTIFIC", "CANON",
    "COVIDIEN", "DEPUY", "ETHICON", "FUJIFILM", "GE", "HITACHI", "JOHNSON",
    "MEDTRONIC", "OLYMPUS", "PHILIPS", "SAMSUNG", "SIEMENS", "STRYKER",
    "TOSHIBA", "WIPRO",
)
CROSS_CHECK_EXEMPT = {
    "ge_healthcare": {"GE", "WIPRO"},
    "medtronic": {"MEDTRONIC", "COVIDIEN"},
    "philips": {"PHILIPS"},
    "draeger": {"DRAGER"},
    "mindray": {"MINDRAY"},
}

TOP_UNMAPPED_CODES = 25


# --------------------------------------------------------------------- helpers
def sha256_file(path: Path, chunk_size: int = 4 * 1024 * 1024) -> str:
    """SHA-256 hex digest of a file, streamed."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def connect_ro(path: Path) -> sqlite3.Connection:
    """Open a SQLite database strictly read-only."""
    uri = f"file:{path.resolve().as_posix()}?mode=ro"
    connection = sqlite3.connect(uri, uri=True)
    connection.row_factory = sqlite3.Row
    return connection


def quarter_index(date_text: str | None) -> int | None:
    """Quarter index on the 1976-Q1..2026-Q2 grid, or None if unparseable/absent."""
    if not date_text:
        return None
    text = str(date_text).strip()
    try:
        year = int(text[0:4])
    except (TypeError, ValueError):
        return None
    if len(text) >= 7 and text[4] == "-":
        try:
            month = int(text[5:7])
        except ValueError:
            return None
    else:
        month = 1
    if not 1 <= month <= 12:
        return None
    return (year - GRID_START_YEAR) * 4 + (month - 1) // 3


def quarter_label(qidx: int) -> str:
    year = GRID_START_YEAR + qidx // 4
    quarter = qidx % 4 + 1
    return f"{year}-Q{quarter}"


def decade_label(date_text: str | None) -> str:
    if not date_text:
        return "unknown"
    year = str(date_text)[:4]
    if len(year) == 4 and year.isdigit():
        return f"{int(year) // 10 * 10}s"
    return "unknown"


def quarter_upper_bound_qidx() -> int:
    return (GRID_END_YEAR - GRID_START_YEAR) * 4 + (GRID_END_QUARTER - 1)


def quarter_labels() -> list[str]:
    return [quarter_label(index) for index in range(quarter_upper_bound_qidx() + 1)]


def material_pma(payload_text: str | None) -> tuple[bool, bool]:
    """Apply the frozen PMA materiality rule.

    Returns ``(is_material, payload_parsed)``.  An unparseable payload is treated
    as *non-material* (conservative exclusion) and counted in the audit.
    """
    try:
        payload = json.loads(payload_text) if payload_text else {}
    except (TypeError, ValueError):
        return False, False
    if not isinstance(payload, dict):
        return False, False
    supplement = payload.get("supplement_number")
    supplement_type = str(payload.get("supplement_type") or "").upper()
    if supplement is None or str(supplement).strip() in ("", "0", "S0"):
        return True, True
    return "PANEL TRACK" in supplement_type, True


def _has_token(text: str, token: str) -> bool:
    return re.search(rf"\b{re.escape(token)}\b", text) is not None


def is_parent_attributed(
    company_key: str,
    applicant_raw: str,
    registry_accepted: frozenset[tuple[str, str]] = frozenset(),
) -> bool:
    """True when the applicant string is parent-branded for the attribution rule.

    ``True`` means "not an acquired-brand attribution risk".  The 48 auxiliary
    roster companies are always returned True (their brand-token sets are not
    audited).  For the five deep cases, a string is parent-attributed if it is
    one of the registry's exact accepted aliases (a typo of the parent name is
    still the parent, not an acquired brand) or if it contains the parent brand
    token in any accepted orthography.
    """
    tokens = PARENT_BRAND_TOKENS.get(company_key)
    if tokens is None:
        return True
    if (company_key, applicant_raw) in registry_accepted:
        return True
    upper = applicant_raw.upper()
    return any(token in upper for token in tokens)


# ------------------------------------------------------------------ main build
def build(
    db_path: Path,
    research_db_path: Path,
    out_dir: Path,
    experiments_dir: Path,
) -> dict[str, Any]:
    pc_tracks: dict[str, str] = read_json(ROOT / "config" / "product_code_tracks.json")
    track_config = read_json(ROOT / "config" / "tracks_device.json")
    track_meta = {track["id"]: track for track in track_config["tracks"]}
    aliases = read_json(ROOT / "config" / "hist_entity_aliases.json")
    alias_company: dict[str, str] = {}
    alias_spec: dict[str, Mapping[str, Any]] = {}
    for company_key, spec in aliases["companies"].items():
        alias_spec[company_key] = spec
        for raw in spec.get("accept_exact") or ():
            if raw in alias_company and alias_company[raw] != company_key:
                raise SystemExit(f"alias {raw!r} claimed by two companies")
            alias_company[raw] = company_key

    with closing(connect_ro(research_db_path)) as research:
        roster_rows = research.execute("SELECT key, name_en FROM companies").fetchall()
    roster: dict[str, str] = {row["key"]: row["name_en"] for row in roster_rows}
    if not roster:
        raise SystemExit("research companies roster is empty")

    company_meta: dict[str, dict[str, str]] = {}
    for key, name in roster.items():
        company_meta[key] = {
            "key": key,
            "display_name": name,
            "cohort": "deep_case" if key in ROSTER_DEEP_CASES else "roster",
        }
    for key in ALIAS_DEEP_CASES:
        spec = alias_spec.get(key)
        if spec is None:
            raise SystemExit(f"missing alias registry entry for {key}")
        company_meta[key] = {
            "key": key,
            "display_name": str(spec["display_name"]),
            "cohort": "deep_case",
        }
    expected_deep = set(DEEP_CASES)
    if not expected_deep.issubset(company_meta):
        missing = sorted(expected_deep - set(company_meta))
        raise SystemExit(f"deep-case companies absent from universe: {missing}")

    deny_set: set[tuple[str, str]] = set(DENY_LIST)
    max_qidx = quarter_upper_bound_qidx()

    # ------------------------------------------------------------ single pass
    material_total = 0
    non_material_total = 0
    payload_parse_failures = 0
    material_by_source: Counter[str] = Counter()
    material_by_source_decade: dict[tuple[str, str], Counter[str]] = defaultdict(Counter)
    unmapped_product_codes: Counter[str] = Counter()
    unmapped_by_source: Counter[str] = Counter()
    fallback_rescued_all = 0
    fallback_rescued_material = 0
    no_track_material = 0
    no_company_material = 0
    company_mapped_material = 0
    company_and_track_material = 0
    denied_events = 0
    before_grid = 0
    after_grid = 0
    material_before_grid_total = 0
    material_after_grid_total = 0
    unparseable_material_dates = 0
    post_grid_events: list[dict[str, Any]] = []
    panel_events: list[dict[str, Any]] = []

    # entity audit (panel sources): (company_key, applicant_raw) -> counters
    deep_strings: dict[tuple[str, str], Counter[str]] = defaultdict(Counter)
    # funnel counters by source
    funnel: dict[str, Counter[str]] = defaultdict(Counter)

    query = (
        "SELECT source, kind, event_date, available_at, company_key, applicant_raw, "
        "track_id, product_code, payload, fetched_at FROM events "
        "WHERE source IN (?, ?)"
    )
    with closing(connect_ro(db_path)) as store:
        max_fetched = store.execute("SELECT MAX(fetched_at) FROM events").fetchone()[0]
        rows = store.execute(query, DEVICE_SOURCES)
        for row in rows:
            source = row["source"]
            kind = row["kind"]
            applicant = row["applicant_raw"] or ""
            if source == DEVICE_510K:
                is_material = True
                parsed = True
            else:
                is_material, parsed = material_pma(row["payload"])
            if not parsed:
                payload_parse_failures += 1

            # ---- track mapping (needed for the materiality/coverage audit)
            track_id = (row["track_id"] or "").strip()
            used_fallback = False
            if not track_id:
                fallback_track = pc_tracks.get((row["product_code"] or "").strip(), "")
                if fallback_track:
                    track_id = fallback_track
                    used_fallback = True
                    fallback_rescued_all += 1
            track_ok = bool(track_id) and track_id in track_meta

            # ---- company mapping
            store_key = row["company_key"]
            company_key: str | None = None
            if store_key in roster:
                company_key = store_key
            elif applicant in alias_company:
                company_key = alias_company[applicant]

            # ---- entity audit accumulation for deep cases (all device rows)
            if company_key in DEEP_CASES or (
                store_key in ROSTER_DEEP_CASES and store_key in roster
            ):
                audit_key = company_key or store_key
                stats = deep_strings[(audit_key, applicant)]
                stats["n_events"] += 1
                stats["n_510k"] += 1 if kind == "510k" else 0
                stats["n_pma"] += 1 if kind == "pma" else 0
                if is_material:
                    stats["n_material"] += 1
                if (audit_key, applicant) in deny_set:
                    stats["denied"] += 1

            if not is_material:
                non_material_total += 1
                continue

            material_total += 1
            material_by_source[source] += 1
            decade = decade_label(row["event_date"])
            block = material_by_source_decade[(source, decade)]
            block["total"] += 1
            availability = row["available_at"] or row["event_date"]
            material_qidx = quarter_index(availability)
            if material_qidx is None:
                unparseable_material_dates += 1
                funnel[source]["unparseable_date"] += 1
            elif material_qidx < 0:
                material_before_grid_total += 1
            elif material_qidx > max_qidx:
                material_after_grid_total += 1
            if used_fallback:
                fallback_rescued_material += 1
            if not track_ok:
                unmapped_by_source[source] += 1
                unmapped_product_codes[(row["product_code"] or "<NULL>")] += 1
                block["track_unmapped"] += 1
                no_track_material += 1
                funnel[source]["material_no_track"] += 1
            else:
                block["track_mapped"] += 1
            if company_key is None:
                no_company_material += 1
                block["company_unmapped"] += 1
                funnel[source]["material_no_company"] += 1
                continue
            company_mapped_material += 1
            block["company_mapped"] += 1
            funnel[source]["material_company_mapped"] += 1
            if not track_ok:
                continue

            if (company_key, applicant) in deny_set:
                denied_events += 1
                continue

            company_and_track_material += 1
            funnel[source]["material_company_and_track"] += 1
            qidx = material_qidx
            if qidx is None:
                continue
            if qidx < 0:
                before_grid += 1
                funnel[source]["before_grid"] += 1
                continue
            if qidx > max_qidx:
                after_grid += 1
                funnel[source]["after_grid"] += 1
                post_grid_events.append(
                    {
                        "company_key": company_key,
                        "track_id": track_id,
                        "qidx": qidx,
                        "event_date": row["event_date"],
                        "availability": availability,
                        "kind": kind,
                        "applicant_raw": applicant,
                        "source": source,
                    }
                )
                continue

            panel_events.append(
                {
                    "company_key": company_key,
                    "track_id": track_id,
                    "qidx": qidx,
                    "event_date": row["event_date"],
                    "availability": availability,
                    "kind": kind,
                    "applicant_raw": applicant,
                    "source": source,
                }
            )
            deep_stats = deep_strings.get((company_key, applicant))
            if deep_stats is not None:
                deep_stats["n_panel"] += 1

    if not max_fetched:
        raise SystemExit("could not read a data snapshot timestamp (fetched_at)")

    # -------------------------------------------------------- panel assembly
    companies: dict[str, dict[str, Any]] = {}
    for event in panel_events:
        key = event["company_key"]
        record = companies.get(key)
        if record is None:
            record = {
                "key": key,
                "display_name": company_meta[key]["display_name"],
                "cohort": company_meta[key]["cohort"],
                "total_material_events": 0,
                "first_event_qidx": event["qidx"],
                "last_event_qidx": event["qidx"],
            }
            companies[key] = record
        record["total_material_events"] += 1
        record["first_event_qidx"] = min(record["first_event_qidx"], event["qidx"])
        record["last_event_qidx"] = max(record["last_event_qidx"], event["qidx"])

    tracks: dict[str, dict[str, Any]] = {}
    for event in panel_events:
        track_id = event["track_id"]
        record = tracks.get(track_id)
        if record is None:
            meta = track_meta[track_id]
            record = {
                "id": track_id,
                "name_en": meta["name_en"],
                "category": meta["category"],
                "domain": meta["domain"],
                "first_industry_qidx": event["qidx"],
                "n_firms_ever": 0,
            }
            tracks[track_id] = record
        record["first_industry_qidx"] = min(record["first_industry_qidx"], event["qidx"])
    firms_by_track: dict[str, set[str]] = defaultdict(set)
    for event in panel_events:
        firms_by_track[event["track_id"]].add(event["company_key"])
    for track_id, record in tracks.items():
        record["n_firms_ever"] = len(firms_by_track[track_id])

    pairs = _build_pairs(panel_events)
    pairs_including_post_grid = _build_pairs(panel_events + post_grid_events)

    # ---- attribution sensitivity: pairs_no_acquired
    registry_accepted = frozenset(
        (company_key, raw) for raw, company_key in alias_company.items()
    )

    def is_attribution_risk(event: Mapping[str, Any]) -> bool:
        return not is_parent_attributed(
            event["company_key"], event["applicant_raw"], registry_accepted
        )

    acquired_events: list[dict[str, Any]] = []
    retained_events: list[dict[str, Any]] = []
    for event in panel_events:
        (acquired_events if is_attribution_risk(event) else retained_events).append(event)
    pairs_no_acquired = _build_pairs(retained_events)

    # ------------------------------------------------------------- audits
    entity_resolution = _entity_audit(
        db_path=db_path,
        roster=roster,
        company_meta=company_meta,
        alias_spec=alias_spec,
        registry_accepted=registry_accepted,
        deep_strings=deep_strings,
        deny_list=deny_set,
        denied_events=denied_events,
        panel_events=panel_events,
        pairs=pairs,
        pairs_no_acquired=pairs_no_acquired,
        acquired_events=acquired_events,
        retained_events=retained_events,
    )

    unmapped_total = sum(unmapped_by_source.values())
    track_coverage = {
        "scope": "all material device events in the two panel sources, regardless of company",
        "material_device_events_total": material_total,
        "material_events_by_source": dict(sorted(material_by_source.items())),
        "track_mapping": {
            "mapped": material_total - unmapped_total,
            "unmapped": unmapped_total,
            "pct_mapped": _pct(material_total - unmapped_total, material_total),
            "unmapped_by_source": dict(sorted(unmapped_by_source.items())),
            "by_source_decade": {
                f"{source}|{decade}": dict(block)
                for (source, decade), block in sorted(material_by_source_decade.items())
            },
        },
        "product_code_fallback": {
            "config_file": "config/product_code_tracks.json",
            "config_code_to_track_entries": len(pc_tracks),
            "fallback_events_rescued_all_device_events": fallback_rescued_all,
            "fallback_events_rescued_material_events": fallback_rescued_material,
            "note": (
                "the documented fallback (events.track_id missing -> product_code mapping) "
                "rescued no material event in this snapshot: every event without a track_id "
                "also has a product_code absent from the config file. The panel's effective "
                "track universe is therefore events.track_id only (38 of the 50 configured tracks)."
            ),
        },
        "panel_funnel": {
            "material_device_events_total": material_total,
            "excluded_no_track": no_track_material,
            "excluded_no_company_in_panel": no_company_material,
            "company_mapped_material": company_mapped_material,
            "company_and_track_mapped_material": company_and_track_material,
            "excluded_before_grid_start": before_grid,
            "excluded_after_grid_end": after_grid,
            "excluded_by_deny_list": denied_events,
            "in_panel": len(panel_events),
            "by_source": {source: dict(counter) for source, counter in sorted(funnel.items())},
        },
        "top_unmapped_product_codes": [
            {"product_code": code, "n_material_events": count}
            for code, count in unmapped_product_codes.most_common(TOP_UNMAPPED_CODES)
        ],
        "tracks_in_panel": len(tracks),
        "config_tracks": len(track_meta),
        "tracks_without_panel_events": sorted(set(track_meta) - set(tracks)),
        "grid_truncation": {
            "material_events_before_grid_start_in_store": material_before_grid_total,
            "material_events_before_grid_start_in_panel_companies": before_grid,
            "material_events_after_grid_end_in_store": material_after_grid_total,
            "material_events_after_grid_end_company_and_track_mapped": after_grid,
            "unparseable_material_dates": unparseable_material_dates,
            "panel_events_if_after_grid_events_included": len(panel_events) + len(post_grid_events),
            "pairs_if_after_grid_events_included": len(pairs_including_post_grid),
            "note": (
                "the store's PMA lane starts 1968-10-09: 22 PMA records predate the 1976-Q1 grid "
                "start and 18 of them are material (original approvals), but none is attributed to "
                "a panel company or track, so grid truncation costs the panel 0 events. 2026-Q3 is "
                "partial and excluded, which drops the 118 company+track-mapped material events "
                "dated 2026-07-01..2026-10-18; including them would give the counts shown above "
                "(these post-grid events can never be a label inside the 1976-Q1..2026-Q2 "
                "evaluation window, so no label information is lost)."
            ),
        },
        "payload_parse_failures": payload_parse_failures,
        "note": (
            f"{len(pc_tracks)} product-code entries in config/product_code_tracks.json; "
            "the 7,097 figure is the row count of the store's product_codes table, not this file"
        ),
    }

    date_quality = _date_audit(db_path)

    per_decade = Counter()
    for event in panel_events:
        per_decade[decade_label(event["event_date"])] += 1
    panel_summary = {
        "n_companies": len(companies),
        "n_companies_by_cohort": dict(
            sorted(Counter(record["cohort"] for record in companies.values()).items())
        ),
        "n_tracks": len(tracks),
        "n_pairs": len(pairs),
        "n_pairs_with_events": sum(1 for pair in pairs if pair["event_qidx"]),
        "n_pairs_no_acquired": len(pairs_no_acquired),
        "n_material_events": len(panel_events),
        "first_panel_event_qidx": min(event["qidx"] for event in panel_events),
        "last_panel_event_qidx": max(event["qidx"] for event in panel_events),
        "first_panel_event_quarter": quarter_label(min(event["qidx"] for event in panel_events)),
        "last_panel_event_quarter": quarter_label(max(event["qidx"] for event in panel_events)),
        "per_decade_event_counts": dict(sorted(per_decade.items())),
        "companies_with_lt_5_events": [
            {"company_key": key, "n_material_events": record["total_material_events"]}
            for key, record in sorted(companies.items())
            if record["total_material_events"] < 5
        ],
        "companies_with_no_panel_events": sorted(set(company_meta) - set(companies)),
        "n_companies_in_universe": len(company_meta),
    }

    first_qidx_by_pair = {
        (pair["company_key"], pair["track_id"]): pair["event_qidx"][0] for pair in pairs
    }
    left_censoring_pairs = sorted(
        pair for pair, first_qidx in first_qidx_by_pair.items() if first_qidx <= 3
    )
    left_censoring = {
        "definition": (
            "pairs whose first panel material event falls in the first four quarters of the grid "
            "(1976-Q1..1976-Q4); a pair that entered before 1976 is indistinguishable from a "
            "pair that never entered, so these are the pairs exposed to pre-1976 censoring"
        ),
        "n_pairs": len(left_censoring_pairs),
        "n_pairs_first_quarter": sum(1 for value in first_qidx_by_pair.values() if value == 0),
        "pairs": [
            {"company_key": company_key, "track_id": track_id, "first_event_qidx": first_qidx_by_pair[(company_key, track_id)]}
            for company_key, track_id in left_censoring_pairs
        ],
    }

    audits: dict[str, Any] = {
        "schema": AUDITS_SCHEMA,
        "generated_at": max_fetched,
        "source_db": str(db_path.relative_to(ROOT)) if db_path.is_relative_to(ROOT) else str(db_path),
        "entity_resolution": entity_resolution,
        "track_coverage": track_coverage,
        "date_quality": date_quality,
        "panel_summary": panel_summary,
        "left_censoring": left_censoring,
        "material_event_rule": _material_event_rule_text(),
    }

    panel = {
        "schema": PANEL_SCHEMA,
        "generated_at": max_fetched,
        "quarter_start": QUARTER_START,
        "quarter_end": QUARTER_END,
        "quarters": quarter_labels(),
        "companies": [companies[key] for key in sorted(companies)],
        "tracks": [tracks[key] for key in sorted(tracks)],
        "pairs": pairs,
        "pairs_no_acquired": pairs_no_acquired,
        "audits": {
            "schema": AUDITS_SCHEMA,
            "reference": "experiments/hist_v1/audits.json",
            "entity_resolution": {
                "deny_list": sorted(f"{company}|{raw}" for company, raw in deny_set),
                "deny_list_events_removed": denied_events,
                "n_deep_case_strings_audited": sum(
                    len(record["strings"]) for record in entity_resolution["companies"].values()
                ),
                "attribution_risk_event_counts": entity_resolution["attribution_sensitivity"][
                    "per_company_event_counts"
                ],
                "attribution_risk_pairs_removed": entity_resolution["attribution_sensitivity"][
                    "totals"
                ]["pairs_removed"],
            },
            "track_coverage": {
                "material_device_events_total": material_total,
                "track_mapped": material_total - unmapped_total,
                "track_unmapped": unmapped_total,
                "fallback_events_rescued_material": fallback_rescued_material,
                "products_codes_note": track_coverage["note"],
            },
            "date_quality": {
                "available_at_lt_event_date": date_quality["n_available_at_lt_event_date"],
                "available_at_missing": date_quality["n_available_at_missing"],
            },
            "panel_summary": panel_summary,
            "left_censoring": {
                "n_pairs_first_event_in_first_4_quarters": left_censoring["n_pairs"],
                "n_pairs_first_quarter": left_censoring["n_pairs_first_quarter"],
            },
        },
    }

    # ------------------------------------------------------------- write out
    _validate_panel(panel)
    out_dir.mkdir(parents=True, exist_ok=True)
    experiments_dir.mkdir(parents=True, exist_ok=True)
    panel_path = out_dir / "panel.json"
    audits_path = experiments_dir / "audits.json"
    manifest_path = experiments_dir / "manifest.json"

    _write_json(panel_path, panel)
    _write_json(audits_path, audits)

    manifest = _build_manifest(
        db_path=db_path,
        research_db_path=research_db_path,
        panel_path=panel_path,
        audits_path=audits_path,
        panel=panel,
        audits=audits,
        generated_at=max_fetched,
        db_fetched_at=max_fetched,
    )
    _write_json(manifest_path, manifest)

    return {
        "panel_path": str(panel_path),
        "audits_path": str(audits_path),
        "manifest_path": str(manifest_path),
        "panel_bytes": panel_path.stat().st_size,
        "panel_sha256": sha256_file(panel_path),
        "audits_sha256": sha256_file(audits_path),
        "manifest_sha256": sha256_file(manifest_path),
        "panel": panel,
        "audits": audits,
        "manifest": manifest,
    }


def _pct(numerator: int, denominator: int) -> float:
    return round(100.0 * numerator / denominator, 2) if denominator else 0.0


def _material_event_rule_text() -> str:
    return (
        "material = every openfda_device_510k record; openfda_device_pma record only when "
        "payload.supplement_number is empty/null/'0'/'S0' or payload.supplement_type contains "
        "'PANEL TRACK' (identical to experiments/reverse_rd_v2/run_v2.py)"
    )


def _build_pairs(events: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Group material events into ``(company_key, track_id)`` pair records."""
    grouped: dict[tuple[str, str], list[tuple[int, str, str]]] = defaultdict(list)
    for event in events:
        grouped[(event["company_key"], event["track_id"])].append(
            (event["qidx"], event["availability"], event["kind"])
        )
    pairs: list[dict[str, Any]] = []
    for (company_key, track_id), items in sorted(grouped.items()):
        items.sort()
        iso_by_quarter: dict[int, str] = {}
        count_by_quarter: dict[int, int] = {}
        n_510k = n_pma = 0
        for qidx, iso, kind in items:
            if qidx not in iso_by_quarter or iso < iso_by_quarter[qidx]:
                iso_by_quarter[qidx] = iso
            count_by_quarter[qidx] = count_by_quarter.get(qidx, 0) + 1
            if kind == "510k":
                n_510k += 1
            else:
                n_pma += 1
        qidxs = sorted(iso_by_quarter)
        pairs.append(
            {
                "company_key": company_key,
                "track_id": track_id,
                "event_qidx": qidxs,
                "event_iso": [iso_by_quarter[qidx] for qidx in qidxs],
                # material events in each quarter (sum == n_510k + n_pma); a
                # quarter with 3 clearances has count 3, so the evaluator's
                # activity features are event counts, not quarter counts
                "event_counts": [count_by_quarter[qidx] for qidx in qidxs],
                "n_510k": n_510k,
                "n_pma": n_pma,
            }
        )
    return pairs


def _validate_panel(panel: Mapping[str, Any]) -> None:
    """Fail the build if the panel violates its documented contract or the frozen grid.

    Checks: quarter labels, pair ordering/uniqueness, event-qidx bounds, that each
    ``event_iso`` really belongs to its ``event_qidx`` (so no event can be placed
    earlier than its availability quarter), aggregated company/track consistency,
    and that ``pairs_no_acquired`` is an event-subset of ``pairs``.
    """
    quarters = panel["quarters"]
    expected_quarters = quarter_labels()
    if quarters != expected_quarters:
        raise SystemExit("panel validation: quarter labels do not match 1976-Q1..2026-Q2")
    if panel["quarter_start"] != expected_quarters[0] or panel["quarter_end"] != expected_quarters[-1]:
        raise SystemExit("panel validation: quarter_start/quarter_end mismatch")
    max_qidx = len(quarters) - 1

    company_keys = [record["key"] for record in panel["companies"]]
    if company_keys != sorted(company_keys) or len(set(company_keys)) != len(company_keys):
        raise SystemExit("panel validation: companies not sorted and unique")
    track_ids = [record["id"] for record in panel["tracks"]]
    if track_ids != sorted(track_ids) or len(set(track_ids)) != len(track_ids):
        raise SystemExit("panel validation: tracks not sorted and unique")
    companies = {record["key"]: record for record in panel["companies"]}
    tracks = {record["id"]: record for record in panel["tracks"]}
    for record in companies.values():
        if record["cohort"] not in ("deep_case", "roster"):
            raise SystemExit(f"panel validation: bad cohort {record['cohort']!r}")
        if record["total_material_events"] < 1:
            raise SystemExit(f"panel validation: company {record['key']} has no material event")

    pair_keys: list[tuple[str, str]] = []
    total_events = 0
    events_by_company: Counter[str] = Counter()
    first_by_company: dict[str, int] = {}
    last_by_company: dict[str, int] = {}
    for pair in panel["pairs"]:
        key = (pair["company_key"], pair["track_id"])
        pair_keys.append(key)
        if key[0] not in companies or key[1] not in tracks:
            raise SystemExit(f"panel validation: pair {key} references an unknown company/track")
        qidxs = pair["event_qidx"]
        isos = pair["event_iso"]
        counts = pair["event_counts"]
        if not qidxs or not (len(qidxs) == len(isos) == len(counts)):
            raise SystemExit(f"panel validation: bad event arrays for {key}")
        if qidxs != sorted(set(qidxs)):
            raise SystemExit(f"panel validation: event_qidx not sorted and unique for {key}")
        if any(not isinstance(count, int) or count < 1 for count in counts):
            raise SystemExit(f"panel validation: event_counts must be positive ints for {key}")
        for qidx, iso in zip(qidxs, isos):
            if not 0 <= qidx <= max_qidx:
                raise SystemExit(f"panel validation: event_qidx {qidx} out of bounds for {key}")
            if quarter_index(iso) != qidx:
                raise SystemExit(
                    f"panel validation: event_iso {iso!r} is not in quarter {qidx} for {key} "
                    "(event placed earlier than its availability)"
                )
        n_events = pair["n_510k"] + pair["n_pma"]
        if n_events < len(qidxs):
            raise SystemExit(f"panel validation: fewer material events than quarters for {key}")
        if sum(counts) != n_events:
            raise SystemExit(
                f"panel validation: sum(event_counts) != n_510k + n_pma for {key}"
            )
        total_events += n_events
        events_by_company[key[0]] += n_events
        first_by_company[key[0]] = min(first_by_company.get(key[0], qidxs[0]), qidxs[0])
        last_by_company[key[0]] = max(last_by_company.get(key[0], qidxs[-1]), qidxs[-1])
    if pair_keys != sorted(pair_keys) or len(set(pair_keys)) != len(pair_keys):
        raise SystemExit("panel validation: pairs not sorted and unique")

    for key, record in companies.items():
        if record["total_material_events"] != events_by_company[key]:
            raise SystemExit(f"panel validation: company total mismatch for {key}")
        if (
            record["first_event_qidx"] != first_by_company[key]
            or record["last_event_qidx"] != last_by_company[key]
        ):
            raise SystemExit(f"panel validation: company first/last quarter mismatch for {key}")

    summary = panel["audits"]["panel_summary"]
    if total_events != summary["n_material_events"]:
        raise SystemExit("panel validation: panel material-event total mismatch")
    if len(pair_keys) != summary["n_pairs"]:
        raise SystemExit("panel validation: pair total mismatch")

    firms_by_track: dict[str, set[str]] = defaultdict(set)
    first_by_track: dict[str, int] = {}
    for pair in panel["pairs"]:
        firms_by_track[pair["track_id"]].add(pair["company_key"])
        first_by_track[pair["track_id"]] = min(
            first_by_track.get(pair["track_id"], pair["event_qidx"][0]), pair["event_qidx"][0]
        )
    for track_id, record in tracks.items():
        if record["n_firms_ever"] != len(firms_by_track[track_id]):
            raise SystemExit(f"panel validation: track firm count mismatch for {track_id}")
        if record["first_industry_qidx"] != first_by_track[track_id]:
            raise SystemExit(f"panel validation: track first quarter mismatch for {track_id}")

    original = {(pair["company_key"], pair["track_id"]): pair for pair in panel["pairs"]}
    for pair in panel["pairs_no_acquired"]:
        key = (pair["company_key"], pair["track_id"])
        if key not in original:
            raise SystemExit(f"panel validation: pairs_no_acquired {key} is not a panel pair")
        if not set(pair["event_qidx"]) <= set(original[key]["event_qidx"]):
            raise SystemExit(f"panel validation: pairs_no_acquired is not an event subset for {key}")
        source_pair = original[key]
        if sum(pair["event_counts"]) != pair["n_510k"] + pair["n_pma"]:
            raise SystemExit(
                f"panel validation: pairs_no_acquired event_counts mismatch for {key}"
            )
        source_counts = dict(zip(source_pair["event_qidx"], source_pair["event_counts"]))
        for qidx, count in zip(pair["event_qidx"], pair["event_counts"]):
            if count > source_counts[qidx]:
                raise SystemExit(
                    f"panel validation: pairs_no_acquired count exceeds panel count for {key}"
                )


def _entity_audit(
    *,
    db_path: Path,
    roster: Mapping[str, str],
    company_meta: Mapping[str, Mapping[str, str]],
    alias_spec: Mapping[str, Mapping[str, Any]],
    registry_accepted: frozenset[tuple[str, str]],
    deep_strings: Mapping[tuple[str, str], Counter],
    deny_list: set[tuple[str, str]],
    denied_events: int,
    panel_events: list[dict[str, Any]],
    pairs: list[dict[str, Any]],
    pairs_no_acquired: list[dict[str, Any]],
    acquired_events: list[dict[str, Any]],
    retained_events: list[dict[str, Any]],
) -> dict[str, Any]:
    """Audit every applicant_raw string attributed to a deep-case company."""
    # all-source counts per (company_key, applicant_raw), for the roster deep cases
    all_source_counts: dict[tuple[str, str], Counter[str]] = defaultdict(Counter)
    with closing(connect_ro(db_path)) as store:
        for row in store.execute(
            "SELECT company_key, applicant_raw, source, COUNT(*) AS n FROM events "
            "WHERE company_key IN (?, ?, ?) GROUP BY company_key, applicant_raw, source",
            ROSTER_DEEP_CASES,
        ):
            all_source_counts[(row["company_key"], row["applicant_raw"] or "")][row["source"]] += row["n"]

        # all-source counts for the exact alias strings of the two roster-absent cases
        for company_key in ALIAS_DEEP_CASES:
            accept = list(alias_spec[company_key].get("accept_exact") or ())
            for start in range(0, len(accept), 200):
                chunk = accept[start:start + 200]
                placeholders = ",".join("?" for _ in chunk)
                for row in store.execute(
                    f"SELECT applicant_raw, source, COUNT(*) AS n FROM events "
                    f"WHERE applicant_raw IN ({placeholders}) GROUP BY applicant_raw, source",
                    chunk,
                ):
                    all_source_counts[(company_key, row["applicant_raw"])][row["source"]] += row["n"]

    # candidate strings that look like the company name but are not accepted
    candidate_not_accepted: list[dict[str, Any]] = []
    seen_candidates: set[tuple[str, str, str]] = set()
    with closing(connect_ro(db_path)) as store:
        pattern_globs = {
            "draeger": ("%DRAGER%", "%DRAEGER%", "%DRAEG%"),
            "mindray": ("%MINDRAY%",),
        }
        for company_key, patterns in pattern_globs.items():
            accept = set(alias_spec[company_key].get("accept_exact") or ())
            reject = set(alias_spec[company_key].get("reject_exact") or ())
            for pattern in patterns:
                for row in store.execute(
                    "SELECT applicant_raw, source, COUNT(*) AS n FROM events "
                    "WHERE UPPER(applicant_raw) LIKE ? GROUP BY applicant_raw, source",
                    (pattern,),
                ):
                    raw = row["applicant_raw"] or ""
                    if raw in accept or raw in reject:
                        continue
                    if (company_key, raw, row["source"]) in seen_candidates:
                        continue
                    seen_candidates.add((company_key, raw, row["source"]))
                    candidate_not_accepted.append(
                        {
                            "company_key": company_key,
                            "applicant_raw": raw,
                            "source": row["source"],
                            "n_events": row["n"],
                            "decision": "rejected",
                            "reason": (
                                "not an accepted exact alias; if it is the company it is an FDA "
                                "transcription variant that must be added to config/hist_entity_aliases.json "
                                "by a human reviewer before it can enter the panel"
                            ),
                        }
                    )

    companies_audit: dict[str, Any] = {}
    for company_key in DEEP_CASES:
        display_name = company_meta[company_key]["display_name"]
        tokens = PARENT_BRAND_TOKENS[company_key]
        rosters = company_key in roster
        strings: list[dict[str, Any]] = []
        attribution_risk_strings: list[dict[str, Any]] = []
        cross_conflicts: list[dict[str, Any]] = []

        if rosters:
            candidate_keys = {raw for (ck, raw) in deep_strings if ck == company_key}
            candidate_keys |= {raw for (ck, raw) in all_source_counts if ck == company_key}
            keys = sorted(
                candidate_keys,
                key=lambda raw: (
                    -deep_strings[(company_key, raw)]["n_events"],
                    -sum(all_source_counts.get((company_key, raw), Counter()).values()),
                    raw,
                ),
            )
        else:
            keys = list(alias_spec[company_key].get("accept_exact") or ())

        for raw in keys:
            stats = deep_strings.get((company_key, raw), Counter())
            all_counts = all_source_counts.get((company_key, raw), Counter())
            n_all = sum(all_counts.values())
            n_events = stats["n_events"]
            n_non_device = max(0, n_all - n_events)
            risky = not is_parent_attributed(company_key, raw, registry_accepted)
            denied = (company_key, raw) in deny_list
            entry = {
                "applicant_raw": raw,
                "n_events_panel_sources": n_events,
                "n_510k": stats["n_510k"],
                "n_pma": stats["n_pma"],
                "n_material": stats["n_material"],
                "n_panel_events": stats["n_panel"],
                "n_non_device_source_events": n_non_device,
                "in_panel_sources": n_events > 0,
                "decision": "reject" if denied else "accept",
                "reason": _string_reason(raw, tokens, risky, denied, n_events),
                "attribution_risk": risky,
            }
            strings.append(entry)
            if risky:
                attribution_risk_strings.append(
                    {
                        "applicant_raw": raw,
                        "n_events_panel_sources": n_events,
                        "n_material": stats["n_material"],
                        "n_panel_events": stats["n_panel"],
                    }
                )
            up = raw.upper()
            for other in OTHER_COMPANY_TOKENS:
                if other in CROSS_CHECK_EXEMPT.get(company_key, set()):
                    continue
                if _has_token(up, other):
                    cross_conflicts.append(
                        {
                            "applicant_raw": raw,
                            "conflicting_company_token": other,
                            "n_events_panel_sources": n_events,
                        }
                    )

        block: dict[str, Any] = {
            "display_name": display_name,
            "cohort": "deep_case",
            "resolution": (
                "store company_key (51-company roster)" if rosters else "exact applicant_raw alias (config/hist_entity_aliases.json)"
            ),
            "n_strings": len(strings),
            "n_events_panel_sources": sum(entry["n_events_panel_sources"] for entry in strings),
            "n_material_events": sum(entry["n_material"] for entry in strings),
            "n_panel_events": sum(entry["n_panel_events"] for entry in strings),
            "strings": strings,
            "attribution_risk_strings": attribution_risk_strings,
            "cross_company_token_conflicts": cross_conflicts,
        }
        if not rosters:
            block["accepted_aliases"] = [
                {
                    "alias": alias,
                    "n_events_panel_sources": next(
                        (entry["n_events_panel_sources"] for entry in strings if entry["applicant_raw"] == alias),
                        0,
                    ),
                    "n_events_all_sources": sum(all_source_counts.get((company_key, alias), Counter()).values()),
                }
                for alias in alias_spec[company_key].get("accept_exact") or ()
            ]
            block["rejected_aliases"] = list(alias_spec[company_key].get("reject_exact") or ())
            block["candidate_strings_not_accepted"] = [
                entry for entry in candidate_not_accepted if entry["company_key"] == company_key
            ]
        companies_audit[company_key] = block

    # ---- attribution sensitivity: per-company removal statistics
    per_company_event_counts: dict[str, int] = {}
    per_company_pair_counts: dict[str, int] = {}
    per_company_removed: dict[str, dict[str, int]] = {}
    pairs_before_by_company = Counter(pair["company_key"] for pair in pairs)
    pairs_after_by_company = Counter(pair["company_key"] for pair in pairs_no_acquired)
    events_before_by_company = Counter(event["company_key"] for event in panel_events)
    events_after_by_company = Counter(event["company_key"] for event in retained_events)
    removed_by_company = Counter(event["company_key"] for event in acquired_events)
    for company_key in DEEP_CASES:
        per_company_event_counts[company_key] = removed_by_company.get(company_key, 0)
        per_company_pair_counts[company_key] = (
            pairs_before_by_company.get(company_key, 0) - pairs_after_by_company.get(company_key, 0)
        )
        per_company_removed[company_key] = {
            "panel_events_before": events_before_by_company.get(company_key, 0),
            "panel_events_removed": removed_by_company.get(company_key, 0),
            "pairs_before": pairs_before_by_company.get(company_key, 0),
            "pairs_after": pairs_after_by_company.get(company_key, 0),
            "pairs_removed": per_company_pair_counts[company_key],
        }

    registry_refinement = None
    draeger = alias_spec["draeger"]
    if draeger.get("refinement_history"):
        registry_refinement = {
            "file": "config/hist_entity_aliases.json",
            "history": draeger["refinement_history"],
            "accept_exact_count": len(draeger.get("accept_exact") or ()),
        }

    return {
        "scope": (
            "panel sources only (openfda_device_510k, openfda_device_pma); counts marked "
            "n_non_device_source_events cover the same applicant_raw string in the other store "
            "sources (recalls/ctgov/sec) for completeness but do not enter the panel"
        ),
        "store_mapping_note": (
            "the store company_key is a *current corporate group* mapping: historical events of "
            "acquired brands are attributed to the acquirer (e.g. Covidien/Tyco Healthcare/Valleylab/"
            "Kendall -> Medtronic). That is a point-in-time look-ahead in the entity definition; the "
            "pre-registration declares the auxiliary roster mapping unaudited. The deep-case audit "
            "below enumerates every such string; the panel variant pairs_no_acquired removes them."
        ),
        "deny_list": sorted(f"{company}|{raw}" for company, raw in deny_list),
        "deny_list_events_removed": denied_events,
        "deny_list_note": (
            "one entry -- 'philips|Björn Philips' -- a ctgov clinical-trial investigator name "
            "whose surname token made the store's token-containment mapping assign it to Philips; "
            "it is not a legal name, brand or subsidiary. It has 0 panel-source (510(k)/PMA) "
            "events, so applying the deny list removes 0 panel events (documented zero, not "
            "silent). No applicant_raw string that occurs in the panel sources belongs to an "
            "unrelated company; the illustrative false positive 'Surge Medical Sales' does not "
            "occur in the store (a LIKE '%SURGE%'/'%SALES%' scan finds such strings only with "
            "company_key = NULL, never assigned to GE HealthCare). Strings that are *not legal "
            "entities* but are unambiguous internal divisions, business units or product lines "
            "(e.g. 'Surgical Devices, A Global Business Unit Covidien', 'Philips Clinical & "
            "Medical Affairs Global') are accepted, not denied, because they are the company's "
            "own business. Every string is listed in companies[*].strings, including strings the "
            "store assigns only in non-panel sources (recalls/ctgov/sec)."
        ),
        "companies": companies_audit,
        "candidate_strings_not_accepted": sorted(
            candidate_not_accepted, key=lambda item: (item["company_key"], -item["n_events"], item["applicant_raw"])
        ),
        "registry_refinement": registry_refinement,
        "attribution_sensitivity": {
            "rule": (
                "an event is removed when its company is one of the five deep cases and the "
                "upper-case applicant_raw is neither a registry-accepted exact alias of that "
                "company nor contains its parent-brand token (MEDTRONIC / GE / PHILIPS / "
                "DRAGER or DRAEGER / MINDRAY). The 48 auxiliary roster companies are unchanged: "
                "their brand-token sets are not audited (declared limitation)."
            ),
            "variant_pairs": "pairs_no_acquired in out/hist_v1/panel.json",
            "per_company": per_company_removed,
            "per_company_event_counts": per_company_event_counts,
            "totals": {
                "panel_events_before": len(panel_events),
                "panel_events_removed": len(acquired_events),
                "panel_events_after": len(retained_events),
                "pairs_before": len(pairs),
                "pairs_removed": len(pairs) - len(pairs_no_acquired),
                "pairs_after": len(pairs_no_acquired),
                "n_companies_affected": sum(1 for value in removed_by_company.values() if value),
            },
            "known_quirk": (
                "the literal single-token 'DRAGER' test would have flagged 15 Dräger strings / "
                "108 events because the standard umlaut transliteration is 'Draeger', which does "
                "not contain 'DRAGER' as a substring. The implemented rule accepts both "
                "orthographies and treats every registry-accepted exact alias (including the "
                "'Draeget' typo) as parent-attributed, so the net attribution removal is "
                "Medtronic only (Covidien/Tyco/Kendall/Valleylab era events). Strings that contain "
                "the parent token but belong to a since-divested line (e.g. 'Ge Healthcare, Breas "
                "Medical AB', 'Philips Lighting Co.') stay in pairs_no_acquired: the rule targets "
                "acquired-brand history, not divestitures."
            ),
        },
    }


def _string_reason(
    raw: str,
    tokens: tuple[str, ...],
    risky: bool,
    denied: bool = False,
    n_panel_source_events: int = 0,
) -> str:
    if denied:
        return (
            "rejected: not a legal name, brand or subsidiary of the company; the store's "
            "token-containment mapping matched it (a clinical-trial investigator surname). "
            "It has 0 panel-source events, so the deny list removes 0 panel events."
        )
    if n_panel_source_events == 0:
        return (
            "accepted for completeness: the store assigns this string to the company, but it "
            "has no panel-source (510(k)/PMA) event, so it cannot enter the panel"
        )
    if not risky:
        return (
            "accepted: legal name, brand or subsidiary of the company (contains parent-brand "
            f"token {tokens[0]})"
        )
    return (
        "accepted: former name or acquired-brand subsidiary of a company now in this corporate "
        "group; unambiguous but NOT point-in-time attributable (attribution risk)"
    )


def _date_audit(db_path: Path) -> dict[str, Any]:
    with closing(connect_ro(db_path)) as store:
        per_source: dict[str, dict[str, Any]] = {}
        for row in store.execute(
            "SELECT source, COUNT(*) AS n, MIN(event_date) AS min_event_date, "
            "MAX(event_date) AS max_event_date, MIN(available_at) AS min_available_at, "
            "MAX(available_at) AS max_available_at, "
            "SUM(CASE WHEN available_at IS NULL OR available_at = '' THEN 1 ELSE 0 END) AS n_avail_missing, "
            "SUM(CASE WHEN available_at < event_date THEN 1 ELSE 0 END) AS n_avail_lt_event, "
            "SUM(CASE WHEN available_at = event_date THEN 1 ELSE 0 END) AS n_avail_eq_event, "
            "SUM(CASE WHEN available_at > event_date THEN 1 ELSE 0 END) AS n_avail_gt_event "
            "FROM events WHERE source IN (?, ?) GROUP BY source",
            DEVICE_SOURCES,
        ):
            per_source[row["source"]] = {
                "n_events": row["n"],
                "min_event_date": row["min_event_date"],
                "max_event_date": row["max_event_date"],
                "min_available_at": row["min_available_at"],
                "max_available_at": row["max_available_at"],
                "n_available_at_missing": row["n_avail_missing"],
                "n_available_at_lt_event_date": row["n_avail_lt_event"],
                "n_available_at_eq_event_date": row["n_avail_eq_event"],
                "n_available_at_gt_event_date": row["n_avail_gt_event"],
            }
        totals = {
            "n_available_at_lt_event_date": sum(
                block["n_available_at_lt_event_date"] for block in per_source.values()
            ),
            "n_available_at_missing": sum(
                block["n_available_at_missing"] for block in per_source.values()
            ),
            "n_available_at_gt_event_date": sum(
                block["n_available_at_gt_event_date"] for block in per_source.values()
            ),
        }
    return {
        "scope": "the two panel sources; the panel quarter is derived from available_at "
        "(falling back to event_date) so pre-registration section 2 is satisfied",
        "sources": per_source,
        **totals,
        "note": (
            "available_at equals event_date for every source row in this snapshot, so the panel "
            "quarter is the FDA decision quarter and the declared decision-date-as-availability "
            "approximation is exact here"
        ),
    }


def _build_manifest(
    *,
    db_path: Path,
    research_db_path: Path,
    panel_path: Path,
    audits_path: Path,
    panel: Mapping[str, Any],
    audits: Mapping[str, Any],
    generated_at: str,
    db_fetched_at: str,
) -> dict[str, Any]:
    script_path = Path(__file__).resolve()
    tracked_files = [
        (db_path, "source event store (read-only)"),
        (research_db_path, "roster + publication counts (read-only)"),
        (ROOT / "config" / "product_code_tracks.json", "product_code -> track fallback mapping"),
        (ROOT / "config" / "tracks_device.json", "track metadata (category/domain/name)"),
        (ROOT / "config" / "hist_entity_aliases.json", "deep-case exact-string alias registry"),
        (script_path, "panel builder"),
        (panel_path, "generated panel"),
    ]
    files: dict[str, Any] = {}
    for path, role in tracked_files:
        files[_rel(path)] = {
            "sha256": sha256_file(path),
            "bytes": path.stat().st_size,
            "role": role,
        }

    with closing(connect_ro(db_path)) as store:
        medradar_counts = {
            "events": store.execute("SELECT COUNT(*) FROM events").fetchone()[0],
            "events.openfda_device_510k": store.execute(
                "SELECT COUNT(*) FROM events WHERE source = ?", (DEVICE_510K,)
            ).fetchone()[0],
            "events.openfda_device_pma": store.execute(
                "SELECT COUNT(*) FROM events WHERE source = ?", (DEVICE_PMA,)
            ).fetchone()[0],
            "companies": store.execute("SELECT COUNT(*) FROM companies").fetchone()[0],
            "product_codes": store.execute("SELECT COUNT(*) FROM product_codes").fetchone()[0],
            "tracks": store.execute("SELECT COUNT(*) FROM tracks").fetchone()[0],
        }
    with closing(connect_ro(research_db_path)) as research:
        research_counts = {
            "companies": research.execute("SELECT COUNT(*) FROM companies").fetchone()[0],
            "publication_counts": research.execute(
                "SELECT COUNT(*) FROM publication_counts"
            ).fetchone()[0],
        }

    head_commit, branch = _git_head()
    return {
        "schema": MANIFEST_SCHEMA,
        "generated_at": generated_at,
        "generated_at_semantics": (
            "maximum fetched_at of the source event store (data snapshot time), not wall-clock; "
            "no clock value is embedded so regeneration is byte-identical"
        ),
        "command": "python experiments/hist_v1/build_panel.py",
        "argv": list(sys.argv),
        "worktree": ROOT.as_posix(),
        "git": {
            "head_commit": head_commit,
            "branch": branch,
            "available": head_commit is not None,
            "note": "the worktree HEAD commit; this build did not commit anything",
        },
        "files": files,
        "row_counts": {
            "medradar": medradar_counts,
            "research": research_counts,
            "panel": {
                "companies": len(panel["companies"]),
                "companies_deep_case": sum(
                    1 for record in panel["companies"] if record["cohort"] == "deep_case"
                ),
                "tracks": len(panel["tracks"]),
                "pairs": len(panel["pairs"]),
                "pairs_no_acquired": len(panel["pairs_no_acquired"]),
                "material_events": audits["panel_summary"]["n_material_events"],
                "quarters": len(panel["quarters"]),
            },
        },
        "data_snapshot": {
            "max_fetched_at_all_sources": db_fetched_at,
            "panel_sources": list(DEVICE_SOURCES),
        },
        "notes": [
            "outputs: out/hist_v1/panel.json (git-ignored), experiments/hist_v1/audits.json, experiments/hist_v1/manifest.json",
            "panel.json is compact, key-sorted UTF-8 JSON with a trailing newline; two runs on the same inputs are byte-identical",
            "audits.json is generated by the same run; its SHA-256 is recorded here for convenience",
        ],
        "audits_json_sha256": sha256_file(audits_path),
    }


def _git_head() -> tuple[str | None, str | None]:
    try:
        head = subprocess.run(
            ["git", "-C", str(ROOT), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=False,
        )
        branch = subprocess.run(
            ["git", "-C", str(ROOT), "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True,
            text=True,
            check=False,
        )
        if head.returncode != 0:
            return None, None
        return head.stdout.strip() or None, (branch.stdout.strip() or None)
    except (OSError, subprocess.SubprocessError):
        return None, None


def _rel(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT.resolve()).as_posix()
    except ValueError:
        return path.resolve().as_posix()


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    path.write_bytes((text + "\n").encode("utf-8"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=str(ROOT / "data" / "medradar.sqlite"))
    parser.add_argument("--research-db", default=str(ROOT / "data" / "research.sqlite"))
    parser.add_argument("--out-dir", default=str(ROOT / "out" / "hist_v1"))
    parser.add_argument("--experiments-dir", default=str(ROOT / "experiments" / "hist_v1"))
    args = parser.parse_args(argv)

    result = build(
        db_path=Path(args.db),
        research_db_path=Path(args.research_db),
        out_dir=Path(args.out_dir),
        experiments_dir=Path(args.experiments_dir),
    )
    panel = result["panel"]
    summary = {
        "panel": result["panel_path"],
        "panel_bytes": result["panel_bytes"],
        "panel_sha256": result["panel_sha256"],
        "audits": result["audits_path"],
        "manifest": result["manifest_path"],
        "quarter_start": panel["quarter_start"],
        "quarter_end": panel["quarter_end"],
        "n_quarters": len(panel["quarters"]),
        "n_companies": len(panel["companies"]),
        "n_tracks": len(panel["tracks"]),
        "n_pairs": len(panel["pairs"]),
        "n_pairs_no_acquired": len(panel["pairs_no_acquired"]),
        "n_material_events": result["audits"]["panel_summary"]["n_material_events"],
        "first_panel_event_quarter": result["audits"]["panel_summary"]["first_panel_event_quarter"],
        "last_panel_event_quarter": result["audits"]["panel_summary"]["last_panel_event_quarter"],
        "deny_list_events_removed": result["audits"]["entity_resolution"]["deny_list_events_removed"],
        "attribution_pairs_removed": result["audits"]["entity_resolution"]["attribution_sensitivity"][
            "totals"
        ]["pairs_removed"],
        "git_head": result["manifest"]["git"]["head_commit"],
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
