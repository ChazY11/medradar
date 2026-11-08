"""Shared helpers for the trials / grants connectors.

The clock, company-identity and provenance rules are identical to the scholarly
package, so they are imported rather than re-implemented — one rule, one place to
audit.  This module is only a re-export surface.
"""

from __future__ import annotations

from ..scholarly._common import (
    as_datetime,
    coerce_date,
    company_refs,
    date10,
    metadata_clock_fields,
    nct_ids_in_text,
    provenance,
    raw_block,
    time_block,
)

__all__ = [
    "as_datetime",
    "coerce_date",
    "company_refs",
    "date10",
    "metadata_clock_fields",
    "nct_ids_in_text",
    "provenance",
    "raw_block",
    "time_block",
]
