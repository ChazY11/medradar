"""medRxiv / bioRxiv preprints - the fastest public signal this project can read.

Why this lane exists
--------------------
The literature adapters already here (PubMed, Europe PMC, Crossref) all index a paper *after* it
has been through a journal. For "what is this company working on right now" that is months late.
Preprints appear in days, and both servers expose a keyless JSON API over a date interval with
an explicit total, which makes an incremental crawl straightforward instead of a guess.

Measured 2026-11-24 from the production host: a 23-day medRxiv window returned 200 with 30
records per page and ``count_new_papers`` / ``total`` in the message block, so the adapter knows
how far to page without scraping.

What it deliberately does not claim
-----------------------------------
``published`` is ``"NA"`` until the work appears in a journal. That field is stored rather than
interpreted: a preprint that later became a paper is a *transition* this adapter can report, but
inventing a publication date for it today would be a fabrication.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Iterable, Mapping

from ..adapter import CollectContext
from ..records import (
    PRECISION_DATE,
    MappingResult,
    Page,
    RawRecord,
    Scope,
    normalize_moment,
)

BASE = "https://api.{server}.org/details/{server}/{start}/{end}/{cursor}"
PAGE_SIZE = 100
MAX_RESULTS_PER_SCOPE = 2_000
WINDOW_OVERLAP_DAYS = 7
EARLIEST = date(2019, 6, 1)
SERVERS = ("medrxiv", "biorxiv")

#: The registry is browsed by category, not by free text, so the scope is a category rather than
#: a query term. The categories chosen are the ones a device engineer actually reads; a preprint
#: about a catheter or a monitor lands in one of these.
CATEGORIES: tuple[str, ...] = (
    "cardiovascular medicine",
    "surgery",
    "radiology and imaging",
    "intensive care and critical care medicine",
    "rehabilitation medicine and physical therapy",
    "health informatics",
    "medical ethics",
    "primary care research",
    "orthopedics",
    "oncology",
)
#: Categories are filtered client-side from one window per server, so a scope is a server, not a
#: category. Asking the API ten times for the same window would be ten identical downloads.
SCOPES: tuple[str, ...] = SERVERS


class PreprintAdapter:
    source_id = "preprints"
    label = "medRxiv / bioRxiv (preprint date, category, later journal outcome)"
    adapter_version = "radar-preprints-1"
    declared_cadence_hours = 6.0
    #: ``publication``, not a new ``preprint`` type. Measured: ``assessment.py`` decides the whole
    #: publication path with an exact ``record_type == "publication"`` test and classifies
    #: authenticity with ``record_type in ("publication", "clinical_trial")``. A new type would
    #: have silently skipped both and graded every preprint as SECONDARY. The distinguishing fact
    #: travels in ``payload["channel"]`` and ``extra["peer_review"]`` instead, where nothing has
    #: to branch on it to stay correct.
    record_types = ("publication",)

    def __init__(self, taxonomy, *, servers: Iterable[str] | None = None,
                 categories: Iterable[str] | None = None,
                 page_size: int = PAGE_SIZE,
                 max_results: int = MAX_RESULTS_PER_SCOPE) -> None:
        self.taxonomy = taxonomy
        self.servers = tuple(s.lower() for s in (servers or SERVERS))
        self.categories = tuple(c.lower() for c in (categories or CATEGORIES))
        self.page_size = min(int(page_size), 100)
        self.max_results = int(max_results)

    # --------------------------------------------------------------------- plan
    def plan(self, ctx: CollectContext) -> list[Scope]:
        return [Scope(f"server:{server}") for server in self.servers]

    def _window(self, ctx: CollectContext) -> tuple[str, str]:
        end = date.today()
        start = end - timedelta(days=30)
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
        server = scope.scope_id.split(":", 1)[1]
        if server not in self.servers:
            raise ValueError(f"unknown preprint server {server!r}")
        start, end = self._window(ctx)
        offset = int(cursor or 0)
        if offset >= self.max_results:
            return Page(records=[], next_cursor=None, watermark=end,
                        note=f"{server}: offset cap reached")
        data = ctx.fetcher.get_json(
            BASE.format(server=server, start=start, end=end, cursor=offset),
            allow_not_found=True,
        ) or {}
        message = ((data.get("messages") or [{}])[0]) if data.get("messages") else {}
        total = int(message.get("total") or 0)
        collected = data.get("collection") or []
        records = [record for row in collected if (record := _record(row, server))]
        kept = [record for record in records
                if str(record.payload.get("category") or "").lower() in self.categories]
        next_cursor = None
        if collected and offset + len(collected) < min(total, self.max_results):
            next_cursor = str(offset + len(collected))
        return Page(
            records=kept,
            next_cursor=next_cursor,
            watermark=end,
            note=(f"{server}: {len(kept)} kept of {len(collected)} on page "
                  f"(window {start}..{end}, total {total})"),
        )

    # ------------------------------------------------------------------ mapping
    def map_record(self, record: RawRecord, ctx: CollectContext) -> MappingResult:
        from ..classify import RuleMapper

        return RuleMapper(self.taxonomy).map(record)


def _record(raw: Mapping[str, Any], server: str) -> RawRecord | None:
    doi = str(raw.get("doi") or "").strip()
    title = " ".join(str(raw.get("title") or "").split())
    if not doi and not title:
        return None
    posted = normalize_moment(raw.get("date"))
    authors = [part.strip() for part in str(raw.get("authors") or "").split(";") if part.strip()]
    institution = str(raw.get("author_corresponding_institution") or "").strip()
    published = str(raw.get("published") or "NA").strip()
    abstract = " ".join(str(raw.get("abstract") or "").split())
    category = str(raw.get("category") or "").strip()

    return RawRecord(
        source="preprints",
        source_record_id=f"{server}:{doi or title[:80]}",
        official_identifier=doi or None,
        record_type="publication",
        title=title[:400] or "(untitled)",
        url=f"https://doi.org/{doi}" if doi else None,
        event_at=posted[0],
        event_at_precision=posted[1],
        # The preprint posting date is a real public instant: a reader could have seen it that
        # day. A journal publication date is a *different* event and is not invented here.
        published_at=posted[0],
        published_at_precision=posted[1],
        source_updated_at=posted[0],
        source_updated_at_precision=posted[1],
        payload={
            "server": server,
            "channel": "preprint",
            "doi": doi,
            "version": raw.get("version"),
            "category": category,
            "posted_date": raw.get("date"),
            "journal_published": published,
            "funder": raw.get("funder"),
            "license": raw.get("license"),
            "corresponding_institution": institution,
            "authors": authors,
        },
        text=" ".join(filter(None, [title, abstract, category]))[:12000],
        extra={
            "organization_hint": institution or None,
            "organization_role": "corresponding_institution",
            "affiliations": [institution] if institution else [],
            "authors": authors,
            "official_identifier": doi or None,
            "published_at_status": (
                "source_published_instant" if posted[0] else "not_published_by_source"),
            "open_access": {
                "is_open_access": True,   # every preprint on both servers is openly readable
                "has_pdf": True,
                "full_text_permitted": True,
                "license": raw.get("license"),
            },
            "journal_outcome": (
                "not_yet_published" if published.upper() == "NA"
                else f"published:{published}"),
            # Carried here rather than as a record_type, so a reader can still tell a preprint
            # from a peer-reviewed paper without any downstream branch changing.
            "peer_review": "not_peer_reviewed",
        },
    )


__all__ = ["CATEGORIES", "PreprintAdapter", "SERVERS"]
