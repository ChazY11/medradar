"""Google Patents - the patent lane that works while EPO review is pending.

Why this exists
---------------
EPO OPS is the durable answer and its adapter is written (``patents_ops.py``), but a fresh account
sits in "pending EPO administrator approval" and cannot log in or receive a consumer key. Leaving
the patent section empty for days is worse than using a second source that answers today.

What it actually is
-------------------
``patents.google.com`` has no published API. The page's own search is driven by an internal XHR:

    GET https://patents.google.com/xhr/query?url=<inner-query>&exp=

Measured 2026-11-24 from the production host, with a browser User-Agent:

    assignee=medtronic                 -> 124,609 results, 100 pages
    q="medtronic"                      ->  52,009 results
    q=spine&assignee=medtronic         ->  45,815 results
    inner page=1 / page=2              -> num_page advances, 10 hits per page, first ids change

Each hit carries ``publication_number``, ``title``, ``publication_date``, ``grant_date``,
``assignee``, ``inventor`` and a ``pdf`` path. That is enough to fill the same table the file
importer and EPO both fill.

Because it is not a published API, it can change without notice. That risk is not hidden: the
module reports a shape change as an error rather than as "this company holds no patents", and the
caller can fall back to EPO once the account is approved. Requests are paced at one every two
seconds, which is far slower than a human browsing the same site.

Measured 2026-11-24, after roughly a dozen probes from the host and from a residential line: the
whole ``patents.google.com`` domain began answering **503 to every client**, including a plain
browser User-Agent and the ordinary HTML search page. The block was not header-specific - adding
``Referer``, gzip and language negotiation changed nothing, and it applied to both the datacentre
address and the residential one. So this lane is a guest that can be shown the door at any rate,
and it must never be the only way the patent table gets filled. EPO OPS is the durable lane; this
module is the stopgap while that account is under review, and a 503 here is reported as a 503,
never as "no patents found".

Attribution
-----------
``assignee=`` is a substring match on the applicant field, so a query for one company returns
patents whose recorded applicant is a subsidiary (a search for "medtronic" returns Warsaw
Orthopedic filings). Writing only the queried name would silently attribute a subsidiary's patents
to the parent, and writing only the recorded applicant would make the parent unqueryable.

Both rows are therefore written, distinguished by ``assignee_type``:

    applicant      the applicant printed on the document - the fact
    query_matched  the name this enquiry matched - the trail

``patents_for_assignee`` counts distinct patent ids, so a caller sees the combined number and can
audit the split from the table without guessing.
"""

from __future__ import annotations

import html
import json
import re
from dataclasses import dataclass
from typing import Any, Iterable, Mapping
from urllib.parse import urlencode

XHR = "https://patents.google.com/xhr/query"
#: The endpoint returns ten hits per page and refuses to page past 100.
HITS_PER_PAGE = 10
MAX_PAGES = 100
_TAG = re.compile(r"<[^>]+>")
_SPACE = re.compile(r"\s+")


def _clean(value: Any, limit: int = 400) -> str:
    """Strip the response's own highlighting markup.

    Measured: a search for ``medtronic`` returns ``"<b>Medtronic</b> CV Luxembourg S.a.r.l"`` as
    the assignee, because the page highlights the matched term in the HTML it ships. Stored
    verbatim, that string never matches a normalised company name and every row would be dead
    weight in the join.
    """
    text = html.unescape(str(value or ""))
    text = _TAG.sub("", text)
    return _SPACE.sub(" ", text).strip()[:limit]


class GooglePatentsError(RuntimeError):
    """A quotable failure - never converted into an empty result."""


@dataclass
class GooglePatentHit:
    publication_number: str
    title: str
    publication_date: str
    assignee: str
    inventor: str
    kind: str
    pdf: str

    def to_dict(self) -> dict[str, Any]:
        return {"patent_id": self.publication_number, "title": self.title,
                "patent_date": self.publication_date, "organization": self.assignee}


def inner_query(assignee: str = "", query: str = "", page: int = 0,
                country: str = "") -> str:
    """Build the value of the ``url=`` parameter.

    The endpoint takes the real search expression url-encoded *inside* ``url=``, so ``page`` is a
    term of the search rather than a top-level argument. Sending ``&page=`` beside ``url=`` is
    ignored - measured: ``num_page`` stayed at 0 and the first hit did not change.
    """
    terms: list[str] = []
    if assignee:
        terms.append(f"assignee={assignee}")
    if query:
        terms.append(f'q="{query}"')
    if country:
        terms.append(f"country={country}")
    if not terms:
        raise ValueError("a patent search needs an assignee, a query, or a country")
    if page:
        terms.append(f"page={int(page)}")
    return "&".join(terms)


@dataclass
class GooglePatentsClient:
    fetcher: Any
    base: str = XHR

    def search(self, assignee: str = "", *, query: str = "", page: int = 0,
               country: str = "") -> dict[str, Any]:
        url = f"{self.base}?{urlencode({'url': inner_query(assignee, query, page, country), 'exp': ''})}"
        payload = self.fetcher.get_json(url, headers={"Accept": "application/json"}) or {}
        if not isinstance(payload, Mapping) or "results" not in payload:
            raise GooglePatentsError(
                "the XHR answered without a results object; the internal query API has changed")
        return payload


