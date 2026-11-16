"""Dräger official newsroom adapter (robots-permitted sitemap + article pages).

The newsroom sitemap is the inventory and it carries a per-article ``<lastmod>``, which is
the best incremental key a static site can offer: a new ``<loc>`` is a new article, and a
newer ``lastmod`` on a known ``<loc>`` is the operator saying the article changed.

Access is verified, not assumed: ``docs/radar/evidence/source_probe.json`` records that
``draeger.com/robots.txt`` is readable, that it does not disallow
``/en_uk/sitemap/NewsroomArticle.xml`` or the article paths, and that both returned HTTP 200
to the MedRadar user agent.

The adapter re-fetches only new or lastmod-changed pages, capped at ``max_new_pages`` per run.
"""

from __future__ import annotations

import html as html_module
import re
import xml.etree.ElementTree as ET
from typing import Any

from ..adapter import CollectContext
from ..records import MappingResult, Page, RawRecord, Scope, normalize_moment

SITEMAP_URL = "https://www.draeger.com/en_uk/sitemap/NewsroomArticle.xml"
TITLE_PATTERN = re.compile(r"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)
DESCRIPTION_PATTERN = re.compile(r'<meta[^>]+name="description"[^>]+content="([^"]*)"', re.IGNORECASE)


class DraegerAdapter:
    source_id = "draeger_official"
    label = "Dräger official newsroom"
    adapter_version = "radar-draeger-1"
    declared_cadence_hours = 12.0
    record_types = ("press_release",)
    enabled = True
    access_state = "ENABLED"
    access_reason = None

    def __init__(self, taxonomy, *, sitemap_url: str = SITEMAP_URL, max_new_pages: int = 20) -> None:
        self.taxonomy = taxonomy
        self.sitemap_url = sitemap_url
        self.max_new_pages = int(max_new_pages)

    # --------------------------------------------------------------------- plan
    def plan(self, ctx: CollectContext) -> list[Scope]:
        return [Scope("sitemap")]

    # -------------------------------------------------------------------- fetch
    def fetch_page(self, ctx: CollectContext, scope: Scope, cursor: str | None) -> Page:
        if scope.scope_id != "sitemap":
            raise ValueError(f"unknown scope {scope.scope_id!r}")
        xml_text = ctx.fetcher.get_xml(self.sitemap_url)
        entries = _sitemap_entries(xml_text)
        if not entries:
            return Page(records=[], next_cursor=None, watermark=ctx.watermark,
                        note="the newsroom sitemap exposed no article entries")
        known = ctx.ledger.known_source_records(self.source_id)
        pending: list[dict[str, Any]] = []
        for entry in entries:
            prior = known.get(entry["record_id"])
            if prior is None:
                pending.append(entry)
            elif entry["lastmod"] and prior.get("source_updated_at") and entry["lastmod"] > prior["source_updated_at"]:
                pending.append(entry)
        pending.sort(key=lambda item: (item["lastmod"] or "", item["record_id"]), reverse=True)
        attempted = pending[: self.max_new_pages]
        records: list[RawRecord] = []
        errors: list[str] = []
        for entry in attempted:
            try:
                page_html = ctx.fetcher.get_text(entry["url"]).body
            except Exception as error:  # noqa: BLE001 - one article must not fail the scope
                errors.append(f"{entry['url']}: {type(error).__name__}: {error}")
                continue
            records.append(_record_from_entry(entry, page_html))
        next_cursor = "more" if len(pending) > len(attempted) else None
        newest_lastmod = max((entry["lastmod"] for entry in entries if entry["lastmod"]), default=None)
        return Page(
            records=records,
            next_cursor=next_cursor,
            watermark=newest_lastmod or ctx.watermark,
            note=(
                f"{len(entries)} sitemap entries, {len(pending)} new or lastmod-changed, "
                f"{len(attempted)} fetched, {len(errors)} failed"
                + (f"; errors: {'; '.join(errors[:3])}" if errors else "")
            ),
        )

    # ------------------------------------------------------------------ mapping
    def map_record(self, record: RawRecord, ctx: CollectContext) -> MappingResult:
        from ..classify import RuleMapper, ROLE_VENDOR

        mapping = RuleMapper(self.taxonomy).map(record)
        if not mapping.organization_candidates:
            candidates = tuple(
                {**candidate, "role": ROLE_VENDOR}
                for candidate in self.taxonomy.resolve_organization("Draegerwerk AG & Co. KGaA")
            )
            mapping = MappingResult(
                organization_candidates=candidates,
                product_candidates=mapping.product_candidates,
                technology_topics=mapping.technology_topics,
                method_version=mapping.method_version,
                note=mapping.note,
            )
        return mapping


def _sitemap_entries(xml_text: str) -> list[dict[str, Any]]:
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return []
    namespace = ""
    if root.tag.startswith("{"):
        namespace = root.tag.split("}", 1)[0] + "}"
    entries: list[dict[str, Any]] = []
    seen: set[str] = set()
    for node in root.iter(f"{namespace}url"):
        loc = (node.findtext(f"{namespace}loc") or "").strip()
        if not loc or loc in seen:
            continue
        seen.add(loc)
        lastmod_raw = (node.findtext(f"{namespace}lastmod") or "").strip()
        lastmod, _ = normalize_moment(lastmod_raw) if lastmod_raw else (None, "unknown")
        entries.append({
            "url": loc,
            "record_id": _record_id(loc),
            "lastmod": lastmod,
        })
    return entries


def _record_id(url: str) -> str:
    path = url.split("://", 1)[-1]
    path = path.split("/", 1)[1] if "/" in path else path
    return "draeger:" + path.strip("/").lower()


def _record_from_entry(entry: dict[str, Any], html: str) -> RawRecord:
    from ..classify import extract_vendor_product

    title_match = TITLE_PATTERN.search(html)
    title = _clean(title_match.group(1)) if title_match else ""
    title = re.sub(r"\s*\|\s*Dr[äa]ger\s*$", "", title).strip()
    if not title:
        title = entry["record_id"].rsplit("/", 1)[-1].replace("-", " ")
    description = ""
    description_match = DESCRIPTION_PATTERN.search(html)
    if description_match:
        description = _clean(description_match.group(1))
    # A newsroom article page rarely states a machine-readable publication date; lastmod is
    # the operator's own statement about the page, so it is stored as source_updated_at and
    # the publication date is left unknown rather than guessed.
    payload = {
        "title": title,
        "description": description,
        "official_url": entry["url"],
        "sitemap_lastmod": entry["lastmod"],
        "publisher": "Drägerwerk AG & Co. KGaA",
    }
    return RawRecord(
        source="draeger_official",
        source_record_id=entry["record_id"],
        official_identifier=entry["url"],
        record_type="press_release",
        title=title,
        url=entry["url"],
        event_at=None,
        event_at_precision="unknown",
        published_at=None,
        published_at_precision="unknown",
        source_updated_at=entry["lastmod"],
        source_updated_at_precision="datetime" if entry["lastmod"] else "unknown",
        payload=payload,
        text=" ".join(filter(None, [title, description])),
        extra={
            "organization_hint": "Draegerwerk AG & Co. KGaA",
            "organization_role": "official_publisher",
            "publisher_hint": "Draegerwerk AG & Co. KGaA",
            "product_hint": extract_vendor_product(title),
            "product_identifier": entry["url"],
            "product_codes": [],
            "official_identifier": entry["url"],
        },
    )


def _clean(value: str) -> str:
    return " ".join(html_module.unescape(value).split())
