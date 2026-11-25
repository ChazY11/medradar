"""Europe PMC adapter - the first source in this project with a real public timestamp.

The gap this closes
-------------------
MedRadar's headline limitation is that the committed snapshot carries
``published_at = available_at = event_date`` on every row, so *independent public time is 0
rows* and no point-in-time claim is possible. That is true of openFDA: neither 510(k) nor PMA
publishes a posting date.

Europe PMC does publish one. Three separate fields answer three different questions:

* ``firstPublicationDate`` - when the work first became public. This is the honest
  ``published_at``: a reader could have seen it that day.
* ``firstIndexDate`` - when Europe PMC indexed it. That is ``source_updated_at``, and it is
  *later* than first publication, which is exactly the lag a naive pipeline hides.
* ``dateOfCreation`` - when this particular record was created in Europe PMC.

Keeping them apart is the whole point. A publication whose firstPublicationDate is
2026-03-01 but whose firstIndexDate is 2026-04-10 could not have been read on 2026-03-02 by
anyone using *this index*, and a backtest that pretends otherwise is leaking 40 days.

Europe PMC also states ``isOpenAccess``/``inPMC``/``hasPDF`` per record, so the full-text
lane knows which records it may fetch instead of guessing from the publisher.
"""

from __future__ import annotations
from ..watermark import utc_today

import re
from datetime import date, timedelta
from typing import Any, Iterable, Mapping, Sequence

from ..adapter import CollectContext
from ..records import (
    PRECISION_DATE,
    MappingResult,
    Page,
    RawRecord,
    Scope,
    normalize_moment,
)

SEARCH = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"
PAGE_SIZE = 100
MAX_RESULTS_PER_SCOPE = 5_000
WINDOW_OVERLAP_DAYS = 14
EARLIEST = date(2018, 1, 1)

#: Query set. ``id`` is the scope key; ``term`` is Europe PMC's query syntax, which is
#: PubMed-like but adds ``FIRST_PDATE`` for the public-availability bound.
#:
#: The window is applied by the adapter, never baked into the term, so the same term can be
#: reused for a backfill and for an incremental cycle.
QUERIES: tuple[Mapping[str, Any], ...] = (
    {
        "id": "monitoring",
        "term": (
            '(TITLE_ABS:"patient monitor" OR TITLE_ABS:"patient monitoring" '
            'OR TITLE_ABS:"vital signs monitoring" OR TITLE_ABS:"ICU monitor")'
        ),
    },
    {
        "id": "respiratory",
        "term": (
            '(TITLE_ABS:"mechanical ventilation" OR TITLE_ABS:"ventilator" '
            'OR TITLE_ABS:"respiratory support")'
        ),
    },
    {
        "id": "cardiovascular_devices",
        "term": (
            '(TITLE_ABS:"transcatheter" OR TITLE_ABS:"left atrial appendage" '
            'OR TITLE_ABS:"drug-eluting stent" OR TITLE_ABS:"cardiac rhythm")'
        ),
    },
    {
        "id": "surgical_robotics",
        "term": (
            '(TITLE_ABS:"surgical robot" OR TITLE_ABS:"robotic surgery" '
            'OR TITLE_ABS:"robot-assisted")'
        ),
    },
    {
        "id": "device_safety",
        "term": (
            '(TITLE_ABS:"medical device" AND (TITLE_ABS:"recall" OR TITLE_ABS:"adverse event" '
            'OR TITLE_ABS:"failure mode" OR TITLE_ABS:"post-market"))'
        ),
    },
)


