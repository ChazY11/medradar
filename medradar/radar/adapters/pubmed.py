"""PubMed adapter (NCBI E-utilities).

The only free, documented, programmatic route to the biomedical literature index. No API
key is used, so the documented ceiling is 3 requests/second - the transport enforces it.

Incremental strategy
--------------------
E-utilities search supports a date window on the *Entrez* date (``datetype=edat``), which
is when the record entered PubMed, not when the study happened. The adapter walks a window
``[watermark - 3 days, today]`` and reports ``today`` as the scope watermark. The overlap
absorbs late indexing. Because the engine only advances a watermark for scopes that finished
without a failure, a 429 or a timeout leaves the window intact for the next attempt.

What is stored and what is not
-----------------------------
Stored: PMID, title, journal, publication date(s) with their precision, authors, affiliations,
abstract, DOI, MeSH terms, and the official PubMed URL. Not stored: full text (never
requested), and no claim that an affiliation is a product manufacturer - an affiliation is
an ``organization`` candidate with role ``publication_affiliation``, which the graph layer
may only use for ``DOCUMENT_MENTIONS_COMPANY``.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from datetime import date, timedelta
from typing import Any, Iterable, Mapping

from ..adapter import CollectContext
from ..records import MappingResult, Page, RawRecord, Scope, normalize_moment

ESEARCH = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
EFETCH = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
PAGE_SIZE = 100
MAX_RESULTS_PER_SCOPE = 300
WINDOW_OVERLAP_DAYS = 3
EARLIEST = "2015/01/01"

#: Named queries. ``[tiab]`` is title/abstract, ``[ad]`` is affiliation.
#: Each query is a documented literal: a reviewer can paste it into PubMed and get the same
#: records, which is the point.
QUERIES: tuple[dict[str, Any], ...] = (
    {
        "id": "cardio",
        "label": "ECG, arrhythmia and cardiac monitoring in critical care",
        "term": (
            '("electrocardiograph*"[tiab] OR "ECG"[tiab] OR "arrhythmia"[tiab]) AND '
            '("intensive care"[tiab] OR "ICU"[tiab] OR "patient monitor"[tiab] OR "patient monitoring"[tiab])'
        ),
    },
    {
        "id": "oximetry",
        "label": "SpO2 and pulse oximetry in critical care",
        "term": (
            '("oximetry"[tiab] OR "oximeter"[tiab] OR "SpO2"[tiab] OR "oxygen saturation"[tiab]) AND '
            '("intensive care"[tiab] OR "ICU"[tiab] OR "patient monitor"[tiab] OR "patient monitoring"[tiab])'
        ),
    },
    {
        "id": "pressure",
        "label": "Invasive and non-invasive blood pressure monitoring",
        "term": (
            '("invasive blood pressure"[tiab] OR "non-invasive blood pressure"[tiab] OR "NIBP"[tiab] '
            'OR "arterial pressure"[tiab]) AND ("intensive care"[tiab] OR "ICU"[tiab] OR "patient monitor"[tiab])'
        ),
    },
    {
        "id": "alarms",
        "label": "Physiological alarms, alarm fatigue and signal quality",
        "term": (
            '("alarm fatigue"[tiab] OR "alarm management"[tiab] OR "false alarm"[tiab] OR "false alarms"[tiab] '
            'OR "signal quality"[tiab]) AND ("intensive care"[tiab] OR "ICU"[tiab] OR "patient monitor"[tiab])'
        ),
    },
    {
        "id": "prediction",
        "label": "Deterioration prediction and clinical AI in intensive care",
        "term": (
            '("machine learning"[tiab] OR "artificial intelligence"[tiab] OR "deterioration"[tiab] '
            'OR "early warning score"[tiab]) AND ("intensive care"[tiab] OR "ICU"[tiab])'
        ),
    },
    {
        "id": "integration",
        "label": "Device integration, interoperability and central monitoring",
        "term": (
            '("HL7"[tiab] OR "FHIR"[tiab] OR "interoperability"[tiab] OR "central station"[tiab] '
            'OR "telemetry"[tiab]) AND ("intensive care"[tiab] OR "patient monitor"[tiab] OR "hospital"[tiab])'
        ),
    },
    {
        "id": "vendors",
        "label": "Research authored at the focus vendors (affiliation only)",
        "term": (
            '("Philips"[ad] OR "GE Healthcare"[ad] OR "GE HealthCare"[ad] OR "Draeger"[ad] OR "Dräger"[ad]) '
            'AND ("monitor"[tiab] OR "monitoring"[tiab] OR "intensive care"[tiab] OR "ICU"[tiab])'
        ),
    },
)


class PubMedAdapter:
    source_id = "pubmed"
    label = "PubMed / NCBI E-utilities"
    adapter_version = "radar-pubmed-1"
    declared_cadence_hours = 6.0
    record_types = ("publication",)

    def __init__(self, taxonomy, *, queries: Iterable[Mapping[str, Any]] | None = None,
                 page_size: int = PAGE_SIZE, max_results: int = MAX_RESULTS_PER_SCOPE) -> None:
        self.taxonomy = taxonomy
        self.queries = tuple(queries or QUERIES)
        self.page_size = int(page_size)
        self.max_results = int(max_results)
        self._query_by_id = {q["id"]: q for q in self.queries}

    # --------------------------------------------------------------------- plan
    def plan(self, ctx: CollectContext) -> list[Scope]:
        return [Scope(f"query:{query['id']}") for query in self.queries]

    def _window(self, ctx: CollectContext) -> tuple[str, str]:
        end = date.today()
        start = end - timedelta(days=60)
        if ctx.watermark:
            normalized = normalize_moment(ctx.watermark)[0]
            if normalized:
                try:
                    start = date.fromisoformat(normalized[:10]) - timedelta(days=WINDOW_OVERLAP_DAYS)
                except ValueError:
                    pass
        earliest = date(2015, 1, 1)
        if start < earliest:
            start = earliest
        return start.strftime("%Y/%m/%d"), end.strftime("%Y/%m/%d")

    # -------------------------------------------------------------------- fetch
    def fetch_page(self, ctx: CollectContext, scope: Scope, cursor: str | None) -> Page:
        query_id = scope.scope_id.split(":", 1)[1]
        query = self._query_by_id.get(query_id)
        if query is None:
            raise ValueError(f"unknown PubMed query {query_id!r}")
        retstart = int(cursor or 0)
        if retstart >= self.max_results:
            return Page(records=[], next_cursor=None, watermark=date.today().isoformat(),
                        note=f"query {query_id}: page cap reached")
        start, end = self._window(ctx)
        search = ctx.fetcher.get_json(ESEARCH, params={
            "db": "pubmed",
            "term": query["term"],
            "retmode": "json",
            "retmax": self.page_size,
            "retstart": retstart,
            "datetype": "edat",
            "mindate": start,
            "maxdate": end,
            "sort": "pub+date",
        }) or {}
        result = (search.get("esearchresult") or {})
        ids = [str(value) for value in (result.get("idlist") or [])]
        if not ids:
            return Page(records=[], next_cursor=None, watermark=end.replace("/", "-"),
                        note=f"query {query_id}: no records in {start}..{end}")
        records = self._efetch(ctx, ids)
        total = int(result.get("count") or len(ids))
        next_cursor = None
        if len(ids) >= self.page_size and retstart + len(ids) < min(total, self.max_results):
            next_cursor = str(retstart + len(ids))
        return Page(
            records=records,
            next_cursor=next_cursor,
            watermark=end.replace("/", "-"),
            note=f"query {query_id}: {len(records)} of {total} records in {start}..{end}",
        )

    def _efetch(self, ctx: CollectContext, ids: list[str]) -> list[RawRecord]:
        from urllib.parse import urlencode

        url = EFETCH + "?" + urlencode({"db": "pubmed", "id": ",".join(ids), "retmode": "xml"})
        xml_text = ctx.fetcher.get_xml(url)
        return [_record_from_article(article) for article in _articles(xml_text)]

    # ------------------------------------------------------------------ mapping
    def map_record(self, record: RawRecord, ctx: CollectContext) -> MappingResult:
        from ..classify import RuleMapper

        return RuleMapper(self.taxonomy).map(record)

    def accept_record(self, record: RawRecord, mapping) -> tuple[bool, str]:
        """Keep a paper only if it studies monitoring technology or names a monitored vendor.

        The PubMed queries are topical, but a query is a search, not a filter. A study that
        predicts deterioration from ICU data matches the decision-support topic while being a
        clinical study, not device research; :func:`medradar.radar.classify.publication_relevance`
        is the gate that separates the two, and its rejection reason is recorded.
        """
        from ..classify import publication_relevance

        return publication_relevance(mapping)


def _articles(xml_text: str) -> list[ET.Element]:
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return []
    return list(root.iter("PubmedArticle"))


def _text(element: ET.Element | None) -> str:
    if element is None:
        return ""
    return " ".join("".join(element.itertext()).split())


def _record_from_article(article: ET.Element) -> RawRecord:
    pmid = _text(article.find(".//MedlineCitation/PMID"))
    title = _text(article.find(".//Article/ArticleTitle")) or "(untitled)"
    journal = _text(article.find(".//Journal/Title"))
    abstract_parts = [
        _text(node) for node in article.findall(".//Abstract/AbstractText")
    ]
    abstract = " ".join(part for part in abstract_parts if part)
    doi = ""
    for node in article.findall(".//ArticleIdList/ArticleId"):
        if (node.get("IdType") or "").lower() == "doi":
            doi = _text(node)
            break
    if not doi:
        # Older/leaner records carry the DOI only as an ELocationID. Both are the publisher's
        # own statement of the identifier, so either is acceptable; a derived DOI never is.
        for node in article.findall(".//Article/ELocationID"):
            if (node.get("EIdType") or "").lower() == "doi":
                doi = _text(node)
                break
    authors: list[str] = []
    affiliations: list[str] = []
    for author in article.findall(".//AuthorList/Author"):
        last = _text(author.find("LastName"))
        fore = _text(author.find("ForeName"))
        collective = _text(author.find("CollectiveName"))
        if collective:
            authors.append(collective)
        elif last or fore:
            authors.append(" ".join(filter(None, [fore, last])))
        for node in author.findall(".//AffiliationInfo/Affiliation"):
            value = _text(node)
            if value and value not in affiliations:
                affiliations.append(value)
    mesh = [_text(node) for node in article.findall(".//MeshHeading/DescriptorName")]
    published, published_precision = _publication_moment(article)
    payload = {
        "pmid": pmid,
        "title": title,
        "journal": journal,
        "abstract": abstract,
        "doi": doi or None,
        "authors": authors,
        "affiliations": affiliations,
        "mesh_terms": [term for term in mesh if term],
        "publication_date": published,
        "publication_precision": published_precision,
    }
    return RawRecord(
        source="pubmed",
        source_record_id=f"pmid:{pmid}",
        official_identifier=f"PMID:{pmid}",
        record_type="publication",
        title=title,
        url=f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/" if pmid else None,
        event_at=published,
        event_at_precision=published_precision,
        published_at=published,
        published_at_precision=published_precision,
        payload=payload,
        text=" ".join(filter(None, [title, abstract, journal, " ".join(mesh)])),
        extra={
            "organization_hint": primary_vendor_affiliation(affiliations),
            "organization_role": "publication_affiliation",
            "affiliations": affiliations,
            "product_hint": None,
            "product_codes": [],
            "official_identifier": f"PMID:{pmid}",
            "pmid": pmid or None,
            "doi": doi or None,
        },
    )


VENDOR_AFFILIATION_TERMS = (
    "philips", "ge healthcare", "ge health care", "ge medical systems", "draeger", "dräger",
)


def primary_vendor_affiliation(affiliations: Iterable[str]) -> str | None:
    """The first affiliation string that names one of the monitored vendors, if any.

    It is returned as the organisation *hint* only. The rule layer tags it with role
    ``publication_affiliation``, so it can never become a product capability.
    """
    for affiliation in affiliations:
        lowered = affiliation.lower()
        if any(term in lowered for term in VENDOR_AFFILIATION_TERMS):
            return affiliation
    return None


def _publication_moment(article: ET.Element) -> tuple[str | None, str]:
    """Prefer ``ArticleDate`` (full date); fall back to ``PubDate`` at its own precision."""
    for node in article.findall(".//ArticleDate"):
        year = _text(node.find("Year"))
        month = _text(node.find("Month")) or "01"
        day = _text(node.find("Day")) or "01"
        if year:
            return f"{year}-{int(month):02d}-{int(day):02d}", "date"
    pub_date = article.find(".//JournalIssue/PubDate")
    if pub_date is not None:
        year = _text(pub_date.find("Year"))
        month = _text(pub_date.find("Month"))
        day = _text(pub_date.find("Day"))
        medline = _text(pub_date.find("MedlineDate"))
        if year and month and day.isdigit():
            return f"{year}-{_month_number(month):02d}-{int(day):02d}", "date"
        if year and month:
            return f"{year}-{_month_number(month):02d}", "year"
        if year:
            return year, "year"
        if medline:
            import re

            match = re.search(r"(\d{4})", medline)
            if match:
                return match.group(1), "year"
    return None, "unknown"


def _month_number(value: str) -> int:
    value = value.strip()
    if value.isdigit():
        return int(value)
    names = {name: index for index, name in enumerate(
        ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], start=1
    )}
    return names.get(value[:3].lower(), 1)
