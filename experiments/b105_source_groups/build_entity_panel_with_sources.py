#!/usr/bin/env python3
"""B-018 / b105: attach company-level source groups to the frozen P2 entity panel.

The frozen P2 panel (``experiments/cycle2_coverage``) is entity-level: rows are
keyed by the deterministic applicant-entity key, not by a curated company key.
The three "source" groups requested by B-018 are company-level tables:

* financial: ``financial_facts`` (consolidated SEC XBRL), 32 companies;
* market: ``market_bars`` (point-in-time daily bars), tickers for the roster;
* publication: ``publication_counts`` (OpenAlex annual counts), 51 companies.

The join is done in two exact steps and never with a fuzzy proxy:

1. entity -> curated company: an entity maps to the unique ``company_key`` that
   the store's own 510(k)/PMA rows carry for it. Entities with zero or 2+ distinct
   company keys are not mapped; their source features stay missing and the
   missingness is reported (no name/alias matching is invented).
2. company -> source group feature: the frozen point-in-time builders
   (``financial_features.features_by_company``,
   ``market_features.market_features``, ``publication_features.publication_features``)
   are called with the same cutoffs as the panel. No new feature definition is
   introduced here; only the row-to-company dispatch is new, because the frozen
   ``attach_*`` helpers read ``example["company_key"]`` which on this panel is
   the *entity* key, not the parent company.

Rows whose entity has no parent company keep ``None`` for the group features
(plus the group's own missing flag where the frozen spec has one); the model then
uses its training-only median imputation. That is a missing-data statement, not a
substitute for the identifier the row does not have.

Usage:
    python experiments/b105_source_groups/build_entity_panel_with_sources.py
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import sqlite3
import sys
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parents[1]
sys.path.insert(0, str(ROOT))

from experiments.cycle2_coverage.run_cycle2 import build_p2  # noqa: E402
from medradar.config import load_companies  # noqa: E402
from medradar.intelligence.features.financial_features import (  # noqa: E402
    FEATURES as FINANCIAL_FEATURES,
    features_by_company,
)
from medradar.intelligence.features.market_features import (  # noqa: E402
    FEATURES as MARKET_FEATURES,
    market_features,
)
from medradar.intelligence.features.publication_features import (  # noqa: E402
    PUBLICATION_FEATURES,
    publication_features,
)
from medradar.intelligence.features.research_features import (  # noqa: E402
    BASE_FEATURES,
    ENTRY_FEATURES,
)
from medradar.intelligence.sources.market_data import company_ticker_map  # noqa: E402
from medradar.intelligence.sources.publications import load_counts  # noqa: E402
from medradar.intelligence.universe import entity_key, normalise_applicant  # noqa: E402
from medradar.util import sha1  # noqa: E402

DEFAULT_DB = ROOT / "data" / "research.sqlite"
DEFAULT_PANEL = SCRIPT_DIR / "panel_entity_sources.jsonl.gz"
DEFAULT_AVAILABILITY = SCRIPT_DIR / "data_availability.json"
DEFAULT_COHORT_SIZE = 200
DEFAULT_MIN_MATERIAL = 3
DEFAULT_MIN_ACTIVE_YEARS = 2
CYCLE2_COVERAGE_END = "2026-10-15"

#: Every feature key stored in the panel, in a fixed order (compact JSONL).
FEATURE_ORDER: tuple[str, ...] = (
    tuple(BASE_FEATURES) + tuple(ENTRY_FEATURES) + tuple(FINANCIAL_FEATURES)
    + tuple(MARKET_FEATURES) + tuple(PUBLICATION_FEATURES)
)
BASE_PANEL_FEATURES: tuple[str, ...] = tuple(BASE_FEATURES) + tuple(ENTRY_FEATURES)
SOURCE_GROUPS: dict[str, tuple[str, ...]] = {
    "financial": tuple(FINANCIAL_FEATURES),
    "market": tuple(MARKET_FEATURES),
    "publication": tuple(PUBLICATION_FEATURES),
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


class _ConnShim:
    """Minimal ``store.conn`` shim so the frozen loaders can query a raw connection."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self.conn = connection