class EuropePmcAdapter:
    source_id = "europepmc"
    label = "Europe PMC (publication date, open-access state)"
    adapter_version = "radar-europepmc-1"
    declared_cadence_hours = 12.0
    record_types = ("publication",)

    def __init__(self, taxonomy, *, queries: Iterable[Mapping[str, Any]] | None = None,
                 page_size: int = PAGE_SIZE, max_results: int = MAX_RESULTS_PER_SCOPE) -> None:
        self.taxonomy = taxonomy
        self.queries = tuple(queries or QUERIES)
        self.page_size = min(int(page_size), 1000)
        self.max_results = int(max_results)
        self._by_id = {str(query["id"]): query for query in self.queries}

    # --------------------------------------------------------------------- plan
    def plan(self, ctx: CollectContext) -> list[Scope]:
        return [Scope(f"query:{query['id']}") for query in self.queries]

    def _window(self, ctx: CollectContext) -> tuple[str, str]:
        end = utc_today()
        start = end - timedelta(days=60)
        if ctx.watermark:
            normalized = normalize_moment(ctx.watermark)[0]
            if normalized:
                try:
                    start = date.fromisoformat(normalized[:10]) - timedelta(
                        days=WINDOW_OVERLAP_DAYS
                    )
                except ValueError:
                    pass
        if start < EARLIEST:
            start = EARLIEST
        if start > end:
            start = end
        return start.isoformat(), end.isoformat()

    # -------------------------------------------------------------------- fetch
    def fetch_page(self, ctx: CollectContext, scope: Scope, cursor: str | None) -> Page:
        query_id = scope.scope_id.split(":", 1)[1]
        query = self._by_id.get(query_id)
        if query is None:
            raise ValueError(f"unknown Europe PMC query {query_id!r}")
        start, end = self._window(ctx)
        page = int(cursor or 0)
        if page * self.page_size >= self.max_results:
            return Page(records=[], next_cursor=None, watermark=end,
                        note=f"query {query_id}: page cap reached")
        term = f'({query["term"]}) AND FIRST_PDATE:[{start} TO {end}]'
        # No ``sort`` parameter on purpose. Measured 2026-11-21: ``sort=FIRST_PDATE:asc``
        # makes the search endpoint answer 503 "Search service is temporarily unavailable"
        # instead of rejecting the sort field, and a retry loop then looks like an outage.
        # Ordering is not needed here anyway: the incremental bound is the window end, not the
        # newest record, and ``cursorMark`` keeps the result set stable across pages.
        data = ctx.fetcher.get_json(
            SEARCH,
            params={
                "query": term,
                "format": "json",
                "pageSize": self.page_size,
                "resultType": "core",
                "cursorMark": "*" if page == 0 else cursor,
            },
            allow_not_found=True,
        ) or {}
        rows = _results(data)
        records = [record for row in rows if (record := _record(row))]
        hit_count = int(data.get("hitCount") or 0)
        next_cursor = None
        if len(rows) >= self.page_size and (page + 1) * self.page_size < min(hit_count,
                                                                            self.max_results):
            next_cursor = str(page + 1)
        return Page(
            records=records,
            next_cursor=next_cursor,
            watermark=end,
            note=f"query {query_id}: {len(rows)} of {hit_count} records, FIRST_PDATE "
                 f"{start}..{end}",
        )

    # ------------------------------------------------------------------ mapping
    def map_record(self, record: RawRecord, ctx: CollectContext) -> MappingResult:
        from ..classify import RuleMapper

        return RuleMapper(self.taxonomy).map(record)


def _record(raw: Mapping[str, Any]) -> RawRecord | None:
    identifier = str(raw.get("id") or "").strip()
    source_db = str(raw.get("source") or "").strip()
    if not identifier:
        return None
    pmid = str(raw.get("pmid") or "").strip()
    doi = str(raw.get("doi") or "").strip()
    pmcid = str(raw.get("pmcid") or "").strip()
    title = " ".join(str(raw.get("title") or "").split()) or "(untitled)"

    first_public = normalize_moment(raw.get("firstPublicationDate"))
    first_index = normalize_moment(raw.get("firstIndexDate"))
    electronic = normalize_moment(raw.get("electronicPublicationDate"))

    journal = ((raw.get("journalInfo") or {}).get("journal") or {}) if isinstance(
        raw.get("journalInfo"), Mapping) else {}
    journal_title = str(journal.get("title") or journal.get("medlineAbbreviation") or "").strip()

    authors, affiliations = _authors(raw)
    abstract = " ".join(str(raw.get("abstractText") or "").split())
    keywords = [
        str(value) for value in ((raw.get("keywordList") or {}).get("keyword") or [])
        if value
    ]
    is_open_access = str(raw.get("isOpenAccess") or "").upper() == "Y"
    in_pmc = str(raw.get("inPMC") or "").upper() == "Y"

    url = (
        f"https://europepmc.org/article/{source_db}/{identifier}"
        if source_db else f"https://europepmc.org/search?query={identifier}"
    )
    if doi:
        url = f"https://doi.org/{doi}"

    return RawRecord(
        source="europepmc",
        source_record_id=f"epmc:{source_db or 'UNK'}:{identifier}",
        official_identifier=pmid or doi or pmcid or identifier,
        record_type="publication",
        title=title[:400],
        url=url,
        event_at=first_public[0] or electronic[0],
        event_at_precision=first_public[1] if first_public[0] else electronic[1],
        # The one place in this repository where published_at is a real public instant.
        published_at=first_public[0] or electronic[0],
        published_at_precision=first_public[1] if first_public[0] else electronic[1],
        source_updated_at=first_index[0],
        source_updated_at_precision=first_index[1] if first_index[0] else "unknown",
        payload={
            "id": identifier,
            "source_db": source_db,
            "pmid": pmid,
            "pmcid": pmcid,
            "doi": doi,
            "journal": journal_title,
            "first_publication_date": raw.get("firstPublicationDate"),
            "first_index_date": raw.get("firstIndexDate"),
            "electronic_publication_date": raw.get("electronicPublicationDate"),
            "is_open_access": is_open_access,
            "in_pmc": in_pmc,
            "cited_by_count": raw.get("citedByCount"),
            "pub_types": [str(v) for v in ((raw.get("pubTypeList") or {}).get("pubType") or [])],
            "keywords": keywords,
        },
        text=" ".join(filter(None, [title, abstract, " ".join(keywords)]))[:12000],
        extra={
            "organization_hint": _first_company_like(affiliations),
            "organization_role": "author_affiliation",
            "affiliations": affiliations,
            "authors": authors,
            "official_identifier": pmid or doi or identifier,
            "published_at_status": (
                "source_published_instant" if first_public[0]
                else "not_published_by_source"
            ),
            "open_access": {
                "is_open_access": is_open_access,
                "in_pmc": in_pmc,
                "has_pdf": str(raw.get("hasPDF") or "").upper() == "Y",
                "full_text_permitted": bool(is_open_access or in_pmc),
            },
        },
    )


