"""ATLAS research layer: as-of queries and the prospective registry."""

from __future__ import annotations

from .asof import BASES, OBSERVED, PUBLIC_INFERRED, UNPROVABLE, as_of, evidence_history
from .prospective import MARKETS, candidate_summary, register_cross_market_candidates

__all__ = [
    "BASES",
    "MARKETS",
    "OBSERVED",
    "PUBLIC_INFERRED",
    "UNPROVABLE",
    "as_of",
    "candidate_summary",
    "evidence_history",
    "register_cross_market_candidates",
]
