"""MedRadar product layer: the medical technology intelligence workbench.

This package is the PRODUCT-001 deliverable. It reads one immutable openFDA snapshot
(medradar/product/snapshot/) and exposes:

* dataset.py  - attribution, categorisation, counting, coverage (the measurement layer)
* identity.py - organization registry and exact applicant attribution
* compare.py  - conservative side-by-side comparison with coverage warnings
* export.py   - CSV and Markdown exports that reproduce the screen exactly
* api.py      - FastAPI routes and static UI serving

It does not modify research data or the research modules.
"""
from __future__ import annotations

__all__ = ["PRODUCT_NAME", "PRODUCT_VERSION", "POSITIONING_EN", "POSITIONING_ZH"]

PRODUCT_NAME = "MedRadar"
PRODUCT_VERSION = "2.1.0-data-001"
POSITIONING_EN = "Medical technology intelligence platform"
POSITIONING_ZH = "医疗技术情报与竞争分析平台"
