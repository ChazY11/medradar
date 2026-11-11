"""The CONVERGENCE evidence contract: HORIZON ``horizon.evidence.v1`` → ATLAS.

This module is the **semantic** half of the integration.  It contains no I/O and
no database code: it says what each field *means* and what may legally happen to
it during a conversion.  :mod:`medradar.integration.adapter` applies it.

Why a separate contract at all
------------------------------
ATLAS (``medradar.atlas.evidence.v1``) and HORIZON (``horizon.evidence.v1``) look
similar but disagree on three things that a field-rename would silently corrupt:

1. **What "confirmed" means.** In HORIZON, ``evidence_status=CONFIRMED`` means
   "the official source really has this record".  ``identity_status=CONFIRMED``
   means "this record's own identifier resolved at its own source".  Neither says
   that the record describes the *same real-world entity* as some other record.
   ATLAS's ``identity_resolution_status=confirmed`` means exactly that, and is
   only reachable through an authoritative identifier match.  A naive mapping
   would therefore launder 941 source-status flags into confirmed identities.
   :data:`RECORD_STATUS_FIELDS` keeps them as source assertions, and
   :data:`IDENTITY_GRADE` states the ladder.

2. **What an identifier is.** HORIZON's MDALL ``hc_mdall_device_identifier`` is
   *mostly* a Health Canada catalogue token (``6102F-PA00017``) but a small
   minority of values are genuine GTIN-14 UDI-DIs.  Scheme is therefore decided
   per **value**, not per source field: :func:`classify_identifier` promotes a
   value to ``di`` only when it is 14 digits with a valid GS1 Mod-10 check digit,
   and records the derivation.  Nothing is promoted on a name or a guess.

3. **What a time means.** HORIZON publishes an explicit ``clock_class`` and
   ``temporal_note`` per record (e.g. "first_licence_status_dt is an event date;
   last_refresh_dt is a refresh stamp, not a publication date").  Those notes are
   evidence and are carried through.  ``first_observed_at`` is never derived from
   ``event_at`` or ``source_public_at``; when a source has no observation log the
   clock stays **unknown** rather than being invented.

The conversion is allowed to lose *nothing* silently.  Every field that has no
ATLAS home is copied into ``normalized.<source>`` or ``provenance`` and named in
:data:`PRESERVED_ONLY_FIELDS`; fields that genuinely cannot survive are reported
by the adapter as lost-field records.
"""

from __future__ import annotations

import re
from typing import Any, Mapping

CONTRACT_ID = "medradar.convergence.evidence.v1"
CONTRACT_VERSION = "1.0.0"

SOURCE_SCHEMA = "horizon.evidence.v1"
TARGET_SCHEMA = "medradar.atlas.evidence.v1"

# ---------------------------------------------------------------------------
# 1. entity_type -> ATLAS evidence_type
# ---------------------------------------------------------------------------
# Every HORIZON entity_type must have a target.  The mapping is many-to-one in
# places; the original value is always preserved in
# ``normalized.horizon.entity_type`` so the join back to HORIZON stays exact.
EVIDENCE_TYPE_MAP: dict[str, str] = {
    "product_identifier": "product_identifier",
    "regulatory_listing": "device_registration",
    "regulatory_clearance": "regulatory_clearance",
    "regulatory_approval": "regulatory_approval",
    "patent_publication": "patent",
    "publication": "publication",
    "clinical_trial": "clinical_trial",
    "grant": "grant",
    "procurement_award": "procurement_event",
    "trade_flow": "trade_statistic",
    "company_registry": "company_registry",
    "postmarket_event": "postmarket_event",
    "recall": "recall",
}

#: entity types that may never be imported even if the source says so, because
#: the target contract cannot represent their semantics losslessly.
UNMAPPABLE_ENTITY_TYPES: frozenset[str] = frozenset()

