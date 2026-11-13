"""FDA import alerts — connector for ``fda_import_alerts``.

There is **no openFDA endpoint** for import alerts.  The public data lives in the
FDA "Import Alerts" database at ``https://www.accessdata.fda.gov/cms_ia/`` and is
server-rendered HTML (probed live 2026-11-09):

* ``ialist.html``                       — every current import alert, 4 columns:
  *Import Alert Number*, *Import Alert Type*, *Publish Date*, *Import Alert Name*
  (154 alerts at probe time);
* ``industrycategory.html``             — industry groups; the device group is
  ``industrygroup_9.html`` ("Medical Devices & Diagnostic Products"), which
  links 19 device industry sub-lists (``industry_73.html`` …);
* ``importalert_<id>.html``             — one alert, including the "Red List" of
  named foreign establishments (div-based markup, no ``<table>``).

Geometry matters
----------------
An import alert is an enforcement instruction about **foreign establishments or
product types**, not a company quality score.  The index exposes no company
column, so this connector never claims a firm-level link from the index; a
bounded text scan of individual alerts is reported as a text match only.

Time semantics
--------------
``source_public_at`` = the alert's *Publish Date* (or last-published date on the
sorted index).  ``event_at`` is left ``null``: the underlying inspection/violation
date is not published in the index.
"""

from __future__ import annotations

import re
from typing import Any, Mapping

from medradar.external_sources import identity as ev_identity
from medradar.external_sources.regulatory import postmarket_common as common

SOURCE_ID = "fda_import_alerts"
SOURCE_NAME = "FDA import alerts"
KIND = "import_alert"
LICENCE_STATUS = "public_domain"
INDEX_URL = "https://www.accessdata.fda.gov/cms_ia/ialist.html"
BY_DATE_URL = "https://www.accessdata.fda.gov/cms_ia/iapublishdate.html"
DEVICE_GROUP_URL = "https://www.accessdata.fda.gov/cms_ia/industrygroup_9.html"
DETAIL_URL_TEMPLATE = "https://www.accessdata.fda.gov/cms_ia/importalert_{alert_id}.html"
ATTRIBUTION = "U.S. Food and Drug Administration, Import Alerts database (public domain)"

INDEX_TABLE_HEADERS = ("Import Alert Number", "Import Alert Type", "Publish Date", "Import Alert Name")

INTERPRETATION_WARNING = common.IMPORT_ALERT_WARNING

_ALERT_ID_RE = re.compile(r"importalert_([0-9]+)\.html", re.I)


def _alert_id_from_href(href: str) -> str:
    match = _ALERT_ID_RE.search(href or "")
    return match.group(1) if match else ""


def parse_alert_index(html: str) -> list[dict[str, Any]]:
    """Pure parser for ``ialist.html`` / ``iapublishdate.html``."""
    tables = common.html_tables(html)
    table = common.find_table(tables, INDEX_TABLE_HEADERS)
    if table is None:
        return []
    headers = [str(h).strip() for h in table["headers"]]
    rows: list[dict[str, Any]] = []
    for row in table["rows"]:
        cells = row["cells"]
        if len(cells) < 4:
            continue
        item = dict(zip(headers, cells))
        hrefs = [href for cell_hrefs in row["hrefs"] for href in cell_hrefs]
        detail_href = next((href for href in hrefs if _ALERT_ID_RE.search(href)), "")
        alert_number = common.clip(item.get("Import Alert Number", ""), 40)
        if not alert_number:
            continue
        rows.append(
            {
                "alert_number": alert_number,
                "alert_type": common.clip(item.get("Import Alert Type", ""), 40),
                "publish_date": common.clip(item.get("Publish Date", ""), 40),
                "alert_name": common.clip(item.get("Import Alert Name", ""), 800),
                "detail_href": detail_href,
                "detail_id": _alert_id_from_href(detail_href) or alert_number.replace("-", ""),
            }
        )
    return rows


def parse_industry_links(html: str) -> list[dict[str, str]]:
    """Pure parser for an ``industrygroup_*`` page: industry name -> sub-list href."""
    tables = common.html_tables(html)
    out: list[dict[str, str]] = []
    for table in tables:
        for row in table["rows"]:
            names = row["cells"]
            hrefs = [href for cell_hrefs in row["hrefs"] for href in cell_hrefs]
            for index, name in enumerate(names):
                if not name:
                    continue
                href = hrefs[index] if index < len(hrefs) else ""
                out.append({"industry": common.clip(name, 120), "href": common.clip(href, 200)})
    return out


def _source_record_id(item: Mapping[str, Any]) -> str:
    return "import_alert_" + common.record_digest("import_alert", item.get("alert_number"))


