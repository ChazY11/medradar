"""NIH RePORTER adapter - what American labs are being paid to build, years before a product.

Why this layer was empty everywhere else
----------------------------------------
No market-intelligence platform tracks federal research funding against device companies. They
track markets, shares and clearances. A grant awarded in FY2024 is the earliest public statement
that a technology direction is being funded, and it typically precedes a 510(k) by three to
seven years.

The join that makes it more than a list
---------------------------------------
RePORTER returns ``organization.primary_duns`` (and ``org_ueis``). That DUNS is the same key as
the UDI register's ``labeler_duns_number``. So:

    NIH award (primary_duns) -> UDI device (labeler_duns) -> 510(k) clearance

is a join, not a guess. An academic medical centre and a device maker share the identifier space,
so "who is funded to solve this problem" and "who cleared a device for it" become one query.

Time semantics
--------------
* ``award_notice_date`` - when the award was announced. Real public instant; this is ``event_at``
  **and** ``published_at``.
* ``project_start_date`` / ``project_end_date`` - the funded period, not the publication date.
  Recorded in the payload and never used as the event time.
* ``fiscal_year`` - the budget year, an administrative bucket. Never used as a date.

This is the second source in the repository (after Europe PMC) whose ``published_at`` is a real
instant rather than an assumption, which is why it is worth the extra adapter.

Transport note: RePORTER v2 is POST-only. See :meth:`medradar.radar.http.PoliteFetcher.post_json`.
"""

from __future__ import annotations

from datetime import date
from typing import Any, Iterable, Mapping, Sequence

POST_URL = "https://api.reporter.nih.gov/v2/projects/search"
PAGE_SIZE = 100
MAX_ROWS_PER_SCOPE = 5_000

#: Text queries per scope. RePORTER's ``advanced_text_search`` scans title, abstract and terms,
#: so a device word here finds the lab, not the marketing copy.
TERMS: tuple[Mapping[str, str], ...] = (
    {"id": "catheter", "text": "catheter"},
    {"id": "implant", "text": "implantable device"},
    {"id": "monitoring", "text": "physiological monitoring"},
    {"id": "ventilation", "text": "mechanical ventilation"},
    {"id": "stent", "text": "stent graft"},
    {"id": "surgical_robot", "text": "surgical robot"},
    {"id": "neuromodulation", "text": "neuromodulation"},
)

INCLUDE_FIELDS = [
    "ProjectNum", "ProjectTitle", "FiscalYear", "ProjectStartDate", "ProjectEndDate",
    "AwardNoticeDate", "Organization", "AwardAmount", "AgencyIcAdmin",
    "PrincipalInvestigators", "AbstractText", "ProjectDetailUrl",
]


class NihReporterAdapter:
    source_id = "nih_reporter"
    label = "NIH RePORTER (funded research, DUNS-linked)"
    adapter_version = "radar-nih-reporter-1"
    declared_cadence_hours = 168.0
    record_types = ("grant_award",)

    def __init__(self, taxonomy, *, terms: Iterable[Mapping[str, str]] | None = None,
                 fiscal_years: Sequence[int] | None = None,
                 page_size: int = PAGE_SIZE, max_rows: int = MAX_ROWS_PER_SCOPE) -> None:
        self.taxonomy = taxonomy
        self.terms = tuple(terms or TERMS)
        today = date.today()
        # A fiscal year runs Oct 1 - Sep 30. Two years back is enough to catch a newly noticed
        # award; older awards enter through an explicit backfill, not a scheduled cycle.
        self.fiscal_years = tuple(fiscal_years or (today.year - 1, today.year))
        self.page_size = min(int(page_size), 500)
        self.max_rows = int(max_rows)
        self._by_id = {str(term["id"]): term for term in self.terms}

    # --------------------------------------------------------------------- plan
    def plan(self, ctx) -> list:
        from ..adapter import Scope  # local import: adapter module owns the dataclass

        return [
            Scope(f"fy:{year}:{term['id']}", params={"fiscal_year": year, "term": term["id"]})
            for year in self.fiscal_years
            for term in self.terms
        ]

    # -------------------------------------------------------------------- fetch
    def fetch_page(self, ctx, scope, cursor: str | None):
        from ..records import Page

        parts = scope.scope_id.split(":")
        if len(parts) != 3 or parts[0] != "fy":
            raise ValueError(f"unknown NIH RePORTER scope {scope.scope_id!r}")
        year = int(parts[1])
        term = self._by_id.get(parts[2])
        if term is None:
            raise ValueError(f"unknown NIH RePORTER term {parts[2]!r}")
        offset = int(cursor or 0)
        if offset >= self.max_rows:
            return Page(records=[], next_cursor=None, watermark=date.today().isoformat(),
                        note=f"{scope.scope_id}: row cap {self.max_rows} reached")

        payload = {
            "criteria": {
                "fiscal_years": [year],
                "advanced_text_search": {
                    "operator": "and",
                    "search_field": "all",
                    "search_text": term["text"],
                },
            },
            "include_fields": INCLUDE_FIELDS,
            "offset": offset,
            "limit": self.page_size,
        }
        data = ctx.fetcher.post_json(POST_URL, payload, allow_not_found=True) or {}
        meta = data.get("meta") or {}
        total = int(meta.get("total") or 0)
        rows = [row for row in (data.get("results") or []) if isinstance(row, dict)]
        records = [record for row in rows if (record := _record(row))]
        advance = offset + len(rows)
        next_cursor = None
        if len(rows) >= self.page_size and advance < min(total, self.max_rows):
            next_cursor = str(advance)
        return Page(
            records=records,
            next_cursor=next_cursor,
            watermark=date.today().isoformat(),
            note=f"{scope.scope_id}: {len(rows)} of {total} projects",
        )

    # ------------------------------------------------------------------ mapping
    def map_record(self, record, ctx):
        from ..classify import RuleMapper

        return RuleMapper(self.taxonomy).map(record)


