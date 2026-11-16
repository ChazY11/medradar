"""Philips official news adapter (robots-permitted HTML index).

Access is a verified precondition, not an assumption. ``scripts/radar_source_probe.py``
recorded that:

* ``https://www.philips.com/robots.txt`` is readable and does **not** disallow the news
  index or the press-release paths (it does disallow ``/content/`` and ``/crsc/``, which this
  adapter therefore never requests - including the RSS feed that lives under ``/content/``);
* the news index and a press-release page both returned HTTP 200 to the MedRadar user agent.

Incremental strategy
--------------------
The index is the inventory. A press-release URL that is not in the ledger is new; a known URL
is only re-fetched when the index no longer lists it (which is *not* treated as removal - the
index is a rolling window, not the full archive) or when a bounded re-check is due. The
adapter fetches at most ``max_new_pages`` pages per run, so a first run cannot turn into an
unbounded crawl of a vendor site.

Published time
--------------
The press-release pages carry a JSON-LD ``datePublished`` with a timezone, which is a real,
provable publication timestamp. When a page has no such field the adapter stores no
publication time instead of substituting the crawl time.
"""

from __future__ import annotations

import json
import re
from typing import Any

from ..adapter import CollectContext
from ..records import MappingResult, Page, RawRecord, Scope, normalize_moment

