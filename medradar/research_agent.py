"""Deterministic, evidence-grounded research agent for the Market-to-R&D layer.

This module is deliberately **not** a chatbot and contains no model calls. It
implements a fixed, multi-step research workflow whose every factual claim is
traceable to a stored row, a registered forecast or a frozen artifact id:

``question template → plan → tools → evidence table → conflict detection →
hypothesis (explicitly labelled) → counter-evidence → statistical validation →
cited synthesis → uncertainty → research log → stop condition``

Hard rules enforced by the code and the tests:

* no probability is invented: the only probabilities are (a) rows registered in
  the canonical forecast registry, (b) the frozen model forecast rows in
  ``horizon_forecasts`` (with their creation time recorded) and (c) training
  base rates computed from stored examples. A missing probability is reported
  as ``None`` with an explicit "no registered forecast" status, never filled in;
* every claim whose ``evidence_status`` is ``observed`` or ``derived`` carries at
  least one citation pointing at an existing id (event, financial fact, example,
  market bar, publication count, forecast, registry prediction or TKG assertion);
* no network access and no LLM: the optional narrative hook does not exist here,
  so nothing can silently call an API;
* the temporal-knowledge-graph helper (``medradar/intelligence/graph_context.py``)
  is a soft, sibling-owned dependency: it is imported lazily *inside* the tool
  and its absence is reported as ``unavailable`` instead of failing.

Point-in-time discipline: event and financial availability is date-level
(``event_date/available_at`` and ``filed/available_at`` day values); model
forecasts use their creation timestamp. A date-only ``as_of`` therefore means
"everything public on that calendar day"; an ``as_of`` with a time also gates
forecast creation times.
"""
from __future__ import annotations

import argparse
import json
import math
import sqlite3
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping

from .config import load_companies
from .intelligence.evaluation.metrics import brier as brier_score
from .intelligence.evaluation.metrics import ece as expected_calibration_error
from .intelligence.features.financial_features import FEATURES as FINANCIAL_FEATURES
from .intelligence.features.financial_features import FLOW_TAGS, RD_TAGS, REVENUE_TAGS
from .intelligence.features.financial_features import financial_features
from .intelligence.features.market_features import FEATURES as MARKET_FEATURES
from .intelligence.features.market_features import MISSING_KEY as MARKET_MISSING_KEY
from .intelligence.features.market_features import market_features
from .intelligence.features.publication_features import (
    PUBLICATION_FEATURES,
    publication_features,
    publication_knowledge_date,
    usable_publication_years,
)
from .intelligence.features.research_features import _material_pma as material_pma
from .intelligence.sources.market_data import company_ticker_map, normalise_ticker
from .intelligence.sources.publications import load_counts
from .util import add_months, iso, parse_date, utc_now_iso

AGENT_VERSION = "research-agent-1"
DEFAULT_DORMANCY_MONTHS = 36
DEFAULT_HORIZON_MONTHS = 12
CITATION_CAP = 12
RESOLVED_CALIBRATION_MIN = 1
CALIBRATION_ECE_MIN = 10
MODEL_HIGH_THRESHOLD = 0.75
MODEL_VS_BASE_GAP = 0.15
REGISTRY_VS_FROZEN_GAP = 0.05
CONFLICT = "conflict"

TEMPLATES: dict[str, dict[str, str]] = {
    "entry_forecast": {
        "purpose": "Will an active company register its first material event in a dormant track?",
        "target": "entry",
    },
    "market_leading_indicator": {
        "purpose": "Does point-in-time market evidence add information beyond R&D history?",
        "target": "continuation",
    },
    "early_signal": {
        "purpose": "Is there early multi-source evidence that a track is becoming active?",
        "target": "continuation",
    },
    "strategic_shift": {
        "purpose": "Is a company's observed activity mix shifting toward a track?",
        "target": "continuation",
    },
    "cross_source_validation": {
        "purpose": "Do independent sources agree or conflict for a company-track pair?",
        "target": "continuation",
    },
}

#: Fixed tool plan per template: (tool, purpose). The order is part of the
#: deterministic workflow and is recorded verbatim in ``document["plan"]``.
TEMPLATE_PLANS: dict[str, tuple[tuple[str, str], ...]] = {
    "entry_forecast": (
        ("event_history", "Establish point-in-time material-event history and dormancy for the pair."),
        ("financial_context", "Check consolidated R&D/financial capacity evidence as of the cutoff."),
        ("market_context", "Check point-in-time market evidence for the company."),
        ("publication_context", "Check complete-year publication output and growth."),
        ("forecast_evidence", "Look up the canonical forecast registry for a registered probability."),
        ("graph_context", "Optional temporal-knowledge-graph context (soft dependency)."),
        ("counter_evidence", "Enumerate alternative explanations for observed activity."),
        ("baseline_comparison", "Compare the entry base rate with any model/registry probability."),
    ),
    "market_leading_indicator": (
        ("market_context", "Check point-in-time market evidence for the company and benchmarks."),
        ("event_history", "Establish the R&D/regulatory activity baseline for the pair."),
        ("financial_context", "Check consolidated R&D/financial evidence."),
        ("publication_context", "Check complete-year publication output."),
        ("forecast_evidence", "Look up the canonical forecast registry."),
        ("graph_context", "Optional temporal-knowledge-graph context (soft dependency)."),
        ("counter_evidence", "Enumerate alternative explanations for a market signal."),
        ("baseline_comparison", "Compare any model/registry probability with the historical base rate."),
    ),
    "early_signal": (
        ("event_history", "Measure current pair activity and the company's track mix."),
        ("publication_context", "Check complete-year publication activity for the company."),
        ("market_context", "Check point-in-time market evidence."),
        ("financial_context", "Check consolidated R&D/financial evidence."),
        ("forecast_evidence", "Look up the canonical forecast registry."),
        ("graph_context", "Optional temporal-knowledge-graph context (soft dependency)."),
        ("counter_evidence", "Enumerate alternative explanations for early activity."),
        ("baseline_comparison", "Compare any model/registry probability with the historical base rate."),
    ),
    "strategic_shift": (
        ("event_history", "Measure the company's activity in this track versus its other tracks."),
        ("market_context", "Check point-in-time market evidence."),
        ("financial_context", "Check consolidated R&D/financial evidence."),
        ("publication_context", "Check complete-year publication output."),
        ("counter_evidence", "Enumerate alternative explanations for a shift."),
        ("forecast_evidence", "Look up the canonical forecast registry."),
        ("graph_context", "Optional temporal-knowledge-graph context (soft dependency)."),
        ("baseline_comparison", "Compare any model/registry probability with the historical base rate."),
    ),
    "cross_source_validation": (
        ("event_history", "Establish the regulatory activity evidence."),
        ("financial_context", "Establish the consolidated financial evidence."),
        ("market_context", "Establish the market evidence."),
        ("publication_context", "Establish the publication evidence."),
        ("forecast_evidence", "Look up the canonical forecast registry."),
        ("graph_context", "Optional temporal-knowledge-graph context (soft dependency)."),
        ("counter_evidence", "Enumerate alternative explanations across sources."),
        ("baseline_comparison", "Compare any model/registry probability with the historical base rate."),
    ),
}

MISSING_SOURCES = [
    "patents: the USPTO Open Data Portal requires an API key that is absent in this environment, "
    "so no patent evidence is used",
    "hiring/jobs data: not collected",
    "market capitalisation and valuation multiples: no shares-outstanding data in this database",
    "segment- or product-level sales: only consolidated SEC facts are stored",
]

COMMON_LIMITATIONS = [
    "This is an association-and-prediction exercise, not causal inference: a market signal is not evidence "
    "that the market directs R&D, and a regulatory milestone is a lagging R&D proxy.",
    "Probabilities come only from the canonical registry or the frozen model forecast table; unavailable "
    "probabilities are reported as null rather than estimated by the agent.",
    "The event lane's availability time is decision_date + 14 days (estimated), and market bars are known "
    "by trading date only (the vendor publication time is unknown).",
    "Company resolution and the product-code → track taxonomy are the current curated mappings, not "
    "historical ontology versions.",
    "The canonical forecast registry is a sibling Phase-3 artifact; when it is absent every registry-backed "
    "claim is reported as unavailable instead of substituted.",
]

REGISTRY_STATUS = {
    "ok": "forecasts matched",
    "no_registry": "no canonical registry path was provided",
    "registry_missing": "the canonical registry file does not exist",
    "registry_unreadable": "the canonical registry file could not be opened or lacks the expected schema",
    "no_registered_forecast": "the registry contains no forecast whose target matches this company-track pair",
}


# --------------------------------------------------------------------------- time
def _as_of_day(as_of: Any) -> date:
    day = parse_date(as_of)
    if day is None:
        raise ValueError(f"invalid as_of {as_of!r}")
    return day


def _has_time(as_of: Any) -> bool:
    text = str(as_of or "")
    return "T" in text or " " in text


def _as_of_moment(as_of: Any) -> str:
    """Normalised UTC moment for forecast-creation comparisons."""
    text = str(as_of or "").strip()
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        day = _as_of_day(as_of)
        parsed = datetime(day.year, day.month, day.day, tzinfo=timezone.utc)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _visible_at(created_at: Any, as_of: Any) -> bool:
    """True when an ISO timestamp was known at ``as_of``.

    Date-only ``as_of`` values compare at day resolution (the row is usable on
    that calendar day); values with a time compare as UTC moments.
    """
    if created_at in (None, ""):
        return False
    if _has_time(as_of):
        try:
            left = datetime.fromisoformat(str(created_at).replace("Z", "+00:00"))
            right = datetime.fromisoformat(_as_of_moment(as_of).replace("Z", "+00:00"))
        except ValueError:
            return False
        if left.tzinfo is None:
            left = left.replace(tzinfo=timezone.utc)
        return left <= right
    created_day = parse_date(created_at)
    return bool(created_day and created_day <= _as_of_day(as_of))


# --------------------------------------------------------------------------- db
def _connect_ro(db_path: str | Path) -> sqlite3.Connection:
    """Open a SQLite database strictly read-only (never creates or migrates)."""
    path = Path(db_path)
    if not path.exists():
        raise FileNotFoundError(f"database not found: {path}")
    uri = "file:" + path.resolve().as_posix() + "?mode=ro"
    conn = sqlite3.connect(uri, uri=True, timeout=60)
    conn.row_factory = sqlite3.Row
    return conn


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    try:
        row = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)).fetchone()
    except sqlite3.DatabaseError:
        return False
    return row is not None


