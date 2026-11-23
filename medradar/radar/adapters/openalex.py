"""OpenAlex - the breadth lane, and the only one that carries funding and institutions.

Why it is worth a second literature source
------------------------------------------
PubMed and Europe PMC answer "is this indexed in biomedicine". OpenAlex answers three questions
neither can:

* **who** - every authorship carries institution entities (ROR), not a free-text affiliation
  string, so a company can be attached to a paper without guessing;
* **how much it mattered** - ``cited_by_count`` and ``counts_by_year`` give a velocity signal,
  which is the closest thing to "this direction is heating up";
* **who paid** - ``grants[]`` carries funder and award identifiers, which join straight onto the
  NIH award table this project already builds.

Measured 2026-11-24 from the production host: 200 with 1,350,820 works for ``catheter``, so the
window filter is mandatory rather than optional - an unfiltered sweep is not a query, it is the
whole corpus.

Politeness
----------
OpenAlex offers a faster "polite pool" when the caller supplies ``mailto``. This adapter sends
one only when ``MEDRADAR_CONTACT_EMAIL`` is set, because inventing an address to get a better
rate would misrepresent who is making the requests.
"""

from __future__ import annotations

import os
import re
from datetime import date, timedelta
from typing import Any, Iterable, Mapping

from ..adapter import CollectContext
from ..records import (
    PRECISION_DATE,
    PRECISION_UNKNOWN,
    MappingResult,
    Page,
    RawRecord,
    Scope,
    normalize_moment,
)

SEARCH = "https://api.openalex.org/works"
PAGE_SIZE = 200
#: Measured 2026-11-24: OpenAlex is metered. Without a key a request costs $0.001 out of a
#: **$0.10/day budget shared by everyone on the host's IP**, so roughly 100 requests a day; a
#: free key raises it to $1/day. Eight queries at two pages each is 16 requests (~$0.016), which
#: leaves the shared budget for anything else on this host. A deeper lane needs the key.
MAX_RESULTS_PER_SCOPE = 400
WINDOW_OVERLAP_DAYS = 14
EARLIEST = date(2010, 1, 1)
CONTACT_ENV = "MEDRADAR_CONTACT_EMAIL"
#: Select is a cost decision, not just a payload decision: it keeps each page small enough to page
#: cheaply. ``grants`` is NOT a valid select field (measured: 400 "grants is not a valid select
#: field"), so funding metadata is only available on unselected records. Set this to fetch those
#: at roughly 20x the bytes.
FULL_RECORD_ENV = "MEDRADAR_OPENALEX_FULL_RECORDS"
SELECT_FIELDS = ("id,doi,title,publication_date,type,cited_by_count,counts_by_year,"
                 "authorships,topics,primary_location,open_access")

#: Device-relevant directions, as OpenAlex free-text searches. ``id`` is the scope key.
QUERIES: tuple[Mapping[str, Any], ...] = (
    {"id": "catheter_intervention", "term": "catheter intervention"},
    {"id": "patient_monitoring", "term": "patient monitoring vital signs"},
    {"id": "surgical_robotics", "term": "robot assisted surgery"},
    {"id": "cardiac_implant", "term": "transcatheter valve implant"},
    {"id": "wearable_sensing", "term": "wearable physiological sensor"},
    {"id": "device_safety", "term": "medical device failure adverse event"},
    {"id": "imaging_guidance", "term": "image guided intervention"},
    {"id": "neural_interface", "term": "neural implant stimulation"},
)


class OpenAlexAdapter:
    source_id = "openalex"
    label = "OpenAlex (institution entities, citation velocity, grant funding)"
    adapter_version = "radar-openalex-1"
    declared_cadence_hours = 24.0
    record_types = ("publication",)

    def __init__(self, taxonomy, *, queries: Iterable[Mapping[str, Any]] | None = None,
                 page_size: int = PAGE_SIZE,
                 max_results: int = MAX_RESULTS_PER_SCOPE) -> None:
        self.taxonomy = taxonomy
        self.queries = tuple(queries or QUERIES)
        self.page_size = min(int(page_size), PAGE_SIZE)
        self.max_results = int(max_results)
        self._by_id = {str(query["id"]): query for query in self.queries}
        self.contact = (os.environ.get(CONTACT_ENV) or "").strip()
        self.api_key = (os.environ.get("OPENALEX_API_KEY") or "").strip()
        self.full_records = (os.environ.get(FULL_RECORD_ENV) or "").strip() == "1"

    # --------------------------------------------------------------------- plan
    def plan(self, ctx: CollectContext) -> list[Scope]:
        return [Scope(f"query:{query['id']}") for query in self.queries]

    def _window(self, ctx: CollectContext) -> tuple[str, str]:
        end = date.today()
        start = end - timedelta(days=90)
        if ctx.watermark:
            normalized = normalize_moment(ctx.watermark)[0]
            if normalized:
                try:
                    start = date.fromisoformat(normalized[:10]) - timedelta(
                        days=WINDOW_OVERLAP_DAYS)
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
            raise ValueError(f"unknown OpenAlex query {query_id!r}")
        start, end = self._window(ctx)
        params: dict[str, Any] = {
            "search": query["term"],
            "filter": f"from_publication_date:{start},to_publication_date:{end}",
            "per-page": self.page_size,
            "cursor": cursor or "*",
        }
        if not self.full_records:
            # Measured: ``grants`` is not a valid select field, so it is omitted here and the
            # funding join is only possible when full records are requested explicitly.
            params["select"] = SELECT_FIELDS
        if self.contact:
            params["mailto"] = self.contact
        if self.api_key:
            params["api_key"] = self.api_key
        data = ctx.fetcher.get_json(SEARCH, params=params, allow_not_found=True) or {}
        results = data.get("results") or []
        meta = data.get("meta") or {}
        records = [record for row in results if (record := _record(row))]
        next_cursor = meta.get("next_cursor")
        if not results or not next_cursor:
            next_cursor = None
        spent = meta.get("cost_usd")
        return Page(
            records=records,
            next_cursor=next_cursor,
            watermark=end,
            note=(f"query {query_id}: {len(results)} of {meta.get('count')} works, "
                  f"publication_date {start}..{end}"
                  + (f", cost ${spent}" if spent is not None else "")),
        )

    # ------------------------------------------------------------------ mapping
    def map_record(self, record: RawRecord, ctx: CollectContext) -> MappingResult:
        from ..classify import RuleMapper

        return RuleMapper(self.taxonomy).map(record)


