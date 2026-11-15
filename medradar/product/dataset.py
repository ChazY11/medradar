"""Read-only product dataset over the collected openFDA snapshot.

The dataset is loaded once per process from medradar/product/snapshot/ and never mutated. Everything the
product shows is computed here: attribution (via medradar.product.identity), categorisation,
counting, coverage and data-quality states. The API layer is a thin projection of this module.

Design rules:
* attributed records are the only thing that counts as an organization's activity;
* unattributed / rejected records stay visible in coverage and audit data;
* every aggregate carries its basis (event types summed, window, organizations, snapshot);
* a missing value is None, never 0.
"""
from __future__ import annotations

import gzip
import json
import sys
import threading
from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Iterator, Sequence

from .attribution import ownership as ownership_module
from .attribution import status as status_module
from .identity import (
    Decision,
    Rejection,
    Registry,
    normalise_applicant,
    registry_with_overlay,
)

#: review= filter values accepted by filter_events / the API.
REVIEW_FILTERS = {
    "any": "no filter",
    "curated": "records whose mapping is evidence-verified or human-reviewed",
    "verified": "same as curated (explicit alias)",
    "rule_verified": "records whose mapping is justified by a deterministic rule",
    "provisional": "records whose mapping is neither evidence-verified nor human-reviewed",
    "pending_review": "legacy alias for provisional",
    "unverified": "records whose mapping has no rule and no evidence",
}

#: ownership basis accepted by filters and the comparison.
OWNERSHIP_BASES = {
    "current_group": "count every record attributed to the organization today, including acquired predecessor entities",
    "original_registrant": "count only records filed under the organization's own applicant identities, excluding acquired predecessor entities",
}

ROOT = Path(__file__).resolve().parents[2]


def default_data_dir() -> Path:
    """Snapshot directory.

    The collected snapshot is vendored package data (medradar/product/snapshot/), not raw
    runtime data: it ships in the wheel and is hash-addressed in its manifest. MEDRADAR_DATA_DIR
    can point the product at another snapshot (for example a fresh collection being reviewed).
    """
    import os

    override = os.environ.get("MEDRADAR_DATA_DIR")
    candidates = [
        Path(override) if override else None,
        Path(__file__).with_name("snapshot"),
        ROOT / "data" / "product",
    ]
    candidates = [candidate for candidate in candidates if candidate is not None]
    for candidate in candidates:
        if (candidate / "snapshot.json").exists():
            return candidate
    return candidates[1] if len(candidates) > 1 else candidates[0]


DEFAULT_DATA_DIR = default_data_dir()

PRODUCT_NAME = "MedRadar"
PRODUCT_VERSION = "2.0.0-product-002"
PRODUCT_POSITIONING_EN = (
    "Medical technology intelligence: traceable FDA regulatory records for the companies you "
    "compete with, with the identity and time limits stated on every screen."
)
PRODUCT_POSITIONING_ZH = (
    "医疗技术情报平台：以可追溯的 FDA 监管记录为核心，比较目标企业的监管活动，并在每个页面上明确标注身份归属与时间语义的边界。"
)

SOURCE_NAMES = {
    "openfda_510k": "FDA 510(k) premarket notifications",
    "openfda_pma": "FDA premarket approval (PMA) decisions",
    "openfda_recall": "FDA device recall records",
}

EVENT_TYPE_LABELS = {
    "510k": "510(k) clearance",
    "pma": "PMA original approval",
    "pma_supplement": "PMA supplement",
    "recall": "Recall",
}
EVENT_TYPE_ORDER = ("510k", "pma", "pma_supplement", "recall")

SOURCE_OFFICIAL_BASE = {
    "openfda_510k": "https://www.accessdata.fda.gov/scripts/cdrh/cfdocs/cfpmn/pmn.cfm",
    "openfda_pma": "https://www.accessdata.fda.gov/scripts/cdrh/cfdocs/cfpma/pma.cfm",
    "openfda_recall": "https://www.accessdata.fda.gov/scripts/cdrh/cfdocs/cfRes/res.cfm",
}

FRESHNESS_THRESHOLD_DAYS = 30

TIME_SEMANTICS = [
    {"field": "event_date", "meaning": "When the regulatory event happened: the FDA decision date for 510(k)/PMA, the firm's recall initiation date for recalls."},
    {"field": "published_at", "meaning": "When the source published the record, only when the source states it (recalls: FDA posting date). openFDA states no publication time for 510(k)/PMA, so it is null there."},
    {"field": "first_observed_at", "meaning": "When MedRadar first ingested the record. This is the snapshot collection time, not the date the event became public."},
    {"field": "available_at", "meaning": "Conservative lower bound of availability: published_at when known, otherwise first_observed_at."},
    {"field": "record_updated_at", "meaning": "The source's own last-updated marker when exposed by the API, otherwise null."},
]

OUT_OF_SCOPE = [
    {"item": "De Novo classification requests", "reason": "openFDA exposes no De Novo endpoint; not collected in this release."},
    {"item": "NMPA / China registrations", "reason": "The source blocks automated access (HTTP 412 / JavaScript challenge). Not collected."},
    {"item": "EU MDR / CE marks, UDI, establishment registrations", "reason": "Not part of the PRODUCT-001 snapshot."},
    {"item": "Clinical trials, financial filings, patents, hiring signals", "reason": "Research-module sources; not part of the product snapshot."},
    {"item": "Applicant names not in the reviewed registry", "reason": "Shown in the attribution audit; never counted as a tracked organization's activity."},
]


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


def slugify(value: str) -> str:
    text = "".join(ch if ch.isalnum() else "-" for ch in value.strip().casefold())
    while "--" in text:
        text = text.replace("--", "-")
    return text.strip("-") or "unclassified"