def to_evidence(
    item: Mapping[str, Any],
    *,
    fetched_at: str,
    page_body: bytes,
    page_url: str = INDEX_URL,
    company_index: ev_identity.CompanyIndex | None = None,
) -> dict[str, Any]:
    """One import-alert index row -> one schema-v1 evidence record."""
    record_id = _source_record_id(item)
    alert_number = item.get("alert_number", "")
    publish_date = item.get("publish_date", "")
    normalized = {
        "record_type": "import_alert",
        "import_alert_number": alert_number,
        "import_alert_type": item.get("alert_type", ""),
        "import_alert_name": item.get("alert_name", ""),
        "publish_date": publish_date,
        "detail_url": (
            DETAIL_URL_TEMPLATE.format(alert_id=item.get("detail_id")) if item.get("detail_id") else ""
        ),
        # No company field exists in the index; the red list is per-alert and is
        # not part of this record.  Stated explicitly instead of left implicit.
        "firm_linkage": "not available from the index; red lists exist only inside each alert detail page",
        "interpretation_warning": INTERPRETATION_WARNING,
    }
    identifiers = [
        {
            "scheme": "import_alert_no",
            "value": str(alert_number),
            "raw_value": str(alert_number),
            "is_primary": True,
            "note": "FDA import alert number, e.g. 76-01",
        }
    ]
    time_block = common.clock_block(
        event_at=None,
        source_public_at=common.us_date_iso(publish_date),
        quality=common.date_quality(publish_date),
        fetched_at=fetched_at,
        notes=(
            "event_at is null: an import alert's underlying violation/inspection date is not "
            "published in the index. source_public_at = the alert's Publish Date."
        ),
    )
    return common.make_postmarket_evidence(
        source_id=SOURCE_ID,
        kind=KIND,
        source_record_id=record_id,
        source_url=page_url,
        normalized=normalized,
        raw=common.raw_block_from_page(page_body, path=f"{page_url}#{record_id}", media_type="text/html"),
        time=time_block,
        identifiers=identifiers,
        entity_refs=[],
        source_name=SOURCE_NAME,
        licence_status=LICENCE_STATUS,
        attribution=ATTRIBUTION,
        fetched_at=fetched_at,
    )


def parse_to_evidence(
    page_body: bytes,
    *,
    fetched_at: str,
    page_url: str = INDEX_URL,
    company_index: ev_identity.CompanyIndex | None = None,
) -> list[dict[str, Any]]:
    parsed = parse_alert_index(page_body.decode("utf-8", errors="replace"))
    return [
        to_evidence(
            item,
            fetched_at=fetched_at,
            page_body=page_body,
            page_url=page_url,
            company_index=company_index,
        )
        for item in parsed
    ]


def collect(
    client: Any,
    *,
    fetched_at: str = "",
    company_index: ev_identity.CompanyIndex | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Fetch ``ialist.html`` (one request) and normalise every alert row."""
    from medradar.external_sources import base as ev_base

    fetched = fetched_at or ev_base.utc_iso()
    result = client.get(INDEX_URL, accept="text/html")
    meta: dict[str, Any] = {"url": result.url, "status": result.status, "bytes": len(result.body), "error": result.error}
    if not result.ok:
        return [], meta
    records = parse_to_evidence(
        result.body, fetched_at=fetched, page_url=result.url, company_index=company_index
    )
    meta["records"] = len(records)
    return records, meta


def device_alert_subset(records: list[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    """Best-effort *documented* device subset, by alert-name keyword.

    The authoritative device subset is the official
    ``industrygroup_9.html`` -> ``industry_73..91`` hierarchy; this keyword
    filter is only used when those pages were not fetched, and it is labelled as
    a keyword filter wherever it is reported.
    """
    keywords = ("medical device", "medical instrument", "devices", "device", "catheter", "implant", "x-ray")
    out = []
    for record in records:
        name = str((record.get("normalized") or {}).get("import_alert_name", "")).lower()
        if any(keyword in name for keyword in keywords):
            out.append(record)
    return out


__all__ = [
    "BY_DATE_URL",
    "DETAIL_URL_TEMPLATE",
    "DEVICE_GROUP_URL",
    "INDEX_TABLE_HEADERS",
    "INDEX_URL",
    "INTERPRETATION_WARNING",
    "KIND",
    "LICENCE_STATUS",
    "SOURCE_ID",
    "SOURCE_NAME",
    "collect",
    "count_firm_tokens",
    "device_alert_subset",
    "parse_alert_index",
    "parse_industry_links",
    "parse_to_evidence",
    "to_evidence",
]

# Re-exported for callers that scan a red list without importing the common module.
count_firm_tokens = common.count_firm_tokens