def _authors(raw: Mapping[str, Any]) -> tuple[list[str], list[str]]:
    authors: list[str] = []
    affiliations: list[str] = []
    author_list = ((raw.get("authorList") or {}).get("author") or [])
    if not isinstance(author_list, Sequence):
        return authors, affiliations
    for author in author_list:
        if not isinstance(author, Mapping):
            continue
        name = str(author.get("fullName") or "").strip()
        if name:
            authors.append(name)
        for detail in ((author.get("authorAffiliationDetailsList") or {})
                       .get("authorAffiliation") or []):
            if isinstance(detail, Mapping):
                value = " ".join(str(detail.get("affiliation") or "").split())
                if value:
                    affiliations.append(value)
    # Deduplicate while preserving order: a 30-author paper often repeats one institution.
    seen: set[str] = set()
    unique: list[str] = []
    for value in affiliations:
        if value not in seen:
            seen.add(value)
            unique.append(value)
    return authors, unique


#: An affiliation is only a *hint* that a company is involved, so the test has to survive
#: the obvious false positive: "Division of Cardiology, Chi Mei Medical Center" contains
#: "Medical" and is a hospital. Any broader rule than this attributes papers to a company
#: that has nothing to do with them, which is worse than leaving the hint empty.
_ACADEMIC_MARKERS = re.compile(
    r"\b(university|universit[aä]t|universidad|universit[eé]|hospital|hospices?|"
    r"medical\s+cent(?:er|re)|medical\s+school|school\s+of|faculty|department|dept\.?|"
    r"division|institute|college|clinic|clinique|foundation|nhs|health\s+system|"
    r"krankenhaus|chu\b|chru\b|academy|centre\s+hospitalier|research\s+cent(?:er|re)|"
    r"national\s+institute|ministry|agency|authority)\b",
    re.IGNORECASE,
)
#: Legal-form suffixes that a commercial entity states about itself.
_LEGAL_FORMS = re.compile(
    r"\b(inc|incorporated|llc|l\.l\.c|ltd|limited|gmbh|ag|s\.a\.|sa\b|b\.?v\b|n\.?v\b|"
    r"plc|corp|corporation|co\.|company|k\.k|oy|ab|s\.?r\.?l|s\.?p\.?a|kg|se\b)\b",
    re.IGNORECASE,
)
#: Tracked vendors, so a filing that names the company without a legal form still resolves.
_VENDOR_MARKERS = (
    "medtronic", "abbott", "boston scientific", "philips", "siemens healthineers",
    "ge healthcare", "ge medical", "draeger", "dräger", "edwards lifesciences",
    "stryker", "intuitive surgical", "johnson & johnson", "baxter", "becton",
    "bd biosciences", "zimmer biomet", "biotronik", "microport", "mindray", "nihon kohden",
)


def _first_company_like(affiliations: Sequence[str]) -> str | None:
    """Return the first affiliation that is plausibly a commercial entity.

    This is a *hint*, not an attribution: the rule layer still has to accept it, and the full
    affiliation list travels in ``extra`` so a wrong guess stays debuggable. A hospital is
    never a hint even when its name contains "Medical".
    """
    for value in affiliations:
        if _ACADEMIC_MARKERS.search(value):
            continue
        if _LEGAL_FORMS.search(value):
            return value
        lowered = value.lower()
        if any(marker in lowered for marker in _VENDOR_MARKERS):
            return value
    return None


def _results(data: Any) -> list[dict[str, Any]]:
    if not isinstance(data, dict):
        return []
    rows = ((data.get("resultList") or {}).get("result") or [])
    return [row for row in rows if isinstance(row, dict)]


__all__ = ["EuropePmcAdapter", "QUERIES"]
