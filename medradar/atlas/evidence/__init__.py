"""ATLAS evidence layer: the record contract, time semantics and bounded HTTP."""

from __future__ import annotations

from . import schema, timeq
from .http import (
    BudgetExceeded,
    DEFAULT_USER_AGENT,
    HttpClient,
    HttpLedger,
    HttpResult,
    RateLimiter,
    sha256_bytes,
    utc_iso,
    with_params,
)
from .schema import (
    EVIDENCE_TYPES,
    EvidenceError,
    IDENTITY_STATUSES,
    LICENCE_STATUSES,
    QUALITY_FLAGS,
    RELATION_STATUSES,
    SCHEMA_ID,
    SCHEMA_VERSION,
    TIME_QUALITIES,
    canonical_key,
    is_independent,
    make_evidence,
    make_evidence_id,
    require_valid,
    sha256_json,
    sha256_text,
    validate_evidence,
)
from .timeq import (
    build_time,
    check_ordering,
    implied_quality,
    iso,
    lead_time_days,
    parse_date,
    parse_datetime,
    quality_allows_lead_time,
)

__all__ = [name for name in dir() if not name.startswith("_")]
