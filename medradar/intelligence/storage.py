"""Market Intelligence storage, sharing MedRadar's SQLite connection.

Every fact carries valid time and knowledge time. Procurement snapshots are
explicitly marked not point-in-time usable; this is a safety property, not a
formatting detail.
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any, Iterable, Mapping

from ..db import DB
from ..util import ensure_dir, sha1, utc_now_iso

SCHEMA = """
CREATE TABLE IF NOT EXISTS company_identifiers (
    company_key TEXT NOT NULL,
    scheme TEXT NOT NULL,
    identifier TEXT NOT NULL,
    source TEXT NOT NULL,
    valid_from TEXT,
    valid_to TEXT,
    available_at TEXT NOT NULL,
    confidence REAL NOT NULL,
    evidence TEXT,
    PRIMARY KEY (company_key, scheme, identifier, source)
);
CREATE TABLE IF NOT EXISTS financial_facts (
    fact_id TEXT PRIMARY KEY,
    company_key TEXT NOT NULL,
    cik TEXT NOT NULL,
    taxonomy TEXT NOT NULL,
    tag TEXT NOT NULL,
    unit TEXT NOT NULL,
    value REAL NOT NULL,
    period_start TEXT,
    period_end TEXT NOT NULL,
    valid_time TEXT NOT NULL,
    available_at TEXT NOT NULL,
    form TEXT,
    fiscal_year INTEGER,
    fiscal_period TEXT,
    accession TEXT,
    frame TEXT,
    segment_scope TEXT NOT NULL DEFAULT 'consolidated',
    data_quality TEXT NOT NULL,
    source TEXT NOT NULL,
    retrieved_at TEXT NOT NULL,
    payload TEXT
);
CREATE INDEX IF NOT EXISTS idx_financial_pit
ON financial_facts(company_key, tag, unit, available_at, period_end);
CREATE TABLE IF NOT EXISTS procurement_awards (
    procurement_id TEXT PRIMARY KEY,
    buyer TEXT,
    buyer_subagency TEXT,
    supplier TEXT,
    company_key TEXT,
    product_category TEXT,
    naics_code TEXT,
    contract_value REAL,
    currency TEXT DEFAULT 'USD',
    announcement_date TEXT,
    award_date TEXT,
    period_start TEXT,
    period_end TEXT,
    country TEXT DEFAULT 'US',
    original_source TEXT NOT NULL,
    source_url TEXT,
    available_at TEXT NOT NULL,
    retrieved_at TEXT NOT NULL,
    pit_usable INTEGER NOT NULL DEFAULT 0,
    data_quality TEXT NOT NULL,
    match_confidence REAL,
    matched_alias TEXT,
    payload TEXT
);
CREATE INDEX IF NOT EXISTS idx_procurement_company_date
ON procurement_awards(company_key, award_date);
CREATE TABLE IF NOT EXISTS temporal_edges (
    edge_id TEXT PRIMARY KEY,
    subject_type TEXT NOT NULL,
    subject_id TEXT NOT NULL,
    relation TEXT NOT NULL,
    object_type TEXT NOT NULL,
    object_id TEXT NOT NULL,
    valid_time TEXT,
    available_at TEXT NOT NULL,
    assertion_status TEXT NOT NULL,
    evidence_source TEXT NOT NULL,
    evidence_id TEXT NOT NULL,
    confidence REAL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_edges_subject ON temporal_edges(subject_id, relation);
CREATE TABLE IF NOT EXISTS forecast_examples (
    example_id TEXT PRIMARY KEY,
    cutoff TEXT NOT NULL,
    horizon_months INTEGER NOT NULL,
    company_key TEXT NOT NULL,
    track_id TEXT NOT NULL,
    features TEXT NOT NULL,
    feature_available_at TEXT NOT NULL,
    label INTEGER,
    first_target_event_date TEXT,
    target_event_count INTEGER,
    maturity TEXT NOT NULL,
    dataset_version TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_examples_cutoff ON forecast_examples(cutoff, horizon_months);
CREATE TABLE IF NOT EXISTS horizon_forecasts (
    forecast_id TEXT PRIMARY KEY,
    target_company TEXT NOT NULL,
    technology_track TEXT NOT NULL,
    forecast_creation_time TEXT NOT NULL,
    historical_information_cutoff TEXT NOT NULL,
    forecast_horizon_months INTEGER NOT NULL,
    horizon_end TEXT NOT NULL,
    model_version TEXT NOT NULL,
    predicted_probability REAL NOT NULL,
    uncertainty TEXT NOT NULL,
    supporting_evidence TEXT NOT NULL,
    contradictory_evidence TEXT NOT NULL,
    verification_condition TEXT NOT NULL,
    baseline_probability REAL,
    status TEXT NOT NULL,
    outcome INTEGER,
    verified_at TEXT,
    verification_event_id TEXT
);
CREATE TABLE IF NOT EXISTS market_bars (
    ticker TEXT NOT NULL,
    date TEXT NOT NULL,
    open REAL,
    high REAL,
    low REAL,
    close REAL,
    adj_close REAL,
    volume INTEGER,
    source TEXT NOT NULL,
    retrieved_at TEXT NOT NULL,
    PRIMARY KEY (ticker, date)
);
CREATE INDEX IF NOT EXISTS idx_market_bars_date ON market_bars(date, ticker);
CREATE TABLE IF NOT EXISTS publication_counts (
    company_key TEXT NOT NULL,
    year INTEGER NOT NULL,
    works INTEGER NOT NULL,
    query TEXT,
    alias TEXT,
    source TEXT NOT NULL,
    retrieved_at TEXT NOT NULL,
    PRIMARY KEY (company_key, year, source)
);
CREATE TABLE IF NOT EXISTS patent_applications (
    application_id TEXT PRIMARY KEY,
    company_key TEXT,
    assignee TEXT,
    filing_date TEXT,
    publication_date TEXT,
    title TEXT,
    source TEXT NOT NULL,
    retrieved_at TEXT NOT NULL,
    payload TEXT
);
CREATE INDEX IF NOT EXISTS idx_patents_company_pub
ON patent_applications(company_key, publication_date);
"""


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)


class IntelligenceStore:
    def __init__(self, db: DB | str | Path) -> None:
        self.db = db if isinstance(db, DB) else DB(db)
        self.db.conn.executescript(SCHEMA)
        self.db.conn.commit()

    @property
    def conn(self) -> sqlite3.Connection:
        return self.db.conn

    def close(self) -> None:
        self.db.close()

    def __enter__(self) -> "IntelligenceStore":
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()

    def link_identifier(self, row: Mapping[str, Any]) -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO company_identifiers VALUES (?,?,?,?,?,?,?,?,?)",
            (
                row["company_key"], row["scheme"], str(row["identifier"]), row["source"],
                row.get("valid_from"), row.get("valid_to"), row["available_at"],
                float(row.get("confidence", 1.0)), row.get("evidence", ""),
            ),
        )

    def upsert_financial_facts(self, rows: Iterable[Mapping[str, Any]]) -> int:
        materialized = list(rows)
        self.conn.executemany(
            "INSERT OR REPLACE INTO financial_facts VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            [(
                r["fact_id"], r["company_key"], r["cik"], r.get("taxonomy", "us-gaap"),
                r["tag"], r["unit"], float(r["value"]), r.get("period_start"), r["period_end"],
                r["period_end"], r["available_at"], r.get("form"), r.get("fiscal_year"),
                r.get("fiscal_period"), r.get("accession"), r.get("frame"),
                "consolidated", r.get("data_quality", "companyfacts_no_segment_dimension"),
                r.get("source", "sec_xbrl_companyfacts"), r["retrieved_at"], _json(r.get("payload", {})),
            ) for r in materialized],
        )
        self.conn.commit()
        return len(materialized)

    def upsert_procurement(self, rows: Iterable[Mapping[str, Any]]) -> int:
        materialized = list(rows)
        self.conn.executemany(
            "INSERT OR REPLACE INTO procurement_awards VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            [(
                r["procurement_id"], r.get("buyer"), r.get("buyer_subagency"), r.get("supplier"),
                r.get("company_key"), r.get("product_category"), r.get("naics_code"),
                r.get("contract_value"), r.get("currency", "USD"), r.get("announcement_date"),
                r.get("award_date"), r.get("period_start"), r.get("period_end"),
                r.get("country", "US"), r.get("original_source", "usaspending_api_v2"),
                r.get("source_url"), r["available_at"], r["retrieved_at"],
                int(bool(r.get("pit_usable", False))), r["data_quality"], r.get("match_confidence"),
                r.get("matched_alias"), _json(r.get("payload", {})),
            ) for r in materialized],
        )
        self.conn.commit()
        return len(materialized)

    def add_observed_edge(self, *, subject: str, relation: str, object: str,
                          valid_time: str | None, available_at: str,
                          source: str, evidence_id: str, confidence: float = 1.0,
                          subject_type: str = "Company", object_type: str = "Entity") -> None:
        edge_id = sha1("|".join((subject, relation, object, source, evidence_id)))[:32]
        self.conn.execute(
            "INSERT OR REPLACE INTO temporal_edges VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (edge_id, subject_type, subject, relation, object_type, object, valid_time,
             available_at, "observed", source, evidence_id, confidence, utc_now_iso()),
        )

    def replace_examples(self, dataset_version: str, rows: Iterable[Mapping[str, Any]]) -> int:
        materialized = list(rows)
        with self.db.transaction():
            self.conn.execute("DELETE FROM forecast_examples WHERE dataset_version = ?", (dataset_version,))
            self.conn.executemany(
                "INSERT INTO forecast_examples VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                [(
                    r["example_id"], r["cutoff"], r["horizon_months"], r["company_key"],
                    r["track_id"], _json(r["features"]), r["feature_available_at"], r.get("label"),
                    r.get("first_target_event_date"), r.get("target_event_count"), r["maturity"],
                    dataset_version,
                ) for r in materialized],
            )
        return len(materialized)

    def upsert_forecast(self, row: Mapping[str, Any]) -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO horizon_forecasts VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                row["forecast_id"], row["target_company"], row["technology_track"],
                row["forecast_creation_time"], row["historical_information_cutoff"],
                row["forecast_horizon_months"], row["horizon_end"], row["model_version"],
                row["predicted_probability"], _json(row["uncertainty"]),
                _json(row["supporting_evidence"]), _json(row["contradictory_evidence"]),
                _json(row["verification_condition"]), row.get("baseline_probability"),
                row.get("status", "pending"), row.get("outcome"), row.get("verified_at"),
                row.get("verification_event_id"),
            ),
        )
        self.conn.commit()
