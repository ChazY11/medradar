"""Sample frame: which filings exist, which enter the panel, which are fetched.

Nothing here is estimated. Every filing that is excluded is excluded with a
machine-readable reason code, and the reasons are reported as a distribution in
the final sample report, so "we kept 640 of 12,000 filings" can never be read as
"the rest did not exist".
"""

from __future__ import annotations

import datetime as dt
import hashlib
import random
from typing import Any, Iterable, Sequence

from . import timesemantics as ts
from .edgar import ISSUERS, PANEL_FORMS, EdgarClient, Issuer

#: Analysis window, defined on the US/Eastern calendar day of the filing.
FRAME_START = dt.date(2021, 1, 1)
FRAME_END = dt.date(2026, 9, 30)

#: Extra historical strata used ONLY for the timezone/DST verification. They
#: sit before the panel window so they cannot leak into the experiment.
VERIFICATION_START = dt.date(2017, 1, 1)
VERIFICATION_END = dt.date(2020, 12, 31)

#: Foreign private issuers file 6-K/20-F; used for clock-normality checks only.
FOREIGN_FORMS: tuple[str, ...] = ("6-K", "20-F", "40-F")


class Exclusion:
    MISSING_ACCEPTION = "missing_accession"
    BAD_FORM = "form_not_in_frame"
    OUTSIDE_WINDOW = "outside_analysis_window"
    OUTSIDE_VERIFICATION = "outside_verification_window"
    FOREIGN_EXCLUDED = "foreign_private_issuer_not_in_panel"
    DUPLICATE = "duplicate_accession"


def _date(value: str | None) -> dt.date | None:
    if not value:
        return None
    try:
        return dt.date.fromisoformat(value[:10])
    except ValueError:
        return None


def dst_regime(day: dt.date) -> str:
    """EDT or EST, per the same rule used to convert acceptance times."""
    probe = dt.datetime.combine(day, dt.time(12, 0))
    return "EDT" if ts.eastern_utc_offset_hours(probe) == -4 else "EST"


def days_to_transition(day: dt.date) -> int:
    start, end = ts.dst_bounds_utc(day.year)
    edges = (start.date(), end.date())
    return min(abs((day - edge).days) for edge in edges)


def build_frame(client: EdgarClient,
                issuers: Sequence[Issuer] = ISSUERS) -> dict[str, Any]:
    """Pull every issuer's submissions index and classify each filing row.

    Returns a dict with the panel rows, the verification strata, the full
    exclusion ledger and the issuer identity evidence actually observed.
    """
    panel_rows: list[dict[str, Any]] = []
    verify_rows: list[dict[str, Any]] = []
    excluded: list[dict[str, Any]] = []
    identities: dict[str, Any] = {}
    seen: set[str] = set()

    for issuer in issuers:
        payload = client.submissions(issuer)
        identities[issuer.key] = {
            "ticker": issuer.ticker,
            "cik": issuer.cik,
            "name": payload.get("name"),
            "sic": payload.get("sic"),
            "sic_description": payload.get("sicDescription"),
            "entity_type": payload.get("entityType"),
            "former_names": payload.get("formerNames"),
            "fiscal_year_end": payload.get("fiscalYearEnd"),
            "identity_basis": ("ticker->CIK from SEC company_tickers.json; "
                               "CIK->name/SIC from data.sec.gov/submissions"),
        }
        rows = client.submission_rows(issuer, payload)
        for row in rows:
            accession = row.get("accessionNumber")
            form = row.get("form") or ""
            filing_date = _date(row.get("filingDate"))
            record = {
                "issuer": issuer.key,
                "ticker": issuer.ticker,
                "cik": issuer.cik,
                "accession": accession,
                "form": form,
                "filing_date": row.get("filingDate"),
                "report_date": row.get("reportDate"),
                "acceptance_api": row.get("acceptanceDateTime"),
                "primary_document": row.get("primaryDocument"),
                "items_raw": row.get("items"),
                "act": row.get("act"),
                "file_number": row.get("fileNumber"),
                "film_number": row.get("filmNumber"),
                "size": row.get("size"),
                "is_xbrl": row.get("isXBRL"),
                "dst_regime": dst_regime(filing_date) if filing_date else None,
                "days_to_dst_transition": days_to_transition(filing_date) if filing_date else None,
            }
            if not accession or filing_date is None:
                excluded.append({"reason": Exclusion.MISSING_ACCEPTION, **record})
                continue
            if accession in seen:
                excluded.append({"reason": Exclusion.DUPLICATE, **record})
                continue
            seen.add(accession)

            in_panel_form = form in PANEL_FORMS and issuer.panel
            in_foreign_form = form in FOREIGN_FORMS and not issuer.panel
            if not (in_panel_form or in_foreign_form):
                excluded.append({"reason": Exclusion.BAD_FORM, **record})
                continue
            if not issuer.panel and form in FOREIGN_FORMS:
                # Foreign filings are wanted only for clock checks, not the panel.
                if VERIFICATION_START <= filing_date <= FRAME_END:
                    verify_rows.append(record)
                continue
            if FRAME_START <= filing_date <= FRAME_END:
                panel_rows.append(record)
            elif VERIFICATION_START <= filing_date <= VERIFICATION_END:
                verify_rows.append(record)
            else:
                excluded.append({"reason": Exclusion.OUTSIDE_WINDOW, **record})

    panel_rows.sort(key=lambda r: (r["issuer"], r["filing_date"], r["accession"] or ""))
    verify_rows.sort(key=lambda r: (r["issuer"], r["filing_date"], r["accession"] or ""))
    ledger: dict[str, int] = {}
    for row in excluded:
        ledger[row["reason"]] = ledger.get(row["reason"], 0) + 1
    return {
        "frame_start": FRAME_START.isoformat(),
        "frame_end": FRAME_END.isoformat(),
        "verification_start": VERIFICATION_START.isoformat(),
        "verification_end": VERIFICATION_END.isoformat(),
        "issuers": {i.key: {"ticker": i.ticker, "cik": i.cik, "panel": i.panel,
                            "segment": i.segment, "note": i.note} for i in ISSUERS},
        "identities": identities,
        "panel": panel_rows,
        "verification_pool": verify_rows,
        "excluded": excluded,
        "exclusion_ledger": ledger,
    }


