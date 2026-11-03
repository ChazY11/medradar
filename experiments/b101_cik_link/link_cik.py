#!/usr/bin/env python3
"""B-029 / b101 - CIK-based deterministic linking for the SEC 8-K lane.

The 8-K corpus in ``data/medradar.sqlite`` carries a CIK in every payload but
most events have ``company_key IS NULL``.  This script tries to close that gap
with one rule and no others:

    an event links iff its payload CIK, normalised to integer form, exactly
    equals the CIK of exactly one curated company.

There is no name matching, no alias lookup, no token overlap and no similarity
threshold.  Applicant/name token overlap is computed *after* the decision and
reported as descriptive evidence only.

The curated CIK->company map is the committed registry in this directory
(``cik_registry.json``); ``--rebuild-registry`` regenerates it from the local
research store and the local EDGAR candidate dump.  The run itself reads the
store read-only and writes only ``link_report.json`` and ``events_linked.jsonl``.

Exit codes: 0 ok, 2 a required input is missing or malformed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import random
import re
import sqlite3
import sys
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parents[1]

DEFAULT_STORE = ROOT / "data" / "medradar.sqlite"
DEFAULT_RESEARCH = ROOT / "data" / "research.sqlite"
DEFAULT_REGISTRY = SCRIPT_DIR / "cik_registry.json"
DEFAULT_REPORT = SCRIPT_DIR / "link_report.json"
DEFAULT_LINKS = SCRIPT_DIR / "events_linked.jsonl"
DEFAULT_CONFIGS = (
    ROOT / "config" / "companies_device.json",
    ROOT / "config" / "companies_drug.json",
)

#: ``data/`` is gitignored, so the candidate dumps used to build the registry
#: are not portable.  The registry they produce *is* committed, which is what
#: the deterministic run consumes; these paths are only needed to rebuild it on
#: the machine that holds the local corpus.
DEFAULT_CANDIDATES = (
    Path("D:/DEPPSKK/medradar/data/edgar_corpus/candidates.jsonl"),
    Path("D:/DEPPSKK/medradar/data/edgar_corpus/candidates_v2.jsonl"),
)

SOURCE = "sec_edgar_corpus"
CONFIDENCE = 1.0
DEFAULT_SEED = 20261103
DEFAULT_SAMPLE_SIZE = 60
REGISTRY_SCHEMA = "b101.cik_registry.v1"

_CIK_RE = re.compile(r"^\d{1,12}$")
_TOKEN_RE = re.compile(r"[A-Za-z0-9]+")


class InputError(RuntimeError):
    """A required input file/table is missing or unusable."""


# --------------------------------------------------------------------------- CIK
def normalise_cik(value: Any) -> int | None:
    """Return the canonical integer CIK, or ``None`` when *value* is not one.

    Accepts integers, integral floats, and strings that are all digits after
    stripping (so the ten-digit zero-padded form ``"0001613103"`` and
    ``"1613103"`` both yield ``1613103``).  Leading/trailing whitespace is
    ignored; anything else (blank, negative, non-digit, zero) is rejected.
    """
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if value > 0 else None
    if isinstance(value, float):
        if value.is_integer() and value > 0:
            return int(value)
        return None
    if isinstance(value, str):
        text = value.strip()
        if not _CIK_RE.match(text):
            return None
        number = int(text)
        return number if number > 0 else None
    return None


def cik10(cik: int) -> str:
    """The ten-digit EDGAR display form of a CIK."""
    return f"{cik:010d}"


# ------------------------------------------------------------------- read-only DB
def open_readonly(path: str | Path) -> sqlite3.Connection:
    """Open a SQLite store read-only (the canonical store must never be written)."""
    resolved = Path(path)
    if not resolved.exists():
        raise InputError(f"store not found: {resolved}")
    connection = sqlite3.connect(f"file:{resolved.as_posix()}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    return connection


# ---------------------------------------------------------------- payload parsing
def parse_payload(raw: Any) -> dict[str, Any] | None:
    if isinstance(raw, Mapping):
        return dict(raw)
    if raw in (None, ""):
        return None
    try:
        parsed = json.loads(raw)
    except (TypeError, ValueError):
        return None
    return parsed if isinstance(parsed, dict) else None


def load_events(store_path: str | Path) -> list[dict[str, Any]]:
    """Every ``sec_edgar_corpus`` event, with a normalised payload CIK attached."""
    connection = open_readonly(store_path)
    try:
        rows = connection.execute(
            "SELECT event_id, company_key, applicant_raw, title, payload "
            "FROM events WHERE source = ?",
            (SOURCE,),
        ).fetchall()
    finally:
        connection.close()
    events: list[dict[str, Any]] = []
    for row in rows:
        payload = parse_payload(row["payload"])
        events.append(
            {
                "event_id": str(row["event_id"]),
                "company_key": (row["company_key"] or ""),
                "applicant_raw": (row["applicant_raw"] or ""),
                "title": (row["title"] or ""),
                "payload": payload,
                "payload_ok": payload is not None,
                "cik": normalise_cik((payload or {}).get("cik")),
                "accession": str((payload or {}).get("accession") or ""),
            }
        )
    events.sort(key=lambda event: event["event_id"])
    return events


# -------------------------------------------------------------------- identifiers
def load_identifier_rows(research_path: str | Path) -> list[tuple[str, str, str]]:
    """Curated CIK rows from ``research.sqlite.company_identifiers``.

    The table stores scheme ``SEC_CIK`` (not ``CIK``); both spellings are read so
    a future rename cannot silently drop the evidence.  Returns
    ``(company_key, identifier, source)`` triples.
    """
    connection = open_readonly(research_path)
    try:
        exists = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'company_identifiers'"
        ).fetchone()
        if not exists:
            raise InputError("research store has no company_identifiers table")
        rows = connection.execute(
            "SELECT company_key, identifier, source, scheme FROM company_identifiers"
        ).fetchall()
        identifiers_table = connection.execute(
            "SELECT sql FROM sqlite_master WHERE name = 'company_identifiers'"
        ).fetchone()[0]
        research_companies = connection.execute(
            "SELECT key, cik FROM companies"
        ).fetchall()
    finally:
        connection.close()
    selected = [
        (str(row["company_key"]), str(row["identifier"]), str(row["source"] or ""))
        for row in rows
        if str(row["scheme"] or "").strip().upper() in {"CIK", "SEC_CIK"}
    ]
    del identifiers_table
    del research_companies
    return selected


def load_company_tickers(config_paths: Sequence[str | Path]) -> dict[str, set[str]]:
    """Curated roster tickers -> company keys (exact ticker equality only)."""
    tickers: dict[str, set[str]] = {}
    for path in config_paths:
        resolved = Path(path)
        if not resolved.exists():
            raise InputError(f"curated company config not found: {resolved}")
        payload = json.loads(resolved.read_text(encoding="utf-8"))
        for company in payload.get("companies", []):
            key = str(company.get("key") or "").strip()
            ticker = str(company.get("ticker") or "").strip().upper()
            if key and ticker:
                tickers.setdefault(ticker, set()).add(key)
    return tickers


def iter_candidate_rows(paths: Sequence[str | Path]) -> Iterable[dict[str, Any]]:
    for path in paths:
        resolved = Path(path)
        if not resolved.exists():
            continue
        with resolved.open(encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                yield json.loads(line)


# ---------------------------------------------------------------------- registry
def build_curated_registry(
    identifier_rows: Iterable[tuple[str, str, str]],
    candidate_rows: Iterable[Mapping[str, Any]],
    company_tickers: Mapping[str, set[str]],
) -> dict[str, Any]:
    """Build the curated CIK -> company registry.

    Evidence per CIK is the set of company keys it can denote: identifier rows
    from the research store, plus SEC-reported tickers on EDGAR candidate rows
    whose ticker exactly equals a curated roster ticker.  A CIK is usable only
    when that set has exactly one member; otherwise it is written to
    ``ambiguous`` and never links anything.
    """
    evidence: dict[int, dict[str, set[str]]] = {}

    def add(cik: int, company_key: str, label: str) -> None:
        evidence.setdefault(cik, {}).setdefault(company_key, set()).add(label)

    for company_key, identifier, source in identifier_rows:
        cik = normalise_cik(identifier)
        if cik is None:
            continue
        add(cik, company_key, f"company_identifiers:{source or 'unknown'}")

    for row in candidate_rows:
        cik = normalise_cik(row.get("cik"))
        ticker = str(row.get("ticker") or "").strip().upper()
        if cik is None or not ticker:
            continue
        for company_key in sorted(company_tickers.get(ticker, ())):
            add(cik, company_key, f"sec_ticker:{ticker}")

    companies: dict[str, Any] = {}
    ambiguous: dict[str, Any] = {}
    for cik in sorted(evidence):
        claims = evidence[cik]
        if len(claims) == 1:
            company_key = next(iter(claims))
            labels = sorted(labels for labels in claims[company_key])
            tickers = sorted({label.split(":", 1)[1] for label in labels if label.startswith("sec_ticker:")})
            companies[cik10(cik)] = {
                "cik_int": cik,
                "company_key": company_key,
                "ticker": tickers[0] if len(tickers) == 1 else "",
                "evidence": labels,
            }
        else:
            ambiguous[cik10(cik)] = {
                "cik_int": cik,
                "companies": sorted(claims),
                "evidence": {company: sorted(labels) for company, labels in sorted(claims.items())},
            }
    return {"companies": companies, "ambiguous": ambiguous}


def registry_document(registry: Mapping[str, Any], provenance: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "schema": REGISTRY_SCHEMA,
        "built_by": "experiments/b101_cik_link/link_cik.py --rebuild-registry",
        "rule": (
            "payload.cik normalised to int must exactly equal a curated company CIK that maps to "
            "exactly one curated company_key; identifier evidence from research.sqlite."
            "company_identifiers plus SEC-reported tickers on EDGAR candidates whose ticker exactly "
            "equals exactly one curated roster ticker. No names, aliases or similarity are used."
        ),
        "provenance": dict(provenance),
        "companies": registry["companies"],
        "ambiguous": registry["ambiguous"],
    }


def load_registry(path: str | Path) -> dict[str, Any]:
    """Load the committed registry and validate its internal invariants."""
    resolved = Path(path)
    if not resolved.exists():
        raise InputError(f"CIK registry not found: {resolved} (run --rebuild-registry)")
    document = json.loads(resolved.read_text(encoding="utf-8"))
    if document.get("schema") != REGISTRY_SCHEMA:
        raise InputError(f"unexpected registry schema: {document.get('schema')!r}")
    curated: dict[int, dict[str, Any]] = {}
    for key, entry in document.get("companies", {}).items():
        cik = normalise_cik(entry.get("cik_int", key))
        if cik is None or cik10(cik) != str(key):
            raise InputError(f"registry CIK {key!r} is not canonical")
        if cik in curated:
            raise InputError(f"duplicate registry CIK {key!r}")
        curated[cik] = {
            "company_key": str(entry["company_key"]),
            "cik": cik,
            "ticker": str(entry.get("ticker") or ""),
            "evidence": [str(label) for label in entry.get("evidence", [])],
        }
    ambiguous: dict[int, dict[str, Any]] = {}
    for key, entry in document.get("ambiguous", {}).items():
        cik = normalise_cik(entry.get("cik_int", key))
        if cik is None:
            raise InputError(f"ambiguous CIK {key!r} is not canonical")
        if cik in curated:
            raise InputError(f"CIK {key!r} is both curated and ambiguous")
        ambiguous[cik] = {
            "cik": cik,
            "companies": sorted(str(company) for company in entry.get("companies", [])),
        }
    return {"curated": curated, "ambiguous": ambiguous, "document": document}


def independent_identifier_index(research_path: str | Path) -> dict[int, set[str]]:
    """CIK -> company keys from the raw identifier table (precision cross-check)."""
    index: dict[int, set[str]] = {}
    if not Path(research_path).exists():
        return index
    connection = open_readonly(research_path)
    try:
        rows = connection.execute(
            "SELECT company_key, identifier FROM company_identifiers"
        ).fetchall()
    except sqlite3.DatabaseError:
        return index
    finally:
        connection.close()
    for row in rows:
        cik = normalise_cik(row["identifier"])
        if cik is not None:
            index.setdefault(cik, set()).add(str(row["company_key"]))
    return index


# ------------------------------------------------------------------------ funnel
def resolve_events(
    events: Sequence[Mapping[str, Any]],
    curated: Mapping[int, Mapping[str, Any]],
    ambiguous: Mapping[int, Mapping[str, Any]],
) -> dict[str, Any]:
    """Apply the exact-CIK rule to every event and return the full funnel."""
    total = len(events)
    with_cik = 0
    distinct_ciks: set[int] = set()
    unlinked = 0
    already_linked = 0
    payload_errors = 0
    new_links: list[dict[str, Any]] = []
    corroborated: list[dict[str, Any]] = []
    mismatches: list[dict[str, Any]] = []
    linked_ambiguous = 0
    linked_unverifiable = 0
    unlinked_reasons = {"payload_unparseable": 0, "no_cik": 0, "cik_ambiguous": 0, "cik_not_in_curated_registry": 0}
    unlinked_distinct_not_curated: set[int] = set()
    unlinked_applicants: set[str] = set()
    unresolved_registrants: dict[int, dict[str, Any]] = {}
    per_company_new: dict[str, int] = {}
    per_company_corroborated: dict[str, int] = {}

    for event in events:
        # ``load_events`` already normalises; re-normalise so injected rows
        # (tests, alternate loaders) cannot smuggle a non-integer CIK through.
        event_cik = normalise_cik(event.get("cik"))
        payload_ok = bool(event.get("payload_ok", True))
        if event_cik is not None:
            with_cik += 1
            distinct_ciks.add(event_cik)
        if not payload_ok:
            payload_errors += 1
        company_key = str(event.get("company_key") or "")
        if company_key:
            already_linked += 1
            if event_cik is not None and event_cik in curated:
                expected = curated[event_cik]["company_key"]
                if expected == company_key:
                    corroborated.append(_link_record(event, expected, curated[event_cik], "existing_corroborated"))
                    per_company_corroborated[expected] = per_company_corroborated.get(expected, 0) + 1
                else:
                    mismatches.append(
                        {
                            "event_id": event["event_id"],
                            "company_key": company_key,
                            "cik": event_cik,
                            "registry_company_key": expected,
                        }
                    )
            elif event_cik is not None and event_cik in ambiguous:
                linked_ambiguous += 1
            else:
                linked_unverifiable += 1
            continue

        unlinked += 1
        if not payload_ok:
            unlinked_reasons["payload_unparseable"] += 1
            continue
        if event_cik is None:
            unlinked_reasons["no_cik"] += 1
            continue
        if event_cik in curated:
            entry = curated[event_cik]
            record = _link_record(event, entry["company_key"], entry, "new")
            new_links.append(record)
            per_company_new[entry["company_key"]] = per_company_new.get(entry["company_key"], 0) + 1
        elif event_cik in ambiguous:
            unlinked_reasons["cik_ambiguous"] += 1
        else:
            unlinked_reasons["cik_not_in_curated_registry"] += 1
            unlinked_distinct_not_curated.add(event_cik)
            unlinked_applicants.add(str(event.get("applicant_raw") or ""))
            bucket = unresolved_registrants.setdefault(
                event_cik,
                {"cik": event_cik, "cik_10": cik10(event_cik), "events": 0, "applicants": {}},
            )
            bucket["events"] += 1
            bucket["applicants"][str(event.get("applicant_raw") or "")] = (
                bucket["applicants"].get(str(event.get("applicant_raw") or ""), 0) + 1
            )

    top_unresolved = []
    for bucket in sorted(unresolved_registrants.values(), key=lambda item: (-item["events"], item["cik"]))[:10]:
        applicants = sorted(bucket["applicants"].items(), key=lambda pair: (-pair[1], pair[0]))
        top_unresolved.append(
            {
                "cik": bucket["cik"],
                "cik_10": bucket["cik_10"],
                "events": bucket["events"],
                "applicant_raw": applicants[0][0] if applicants else "",
            }
        )

    new_links.sort(key=lambda record: record["event_id"])
    corroborated.sort(key=lambda record: record["event_id"])
    funnel = {
        "sec_8k_events": total,
        "events_with_payload_cik": with_cik,
        "distinct_payload_ciks": len(distinct_ciks),
        "events_cik_equals_exactly_one_curated_cik": len(corroborated) + len(new_links),
        "events_cik_ambiguous": linked_ambiguous + unlinked_reasons["cik_ambiguous"],
        "events_cik_not_in_curated_registry": total
        - (len(corroborated) + len(new_links))
        - (linked_ambiguous + unlinked_reasons["cik_ambiguous"]),
        "already_linked_events": already_linked,
        "unlinked_events": unlinked,
        "unlinked_with_payload_cik": unlinked - unlinked_reasons["payload_unparseable"] - unlinked_reasons["no_cik"],
        "linked_now": len(new_links),
    }
    return {
        "funnel": funnel,
        "new_links": new_links,
        "corroborated": corroborated,
        "mismatches": mismatches,
        "unresolved_reasons": unlinked_reasons,
        "unlinked_distinct_uncurated_ciks": len(unlinked_distinct_not_curated),
        "unlinked_distinct_applicants": len(unlinked_applicants),
        "top_unlinked_registrants": top_unresolved,
        "per_company_new_links": dict(sorted(per_company_new.items())),
        "per_company_corroborated": dict(sorted(per_company_corroborated.items())),
        "payload_parse_errors": payload_errors,
        "events": total,
    }


def _link_record(
    event: Mapping[str, Any],
    company_key: str,
    entry: Mapping[str, Any],
    status: str,
) -> dict[str, Any]:
    cik = int(entry["cik"])
    evidence_fields = ",".join(entry.get("evidence", [])) or "curated_registry"
    return {
        "event_id": str(event["event_id"]),
        "company_key": company_key,
        "cik": cik,
        "cik_10": cik10(cik),
        "accession": str(event.get("accession") or ""),
        "source_field": "payload.cik",
        "evidence": (
            f"exact CIK match: payload.cik={cik10(cik)} equals curated CIK of company_key={company_key} "
            f"(evidence: {evidence_fields}); confidence 1.0; no name/similarity evidence used"
        ),
        "confidence": CONFIDENCE,
        "link_status": status,
    }


# ----------------------------------------------------------------- precision check
def _name_token_overlap(applicant: str, company_key: str) -> bool:
    """Descriptive only - never consulted when deciding a link."""
    applicant_tokens = {token.upper() for token in _TOKEN_RE.findall(applicant or "")}
    company_tokens = {token.upper() for token in _TOKEN_RE.findall(company_key.replace("_", " ") or "")}
    return bool(applicant_tokens & company_tokens)


def precision_check(
    records: Sequence[Mapping[str, Any]],
    curated: Mapping[int, Mapping[str, Any]],
    ambiguous: Mapping[int, Mapping[str, Any]],
    *,
    seed: int = DEFAULT_SEED,
    sample_size: int = DEFAULT_SAMPLE_SIZE,
    independent: Mapping[int, set[str]] | None = None,
    applicant_by_event: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Spot-check a deterministic sample of linked events.

    Every sampled record must have a CIK that is in the curated registry, maps
    to exactly one curated company, is not ambiguous, and matches the company
    key written by the linker.  Where an independent identifier table is
    supplied, the registry entry is also cross-checked against it.
    """
    pool = sorted(records, key=lambda record: record["event_id"])
    rng = random.Random(seed)
    sample = rng.sample(pool, min(sample_size, len(pool))) if pool else []
    checks = {
        "sampled": len(sample),
        "cik_in_curated_registry": 0,
        "cik_maps_to_exactly_one_company": 0,
        "cik_not_ambiguous": 0,
        "company_key_matches_registry": 0,
        "independent_identifier_checked": 0,
        "independent_identifier_agrees": 0,
        "name_token_overlap_descriptive": 0,
    }
    failures: list[dict[str, Any]] = []
    independent = independent or {}
    applicant_by_event = applicant_by_event or {}
    for record in sample:
        cik = record.get("cik")
        normalised = normalise_cik(cik)
        if normalised is None or normalised not in curated:
            failures.append({"event_id": record["event_id"], "reason": "cik_not_in_curated_registry"})
            continue
        checks["cik_in_curated_registry"] += 1
        entry = curated[normalised]
        if entry["company_key"] == record["company_key"]:
            checks["company_key_matches_registry"] += 1
        else:
            failures.append(
                {
                    "event_id": record["event_id"],
                    "reason": "company_key_mismatch",
                    "expected": entry["company_key"],
                    "written": record["company_key"],
                }
            )
        if normalised not in ambiguous:
            checks["cik_not_ambiguous"] += 1
        else:
            failures.append({"event_id": record["event_id"], "reason": "cik_ambiguous"})
        claims = {entry["company_key"]}
        if len(claims) == 1:
            checks["cik_maps_to_exactly_one_company"] += 1
        if normalised in independent:
            checks["independent_identifier_checked"] += 1
            if independent[normalised] == claims:
                checks["independent_identifier_agrees"] += 1
            else:
                failures.append(
                    {
                        "event_id": record["event_id"],
                        "reason": "independent_identifier_disagrees",
                        "independent": sorted(independent[normalised]),
                        "registry": sorted(claims),
                    }
                )
        if _name_token_overlap(applicant_by_event.get(record["event_id"], ""), entry["company_key"]):
            checks["name_token_overlap_descriptive"] += 1
    return {
        "seed": seed,
        "requested_sample_size": sample_size,
        "checks": checks,
        "failures": failures,
        "verdict": "PASS" if not failures else "FAIL",
    }


