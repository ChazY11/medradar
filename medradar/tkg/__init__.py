"""Temporal knowledge graph (TKG) MVP: append-only bitemporal store,
as-of query with independent ``known_at``/``valid_at`` cutoffs, deterministic
point-in-time export, and a read-only adapter from the existing events table.

System-knowledge clock only: public availability times may ride along as
optional source metadata but are never used as a clock. See
``docs/research/TKG_ADR.md``.
"""

from .adapter import ADAPTER_VERSION, SourceReadOnlyError, import_events, open_source
from .export import FORMAT, FORMAT_VERSION, export_snapshot, write_export
from .query import TKGQuery
from .store import (
    SCHEMA_VERSION,
    ClockRegressionError,
    IdempotencyConflict,
    TKGError,
    TKGStore,
    TKGValidationError,
    canonical_json,
    normalize_moment,
    sha256_hex,
)

__all__ = [
    "ADAPTER_VERSION",
    "ClockRegressionError",
    "FORMAT",
    "FORMAT_VERSION",
    "IdempotencyConflict",
    "SCHEMA_VERSION",
    "SourceReadOnlyError",
    "TKGError",
    "TKGQuery",
    "TKGStore",
    "TKGValidationError",
    "canonical_json",
    "export_snapshot",
    "import_events",
    "normalize_moment",
    "open_source",
    "sha256_hex",
    "write_export",
]
