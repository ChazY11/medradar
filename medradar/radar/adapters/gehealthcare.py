"""GE HealthCare official newsroom adapter - shipped, verified, and disabled.

The operator refuses anonymous automated access: both ``robots.txt`` and the newsroom page
return HTTP 403 "Access Denied" from an Akamai edge to a correctly identified client
(recorded in ``docs/radar/evidence/source_probe.json``).

This adapter exists so that the *absence of this source* is a first-class, visible product
state rather than a silent hole:

* it is registered and listed, so the UI can say "not monitored: access restricted";
* it is disabled, so the scheduler never requests it;
* if someone enables it anyway, ``fetch_page`` raises :class:`Refused` rather than trying a
  different header, a cookie jar or a proxy. A refusal is recorded, not circumvented.

GE HealthCare technology evidence still exists in MedRadar - through FDA clearances,
PubMed and Crossref. What is missing is only the vendor's own press releases, and the
product says exactly that.
"""

from __future__ import annotations

from ..adapter import CollectContext
from ..http import Refused
from ..records import MappingResult, Page, RawRecord, Scope

REFUSAL_MESSAGE = (
    "gehealthcare.com refuses anonymous automated access (HTTP 403 on robots.txt and on the "
    "newsroom). The adapter is disabled by policy; see docs/radar/evidence/source_probe.json."
)


class GEHealthCareAdapter:
    source_id = "gehealthcare_official"
    label = "GE HealthCare official newsroom"
    adapter_version = "radar-gehealthcare-1"
    declared_cadence_hours = 24.0
    record_types = ("press_release",)
    enabled = False
    access_state = "BLOCKED"
    access_reason = REFUSAL_MESSAGE

    def __init__(self, taxonomy) -> None:
        self.taxonomy = taxonomy

    def plan(self, ctx: CollectContext) -> list[Scope]:
        return []

    def fetch_page(self, ctx: CollectContext, scope: Scope, cursor: str | None) -> Page:
        raise Refused(REFUSAL_MESSAGE, url="https://www.gehealthcare.com/about/newsroom", status=403)

    def map_record(self, record: RawRecord, ctx: CollectContext) -> MappingResult:
        return MappingResult(note="no record can be collected while access is refused")
