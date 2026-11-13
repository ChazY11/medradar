"""ClinicalTrials.gov v2 connector (``clinical_trial``).

Why ``studyFirstPostDate``
--------------------------
``startDate`` is when the study started (often back-dated and published later);
``lastUpdatePostDate`` moves with every edit.  ``studyFirstPostDate`` is the
registration date — the earliest date a third party could know the trial exists
— so it is the only defensible ``source_public_at``.  ``startDate`` is kept as
``event_at``.

Company attribution
-------------------
``sponsorCollaboratorsModule.leadSponsor.name`` is a structured field and yields
``tier="lead_sponsor"``.  Collaborators yield ``tier="collaborator"``.  The
values are marketing divisions ("Medtronic Cardiac Ablation Solutions"), so
:func:`identity.CompanyIndex.resolve` does the alias work and a negative guard
can still demote a match to ``candidate``.
"""

from __future__ import annotations

from typing import Any, Mapping

from .. import identity, schema
from . import _common

SOURCE_ID = "clinicaltrials_gov"
KIND = "clinical_trial"
LICENCE_STATUS = "public_domain"
SOURCE_NAME = "ClinicalTrials.gov"
ATTRIBUTION = "ClinicalTrials.gov (US NLM)"
BASE_URL = "https://clinicaltrials.gov/api/v2/studies"
DEFAULT_SPONSOR = "Medtronic"
PAGE_SIZE_MAX = 100


def _protocol(study: Mapping[str, Any]) -> Mapping[str, Any]:
    return study.get("protocolSection") or {}


def _identifiers(study: Mapping[str, Any]) -> list[dict[str, Any]]:
    protocol = _protocol(study)
    identification = protocol.get("identificationModule") or {}
    out: list[dict[str, Any]] = []
    nct = identity.build_identifier("nct", identification.get("nctId"), is_primary=True)
    if nct:
        out.append(nct)
    return out


def _interventions(protocol: Mapping[str, Any]) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for intervention in (protocol.get("armsInterventionsModule") or {}).get("interventions") or []:
        if isinstance(intervention, Mapping):
            out.append(
                {
                    "type": str(intervention.get("type") or ""),
                    "name": str(intervention.get("name") or ""),
                }
            )
    return out


def _countries(protocol: Mapping[str, Any]) -> list[str]:
    countries: list[str] = []
    for location in (protocol.get("contactsLocationsModule") or {}).get("locations") or []:
        country = str(location.get("country") or "").strip() if isinstance(location, Mapping) else ""
        if country and country not in countries:
            countries.append(country)
    return countries


