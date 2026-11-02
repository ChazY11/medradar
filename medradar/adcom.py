"""FDA Advisory Committee calendar and briefing-material collector.

This is a public, pre-decision source: it can show an upcoming panel, agenda and
briefing documents. It cannot reveal confidential pending 510(k)/PMA reviews.
The parser is deterministic and standard-library only so fixtures run offline.

Known live limitation (2026-11): FDA's calendar table ships only ``<thead>`` in
the static HTML; the ``<tbody>`` rows are rendered client-side by Drupal
DataTables. :func:`collect` therefore returns a loud non-ok status (``"empty"``
when the table exists but has no server-rendered rows, ``"source_changed"``
when the table markup is gone) with an explicit warning, and writes zero
events. The source is experimental/unavailable until FDA exposes a static or
JSON endpoint; a static fetch must never report ``status="ok"`` with zero
meetings.
"""

from __future__ import annotations

import re
import sys
from datetime import datetime, timedelta
from html.parser import HTMLParser
from typing import Any, Mapping
from urllib.parse import urljoin

from .config import load_tracks
from .db import DB, make_event_id
from .http import Fetcher
from .util import iso, today_utc, truncate

SOURCE = "fda_advisory_committee"
KIND = "advisory_committee"
CALENDAR_URL = "https://www.fda.gov/advisory-committees/advisory-committee-calendar"
DEVICE_TERMS = (
    "cdrh", "devices and radiological health", "medical devices",
    "device panel", "circulatory system devices", "neurological devices",
    "orthopaedic and rehabilitation devices", "clinical chemistry and clinical toxicology devices",
    "immunology devices", "microbiology devices", "molecular and clinical genetics",
    "ophthalmic devices", "anesthesiology and respiratory therapy devices",
    "general and plastic surgery devices", "gastroenterology-urology devices",
    "obstetrics and gynecology devices", "dental products", "radiological devices",
)
DOCUMENT_TERMS = (
    "briefing", "background", "agenda", "executive summary", "slides",
    "presentation", "transcript", "minutes", "materials", "fda summary",
)


