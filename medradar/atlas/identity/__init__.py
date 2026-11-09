"""ATLAS identity layer: names, identifiers, companies and relation decisions."""

from __future__ import annotations

from .companies import CompanyIndex
from .models import (
    Company,
    Device,
    ENTITY_TYPES,
    IdentityError,
    Identifier,
    Manufacturer,
    OFFICIAL_SCHEMES,
)
from .normalize import (
    IdentifierError,
    SCHEMES,
    build_identifier,
    identifiers_by_scheme,
    is_gtin_like,
    name_tokens,
    normalize_di,
    normalize_doi,
    normalize_identifier,
    normalize_licence_number,
    normalize_name,
    normalize_patent_number,
    normalize_product_code,
    normalize_regulatory_number,
    token_subsequence,
)
from .resolver import (
    AUTHORITIES,
    CANDIDATE,
    CONFIRMED,
    DERIVED,
    DeviceView,
    IDENTITY_CONFIRMING_TYPES,
    INFERRED,
    MatchDecision,
    POSSIBLE_MATCH,
    REJECTED,
    RELATED_TECHNOLOGY,
    RELATION_TYPES,
    SAME_DEVICE_IDENTITY,
    SAME_MODEL,
    SAME_PRODUCT_FAMILY,
    SOURCE_DECLARED,
    STATUSES,
    UNDECIDED,
    UNKNOWN,
    UNRELATED,
    baseline_name_match,
    compare_devices,
    name_similarity,
    view_from_evidence,
)

__all__ = [name for name in dir() if not name.startswith("_")]