#: (year, regime, proximity) strata the verification sample must cover.
def verification_strata(frame: dict[str, Any]) -> dict[str, dict[str, Any]]:
    strata: dict[str, dict[str, Any]] = {}
    for row in frame["verification_pool"] + frame["panel"]:
        day = _date(row["filing_date"])
        if day is None:
            continue
        near = "near_transition" if row["days_to_dst_transition"] <= 10 else "mid_season"
        key = "%d|%s|%s" % (day.year, row["dst_regime"], near)
        bucket = strata.setdefault(key, {"key": key, "year": day.year,
                                         "regime": row["dst_regime"],
                                         "proximity": near, "rows": []})
        bucket["rows"].append(row)
    return strata


def select_verification_sample(frame: dict[str, Any], per_stratum: int = 2,
                               seed: int = 20261114) -> list[dict[str, Any]]:
    """Deterministic, stratified, reproducible verification sample.

    Every stratum (year x DST regime x proximity to a transition) contributes up
    to per_stratum filings. Selection is seeded so the exact same filings are
    chosen on any machine.
    """
    rng = random.Random(seed)
    selected: list[dict[str, Any]] = []
    chosen: set[str] = set()
    for key in sorted(verification_strata(frame)):
        bucket = verification_strata(frame)[key]
        rows = list(bucket["rows"])
        rng.shuffle(rows)
        taken = 0
        for row in rows:
            if row["accession"] in chosen:
                continue
            chosen.add(row["accession"])
            selected.append({**row, "stratum": key})
            taken += 1
            if taken >= per_stratum:
                break
    selected.sort(key=lambda r: (r["filing_date"], r["accession"]))
    return selected


def fetch_set(frame: dict[str, Any], verification_rows: Sequence[dict[str, Any]],
              include_panel: bool = True) -> list[dict[str, Any]]:
    """Union of the analysis panel and the verification sample, de-duplicated."""
    by_accession: dict[str, dict[str, Any]] = {}
    if include_panel:
        for row in frame["panel"]:
            by_accession[row["accession"]] = dict(row)
    for row in verification_rows:
        by_accession.setdefault(row["accession"], dict(row))
    rows = [by_accession[key] for key in sorted(by_accession)]
    rows.sort(key=lambda r: (r["filing_date"], r["accession"]))
    return rows


def sample_report(frame: dict[str, Any], verification_rows: Sequence[dict[str, Any]],
                  fetched: Sequence[dict[str, Any]]) -> dict[str, Any]:
    """Honest accounting: what exists, what we took, what we skipped and why."""
    panel = frame["panel"]
    per_issuer: dict[str, int] = {}
    for row in panel:
        per_issuer[row["issuer"]] = per_issuer.get(row["issuer"], 0) + 1
    per_year: dict[str, int] = {}
    for row in panel:
        key = row["filing_date"][:4]
        per_year[key] = per_year.get(key, 0) + 1
    strata = verification_strata(frame)
    return {
        "issuers_in_registry": len(ISSUERS),
        "panel_filings": len(panel),
        "panel_per_issuer": dict(sorted(per_issuer.items())),
        "panel_per_year": dict(sorted(per_year.items())),
        "verification_pool": len(frame["verification_pool"]),
        "verification_strata": len(strata),
        "verification_selected": len(verification_rows),
        "fetched": len(fetched),
        "excluded_total": len(frame["excluded"]),
        "exclusion_ledger": dict(sorted(frame["exclusion_ledger"].items())),
        "frame_start": frame["frame_start"],
        "frame_end": frame["frame_end"],
    }