@dataclass(frozen=True)
class Category:
    id: str
    label: str

    def to_public(self) -> dict[str, str]:
        return {"id": self.id, "label": self.label}


@dataclass
class Event:
    event_id: str
    official_id: str
    source_id: str
    event_type: str
    event_date: str | None
    published_at: str | None
    published_at_status: str
    first_observed_at: str
    available_at: str
    record_updated_at: str | None
    time_quality: str
    organization_key: str | None
    organization_name: str | None
    applicant_name: str
    attribution_status: str
    attribution_basis: str | None
    attribution_review: str | None
    product_code: str | None
    category: Category | None
    device_class: str | None
    device_name: str | None
    title: str
    summary: str | None
    official_url: str
    raw: dict[str, Any]
    # PRODUCT-002 verification fields: the claim each record's attribution supports.
    attribution_verification: str = status_module.PROPOSED
    attribution_verified: bool = False
    attribution_rule: str | None = None
    attribution_evidence_count: int = 0
    attribution_reviewer: str | None = None
    attribution_reviewer_kind: str | None = None
    attribution_provenance: str | None = None
    attribution_is_predecessor: bool = False

    @property
    def year(self) -> str | None:
        return self.event_date[:4] if self.event_date else None

    def to_public(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "official_id": self.official_id,
            "source_id": self.source_id,
            "source_name": SOURCE_NAMES.get(self.source_id, self.source_id),
            "event_type": self.event_type,
            "event_date": self.event_date,
            "published_at": self.published_at,
            "published_at_status": self.published_at_status,
            "first_observed_at": self.first_observed_at,
            "available_at": self.available_at,
            "record_updated_at": self.record_updated_at,
            "time_quality": self.time_quality,
            "organization_key": self.organization_key,
            "organization_name": self.organization_name,
            "applicant_name": self.applicant_name,
            "attribution": {
                "status": self.attribution_status,
                "basis": self.attribution_basis,
                "review": self.attribution_review,
                "verification": self.attribution_verification,
                "verification_label_en": status_module.STATUS_LABELS_EN.get(self.attribution_verification, self.attribution_verification),
                "verification_label_zh": status_module.STATUS_LABELS_ZH.get(self.attribution_verification, self.attribution_verification),
                "verified": self.attribution_verified,
                "rule": self.attribution_rule,
                "evidence_count": self.attribution_evidence_count,
                "reviewer": self.attribution_reviewer,
                "reviewer_kind": self.attribution_reviewer_kind,
                "provenance": self.attribution_provenance,
                "predecessor_entity": self.attribution_is_predecessor,
            },
            "product_code": self.product_code,
            "category": self.category.to_public() if self.category else None,
            "device_class": self.device_class,
            "device_name": self.device_name,
            "title": self.title,
            "summary": self.summary,
            "official_url": self.official_url,
        }


UNATTRIBUTED = "unattributed"


def _matches_review(event: "Event", review: str) -> bool:
    """Semantics of the review= filter.

    curated/verified .... mapping is evidence-verified or human-reviewed (the only "curated" claim)
    rule_verified ....... mapping is justified by a deterministic rule
    provisional ......... mapping is not independently verified (rule-verified counts as provisional)
    unverified .......... mapping has neither a rule nor evidence
    """
    if review in ("curated", "verified"):
        return bool(event.attribution_verified)
    if review == "rule_verified":
        return event.attribution_verification == status_module.RULE_VERIFIED
    if review in ("provisional", "pending_review"):
        return not event.attribution_verified
    if review == "unverified":
        return event.attribution_verification in status_module.PROVISIONAL_STATUSES
    return True


def empty_counts() -> dict[str, Any]:
    return {
        "records": 0,
        "dated": 0,
        "undated": 0,
        "unmapped_category": 0,
        "pending_review": 0,
        "provisional": 0,
        "verified_records": 0,
        "rule_verified_records": 0,
        "curated_share": None,
        "rule_verified_share": None,
        "provisional_share": None,
        "by_verification": {},
        "by_source": [],
        "by_type": [],
    }


def aggregate(events: Sequence[Event]) -> dict[str, Any]:
    """Aggregations over an explicit event sequence. Sparse: empty years are not invented."""
    by_year: dict[str, dict[str, int]] = {}
    by_type: dict[str, int] = {}
    by_category: dict[str, dict[str, Any]] = {}
    by_class: dict[str, int] = {"1": 0, "2": 0, "3": 0, "unknown": 0}
    undated = 0
    for event in events:
        by_type[event.event_type] = by_type.get(event.event_type, 0) + 1
        class_key = event.device_class if event.device_class in ("1", "2", "3") else "unknown"
        by_class[class_key] = by_class.get(class_key, 0) + 1
        category_id = event.category.id if event.category else "unclassified"
        label = event.category.label if event.category else "Unclassified (product code not in the FDA dictionary)"
        bucket = by_category.setdefault(category_id, {"id": category_id, "label": label, "counts": {}, "total": 0})
        bucket["counts"][event.event_type] = bucket["counts"].get(event.event_type, 0) + 1
        bucket["total"] += 1
        if event.year:
            year_bucket = by_year.setdefault(event.year, {})
            year_bucket[event.event_type] = year_bucket.get(event.event_type, 0) + 1
        else:
            undated += 1
    year_rows = []
    for year in sorted(by_year):
        counts = {event_type: by_year[year].get(event_type, 0) for event_type in EVENT_TYPE_ORDER}
        year_rows.append({"year": year, "counts": counts, "total": sum(counts.values())})
    category_rows = sorted(by_category.values(), key=lambda row: (-row["total"], row["label"]))
    for row in category_rows:
        row["counts"] = {event_type: row["counts"].get(event_type, 0) for event_type in EVENT_TYPE_ORDER}
    return {
        "by_year": year_rows,
        "by_type": [
            {"event_type": event_type, "count": by_type.get(event_type, 0)}
            for event_type in EVENT_TYPE_ORDER
            if by_type.get(event_type, 0)
        ],
        "by_category": category_rows,
        "by_class": [{"device_class": key, "count": by_class[key]} for key in ("1", "2", "3", "unknown")],
        "undated_records": undated,
    }