# ------------------------------------------------------------------------- schema
def audit_schema(store_path: str | Path, research_path: str | Path) -> dict[str, Any]:
    """Reproduce the state of the documented CIK columns/tables."""
    audit: dict[str, Any] = {}
    connection = open_readonly(store_path)
    try:
        companies = connection.execute("SELECT key, cik FROM companies").fetchall()
        events = connection.execute(
            "SELECT COUNT(*) AS n, SUM(company_key IS NULL) AS unlinked FROM events WHERE source = ?",
            (SOURCE,),
        ).fetchone()
    finally:
        connection.close()
    audit["store"] = {
        "path": str(Path(store_path)),
        "companies": len(companies),
        "companies_with_nonempty_cik": sum(1 for row in companies if str(row["cik"] or "").strip()),
        "sec_8k_events": int(events["n"] or 0),
        "sec_8k_unlinked": int(events["unlinked"] or 0),
    }
    research = open_readonly(research_path)
    try:
        companies = research.execute("SELECT key, cik FROM companies").fetchall()
        schemes = research.execute(
            "SELECT scheme, COUNT(*) AS n FROM company_identifiers GROUP BY scheme ORDER BY scheme"
        ).fetchall()
        identifiers = research.execute("SELECT COUNT(*) AS n FROM company_identifiers").fetchone()
    finally:
        research.close()
    audit["research"] = {
        "path": str(Path(research_path)),
        "companies": len(companies),
        "companies_with_nonempty_cik": sum(1 for row in companies if str(row["cik"] or "").strip()),
        "company_identifier_rows": int(identifiers["n"] or 0),
        "company_identifier_schemes": {str(row["scheme"]): int(row["n"]) for row in schemes},
    }
    return audit


