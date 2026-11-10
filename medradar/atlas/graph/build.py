"""Build source-declared graph relations from stored evidence.

This module only creates relations the **source itself asserts**:

* ``MANUFACTURED_BY``   device record -> company, from the record's own
  manufacturer/company field (and only when the company link is confirmed or
  explicitly recorded as a candidate).
* ``REGISTERED_AS``     device record -> licence/clearance record, from an
  official identifier the record carries.
* ``BELONGS_TO_FAMILY`` device -> licence family, from MDALL's own grouping.

It deliberately does **not** create ``STUDIED_IN``, ``FUNDED_BY`` or
``RELATED_TO_TECHNOLOGY`` links from name similarity: those require evidence
that the pilot does not have.  Inferred identity relations
(``SAME_DEVICE_IDENTITY`` …) are created by the identity resolver, not here.
"""

from __future__ import annotations

from typing import Any, Iterable, Mapping

from ..evidence import schema as ev
from ..identity.pilot import device_ref
from ..store import AtlasStore

SOURCE_DECLARED_RELATIONS = frozenset({"MANUFACTURED_BY", "REGISTERED_AS", "BELONGS_TO_FAMILY"})


def build_source_declared_relations(store: AtlasStore, *, run_id: str = "") -> dict[str, int]:
    counts: dict[str, int] = {}
    evidence_records = list(store.iter_evidence())
    for record in evidence_records:
        ref = device_ref(record)
        for entity_ref in record.get("entity_refs") or []:
            if entity_ref.get("entity_type") != "company":
                continue
            firm_key = entity_ref.get("firm_key")
            if not firm_key:
                continue
            company_id = ev.deterministic_id("co", "firm", str(firm_key))
            relation_id = ev.deterministic_id("rel", ref, company_id, "MANUFACTURED_BY")
            _insert_relation(
                store,
                relation_id=relation_id,
                from_ref=ref, from_type="device",
                to_ref=company_id, to_type="company",
                relation_type="MANUFACTURED_BY",
                status="CONFIRMED" if entity_ref.get("method") in {"official_id", "exact_alias", "multi_field"} else "CANDIDATE",
                method=str(entity_ref.get("method", "none")),
                authority="source_declared",
                confidence=float(entity_ref.get("confidence", 0.0)),
                basis={"name_raw": entity_ref.get("name_raw", ""), "firm_key": firm_key},
                evidence_ids=[record["evidence_id"]],
                run_id=run_id,
            )
            counts["MANUFACTURED_BY"] = counts.get("MANUFACTURED_BY", 0) + 1

        # A licence/clearance number in a record is a source-declared
        # registration relation between the device record and that number.
        for ident in record.get("identifiers") or []:
            if ident.get("scheme") not in {"licence_no", "510k", "pma"}:
                continue
            target = f"{ident['scheme']}:{ident['value']}"
            relation_id = ev.deterministic_id("rel", ref, target, "REGISTERED_AS")
            _insert_relation(
                store,
                relation_id=relation_id,
                from_ref=ref, from_type="device",
                to_ref=target, to_type="regulatory_identifier",
                relation_type="REGISTERED_AS",
                status="CONFIRMED",
                method="official_identifier",
                authority="source_declared",
                confidence=1.0,
                basis={"scheme": ident["scheme"], "value": ident["value"]},
                evidence_ids=[record["evidence_id"]],
                run_id=run_id,
            )
            counts["REGISTERED_AS"] = counts.get("REGISTERED_AS", 0) + 1
    return counts


def _insert_relation(
    store: AtlasStore,
    *,
    relation_id: str,
    from_ref: str,
    from_type: str,
    to_ref: str,
    to_type: str,
    relation_type: str,
    status: str,
    method: str,
    authority: str,
    confidence: float,
    basis: Mapping[str, Any],
    evidence_ids: Iterable[str],
    run_id: str,
) -> None:
    import json

    from ..evidence.timeq import utc_iso

    with store.transaction() as conn:
        existing = conn.execute(
            "SELECT 1 FROM entity_relations WHERE relation_id=?", (relation_id,)
        ).fetchone()
        if existing:
            return
        conn.execute(
            "INSERT INTO entity_relations(relation_id, from_ref, from_type, to_ref, to_type,"
            " relation_type, status, method, authority, confidence, basis_json,"
            " contradictions_json, rejection_reason, evidence_ids_json, created_at, run_id)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, '[]', '', ?, ?, ?)",
            (
                relation_id, from_ref, from_type, to_ref, to_type, relation_type, status,
                method, authority, float(confidence),
                json.dumps(dict(basis), ensure_ascii=False, sort_keys=True),
                json.dumps(list(evidence_ids)), utc_iso(), run_id,
            ),
        )


__all__ = ["SOURCE_DECLARED_RELATIONS", "build_source_declared_relations"]