class _StoreAdapter:
    """Minimal ``store`` shim exposing ``.conn`` for the feature helpers."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn


def _ticker_map(tickers: Any = None) -> dict[str, str]:
    if tickers is not None:
        return {str(key): normalise_ticker(value) for key, value in dict(tickers).items()}
    try:
        return company_ticker_map(load_companies("device"))
    except Exception:  # pragma: no cover - config is part of the checkout
        return {}


# ----------------------------------------------------------------------- citations
def _cite(kind: str, locator: Any, label: str | None = None) -> dict[str, str]:
    citation = {"kind": kind, "locator": str(locator)}
    if label:
        citation["label"] = label
    return citation


def _dedupe_citations(citations: Iterable[Mapping[str, Any]]) -> list[dict[str, str]]:
    seen: dict[tuple[str, str], dict[str, str]] = {}
    for citation in citations:
        key = (str(citation.get("kind")), str(citation.get("locator")))
        if key not in seen:
            seen[key] = {k: str(v) for k, v in citation.items()}
    return [seen[key] for key in sorted(seen)]


def _num(value: Any, digits: int = 4) -> str:
    """Render a stored number for prose; the raw value stays in the evidence table."""
    if value is None:
        return "n/a"
    try:
        return f"{float(value):.{digits}f}"
    except (TypeError, ValueError):
        return str(value)


def _claim(claim_id: str, tool: str, statement: str, *, values: Mapping[str, Any] | None = None,
           citations: Iterable[Mapping[str, Any]] = (), evidence_status: str = "observed",
           warnings: Iterable[str] = ()) -> dict[str, Any]:    return {
        "claim_id": claim_id,
        "tool": tool,
        "statement": statement,
        "values": dict(values or {}),
        "citations": _dedupe_citations(citations),
        "evidence_status": evidence_status,
        "warnings": list(warnings),
    }


# ------------------------------------------------------------------------- tools
def forecast_evidence(registry_path: str | Path | None, company: str, track: str,
                      *, as_of: Any = None) -> dict[str, Any]:
    """Registered canonical forecasts for a company-track pair.

    Reads the Phase-3 forecast registry (schema ``forecast_registry.SCHEMA``)
    strictly read-only. ``as_of`` is optional here (the registry tool is also
    usable without a temporal frame); when it is supplied, forecasts created
    after ``as_of`` are returned with ``visible_at_as_of=False`` and are excluded
    from ``visible``.
    """
    output: dict[str, Any] = {
        "tool": "forecast_evidence", "status": "no_registry",
        "values": {"registry_path": str(registry_path) if registry_path else None,
                   "matched": 0, "visible": 0, "forecasts": [], "resolved_outcomes": [],
                   "calibration": {"status": "insufficient_verified_forecasts", "n": 0,
                                   "note": "no canonical registry available"}},
        "citations": [],
        "warnings": [REGISTRY_STATUS["no_registry"]],
    }
    if not registry_path:
        return output
    path = Path(registry_path)
    if not path.exists():
        output["status"] = "registry_missing"
        output["warnings"] = [f"{REGISTRY_STATUS['registry_missing']}: {path}"]
        return output
    try:
        conn = _connect_ro(path)
    except (OSError, sqlite3.DatabaseError) as exc:
        output["status"] = "registry_unreadable"
        output["warnings"] = [f"{REGISTRY_STATUS['registry_unreadable']}: {exc}"]
        return output
    try:
        if not (_table_exists(conn, "forecasts") and _table_exists(conn, "resolutions")):
            output["status"] = "registry_unreadable"
            output["warnings"] = [REGISTRY_STATUS["registry_unreadable"] + " (missing forecasts/resolutions tables)"]
            return output
        forecast_rows = [dict(row) for row in conn.execute(
            "SELECT * FROM forecasts ORDER BY information_cutoff, prediction_id")]
        matches = [row for row in forecast_rows
                   if _target_matches(row.get("target_type"), row.get("target_id"),
                                      row.get("target_attrs"), company, track)]
        resolutions: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in conn.execute("SELECT * FROM resolutions ORDER BY prediction_id, resolution_version"):
            resolutions[str(row["prediction_id"])].append(dict(row))
    except sqlite3.DatabaseError as exc:
        output["status"] = "registry_unreadable"
        output["warnings"] = [f"{REGISTRY_STATUS['registry_unreadable']}: {exc}"]
        return output
    finally:
        conn.close()
    records = []
    citations: list[dict[str, Any]] = []
    for row in matches:
        entries = resolutions.get(str(row["prediction_id"]), [])
        latest = entries[-1] if entries else None
        visible = _visible_at(row.get("generated_at"), as_of) if as_of is not None else True
        record = {
            "prediction_id": row["prediction_id"],
            "p": row["p"],
            "record_kind": row["record_kind"],
            "horizon_months": row["horizon_months"],
            "window_start": row["window_start"],
            "window_end": row["window_end"],
            "information_cutoff": row["information_cutoff"],
            "generated_at": row["generated_at"],
            "model_version": row["model_version"],
            "feature_version": row["feature_version"],
            "target_type": row["target_type"],
            "target_id": row["target_id"],
            "evidence": {
                "source_locator": row["source_locator"],
                "evidence_sha256": row["evidence_sha256"],
                "evidence_kind": row["evidence_kind"],
            },
            "provenance": json.loads(row["provenance"] or "[]"),
            "status": "pending" if latest is None else (
                "resolved_outcome" if latest.get("outcome") is not None else "resolved_censor"),
            "resolution": None if latest is None else {
                "version": latest["resolution_version"], "kind": latest["kind"],
                "outcome": latest.get("outcome"), "event_time": latest.get("event_time"),
                "resolved_at": latest["resolved_at"], "source_locator": latest["source_locator"],
            },
            "visible_at_as_of": visible,
        }
        records.append(record)
        citations.append(_cite("registry_forecast", row["prediction_id"],
                               f"registry forecast p={row['p']:.4f}"))
    visible_records = [record for record in records if record["visible_at_as_of"]]
    resolved = [(record["p"], int(record["resolution"]["outcome"]))
                for record in visible_records
                if record["resolution"] and record["resolution"].get("outcome") is not None]
    calibration: dict[str, Any] = {
        "status": "insufficient_verified_forecasts", "n": len(resolved), "min_required": RESOLVED_CALIBRATION_MIN,
        "note": "no resolved canonical forecast outcomes at or before the as-of date",
    }
    if resolved:
        labels = [label for _, label in resolved]
        probabilities = [probability for probability, _ in resolved]
        calibration = {
            "status": "evaluated",
            "n": len(resolved),
            "brier": brier_score(labels, probabilities),
            "ece": expected_calibration_error(labels, probabilities) if len(resolved) >= CALIBRATION_ECE_MIN else None,
            "note": "computed from resolved canonical forecast outcomes visible at the as-of date",
        }
    output.update({
        "status": "ok" if records else "no_registered_forecast",
        "values": {
            "registry_path": str(path),
            "matched": len(records),
            "visible": len(visible_records),
            "forecasts": records,
            "resolved_outcomes": [
                {"prediction_id": record["prediction_id"], "outcome": int(record["resolution"]["outcome"]),
                 "p": record["p"]} for record in visible_records
                if record["resolution"] and record["resolution"].get("outcome") is not None],
            "calibration": calibration,
        },
        "citations": _dedupe_citations(citations),
        "warnings": [] if records else [REGISTRY_STATUS["no_registered_forecast"]],
    })
    return output


def _target_matches(target_type: Any, target_id: Any, target_attrs: Any,
                    company: str, track: str) -> bool:
    """Best-effort target matching for the canonical registry.

    Documented assumption: the sibling Phase-3 task registers forecasts whose
    target identifies the pair either in ``target.attrs`` (keys such as
    ``company``/``company_key``/``target_company`` and
    ``track``/``track_id``/``technology_track``) or in ``target.id`` (tokens
    separated by ``|``, ``:`` or ``/`` or the two identifiers concatenated).
    Nothing is inferred from proximity or fuzzy matching.
    """
    wanted_company, wanted_track = str(company).strip().lower(), str(track).strip().lower()
    if not wanted_company or not wanted_track:
        return False
    attrs = target_attrs
    if isinstance(attrs, str):
        try:
            attrs = json.loads(attrs)
        except (TypeError, ValueError):
            attrs = None
    if isinstance(attrs, Mapping):
        values = {str(key).strip().lower(): str(value).strip().lower()
                  for key, value in attrs.items() if isinstance(value, (str, int))}
        company_keys = ("company", "company_key", "target_company", "company_id")
        track_keys = ("track", "track_id", "technology_track", "track_key")
        company_value = next((values[key] for key in company_keys if key in values), None)
        track_value = next((values[key] for key in track_keys if key in values), None)
        if company_value is not None and track_value is not None:
            return company_value == wanted_company and track_value == wanted_track
    tokens = {token.strip().lower()
              for token in str(target_id or "").replace("|", " ").replace(":", " ").replace("/", " ")
              .replace("::", " ").replace(",", " ").split()}
    if wanted_company in tokens and wanted_track in tokens:
        return True
    text = str(target_id or "").strip().lower()
    return text in (f"{wanted_company}|{wanted_track}", f"{wanted_company}:{wanted_track}",
                    f"{wanted_company}/{wanted_track}", f"{wanted_company}-{wanted_track}")


def _material_events(conn: sqlite3.Connection, company: str, track: str) -> list[dict[str, Any]]:
    if not _table_exists(conn, "events"):
        return []
    rows = [dict(row) for row in conn.execute(
        "SELECT event_id, kind, event_date, available_at, product_code, title, timestamp_quality, payload "
        "FROM events WHERE company_key = ? AND track_id = ? AND kind IN ('510k', 'pma') "
        "ORDER BY event_date, event_id", (company, track))]
    events = []
    for row in rows:
        if row["kind"] == "pma" and not material_pma(row.get("payload") or ""):
            continue
        day = parse_date(row["event_date"])
        available = parse_date(str(row.get("available_at") or "")[:10]) or day
        if day is None:
            continue
        row["day"] = day
        row["available"] = available
        events.append(row)
    return events


def event_history(db: str | Path, company: str, track: str, as_of: Any,
                  *, dormancy_months: int = DEFAULT_DORMANCY_MONTHS) -> dict[str, Any]:
    """Point-in-time material event history for one company-track pair."""
    as_of_day = _as_of_day(as_of)
    conn = _connect_ro(db)
    try:
        events = [event for event in _material_events(conn, company, track)
                  if event["day"] <= as_of_day and event["available"] <= as_of_day]
    finally:
        conn.close()
    if not events:
        return {
            "tool": "event_history", "status": "no_events",
            "values": {"total": 0, "recent_12m": 0, "recent_36m": 0, "first_event_date": None,
                       "last_event_date": None, "months_since_last_event": None,
                       "dormant": True, "dormancy_months": dormancy_months,
                       "events_by_year": {}, "timestamp_quality": {}, "event_ids": []},
            "citations": [],
            "warnings": ["no material 510(k)/PMA event for this pair is public at the as-of date"],
        }
    latest = max(event["day"] for event in events)
    recent_12 = [event for event in events if event["day"] > add_months(as_of_day, -12)]
    recent_36 = [event for event in events if event["day"] > add_months(as_of_day, -dormancy_months)]
    months_since = (as_of_day - latest).days / (365.25 / 12.0)
    by_year = Counter(str(event["day"].year) for event in events)
    quality = Counter(str(event.get("timestamp_quality") or "unknown") for event in events)
    cited = sorted(events, key=lambda event: (event["day"], event["event_id"]))[-CITATION_CAP:]
    citations = [_cite("event", event["event_id"], f"{event['kind']} {event['event_date']}")
                 for event in cited]
    return {
        "tool": "event_history", "status": "ok",
        "values": {
            "total": len(events),
            "recent_12m": len(recent_12),
            "recent_36m": len(recent_36),
            "first_event_date": min(event["day"] for event in events).isoformat(),
            "last_event_date": latest.isoformat(),
            "months_since_last_event": months_since,
            "dormant": not recent_36,
            "dormancy_months": dormancy_months,
            "events_by_year": {year: by_year[year] for year in sorted(by_year)},
            "timestamp_quality": {name: quality[name] for name in sorted(quality)},
            "event_ids": [event["event_id"] for event in cited],
            "event_id_count": len(events),
        },
        "citations": citations, "warnings": [],
    }


def _latest_annual_fact(rows: list[dict[str, Any]], tags: Iterable[str], as_of_day: date
                        ) -> dict[str, Any] | None:
    tag_set = set(tags)
    candidates = []
    for row in rows:
        if row.get("tag") not in tag_set or row.get("unit") != "USD":
            continue
        available, end = parse_date(row.get("available_at")), parse_date(row.get("period_end"))
        if not available or not end or available > as_of_day or end > as_of_day:
            continue
        start = parse_date(row.get("period_start"))
        if str(row.get("tag")) in FLOW_TAGS and (not start or not 300 <= (end - start).days <= 450):
            continue
        candidates.append((end, str(row.get("accession") or ""), available, row))
    if not candidates:
        return None
    candidates.sort(key=lambda item: (item[0], item[2], item[1]))
    end, _accession, available, row = candidates[-1]
    return {"fact_id": row.get("fact_id"), "tag": row.get("tag"), "value": row.get("value"),
            "period_end": end.isoformat(), "available_at": available.isoformat(),
            "data_quality": row.get("data_quality")}


def financial_context(db: str | Path, company: str, as_of: Any) -> dict[str, Any]:
    """Latest point-in-time consolidated financial evidence for one company."""
    as_of_day = _as_of_day(as_of)
    conn = _connect_ro(db)
    try:
        if not _table_exists(conn, "financial_facts"):
            rows: list[dict[str, Any]] = []
        else:
            rows = [dict(row) for row in conn.execute(
                "SELECT * FROM financial_facts WHERE company_key = ?", (company,))]
    finally:
        conn.close()
    if not rows:
        return {
            "tool": "financial_context", "status": "no_financial_facts",
            "values": {"features": {name: None for name in FINANCIAL_FEATURES},
                       "rd_fact": None, "revenue_fact": None, "facts_available": 0},
            "citations": [],
            "warnings": ["no consolidated SEC financial facts for this company (non-US filer or unresolved)"],
        }
    features = financial_features(rows, as_of_day)
    rd_fact = _latest_annual_fact(rows, RD_TAGS, as_of_day)
    revenue_fact = _latest_annual_fact(rows, REVENUE_TAGS, as_of_day)
    available_rows = [row for row in rows
                      if parse_date(row.get("available_at")) and parse_date(row["available_at"]) <= as_of_day]
    citations = []
    for fact in (rd_fact, revenue_fact):
        if fact and fact.get("fact_id"):
            citations.append(_cite("financial_fact", fact["fact_id"],
                                   f"{fact['tag']} {fact['period_end']}"))
    data_quality = sorted({str(row.get("data_quality") or "unknown") for row in available_rows})
    return {
        "tool": "financial_context", "status": "ok",
        "values": {"features": features, "rd_fact": rd_fact, "revenue_fact": revenue_fact,
                   "facts_available": len(available_rows), "data_quality": data_quality},
        "citations": citations,
        "warnings": [] if (rd_fact or revenue_fact) else [
            "financial facts exist but none is an annual observation public at the as-of date"],
    }


def _bar_date(conn: sqlite3.Connection, ticker: str, on_or_before: str) -> str | None:
    if not _table_exists(conn, "market_bars"):
        return None
    row = conn.execute(
        "SELECT MAX(date) FROM market_bars WHERE ticker = ? AND date <= ?",
        (normalise_ticker(ticker), on_or_before)).fetchone()
    return iso(row[0]) if row and row[0] else None


def market_context(db: str | Path, company: str, as_of: Any, *, tickers: Any = None) -> dict[str, Any]:
    """Point-in-time market feature values from ``market_bars`` with bar citations."""
    as_of_day = _as_of_day(as_of)
    mapping = _ticker_map(tickers)
    ticker = normalise_ticker(mapping.get(company))
    conn = _connect_ro(db)
    try:
        if not _table_exists(conn, "market_bars"):
            return {
                "tool": "market_context", "status": "no_market_data",
                "values": {"ticker": ticker or None, "last_bar_date": None,
                           "features": {name: None for name in MARKET_FEATURES},
                           MARKET_MISSING_KEY: 1, "benchmarks": {}},
                "citations": [],
                "warnings": ["the database has no market_bars table"],
            }
        if not ticker:
            return {
                "tool": "market_context", "status": "no_ticker",
                "values": {"ticker": None, "last_bar_date": None,
                           "features": {name: None for name in MARKET_FEATURES},
                           MARKET_MISSING_KEY: 1, "benchmarks": {}},
                "citations": [],
                "warnings": ["no curated ticker mapping for this company; market features are null"],
            }
        adapter = _StoreAdapter(conn)
        features = market_features(adapter, company, as_of_day, mapping)
        last_bar = _bar_date(conn, ticker, as_of_day.isoformat())
        window_start_bar = _bar_date(conn, ticker, (as_of_day - timedelta(days=365)).isoformat())
        benchmark_dates = {benchmark: _bar_date(conn, benchmark, as_of_day.isoformat())
                           for benchmark in ("SPY", "XBI")}
    finally:
        conn.close()
    citations = []
    if last_bar:
        citations.append(_cite("market_bar", f"{ticker}:{last_bar}", f"{ticker} last bar"))
    if window_start_bar:
        citations.append(_cite("market_bar", f"{ticker}:{window_start_bar}", f"{ticker} window-start bar"))
    for benchmark, bar in sorted(benchmark_dates.items()):
        if bar:
            citations.append(_cite("market_bar", f"{benchmark}:{bar}", f"{benchmark} last bar"))
    missing = int(features.get(MARKET_MISSING_KEY) or 0)
    status = "ok" if missing == 0 else ("partial" if last_bar else "no_market_data")
    return {
        "tool": "market_context", "status": status,
        "values": {"ticker": ticker, "last_bar_date": last_bar, "features": features,
                   "benchmarks": benchmark_dates},
        "citations": _dedupe_citations(citations),
        "warnings": [] if missing == 0 else [
            "at least one market feature is unavailable (null) at this cutoff; missing is flagged, never filled in"],
    }


def publication_context(db: str | Path, company: str, as_of: Any) -> dict[str, Any]:
    """Complete-year publication counts and growth with knowledge dates."""
    as_of_day = _as_of_day(as_of)
    conn = _connect_ro(db)
    try:
        counts = load_counts(_StoreAdapter(conn))
    finally:
        conn.close()
    company_counts = counts.get(company)
    if not company_counts:
        return {
            "tool": "publication_context", "status": "no_publication_data",
            "values": {"counts": {}, "features": {name: None for name in PUBLICATION_FEATURES},
                       "knowledge_date": None, "years_used": []},
            "citations": [],
            "warnings": ["no persisted OpenAlex annual publication counts for this company"],
        }
    features = publication_features(company_counts, as_of_day)
    years = usable_publication_years(as_of_day)
    used = years[-3:] if years else []
    citations = [_cite("publication_count", f"{company}:{year}",
                       f"{company} {year} works={company_counts.get(year)}") for year in used]
    knowledge = publication_knowledge_date(used[-1]) if used else None
    return {
        "tool": "publication_context", "status": "ok",
        "values": {"counts": {str(year): company_counts[year] for year in sorted(company_counts)},
                   "features": features, "years_used": used,
                   "knowledge_date": knowledge.isoformat() if knowledge else None},
        "citations": citations, "warnings": [],
    }


def graph_context(tkg_path: str | Path | None, company: str, track: str, as_of: Any) -> dict[str, Any]:
    """Optional temporal-knowledge-graph context (soft sibling dependency).

    The sibling Phase-3 task owns ``medradar/intelligence/graph_context.py``.
    That module is imported lazily *here* (never at import time), so this agent
    keeps working when it has not been merged. If the module is absent, a
    read-only raw query over the TKG schema is used when a TKG file is present;
    otherwise the tool reports ``unavailable`` and the workflow records the
    dependency as a data gap — it never fabricates graph edges.
    """
    if not tkg_path:
        return {"tool": "graph_context", "status": "not_requested",
                "values": {"tkg_path": None, "nodes": 0, "edges": 0}, "citations": [],
                "warnings": ["no --tkg path requested; graph context skipped"]}
    path = Path(tkg_path)
    if not path.exists():
        return {"tool": "graph_context", "status": "unavailable",
                "values": {"tkg_path": str(path), "nodes": 0, "edges": 0}, "citations": [],
                "warnings": ["the supplied TKG path does not exist"]}
    helper_error = None
    try:  # lazy import: the sibling module is optional
        from .intelligence import graph_context as sibling  # type: ignore[attr-defined]
    except Exception as exc:  # noqa: BLE001 - report the exact reason
        helper_error = f"{type(exc).__name__}: {exc}"
        sibling = None
    if sibling is not None:
        for name in ("graph_context", "query_graph_context", "context_for_pair"):
            function = getattr(sibling, name, None)
            if callable(function):
                try:
                    result = function(str(path), company, track, str(as_of))
                    return {
                        "tool": "graph_context", "status": "ok",
                        "values": {"tkg_path": str(path), "source": "medradar.intelligence.graph_context",
                                   "result": result,
                                   "nodes": len(result.get("nodes", [])) if isinstance(result, Mapping) else 0,
                                   "edges": len(result.get("edges", [])) if isinstance(result, Mapping) else 0},
                        "citations": [_cite("tkg_assertion", item.get("assertion_id"))
                                      for item in _iter_assertions(result)],
                        "warnings": [],
                    }
                except Exception as exc:  # noqa: BLE001
                    helper_error = f"sibling graph_context failed: {type(exc).__name__}: {exc}"
                    break
    try:
        conn = _connect_ro(path)
    except (OSError, sqlite3.DatabaseError) as exc:
        return {"tool": "graph_context", "status": "unavailable",
                "values": {"tkg_path": str(path), "nodes": 0, "edges": 0}, "citations": [],
                "warnings": [f"TKG file could not be read: {exc}", f"sibling helper: {helper_error}"]}
    try:
        if not (_table_exists(conn, "nodes") and _table_exists(conn, "edges")):
            return {"tool": "graph_context", "status": "unavailable",
                    "values": {"tkg_path": str(path), "nodes": 0, "edges": 0}, "citations": [],
                    "warnings": ["TKG schema not found (nodes/edges tables missing)",
                                 f"sibling helper: {helper_error}"]}
        moment = _as_of_moment(as_of)
        company_lower, track_lower = company.lower(), track.lower()
        nodes = [dict(row) for row in conn.execute(
            "SELECT assertion_id, node_type, node_id, recorded_at FROM nodes WHERE recorded_at <= ?",
            (moment,))]
        edges = [dict(row) for row in conn.execute(
            "SELECT assertion_id, edge_type, src_id, dst_id, recorded_at FROM edges WHERE recorded_at <= ?",
            (moment,))]
    finally:
        conn.close()

    def _matches(text: Any) -> bool:
        value = str(text or "").lower()
        return company_lower in value or track_lower in value

    matched_nodes = [row for row in nodes if _matches(row["node_id"]) or _matches(row["node_type"])]
    matched_edges = [row for row in edges if _matches(row["src_id"]) or _matches(row["dst_id"])
                     or _matches(row["edge_type"])]
    citations = [_cite("tkg_assertion", row["assertion_id"], f"node {row['node_id']}")
                 for row in matched_nodes[:CITATION_CAP]]
    citations += [_cite("tkg_assertion", row["assertion_id"],
                        f"edge {row['src_id']}->{row['dst_id']}") for row in matched_edges[:CITATION_CAP]]
    status = "ok" if citations else "no_graph_matches"
    warnings = []
    if helper_error:
        warnings.append(f"graph_context helper unavailable ({helper_error}); used a read-only raw TKG query")
    return {
        "tool": "graph_context", "status": status,
        "values": {"tkg_path": str(path), "source": "raw_tkg_read_only",
                   "nodes": len(matched_nodes), "edges": len(matched_edges)},
        "citations": _dedupe_citations(citations), "warnings": warnings,
    }


def _iter_assertions(result: Any) -> Iterable[Mapping[str, Any]]:
    if isinstance(result, Mapping):
        for key in ("nodes", "edges", "assertions"):
            items = result.get(key)
            if isinstance(items, list):
                for item in items:
                    if isinstance(item, Mapping) and item.get("assertion_id"):
                        yield item


def counter_evidence(db: str | Path, company: str, track: str, as_of: Any,
                     *, tickers: Any = None) -> dict[str, Any]:
    """Alternative explanations, each with citations or an explicit data gap."""
    as_of_day = _as_of_day(as_of)
    conn = _connect_ro(db)
    try:
        items: list[dict[str, Any]] = []
        warnings: list[str] = []
        if _table_exists(conn, "events"):
            track_rows = [dict(row) for row in conn.execute(
                "SELECT event_id, kind, event_date, available_at, company_key, payload FROM events "
                "WHERE track_id = ? AND company_key IS NOT NULL AND company_key <> ? "
                "AND kind IN ('510k','pma') ORDER BY event_date, event_id", (track, company))]
            track_rows = [row for row in track_rows
                          if parse_date(row["event_date"])
                          and parse_date(row["event_date"]) <= as_of_day
                          and (parse_date(str(row.get("available_at") or "")[:10])
                               or parse_date(row["event_date"])) <= as_of_day
                          and (row["kind"] == "510k" or material_pma(row.get("payload") or ""))]
            recent_track = [row for row in track_rows
                            if parse_date(row["event_date"]) > add_months(as_of_day, -12)]
            by_company = Counter(str(row["company_key"]) for row in recent_track)
            top_companies = sorted(by_company.items(), key=lambda item: (-item[1], item[0]))[:5]
            cited = sorted(track_rows, key=lambda row: (row["event_date"], row["event_id"]))[-CITATION_CAP:]
            items.append({
                "check": "track_activity_by_other_companies",
                "finding": (f"{len(recent_track)} material events by other companies in {track} in the "
                            f"trailing 12 months (total in window: {len(track_rows)}); track-level activity "
                            "could explain an individual company's observed behaviour."),
                "values": {"recent_12m_other_company_events": len(recent_track),
                           "total_other_company_events": len(track_rows),
                           "top_other_companies": [{"company": name, "events": count}
                                                   for name, count in top_companies]},
                "citations": [_cite("event", row["event_id"], f"{row['company_key']} {row['event_date']}")
                              for row in cited],
                "evidence_status": "observed" if track_rows else "not_available",
            })
            company_rows = [dict(row) for row in conn.execute(
                "SELECT event_id, kind, event_date, available_at, track_id, payload FROM events "
                "WHERE company_key = ? AND kind IN ('510k','pma') ORDER BY event_date, event_id", (company,))]
            company_rows = [row for row in company_rows
                            if parse_date(row["event_date"])
                            and parse_date(row["event_date"]) <= as_of_day
                            and (parse_date(str(row.get("available_at") or "")[:10])
                                 or parse_date(row["event_date"])) <= as_of_day
                            and (row["kind"] == "510k" or material_pma(row.get("payload") or ""))]
            recent_company = [row for row in company_rows
                              if parse_date(row["event_date"]) > add_months(as_of_day, -12)]
            by_track = Counter(str(row["track_id"]) for row in recent_company)
            other_tracks = sorted(((name, count) for name, count in by_track.items() if name != track),
                                  key=lambda item: (-item[1], item[0]))[:5]
            cited_company = sorted(recent_company,
                                   key=lambda row: (row["event_date"], row["event_id"]))[-CITATION_CAP:]
            items.append({
                "check": "company_activity_in_other_tracks",
                "finding": (f"the company has {len(recent_company)} material events in the trailing 12 months "
                            f"across {len({row['track_id'] for row in recent_company})} tracks; activity outside "
                            f"{track} can make a pair-level signal look stronger or weaker than it is."),
                "values": {"recent_12m_company_events": len(recent_company),
                           "other_tracks": [{"track": name, "events": count} for name, count in other_tracks]},
                "citations": [_cite("event", row["event_id"], f"{row['track_id']} {row['event_date']}")
                              for row in cited_company],
                "evidence_status": "observed" if company_rows else "not_available",
            })
        else:
            warnings.append("events table missing; event-based counter-evidence unavailable")
        # Market-regime counter-evidence.
        mapping = _ticker_map(tickers)
        market = market_context(db, company, as_of, tickers=mapping) if mapping else {
            "tool": "market_context", "status": "no_ticker", "values": {}, "citations": [], "warnings": []}
        features = market.get("values", {}).get("features", {})
        regime = features.get("mkt_regime_spy_above_200d")
        spy_return = features.get("mkt_rel_spy_12m")
        items.append({
            "check": "market_regime",
            "finding": (
                "SPY is above its 200-day average at the as-of date; broad-market conditions could explain part "
                "of any market signal." if regime == 1 else
                "SPY is not above its 200-day average at the as-of date; a market signal may be cyclical rather "
                "than company-specific." if regime == 0 else
                "the benchmark regime could not be computed at this date."),
            "values": {"spy_above_200d": regime, "company_rel_spy_12m": spy_return},
            "citations": market.get("citations", []),
            "evidence_status": "derived" if regime is not None else "not_available",
        })
        # Peer financial trend counter-evidence.
        peer = _peer_financial_trend(conn, as_of_day)
        items.append(peer)
        warnings.extend(peer.pop("warnings", []))
    finally:
        conn.close()
    citations = _dedupe_citations(citation for item in items for citation in item["citations"])
    return {
        "tool": "counter_evidence",
        "status": "ok" if any(item["evidence_status"] != "not_available" for item in items) else "no_data",
        "values": {"items": items},
        "citations": citations, "warnings": warnings,
    }


def _peer_financial_trend(conn: sqlite3.Connection, as_of_day: date) -> dict[str, Any]:
    if not _table_exists(conn, "financial_facts"):
        return {"check": "peer_financial_trend", "finding": "no consolidated financial facts are stored.",
                "values": {"peer_growth_median": None, "peers_used": 0}, "citations": [],
                "evidence_status": "not_available", "warnings": []}
    rows = [dict(row) for row in conn.execute("SELECT * FROM financial_facts")]
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[str(row["company_key"])].append(row)
    growths: list[float] = []
    citations: list[dict[str, Any]] = []
    for company in sorted(grouped):
        values = financial_features(grouped[company], as_of_day)
        growth = values.get("fin_revenue_growth")
        if growth is None or not math.isfinite(float(growth)):
            continue
        growths.append(float(growth))
        fact = _latest_annual_fact(grouped[company], REVENUE_TAGS, as_of_day)
        if fact and fact.get("fact_id") and len(citations) < CITATION_CAP:
            citations.append(_cite("financial_fact", fact["fact_id"],
                                   f"{company} revenue {fact['period_end']}"))
    growths.sort()
    median = growths[len(growths) // 2] if growths else None
    finding = ("no peer-company revenue growth could be computed at this date."
               if median is None else
               f"median annual consolidated revenue growth across {len(growths)} peer companies is "
               f"{median:.4f} at the as-of date; a peer-wide trend is an alternative explanation for a "
               "company-level financial signal.")
    return {"check": "peer_financial_trend", "finding": finding,
            "values": {"peer_growth_median": median, "peers_used": len(growths)},
            "citations": _dedupe_citations(citations),
            "evidence_status": "derived" if median is not None else "not_available",
            "warnings": [] if median is not None else ["no peer financial growth available"]}


def _resolve_model_probability(conn: sqlite3.Connection, company: str, track: str, as_of: Any, *,
                               target: str, registry: str | Path | None) -> dict[str, Any]:
    """Model/registry probability only; never a fabricated estimate."""
    evidence = forecast_evidence(registry, company, track, as_of=as_of)
    visible = [record for record in evidence["values"].get("forecasts", [])
               if record.get("visible_at_as_of")]
    preferred = [record for record in visible if record.get("record_kind") == "forecast"] or visible
    preferred.sort(key=lambda record: (str(record.get("information_cutoff") or ""),
                                       str(record.get("prediction_id"))))
    if preferred:
        record = preferred[-1]
        return {
            "p": record["p"], "source": "canonical_registry",
            "citation": _cite("registry_forecast", record["prediction_id"],
                              f"registry p={record['p']:.4f}"),
            "prediction_id": record["prediction_id"], "record_kind": record["record_kind"],
            "information_cutoff": record["information_cutoff"],
            "horizon_months": record["horizon_months"],
            "created_at": record["generated_at"], "target": target,
            "status": "ok",
        }
    if target == "continuation" and _table_exists(conn, "horizon_forecasts"):
        rows = [dict(row) for row in conn.execute(
            "SELECT * FROM horizon_forecasts WHERE target_company = ? AND technology_track = ? "
            "ORDER BY forecast_creation_time, forecast_id", (company, track))]
        rows = [row for row in rows if _visible_at(row.get("forecast_creation_time"), as_of)]
        if rows:
            row = rows[-1]
            return {
                "p": row["predicted_probability"], "source": "frozen_model_forecasts",
                "citation": _cite("horizon_forecast", row["forecast_id"],
                                  f"frozen model p={row['predicted_probability']:.4f}"),
                "forecast_id": row["forecast_id"], "information_cutoff": row["historical_information_cutoff"],
                "horizon_months": row["forecast_horizon_months"],
                "created_at": row["forecast_creation_time"], "target": target,
                "baseline_probability": row.get("baseline_probability"),
                "status": row.get("status") or "pending",
                "uncertainty": _json_or_none(row.get("uncertainty")),
                "verification_condition": _json_or_none(row.get("verification_condition")),
            }
    return {"p": None, "source": None, "citation": None, "target": target, "status": "none",
            "note": ("no canonical-registry forecast was visible at the as-of date"
                     if target == "entry" else
                     "no canonical-registry forecast and no visible frozen model forecast for this pair")}


def _json_or_none(value: Any) -> Any:
    if value is None:
        return None
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return None


def baseline_comparison(db: str | Path, company: str, track: str, as_of: Any, *,
                        target: str = "continuation", registry: str | Path | None = None) -> dict[str, Any]:
    """Per-pair historical base rate under the purged rule, versus any model p."""
    as_of_day = _as_of_day(as_of)
    dataset_version = "first_entry_v1" if target == "entry" else "reverse_rd_v1"
    conn = _connect_ro(db)
    try:
        if not _table_exists(conn, "forecast_examples"):
            return {"tool": "baseline_comparison", "status": "no_examples",
                    "values": {"dataset_version": dataset_version, "pair_rows": 0, "pair_positives": 0,
                               "pair_base_rate": None, "model": None, "delta": None,
                               "global_base_rate": None, "latest_mature_cutoff": None},
                    "citations": [], "warnings": ["forecast_examples table missing"]}
        rows = [dict(row) for row in conn.execute(
            "SELECT example_id, cutoff, label, maturity, first_target_event_date FROM forecast_examples "
            "WHERE dataset_version = ? AND company_key = ? AND track_id = ? "
            "ORDER BY cutoff, example_id", (dataset_version, company, track))]
        model = _resolve_model_probability(conn, company, track, as_of, target=target, registry=registry)
        all_rows = [dict(row) for row in conn.execute(
            "SELECT example_id, cutoff, label, maturity FROM forecast_examples WHERE dataset_version = ?",
            (dataset_version,))]
    finally:
        conn.close()
    horizon = DEFAULT_HORIZON_MONTHS
    mature = [row for row in rows if row.get("maturity") == "mature" and row.get("label") is not None]
    purged = [row for row in mature
              if add_months(parse_date(row["cutoff"]), horizon) <= as_of_day]
    pair_positives = sum(int(row["label"]) for row in purged)
    pair_rate = pair_positives / len(purged) if purged else None
    global_mature = [row for row in all_rows if row.get("maturity") == "mature" and row.get("label") is not None]
    global_purged = [row for row in global_mature
                     if add_months(parse_date(row["cutoff"]), horizon) <= as_of_day]
    global_rate = (sum(int(row["label"]) for row in global_purged) / len(global_purged)
                   if global_purged else None)
    latest_cutoff = max((row["cutoff"] for row in global_mature), default=None)
    citations = [_cite("example", row["example_id"],
                       f"label={row['label']} cutoff={row['cutoff']}") for row in purged[-CITATION_CAP:]]
    if model.get("citation"):
        citations.append(model["citation"])
    model_p = model.get("p")
    delta = (model_p - pair_rate) if (model_p is not None and pair_rate is not None) else None
    if not purged:
        interpretation = ("no matured purged example exists for this pair at the as-of date; the pair base rate "
                          "is unavailable rather than zero.")
    elif len(purged) < 10:
        interpretation = (f"only {len(purged)} matured purged pair examples exist; the base rate is a weak "
                          "reference, not a stable estimate.")
    else:
        interpretation = (f"the pair's historical base rate is based on {len(purged)} matured purged examples; "
                          "it is a reference rate for comparison, not a causal effect.")
    if model_p is None:
        model_note = model.get("note") or "no model or registry probability is available at this as-of date"
    elif delta is None:
        model_note = "a model probability exists but there is no matured pair base rate to compare it with"
    else:
        direction = "above" if delta > 0 else ("below" if delta < 0 else "equal to")
        model_note = (f"the model probability is {abs(delta):.4f} {direction} the purged pair base rate; "
                      "the difference is a ranking/calibration comparison, not evidence of skill.")
    return {
        "tool": "baseline_comparison", "status": "ok" if rows else "no_examples",
        "values": {
            "dataset_version": dataset_version, "target": target, "horizon_months": horizon,
            "pair_rows": len(rows), "pair_purged_rows": len(purged), "pair_positives": pair_positives,
            "pair_base_rate": pair_rate, "global_base_rate": global_rate,
            "global_purged_rows": len(global_purged), "latest_mature_cutoff": latest_cutoff,
            "model": model, "model_p": model_p, "delta": delta,
            "interpretation": interpretation + " " + model_note,
        },
        "citations": _dedupe_citations(citations),
        "warnings": [] if purged else ["no matured purged pair examples at this as-of date"],
    }


# ------------------------------------------------------------------- conflicts
def detect_conflicts(tool_outputs: Mapping[str, Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Deterministic cross-source conflict rules.

    A conflict is *reported*, never resolved by the agent: it is an explicit
    statement that two evidence sources disagree, with citations to both.
    """
    conflicts: list[dict[str, Any]] = []

    def add(rule: str, description: str, claims: list[str],
            citations: Iterable[Mapping[str, Any]]) -> None:
        conflicts.append({
            "conflict_id": f"conflict:{len(conflicts) + 1}",
            "rule": rule,
            "description": description,
            "claims": claims,
            "citations": _dedupe_citations(citations),
        })

    baseline = tool_outputs.get("baseline_comparison", {}).get("values", {})
    events = tool_outputs.get("event_history", {}).get("values", {})
    market = tool_outputs.get("market_context", {}).get("values", {}).get("features", {})
    financial = tool_outputs.get("financial_context", {}).get("values", {}).get("features", {})
    publications = tool_outputs.get("publication_context", {}).get("values", {}).get("features", {})
    registry = tool_outputs.get("forecast_evidence", {}).get("values", {})
    pair_rate = baseline.get("pair_base_rate")
    model_p = baseline.get("model_p")
    if model_p is not None and pair_rate is not None and model_p >= MODEL_HIGH_THRESHOLD \
            and model_p - pair_rate >= MODEL_VS_BASE_GAP:
        add("model_high_vs_base_rate_low",
            f"the model/registry probability {_num(model_p)} is at least {MODEL_VS_BASE_GAP:.2f} above the "
            f"purged pair base rate {_num(pair_rate)}; either the model uses information the base rate ignores "
            "or it is over-confident on this pair.",
            ["baseline_comparison", "forecast_evidence"],
            tool_outputs.get("baseline_comparison", {}).get("citations", []))
    registry_forecasts = [record for record in registry.get("forecasts", [])
                          if record.get("visible_at_as_of")]
    frozen = baseline.get("model", {})
    if registry_forecasts and frozen.get("source") == "frozen_model_forecasts":
        best = max(registry_forecasts, key=lambda record: (record.get("information_cutoff") or "",
                                                           record.get("prediction_id") or ""))
        registry_p, frozen_p = best.get("p"), frozen.get("p")
        if registry_p is not None and frozen_p is not None and abs(registry_p - frozen_p) > REGISTRY_VS_FROZEN_GAP:
            add("registry_vs_frozen_artifact_mismatch",
                f"the canonical registry probability {_num(registry_p)} differs from the frozen model forecast "
                f"{_num(frozen_p)} for the same pair by more than {REGISTRY_VS_FROZEN_GAP:.2f}; the registry row "
                "must be checked for a different information cutoff or model version.",
                ["forecast_evidence", "baseline_comparison"],
                [*[citation for citation in registry.get("citations", [])],
                 *( [frozen["citation"]] if frozen.get("citation") else [])])
    market_positive = market.get("mkt_ret_12m") is not None and market.get("mkt_ret_12m") > 0
    fundamentals_negative = any(
        isinstance(financial.get(name), (int, float)) and financial[name] < 0
        for name in ("fin_revenue_growth", "fin_rd_growth"))
    if market_positive and fundamentals_negative:
        add("market_positive_vs_fundamentals_negative",
            "the trailing 12-month market return is positive while consolidated revenue and/or R&D growth is "
            "negative; the market signal is not confirmed by the fundamentals in this database.",
            ["market_context", "financial_context"],
            tool_outputs.get("market_context", {}).get("citations", []))
    pub_growth = publications.get("pub_growth_prev_year")
    if market_positive and isinstance(pub_growth, (int, float)) and pub_growth < 0:
        add("market_positive_vs_publication_negative",
            "the trailing 12-month market return is positive while complete-year publication output is declining; "
            "market sentiment and research output disagree.",
            ["market_context", "publication_context"],
            tool_outputs.get("publication_context", {}).get("citations", []))
    recent_other = None
    for item in tool_outputs.get("counter_evidence", {}).get("values", {}).get("items", []):
        if item.get("check") == "track_activity_by_other_companies":
            recent_other = item.get("values", {}).get("recent_12m_other_company_events")
    pair_recent = events.get("recent_36m")
    if isinstance(recent_other, int) and recent_other >= 10 and isinstance(pair_recent, int) and pair_recent == 0:
        add("track_activity_vs_company_dormancy",
            f"other companies registered {recent_other} material events in this track in the last 12 months "
            "while this pair has no event in the last 36 months; track-level activity is not company-level intent.",
            ["counter_evidence:track_activity_by_other_companies", "event_history"],
            tool_outputs.get("event_history", {}).get("citations", []))
    return conflicts


