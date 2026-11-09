"""Queryable knowledge relations over the ATLAS store.

The queries are the deliverable, not a UI.  Each returns a JSON-serialisable
dict with an explicit ``evidence`` section and an explicit ``status`` so a
caller can tell a source-declared fact from a candidate.

Implemented queries
-------------------
``company_devices``          company -> devices, each with its official identifiers
``device_identity``          device -> identifiers + evidence + source records
``device_research_candidates`` device -> publications/trials **candidates** by
                             product code (empty rather than invented)
``technology_companies``     FDA product code -> companies with devices in it
``relation_evidence``        one relation -> its evidence, basis and history
``rejected_relations``       relations rejected, with the reason
``evidence_path``            company -> device -> identifier -> regulatory record
"""

from __future__ import annotations

import json
from typing import Any, Mapping

from ..evidence import schema as ev
from ..store import AtlasStore


def _company_id(company_key: str) -> str:
    return ev.deterministic_id("co", "firm", company_key)


def _evidence_of(store: AtlasStore, evidence_id: str) -> dict[str, Any] | None:
    record = store.get_evidence(evidence_id)
    if not record:
        return None
    return {
        "evidence_id": record["evidence_id"],
        "source_id": record["source_id"],
        "source_record_id": record["source_record_id"],
        "source_url": record["source_url"],
        "evidence_type": record["evidence_type"],
        "time": record["time"],
        "licence_status": record["licence_status"],
        "identity_resolution_status": record["identity_resolution_status"],
        "quality_flags": record["quality_flags"],
    }


def company_devices(store: AtlasStore, company_key: str) -> dict[str, Any]:
    company_id = _company_id(company_key)
    company = store.query("SELECT * FROM companies WHERE company_id=?", (company_id,))
    devices = store.query(
        "SELECT device_id, canonical_name, brand_name, model_number, device_class,"
        " markets_json, metadata_json FROM devices WHERE company_id=? ORDER BY canonical_name",
        (company_id,),
    )
    out = []
    for device in devices:
        idents = store.query(
            "SELECT scheme, value, issuer, is_primary FROM device_identifiers WHERE device_id=?"
            " ORDER BY is_primary DESC, scheme",
            (device["device_id"],),
        )
        meta = json.loads(device.get("metadata_json") or "{}")
        out.append(
            {
                "device_ref": device["device_id"],
                "canonical_name": device["canonical_name"],
                "brand_name": device["brand_name"],
                "model_number": device["model_number"],
                "device_class": device["device_class"],
                "markets": json.loads(device["markets_json"] or "[]"),
                "identifiers": idents,
                "evidence": _evidence_of(store, meta.get("evidence_id", "")),
            }
        )
    return {
        "query": "company_devices",
        "company_key": company_key,
        "company": company[0] if company else None,
        "count": len(out),
        "devices": out,
        "note": "Every device row is backed by an evidence record; identifiers keep their scheme.",
    }


def device_identity(store: AtlasStore, device_ref: str) -> dict[str, Any]:
    rows = store.query("SELECT * FROM devices WHERE device_id=?", (device_ref,))
    if not rows:
        return {"query": "device_identity", "device_ref": device_ref, "found": False}
    device = rows[0]
    idents = store.query(
        "SELECT scheme, value, issuer, is_primary, evidence_id FROM device_identifiers"
        " WHERE device_id=? ORDER BY is_primary DESC, scheme",
        (device_ref,),
    )
    relations = store.query(
        "SELECT relation_id, relation_type, status, method, authority, confidence,"
        " evidence_ids_json, rejection_reason FROM entity_relations"
        " WHERE (from_ref=? OR to_ref=?) AND revoked_at=''",
        (device_ref, device_ref),
    )
    for relation in relations:
        relation["evidence_ids"] = json.loads(relation.pop("evidence_ids_json"))
    return {
        "query": "device_identity",
        "device_ref": device_ref,
        "found": True,
        "device": device,
        "identifiers": idents,
        "relations": relations,
        "note": "Identifiers are scheme-specific; a DI is not interchangeable with a licence number.",
    }


def device_research_candidates(store: AtlasStore, device_ref: str) -> dict[str, Any]:
    """Honest empty-by-default research linkage.

    ATLAS-001 did not collect publications/trials for devices.  Returning an
    empty *candidate* list with the reason is the correct answer; inventing a
    link from a product code would be the error this project exists to avoid.
    """
    rows = store.query(
        "SELECT GROUP_CONCAT(product_code) AS codes FROM device_product_codes WHERE device_id=?",
        (device_ref,),
    )
    codes = [c for c in str(rows[0]["codes"] or "").split(",") if c] if rows else []
    return {
        "query": "device_research_candidates",
        "device_ref": device_ref,
        "product_codes": codes,
        "candidates": [],
        "status": "NOT_COLLECTED",
        "reason": "publications/trials were not collected for devices in ATLAS-001; "
                  "a product-code match would be a candidate, not proof of study",
    }