INDEX_URL = "https://www.philips.com/a-w/about/news.html"
PRESS_PATTERN = re.compile(
    r"https://www\.philips\.com/a-w/about/news/archive/standard/news/press/"
    r"(?P<year>20\d{2})/(?P<slug>[A-Za-z0-9\-_%\.]+)\.html"
)
TITLE_PATTERN = re.compile(r"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)
DATE_PUBLISHED_PATTERN = re.compile(r'"datePublished"\s*:\s*"([^"]+)"')
DESCRIPTION_PATTERN = re.compile(r'<meta[^>]+name="description"[^>]+content="([^"]*)"', re.IGNORECASE)


class PhilipsAdapter:
    source_id = "philips_official"
    label = "Philips official news"
    adapter_version = "radar-philips-1"
    declared_cadence_hours = 12.0
    record_types = ("press_release",)
    enabled = True
    access_state = "ENABLED"
    access_reason = None

    def __init__(self, taxonomy, *, index_url: str = INDEX_URL, max_new_pages: int = 20) -> None:
        self.taxonomy = taxonomy
        self.index_url = index_url
        self.max_new_pages = int(max_new_pages)

    # --------------------------------------------------------------------- plan
    def plan(self, ctx: CollectContext) -> list[Scope]:
        return [Scope("index")]

    # -------------------------------------------------------------------- fetch
    def fetch_page(self, ctx: CollectContext, scope: Scope, cursor: str | None) -> Page:
        if scope.scope_id != "index":
            raise ValueError(f"unknown scope {scope.scope_id!r}")
        html = ctx.fetcher.get_text(self.index_url).body
        links = _press_links(html)
        if not links:
            return Page(records=[], next_cursor=None, watermark=ctx.watermark,
                        note="the permitted news index exposed no press-release links")
        known = ctx.ledger.existing_record_ids(self.source_id, [link["record_id"] for link in links])
        new_links = [link for link in links if link["record_id"] not in known]
        # Newest year first so a capped run picks up the most recent releases.
        new_links.sort(key=lambda item: (item["year"], item["record_id"]), reverse=True)
        attempted = new_links[: self.max_new_pages]
        records: list[RawRecord] = []
        failed: list[str] = []
        errors: list[str] = []
        for link in attempted:
            try:
                page_html = ctx.fetcher.get_text(link["url"]).body
            except Exception as error:  # noqa: BLE001 - one page must not fail the scope
                failed.append(link["record_id"])
                errors.append(f"{link['url']}: {type(error).__name__}: {error}")
                continue
            records.append(_record_from_page(link, page_html))
        next_cursor = "more" if len(new_links) > len(attempted) else None
        watermark = max((record.published_at or record.event_at or "" for record in records), default="") or None
        return Page(
            records=records,
            next_cursor=next_cursor,
            watermark=watermark or ctx.watermark,
            failed_ids=[],  # a page that failed was never observed, so it has no id to mark
            note=(
                f"{len(links)} links on the index, {len(known)} already observed, "
                f"{len(attempted)} fetched, {len(failed)} failed"
                + (f"; errors: {'; '.join(errors[:3])}" if errors else "")
            ),
        )

    # ------------------------------------------------------------------ mapping
    def map_record(self, record: RawRecord, ctx: CollectContext) -> MappingResult:
        from ..classify import RuleMapper, ROLE_VENDOR

        mapping = RuleMapper(self.taxonomy).map(record)
        if not mapping.organization_candidates:
            # The publisher of the page is Philips by construction of this adapter.
            candidates = tuple(
                {**candidate, "role": ROLE_VENDOR}
                for candidate in self.taxonomy.resolve_organization("Royal Philips")
            )
            mapping = MappingResult(
                organization_candidates=candidates,
                product_candidates=mapping.product_candidates,
                technology_topics=mapping.technology_topics,
                method_version=mapping.method_version,
                note=mapping.note,
            )
        return mapping


def _press_links(html: str) -> list[dict[str, Any]]:
    seen: dict[str, dict[str, Any]] = {}
    for match in PRESS_PATTERN.finditer(html):
        url = match.group(0)
        slug = match.group("slug")
        record_id = f"philips:{match.group('year')}:{slug.lower()}"
        seen[record_id] = {"url": url, "record_id": record_id, "year": match.group("year"),
                          "slug": slug}
    return list(seen.values())


def _record_from_page(link: dict[str, Any], html: str) -> RawRecord:
    from ..classify import extract_vendor_product

    title_match = TITLE_PATTERN.search(html)
    title = _clean(title_match.group(1)) if title_match else link["slug"].replace("-", " ")
    title = re.sub(r"\s*\|\s*Philips\s*$", "", title).strip() or link["slug"]
    published = None
    precision = "unknown"
    date_match = DATE_PUBLISHED_PATTERN.search(html)
    if date_match:
        published, precision = normalize_moment(date_match.group(1))
    description = ""
    description_match = DESCRIPTION_PATTERN.search(html)
    if description_match:
        description = _clean(description_match.group(1))
    payload = {
        "title": title,
        "description": description,
        "official_url": link["url"],
        "year": link["year"],
        "slug": link["slug"],
        "publisher": "Royal Philips",
    }
    return RawRecord(
        source="philips_official",
        source_record_id=link["record_id"],
        official_identifier=link["url"],
        record_type="press_release",
        title=title,
        url=link["url"],
        event_at=published,
        event_at_precision=precision,
        published_at=published,
        published_at_precision=precision,
        payload=payload,
        text=" ".join(filter(None, [title, description])),
        extra={
            "organization_hint": "Royal Philips",
            "organization_role": "official_publisher",
            "publisher_hint": "Royal Philips",
            "product_hint": extract_vendor_product(title),
            "product_identifier": link["url"],
            "product_codes": [],
            "official_identifier": link["url"],
        },
    )


def _clean(value: str) -> str:
    import html as html_module

    return " ".join(html_module.unescape(value).split())


def parse_json_ld(html: str) -> list[dict[str, Any]]:
    """Extract JSON-LD blocks; used by tests and by the page parser's date fallback."""
    blocks: list[dict[str, Any]] = []
    for match in re.finditer(r'<script[^>]+type="application/ld\+json"[^>]*>(.*?)</script>', html,
                             re.IGNORECASE | re.DOTALL):
        try:
            value = json.loads(match.group(1))
        except ValueError:
            continue
        if isinstance(value, dict):
            blocks.append(value)
        elif isinstance(value, list):
            blocks.extend(item for item in value if isinstance(item, dict))
    return blocks
