"""Pure logic for the Europe PMC third-source cross-check (frozen in THIRD_SOURCE_PROTOCOL.md).

  * ``build_query`` — deterministic (company affiliation OR alias) AND (keyword terms) string, recorded verbatim;
  * ``classify`` — assign SUPPORTED_BEFORE / NO_RECORD / AMBIGUOUS / AFTER_CLEARANCE from dated hits;
  * ``lead_days`` — publication-to-clearance lead, positive when the paper precedes the clearance;
  * ``is_independent`` — exclude records that merely report a clinical trial (NCT identifier in title/abstract).

No label is produced here, by protocol.
"""
from __future__ import annotations

import re
from datetime import date
from typing import Iterable, Mapping, Sequence

QUARTER_DAYS = 91.25
NCT_PATTERN = re.compile(r"\bNCT\d{8}\b", re.IGNORECASE)
MAX_KEYWORD_TERMS = 3

#: frozen company affiliation terms (the same applicant aliases the study already uses)
COMPANY_TERMS = {
    "medtronic": ("Medtronic",),
    "ge_healthcare": ("GE HealthCare", "GE Medical"),
    "philips": ("Philips",),
    "mindray": ("Mindray",),
    "draeger": ("Draeger", "Dräger"),
}


def keyword_terms(matched_keywords: Sequence[str]) -> list[str]:
    """At most three keyword phrases, longest-token first, upper-cased, punctuation stripped."""
    cleaned = []
    for keyword in matched_keywords or []:
        text = re.sub(r"[^A-Za-z0-9 ]+", " ", str(keyword)).strip()
        if text:
            cleaned.append(text)
    cleaned.sort(key=lambda item: (-len(item.split()), -len(item)))
    return cleaned[:MAX_KEYWORD_TERMS]


def build_query(company: str, matched_keywords: Sequence[str]) -> dict:
    """Return the verbatim query and its components, so the search can be reproduced by hand."""
    terms = COMPANY_TERMS.get(company)
    if not terms:
        raise ValueError(f"no frozen affiliation terms for {company!r}")
    keywords = keyword_terms(matched_keywords)
    if not keywords:
        raise ValueError(f"no keyword terms for {company!r}")
    affiliation = " OR ".join(f'AFF:"{term}"' for term in terms)
    keyword_clause = " OR ".join(f'"{keyword}"' for keyword in keywords)
    query = f"({affiliation}) AND ({keyword_clause})"
    return {"query": query, "affiliation_terms": list(terms), "keyword_terms": keywords}


def parse_date(value: str | None) -> date | None:
    if not value:
        return None
    text = str(value).strip()[:10]
    try:
        return date.fromisoformat(text)
    except ValueError:
        return None


def is_independent(record: Mapping) -> bool:
    """A record reporting a clinical trial is not independent corroboration for this purpose."""
    haystack = f"{record.get('title') or ''} {record.get('abstractText') or ''}"
    return not NCT_PATTERN.search(haystack)


def lead_days(publication: date, clearance: date) -> int:
    """Positive when the publication precedes the clearance."""
    return (clearance - publication).days


def lead_quarters(days: int) -> float:
    return round(days / QUARTER_DAYS, 2)


def classify(records: Iterable[Mapping], *, clearance_date: date) -> dict:
    """Classify an event from its search hits; deterministic and order-independent."""
    dated, undated, trial_reports, used = [], 0, 0, []
    for record in records:
        publication = parse_date(record.get("firstPublicationDate"))
        if publication is None:
            undated += 1
            continue
        if not is_independent(record):
            trial_reports += 1
            continue
        dated.append((publication, record))
    before = [(publication, record) for publication, record in dated if publication < clearance_date]
    after = [(publication, record) for publication, record in dated if publication >= clearance_date]
    if before:
        publication, record = min(before, key=lambda item: item[0])
        days = lead_days(publication, clearance_date)
        return {"status": "SUPPORTED_BEFORE", "earliest_date": publication.isoformat(),
                "lead_days": days, "lead_quarters": lead_quarters(days),
                "earliest_record": {"title": record.get("title"),
                                    "authors": record.get("authorString"),
                                    "journal": (record.get("journalInfo") or {}).get("journal", {}).get("title")
                                    if isinstance(record.get("journalInfo"), Mapping) else None,
                                    "pmid": record.get("pmid"), "doi": record.get("doi")},
                "usable_records": len(before) + len(after), "undated": undated,
                "trial_reports_excluded": trial_reports}
    if after:
        publication, record = min(after, key=lambda item: item[0])
        return {"status": "AFTER_CLEARANCE", "earliest_date": publication.isoformat(),
                "lead_days": lead_days(publication, clearance_date),
                "lead_quarters": lead_quarters(lead_days(publication, clearance_date)),
                "earliest_record": {"title": record.get("title"), "pmid": record.get("pmid")},
                "usable_records": len(dated), "undated": undated, "trial_reports_excluded": trial_reports}
    if undated or trial_reports:
        return {"status": "AMBIGUOUS", "earliest_date": None, "lead_days": None, "lead_quarters": None,
                "usable_records": 0, "undated": undated, "trial_reports_excluded": trial_reports,
                "reason": "records exist but none is an independent, dated record"}
    return {"status": "NO_RECORD", "earliest_date": None, "lead_days": None, "lead_quarters": None,
            "usable_records": 0, "undated": 0, "trial_reports_excluded": 0}