@dataclass
class OrgStats:
    key: str
    counts: dict[str, Any]
    aggregations: dict[str, Any]
    window: dict[str, Any]
    sources: list[dict[str, Any]]
    recent_events: list[dict[str, Any]]
    first_observed_at: str | None
    pending_review_records: int
    unattributed_in_scope: int
    rejected_in_scope: int
    verified_records: int = 0
    rule_verified_records: int = 0
    proposed_records: int = 0
    predecessor_records: int = 0
    original_registrant_records: int = 0
    status_counts: dict[str, int] = field(default_factory=dict)


@dataclass
class Dataset:
    data_dir: Path
    manifest: dict[str, Any]
    events: list[Event]
    events_by_id: dict[str, Event]
    applicants: list[dict[str, Any]]
    categories: list[Category]
    registry: Registry
    org_stats: dict[str, OrgStats]
    global_counts: dict[str, Any]
    global_aggregations: dict[str, Any]
    global_by_type: dict[str, int] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    applicant_by_name: dict[str, dict[str, Any]] = field(default_factory=dict)
    review_overlay_applied: int = 0
    review_db: str | None = None
    _org_events: dict[str, list[Event]] = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    # ------------------------------------------------------------------ meta
    @property
    def snapshot_id(self) -> str:
        return str(self.manifest.get("id") or "unknown")

    @property
    def collected_at(self) -> str:
        return str(self.manifest.get("collected_at") or "")

    def snapshot_ref(self) -> dict[str, Any]:
        files = self.manifest.get("files") or {}
        return {
            "id": self.snapshot_id,
            "collected_at": self.collected_at,
            "openfda_last_updated": (self.manifest.get("openfda") or {}).get("last_updated"),
            "file_sha256": {name: str(meta.get("sha256") or "") for name, meta in files.items()},
            "note": "Immutable openFDA snapshot. Attribution and time limits are stated per record.",
        }

    def freshness(self) -> dict[str, Any]:
        collected = self.manifest.get("collected_at")
        if not collected:
            return {"state": "unknown", "age_days": None, "threshold_days": FRESHNESS_THRESHOLD_DAYS, "collected_at": None}
        try:
            moment = datetime.fromisoformat(str(collected).replace("Z", "+00:00"))
        except ValueError:
            return {"state": "unknown", "age_days": None, "threshold_days": FRESHNESS_THRESHOLD_DAYS, "collected_at": collected}
        age = (datetime.now(timezone.utc) - moment).days
        return {
            "state": "fresh" if age <= FRESHNESS_THRESHOLD_DAYS else "stale",
            "age_days": age,
            "threshold_days": FRESHNESS_THRESHOLD_DAYS,
            "collected_at": collected,
        }

    # ------------------------------------------------------------------ lookups
    def organization(self, key: str):
        return self.registry.organization(key)

    def resolve_event(self, identifier: str) -> Event | None:
        """Resolve an event by full event id or by the official FDA identifier.

        Official identifiers are what a user sees and what appears on the FDA page, so a deep
        link such as /events/K231234 must work. If an official identifier is ambiguous across
        sources, only the full event id resolves; the API then returns a not-found rather than
        guessing which record the user meant.
        """
        direct = self.events_by_id.get(identifier)
        if direct is not None:
            return direct
        matches = [event for event in self.events if event.official_id == identifier]
        if len(matches) == 1:
            return matches[0]
        return None

    def org_events(self, key: str) -> list[Event]:
        return self._org_events.get(key, [])

    def events_for_org(self, key: str) -> list[Event]:
        return self._org_events.get(key, [])

    def basis(self, events: Sequence[Event], event_types: Sequence[str] | None = None, window: dict[str, Any] | None = None, rule: str = "") -> dict[str, Any]:
        return {
            "event_types": list(event_types or EVENT_TYPE_ORDER),
            "window": window or {"from": None, "to": None},
            "org_keys": sorted({event.organization_key for event in events if event.organization_key}),
            "snapshot_id": self.snapshot_id,
            "rule": rule or "Count of attributed regulatory records; one record is one row in the source dataset.",
        }

    def counts(self, events: Sequence[Event]) -> dict[str, Any]:
        by_source: dict[str, int] = {}
        by_type: dict[str, int] = {}
        by_verification: dict[str, int] = {}
        dated = undated = unmapped = verified = rule_verified = provisional = 0
        for event in events:
            by_source[event.source_id] = by_source.get(event.source_id, 0) + 1
            by_type[event.event_type] = by_type.get(event.event_type, 0) + 1
            if event.event_date:
                dated += 1
            else:
                undated += 1
            if event.category is None:
                unmapped += 1
            verification = event.attribution_verification
            by_verification[verification] = by_verification.get(verification, 0) + 1
            if event.attribution_verified:
                verified += 1
            elif verification == status_module.RULE_VERIFIED:
                rule_verified += 1
            else:
                provisional += 1
        total = len(events)
        # A share of nothing is UNKNOWN, never 0.0: the product must not show "0% verified"
        # for an organization that has no attributed records at all.
        return {
            "records": total,
            "dated": dated,
            "undated": undated,
            "unmapped_category": unmapped,
            "pending_review": provisional + rule_verified,
            "provisional": provisional,
            "verified_records": verified,
            "rule_verified_records": rule_verified,
            "curated_share": round(verified / total, 6) if total else None,
            "rule_verified_share": round(rule_verified / total, 6) if total else None,
            "provisional_share": round(provisional / total, 6) if total else None,
            "by_verification": {name: count for name, count in sorted(by_verification.items())},
            "by_source": [
                {"source_id": source_id, "count": by_source[source_id]}
                for source_id in SOURCES_ORDER
                if by_source.get(source_id)
            ],
            "by_type": [
                {"event_type": event_type, "count": by_type[event_type]}
                for event_type in EVENT_TYPE_ORDER
                if by_type.get(event_type)
            ],
        }

    # ------------------------------------------------------------------ queries
    def filter_events(
        self,
        *,
        org_keys: Iterable[str] | None = None,
        event_types: Iterable[str] | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
        categories: Iterable[str] | None = None,
        query: str | None = None,
        review: str | None = None,
        basis: str | None = None,
    ) -> list[Event]:
        pools: list[Event]
        if org_keys:
            keys = list(org_keys)
            merged: list[Event] = []
            for key in keys:
                merged.extend(self._org_events.get(key, []))
            pools = merged
        else:
            pools = [event for event in self.events if event.organization_key]
        type_set = {item for item in event_types or [] if item}
        from_date = _parse_date(date_from)
        to_date = _parse_date(date_to)
        category_set = {item for item in categories or [] if item}
        needle = (query or "").strip().casefold()
        review = (review or "").strip() or None
        if review == "any":
            review = None
        if review and review not in REVIEW_FILTERS:
            raise ValueError("unknown review filter: " + review + "; expected one of " + ", ".join(REVIEW_FILTERS))
        basis = (basis or "").strip() or None
        if basis and basis not in OWNERSHIP_BASES:
            raise ValueError("unknown ownership basis: " + basis + "; expected one of " + ", ".join(OWNERSHIP_BASES))
        out: list[Event] = []
        for event in pools:
            if type_set and event.event_type not in type_set:
                continue
            if from_date or to_date:
                if event.event_date is None:
                    continue
                moment = _parse_date(event.event_date)
                if moment is None:
                    continue
                if from_date and moment < from_date:
                    continue
                if to_date and moment > to_date:
                    continue
            if category_set:
                category_id = event.category.id if event.category else "unclassified"
                if category_id not in category_set:
                    continue
            if review is not None and not _matches_review(event, review):
                continue
            if basis == "original_registrant" and event.attribution_is_predecessor:
                continue
            if needle:
                haystack = " ".join(
                    item for item in (event.device_name, event.applicant_name, event.official_id, event.title, event.product_code) if item
                ).casefold()
                if needle not in haystack:
                    continue
            out.append(event)
        return out

    def sort_events(self, events: list[Event], sort: str) -> list[Event]:
        if sort == "event_date_asc":
            return sorted(events, key=lambda event: (event.event_date is None, event.event_date or "", event.event_id))
        if sort == "official_id_asc":
            return sorted(events, key=lambda event: (event.official_id or "", event.event_id))
        return sorted(events, key=lambda event: (event.event_date is None, -(int(event.event_date.replace("-", "")) if event.event_date else 0), event.event_id))

    def search(self, query: str, limit: int = 8) -> dict[str, Any]:
        from .identity import search_organizations

        started = datetime.now(timezone.utc)
        hits, applicant_only = search_organizations(query, (row["applicant_name"] for row in self.applicants))
        names = [row["applicant_name"] for row in self.applicants]
        results = []
        for hit in hits[:limit]:
            stats = self.org_stats.get(hit.organization.key)
            window = stats.window if stats else {"from": None, "to": None}
            results.append({
                "key": hit.organization.key,
                "display_name": hit.organization.display_name,
                "legal_name": hit.organization.legal_name,
                "ticker": hit.organization.ticker,
                "country": hit.organization.country,
                "organization_type": hit.organization.organization_type,
                "event_count": stats.counts["records"] if stats else 0,
                "event_range": window,
                "match": {"field": hit.match_field, "value": hit.match_value},
                "ambiguous_name": self._ambiguous(hit.organization.key),
            })
        unmatched = []
        for name in applicant_only[:10]:
            row = self.applicant_by_name.get(name) or {}
            unmatched.append({
                "applicant_name": name,
                "record_count": int(row.get("records") or 0),
                "note": "not attributed to a tracked organization",
            })
        took = (datetime.now(timezone.utc) - started).total_seconds() * 1000.0
        return {
            "query": query,
            "results": results,
            "applicant_matches": unmatched,
            "coverage": {
                "tracked_organizations": len(self.registry.organizations),
                "note": "Search covers the tracked organizations in this snapshot; it is not a full FDA applicant registry.",
            },
            "took_ms": round(took, 1),
        }

    def _ambiguous(self, key: str) -> bool:
        """True when another tracked organization shares a distinctive applicant token.

        The product surfaces this as "distinct legal entities - verify before aggregation" rather
        than merging them.
        """
        tokens = {token.casefold() for token in (self.registry.by_key[key].search_tokens if key in self.registry.by_key else ()) if len(token) > 5}
        for other in self.registry.organizations:
            if other.key == key:
                continue
            other_tokens = {token.casefold() for token in other.search_tokens if len(token) > 5}
            if tokens & other_tokens:
                return True
        return False

    # ------------------------------------------------------------------ public payloads
    def meta(self) -> dict[str, Any]:
        return {
            "product": {
                "name": PRODUCT_NAME,
                "version": PRODUCT_VERSION,
                "positioning_en": PRODUCT_POSITIONING_EN,
                "positioning_zh": PRODUCT_POSITIONING_ZH,
            },
            "snapshot": self.snapshot_ref(),
            "freshness": self.freshness(),
            "sources": self.sources(),
            "out_of_scope": OUT_OF_SCOPE,
            "event_types": [
                {"event_type": event_type, "label": EVENT_TYPE_LABELS[event_type],
                 "note": {
                     "510k": "Original 510(k) clearances returned by the FDA 510(k) endpoint.",
                     "pma": "Original PMA approvals only; supplements are counted separately.",
                     "pma_supplement": "Changes to an approved PMA device. Not a new device and never counted as one.",
                     "recall": "Recall records. A safety action, not evidence of product technology.",
                 }[event_type]}
                for event_type in EVENT_TYPE_ORDER
            ],
            "categories": [category.to_public() for category in self.categories],
            "coverage": {
                "tracked_organizations": len(self.registry.organizations),
                "total_records": len(self.events),
                "attributed_records": self.global_counts["records"],
                "unattributed_records": len(self.events) - self.global_counts["records"],
                "earliest_event_date": self.manifest.get("coverage", {}).get("min_event_date"),
                "latest_event_date": self.manifest.get("coverage", {}).get("max_event_date"),
            },
            "metric_definitions": status_module.metric_definitions(),
            "metrics": self.metrics_summary(),
            "ownership": {
                "verified_relations": sum(1 for relation in ownership_module.ownership().relations if relation.verified),
                "unresolved_relations": sum(1 for relation in ownership_module.ownership().relations if not relation.verified),
                "policy": "Counts use CURRENT GROUP attribution unless a caller selects the original-registrant basis. Historical owners are only stated where an independent filing with an effective date is recorded.",
                "updated_at": ownership_module.ownership().updated_at,
            },
            "review_ledger": {
                "decisions_applied": self.review_overlay_applied,
                "db": self.review_db,
                "note": "Internal identity review decisions are applied to every count on this page. Writes are only possible through the loopback-bound admin service.",
            },
            "time_semantics": TIME_SEMANTICS,
            "limitations": self.limitations(),
            "methodology_url": "/sources",
            "registry_updated_at": self.registry.updated_at,
        }

    def sources(self) -> list[dict[str, Any]]:
        files = self.manifest.get("files") or {}
        by_source = (self.manifest.get("counts") or {}).get("by_source") or {}
        organization_queries = self.manifest.get("organizations") or []
        endpoint_map: dict[str, set[str]] = {}
        collected_map: dict[str, int] = {}
        for entry in organization_queries:
            for query in entry.get("queries") or []:
                source_id = query.get("source_id")
                if not source_id:
                    continue
                collected_map[source_id] = collected_map.get(source_id, 0) + int(query.get("records") or 0)
                for url in query.get("urls") or []:
                    endpoint_map.setdefault(source_id, set()).add(url.split("?")[0])
        rows = []
        for source_id in SOURCES_ORDER:
            dates = [event.event_date for event in self.events if event.source_id == source_id and event.event_date]
            endpoints = sorted(endpoint_map.get(source_id, set())) or ["https://api.fda.gov" + {
                "openfda_510k": "/device/510k.json",
                "openfda_pma": "/device/pma.json",
                "openfda_recall": "/device/recall.json",
            }[source_id]]
            rows.append({
                "source_id": source_id,
                "name": SOURCE_NAMES[source_id],
                "official_base_url": SOURCE_OFFICIAL_BASE[source_id],
                "endpoints": endpoints,
                "queried_endpoints": endpoints,
                "licence": "public domain (openFDA)",
                "collected": source_id in by_source,
                "records": int(by_source.get(source_id) or 0),
                "min_event_date": min(dates) if dates else None,
                "max_event_date": max(dates) if dates else None,
                "collected_at": self.collected_at,
                "note": {
                    "openfda_510k": "No publication timestamp in the source; published_at is null.",
                    "openfda_pma": "Includes PMA supplements; originals and supplements are counted as different event types.",
                    "openfda_recall": "event_date uses recall initiation; published_at uses the FDA posting date.",
                }[source_id],
            })
        rows.append({
            "source_id": "openfda_classification",
            "name": "FDA device classification (product code dictionary)",
            "official_base_url": "https://www.accessdata.fda.gov/scripts/cdrh/cfdocs/cfPCD/classification.cfm",
            "licence": "public domain (openFDA)",
            "collected": bool(files.get("classifications.jsonl.gz")),
            "records": int((self.manifest.get("counts") or {}).get("product_codes") or 0),
            "endpoints": ["https://api.fda.gov/device/classification.json"],
            "queried_endpoints": ["https://api.fda.gov/device/classification.json"],
            "min_event_date": None,
            "max_event_date": None,
            "collected_at": self.collected_at,
            "note": "Used to map product codes to the FDA medical specialty shown as category.",
        })
        return rows

    def limitations(self) -> list[str]:
        items = [
            "Snapshot-based: the system shows data as collected at the snapshot timestamp, never a live feed.",
            "510(k) and PMA records expose no publication timestamp in openFDA; the product never infers one.",
            "Applicant attribution is exact-string against a reviewed registry; unattributed records are visible in the audit, not hidden.",
            "Counts are regulatory records, not products, devices or innovations. Records are not comparable across event types.",
            "Coverage is limited to the tracked organizations in the registry and to the sources listed on the sources page.",
        ]
        items.extend(
            org.display_name
            + ": "
            + str(self.org_stats[org.key].proposed_records)
            + " attributed record(s) rest on mappings with no independent verification (provisional attribution)."
            for org in self.registry.organizations
            if org.key in self.org_stats and self.org_stats[org.key].proposed_records
        )
        return items

    def organizations_payload(self) -> dict[str, Any]:
        rows = []
        for org in sorted(self.registry.organizations, key=lambda item: (not item.featured, item.display_name.casefold())):
            stats = self.org_stats.get(org.key)
            rows.append({
                "key": org.key,
                "display_name": org.display_name,
                "legal_name": org.legal_name,
                "ticker": org.ticker,
                "country": org.country,
                "organization_type": org.organization_type,
                "featured": org.featured,
                "event_count": stats.counts["records"] if stats else 0,
                "event_range": stats.window if stats else {"from": None, "to": None},
                "attribution_review": org.registry_review,
                "verified_records": stats.verified_records if stats else 0,
                "rule_verified_records": stats.rule_verified_records if stats else 0,
                "provisional_records": stats.proposed_records if stats else 0,
                "curated_share": stats.counts["curated_share"] if stats else None,
            })
        return {
            "organizations": rows,
            "total": len(rows),
            "note": "Tracked organizations in this snapshot. Each row carries the verification state of the mappings behind its counts; curated_share is null when the organization has no attributed records.",
        }

    def organization_profile(self, key: str) -> dict[str, Any]:
        org = self.registry.organization(key)
        if org is None:
            raise KeyError(key)
        stats = self.org_stats.get(key) or _empty_org_stats(key)
        decisions = list(self.registry.accepted_spellings_by_org.get(key, ()))
        pending_decisions = [item for item in decisions if item.provisional]
        examples = []
        for decision in decisions:
            row = self.applicant_by_name.get(decision.applicant_name) or {}
            examples.append({
                "applicant_name": decision.applicant_name,
                "basis": decision.basis,
                "basis_label": decision.to_public()["basis_label"],
                "review": decision.review,
                "status": decision.status,
                "status_label_en": decision.to_public()["status_label_en"],
                "verified": decision.verified,
                "rule": decision.rule,
                "evidence_count": len(decision.evidence),
                "decision_uid": decision.decision_uid,
                "reviewer": decision.reviewer,
                "reviewer_kind": decision.reviewer_kind,
                "record_count": int(row.get("records") or 0),
            })
        examples.sort(key=lambda item: -item["record_count"])
        top_examples = examples[:12]
        status_counts: dict[str, int] = {}
        for decision in decisions:
            status_counts[decision.status] = status_counts.get(decision.status, 0) + 1
        return {
            "key": org.key,
            "display_name": org.display_name,
            "display_name_zh": org.display_name_zh,
            "legal_name": org.legal_name,
            "ticker": org.ticker,
            "exchange": org.exchange,
            "country": org.country,
            "country_name": org.country_name,
            "organization_type": org.organization_type,
            "description": org.description,
            "registry": {
                "review_status": org.registry_review,
                "metadata_source": org.metadata_source,
                "updated_at": self.registry.updated_at,
                "attribution_note": (
                    "Applicant attribution uses exact spelling matches from the reviewed registry. "
                    "Strings that are not accepted are counted in the audit, never folded into this organization."
                ),
            },
            "ownership": ownership_module.organization_ownership_summary(key, events=self.org_events(key)),
            "verification": {
                "definition": "Verification status of the applicant mappings that produced the counts on this page. Curated means evidence-verified or human-reviewed; a deterministic rule is reported separately and is NOT review.",
                "attributed_records": stats.counts["records"],
                "verified_records": stats.verified_records,
                "rule_verified_records": stats.rule_verified_records,
                "provisional_records": stats.proposed_records,
                "curated_share": stats.counts["curated_share"],
                "rule_verified_share": stats.counts["rule_verified_share"],
                "provisional_share": stats.counts["provisional_share"],
                "by_status": stats.status_counts,
                "accepted_spellings": len(decisions),
                "verified_spellings": sum(1 for item in decisions if item.verified),
                "rule_verified_spellings": sum(1 for item in decisions if item.rule_verified),
                "provisional_spellings": len(pending_decisions),
                "status_counts_spellings": status_counts,
                "human_reviewed_spellings": sum(1 for item in decisions if item.status == "human_reviewed"),
                "risk_note": (
                    "This organization's counts depend on mappings that are not independently verified."
                    if stats.proposed_records
                    else "Every mapping behind these counts is rule-verified or better."
                ),
            },
            "attribution": {
                "accepted_spellings": len([item for item in decisions if item.verified]),
                "pending_review_spellings": len(pending_decisions),
                "rejected_spellings": [
                    {"applicant_name": rejection.applicant_name, "reason": rejection.reason}
                    for rejection in org.reject_exact
                ],
                "unattributed_in_scope": stats.unattributed_in_scope,
                "examples": top_examples,
            },
            "coverage": {
                "window": stats.window,
                "sources": stats.sources,
            },
            "counts": stats.counts,
            "aggregations": stats.aggregations,
            "recent_events": stats.recent_events,
            "data_quality_notes": self._org_quality_notes(org, stats),
            "basis": self.basis(self.org_events(key), rule="Count of records attributed to this organization by exact applicant spelling."),
            "snapshot": self.snapshot_ref(),
            "freshness": self.freshness(),
        }

    def _org_quality_notes(self, org, stats: OrgStats) -> list[str]:
        notes: list[str] = []
        if stats.counts["records"] == 0:
            notes.append("No records were attributed to this organization in the snapshot. This is a coverage statement, not evidence that the company had no regulatory activity.")
        if stats.pending_review_records:
            notes.append(str(stats.pending_review_records) + " attributed record(s) come from applicant spellings whose attribution is pending human review.")
        if stats.unattributed_in_scope:
            notes.append(str(stats.unattributed_in_scope) + " record(s) were retrieved within this organization's search scope but could not be attributed; see the attribution audit.")
        if stats.rejected_in_scope:
            notes.append(str(stats.rejected_in_scope) + " record(s) matched a rejected applicant spelling (a different business) and are excluded.")
        if stats.counts["undated"]:
            notes.append(str(stats.counts["undated"]) + " record(s) have no usable event date and are excluded from time series.")
        if stats.counts["unmapped_category"]:
            notes.append(str(stats.counts["unmapped_category"]) + " record(s) use a product code absent from the FDA classification dictionary (category unclassified).")
        sources_with_data = [row for row in stats.sources if row["records"]]
        if len(sources_with_data) < 3 and sources_with_data:
            notes.append("Coverage differs by source: " + ", ".join(row["source_id"] for row in sources_with_data) + " only.")
        return notes

    def metrics_summary(self) -> dict[str, Any]:
        """The attribution and coverage metrics, computed from this dataset only."""
        from .metrics import attribution_metrics, summarise

        metrics = attribution_metrics(self)
        self._metrics = metrics
        return summarise(metrics)

    def metrics(self) -> dict[str, Any]:
        from .metrics import attribution_metrics

        cached = getattr(self, '_metrics', None)
        if cached is not None:
            return cached
        self._metrics = attribution_metrics(self)
        return self._metrics

    def global_share(self, events: Sequence[Event]) -> dict[str, float]:
        totals = {event_type: 0 for event_type in EVENT_TYPE_ORDER}
        for event in events:
            totals[event.event_type] = totals.get(event.event_type, 0) + 1
        return {
            event_type: (round(totals[event_type] / self.global_by_type.get(event_type, 1), 6) if totals[event_type] else 0.0)
            for event_type in EVENT_TYPE_ORDER
        }