def _record(raw: Mapping[str, Any]) -> Any:
    from ..records import PRECISION_DATE, RawRecord, normalize_moment

    project_num = str(raw.get("project_num") or "").strip()
    title = " ".join(str(raw.get("project_title") or "").split())
    if not project_num or not title:
        return None

    organization = raw.get("organization") or {}
    org_name = " ".join(str(organization.get("org_name") or "").split())
    duns = str(organization.get("primary_duns") or "").strip() or None
    uei = str(organization.get("primary_uei") or "").strip() or None
    # RePORTER sometimes returns a list; the primary is the first declared value.
    if duns is None:
        duns_list = organization.get("org_duns") or []
        if isinstance(duns_list, list) and duns_list:
            duns = str(duns_list[0]).strip() or None

    notice = normalize_moment(raw.get("award_notice_date"))
    start = normalize_moment(raw.get("project_start_date"))
    abstract = " ".join(str(raw.get("abstract_text") or "").split())
    pIs = [
        " ".join(str(person.get("full_name") or "").split())
        for person in (raw.get("principal_investigators") or [])
        if isinstance(person, Mapping) and person.get("full_name")
    ]
    agency = raw.get("agency_ic_admin") or {}
    agency_name = str(agency.get("name") or agency.get("abbreviation") or "").strip()

    return RawRecord(
        source="nih_reporter",
        source_record_id=f"nih:{project_num}",
        official_identifier=project_num,
        record_type="grant_award",
        title=title[:400],
        url=_detail_url(raw, project_num),
        event_at=notice[0] or start[0],
        event_at_precision=notice[1] if notice[0] else start[1],
        # A real public instant: RePORTER publishes the notice date.
        published_at=notice[0] or start[0],
        published_at_precision=notice[1] if notice[0] else start[1],
        payload={
            "project_num": project_num,
            "fiscal_year": raw.get("fiscal_year"),
            "award_notice_date": raw.get("award_notice_date"),
            "project_start_date": raw.get("project_start_date"),
            "project_end_date": raw.get("project_end_date"),
            "award_amount": raw.get("award_amount"),
            "organization": org_name or None,
            "primary_duns": duns,
            "primary_uei": uei,
            "agency": agency_name or None,
            "principal_investigators": pIs,
        },
        text=" ".join(filter(None, [title, abstract]))[:12000],
        extra={
            "organization_hint": org_name or None,
            "organization_role": "grantee_organization",
            "duns": duns,
            "uei": uei,
            "product_codes": [],
            "official_identifier": project_num,
            "published_at_status": (
                "source_published_instant" if notice[0] else "not_published_by_source"
            ),
            "grant": {
                "agency": agency_name or None,
                "award_amount": raw.get("award_amount"),
                "fiscal_year": raw.get("fiscal_year"),
                "principal_investigators": pIs,
                "has_duns": bool(duns),
            },
        },
    )


def _detail_url(raw: Mapping[str, Any], project_num: str) -> str:
    detail = str(raw.get("project_detail_url") or "").strip()
    if detail:
        return detail
    return f"https://reporter.nih.gov/search/?projectNums={project_num}"


__all__ = ["INCLUDE_FIELDS", "NihReporterAdapter", "POST_URL", "TERMS"]