# ---------------------------------------------------------------------------
# 2. identifier schemes
# ---------------------------------------------------------------------------
# ``value_classified=True`` means the target scheme depends on the *value* and is
# decided by :func:`classify_identifier`, not by the incoming scheme name.
IDENTIFIER_SCHEME_MAP: dict[str, tuple[str, str]] = {
    # horizon scheme: (atlas scheme, semantic note)
    "udi_di": ("di", "FDA GUDID primary device identifier; a 14-digit GTIN-14."),
    "hc_device_licence": ("licence_no", "Health Canada medical device licence number (licence-level, not device-level)."),
    "hc_mdall_device_id": ("hc_mdall_device_id", "Health Canada internal MDALL device row id; stable within MDALL only."),
    "hc_mdall_device_identifier": (
        "hc_device_identifier",
        "MDALL device_identifier: usually a manufacturer catalogue/model token; "
        "promoted to scheme 'di' only when the value is a check-digit-valid GTIN-14.",
    ),
    "uspto_510k": ("510k", "FDA 510(k) clearance number."),
    "uspto_pma": ("pma", "FDA premarket approval number."),
    "nct": ("nct", "ClinicalTrials.gov registry identifier."),
    "doi": ("doi", "Digital Object Identifier; lower-cased for canonical keys."),
    "pmid": ("pmid", "PubMed identifier."),
    "pmcid": ("pmcid", "PubMed Central identifier."),
    "pubmed_mid": ("pmid", "PubMed identifier (legacy field spelling)."),
    "openalex_id": ("openalex_id", "OpenAlex work identifier."),
    "s2_corpus_id": ("s2_corpus_id", "Semantic Scholar corpus id."),
    "mag": ("mag", "Microsoft Academic Graph id (retired namespace, kept as-is)."),
    "handle": ("handle", "Handle/DOI-alternative persistent identifier."),
    "cipo_patent_number": ("patent_no", "Canadian patent number."),
    "epo_publication_number": ("patent_no", "EPO publication number (A/B kind code included)."),
    "epo_application_number": ("patent_application_no", "EPO application number."),
    "pct_publication_number": ("pct_publication_number", "WIPO PCT publication number."),
    "pct_application_number": ("pct_application_number", "WIPO PCT application number."),
    "ocds_ocid": ("ocid", "Open Contracting Partnership contract id (an EVENT id, not a party id)."),
    "ocds_party_id": ("ocds_party_id", "OCDS party id scoped to one ocid."),
    "ted_publication_number": ("ted_publication_number", "EU TED tender publication number."),
    "hs_code": ("hs_code", "Harmonized System commodity code (a classification, not an identity)."),
    "eurostat_comext_cell": ("eurostat_comext_cell", "Eurostat Comext dataset cell coordinate."),
    "hmrc_ots_series": ("hmrc_ots_series", "HMRC Overseas Trade Statistics series key."),
    "usaspending_generated_internal_id": (
        "usaspending_generated_internal_id",
        "USAspending internal record id; not stable across releases.",
    ),
    "federal_award_id": ("federal_award_id", "US federal award identifier."),
    "sam_uei": ("sam_uei", "SAM.gov Unique Entity Identifier (company-level)."),
    "fda_product_code": ("fda_product_code", "FDA product code (a classification, not an identity)."),
    "fda_registration_number": ("fda_registration_number", "FDA establishment registration number."),
    "fda_fei": ("fda_fei", "FDA Establishment Identifier."),
    "cfr_regulation": ("cfr_regulation", "21 CFR regulation citation."),
    "anvisa_registro": ("anvisa_registro", "ANVISA product registration number."),
    "anvisa_processo": ("anvisa_processo", "ANVISA administrative process number."),
    "nih_project_num": ("nih_project_num", "NIH project number."),
    "nih_core_project_num": ("nih_project_num", "NIH core project number."),
    "cordis_rcn": ("cordis_rcn", "EU CORDIS record control number."),
    "cordis_grant_agreement_id": ("cordis_grant_agreement_id", "EU grant agreement id."),
}

#: schemes whose values are classifications, not entity identifiers.  They may
#: never become a ``canonical_key`` basis, and may never create a confirmed
#: identity relation on their own.
CLASSIFICATION_SCHEMES: frozenset[str] = frozenset(
    {
        "hs_code",
        "fda_product_code",
        "cfr_regulation",
        "eurostat_comext_cell",
        "hmrc_ots_series",
    }
)

_GTIN14 = re.compile(r"^\d{14}$")


def gtin_check_digit(value: str) -> int | None:
    """GS1 Mod-10 check digit for a 14-digit GTIN, or ``None`` if not a GTIN-14.

    Weighting follows the GS1 general specification: positions 1..13 from the
    left are multiplied by 3,1,3,1,... and the check digit is ``(10 - sum%10)%10``.
    """
    if not isinstance(value, str) or not _GTIN14.match(value):
        return None
    total = 0
    for index, char in enumerate(value[:13]):
        digit = int(char)
        total += digit * (3 if index % 2 == 0 else 1)
    return (10 - total % 10) % 10