# ------------------------------------------------------------------ entity join
def entity_parent_map(connection: sqlite3.Connection) -> tuple[dict[str, str], dict[str, Any]]:
    """Exact entity -> curated company map from the store's own 510(k)/PMA links.

    Uses **all** 510(k)/PMA rows (including non-material PMA supplements) because
    linkage evidence is not restricted by the material-event rule; the panel's
    own material filter is applied separately by the frozen builder.
    """
    claims: dict[str, set[str]] = {}
    rows = connection.execute(
        "SELECT company_key, applicant_raw FROM events WHERE kind IN ('510k','pma')"
    ).fetchall()
    for company_key, applicant_raw in rows:
        if not company_key:
            continue
        entity = entity_key(normalise_applicant(applicant_raw))
        if not entity:
            continue
        claims.setdefault(entity, set()).add(str(company_key))
    mapped = {entity: next(iter(keys)) for entity, keys in claims.items() if len(keys) == 1}
    ambiguous = {entity: sorted(keys) for entity, keys in claims.items() if len(keys) > 1}
    stats = {
        "entities_with_link_evidence": len(claims),
        "entities_mapped_to_one_company": len(mapped),
        "entities_ambiguous": len(ambiguous),
        "ambiguous_entities": {entity: keys for entity, keys in sorted(ambiguous.items())[:20]},
        "companies_represented": len(set(mapped.values())),
        "rule": (
            "entity -> company_key only when the store's 510(k)/PMA rows for that exact "
            "deterministic entity key carry exactly one distinct company_key; no name matching"
        ),
    }
    return mapped, stats


# ----------------------------------------------------------------- feature joins
def financial_feature_map(connection: sqlite3.Connection, cutoffs: list[str]
                          ) -> tuple[dict[tuple[str, str], dict[str, float | None]], dict[str, Any]]:
    rows = [dict(row) for row in connection.execute(
        "SELECT company_key, tag, unit, value, period_start, period_end, available_at, "
        "accession, fiscal_year FROM financial_facts"
    ).fetchall()]
    feature_map = features_by_company(rows, cutoffs)
    companies = sorted({str(row["company_key"]) for row in rows})
    return feature_map, {"rows": len(rows), "companies": len(companies),
                         "company_keys": companies}


def market_feature_map(connection: sqlite3.Connection, cutoffs: list[str],
                       company_tickers: dict[str, str]) -> tuple[dict[tuple[str, str], dict[str, Any]], dict[str, Any]]:
    shim = _ConnShim(connection)
    cache: dict[Any, Any] = {}
    feature_map: dict[tuple[str, str], dict[str, Any]] = {}
    for company, ticker in sorted(company_tickers.items()):
        for cutoff in cutoffs:
            feature_map[(company, cutoff)] = market_features(
                shim, company, cutoff, company_tickers, cache=cache)
    covered = sorted({company for (company, _cutoff), values in feature_map.items()
                      if int(values.get("mkt_missing", 1)) == 0})
    return feature_map, {
        "companies_in_ticker_map": len(company_tickers),
        "companies_with_market_features": len(covered),
        "company_keys": covered,
        "market_bars_tickers": [row[0] for row in connection.execute(
            "SELECT DISTINCT ticker FROM market_bars ORDER BY ticker")],
    }


def publication_feature_map(connection: sqlite3.Connection, cutoffs: list[str]
                            ) -> tuple[dict[tuple[str, str], dict[str, float | None]], dict[str, Any]]:
    counts = load_counts(_ConnShim(connection))
    feature_map = {
        (company, cutoff): publication_features(counts.get(company), cutoff)
        for company in sorted(counts) for cutoff in cutoffs
    }
    return feature_map, {
        "companies_with_counts": len(counts),
        "years_per_company": {company: len(years) for company, years in sorted(counts.items())},
    }


def _blank_group_features(group: str) -> dict[str, float | None]:
    if group == "financial":
        return {name: None for name in FINANCIAL_FEATURES} | {"fin_facts_available": 0.0}
    if group == "market":
        return {name: None for name in MARKET_FEATURES} | {"mkt_missing": 1.0}
    return {name: None for name in PUBLICATION_FEATURES} | {"pub_missing": 1.0}


def _group_available(group: str, values: dict[str, Any]) -> bool:
    if group == "financial":
        return float(values.get("fin_facts_available") or 0.0) > 0.0
    if group == "market":
        return int(values.get("mkt_missing", 1)) == 0
    return float(values.get("pub_missing", 1.0)) == 0.0


