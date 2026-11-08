"""UK Find a Tender — OCDS 1.1 release packages (verified 2026-11-09, no key).

Why this connector emits **two** evidence kinds
-----------------------------------------------
A UK FTS release carries a ``tag`` that states its procurement stage:

* ``tag == ["tender"]``  → the procurement was **published as an opportunity**
  (``procurement_notice``)
* ``tag`` contains ``award`` / ``contract`` → the **award and the signed
  contract** were published (``procurement_award``)

That is the whole point of using OCDS here: "a tender was announced" and "a
contract was awarded" are different records with different dates, and the source
labels which is which.  This module keeps them as different ``kind`` values
instead of flattening them into one "procurement" bucket.

Four clocks in this source (all four genuinely present)
-------------------------------------------------------
``source_public_at``  ``release.date`` — when this release was published
``event_at``          ``contracts[0].dateSigned`` — when the contract was signed
                      (for a tender release: ``null``, there is no event yet)
``first_observed_at`` the fetch clock (never back-filled)
``fetched_at``        this collection

``release.date`` is the *release's* publication/update time.  For a re-published
release it is later than the first public appearance of the ``ocid``; a
first-visibility claim therefore needs the earliest release of that ``ocid``,
which this connector does not reconstruct.
"""

from __future__ import annotations

from typing import Any, Iterable, Mapping

from medradar.external_sources import base as ev_base
from medradar.external_sources import identity as ev_identity
from medradar.external_sources.procurement import common

SOURCE_ID = "uk_find_a_tender"
SOURCE_NAME = "UK Find a Tender service (OCDS 1.1)"
KIND = "procurement_award"
LICENCE_STATUS = "open_licence"
ATTRIBUTION = "UK Find a Tender service, Crown copyright, Open Government Licence v3.0"
REDISTRIBUTION = "yes"

PACKAGES_URL = "https://www.find-tender.service.gov.uk/api/1.0/ocdsReleasePackages"

TENDER_KIND = "procurement_notice"
AWARD_KIND = "procurement_award"

#: Stage markers observed in real releases, mapped to evidence kinds.
STAGE_KINDS = {
    "tender": TENDER_KIND,
    "tenderAmendment": TENDER_KIND,
    "planning": TENDER_KIND,
    "award": AWARD_KIND,
    "contract": AWARD_KIND,
    "implementation": AWARD_KIND,
}


def release_kind(release: Mapping[str, Any]) -> str:
    """Map an OCDS release ``tag`` list onto an evidence kind (stage-first)."""
    tags = release.get("tag") or []
    if isinstance(tags, str):
        tags = [tags]
    lowered = [str(t).strip() for t in tags]
    for tag in lowered:
        if tag in {"award", "contract", "implementation"}:
            return AWARD_KIND
    for tag in lowered:
        if tag in STAGE_KINDS:
            return STAGE_KINDS[tag]
    # A release with no recognisable stage tag is a notice: calling it an award
    # would over-claim, which is the error this module is written to avoid.
    return TENDER_KIND


def release_record_id(release: Mapping[str, Any]) -> str:
    """``ocid#release.id`` when both exist, else a digest of the identifying fields."""
    ocid = common.clip(release.get("ocid"), 120)
    rid = common.clip(release.get("id"), 120)
    if ocid and rid:
        return f"{ocid}#{rid}"
    if ocid:
        return ocid
    if rid:
        return rid
    return "release_" + common.digest(ocid, release.get("date"), release.get("tag"))