def is_gtin14(value: Any) -> bool:
    """True only for a 14-digit string whose check digit validates."""
    if not isinstance(value, str):
        return False
    expected = gtin_check_digit(value)
    return expected is not None and expected == int(value[13])


def classify_identifier(
    scheme: str, value: Any, *, is_primary: bool = False
) -> tuple[str, dict[str, Any]]:
    """Return ``(atlas_scheme, derivation)`` for one incoming identifier.

    The only value-dependent promotion in the whole contract is
    ``hc_mdall_device_identifier`` → ``di``: Health Canada's device_identifier
    field carries a model token for the large majority of rows but a genuine
    GTIN-14 for a small minority, and that minority is the only official
    US–Canada identity bridge that exists.  Promotion requires a *validated*
    check digit; a 14-digit string with a bad check digit is reported as
    malformed and stays in its original scheme.
    """
    raw = str(value).strip() if value is not None else ""
    note: dict[str, Any] = {"source_scheme": scheme}

    if scheme in CLASSIFICATION_SCHEMES:
        note["role"] = "classification"
    mapped, semantics = IDENTIFIER_SCHEME_MAP.get(scheme, (scheme, "unmapped scheme (passed through)"))
    note["scheme_semantics"] = semantics
    if scheme not in IDENTIFIER_SCHEME_MAP:
        note["unmapped"] = True

    if scheme in {"udi_di", "hc_mdall_device_identifier"}:
        gtin = is_gtin14(raw)
        note["gtin14_valid"] = gtin
        if scheme == "hc_mdall_device_identifier":
            if gtin:
                note["derivation"] = "hc_mdall_device_identifier_promoted_to_di_on_valid_gtin14"
                return "di", note
            if _GTIN14.match(raw):
                note["derivation"] = "gtin14_shape_but_check_digit_invalid_not_promoted"
            else:
                note["derivation"] = "mdall_catalogue_token_not_a_udi"
            return mapped, note
        # udi_di: a GUDID UDI-DI that does not validate is a source defect, keep
        # the scheme but record it so the quality checker can flag it.
        if not gtin:
            note["derivation"] = "udi_di_value_failed_gtin14_check"
        return mapped, note

    if scheme == "hc_mdall_device_id":
        note["role"] = "regional_record_id"
    return mapped, note


# ---------------------------------------------------------------------------
# 3. record status (HORIZON) vs identity grade (CONVERGENCE)
# ---------------------------------------------------------------------------
#: HORIZON fields that describe the *record*, never an entity link.  They are
#: preserved verbatim under ``normalized.horizon_record_status`` and are never
#: mapped onto ``identity_resolution_status``.
RECORD_STATUS_FIELDS: tuple[str, ...] = ("evidence_status", "identity_status")

#: The six convergence identity grades.  Ordered weakest → strongest.
IDENTITY_GRADES: tuple[str, ...] = (
    "REJECTED_RELATION",
    "CONTRADICTED_RELATION",
    "UNVERIFIED_RELATION",
    "CANDIDATE_RELATION",
    "SOURCE_ASSERTED_RELATION",
    "AUTHORITATIVE_ID_MATCH",
)