# ----------------------------------------------------------------------- rebuild
def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def rebuild_registry(
    *,
    research_path: str | Path,
    config_paths: Sequence[str | Path],
    candidate_paths: Sequence[str | Path],
) -> dict[str, Any]:
    identifier_rows = load_identifier_rows(research_path)
    company_tickers = load_company_tickers(config_paths)
    candidates: list[dict[str, Any]] = []
    sources: list[dict[str, Any]] = []
    for path in candidate_paths:
        resolved = Path(path)
        if not resolved.exists():
            sources.append({"path": str(resolved), "present": False})
            continue
        rows = list(iter_candidate_rows([resolved]))
        candidates.extend(rows)
        sources.append(
            {
                "path": str(resolved),
                "present": True,
                "rows": len(rows),
                "sha256": _sha256(resolved),
                "ticker_source": "SEC EDGAR full-text search candidate dump (registrant ticker as reported by SEC)",
            }
        )
    provenance = {
        "identifier_table": {
            "path": str(Path(research_path)),
            "table": "company_identifiers",
            "schemes": ["SEC_CIK", "CIK"],
            "rows": len(identifier_rows),
            "companies": len({row[0] for row in identifier_rows}),
        },
        "candidate_sources": sources,
        "company_configs": [
            {"path": str(Path(path)), "sha256": _sha256(Path(path)) if Path(path).exists() else ""}
            for path in config_paths
        ],
        "ticker_rule": "curated roster ticker must exactly equal the SEC-reported registrant ticker",
        "candidates_rows_total": len(candidates),
        "generated_at": "deterministic: no wall-clock timestamp is recorded",
    }
    built = build_curated_registry(identifier_rows, candidates, company_tickers)
    document = registry_document(built, provenance)
    validate_registry_document(document)
    return document