def _supplier_names(release: Mapping[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for award in release.get("awards") or []:
        if not isinstance(award, Mapping):
            continue
        for supplier in award.get("suppliers") or []:
            if isinstance(supplier, Mapping):
                out.append({"name": common.clip(supplier.get("name"), 300), "id": common.clip(supplier.get("id"), 120)})
    if not out:  # fall back to parties tagged as supplier
        for party in release.get("parties") or []:
            if isinstance(party, Mapping) and "supplier" in (party.get("roles") or []):
                out.append({"name": common.clip(party.get("name"), 300), "id": common.clip(party.get("id"), 120)})
    return out


def _first_contract(release: Mapping[str, Any]) -> Mapping[str, Any]:
    for contract in release.get("contracts") or []:
        if isinstance(contract, Mapping):
            return contract
    return {}


def _contract_value(contract: Mapping[str, Any]) -> tuple[float | None, str]:
    value = contract.get("value") if isinstance(contract, Mapping) else None
    if not isinstance(value, Mapping):
        return None, ""
    amount = value.get("amount")
    currency = common.clip(value.get("currency"), 8)
    if not isinstance(amount, (int, float)):
        return None, currency
    return float(amount), currency


def to_evidence(
    raw_item: Mapping[str, Any],
    *,
    fetched_at: str = "",
    company_index: ev_identity.CompanyIndex | None = None,
    collection_run_id: str = "",
) -> dict[str, Any]:
    """One OCDS release -> one notice or award evidence record."""
    fetched = fetched_at or common.utc_iso()
    release = dict(raw_item)
    kind = release_kind(release)
    record_id = release_record_id(release)

    tender = release.get("tender") or {}
    if not isinstance(tender, Mapping):
        tender = {}
    contract = _first_contract(release)
    amount, currency = _contract_value(contract)
    suppliers = _supplier_names(release)

    classification = tender.get("classification") or {}
    if not isinstance(classification, Mapping):
        classification = {}

    release_date = common.clip(release.get("date"), 40)
    signed = common.clip(contract.get("dateSigned"), 40)
    awards = [a for a in (release.get("awards") or []) if isinstance(a, Mapping)]
    award_date = common.clip(awards[0].get("date"), 40) if awards else ""

    normalized = {
        "ocid": common.clip(release.get("ocid"), 120),
        "release_id": common.clip(release.get("id"), 120),
        "release_tags": list(release.get("tag") or []),
        "procurement_stage": "tender published" if kind == TENDER_KIND else "award/contract published",
        "tender_title": common.clip(tender.get("title"), 400),
        "tender_status": common.clip(tender.get("status"), 80),
        "main_procurement_category": common.clip(tender.get("mainProcurementCategory"), 80),
        "cpv_code": common.clip(classification.get("id"), 40),
        "cpv_description": common.clip(classification.get("description"), 300),
        "n_awards": len(awards),
        "award_id": common.clip(awards[0].get("id"), 120) if awards else "",
        "award_date": award_date,
        "suppliers": suppliers,
        "contract_id": common.clip(contract.get("id"), 120),
        "contract_status": common.clip(contract.get("status"), 80),
        "contract_date_signed": signed,
        "contract_value": amount,
        "contract_value_currency": currency,
        "product_link": "none - CPV category plus free-text item descriptions; no device model or UDI",
        "stage_note": (
            "a tender release states that a procurement was published; an award/contract "
            "release states that it was awarded and signed. They are different facts and "
            "are stored as different evidence kinds."
        ),
    }

    raw_body = common.canonical_json_line(release).encode("utf-8")
    raw = common.raw_block(raw_body, path=f"{PACKAGES_URL}#release:{record_id}")

    identifiers = common.identifier_list(
        ("ocid", release.get("ocid"), {"is_primary": True, "note": "Open Contracting ID"}),
        ("contest_id", release.get("id"), {}),
        ("award_id", (awards[0].get("id") if awards else None), {"note": "OCDS award id"}),
    )
    # supplier organisation identifiers are identifiers of the *supplier*, not of
    # this procurement record, so they are carried in normalized only.

    if kind == TENDER_KIND:
        time_block = common.clock_block(
            event_at=None,
            source_public_at=release_date,
            fetched_at=fetched,
            notes=(
                "tender release: source_public_at = release.date (when the opportunity was "
                "published). event_at is null — nothing has been awarded yet, and inventing "
                "an event date from the release date would be circular."
            ),
        )
    else:
        time_block = common.clock_block(
            event_at=signed or award_date,
            source_public_at=release_date,
            fetched_at=fetched,
            notes=(
                "award release: source_public_at = release.date; event_at = "
                "contracts[0].dateSigned (falling back to awards[0].date). awards[0].date was "
                "null in every record probed, so dateSigned is the usable event date. "
                "release.date is a RELEASE publication time, not necessarily the first public "
                "appearance of the ocid."
            ),
        )

    entity_refs = [common.resolve_company(company_index, s["name"], country="GB") for s in suppliers if s["name"]]

    return common.evidence(
        source_id=SOURCE_ID,
        kind=kind,
        source_record_id=record_id,
        source_url=PACKAGES_URL,
        normalized=normalized,
        raw=raw,
        time_block=time_block,
        identifiers=identifiers,
        entity_refs=entity_refs,
        source_name=SOURCE_NAME,
        licence_status=LICENCE_STATUS,
        attribution=ATTRIBUTION,
        redistribution=REDISTRIBUTION,
        fetched_at=fetched,
        collection_run_id=collection_run_id,
    )


def collect(
    client: Any,
    *,
    limit: int = 50,
    stages: str | None = None,
    updated_from: str | None = None,
    updated_to: str | None = None,
    page_size: int = 25,
    max_pages: int = 4,
    company_index: ev_identity.CompanyIndex | None = None,
    fetched_at: str = "",
    collection_run_id: str = "",
) -> list[dict[str, Any]]:
    """Collect at most ``limit`` release records from the OCDS feed.

    The feed has **no keyword parameter** (``keywords=`` returns HTTP 400), so
    firm-targeted retrieval is impossible here: the only honest modes are a date
    window and a stage filter.  Both are exposed as arguments.
    """
    if limit <= 0:
        raise ValueError("limit must be positive")
    fetched = fetched_at or ev_base.utc_iso()
    size = max(1, min(int(page_size), 100, limit))
    remaining = int(limit)
    records: list[dict[str, Any]] = []
    for page in range(1, max_pages + 1):
        if remaining <= 0:
            break
        requested = max(1, min(size, remaining))
        params: dict[str, Any] = {"limit": requested}
        if stages:
            params["stages"] = stages
        if updated_from:
            params["updatedFrom"] = updated_from
        if updated_to:
            params["updatedTo"] = updated_to
        result = client.get(PACKAGES_URL, params=params)
        if not result.ok:
            break
        try:
            body = result.json() or {}
        except Exception:
            break
        releases = body.get("releases") or []
        if not isinstance(releases, list) or not releases:
            break
        for release in releases:
            if remaining <= 0:
                break
            if not isinstance(release, dict):
                continue
            records.append(
                to_evidence(
                    release,
                    fetched_at=fetched,
                    company_index=company_index,
                    collection_run_id=collection_run_id,
                )
            )
            remaining -= 1
        if len(releases) < requested:
            break
    return records


def split_by_stage(records: Iterable[Mapping[str, Any]]) -> dict[str, int]:
    """Count records per kind, so a report can never silently merge the stages."""
    counts: dict[str, int] = {TENDER_KIND: 0, AWARD_KIND: 0}
    for record in records:
        kind = str(record.get("kind", ""))
        counts[kind] = counts.get(kind, 0) + 1
    return counts


__all__ = [
    "ATTRIBUTION",
    "AWARD_KIND",
    "KIND",
    "LICENCE_STATUS",
    "PACKAGES_URL",
    "SOURCE_ID",
    "SOURCE_NAME",
    "STAGE_KINDS",
    "TENDER_KIND",
    "collect",
    "release_kind",
    "release_record_id",
    "split_by_stage",
    "to_evidence",
]