#: How each convergence grade is allowed to appear in the ATLAS target.
#: ``may_set_confirmed_identity`` is the hard guard: only grades listed there may
#: produce ``identity_resolution_status="confirmed"``, and only together with an
#: authoritative identifier basis.
IDENTITY_GRADE_EFFECTS: dict[str, dict[str, Any]] = {
    "AUTHORITATIVE_ID_MATCH": {
        "atlas_identity_status": "confirmed",
        "atlas_relation_status": "asserted_by_source",
        "atlas_method": "official_id",
        "may_set_confirmed_identity": True,
        "atlas_db_status": "CONFIRMED",
        "requires_official_identifier": True,
        "explanation": "Both sides carry the same official identifier in the same namespace.",
    },
    "SOURCE_ASSERTED_RELATION": {
        "atlas_identity_status": "candidate",
        "atlas_relation_status": "asserted_by_source",
        "atlas_method": "multi_field",
        "may_set_confirmed_identity": False,
        "atlas_db_status": "CONFIRMED",
        "requires_official_identifier": False,
        "explanation": "A source or register asserts the relation; it is not an identity match.",
    },
    "CANDIDATE_RELATION": {
        "atlas_identity_status": "candidate",
        "atlas_relation_status": "candidate",
        "atlas_method": "candidate",
        "may_set_confirmed_identity": False,
        "atlas_db_status": "CANDIDATE",
        "requires_official_identifier": False,
        "explanation": "Similarity or a soft field suggests the relation; unconfirmed by construction.",
    },
    "UNVERIFIED_RELATION": {
        "atlas_identity_status": "none",
        "atlas_relation_status": "unknown",
        "atlas_method": "none",
        "may_set_confirmed_identity": False,
        "atlas_db_status": "CANDIDATE",
        "requires_official_identifier": False,
        "explanation": "A relation was claimed somewhere but cannot be checked from available evidence.",
    },
    "CONTRADICTED_RELATION": {
        "atlas_identity_status": "none",
        "atlas_relation_status": "contradicted",
        "atlas_method": "none",
        "may_set_confirmed_identity": False,
        "atlas_db_status": "REJECTED",
        "requires_official_identifier": False,
        "explanation": "An official field contradicts the relation.",
    },
    "REJECTED_RELATION": {
        "atlas_identity_status": "none",
        "atlas_relation_status": "none",
        "atlas_method": "none",
        "may_set_confirmed_identity": False,
        "atlas_db_status": "REJECTED",
        "requires_official_identifier": False,
        "explanation": "The relation was evaluated and refused; kept only as a negative control.",
    },
}

#: HORIZON ``relations[].relation_type`` → convergence grade.
#:
#: ``applicant_group_candidate`` is HORIZON's own name for a *hypothesis* about
#: corporate grouping, so it can only ever be a candidate.  The two
#: bibliographic relations are asserted by the issuing patent office for their own
#: documents, which is a source assertion — not a device-identity match.
RELATION_TYPE_GRADE: dict[str, str] = {
    "applicant_group_candidate": "CANDIDATE_RELATION",
    "priority_claim": "SOURCE_ASSERTED_RELATION",
    "application_to_publication": "SOURCE_ASSERTED_RELATION",
}

#: Relations whose grade may never be raised by the adapter, whatever the record
#: claims.  This is the anti-promotion guard the CI asserts on.
NON_PROMOTABLE_RELATION_TYPES: frozenset[str] = frozenset(
    {"applicant_group_candidate"}
)

# ---------------------------------------------------------------------------
# 4. quality flags
# ---------------------------------------------------------------------------
#: HORIZON flag → ATLAS flag.  Only semantics-preserving translations appear
#: here; everything else is preserved verbatim in
#: ``normalized.source_quality_flags`` so no signal is lost.
QUALITY_FLAG_MAP: dict[str, str] = {
    "MISSING_PUBLICATION_DATE": "missing_time",
    "MISSING_FILING_DATE": "missing_time",
    "MISSING_PRIORITY_DATE": "missing_time",
    "MISSING_MANUFACTURER": "missing_company",
    "MISSING_TITLE": "missing_primary_identifier",
    "NAME_MATCH_ONLY": "unverified_identity",
    "RETROSPECTIVE_FIELD": "derived_time",
    "PARSED_FROM_HTML": "schema_drift",
    "DOCUMENT_IS_SEARCH_REPORT": "schema_drift",
    "SITEMAP_ONLY": "truncated_payload",
    # deliberately untranslated (no faithful ATLAS equivalent):
    #   SNAPSHOT_ONLY, MISSING_CLASSIFICATION, NOT_MEDTECH_ON_FRONT_PAGE,
    #   DOCUMENT_IS_CORRECTION
}

#: Flags that make a record ineligible to support any *identity* claim, even if
#: some other field looks like an identifier.
IDENTITY_BLOCKING_FLAGS: frozenset[str] = frozenset({"NAME_MATCH_ONLY"})

# ---------------------------------------------------------------------------
# 5. time semantics
# ---------------------------------------------------------------------------
TIME_CLOCKS: tuple[str, ...] = (
    "event_at",
    "source_public_at",
    "first_observed_at",
    "fetched_at",
)

#: Substrings in HORIZON's ``attributes.temporal_note`` that mean a date is *not*
#: a publication date.  Used to detect event/public confusion rather than trust
#: the field name.
NON_PUBLICATION_HINTS: tuple[str, ...] = (
    "not a publication date",
    "refresh stamp",
    "database refresh",
    "snapshot",
)