def validate_registry_document(document: Mapping[str, Any]) -> None:
    """Registry invariants: canonical keys, disjoint sets, one company per CIK."""
    companies = document.get("companies", {})
    ambiguous = document.get("ambiguous", {})
    seen_companies: dict[str, str] = {}
    for key, entry in companies.items():
        cik = normalise_cik(entry.get("cik_int", key))
        if cik is None or cik10(cik) != str(key):
            raise InputError(f"non-canonical curated CIK key {key!r}")
        company_key = str(entry.get("company_key") or "")
        if not company_key:
            raise InputError(f"curated CIK {key!r} has no company_key")
        if company_key in seen_companies:
            raise InputError(
                f"company_key {company_key!r} claims two CIKs "
                f"({seen_companies[company_key]!r}, {key!r})"
            )
        seen_companies[company_key] = str(key)
    overlap = set(companies) & set(ambiguous)
    if overlap:
        raise InputError(f"CIKs both curated and ambiguous: {sorted(overlap)!r}")


def write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    path.write_text(text, encoding="utf-8")


def write_jsonl(path: Path, records: Sequence[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        json.dumps(record, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
        for record in records
    ]
    path.write_text(("\n".join(lines) + "\n") if lines else "", encoding="utf-8")


# -------------------------------------------------------------------------- main
def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="B-029 CIK-based deterministic 8-K linking")
    parser.add_argument("--store", default=str(DEFAULT_STORE), help="medradar.sqlite (read-only)")
    parser.add_argument("--research", default=str(DEFAULT_RESEARCH), help="research.sqlite (read-only)")
    parser.add_argument("--registry", default=str(DEFAULT_REGISTRY), help="curated CIK registry JSON")
    parser.add_argument("--report", default=str(DEFAULT_REPORT), help="link report JSON output")
    parser.add_argument("--links", default=str(DEFAULT_LINKS), help="linked-event mapping JSONL output")
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED, help="precision-sample RNG seed")
    parser.add_argument("--sample-size", type=int, default=DEFAULT_SAMPLE_SIZE)
    parser.add_argument("--rebuild-registry", action="store_true", help="regenerate the curated CIK registry")
    parser.add_argument("--candidates", nargs="*", default=[str(path) for path in DEFAULT_CANDIDATES])
    parser.add_argument("--configs", nargs="*", default=[str(path) for path in DEFAULT_CONFIGS])
    return parser