# ----------------------------------------------------------------- focus block
def template_focus(template: str, tool_outputs: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    """Template-specific derived analysis (deterministic, citation-preserving)."""
    events = tool_outputs.get("event_history", {}).get("values", {})
    financial = tool_outputs.get("financial_context", {}).get("values", {}).get("features", {})
    market = tool_outputs.get("market_context", {}).get("values", {})
    publications = tool_outputs.get("publication_context", {}).get("values", {})
    baseline = tool_outputs.get("baseline_comparison", {}).get("values", {})
    focus: dict[str, Any] = {"template": template}
    if template == "entry_forecast":
        months = events.get("months_since_last_event")
        focus["dormancy"] = {
            "last_event_date": events.get("last_event_date"),
            "months_since_last_event": months,
            "dormant": events.get("dormant"),
            "entry_base_rate": baseline.get("pair_base_rate"),
            "entry_base_rows": baseline.get("pair_purged_rows"),
            "note": ("the entry target asks about a first observed event in a track the company has not touched "
                     "for at least the dormancy window; being dormant is a precondition, not evidence of intent."),
        }
    elif template == "market_leading_indicator":
        focus["market_vs_rd_history"] = {
            "market_ret_12m": market.get("features", {}).get("mkt_ret_12m"),
            "market_rel_spy_12m": market.get("features", {}).get("mkt_rel_spy_12m"),
            "company_events_12m": events.get("recent_12m"),
            "company_events_36m": events.get("recent_36m"),
            "rd_momentum_proxy": ("no positive pair activity in 12 months" if not events.get("recent_12m")
                                  else "pair activity observed in the last 12 months"),
            "note": ("market data can only add a *leading-indicator hypothesis*; this agent does not test "
                     "incremental predictive value, and no causal market-to-R&D claim is made."),
        }
    elif template == "early_signal":
        by_year = events.get("events_by_year", {})
        years = sorted(by_year)
        recent = sum(by_year[year] for year in years[-2:]) if years else 0
        prior = sum(by_year[year] for year in years[-4:-2]) if len(years) >= 4 else 0
        focus["signal_density"] = {
            "events_by_year": by_year,
            "events_last_2_years": recent,
            "events_prior_2_years": prior,
            "publication_prev_year": publications.get("features", {}).get("pub_count_prev_year"),
            "publication_growth": publications.get("features", {}).get("pub_growth_prev_year"),
            "market_ret_12m": market.get("features", {}).get("mkt_ret_12m"),
            "note": ("early evidence is a description of the current record, not a forecast; it cannot be "
                     "evaluated without a prospective test."),
        }
    elif template == "strategic_shift":
        by_year = events.get("events_by_year", {})
        years = sorted(by_year)
        recent = sum(by_year[year] for year in years[-2:]) if years else 0
        prior = sum(by_year[year] for year in years[-4:-2]) if len(years) >= 4 else 0
        total = sum(by_year.values())
        focus["track_shift"] = {
            "events_last_2_years": recent,
            "events_prior_2_years": prior,
            "share_of_company_pair_events_last_2_years": (recent / total if total else None),
            "pair_events_total": total,
            "financial_rd_growth": financial.get("fin_rd_growth"),
            "note": ("a shift is inferred from observed public events only; absence of events is not evidence "
                     "that internal research stopped."),
        }
    elif template == "cross_source_validation":
        signals = []
        if events.get("recent_12m") is not None:
            signals.append({"source": "events", "signal": "active" if events.get("recent_12m") else "inactive",
                            "value": events.get("recent_12m")})
        growth = financial.get("fin_revenue_growth")
        if growth is not None:
            signals.append({"source": "financial", "signal": "growing" if growth > 0 else "contracting",
                            "value": growth})
        market_return = market.get("features", {}).get("mkt_ret_12m")
        if market_return is not None:
            signals.append({"source": "market", "signal": "positive" if market_return > 0 else "negative",
                            "value": market_return})
        pub_growth = publications.get("features", {}).get("pub_growth_prev_year")
        if pub_growth is not None:
            signals.append({"source": "publications", "signal": "growing" if pub_growth > 0 else "declining",
                            "value": pub_growth})
        model_p = baseline.get("model_p")
        if model_p is not None:
            signals.append({"source": "model", "signal": "high" if model_p >= 0.5 else "low", "value": model_p})
        negative = {"inactive", "negative", "contracting", "declining", "low"}
        orientations = {bool(item["signal"] in negative) for item in signals}
        focus["source_agreement"] = {
            "signals": signals,
            "agreement": ("insufficient sources" if len(signals) < 2 else
                          "consistent" if len(orientations) == 1 else "mixed"),
            "note": "source agreement is descriptive; it is not scored as a probability by this agent.",
        }
    return focus


# --------------------------------------------------------------------- workflow
def question_text(template: str, company: str, track: str, as_of: Any) -> str:
    moment = iso(as_of) or str(as_of)
    if template == "entry_forecast":
        return f"Will {company} register a first material event in {track} within 12 months of {moment}?"
    if template == "market_leading_indicator":
        return (f"Does point-in-time market evidence for {company} add information beyond R&D history about "
                f"future {track} activity after {moment}?")
    if template == "early_signal":
        return f"Is there early multi-source evidence that {track} is becoming active around {moment}?"
    if template == "strategic_shift":
        return f"Is {company} shifting observed research activity toward {track} as of {moment}?"
    if template == "cross_source_validation":
        return f"Do independent sources agree or conflict for {company} / {track} at {moment}?"
    raise ValueError(f"unknown template {template!r}")


def run_agent(company: str, track: str, *, template: str = "entry_forecast", as_of: Any,
              db: str | Path, registry: str | Path | None = None, tkg: str | Path | None = None,
              tickers: Any = None, now: Callable[[], str] = utc_now_iso) -> dict[str, Any]:
    """Run the deterministic evidence-grounded workflow and return a JSON document.

    The output is a plain JSON-serialisable dict; only ``log[].at`` timestamps
    depend on wall-clock time. Running the same inputs twice produces identical
    evidence, conflicts, hypothesis, synthesis and citations.
    """
    if template not in TEMPLATES:
        raise ValueError(f"unknown template {template!r}; choose one of {sorted(TEMPLATES)}")
    plan_spec = TEMPLATE_PLANS[template]
    as_of_day = _as_of_day(as_of)
    moment = _as_of_moment(as_of)
    document: dict[str, Any] = {
        "agent_version": AGENT_VERSION,
        "question": {
            "text": question_text(template, company, track, as_of),
            "company": company, "track": track, "template": template,
            "as_of": moment if _has_time(as_of) else as_of_day.isoformat(),
        },
        "template": template,
        "as_of": moment if _has_time(as_of) else as_of_day.isoformat(),
        "company": company, "track": track,
        "plan": [],
        "steps": [],
        "evidence": [],
        "conflicts": [],
        "hypothesis": {},
        "counter_evidence": {},
        "statistical_validation": {},
        "template_focus": {},
        "uncertainty": {},
        "synthesis": [],
        "citations": [],
        "limitations": list(COMMON_LIMITATIONS),
        "log": [],
        "stop_condition": {},
        "degraded": False,
        "failures": [],
    }
    for index, (tool, purpose) in enumerate(plan_spec, start=1):
        document["plan"].append({"seq": index, "tool": tool, "purpose": purpose})
    log: list[dict[str, Any]] = document["log"]

    def log_event(phase: str, *, tool: str | None = None, status: str | None = None,
                  note: str | None = None, citations: int = 0) -> None:
        log.append({"seq": len(log) + 1, "at": now(), "phase": phase, "tool": tool,
                    "status": status, "citations": citations, "note": note})

    log_event("plan", note=f"{len(plan_spec)} deterministic tool steps for template {template}")
    outputs: dict[str, dict[str, Any]] = {}
    claims: list[dict[str, Any]] = document["evidence"]
    tool_args = {"company": company, "track": track, "as_of": document["as_of"]}
    for step in plan_spec:
        tool = step[0]
        if tool == "forecast_evidence":
            result = forecast_evidence(registry, company, track, as_of=as_of)
        elif tool == "event_history":
            result = event_history(db, company, track, as_of)
        elif tool == "financial_context":
            result = financial_context(db, company, as_of)
        elif tool == "market_context":
            result = market_context(db, company, as_of, tickers=tickers)
        elif tool == "publication_context":
            result = publication_context(db, company, as_of)
        elif tool == "graph_context":
            result = graph_context(tkg, company, track, as_of)
        elif tool == "counter_evidence":
            result = counter_evidence(db, company, track, as_of, tickers=tickers)
        elif tool == "baseline_comparison":
            result = baseline_comparison(db, company, track, as_of, target=TEMPLATES[template]["target"],
                                         registry=registry)
        else:  # pragma: no cover - plans are fixed
            raise AssertionError(f"unplanned tool {tool}")
        outputs[tool] = result
        citations = result.get("citations", [])
        document["steps"].append({
            "seq": len(document["steps"]) + 1, "tool": tool, "purpose": step[1],
            "status": result.get("status"),
            "citation_count": len(citations),
            "warnings": list(result.get("warnings", [])),
        })
        log_event("tool", tool=tool, status=result.get("status"),
                  citations=len(citations),
                  note="; ".join(result.get("warnings", [])) or None)
        if result.get("status") in ("no_registry", "registry_missing", "registry_unreadable", "unavailable",
                                    "no_data", "no_market_data", "no_ticker"):
            document["degraded"] = True
            document["failures"].append({"tool": tool, "status": result.get("status"),
                                         "warnings": list(result.get("warnings", []))})
        claims.extend(_claims_for(tool, result, tool_args))
    # Baseline is planned last by every template, so model evidence exists here.
    baseline_values = outputs.get("baseline_comparison", {}).get("values", {})
    model = baseline_values.get("model", {}) or {}
    conflicts = detect_conflicts(outputs)
    document["conflicts"] = conflicts
    log_event("conflict_detection", status="ok", note=f"{len(conflicts)} conflict(s) detected")
    focus = template_focus(template, outputs)
    document["template_focus"] = focus
    counter = outputs.get("counter_evidence", {})
    document["counter_evidence"] = {
        "items": counter.get("values", {}).get("items", []),
        "status": counter.get("status"),
        "warnings": counter.get("warnings", []),
        "note": ("no alternative explanation could be evidenced at this as-of date"
                 if counter.get("status") == "no_data" else
                 "alternative explanations are listed with their own citations"),
        "citations": counter.get("citations", []),
    }
    hypothesis = _build_hypothesis(template, company, track, document, outputs, model, focus)
    document["hypothesis"] = hypothesis
    log_event("hypothesis", status="ok", citations=len(hypothesis.get("citations", [])),
              note=hypothesis.get("label"))
    validation = _statistical_validation(outputs, model, document["conflicts"])
    document["statistical_validation"] = validation
    log_event("statistical_validation", status=validation.get("calibration_status"),
              citations=len(validation.get("citations", [])))
    uncertainty = _uncertainty_block(outputs, model, document["conflicts"], registry, tkg)
    document["uncertainty"] = uncertainty
    synthesis = _synthesis(document, outputs, hypothesis, validation, uncertainty, model)
    document["synthesis"] = synthesis
    document["citations"] = _dedupe_citations(
        citation for claim in claims for citation in claim["citations"])
    log_event("synthesis", status="ok", citations=len(document["citations"]),
              note=f"{len(synthesis)} cited statements")
    failed = [step for step in document["steps"] if step.get("status") in
              ("no_events", "no_financial_facts", "no_publication_data", "no_registered_forecast",
               "registry_missing", "registry_unreadable", "unavailable", "no_data")]
    document["stop_condition"] = {
        "reached": True,
        "planned_steps": len(plan_spec),
        "completed_steps": len(document["steps"]),
        "failed_steps": [{"tool": step["tool"], "status": step["status"]} for step in failed],
        "reason": ("the deterministic tool plan is exhausted. Remaining uncertainty needs sources that are not "
                   "available in this environment (patents, hiring, canonical registry when absent); the agent "
                   "stops instead of guessing."),
    }
    log_event("stop", status="ok", note=document["stop_condition"]["reason"])
    return document


def _claims_for(tool: str, result: Mapping[str, Any], args: Mapping[str, Any]) -> list[dict[str, Any]]:
    status = result.get("status")
    values = result.get("values", {})
    citations = result.get("citations", [])
    warnings = result.get("warnings", [])
    if tool == "event_history":
        if status == "no_events":
            return [_claim("event_history", tool,
                           f"no material event for {args['company']} / {args['track']} is public at the as-of date.",
                           values={"total": 0, "dormant": True},
                           citations=[], evidence_status="not_available", warnings=warnings)]
        return [_claim("event_history", tool,
                       f"{values['total']} material events for the pair, last on {values['last_event_date']}; "
                       f"{values['recent_12m']} in the trailing 12 months and {values['recent_36m']} in the "
                       f"trailing 36 months.",
                       values=values, citations=citations, evidence_status="observed")]
    if tool == "financial_context":
        if status == "no_financial_facts":
            return [_claim("financial_context", tool,
                           "no consolidated SEC financial facts are available for this company.",
                           values=values, citations=[], evidence_status="not_available", warnings=warnings)]
        return [_claim("financial_context", tool,
                       f"latest annual R&D fact {values.get('rd_fact')} and revenue fact "
                       f"{values.get('revenue_fact')} are public at the as-of date.",
                       values=values, citations=citations, evidence_status="observed")]
    if tool == "market_context":
        if not citations:
            return [_claim("market_context", tool,
                           f"market features are unavailable ({status}).",
                           values=values, citations=[], evidence_status="not_available", warnings=warnings)]
        features = values.get("features", {})
        return [_claim("market_context", tool,
                       f"ticker {values.get('ticker')} last bar {values.get('last_bar_date')}: "
                       f"trailing 12m return {_num(features.get('mkt_ret_12m'))} and excess return versus SPY "
                       f"{_num(features.get('mkt_rel_spy_12m'))}.",
                       values=values, citations=citations,
                       evidence_status="derived" if int(features.get(MARKET_MISSING_KEY) or 0) == 0 else "insufficient",
                       warnings=warnings)]
    if tool == "publication_context":
        if status == "no_publication_data":
            return [_claim("publication_context", tool,
                           "no complete-year publication counts are stored for this company.",
                           values=values, citations=[], evidence_status="not_available", warnings=warnings)]
        features = values.get("features", {})
        return [_claim("publication_context", tool,
                       f"complete-year publication counts {values.get('counts')} with knowledge date "
                       f"{values.get('knowledge_date')}; prior-year growth "
                       f"{_num(features.get('pub_growth_prev_year'))}.",
                       values=values, citations=citations, evidence_status="observed")]
    if tool == "forecast_evidence":
        if status != "ok":
            return [_claim("forecast_evidence", tool,
                           f"no canonical registered forecast is available ({status}: "
                           f"{REGISTRY_STATUS.get(str(status), status)}).",
                           values={"status": status, "matched": 0}, citations=[],
                           evidence_status="not_available", warnings=warnings)]
        visible = [record for record in values.get("forecasts", []) if record.get("visible_at_as_of")]
        record = (visible or values.get("forecasts", []))[-1]
        return [_claim("forecast_evidence", tool,
                       f"the canonical registry holds {values.get('matched')} matching forecast(s) "
                       f"({values.get('visible')} visible at the as-of date); latest p={record['p']} with "
                       f"model_version {record['model_version']}.",
                       values=values, citations=citations, evidence_status="observed")]
    if tool == "graph_context":
        if status == "ok":
            return [_claim("graph_context", tool,
                           f"the temporal knowledge graph contributes {values.get('nodes')} node(s) and "
                           f"{values.get('edges')} edge(s) mentioning the company or track.",
                           values=values, citations=citations, evidence_status="observed", warnings=warnings)]
        return [_claim("graph_context", tool,
                       f"graph context is {status}; the optional sibling TKG helper was not usable.",
                       values=values, citations=[], evidence_status="not_available", warnings=warnings)]
    if tool == "counter_evidence":
        claims = []
        for item in values.get("items", []):
            claims.append(_claim(f"counter_evidence:{item['check']}", tool,
                                 f"{item['check']}: {item['finding']}",
                                 values=item.get("values", {}), citations=item.get("citations", []),
                                 evidence_status=item.get("evidence_status", "not_available")))
        if not claims:
            claims.append(_claim("counter_evidence", tool, "no alternative explanation was found.",
                                 values=values, citations=[], evidence_status="not_available",
                                 warnings=warnings))
        return claims
    if tool == "baseline_comparison":
        model_evidence = values.get("model", {}) or {}
        return [_claim("baseline_comparison", tool,
                       f"purged pair base rate {_num(values.get('pair_base_rate'))} over "
                       f"{values.get('pair_purged_rows')} matured example(s); model probability "
                       f"{_num(values.get('model_p'))} (source: {model_evidence.get('source')}) gives delta "
                       f"{_num(values.get('delta'))}. {values.get('interpretation')}",
                       values=values, citations=citations,
                       evidence_status="derived" if values.get("pair_base_rate") is not None else "insufficient",
                       warnings=warnings)]
    raise AssertionError(f"no claim builder for tool {tool}")  # pragma: no cover


def _citations_for_claims(claim_ids: Iterable[str], claims: Iterable[Mapping[str, Any]]
                  ) -> tuple[list[dict[str, str]], list[str]]:
    index = {claim["claim_id"]: claim for claim in claims}
    citations: list[dict[str, Any]] = []
    missing: list[str] = []
    for claim_id in claim_ids:
        claim = index.get(claim_id)
        if claim is None:
            missing.append(claim_id)
            continue
        citations.extend(claim.get("citations", []))
    return _dedupe_citations(citations), missing


def _build_hypothesis(template: str, company: str, track: str, document: Mapping[str, Any],
                      outputs: Mapping[str, Mapping[str, Any]], model: Mapping[str, Any],
                      focus: Mapping[str, Any]) -> dict[str, Any]:
    events = outputs.get("event_history", {}).get("values", {})
    baseline = outputs.get("baseline_comparison", {}).get("values", {})
    pair_rate = baseline.get("pair_base_rate")
    model_p = model.get("p")
    if template == "entry_forecast":
        statement = (f"Hypothesis (not a causal finding): {company} will register a first material public event "
                     f"in {track} within 12 months of the as-of date. Supporting facts: the pair is dormant "
                     f"(last event {events.get('last_event_date')}, "
                     f"{_num(events.get('months_since_last_event'), 1)} months before the as-of date) and the "
                     f"pair's purged entry base rate is {_num(pair_rate)}.")
        claim_ids = ["event_history", "baseline_comparison", "counter_evidence:track_activity_by_other_companies"]
    elif template == "market_leading_indicator":
        statement = (f"Hypothesis (not a causal finding): point-in-time market evidence for {company} carries "
                     f"information about future {track} activity beyond the R&D history. The agent reports the "
                     f"market values, the observed R&D activity and the base rate; it does not test incremental "
                     f"predictive value, so this remains untested.")
        claim_ids = ["market_context", "event_history", "baseline_comparison"]
    elif template == "early_signal":
        statement = (f"Hypothesis (not a causal finding): multi-source evidence indicates that {track} is "
                     f"becoming more active around the as-of date. The evidence table records the current "
                     f"record; early signal is not yet a validated forecast.")
        claim_ids = ["event_history", "publication_context", "market_context"]
    elif template == "strategic_shift":
        statement = (f"Hypothesis (not a causal finding): {company} is shifting observed public activity toward "
                     f"{track}. The claim rests on the event-count mix and, if available, financial and market "
                     f"context; absence of events is not evidence of stopped internal research.")
        claim_ids = ["event_history", "financial_context", "market_context"]
    else:
        statement = (f"Hypothesis (not a causal finding): the independent sources for {company} / {track} are "
                     f"consistent at the as-of date. Conflicts are listed explicitly rather than resolved by the "
                     f"agent, and consistency is not scored as a probability.")
        claim_ids = ["event_history", "financial_context", "market_context", "publication_context"]
    citations, missing = _citations_for_claims(claim_ids, document["evidence"])
    probability_source = None
    if model_p is not None:
        probability_source = {"p": model_p, "source": model.get("source"),
                              "citation": model.get("citation")}
    return {
        "label": "hypothesis, not a causal finding",
        "statement": statement,
        "template": template,
        "supported_by_claims": claim_ids,
        "missing_claims": missing,
        "model_probability": model_p,
        "probability_source": probability_source,
        "citations": citations,
        "falsification_condition": (
            "the hypothesis is falsified if the pair's first material event occurs after the 12-month window, "
            "if the cited evidence cannot be reproduced from the named rows, or if a later conflict invalidates "
            "the cited evidence."
            if template == "entry_forecast" else
            "the hypothesis is falsified if the cited evidence cannot be reproduced from the named rows or if "
            "a controlled prospective test shows no incremental information."),
        "template_focus": dict(focus),
    }


def _statistical_validation(outputs: Mapping[str, Mapping[str, Any]], model: Mapping[str, Any],
                            conflicts: list[Mapping[str, Any]]) -> dict[str, Any]:
    baseline = outputs.get("baseline_comparison", {}).get("values", {})
    registry = outputs.get("forecast_evidence", {}).get("values", {})
    calibration = registry.get("calibration", {"status": "insufficient_verified_forecasts", "n": 0})
    pair_rate = baseline.get("pair_base_rate")
    model_p = model.get("p")
    delta = (model_p - pair_rate) if (model_p is not None and pair_rate is not None) else None
    if delta is None:
        interpretation = ("no model-versus-baseline comparison is possible at this as-of date: "
                          f"pair base rate={pair_rate}, model probability={model_p}.")
    else:
        interpretation = (f"delta = model probability - pair base rate = {delta:.6f}. This is a descriptive "
                          "comparison on one pair; it is not a significance test and no predictive-skill claim "
                          "is made.")
    citations = list(baseline.get("citations", []))
    return {
        "pair_base_rate": pair_rate,
        "pair_purged_rows": baseline.get("pair_purged_rows"),
        "global_base_rate": baseline.get("global_base_rate"),
        "latest_mature_cutoff": baseline.get("latest_mature_cutoff"),
        "model_probability": model_p,
        "model_source": model.get("source"),
        "delta": delta,
        "interpretation": interpretation,
        "calibration_status": calibration.get("status", "insufficient_verified_forecasts"),
        "calibration": calibration,
        "conflict_count": len(conflicts),
        "citations": _dedupe_citations(citations),
    }


def _uncertainty_block(outputs: Mapping[str, Mapping[str, Any]], model: Mapping[str, Any],
                       conflicts: list[Mapping[str, Any]], registry: str | Path | None,
                       tkg: str | Path | None) -> dict[str, Any]:
    model_uncertainty = model.get("uncertainty")
    if model_uncertainty is None:
        model_uncertainty = {
            "status": "not_available",
            "note": "no calibrated uncertainty payload is available for the visible probability",
        }
    flags: list[str] = []
    events = outputs.get("event_history", {}).get("values", {})
    if events.get("timestamp_quality"):
        flags.append("event availability is decision_date + 14 days (estimated) for all stored rows")
    financial = outputs.get("financial_context", {}).get("values", {})
    if financial.get("data_quality"):
        flags.append(f"financial facts are {', '.join(financial['data_quality'])} "
                     "(consolidated company revenue, not product/segment sales)")
    market = outputs.get("market_context", {}).get("values", {})
    if market.get("ticker"):
        flags.append("market bars are known by trading date only; the vendor publication time is unknown")
    publications = outputs.get("publication_context", {}).get("values", {})
    if publications.get("knowledge_date"):
        flags.append(f"publication counts are complete-year data with a conservative knowledge date "
                     f"({publications['knowledge_date']})")
    missing = list(MISSING_SOURCES)
    if registry is None or not Path(registry).exists():
        missing.append("canonical forecast registry: absent; registry-backed claims are unavailable")
    if tkg is None:
        missing.append("temporal knowledge graph: not requested; graph context skipped")
    elif not Path(tkg).exists():
        missing.append("temporal knowledge graph: the supplied path does not exist")
    return {
        "model_uncertainty": model_uncertainty,
        "model_uncertainty_source": model.get("citation"),
        "data_quality_flags": flags,
        "missing_sources": missing,
        "conflict_count": len(conflicts),
        "conflicts": [conflict["rule"] for conflict in conflicts],
        "notes": [
            "uncertainty is described from stored evidence; no interval is fabricated",
            "the model's temporal-ensemble spread is not a causal confidence interval",
        ],
    }


def _synthesis(document: Mapping[str, Any], outputs: Mapping[str, Mapping[str, Any]],
               hypothesis: Mapping[str, Any], validation: Mapping[str, Any],
               uncertainty: Mapping[str, Any], model: Mapping[str, Any]) -> list[dict[str, Any]]:
    claims = {claim["claim_id"]: claim for claim in document["evidence"]}
    statements: list[dict[str, Any]] = []

    def add(statement: str, claim_ids: Iterable[str], *, evidence_status: str | None = None) -> None:
        chosen = [claim_id for claim_id in claim_ids if claim_id in claims]
        citations, missing = _citations_for_claims(chosen, claims.values())
        status = evidence_status or (
            "derived" if chosen and all(claims[claim_id]["evidence_status"] in ("observed", "derived")
                                        for claim_id in chosen) else "not_available")
        statements.append({
            "statement": statement,
            "claim_ids": chosen,
            "missing_claims": missing,
            "citations": citations,
            "evidence_status": status,
        })

    events = outputs.get("event_history", {}).get("values", {})
    if events.get("total"):
        add(f"The pair has {events['total']} material public events; the last is {events['last_event_date']} and "
            f"{events['recent_12m']} occurred in the trailing 12 months.", ["event_history"])
    else:
        add("No material public event for the pair is public at the as-of date.", ["event_history"],
            evidence_status="not_available")
    financial_claim = claims.get("financial_context")
    if financial_claim and financial_claim["evidence_status"] == "observed":
        add("Consolidated financial evidence is available with the fact ids and filed dates in the evidence "
            "table.", ["financial_context"])
    else:
        add("Consolidated financial evidence is unavailable for this company at this date.",
            ["financial_context"], evidence_status="not_available")
    market_claim = claims.get("market_context")
    if market_claim and market_claim["citations"]:
        add("Point-in-time market evidence with bar citations is available; it is a market signal, not a measure "
            "of technological capability.", ["market_context"], evidence_status=market_claim["evidence_status"])
    else:
        add("Point-in-time market evidence is unavailable at this date.", ["market_context"],
            evidence_status="not_available")
    if claims.get("publication_context"):
        add("Complete-year publication counts and their knowledge date are recorded as evidence.",
            ["publication_context"], evidence_status=claims["publication_context"]["evidence_status"])
    add(f"Purged pair base rate: {_num(validation.get('pair_base_rate'))} over "
        f"{validation.get('pair_purged_rows')} matured examples; model probability "
        f"{_num(validation.get('model_probability'))} (source {validation.get('model_source')}); delta "
        f"{_num(validation.get('delta'))}.", ["baseline_comparison"],
        evidence_status="derived" if validation.get("pair_base_rate") is not None else "insufficient")
    if model.get("p") is not None:
        add(f"A probability of {_num(model['p'])} is taken from {model.get('source')} with citation "
            f"{model.get('citation')}; the agent did not generate it.", ["forecast_evidence", "baseline_comparison"],
            evidence_status="observed")
    else:
        add("No model or registered probability is available at the as-of date; none is invented.",
            ["forecast_evidence", "baseline_comparison"], evidence_status="not_available")
    conflict_rules = ", ".join(conflict["rule"] for conflict in document["conflicts"]) or "none"
    add(f"{len(document['conflicts'])} cross-source conflict(s) detected: {conflict_rules}. Conflicts are "
        "reported, not resolved.", ["baseline_comparison"], evidence_status="derived")
    counter = document["counter_evidence"]
    counter_claim_ids = [claim_id for claim_id in claims if claim_id.startswith("counter_evidence")]
    add(f"Counter-evidence: {len(counter['items'])} alternative-explanation checks were run "
        f"({counter['status']}).", counter_claim_ids, evidence_status="derived")
    add(hypothesis["statement"], hypothesis["supported_by_claims"],
        evidence_status="derived" if hypothesis.get("citations") else "not_available")
    add("Uncertainty and data-quality gaps: " + "; ".join(uncertainty["data_quality_flags"][:2] +
                                                         uncertainty["missing_sources"][:2]),
        ["event_history", "financial_context"], evidence_status="derived")
    return statements


# ------------------------------------------------------------------- rendering
def render_markdown(document: Mapping[str, Any]) -> str:
    """Render a research-agent document as Markdown (citations preserved)."""
    lines: list[str] = []
    lines.append(f"# Research agent — {document['question']['text']}")
    lines.append("")
    lines.append(f"- template: `{document['template']}`")
    lines.append(f"- as-of: `{document['as_of']}`")
    lines.append(f"- company / track: `{document['company']}` / `{document['track']}`")
    lines.append(f"- agent version: `{document['agent_version']}`"
                 + (" — **degraded** (missing evidence sources)" if document.get("degraded") else ""))
    lines.append("")
    lines.append("## Hypothesis (not a causal finding)")
    lines.append("")
    lines.append(document["hypothesis"].get("statement", "n/a"))
    lines.append("")
    lines.append("## Evidence table")
    lines.append("")
    lines.append("| claim | status | statement | citations |")
    lines.append("|---|---|---|---|")
    for claim in document["evidence"]:
        citations = ", ".join(f"{c['kind']}:{c['locator']}" for c in claim["citations"][:3])
        lines.append(f"| `{claim['claim_id']}` | {claim['evidence_status']} | "
                     f"{claim['statement'].replace('|', '/')} | {citations or '—'} |")
    lines.append("")
    lines.append("## Conflicts")
    lines.append("")
    if document["conflicts"]:
        for conflict in document["conflicts"]:
            lines.append(f"- **{conflict['rule']}** ({conflict['conflict_id']}): {conflict['description']}")
    else:
        lines.append("- none detected")
    lines.append("")
    lines.append("## Counter-evidence")
    lines.append("")
    for item in document["counter_evidence"]["items"]:
        lines.append(f"- *{item['check']}* ({item['evidence_status']}): {item['finding']}")
    lines.append("")
    lines.append("## Statistical validation")
    lines.append("")
    validation = document["statistical_validation"]
    lines.append(f"- pair base rate: {validation.get('pair_base_rate')} over "
                 f"{validation.get('pair_purged_rows')} matured examples")
    lines.append(f"- model probability: {validation.get('model_probability')} "
                 f"(source: {validation.get('model_source')})")
    lines.append(f"- delta: {validation.get('delta')}")
    lines.append(f"- calibration: {validation.get('calibration_status')}")
    lines.append("")
    lines.append("## Synthesis")
    lines.append("")
    for statement in document["synthesis"]:
        lines.append(f"- {statement['statement']}")
        if statement["citations"]:
            lines.append("  - citations: " + ", ".join(
                f"{c['kind']}:{c['locator']}" for c in statement["citations"][:5]))
    lines.append("")
    lines.append("## Uncertainty")
    lines.append("")
    lines.append(f"- model uncertainty: {document['uncertainty']['model_uncertainty']}")
    for flag in document["uncertainty"]["data_quality_flags"]:
        lines.append(f"- data quality: {flag}")
    for missing in document["uncertainty"]["missing_sources"]:
        lines.append(f"- missing source: {missing}")
    lines.append("")
    lines.append("## Research log")
    lines.append("")
    for entry in document["log"]:
        lines.append(f"1. `{entry['phase']}`"
                     + (f" `{entry['tool']}`" if entry.get("tool") else "")
                     + f" — status={entry.get('status')} citations={entry.get('citations')}")
    lines.append("")
    lines.append("## Stop condition")
    lines.append("")
    lines.append(document["stop_condition"]["reason"])
    lines.append("")
    lines.append("## Limitations")
    lines.append("")
    for limitation in document["limitations"]:
        lines.append(f"- {limitation}")
    return "\n".join(lines)


# ------------------------------------------------------------------------- CLI
def latest_example_as_of(db: str | Path) -> str | None:
    """Latest stored example cutoff (a deterministic CLI default for ``--as-of``)."""
    conn = _connect_ro(db)
    try:
        if not _table_exists(conn, "forecast_examples"):
            return None
        row = conn.execute("SELECT MAX(cutoff) FROM forecast_examples").fetchone()
        return iso(row[0]) if row and row[0] else None
    finally:
        conn.close()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Deterministic evidence-grounded research agent (no LLM, no network).")
    parser.add_argument("--list-templates", action="store_true",
                        help="print the supported templates (JSON) and exit")
    sub = parser.add_subparsers(dest="command")
    ask = sub.add_parser("ask", help="run one research question")
    ask.add_argument("--company", required=True)
    ask.add_argument("--track", required=True)
    ask.add_argument("--template", default="entry_forecast", choices=sorted(TEMPLATES))
    ask.add_argument("--as-of", default=None,
                     help="point-in-time cutoff (date or ISO datetime); default: latest stored example cutoff")
    ask.add_argument("--db", default=None, help="research database (default: data/research.sqlite)")
    ask.add_argument("--registry", default=None,
                     help="canonical forecast registry (default: data/registry.sqlite when present)")
    ask.add_argument("--tkg", default=None, help="optional temporal knowledge graph file")
    ask.add_argument("--format", default="json", choices=("json", "markdown"))
    ask.add_argument("--out", default=None, help="write the document to this path")
    return parser


def _default_db() -> Path:
    root = Path(__file__).resolve().parents[1]
    research = root / "data" / "research.sqlite"
    if research.exists():
        return research
    return root / "data" / "medradar.sqlite"


def _default_registry() -> Path | None:
    candidate = Path(__file__).resolve().parents[1] / "data" / "registry.sqlite"
    return candidate if candidate.exists() else None


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.list_templates:
        print(json.dumps([{"name": name, **description} for name, description in sorted(TEMPLATES.items())],
                         ensure_ascii=False, indent=2))
        return 0
    if args.command != "ask":
        parser.print_help()
        return 2
    db = args.db or str(_default_db())
    registry = args.registry if args.registry is not None else _default_registry()
    as_of = args.as_of
    if as_of is None:
        as_of = latest_example_as_of(db)
        if as_of is None:
            print(json.dumps({"error": "no --as-of supplied and the database has no stored examples"}))
            return 2
    document = run_agent(args.company, args.track, template=args.template, as_of=as_of,
                         db=db, registry=registry, tkg=args.tkg)
    if args.out:
        target = Path(args.out)
        target.parent.mkdir(parents=True, exist_ok=True)
        if args.format == "markdown":
            target.write_text(render_markdown(document), encoding="utf-8")
        else:
            target.write_text(json.dumps(document, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    if args.format == "markdown":
        print(render_markdown(document))
    else:
        print(json.dumps(document, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
