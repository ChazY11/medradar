"""NCBI PubMed E-utilities connector (``publication``).

Two requests per batch, not one per record: ``esearch`` resolves the PMIDs and
``esummary`` returns their metadata in a single call.  The connector never
fetches full-text XML, so it stays inside the documented 3 req/s un-keyed limit
(the caller's ``HttpClient`` enforces the pacing).

Timestamp rule
--------------
``source_public_at`` = ``epubdate`` (electronic publication) when present, else
``pubdate``.  ``event_at`` = ``pubdate`` (the citation's publication date, often
month-year, i.e. ``coarse``).

Known limitation, stated rather than worked around
--------------------------------------------------
``esummary`` carries no author affiliation and no funder award id, so this
connector emits **no company entity_refs**.  Attributing a paper to a firm
requires Europe PMC core records or PubMed efetch, both of which are separate
decisions; silently guessing from a title is forbidden by the protocol.
"""

from __future__ import annotations

from typing import Any, Mapping

from .. import identity, schema
from . import _common

SOURCE_ID = "pubmed_eutils"
KIND = "publication"
LICENCE_STATUS = "open_no_explicit_licence"
SOURCE_NAME = "NCBI PubMed E-utilities"
ATTRIBUTION = "NCBI PubMed"
ESEARCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
ESUMMARY_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi"
DEFAULT_TERM = "medical device[MeSH Terms]"
TOOL = "medradar_research"
EMAIL = "medradar.research@example.org"


def _article_ids(docsum: Mapping[str, Any]) -> dict[str, str]:
    out: dict[str, str] = {}
    for entry in docsum.get("articleids") or []:
        if not isinstance(entry, Mapping):
            continue
        kind = str(entry.get("idtype") or "").strip().lower()
        value = str(entry.get("value") or "").strip()
        if kind and value:
            out.setdefault(kind, value)
    return out


def _identifiers(item: Mapping[str, Any]) -> list[dict[str, Any]]:
    docsum = item.get("docsum") or {}
    ids = _article_ids(docsum)
    out: list[dict[str, Any]] = []
    pmid = identity.build_identifier("pmid", item.get("uid") or ids.get("pubmed"), is_primary=True)
    if pmid:
        out.append(pmid)
    doi = identity.build_identifier("doi", ids.get("doi"))
    if doi:
        out.append(doi)
    pmcid = identity.build_identifier("pmcid", ids.get("pmc"))
    if pmcid:
        out.append(pmcid)
    return out


def to_evidence(raw_item: Mapping[str, Any], *, fetched_at: Any = None) -> dict[str, Any]:
    """One ``{"uid": ..., "docsum": {...}}`` pair -> one ``publication`` record."""
    item = dict(raw_item)
    docsum = dict(item.get("docsum") or {})
    fetched = _common.as_datetime(fetched_at)
    uid = str(item.get("uid") or docsum.get("uid") or "").strip()
    if not uid:
        raise ValueError("pubmed item without uid")
    epubdate = docsum.get("epubdate")
    pubdate = docsum.get("pubdate")
    public_at = epubdate or pubdate
    ids = _article_ids(docsum)
    normalized = {
        "title": str(docsum.get("title") or "").strip(),
        "journal": str(docsum.get("fulljournalname") or docsum.get("source") or ""),
        "pubdate": pubdate,
        "epubdate": epubdate,
        "sortpubdate": docsum.get("sortpubdate"),
        "volume": docsum.get("volume"),
        "issue": docsum.get("issue"),
        "pages": docsum.get("pages"),
        "pubtype": docsum.get("pubtype"),
        "authors_count": len(docsum.get("authors") or []),
        "article_ids": ids,
        "doi": ids.get("doi"),
        "pmcid": ids.get("pmc"),
        "author_affiliations": [],
        "grant_numbers": [],
        "trial_ids": [],
        "metadata_clock_fields": _common.metadata_clock_fields(
            ("lr", docsum.get("lr")),
            ("sortpubdate", docsum.get("sortpubdate")),
        ),
        "attribution_note": (
            "esummary exposes neither affiliations nor funder award ids; "
            "company attribution is therefore not attempted from this source"
        ),
    }
    return schema.make_evidence(
        source_id=SOURCE_ID,
        kind=KIND,
        source_record_id=uid,
        source_url=f"https://pubmed.ncbi.nlm.nih.gov/{uid}/",
        normalized=normalized,
        raw=_common.raw_block(item),
        time=_common.time_block(
            event_at=pubdate,
            source_public_at=public_at,
            fetched_at=fetched,
            notes="epubdate preferred as the public clock; pubdate may be month-year (coarse)",
        ),
        identifiers=_identifiers(item),
        entity_refs=[],
        provenance=_common.provenance(
            source_name=SOURCE_NAME,
            licence_status=LICENCE_STATUS,
            attribution=ATTRIBUTION,
            redistribution="NLM terms; some records publisher-copyright",
            evidence_reference=f"https://pubmed.ncbi.nlm.nih.gov/{uid}/",
            quality=_common.coerce_date(public_at)[1],
        ),
        fetched_at=fetched.isoformat(),
    )


def search_pmids(
    client: Any,
    *,
    term: str = DEFAULT_TERM,
    limit: int = 50,
    tool: str = TOOL,
    email: str = EMAIL,
) -> list[str]:
    """One ``esearch`` call -> up to ``limit`` PMIDs."""
    if limit <= 0:
        return []
    result = client.get(
        ESEARCH_URL,
        params={
            "db": "pubmed",
            "term": term,
            "retmode": "json",
            "retmax": int(limit),
            "sort": "pub date",
            "tool": tool,
            "email": email,
        },
    )
    if not result.ok:
        return []
    payload = result.json()
    ids = ((payload.get("esearchresult") or {}).get("idlist")) or []
    return [str(pid) for pid in ids[:limit]]


def fetch_items(
    client: Any,
    *,
    limit: int = 50,
    term: str = DEFAULT_TERM,
    tool: str = TOOL,
    email: str = EMAIL,
) -> list[dict[str, Any]]:
    """esearch + esummary; returns ``{"uid", "docsum"}`` items (two requests max)."""
    pmids = search_pmids(client, term=term, limit=limit, tool=tool, email=email)
    if not pmids:
        return []
    result = client.get(
        ESUMMARY_URL,
        params={
            "db": "pubmed",
            "retmode": "json",
            "id": ",".join(pmids),
            "tool": tool,
            "email": email,
        },
    )
    if not result.ok:
        return []
    payload = result.json()
    result_block = payload.get("result") or {}
    items: list[dict[str, Any]] = []
    for uid in result_block.get("uids") or []:
        docsum = result_block.get(str(uid))
        if isinstance(docsum, Mapping):
            items.append({"uid": str(uid), "docsum": dict(docsum)})
    return items[:limit]


def collect(
    client: Any,
    *,
    limit: int = 50,
    term: str = DEFAULT_TERM,
    tool: str = TOOL,
    email: str = EMAIL,
) -> list[dict[str, Any]]:
    """Fetch up to ``limit`` citations and return schema-valid evidence records."""
    fetched = _common.as_datetime(None)
    items = fetch_items(client, limit=limit, term=term, tool=tool, email=email)
    return [to_evidence(item, fetched_at=fetched) for item in items]


__all__ = [
    "SOURCE_ID",
    "KIND",
    "LICENCE_STATUS",
    "collect",
    "fetch_items",
    "search_pmids",
    "to_evidence",
]
