"""Build steps for SCIENCE-002: universe -> panel -> artifacts.

Every step is deterministic given the cached source bytes, and every artifact
records the SHA-256 of the inputs it was derived from.
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from . import fda, sec, universe
from .entity import SecRegistrant, normalise_name
from .sources import Cache, sha256_bytes

STUDY = Path(__file__).resolve().parent
ARTIFACTS = STUDY / "artifacts"
DATA = STUDY / "data"
CACHE = DATA / "cache"

#: 510(k) bulk export used by this study (bytes + hash recorded in the artifact).
FIVE_TEN_K_ZIP = CACHE / "openfda" / "device-510k-0001-of-0001.json.zip"
FIVE_TEN_K_CSV = CACHE / "fda_510k_records.csv"
OWNER_MAP_CSV = CACHE / "fda_registration_owner_map.csv"


@dataclass
class UniverseBuild:
    firms: dict[str, universe.UniverseFirm]
    included: list[universe.UniverseFirm]
    excluded: list[dict[str, str]]
    matches: list[dict[str, Any]]
    submissions: dict[str, sec.Submissions]
    facts: dict[str, sec.CompanyFacts]
    tickers: dict[str, str]
    meta: dict[str, Any]


def _submissions_for(cache: Cache, ciks: Iterable[str],
                     progress: bool = False) -> dict[str, sec.Submissions]:
    out: dict[str, sec.Submissions] = {}
    for i, cik in enumerate(sorted(set(ciks))):
        out[cik] = sec.load_submissions(cache, cik)
        if progress and i % 25 == 0:
            print("  submissions", i, flush=True)
    return out


def _facts_for(cache: Cache, ciks: Iterable[str], progress: bool = False) -> dict[str, sec.CompanyFacts]:
    out: dict[str, sec.CompanyFacts] = {}
    for i, cik in enumerate(sorted(set(ciks))):
        try:
            out[cik] = sec.load_company_facts(cache, cik)
        except Exception as exc:  # a missing companyfacts document is a fact, not a crash
            print("  companyfacts missing for", cik, type(exc).__name__, flush=True)
            continue
        if progress and i % 25 == 0:
            print("  companyfacts", i, flush=True)
    return out


def build_universe(cache: Cache, artifacts: Path = ARTIFACTS,
                   cache_dir: Path = CACHE, verbose: bool = True,
                   include_tier_b: bool = True,
                   sic_set: Mapping[str, str] | None = None) -> UniverseBuild:
    """Build the universe. The two keyword switches exist only for the
    pre-registered sensitivities S1 (strict attribution) and S2 (no SIC 3826)."""
    records = fda.read_records_csv(cache_dir / FIVE_TEN_K_CSV.name)
    counts = universe.window_clearance_counts(records)
    tickers_by_root = universe.load_tickers(cache)
    owner_map = universe.load_owner_map(cache_dir / OWNER_MAP_CSV.name)

    roots = universe.candidate_roots(counts, tickers_by_root, owner_map,
                                     universe.MIN_WINDOW_CLEARANCES)
    if verbose:
        print("candidate SEC roots:", len(roots), flush=True)
    cik_title: dict[str, dict[str, Any]] = {}
    for root in roots:
        for row in tickers_by_root[root]:
            cik_title.setdefault(row["cik"], {"title": row["title"], "ticker": row["ticker"]})
    if verbose:
        print("candidate CIKs:", len(cik_title), flush=True)

    subs = _submissions_for(cache, cik_title, progress=verbose)
    registrants = [
        SecRegistrant(cik=cik, title=subs[cik].name or info["title"],
                      ticker=info["ticker"], sic=subs[cik].sic,
                      sic_description=subs[cik].sic_description,
                      former_names=tuple((str(n.get("name") or ""),
                                          str(n.get("from") or ""), str(n.get("to") or ""))
                                         for n in subs[cik].former_names))
        for cik, info in sorted(cik_title.items()) if cik in subs
    ]
    proposals = universe.propose_matches(registrants, counts, owner_map,
                                        include_tier_b=include_tier_b)
    matches, ledger = universe.resolve_ambiguity(proposals)
    if verbose:
        print("proposed matches:", len(proposals), "accepted:", len(matches),
              "ambiguous dropped:", len(ledger), flush=True)

    ticker_by_cik = {cik: info["ticker"] for cik, info in cik_title.items()}
    firms = universe.firms_from_matches(matches, subs, ticker_by_cik)

    facts = _facts_for(cache, firms.keys(), progress=verbose)

    included: list[universe.UniverseFirm] = []
    excluded: list[dict[str, str]] = []
    for cik, firm in sorted(firms.items(), key=lambda kv: -kv[1].n_window_clearances):
        ok, reason = universe.eligibility(firm, subs.get(cik), facts.get(cik),
                                          sic_set or universe.DEVICE_SIC)
        if ok:
            included.append(firm)
        else:
            excluded.append({**firm.as_row(), "status": "excluded", "reason": reason})
    if verbose:
        print("firms with any attribution:", len(firms), "included:", len(included), flush=True)

    return UniverseBuild(firms=firms, included=included, excluded=excluded,
                         matches=matches, submissions=subs, facts=facts,
                         tickers=ticker_by_cik, meta={
                             "n_candidate_roots": len(roots),
                             "n_candidate_ciks": len(cik_title),
                             "n_proposals": len(proposals),
                             "n_accepted": len(matches),
                             "n_ambiguous": len(ledger),
                             "n_included": len(included),
                             "n_excluded": len(excluded),
                         })
def clearance_index(build: UniverseBuild, cache_dir: Path = CACHE) -> dict[str, list]:
    """cik -> sorted decision dates of every cleared 510(k) attributed to that firm.

    The mapping is many-to-one by construction (an applicant root belongs to at
    most one firm after ambiguity resolution), so no clearance can be counted for
    two firms.
    """
    from datetime import datetime
    records = fda.read_records_csv(cache_dir / FIVE_TEN_K_CSV.name)
    root_to_cik: dict[str, str] = {}
    for firm in build.included:
        for match in firm.applicants:
            root_to_cik[str(match["applicant_root"])] = firm.cik
    out: dict[str, list] = {}
    for row in records:
        if (row.get("decision_code") or "") not in fda.CLEARED_DECISION_CODES:
            continue
        root = normalise_name(row.get("applicant") or "")
        cik = root_to_cik.get(root)
        day = row.get("decision_date") or ""
        if cik is None or not day:
            continue
        try:
            parsed = datetime.strptime(day, "%Y-%m-%d").date()
        except ValueError:
            continue
        out.setdefault(cik, []).append(parsed)
    for cik in out:
        out[cik].sort()
    return out