SOURCES_ORDER = ("openfda_510k", "openfda_pma", "openfda_recall")


def _empty_org_stats(key: str) -> OrgStats:
    return OrgStats(
        key=key,
        counts=empty_counts(),
        aggregations={"by_year": [], "by_type": [], "by_category": [], "by_class": [], "undated_records": 0},
        window={"from": None, "to": None},
        sources=[],
        recent_events=[],
        first_observed_at=None,
        pending_review_records=0,
        unattributed_in_scope=0,
        rejected_in_scope=0,
        verified_records=0,
        rule_verified_records=0,
        proposed_records=0,
        predecessor_records=0,
        original_registrant_records=0,
        status_counts={},
    )


# --------------------------------------------------------------------------- loading
def _read_jsonl_gz(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def load_dataset(data_dir: Path | str | None = None, review_db: Path | str | None = None) -> Dataset:
    base = Path(data_dir) if data_dir else DEFAULT_DATA_DIR
    manifest_path = base / "snapshot.json"
    if not manifest_path.exists():
        raise FileNotFoundError(
            "no product snapshot at " + str(base) + "; run: python scripts/product_collect.py"
        )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    raw_events = _read_jsonl_gz(base / "events.jsonl.gz")
    applicants = _read_jsonl_gz(base / "applicants.jsonl.gz")
    classifications = _read_jsonl_gz(base / "classifications.jsonl.gz")

    overlay_items: tuple = ()
    resolved_review_db: Path | None
    if review_db is not None:
        resolved_review_db = Path(review_db)
    else:
        from .review.store import default_db_path

        resolved_review_db = default_db_path()
    if resolved_review_db is not None and resolved_review_db.exists():
        from .review.store import ReviewStore

        overlay_items = ReviewStore(resolved_review_db).overlay_items()
    registry = registry_with_overlay(overlay_items)
    collected_at = str(manifest.get("collected_at") or "")
    openfda_updated = (manifest.get("openfda") or {}).get("last_updated")

    category_by_code: dict[str, Category] = {}
    for row in classifications:
        code = str(row.get("product_code") or "").upper()
        if not code:
            continue
        specialty = row.get("specialty") or "Unclassified"
        category_by_code[code] = Category(id=slugify(specialty), label=str(specialty))
    categories = sorted({(cat.id, cat.label) for cat in category_by_code.values()})
    category_list = [Category(id=cat_id, label=label) for cat_id, label in categories]

    events: list[Event] = []
    for row in raw_events:
        applicant = str(row.get("applicant_name") or "")
        decision, rejection = registry.decide(applicant)
        verification: str | None = UNATTRIBUTED
        verified = False
        rule: str | None = None
        evidence_count = 0
        reviewer: str | None = None
        reviewer_kind: str | None = None
        provenance: str | None = None
        if decision is not None:
            org_key = decision.organization_key
            org_name = registry.by_key[org_key].display_name if org_key in registry.by_key else None
            status = "attributed"
            basis = decision.basis
            review = decision.review
            verification = decision.status
            verified = decision.verified
            rule = decision.rule
            evidence_count = len(decision.evidence)
            reviewer = decision.reviewer
            reviewer_kind = decision.reviewer_kind
            provenance = decision.provenance
        elif rejection is not None:
            org_key = None
            org_name = None
            status = "rejected"
            basis = None
            review = "rejected"
            verification = status_module.REJECTED
            reviewer = rejection.reviewer
            reviewer_kind = rejection.reviewer_kind
            provenance = "review_ledger"
        else:
            org_key = None
            org_name = None
            status = "unattributed"
            basis = None
            review = None
        predecessor = bool(org_key) and ownership_module.is_predecessor_applicant(org_key, applicant)
        code = (row.get("product_code") or "").upper() or None
        category = category_by_code.get(code) if code else None
        published = row.get("published_at")
        events.append(
            Event(
                event_id=row["event_id"],
                official_id=str(row.get("official_id") or ""),
                source_id=row["source_id"],
                event_type=row["event_type"],
                event_date=row.get("event_date"),
                published_at=published,
                published_at_status=row.get("published_at_status") or ("from_source" if published else "not_published_by_source"),
                first_observed_at=collected_at,
                available_at=published or collected_at,
                record_updated_at=openfda_updated,
                time_quality=row.get("time_quality") or "unknown",
                organization_key=org_key,
                organization_name=org_name,
                applicant_name=applicant,
                attribution_status=status,
                attribution_basis=basis,
                attribution_review=review,
                product_code=code,
                category=category,
                device_class=(row.get("raw") or {}).get("device_class"),
                device_name=row.get("device_name"),
                title=row.get("title") or row.get("official_id") or row["event_id"],
                summary=row.get("summary"),
                official_url=row.get("official_url") or "",
                raw=row.get("raw") or {},
                attribution_verification=verification or UNATTRIBUTED,
                attribution_verified=verified,
                attribution_rule=rule,
                attribution_evidence_count=evidence_count,
                attribution_reviewer=reviewer,
                attribution_reviewer_kind=reviewer_kind,
                attribution_provenance=provenance,
                attribution_is_predecessor=predecessor,
            )
        )

    # device class comes from the FDA classification dictionary (joined on product code)
    class_by_code = {str(row.get("product_code") or "").upper(): row.get("device_class") for row in classifications}
    for event in events:
        if event.device_class is None and event.product_code:
            value = class_by_code.get(event.product_code)
            if value in ("1", "2", "3"):
                event.device_class = value

    events.sort(key=lambda event: event.event_id)
    events_by_id = {event.event_id: event for event in events}

    org_events: dict[str, list[Event]] = {}
    for event in events:
        if event.organization_key:
            org_events.setdefault(event.organization_key, []).append(event)

    applicant_by_name = {str(row.get("applicant_name")): row for row in applicants}

    dataset = Dataset(
        data_dir=base,
        manifest=manifest,
        events=events,
        events_by_id=events_by_id,
        applicants=applicants,
        categories=category_list,
        registry=registry,
        org_stats={},
        global_counts={},
        global_aggregations={},
    )
    dataset._org_events = org_events
    dataset.applicant_by_name = applicant_by_name

    attributed = [event for event in events if event.organization_key]
    dataset.global_counts = dataset.counts(attributed)
    dataset.global_aggregations = aggregate(attributed)
    dataset.global_by_type = {
        event_type: sum(1 for event in attributed if event.event_type == event_type)
        for event_type in EVENT_TYPE_ORDER
    }

    # unattributed / rejected records that were retrieved within an organization's search scope
    scope_stats: dict[str, dict[str, int]] = {}
    for row in applicants:
        for scope, count in (row.get("by_org_scope") or {}).items():
            bucket = scope_stats.setdefault(str(scope), {"unattributed": 0, "rejected": 0})
            decision, rejection = registry.decide(str(row.get("applicant_name")))
            if decision is not None:
                continue
            if rejection is not None:
                bucket["rejected"] += int(count)
            else:
                bucket["unattributed"] += int(count)

    for org in registry.organizations:
        rows = org_events.get(org.key, [])
        if rows:
            dates = [event.event_date for event in rows if event.event_date]

            window = {"from": min(dates) if dates else None, "to": max(dates) if dates else None}
        else:
            window = {"from": None, "to": None}
        sources = []
        for source_id in SOURCES_ORDER:
            source_events = [event for event in rows if event.source_id == source_id]
            dates = [event.event_date for event in source_events if event.event_date]
            sources.append({
                "source_id": source_id,
                "name": SOURCE_NAMES[source_id],
                "records": len(source_events),
                "min_event_date": min(dates) if dates else None,
                "max_event_date": max(dates) if dates else None,
                "first_observed_at": collected_at if source_events else None,
                "published_field_available": source_id == "openfda_recall",
            })
        recent = sorted(rows, key=lambda event: (event.event_date is None, -(int(event.event_date.replace("-", "")) if event.event_date else 0), event.event_id))[:10]
        scope = scope_stats.get(org.key, {"unattributed": 0, "rejected": 0})
        row_counts = dataset.counts(rows)
        status_counts: dict[str, int] = {}
        for event in rows:
            key_name = event.attribution_verification
            status_counts[key_name] = status_counts.get(key_name, 0) + 1
        dataset.org_stats[org.key] = OrgStats(
            key=org.key,
            counts=row_counts,
            aggregations=aggregate(rows),
            window=window,
            sources=sources,
            recent_events=[event.to_public() for event in recent],
            first_observed_at=collected_at if rows else None,
            pending_review_records=int(row_counts["pending_review"]),
            unattributed_in_scope=int(scope["unattributed"]),
            rejected_in_scope=int(scope["rejected"]),
            verified_records=int(row_counts["verified_records"]),
            rule_verified_records=int(row_counts["rule_verified_records"]),
            proposed_records=int(row_counts["provisional"]),
            predecessor_records=sum(1 for event in rows if event.attribution_is_predecessor),
            original_registrant_records=sum(1 for event in rows if not event.attribution_is_predecessor),
            status_counts=status_counts,
        )

    dataset.warnings = registry.warnings[:]
    dataset.review_overlay_applied = int(getattr(registry, "overlay_applied", 0))
    dataset.review_db = str(resolved_review_db) if resolved_review_db is not None else None
    return dataset