def _kind_of(publication_number: str) -> str:
    """The kind code is the trailing letter+digits of a publication number (B2, A1, U1)."""
    text = (publication_number or "").strip().upper()
    for index in range(len(text) - 1, -1, -1):
        if text[index].isalpha():
            return text[index:]
    return ""


def _patent_type(kind: str) -> str | None:
    """``B``/``P`` are granted, ``A`` is an application. Anything else stays unclassified rather
    than being guessed: an unknown kind is not evidence of a grant."""
    if not kind:
        return None
    head = kind[0]
    if head in ("B", "P"):
        return "grant"
    if head == "A":
        return "application"
    return None


def _iter_hits(payload: Mapping[str, Any]) -> Iterable[Mapping[str, Any]]:
    results = payload.get("results") or {}
    for cluster in results.get("cluster") or []:
        for row in cluster.get("result") or []:
            if isinstance(row, Mapping):
                yield row


def parse(payload: Mapping[str, Any]) -> tuple[int, list[GooglePatentHit]]:
    """Read one page. A page with no hits but a non-zero total is a real (if unhelpful) answer;
    a payload that is not the documented shape is an error."""
    results = payload.get("results")
    if not isinstance(results, Mapping):
        raise GooglePatentsError("no results object in the response")
    try:
        total = int(results.get("total_num_results") or 0)
    except (TypeError, ValueError):
        total = 0
    hits: list[GooglePatentHit] = []
    for row in _iter_hits(payload):
        patent = row.get("patent") or {}
        number = str(patent.get("publication_number") or "").strip()
        if not number:
            # ``id`` is "patent/US12279798B2/en"; the middle segment is the publication number.
            raw_id = str(row.get("id") or "")
            parts = raw_id.split("/")
            if len(parts) >= 2:
                number = parts[1].strip()
        if not number:
            continue
        hits.append(GooglePatentHit(
            publication_number=number,
            title=_clean(patent.get("title")),
            publication_date=_clean(patent.get("publication_date")
                                    or patent.get("grant_date"), 10),
            assignee=_clean(patent.get("assignee"), 200),
            inventor=_clean(patent.get("inventor"), 200),
            kind=_kind_of(number),
            pdf=_clean(patent.get("pdf"), 200),
        ))
    if not hits and total:
        raise GooglePatentsError(
            f"the response claims {total} results but carried no parsable hit; "
            "the record shape has changed")
    return total, hits


def import_assignee(reference, name: str, *, client: GooglePatentsClient,
                    pages: int = 1, country: str = "") -> dict[str, Any]:
    """Query one applicant and write both attribution rows for every hit."""
    from .patents import normalise_assignee
    from .patents_bulk import ensure_tables

    ensure_tables(reference)
    query_key = normalise_assignee(name)
    if not query_key:
        raise ValueError("empty assignee name")
    pages = max(1, min(int(pages), MAX_PAGES))

    total = 0
    written = 0
    applicant_rows = 0
    query_rows = 0
    seen: set[str] = set()
    for page in range(pages):
        payload = client.search(name, page=page, country=country)
        total, hits = parse(payload)
        if not hits:
            break
        for hit in hits:
            seen.add(hit.publication_number)
            reference.conn.execute(
                "INSERT OR REPLACE INTO bulk_patent (patent_id, title, patent_date, patent_type) "
                "VALUES (?,?,?,?)",
                (hit.publication_number, hit.title or None, hit.publication_date or None,
                 _patent_type(hit.kind)))
            reference.conn.execute(
                "INSERT OR REPLACE INTO bulk_patent_assignee "
                "(patent_id, assignee_id, organization, organization_norm, assignee_type) "
                "VALUES (?,?,?,?,?)",
                (hit.publication_number, f"google-query:{query_key}", name, query_key,
                 "query_matched"))
            query_rows += 1
            actual = normalise_assignee(hit.assignee) if hit.assignee else ""
            if actual:
                reference.conn.execute(
                    "INSERT OR REPLACE INTO bulk_patent_assignee "
                    "(patent_id, assignee_id, organization, organization_norm, assignee_type) "
                    "VALUES (?,?,?,?,?)",
                    (hit.publication_number, f"google-actual:{actual}", hit.assignee, actual,
                     "applicant"))
                applicant_rows += 1
        if len(hits) < HITS_PER_PAGE:
            break
    reference.conn.commit()
    written = len(seen)
    return {"assignee": name, "total_reported": total, "rows_written": written,
            "applicant_rows": applicant_rows, "query_rows": query_rows,
            "pages_read": pages}


__all__ = [
    "GooglePatentHit",
    "GooglePatentsClient",
    "GooglePatentsError",
    "HITS_PER_PAGE",
    "MAX_PAGES",
    "import_assignee",
    "inner_query",
    "parse",
]
