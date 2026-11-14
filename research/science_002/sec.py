"""SEC EDGAR access with explicit point-in-time semantics (SCIENCE-002).

What is taken from EDGAR, and what each field can prove
------------------------------------------------------
submissions (`data.sec.gov/submissions/CIK##########.json`)
    `acceptanceDateTime`  - ISO-8601 UTC instant at which EDGAR accepted a filing.
                            SCIENCE-001 verified on 720 filings that the raw
                            archive header (US/Eastern wall clock) converted with
                            the DST rule reproduces this value to the second, so
                            it is used here as the PIT instant for 8-K activity.
                            It is a *lower bound* on public availability.
    `filingDate`          - calendar day; never used as an instant.
    `items`               - SEC-assigned 8-K item codes (e.g. '2.02,9.01').
    `form`                - form type.
    `sic`, `sicDescription`, `formerNames` - registrant attributes; formerNames
                            carry the SEC-published rename intervals.

companyfacts (`data.sec.gov/api/xbrl/companyfacts/CIK##########.json`)
    each fact carries `filed`, the day of the filing that reported it. A fact is
    treated as publicly knowable only from that day (day granularity, stated as a
    limitation). When the same period is reported by several filings, the
    *first* one is used, because that is what a reader at the time would have
    seen; later restatements are not silently backfilled.

Nothing in this module returns a "publication timestamp" for SEC content, and
nothing fills a missing timestamp by estimate.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Any, Iterable

from .sources import Cache

SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik}.json"
COMPANY_FACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"

#: 8-K forms that count as disclosure activity.
EIGHT_K_FORMS = ("8-K", "8-K/A")

#: us-gaap tags used, in preference order. The first tag present with data wins
#: so that a firm is never double counted across equivalent tags.
RD_TAGS = (
    "ResearchAndDevelopmentExpense",
    "ResearchAndDevelopmentExpenseExcludingAcquiredInProcessCost",
)
REVENUE_TAGS = (
    "RevenueFromContractWithCustomerExcludingAssessedTax",
    "Revenues",
    "SalesRevenueNet",
    "RevenueFromContractWithCustomerIncludingAssessedTax",
)


def parse_instant(value: str | None) -> datetime | None:
    """Parse an SEC ISO-8601 instant into an aware UTC datetime."""
    if not value:
        return None
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    if dt.tzinfo is None:
        return None
    return dt.astimezone(timezone.utc)


def parse_day(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return datetime.strptime(value.strip()[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


@dataclass(frozen=True)
class Filing:
    accession: str
    form: str
    filing_date: date
    acceptance_utc: datetime | None
    items: tuple[str, ...]
    primary_document: str = ""

    def has_item(self, code: str) -> bool:
        return code in self.items


def split_items(raw: Any) -> tuple[str, ...]:
    if not raw:
        return ()
    text = str(raw)
    parts = [p.strip() for p in text.replace(";", ",").split(",")]
    return tuple(p for p in parts if p)


def recent_filings(payload: dict[str, Any], forms: Iterable[str] | None = None) -> list[Filing]:
    """Extract filings from the submissions payload's `recent` block.

    Only the *recent* block is used. `page_count`/`coverage` are returned by
    `filings_from_payload` so a caller can prove whether the block covers the
    study window before relying on it.
    """
    recent = (payload.get("filings") or {}).get("recent") or {}
    columns = ("accessionNumber", "filingDate", "acceptanceDateTime", "form",
               "items", "primaryDocument")
    if not all(col in recent for col in columns[:5]):
        return []
    wanted = set(forms) if forms else None
    out: list[Filing] = []
    n = len(recent.get("accessionNumber") or [])
    for i in range(n):
        form = str(recent["form"][i] or "")
        if wanted is not None and form not in wanted:
            continue
        day = parse_day(recent["filingDate"][i])
        if day is None:
            continue
        out.append(Filing(
            accession=str(recent["accessionNumber"][i] or ""),
            form=form,
            filing_date=day,
            acceptance_utc=parse_instant(recent["acceptanceDateTime"][i]),
            items=split_items(recent["items"][i]),
            primary_document=str(recent["primaryDocument"][i] or ""),
        ))
    return out


@dataclass
class Submissions:
    cik: str
    name: str
    sic: str
    sic_description: str
    former_names: tuple[dict[str, Any], ...]
    filings: list[Filing]
    recent_oldest: date | None
    recent_newest: date | None
    raw: dict[str, Any] = field(default_factory=dict)

    def coverage(self) -> str:
        if self.recent_oldest is None:
            return "empty"
        return f"{self.recent_oldest.isoformat()}..{(self.recent_newest or self.recent_oldest).isoformat()}"


def _filings_from_block(block: dict[str, Any]) -> list[Filing]:
    if not block or "accessionNumber" not in block:
        return []
    holder = {"filings": {"recent": block}}
    return recent_filings(holder)


def load_submissions(cache: Cache, cik: str, history: bool = True) -> Submissions:
    """Load a registrant's submissions, optionally merging the older index files.

    EDGAR keeps only the most recent ~1000 filings in the main document and puts
    older ones in numbered sibling files (`filings.files`). A trailing-365-day
    feature at the start of a 2021 panel needs 2020 filings, so the older files
    are merged when present. Without them, high-volume filers would silently lose
    their earliest window (this is exactly why the coverage floor is asserted per
    row rather than assumed).
    """
    payload = cache.get_json(SUBMISSIONS_URL.format(cik=cik))
    files = ((payload.get("filings") or {}).get("files") or [])
    filings = recent_filings(payload)
    if history:
        for entry in files:
            name = str(entry.get("name") or "")
            if not name:
                continue
            try:
                block = cache.get_json("https://data.sec.gov/submissions/" + name)
            except Exception:
                continue
            filings.extend(_filings_from_block(block))
    seen: set[str] = set()
    unique: list[Filing] = []
    for filing in filings:
        if filing.accession in seen:
            continue
        seen.add(filing.accession)
        unique.append(filing)
    unique.sort(key=lambda f: (f.filing_date, f.accession))
    days = [f.filing_date for f in unique]
    return Submissions(
        cik=cik,
        name=str(payload.get("name") or ""),
        sic=str(payload.get("sic") or ""),
        sic_description=str(payload.get("sicDescription") or ""),
        former_names=tuple(payload.get("formerNames") or ()),
        filings=unique,
        recent_oldest=min(days) if days else None,
        recent_newest=max(days) if days else None,
        raw=payload,
    )


# --------------------------------------------------------------------------- #
# XBRL company facts
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class Fact:
    tag: str
    start: date
    end: date
    value: float
    filed: date
    form: str
    frame: str = ""

    def as_row(self) -> dict[str, Any]:
        return {"tag": self.tag, "start": self.start.isoformat(), "end": self.end.isoformat(),
                "value": self.value, "filed": self.filed.isoformat(), "form": self.form}


def _pick_tag(us_gaap: dict[str, Any], tags: Iterable[str]) -> tuple[str, list[dict[str, Any]]]:
    for tag in tags:
        unit = ((us_gaap.get(tag) or {}).get("units") or {}).get("USD")
        if unit:
            return tag, unit
    return "", []


def duration_facts(payload: dict[str, Any], tags: Iterable[str]) -> list[Fact]:
    """Duration facts (income-statement style), first-reported only.

    A period may be reported again by later filings. The first report is kept and
    the rest are dropped, so a point-in-time view never sees a restatement it
    could not have seen.
    """
    us_gaap = ((payload.get("facts") or {}).get("us-gaap") or {})
    tag, rows = _pick_tag(us_gaap, tags)
    if not tag:
        return []
    first: dict[tuple[date, date], Fact] = {}
    for row in rows:
        start = parse_day(row.get("start"))
        end = parse_day(row.get("end"))
        filed = parse_day(row.get("filed"))
        if start is None or end is None or filed is None:
            continue
        try:
            value = float(row.get("val"))
        except (TypeError, ValueError):
            continue
        key = (start, end)
        previous = first.get(key)
        if previous is None or filed < previous.filed:
            first[key] = Fact(tag, start, end, value, filed, str(row.get("form") or ""),
                              str(row.get("frame") or ""))
    return sorted(first.values(), key=lambda f: (f.end, f.filed))


@dataclass
class CompanyFacts:
    cik: str
    rd: list[Fact]
    revenue: list[Fact]
    rd_tag: str = ""
    revenue_tag: str = ""


def load_company_facts(cache: Cache, cik: str) -> CompanyFacts:
    payload = cache.get_json(COMPANY_FACTS_URL.format(cik=cik))
    us_gaap = ((payload.get("facts") or {}).get("us-gaap") or {})
    return CompanyFacts(
        cik=cik,
        rd=duration_facts(payload, RD_TAGS),
        revenue=duration_facts(payload, REVENUE_TAGS),
        rd_tag=_pick_tag(us_gaap, RD_TAGS)[0],
        revenue_tag=_pick_tag(us_gaap, REVENUE_TAGS)[0],
    )