def _space(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


class _TableParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.tables: list[list[list[dict[str, Any]]]] = []
        self._table_depth = 0
        self._rows: list[list[dict[str, Any]]] = []
        self._row: list[dict[str, Any]] | None = None
        self._cell: dict[str, Any] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        if tag == "table":
            if self._table_depth == 0:
                self._rows = []
            self._table_depth += 1
        elif tag == "tr" and self._table_depth:
            self._row = []
        elif tag in ("td", "th") and self._table_depth:
            self._cell = {"text": [], "links": [], "header": tag == "th"}
        elif tag == "a" and self._cell is not None:
            href = str(attributes.get("href") or "").strip()
            if href:
                self._cell["links"].append({"href": href, "text": ""})

    def handle_endtag(self, tag: str) -> None:
        if tag in ("td", "th") and self._cell is not None:
            self._cell["text"] = _space(" ".join(self._cell["text"]))
            if self._row is not None:
                self._row.append(self._cell)
            self._cell = None
        elif tag == "tr" and self._row is not None:
            if self._row:
                self._rows.append(self._row)
            self._row = None
        elif tag == "table" and self._table_depth:
            self._table_depth -= 1
            if self._table_depth == 0:
                self.tables.append(self._rows)
                self._rows = []

    def handle_data(self, data: str) -> None:
        if self._cell is None:
            return
        self._cell["text"].append(data)
        if self._cell["links"]:
            self._cell["links"][-1]["text"] += data


def parse_date(value: Any) -> str:
    text = _space(str(value or "")).replace(".", "")
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%B %d, %Y", "%b %d, %Y"):
        try:
            return datetime.strptime(text, fmt).date().isoformat()
        except ValueError:
            pass
    match = re.search(r"(20\d{2})-(\d{2})-(\d{2})", text)
    return match.group(0) if match else ""


def _calendar_table_present(html: str) -> bool:
    """Whether the page contains FDA's advisory-committee calendar table.

    Match the table element's own class, not the many navigation links to
    ``/advisory-committees/advisory-committee-calendar`` that survive a markup
    change.
    """
    return bool(re.search(
        r'<table[^>]*class=["\'][^"\']*lcds-datatable--advisory-committee-calendar',
        html or "", re.I,
    ))


def content_current_as_of(html: str) -> str:
    """Read the page's "Content current as of" date.

    The live page wraps the value in a machine-readable
    ``<time datetime="2026-10-30T07:55:31-04:00">10/30/2026</time>`` element;
    older/offline fixtures use a plain ``M/D/YYYY`` text node. Prefer the
    ``datetime`` attribute, then fall back to the visible text.
    """
    page = html or ""
    heading = re.search(r"Content\s+current\s+as\s+of", page, re.I)
    if not heading:
        return ""
    # A small window after the heading: enough for the <h2> + <p> + <time> block.
    window = page[heading.start(): heading.start() + 2000]
    stamp = re.search(r"<time[^>]*\bdatetime=[\"']([^\"']+)[\"']", window, re.I)
    if stamp:
        parsed = parse_date(stamp.group(1))
        if parsed:
            return parsed
    visible = re.sub(r"<[^>]+>", " ", window)
    match = re.search(r"(\d{1,2}/\d{1,2}/20\d{2})", visible)
    return parse_date(match.group(1)) if match else ""


def parse_calendar(html: str, base_url: str = CALENDAR_URL) -> list[dict[str, Any]]:
    """Parse FDA's five-column calendar (start/end/meeting/office/center)."""
    parser = _TableParser()
    parser.feed(html or "")
    meetings: list[dict[str, Any]] = []
    for table in parser.tables:
        for row in table:
            if len(row) < 5 or any(cell["header"] for cell in row[:2]):
                continue
            start = parse_date(row[0]["text"])
            end = parse_date(row[1]["text"]) or start
            meeting = row[2]["text"]
            if not start or not meeting or meeting.lower() == "meeting":
                continue
            links: list[dict[str, str]] = []
            for cell in row:
                for link in cell["links"]:
                    links.append({
                        "url": urljoin(base_url, link["href"]),
                        "text": _space(link["text"]),
                    })
            meeting_url = next((link["url"] for link in links if link["url"]), CALENDAR_URL)
            meetings.append({
                "start_date": start,
                "end_date": end,
                "meeting": meeting,
                "office": row[3]["text"],
                "center": row[4]["text"],
                "url": meeting_url,
                "links": links,
            })
    return meetings


def parse_document_links(html: str, base_url: str) -> list[dict[str, str]]:
    """Extract agenda/briefing/slides links from a meeting detail page."""
    # HTMLParser is reused through a small anchor-only subclass to avoid a
    # dependency on BeautifulSoup in the runtime package.
    class Anchors(HTMLParser):
        def __init__(self) -> None:
            super().__init__(convert_charrefs=True)
            self.links: list[dict[str, str]] = []
            self._current: dict[str, str] | None = None

        def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
            if tag == "a":
                href = str(dict(attrs).get("href") or "").strip()
                if href:
                    self._current = {"url": urljoin(base_url, href), "text": ""}

        def handle_data(self, data: str) -> None:
            if self._current is not None:
                self._current["text"] += data

        def handle_endtag(self, tag: str) -> None:
            if tag == "a" and self._current is not None:
                self._current["text"] = _space(self._current["text"])
                self.links.append(self._current)
                self._current = None

    anchors = Anchors()
    anchors.feed(html or "")
    seen: set[str] = set()
    result: list[dict[str, str]] = []
    for link in anchors.links:
        label = f"{link['text']} {link['url']}".lower()
        if not any(term in label for term in DOCUMENT_TERMS) and not link["url"].lower().endswith(".pdf"):
            continue
        if link["url"] in seen:
            continue
        seen.add(link["url"])
        result.append(link)
    return result


def is_device_meeting(meeting: Mapping[str, Any]) -> bool:
    text = " ".join(str(meeting.get(key) or "") for key in ("meeting", "office", "center")).lower()
    return any(term in text for term in DEVICE_TERMS)


def build_event(
    meeting: Mapping[str, Any],
    *,
    track_id: str | None,
    as_of: str,
    content_date: str = "",
    documents: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    start = str(meeting["start_date"])
    name = str(meeting["meeting"])
    links = list(meeting.get("links") or [])
    documents = documents if documents is not None else [
        link for link in links
        if any(term in f"{link.get('text', '')} {link.get('url', '')}".lower() for term in DOCUMENT_TERMS)
    ]
    # The calendar's "content current" date proves availability by that date,
    # not the original announcement instant; keep it estimated and non-tradable.
    published = content_date or as_of
    return {
        "event_id": make_event_id(SOURCE, KIND, start, name),
        "source": SOURCE,
        "kind": KIND,
        "event_date": start,
        "published_at": published,
        "available_at": published,
        "timestamp_quality": "estimated",
        "as_of": as_of,
        "company_key": None,
        "applicant_raw": str(meeting.get("office") or "FDA"),
        "country": "US",
        "track_id": track_id,
        "product_code": None,
        "title": truncate(f"FDA 咨询委员会：{name}", 400),
        "summary": truncate(
            f"{meeting.get('center') or 'FDA'}｜{start} 至 {meeting.get('end_date') or start}"
            f"｜公开材料 {len(documents)} 份",
            1200,
        ),
        "url": str(meeting.get("url") or CALENDAR_URL),
        "payload": {
            "meeting": name,
            "start_date": start,
            "end_date": meeting.get("end_date") or start,
            "office": meeting.get("office") or "",
            "center": meeting.get("center") or "",
            "stage": "pre_decision",
            "documents": documents,
            "calendar_url": CALENDAR_URL,
            "monitoring_scope": "public advisory-committee information only; not confidential pending applications",
        },
    }


def collect(db: DB, fetcher: Fetcher, months: int = 12, limit: int = 100, **_: Any) -> dict[str, Any]:
    """Collect public device-relevant meetings and any linked briefing files."""
    html = fetcher.get_text(CALENDAR_URL)
    meetings = parse_calendar(html)
    device_meetings = [meeting for meeting in meetings if is_device_meeting(meeting)]
    today = today_utc()
    earliest = today - timedelta(days=max(1, int(months)) * 31)
    recent = [m for m in device_meetings if m["start_date"] >= iso(earliest)]
    recent.sort(key=lambda row: (row["start_date"], row["meeting"]))
    if limit:
        recent = recent[: int(limit)]
    registry = load_tracks("device")
    as_of = iso(today)
    content_date = content_current_as_of(html)
    events: list[dict[str, Any]] = []
    detail_errors = 0
    document_count = 0
    for meeting in recent:
        text = " ".join(str(meeting.get(key) or "") for key in ("meeting", "office", "center"))
        documents = [
            link for link in meeting.get("links") or []
            if any(term in f"{link.get('text', '')} {link.get('url', '')}".lower() for term in DOCUMENT_TERMS)
        ]
        detail_url = str(meeting.get("url") or "")
        if detail_url and detail_url != CALENDAR_URL:
            try:
                detail = fetcher.get_text(detail_url)
                documents.extend(parse_document_links(detail, detail_url))
            except Exception:
                detail_errors += 1
        unique_documents = list({link["url"]: link for link in documents}.values())
        document_count += len(unique_documents)
        events.append(build_event(
            meeting,
            track_id=registry.match_frontier_text(text),
            as_of=as_of,
            content_date=content_date,
            documents=unique_documents,
        ))
    inserted = db.upsert_events(events) if events else 0
    warnings: list[str] = []
    if meetings:
        status = "ok"
        # A valid empty window (no device meetings in range) is fine; the only
        # dishonest outcome is claiming success when the page itself parsed 0 rows.
        if not content_date:
            warnings.append(
                "content_current_as_of missing; AdCom availability stays estimated from as_of"
            )
    elif _calendar_table_present(html):
        status = "empty"
        warnings.append(
            "calendar table yielded 0 meetings: FDA renders the <tbody> rows client-side"
            " (Drupal/DataTables JS), so the static page has no parseable rows;"
            " the AdCom source is experimental until a static or JSON endpoint exists"
        )
        if not content_date:
            warnings.append("content_current_as_of missing from the fetched page")
    else:
        status = "source_changed"
        warnings.append(
            "calendar table not found in the fetched page (expected"
            " 'lcds-datatable--advisory-committee-calendar'); the FDA page structure"
            " changed and 0 events were written"
        )
    stats = {
        "source": SOURCE,
        "status": status,
        "calendar_meetings": len(meetings),
        "device_meetings": len(device_meetings),
        "events": inserted,
        "documents": document_count,
        "detail_errors": detail_errors,
        "content_current_as_of": content_date or None,
        "timestamp_quality": "estimated",
        "warnings": warnings,
        "scope": "public meetings/materials only; no confidential pending 510(k)/PMA data",
    }
    for message in warnings:
        print(f"[adcom] WARNING: {message}", file=sys.stderr)
    print(f"[adcom] {inserted} device meetings / {document_count} public documents", file=sys.stderr)
    return stats


__all__ = [
    "SOURCE", "KIND", "CALENDAR_URL", "parse_calendar", "parse_document_links",
    "content_current_as_of", "is_device_meeting", "build_event", "collect",
]
