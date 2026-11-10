"""CONVERGENCE: the integration layer between HORIZON data and the ATLAS substrate.

ATLAS provides the unified structure (evidence records, four clocks, identity
separation, versioned relations).  HORIZON provides the global data (24 sources,
a versioned evidence export with per-file SHA-256).  CONVERGENCE is the layer
that proves the two actually work together, and refuses to do so dishonestly.

Modules
-------
``contract``
    Field, identifier, time and identity semantics.  Data only — no I/O.
``clock``
    Strict four-clock conversion; never fabricates an observation history.
``licence``
    Query / analyse / redistribute rights, fail-closed.
``adapter``
    ``HorizonToAtlasAdapter``: one HORIZON record → one validated ATLAS record.
``dedupe``
    Four separate identity layers (record, entity, event, relation).
``staging``
    A *new, isolated* SQLite database built on ATLAS's own append-only store.
``graph``
    Cross-source relations built only from authoritative identifiers, with
    candidates kept apart from confirmations.
``cli``
    ``python -m medradar.integration ...``
"""

from __future__ import annotations

from .adapter import ConversionResult, HorizonToAtlasAdapter, MAPPING_VERSION
from .contract import (
    CONTRACT_ID,
    CONTRACT_VERSION,
    EVIDENCE_TYPE_MAP,
    IDENTITY_GRADES,
    IDENTITY_GRADE_EFFECTS,
    SOURCE_SCHEMA,
    TARGET_SCHEMA,
    gtin_check_digit,
    is_gtin14,
)
from .licence import LicenceError, LicencePolicy

__version__ = "1.0.0"

__all__ = [
    "CONTRACT_ID",
    "CONTRACT_VERSION",
    "ConversionResult",
    "EVIDENCE_TYPE_MAP",
    "HorizonToAtlasAdapter",
    "IDENTITY_GRADES",
    "IDENTITY_GRADE_EFFECTS",
    "LicenceError",
    "LicencePolicy",
    "MAPPING_VERSION",
    "SOURCE_SCHEMA",
    "TARGET_SCHEMA",
    "__version__",
    "gtin_check_digit",
    "is_gtin14",
]