def to_evidence(raw_item: Mapping[str, Any], *, fetched_at: Any = None) -> dict[str, Any]:
    """One CT.gov v2 study -> one ``clinical_trial`` evidence record."""
    study = dict(raw_item)
    fetched = _common.as_datetime(fetched_at)
    protocol = _protocol(study)
    identification = protocol.get("identificationModule") or {}
    status = protocol.get("statusModule") or {}
    nct_id = str(identification.get("nctId") or "").strip()
    if not nct_id:
        raise ValueError("clinicaltrials_gov study without nctId")

    first_posted = (status.get("studyFirstPostDateStruct") or {}).get("date")
    start_date = (status.get("startDateStruct") or {}).get("date")
    sponsor_module = protocol.get("sponsorCollaboratorsModule") or {}
    lead_sponsor = str((sponsor_module.get("leadSponsor") or {}).get("name") or "").strip()
    collaborators = [
        str(item.get("name") or "").strip()
        for item in sponsor_module.get("collaborators") or []
        if isinstance(item, Mapping)
    ]
    design = protocol.get("designModule") or {}
    conditions = (protocol.get("conditionsModule") or {}).get("conditions") or []

    refs = _common.company_refs([lead_sponsor], tier="lead_sponsor") + _common.company_refs(
        collaborators, tier="collaborator"
    )
    normalized = {
        "nct_id": nct_id,
        "brief_title": identification.get("briefTitle"),
        "official_title": identification.get("officialTitle"),
        "acronym": identification.get("acronym"),
        "org_study_id": (identification.get("orgStudyIdInfo") or {}).get("id"),
        "organization_full_name": (identification.get("organization") or {}).get("fullName"),
        "study_type": design.get("studyType"),
        "phases": design.get("phases") or [],
        "overall_status": status.get("overallStatus"),
        "why_stopped": status.get("whyStopped"),
        "study_first_post_date": first_posted,
        "start_date": start_date,
        "last_update_post_date": (status.get("lastUpdatePostDateStruct") or {}).get("date"),
        "primary_completion_date": (status.get("primaryCompletionDateStruct") or {}).get("date"),
        "completion_date": (status.get("completionDateStruct") or {}).get("date"),
        "conditions": conditions,
        "enrollment": (design.get("enrollmentInfo") or {}).get("count"),
        "lead_sponsor": lead_sponsor,
        "lead_sponsor_class": (sponsor_module.get("leadSponsor") or {}).get("class"),
        "collaborators": collaborators,
        "interventions": _interventions(protocol),
        "countries": _countries(protocol),
        "trial_ids": [{"value": nct_id, "field": "identificationModule.nctId"}],
        "metadata_clock_fields": _common.metadata_clock_fields(
            ("studyFirstSubmitDate", (status.get("studyFirstSubmitDate"))),
            ("lastUpdatePostDate", (status.get("lastUpdatePostDateStruct") or {}).get("date")),
        ),
    }
    return schema.make_evidence(
        source_id=SOURCE_ID,
        kind=KIND,
        source_record_id=nct_id,
        source_url=f"https://clinicaltrials.gov/study/{nct_id}",
        normalized=normalized,
        raw=_common.raw_block(study),
        time=_common.time_block(
            event_at=start_date,
            source_public_at=first_posted,
            fetched_at=fetched,
            notes="studyFirstPostDate is the first public registration date; startDate is the study start",
        ),
        identifiers=_identifiers(study),
        entity_refs=refs,
        provenance=_common.provenance(
            source_name=SOURCE_NAME,
            licence_status=LICENCE_STATUS,
            attribution=ATTRIBUTION,
            redistribution="allowed (US government work)",
            evidence_reference=f"https://clinicaltrials.gov/study/{nct_id}",
            quality=_common.coerce_date(first_posted)[1],
        ),
        fetched_at=fetched.isoformat(),
    )


def fetch_items(
    client: Any,
    *,
    limit: int = 50,
    sponsor: str = DEFAULT_SPONSOR,
    page_size: int = 25,
    max_pages: int = 2,
) -> list[dict[str, Any]]:
    """Bounded ``query.spons`` pagination; returns raw study dicts."""
    if limit <= 0:
        return []
    size = max(1, min(int(page_size), PAGE_SIZE_MAX, limit))
    token: str | None = None
    seen: dict[str, dict[str, Any]] = {}
    pages = 0
    while pages < max(1, int(max_pages)) and len(seen) < limit:
        params: dict[str, Any] = {
            "query.spons": sponsor,
            "pageSize": size,
            "countTotal": "true",
            "sort": "StudyFirstPostDate:desc",
        }
        if token:
            params["pageToken"] = token
        result = client.get(BASE_URL, params=params)
        pages += 1
        if not result.ok:
            break
        payload = result.json()
        batch = payload.get("studies") or []
        for study in batch:
            if isinstance(study, Mapping):
                protocol = _protocol(study)
                nct = ((protocol.get("identificationModule") or {}).get("nctId") or "").strip()
                if nct:
                    seen.setdefault(nct, dict(study))
        token = payload.get("nextPageToken")
        if not batch or not token:
            break
    return list(seen.values())[:limit]


def collect(
    client: Any,
    *,
    limit: int = 50,
    sponsor: str = DEFAULT_SPONSOR,
    page_size: int = 25,
    max_pages: int = 2,
) -> list[dict[str, Any]]:
    """Fetch up to ``limit`` studies and return schema-valid evidence records."""
    fetched = _common.as_datetime(None)
    items = fetch_items(
        client, limit=limit, sponsor=sponsor, page_size=page_size, max_pages=max_pages
    )
    pieces: list[dict[str, Any]] = []
    for item in items:
        try:
            pieces.append(to_evidence(item, fetched_at=fetched))
        except ValueError:
            continue
    return pieces


__all__ = ["SOURCE_ID", "KIND", "LICENCE_STATUS", "collect", "fetch_items", "to_evidence"]