def technology_companies(store: AtlasStore, product_code: str) -> dict[str, Any]:
    code = str(product_code).strip().upper()
    rows = store.query(
        "SELECT d.device_id, d.canonical_name, d.brand_name, d.company_id, c.canonical_name AS company_name"
        " FROM device_product_codes pc JOIN devices d ON d.device_id=pc.device_id"
        " LEFT JOIN companies c ON c.company_id=d.company_id"
        " WHERE pc.product_code=? ORDER BY c.canonical_name, d.canonical_name",
        (code,),
    )
    companies: dict[str, dict[str, Any]] = {}
    for row in rows:
        key = row["company_name"] or "(unresolved company)"
        entry = companies.setdefault(key, {"company": key, "devices": [], "evidence_count": 0})
        entry["devices"].append({"device_ref": row["device_id"], "name": row["canonical_name"],
                                 "brand": row["brand_name"]})
        entry["evidence_count"] += 1
    return {
        "query": "technology_companies",
        "product_code": code,
        "companies": list(companies.values()),
        "note": "A shared FDA product code is a technology category, not evidence of collaboration.",
    }


def relation_evidence(store: AtlasStore, relation_id: str) -> dict[str, Any]:
    rows = store.query("SELECT * FROM entity_relations WHERE relation_id=?", (relation_id,))
    if not rows:
        return {"query": "relation_evidence", "relation_id": relation_id, "found": False}
    relation = dict(rows[0])
    evidence_ids = json.loads(relation.pop("evidence_ids_json") or "[]")
    relation["relation_evidence"] = [_evidence_of(store, eid) for eid in evidence_ids]
    relation["history"] = store.query(
        "SELECT action, at, reason FROM relation_events WHERE relation_id=? ORDER BY event_id",
        (relation_id,),
    )
    return {"query": "relation_evidence", "relation_id": relation_id, "found": True,
            "relation": relation}


def rejected_relations(store: AtlasStore, limit: int = 20) -> dict[str, Any]:
    rows = store.query(
        "SELECT relation_id, relation_type, method, authority, confidence, rejection_reason,"
        " basis_json FROM entity_relations WHERE status='REJECTED' AND revoked_at=''"
        " ORDER BY relation_id LIMIT ?",
        (int(limit),),
    )
    for row in rows:
        row["basis"] = json.loads(row.pop("basis_json") or "{}")
    return {
        "query": "rejected_relations",
        "count": len(rows),
        "rejected": rows,
        "note": "Rejections are evidence too: they record why a name-only match was refused.",
    }


def evidence_path(store: AtlasStore, company_key: str) -> dict[str, Any]:
    """One complete, real chain: company -> device -> official id -> regulatory record."""
    base = company_devices(store, company_key)
    chains = []
    for device in base["devices"]:
        official = [i for i in device["identifiers"] if i["scheme"] in {"di", "licence_no", "510k", "pma"}]
        if not official:
            continue
        regulatory = []
        # The record that established the device is itself a regulatory record
        # (GUDID registration, MDALL licence).  Linked clearances are added only
        # when an official identifier actually joins them.
        if device.get("evidence"):
            regulatory.append(device["evidence"])
        for ident in official:
            key = f"{ident['scheme']}:{ident['value']}"
            for record in store.evidence_for_canonical_key(key):
                if record.get("evidence_type") in {"regulatory_clearance", "regulatory_approval"}:
                    entry = _evidence_of(store, record["evidence_id"])
                    if entry and entry["evidence_id"] not in {r["evidence_id"] for r in regulatory}:
                        regulatory.append(entry)
        chains.append(
            {
                "company": base["company"]["canonical_name"] if base["company"] else company_key,
                "device": {"device_ref": device["device_ref"], "brand": device["brand_name"],
                           "model": device["model_number"]},
                "official_identity": official,
                "regulatory_records": regulatory,
                "evidence": device["evidence"],
                "chain_complete": bool(regulatory and device["evidence"]),
            }
        )
        if len(chains) >= 20:
            break
    return {
        "query": "evidence_path",
        "company_key": company_key,
        "chains": chains,
        "note": "chain_complete is false when the device has no linked regulatory record; "
                "ATLAS does not fill that gap with inference.",
    }


__all__ = [
    "company_devices",
    "device_identity",
    "device_research_candidates",
    "evidence_path",
    "rejected_relations",
    "relation_evidence",
    "technology_companies",
]
