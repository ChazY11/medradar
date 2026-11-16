"""Typed source/status vocabulary and the official source catalogue."""
from __future__ import annotations

import urllib.parse
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class CheckStatus(str, Enum):
    NO_CHANGE = "NO_CHANGE"
    UPDATE_AVAILABLE = "UPDATE_AVAILABLE"
    CHECK_FAILED = "CHECK_FAILED"
    SOURCE_DEGRADED = "SOURCE_DEGRADED"
    UNKNOWN = "UNKNOWN"


class ChangeType(str, Enum):
    ADDED = "ADDED"
    UPDATED = "UPDATED"
    REMOVED_CONFIRMED = "REMOVED_CONFIRMED"
    UNCHANGED = "UNCHANGED"
    MISSING_ON_RECHECK = "MISSING_ON_RECHECK"
    UNRESOLVED = "UNRESOLVED"


class RecordState(str, Enum):
    ACTIVE = "ACTIVE"
    MISSING_ON_RECHECK = "MISSING_ON_RECHECK"
    QUERY_SCOPE_CHANGED = "QUERY_SCOPE_CHANGED"
    CONFIRMED_REMOVED = "CONFIRMED_REMOVED"
    UNKNOWN = "UNKNOWN"


class RunStatus(str, Enum):
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    PARTIAL = "PARTIAL"
    FAILED = "FAILED"
    NO_CHANGE = "NO_CHANGE"
    BLOCKED = "BLOCKED"
    #: DATA-003: the run refused to start a memory-heavy reconciliation because the host did not
    #: have the headroom. Nothing was collected, no source state advanced, and the next scheduled
    #: run retries. This is deliberately distinct from FAILED and from BLOCKED.
    DEFERRED = "DEFERRED"


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso_now() -> str:
    return utc_now().isoformat().replace("+00:00", "Z")


def parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


@dataclass(frozen=True)
class SourceSpec:
    source_id: str
    endpoint: str
    display_name: str
    event_types: tuple[str, ...]
    scope_field: str | None
    date_field: str
    check_interval_hours: int
    official_frequency: str
    licence: str
    note: str
    is_support_source: bool = False

    def official_url(self, official_id: str, raw: dict[str, Any] | None = None) -> str:
        raw = raw or {}
        if self.source_id == "openfda_510k":
            return "https://www.accessdata.fda.gov/scripts/cdrh/cfdocs/cfpmn/pmn.cfm?ID=" + urllib.parse.quote(official_id)
        if self.source_id == "openfda_pma":
            pma_number = str(raw.get("pma_number") or official_id.split(":")[0])
            url = "https://www.accessdata.fda.gov/scripts/cdrh/cfdocs/cfpma/pma.cfm?id=" + urllib.parse.quote(pma_number)
            supplement = str(raw.get("supplement_number") or "").strip()
            if supplement and supplement not in ("0", "-", "S000") and ":" in official_id:
                url += "&supplement_number=" + urllib.parse.quote(supplement)
            return url
        if self.source_id == "openfda_recall":
            event_number = str(raw.get("res_event_number") or "")
            if event_number:
                return "https://www.accessdata.fda.gov/scripts/cdrh/cfdocs/cfRes/res.cfm?id=" + urllib.parse.quote(event_number)
            return "https://www.accessdata.fda.gov/scripts/cdrh/cfdocs/cfRes/res.cfm"
        if self.source_id == "openfda_classification":
            return "https://www.accessdata.fda.gov/scripts/cdrh/cfdocs/cfPCD/classification.cfm"
        return "https://open.fda.gov/"

    def is_due(
        self, last_checked_at: str | None, now: datetime | None = None,
        *, last_status: str | None = None,
    ) -> bool:
        moment = now or utc_now()
        checked = parse_iso(last_checked_at)
        if checked is None:
            return True
        interval_hours = self.check_interval_hours
        # A failed/degraded check is retried hourly (up to the normal interval) rather than
        # waiting a full day to notice that the source recovered.
        if last_status in ("CHECK_FAILED", "SOURCE_DEGRADED"):
            interval_hours = min(interval_hours, 1)
        elapsed = moment - checked
        return elapsed.total_seconds() >= interval_hours * 3600


SOURCES: dict[str, SourceSpec] = {
    "openfda_510k": SourceSpec(
        source_id="openfda_510k",
        endpoint="/device/510k.json",
        display_name="FDA 510(k) premarket notifications",
        event_types=("510k",),
        scope_field="applicant",
        date_field="decision_date",
        check_interval_hours=24,
        official_frequency="Monthly (openFDA declared)",
        licence="Public domain / openFDA terms",
        note="OpenFDA exposes no publication timestamp for individual 510(k) records.",
    ),
    "openfda_pma": SourceSpec(
        source_id="openfda_pma",
        endpoint="/device/pma.json",
        display_name="FDA PMA approvals and supplements",
        event_types=("pma", "pma_supplement"),
        scope_field="applicant",
        date_field="decision_date",
        check_interval_hours=24,
        official_frequency="Monthly (openFDA declared)",
        licence="Public domain / openFDA terms",
        note="PMA originals and supplements share one official endpoint and one official update version.",
    ),
    "openfda_recall": SourceSpec(
        source_id="openfda_recall",
        endpoint="/device/recall.json",
        display_name="FDA device recall records",
        event_types=("recall",),
        scope_field="recalling_firm",
        date_field="event_date_posted",
        check_interval_hours=6,
        official_frequency="Weekly (openFDA declared)",
        licence="Public domain / openFDA terms",
        note="Recall records expose event_date_posted; that is a publication date, not a record revision timestamp.",
    ),
    "openfda_classification": SourceSpec(
        source_id="openfda_classification",
        endpoint="/device/classification.json",
        display_name="FDA device classification dictionary",
        event_types=(),
        scope_field=None,
        date_field="",
        check_interval_hours=24,
        official_frequency="Monthly (openFDA declared)",
        licence="Public domain / openFDA terms",
        note="Supporting product-code dictionary; it does not create product events.",
        is_support_source=True,
    ),
}

PRODUCT_SOURCE_IDS = ("openfda_510k", "openfda_pma", "openfda_recall")
ALL_SOURCE_IDS = tuple(SOURCES)

STATUS_LABELS = {
    CheckStatus.NO_CHANGE.value: "No new official version",
    CheckStatus.UPDATE_AVAILABLE.value: "Official update available",
    CheckStatus.CHECK_FAILED.value: "Check failed",
    CheckStatus.SOURCE_DEGRADED.value: "Source degraded; automatic sync blocked",
    CheckStatus.UNKNOWN.value: "No trustworthy baseline yet",
}
