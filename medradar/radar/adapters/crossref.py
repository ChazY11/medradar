"""Crossref metadata adapter.

Crossref is the DOI registration agency: it is where a publisher's metadata lands first, so
it can surface a paper before PubMed indexes it. It is also the independent second source
that makes a cross-source identifier match meaningful - the same DOI, observed twice
through two unrelated APIs, is a real ``OFFICIAL_IDENTIFIER_MATCH``.

Incremental strategy
--------------------
``filter=from-created-date:<watermark - 2d>`` plus cursor deep paging. Crossref's
``created`` timestamp is when the metadata record was deposited, not when the article was
published, so it is the right incremental key. The publication date is stored separately,
at the precision Crossref actually states.

Politeness
----------
Crossref asks clients to identify themselves; the registry's contact address is sent as
``mailto`` on every request, which places the traffic in the polite pool.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Iterable, Mapping

from ..adapter import CollectContext
from ..records import MappingResult, Page, RawRecord, Scope, normalize_moment

WORKS = "https://api.crossref.org/works"
MAILTO = "research@medradar.example"
PAGE_SIZE = 100
MAX_PAGES = 3
WINDOW_OVERLAP_DAYS = 2
EARLIEST = "2018-01-01"

QUERIES: tuple[dict[str, str], ...] = (
    {"id": "haemodynamic-monitoring", "query": "patient monitoring intensive care haemodynamic"},
    {"id": "ecg-arrhythmia", "query": "electrocardiogram arrhythmia detection patient monitor"},
    {"id": "oximetry", "query": "pulse oximetry oxygen saturation intensive care"},
    {"id": "blood-pressure", "query": "invasive blood pressure monitoring critical care"},
    {"id": "alarms", "query": "alarm fatigue physiological monitor false alarm"},
    {"id": "deterioration", "query": "clinical deterioration prediction early warning intensive care"},
)


class CrossrefAdapter:
    source_id = "crossref"
    label = "Crossref metadata"
    adapter_version = "radar-crossref-1"
    declared_cadence_hours = 12.0
    record_types = ("publication",)

    def __init__(self, taxonomy, *, queries: Iterable[Mapping[str, str]] | None = None,
                 page_size: int = PAGE_SIZE, max_pages: int = MAX_PAGES,
                 mailto: str = MAILTO) -> None:
        self.taxonomy = taxonomy
        self.queries = tuple(queries or QUERIES)
        self.page_size = int(page_size)
        self.max_pages = int(max_pages)
        self.mailto = mailto
        self._by_id = {query["id"]: query for query in self.queries}

    # --------------------------------------------------------------------- plan
    def plan(self, ctx: CollectContext) -> list[Scope]:
        return [Scope(f"query:{query['id']}") for query in self.queries]

    def _since(self, ctx: CollectContext) -> str:
        if ctx.watermark:
            normalized = normalize_moment(ctx.watermark)[0]
            if normalized:
                try:
                    anchor = date.fromisoformat(normalized[:10])
                    return (anchor - timedelta(days=WINDOW_OVERLAP_DAYS)).isoformat()
                except ValueError:
                    pass
        return EARLIEST

    # -------------------------------------------------------------------- fetch
    def fetch_page(self, ctx: CollectContext, scope: Scope, cursor: str | None) -> Page:
        query_id = scope.scope_id.split(":", 1)[1]
        query = self._by_id.get(query_id)
        if query is None:
            raise ValueError(f"unknown Crossref query {query_id!r}")
        page_number = int(cursor or 0)
        if page_number >= self.max_pages:
            return Page(records=[], next_cursor=None, watermark=date.today().isoformat(),
                        note=f"query {query_id}: page cap reached")
        since = self._since(ctx)
        # Relevance ranking (the default when a query is supplied) is used deliberately:
        # cursor-paging the whole result set sorted by ``created`` returns every deposit the
        # query loosely matches, which is noise. A relevance cut over the recent window
        # returns what actually belongs to the topic.
        data = ctx.fetcher.get_json(WORKS, params={
            "query.bibliographic": query["query"],
            "filter": f"from-created-date:{since},type:journal-article",
            "rows": self.page_size,
            "offset": page_number * self.page_size,
            "mailto": self.mailto,
        }) or {}
        message = data.get("message") or {}
        items = [item for item in (message.get("items") or []) if isinstance(item, dict)]
        records = [record for item in items if (record := _record_from_item(item))]
        total = int(message.get("total-results") or 0)
        next_cursor = str(page_number + 1) if len(items) >= self.page_size and page_number + 1 < self.max_pages else None
        # The watermark is the window's upper bound (what we have covered), not the newest
        # publication date: journals routinely deposit issues dated in the future, and a future
        # watermark would silently skip every subsequent deposit.
        watermark = date.today().isoformat()
        return Page(
            records=records,
            next_cursor=next_cursor,
            watermark=watermark,
            note=f"query {query_id}: {len(records)} of {total} (created since {since}, relevance cut)",
        )

    # REFOUNDATION-004 removed the pre-storage relevance gate from this adapter.
    #
    # ``publication_relevance`` was a second, inconsistent rule set applied before the ledger
    # stored the record. A paper it rejected could never be re-judged by a later rule version and
    # never appeared in an evaluation sample. Crossref answers with something even when nothing
    # matches, so the assessment layer now does the filtering on the stored observation and the
    # default feed stays precise without deleting discovery evidence.

    # ------------------------------------------------------------------ mapping
    def map_record(self, record: RawRecord, ctx: CollectContext) -> MappingResult:
        from ..classify import RuleMapper

        return RuleMapper(self.taxonomy).map(record)


def _record_from_item(item: Mapping[str, Any]) -> RawRecord | None:
    doi = str(item.get("DOI") or "").strip()
    if not doi:
        return None
    title = _first_text(item.get("title")) or "(untitled)"
    container = _first_text(item.get("container-title"))
    abstract = _strip_markup(str(item.get("abstract") or ""))
    authors: list[str] = []
    affiliations: list[str] = []
    for author in item.get("author") or []:
        if not isinstance(author, dict):
            continue
        name = " ".join(filter(None, [str(author.get("given") or "").strip(),
                                      str(author.get("family") or "").strip()])).strip()
        if name:
            authors.append(name)
        for affiliation in author.get("affiliation") or []:
            text = str((affiliation or {}).get("name") or "").strip()
            if text and text not in affiliations:
                affiliations.append(text)
    published, precision = _publication_moment(item)
    created = item.get("created") or {}
    created_at = None
    if isinstance(created, dict) and created.get("date-time"):
        created_at = normalize_moment(str(created["date-time"]))[0]
    payload = {
        "doi": doi,
        "title": title,
        "container_title": container,
        "abstract": abstract,
        "authors": authors,
        "affiliations": affiliations,
        "publication_date": published,
        "publication_precision": precision,
        "created_at": created_at,
        "publisher": item.get("publisher"),
        "type": item.get("type"),
        "subject": list(item.get("subject") or []),
    }
    return RawRecord(
        source="crossref",
        source_record_id=f"doi:{doi.lower()}",
        official_identifier=f"DOI:{doi.lower()}",
        record_type="publication",
        title=title,
        url=f"https://doi.org/{doi}",
        event_at=published,
        event_at_precision=precision,
        published_at=published,
        published_at_precision=precision,
        payload=payload,
        text=" ".join(filter(None, [title, abstract, container, " ".join(item.get("subject") or [])])),
        extra={
            "organization_hint": _vendor_affiliation(affiliations),
            "organization_role": "publication_affiliation",
            "affiliations": affiliations,
            "product_hint": None,
            "product_codes": [],
            "official_identifier": f"DOI:{doi.lower()}",
            "doi": doi.lower(),
        },
    )


VENDOR_TERMS = ("philips", "ge healthcare", "ge health care", "ge medical systems", "draeger", "dräger")


def _vendor_affiliation(affiliations: Iterable[str]) -> str | None:
    for affiliation in affiliations:
        lowered = affiliation.lower()
        if any(term in lowered for term in VENDOR_TERMS):
            return affiliation
    return None


def _first_text(value: Any) -> str:
    if isinstance(value, list) and value:
        return str(value[0] or "").strip()
    return str(value or "").strip()


def _strip_markup(text: str) -> str:
    import re

    return " ".join(re.sub(r"<[^>]+>", " ", text).split())


def _publication_moment(item: Mapping[str, Any]) -> tuple[str | None, str]:
    for key in ("published-online", "published-print", "issued", "published"):
        node = item.get(key)
        if isinstance(node, dict):
            parts = node.get("date-parts") or []
            if parts and parts[0]:
                values = [int(value) for value in parts[0] if value is not None]
                if len(values) >= 3:
                    return f"{values[0]:04d}-{values[1]:02d}-{values[2]:02d}", "date"
                if len(values) == 2:
                    return f"{values[0]:04d}-{values[1]:02d}", "year"
                if len(values) == 1:
                    return f"{values[0]:04d}", "year"
    return None, "unknown"