#: Fields copied into the ATLAS time block so the source's own claim survives.
TIME_EVIDENCE_FIELDS: tuple[str, ...] = (
    "clock_class",
    "temporal_note",
    "public_availability_basis",
    "date_kind",
)

# ---------------------------------------------------------------------------
# 6. lossless preservation
# ---------------------------------------------------------------------------
#: HORIZON fields with no ATLAS column.  They are preserved inside
#: ``normalized.horizon`` and listed in the conversion manifest so a reader can
#: see exactly what happened to each one.
PRESERVED_ONLY_FIELDS: tuple[str, ...] = (
    "schema_version",
    "entity_type",
    "original_name",
    "manufacturer",
    "attributes",
    "evidence_status",
    "identity_status",
    "licence_note",
    "notes",
    "relations",
    "raw_ref",
    "content_hash",
)

#: HORIZON fields consumed by the adapter (i.e. they get a real ATLAS home).
CONSUMED_FIELDS: tuple[str, ...] = (
    "source_id",
    "source_record_id",
    "source_url",
    "identifiers",
    "event_at",
    "source_public_at",
    "first_observed_at",
    "fetched_at",
    "licence_status",
    "quality_flags",
)

#: Every field the source contract declares.  The adapter refuses to import a
#: record carrying an undeclared field unless it is reported as an extension.
DECLARED_SOURCE_FIELDS: frozenset[str] = frozenset(CONSUMED_FIELDS + PRESERVED_ONLY_FIELDS)


# ---------------------------------------------------------------------------
# 7. dedupe identities (four separate layers)
# ---------------------------------------------------------------------------
#: Layer 1 — record identity: one source publication of one record.
DEDUPE_LAYER_RECORD = "record_identity"
#: Layer 2 — entity identity: two records describing the same real-world object.
DEDUPE_LAYER_ENTITY = "entity_identity"
#: Layer 3 — event identity: one official event that may involve several parties.
DEDUPE_LAYER_EVENT = "event_identity"
#: Layer 4 — relation identity: one asserted link between two entities.
DEDUPE_LAYER_RELATION = "relation_identity"

#: Sources whose records describe an *event with parties*.  Collapsing these on
#: the event id alone would delete co-awarded suppliers, which HORIZON explicitly
#: documented as a previously-observed defect class.
PARTY_BEARING_EVENT_SOURCES: frozenset[str] = frozenset(
    {
        "eu_ted",
        "uk_find_a_tender",
        "usaspending",
    }
)


def event_identity_key(source_id: str, source_record_id: str, party: str | None) -> str:
    """Identity of an official *event*, deliberately including the party.

    For a party-bearing source the key is ``source:record:party`` — two suppliers
    named in one award notice are two distinct award facts, not a duplicate.  For
    every other source the party component is empty.
    """
    if source_id in PARTY_BEARING_EVENT_SOURCES:
        return f"{source_id}:{source_record_id}:party={party or 'unattributed'}"
    return f"{source_id}:{source_record_id}"


__all__ = [
    "CLASSIFICATION_SCHEMES",
    "CONSUMED_FIELDS",
    "CONTRACT_ID",
    "CONTRACT_VERSION",
    "DECLARED_SOURCE_FIELDS",
    "DEDUPE_LAYER_ENTITY",
    "DEDUPE_LAYER_EVENT",
    "DEDUPE_LAYER_RECORD",
    "DEDUPE_LAYER_RELATION",
    "EVIDENCE_TYPE_MAP",
    "IDENTIFIER_SCHEME_MAP",
    "IDENTITY_BLOCKING_FLAGS",
    "IDENTITY_GRADES",
    "IDENTITY_GRADE_EFFECTS",
    "NON_PROMOTABLE_RELATION_TYPES",
    "NON_PUBLICATION_HINTS",
    "PARTY_BEARING_EVENT_SOURCES",
    "PRESERVED_ONLY_FIELDS",
    "QUALITY_FLAG_MAP",
    "RECORD_STATUS_FIELDS",
    "RELATION_TYPE_GRADE",
    "SOURCE_SCHEMA",
    "TARGET_SCHEMA",
    "TIME_CLOCKS",
    "TIME_EVIDENCE_FIELDS",
    "UNMAPPABLE_ENTITY_TYPES",
    "classify_identifier",
    "event_identity_key",
    "gtin_check_digit",
    "is_gtin14",
]