def run(args: argparse.Namespace) -> dict[str, Any]:
    if args.rebuild_registry:
        document = rebuild_registry(
            research_path=args.research,
            config_paths=args.configs,
            candidate_paths=args.candidates,
        )
        write_json(Path(args.registry), document)
        return {
            "mode": "rebuild-registry",
            "registry": str(Path(args.registry)),
            "curated_ciks": len(document["companies"]),
            "ambiguous_ciks": len(document["ambiguous"]),
        }

    registry = load_registry(args.registry)
    curated = registry["curated"]
    ambiguous = registry["ambiguous"]
    events = load_events(args.store)
    resolved = resolve_events(events, curated, ambiguous)

    independent = independent_identifier_index(args.research)
    applicant_by_event = {event["event_id"]: event["applicant_raw"] for event in events}
    mapping = sorted(
        resolved["corroborated"] + resolved["new_links"],
        key=lambda record: record["event_id"],
    )
    precision = precision_check(
        mapping,
        curated,
        ambiguous,
        seed=args.seed,
        sample_size=args.sample_size,
        independent=independent,
        applicant_by_event=applicant_by_event,
    )

    ambiguous_report = {
        "ciks": len(ambiguous),
        "companies": {cik10(cik): entry["companies"] for cik, entry in sorted(ambiguous.items())},
        "linked_events_excluded_from_precision": sum(
            1
            for event in events
            if event.get("company_key")
            and event.get("cik") is not None
            and event["cik"] in ambiguous
        ),
        "unlinked_events_excluded_from_linking": resolved["unresolved_reasons"]["cik_ambiguous"],
    }
    per_company_linked = dict(resolved["per_company_corroborated"])
    for company_key, count in resolved["per_company_new_links"].items():
        per_company_linked[company_key] = per_company_linked.get(company_key, 0) + count
    report = {
        "schema": "b101.cik_link_report.v1",
        "backlog_item": "B-029",
        "rule": (
            "exact integer CIK equality against a curated company CIK that maps to exactly one "
            "curated company_key; ambiguous CIKs refused; names/aliases/similarity never used"
        ),
        "inputs": {
            "store": str(Path(args.store)),
            "research": str(Path(args.research)),
            "registry": str(Path(args.registry)),
            "registry_schema": registry["document"].get("schema"),
            "registry_provenance": registry["document"].get("provenance"),
        },
        "registry": {
            "curated_ciks": len(curated),
            "curated_companies": len({entry["company_key"] for entry in curated.values()}),
            "ambiguous_ciks": len(ambiguous),
        },
        "funnel": resolved["funnel"],
        "unresolved_reasons": resolved["unresolved_reasons"],
        "unlinked_distinct_uncurated_ciks": resolved["unlinked_distinct_uncurated_ciks"],
        "unlinked_distinct_applicants": resolved["unlinked_distinct_applicants"],
        "top_unlinked_registrants": resolved["top_unlinked_registrants"],
        "precision_check": precision,
        "ambiguity": ambiguous_report,
        "data_quality": audit_schema(args.store, args.research),
        "existing_links_audit": {
            "already_linked_events": resolved["funnel"]["already_linked_events"],
            "cik_corroborated": len(resolved["corroborated"]),
            "cik_contradicted": len(resolved["mismatches"]),
            "cik_ambiguous_excluded": ambiguous_report["linked_events_excluded_from_precision"],
            "cik_unverifiable": resolved["funnel"]["already_linked_events"]
            - len(resolved["corroborated"])
            - len(resolved["mismatches"])
            - ambiguous_report["linked_events_excluded_from_precision"],
            "contradictions": resolved["mismatches"],
        },
        "per_company_linked_counts": dict(sorted(per_company_linked.items())),
        "per_company_new_link_counts": resolved["per_company_new_links"],
        "artifacts": {
            "events_linked.jsonl": {
                "rows": len(mapping),
                "new_links": len(resolved["new_links"]),
                "regenerable": True,
                "committed": False,
                "note": (
                    "generated deterministically by link_cik.py; intended for the Lead to commit. "
                    "Contains every CIK-anchored link at confidence 1.0 (existing links are marked "
                    "link_status=existing_corroborated; new links would be link_status=new)."
                ),
            },
            "cik_registry.json": {
                "committed": True,
                "regenerable": True,
                "note": "committed input; rebuild needs the local EDGAR candidate dump, which data/ does not track",
            },
        },
        "run": {"seed": args.seed, "sample_size": args.sample_size, "deterministic": True},
    }
    write_json(Path(args.report), report)
    write_jsonl(Path(args.links), mapping)
    return report


