"""Evidence-backed product/technology edges from existing FDA mappings."""
from __future__ import annotations

from typing import Any


def materialize_regulatory_edges(store: Any) -> int:
    rows = store.conn.execute(
        "SELECT company_key,product_code,track_id,MIN(event_date),MIN(available_at),MIN(event_id) "
        "FROM events WHERE kind IN ('510k','pma') AND company_key IS NOT NULL "
        "AND product_code IS NOT NULL AND track_id IS NOT NULL "
        "GROUP BY company_key,product_code,track_id"
    ).fetchall()
    for company, product, track, valid_time, available_at, evidence in rows:
        store.add_observed_edge(
            subject=company, relation="COMPANY_DEVELOPS_PRODUCT", object=product,
            valid_time=valid_time, available_at=available_at, source="openfda_regulatory_event",
            evidence_id=evidence, object_type="Product",
        )
        store.add_observed_edge(
            subject=product, relation="PRODUCT_BELONGS_TO_TECHNOLOGY", object=track,
            valid_time=valid_time, available_at=available_at, source="medradar_product_code_mapping",
            evidence_id=evidence, subject_type="Product", object_type="Technology",
        )
    store.conn.commit()
    return len(rows) * 2