def attach_source_groups(
    examples: list[dict[str, Any]],
    parent_map: dict[str, str],
    financial_map: dict[tuple[str, str], dict[str, float | None]],
    market_map: dict[tuple[str, str], dict[str, Any]],
    publication_map: dict[tuple[str, str], dict[str, float | None]],
) -> dict[str, Any]:
    """Attach the three frozen source groups to every example (in place).

    Rows without a unique parent company receive the group's all-missing vector
    (``None`` values + the group's missing flag), flagged as unavailable. The
    function returns example-level availability counts for the report.
    """
    counters = {group: {"available": 0, "missing": 0, "no_parent": 0}
                for group in SOURCE_GROUPS}
    for example in examples:
        entity = str(example.get("company_key") or "")
        cutoff = str(example.get("cutoff") or "")
        parent = parent_map.get(entity)
        features = example.setdefault("features", {})
        availability: dict[str, bool] = {}
        for group, feature_names in SOURCE_GROUPS.items():
            if group == "financial":
                values = financial_map.get((parent, cutoff)) if parent else None
            elif group == "market":
                values = market_map.get((parent, cutoff)) if parent else None
            else:
                values = publication_map.get((parent, cutoff)) if parent else None
            if values is None:
                values = _blank_group_features(group)
                if not parent:
                    counters[group]["no_parent"] += 1
            available = _group_available(group, values)
            counters[group]["available" if available else "missing"] += 1
            for name in feature_names:
                features[name] = values.get(name)
            if group == "market":
                features["mkt_missing"] = values.get("mkt_missing", 1.0)
            if group == "publication":
                features["pub_missing"] = values.get("pub_missing", 1.0)
            if group == "financial":
                features["fin_facts_available"] = values.get("fin_facts_available", 0.0)
            availability[group] = available
        example["parent_company"] = parent or ""
        example["source_available"] = availability
    return counters


# --------------------------------------------------------------------- pipeline
def build(db_path: Path, *, cohort_size: int = DEFAULT_COHORT_SIZE,
          min_material: int = DEFAULT_MIN_MATERIAL,
          min_active_years: int = DEFAULT_MIN_ACTIVE_YEARS) -> tuple[dict[str, Any], dict[str, Any]]:
    connection = sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        panel, detail = build_p2(
            db_path, cohort_size=cohort_size, min_material=min_material,
            min_active_years=min_active_years)
        examples = panel["examples"]
        cutoffs = sorted({str(example["cutoff"]) for example in examples})
        parent_map, mapping_stats = entity_parent_map(connection)
        financial_map, financial_stats = financial_feature_map(connection, cutoffs)
        market_map, market_stats = market_feature_map(
            connection, cutoffs, company_ticker_map(load_companies("device"), None))
        publication_map, publication_stats = publication_feature_map(connection, cutoffs)
        availability = attach_source_groups(
            examples, parent_map, financial_map, market_map, publication_map)
        # Availability and parent coverage by cutoff / holdout status.
        by_cutoff: dict[str, dict[str, Any]] = {}
        for cutoff in cutoffs:
            rows = [row for row in examples if row["cutoff"] == cutoff]
            by_cutoff[cutoff] = {
                "rows": len(rows),
                "positives": sum(int(row["label"]) for row in rows),
                "rows_with_parent": sum(1 for row in rows if row.get("parent_company")),
                "positives_with_parent": sum(
                    int(row["label"]) for row in rows if row.get("parent_company")),
                **{f"rows_with_{group}": sum(
                    1 for row in rows if row["source_available"][group])
                   for group in SOURCE_GROUPS},
                **{f"positives_with_{group}": sum(
                    int(row["label"]) for row in rows if row["source_available"][group])
                   for group in SOURCE_GROUPS},
            }
        frozen_panel = detail["panel"]
        report = {
            "schema": "b105.entity_panel_sources.v1",
            "backlog_item": "B-018",
            "db": {"path": str(db_path), "sha256": sha256_file(db_path)},
            "frozen_panel": {
                "builder": "experiments.cycle2_coverage.run_cycle2.build_p2",
                "cohort_size": detail["universe"]["cohort_size"],
                "examples": frozen_panel["n_examples"],
                "positives": frozen_panel["n_positives"],
                "entities": frozen_panel["entity_count"],
                "origins": frozen_panel["origins"],
                "coverage_start": frozen_panel["coverage_start"],
                "coverage_end": frozen_panel["coverage_end"],
                "coverage_end_reference": CYCLE2_COVERAGE_END,
            },
            "feature_order": list(FEATURE_ORDER),
            "reference_features": list(BASE_PANEL_FEATURES),
            "source_groups": {group: list(names) for group, names in SOURCE_GROUPS.items()},
            "entity_to_company_join": mapping_stats | {
                "cohort_entities": frozen_panel["entity_count"],
                "examples_with_parent": sum(1 for row in examples if row.get("parent_company")),
                "examples_total": len(examples),
                "examples_with_parent_share": (
                    sum(1 for row in examples if row.get("parent_company")) / len(examples)
                    if examples else None),
                "parents_represented_in_panel": len({
                    row["parent_company"] for row in examples if row.get("parent_company")}),
            },
            "source_tables": {
                "financial": financial_stats,
                "market": market_stats,
                "publication": publication_stats,
            },
            "example_availability": {
                group: {
                    "available": counters["available"],
                    "missing": counters["missing"],
                    "no_parent": counters["no_parent"],
                    "available_share": counters["available"] / len(examples) if examples else None,
                    "available_positives": sum(
                        int(row["label"]) for row in examples
                        if row["source_available"][group]),
                    "total_positives": sum(int(row["label"]) for row in examples),
                }
                for group, counters in availability.items()
            },
            "by_cutoff": by_cutoff,
            "holdout_cutoffs": sorted(cutoffs)[-3:],
            "panel_sha1_of_example_ids": sha1(
                "|".join(sorted(str(row["example_id"]) for row in examples)))[:32],
        }
    finally:
        connection.close()
    return panel, report


