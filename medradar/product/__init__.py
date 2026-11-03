"""MedRadar 2.0 product layer (read-only over the research store)."""
from __future__ import annotations

from .catalog import PRODUCT_SCHEMA, PRODUCT_VERSION

__all__ = ["PRODUCT_VERSION", "PRODUCT_SCHEMA"]