def _institutions(row: Mapping[str, Any]) -> list[str]:
    names: list[str] = []
    for authorship in (row.get("authorships") or []):
        if not isinstance(authorship, Mapping):
            continue
        for institution in (authorship.get("institutions") or []):
            if isinstance(institution, Mapping) and institution.get("display_name"):
                name = str(institution["display_name"]).strip()
                if name and name not in names:
                    names.append(name)
    return names


def _record(row: Mapping[str, Any]) -> RawRecord | None:
    openalex_id = str(row.get("id") or "").strip()
    title = " ".join(str(row.get("title") or "").split())
    if not openalex_id and not title:
        return None
    doi = str(row.get("doi") or "").strip()
    published = normalize_moment(row.get("publication_date"))
    institutions = _institutions(row)
    grants = [
        {"funder": str(grant.get("funder_display_name") or "").strip() or None,
         "award_id": str(grant.get("award_id") or "").strip() or None}
        for grant in (row.get("grants") or []) if isinstance(grant, Mapping)
    ]
    topics = [
        str(topic.get("display_name")) for topic in (row.get("topics") or [])
        if isinstance(topic, Mapping) and topic.get("display_name")
    ]
    source_name = None
    location = row.get("primary_location")
    if isinstance(location, Mapping):
        source = location.get("source")
        if isinstance(source, Mapping):
            source_name = str(source.get("display_name") or "").strip() or None
    open_access = row.get("open_access") if isinstance(row.get("open_access"), Mapping) else {}
    citations = row.get("cited_by_count")
    team = [
        str((authorship.get("author") or {}).get("display_name") or "").strip()
        for authorship in (row.get("authorships") or [])
        if isinstance(authorship, Mapping) and isinstance(authorship.get("author"), Mapping)
    ]
    team = [name for name in team if name]

    return RawRecord(
        source="openalex",
        source_record_id=f"openalex:{openalex_id.rsplit('/', 1)[-1] or title[:80]}",
        official_identifier=doi or openalex_id or None,
        record_type="publication",
        title=title[:400] or "(untitled)",
        url=doi or openalex_id or None,
        event_at=published[0],
        event_at_precision=published[1] if published[0] else PRECISION_UNKNOWN,
        published_at=published[0],
        published_at_precision=published[1] if published[0] else PRECISION_UNKNOWN,
        source_updated_at=published[0],
        source_updated_at_precision=PRECISION_DATE if published[0] else PRECISION_UNKNOWN,
        payload={
            "openalex_id": openalex_id,
            "doi": doi,
            "type": row.get("type"),
            "publication_date": row.get("publication_date"),
            "cited_by_count": citations,
            "counts_by_year": row.get("counts_by_year"),
            "source": source_name,
            "topics": topics,
            "institutions": institutions,
            "grants": grants,
            "authors": team,
            "is_open_access": bool(open_access.get("is_oa")) if open_access else None,
            "oa_status": open_access.get("oa_status") if open_access else None,
        },
        text=" ".join(filter(None, [title, " ".join(topics)]))[:12000],
        extra={
            "organization_hint": _first_company_like(institutions),
            "organization_role": "author_institution",
            "affiliations": institutions,
            "authors": team,
            "official_identifier": doi or openalex_id or None,
            "published_at_status": (
                "source_published_instant" if published[0] else "not_published_by_source"),
            "grants": grants,
            "open_access": {
                "is_open_access": bool(open_access.get("is_oa")) if open_access else None,
                "oa_status": open_access.get("oa_status") if open_access else None,
                "full_text_permitted": bool(open_access.get("is_oa")) if open_access else None,
            },
        },
    )


#: Institutions that are hospitals and universities crowd out the companies, and the company is
#: the thing this project tracks. The suffix list is the same legal-form vocabulary the assignee
#: resolver uses, so the two lanes agree on what a company name looks like.
_COMPANY_WORDS = (
    "INC", "CORP", "CORPORATION", "LLC", "LTD", "LIMITED", "GMBH", "AG", "SA", "SAS", "BV",
    "NV", "SPA", "SRL", "AB", "OY", "PLC", "PTE", "PTY", "CO", "COMPANY", "HOLDINGS", "GROUP",
)
_COMPANY_WORD_SET = frozenset(_COMPANY_WORDS)


def _first_company_like(institutions: list[str]) -> str | None:
    """The first institution whose name carries a legal-form token as a whole word.

    Token matching, not substring matching. Measured false positive that forced this: "University
    College London" matched the substring ``" CO"`` inside "COLLEGE" and was reported as a
    company, which would have attached a university paper to a vendor.
    """
    for name in institutions:
        tokens = set(re.findall(r"[A-Z0-9&]+", name.upper()))
        if tokens & _COMPANY_WORD_SET:
            return name
    return None


__all__ = ["CONTACT_ENV", "FULL_RECORD_ENV", "OpenAlexAdapter", "QUERIES", "SELECT_FIELDS"]