def summarise(report: Mapping[str, Any]) -> str:
    funnel = report["funnel"]
    precision = report["precision_check"]
    checks = precision["checks"]
    return (
        f"8-K events={funnel['sec_8k_events']} with_cik={funnel['events_with_payload_cik']} "
        f"unlinked={funnel['unlinked_events']} "
        f"cik_unambiguous={funnel['events_cik_equals_exactly_one_curated_cik']} "
        f"cik_ambiguous={funnel['events_cik_ambiguous']} "
        f"linked_now={funnel['linked_now']} | precision sampled={checks['sampled']} "
        f"verdict={precision['verdict']} | corroborated={report['existing_links_audit']['cik_corroborated']} "
        f"contradicted={report['existing_links_audit']['cik_contradicted']}"
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_argument_parser()
    args = parser.parse_args(argv)
    try:
        result = run(args)
    except (InputError, sqlite3.DatabaseError, OSError, ValueError) as error:
        print(f"[b101] FAIL: {error}", file=sys.stderr)
        return 2
    if args.rebuild_registry:
        print(
            f"[b101] registry written to {result['registry']}: "
            f"curated_ciks={result['curated_ciks']} ambiguous_ciks={result['ambiguous_ciks']}"
        )
    else:
        print(f"[b101] {summarise(result)}")
        print(f"[b101] report written to {args.report}; mapping written to {args.links}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