# ----------------------------------------------------------------------- I/O
def panel_rows(panel: dict[str, Any]) -> list[dict[str, Any]]:
    """Compact per-example rows with a fixed-order feature vector."""
    rows = []
    for example in panel["examples"]:
        features = example.get("features") or {}
        rows.append({
            "example_id": example["example_id"],
            "cutoff": example["cutoff"],
            "entity": example["company_key"],
            "parent_company": example.get("parent_company", ""),
            "track": example["track_id"],
            "label": int(example["label"]),
            "first_target_event_date": example.get("first_target_event_date"),
            "features": [features.get(name) for name in FEATURE_ORDER],
            "source_available": {
                group: bool(example["source_available"].get(group))
                for group in SOURCE_GROUPS
            },
        })
    return rows


def write_panel(path: Path, panel: dict[str, Any]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with gzip.open(path, "wt", encoding="utf-8", newline="\n") as handle:
        for row in panel_rows(panel):
            handle.write(json.dumps(row, sort_keys=True, ensure_ascii=False,
                                    separators=(",", ":")) + "\n")
            count += 1
    return count


def read_panel(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            raw = json.loads(line)
            raw["features"] = dict(zip(FEATURE_ORDER, raw["features"]))
            rows.append(raw)
    return rows


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
                    encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=str(DEFAULT_DB))
    parser.add_argument("--panel", default=str(DEFAULT_PANEL))
    parser.add_argument("--availability", default=str(DEFAULT_AVAILABILITY))
    args = parser.parse_args(argv)
    try:
        panel, report = build(Path(args.db))
    except (FileNotFoundError, ValueError, sqlite3.DatabaseError) as error:
        print(f"[b105] FAIL: {error}", file=sys.stderr)
        return 2
    count = write_panel(Path(args.panel), panel)
    report["panel_artifact"] = {
        "path": str(args.panel),
        "rows": count,
        "format": "gzip JSONL; features as fixed-order vector (feature_order above)",
        "committed": False,
        "note": "large and fully regenerable from this script + the frozen store; "
                "commit the script/report, not necessarily the panel",
    }
    write_json(Path(args.availability), report)
    join = report["entity_to_company_join"]
    print(
        f"[b105] panel={count} rows; entities={report['frozen_panel']['entities']} "
        f"mapped_entities={join['entities_mapped_to_one_company']} "
        f"ambiguous={join['entities_ambiguous']} rows_with_parent={join['examples_with_parent']} "
        f"({join['examples_with_parent_share']:.1%}) | availability: "
        + ", ".join(f"{group}={stats['available_share']:.1%}"
                    for group, stats in report["example_availability"].items()))
    print(f"[b105] wrote {args.panel} and {args.availability}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
