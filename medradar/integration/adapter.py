"""``HorizonToAtlasAdapter`` — convert ``horizon.evidence.v1`` into ATLAS evidence.

The adapter is deliberately not a renamer.  It applies
:mod:`medradar.integration.contract` to answer, per record, four questions the
field names cannot answer on their own:

* **What kind of fact is this?** ``entity_type`` → ATLAS ``evidence_type``, with
  an explicit refusal for anything the target cannot represent.
* **What is this identifier, really?** Scheme is decided by value where the
  source field mixes namespaces (MDALL catalogue tokens vs GTIN-14 UDI-DIs).
* **How certain is this?** HORIZON's record-level statuses are preserved as
  *source assertions* and never become ATLAS identity resolution.  A record
  enters ATLAS with ``identity_resolution_status="not_attempted"``; identity can
  only be established later, by :mod:`medradar.integration.graph`, through an
  authoritative identifier match.
* **May we keep it?** The licence gate runs before anything else and fails
  closed.

Nothing is dropped silently.  Every source field is either consumed into a real
ATLAS home or preserved verbatim under ``normalized.horizon``; the conversion
manifest records which is which, and any field the adapter has never seen is
reported as an extension rather than discarded.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping

from medradar.atlas.evidence import schema as atlas_schema
from medradar.atlas.evidence.timeq import utc_iso

from . import clock, contract
from .licence import LicenceError, LicencePolicy

MAPPING_VERSION = f"{contract.CONTRACT_VERSION}+adapter.1"

#: ATLAS quality flags that may be set by the adapter directly.
_KNOWN_ATLAS_FLAGS = set(atlas_schema.QUALITY_FLAGS)


@dataclass
class ConversionResult:
    """Outcome of converting exactly one source record."""

    source_id: str
    source_record_id: str
    status: str  # "converted" | "degraded" | "rejected"
    evidence: dict[str, Any] | None = None
    reason: str = ""
    warnings: list[str] = field(default_factory=list)
    lost_fields: list[str] = field(default_factory=list)
    preserved_fields: list[str] = field(default_factory=list)
    extension_fields: list[str] = field(default_factory=list)
    identifier_decisions: list[dict[str, Any]] = field(default_factory=list)
    relation_claims: list[dict[str, Any]] = field(default_factory=list)
    mapping_version: str = MAPPING_VERSION

    @property
    def ok(self) -> bool:
        return self.status in {"converted", "degraded"}

    def as_manifest_row(self) -> dict[str, Any]:
        """Compact record for the versioned conversion manifest."""
        return {
            "source_id": self.source_id,
            "source_record_id": self.source_record_id,
            "status": self.status,
            "reason": self.reason,
            "warnings": self.warnings,
            "lost_fields": self.lost_fields,
            "preserved_fields": self.preserved_fields,
            "extension_fields": self.extension_fields,
            "output_evidence_id": (self.evidence or {}).get("evidence_id"),
            "output_canonical_key": (self.evidence or {}).get("canonical_key"),
            "output_licence_status": (self.evidence or {}).get("licence_status"),
            "output_identity_status": (self.evidence or {}).get("identity_resolution_status"),
            "relation_grades": sorted({c["grade"] for c in self.relation_claims}),
            "mapping_version": self.mapping_version,
        }


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _canonical(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


class HorizonToAtlasAdapter:
    """Stateless converter.  One instance can convert a whole export."""

    def __init__(
        self,
        policy: LicencePolicy | None = None,
        *,
        mapping_version: str = MAPPING_VERSION,
    ) -> None:
        self.policy = policy or LicencePolicy.load()
        self.mapping_version = mapping_version

    # ------------------------------------------------------------------ public
    def adapt(
        self,
        record: Mapping[str, Any],
        *,
        run_id: str = "",
        import_started_at: str | None = None,
        raw_line: bytes | None = None,
        record_discriminator: str = "",
    ) -> ConversionResult:
        """Convert one HORIZON record into one ATLAS evidence record.

        ``raw_line`` is the exact source bytes when available; passing it lets
        the record bind to the upstream file content rather than to a re-serialised
        copy.  ``import_started_at`` is used only as a fetch-clock fallback and is
        recorded as such.

        ``record_discriminator`` exists because ``source_record_id`` is **not**
        unique within a source: an FDA PMA number covers several supplements and an
        establishment registration number covers several establishment types, each
        a distinct record with a distinct content hash.  ATLAS derives the evidence
        id from ``(source, record_type, source_record_id)``; without a
        discriminator those distinct records would collapse into versions of one
        record and silently disappear from ``evidence_head``.  When the importer
        detects such a collision it passes a stable content-derived discriminator,
        which is appended to the id *basis* only — the stored
        ``source_record_id`` stays exactly what the source said, and the original
        remains in provenance.
        """
        run_started = import_started_at or utc_iso()
        source_id = str(record.get("source_id") or "")
        source_record_id = str(record.get("source_record_id") or "")
        result = ConversionResult(
            source_id=source_id,
            source_record_id=source_record_id,
            status="rejected",
            mapping_version=self.mapping_version,
        )

        # -- 0. structural gates ---------------------------------------------
        declared = record.get("schema_version")
        if declared != contract.SOURCE_SCHEMA:
            result.reason = f"unsupported_source_schema:{declared!r}"
            return result
        if not source_id or not source_record_id:
            result.reason = "missing_source_identity"
            return result

        entity_type = str(record.get("entity_type") or "")
        evidence_type = contract.EVIDENCE_TYPE_MAP.get(entity_type)
        if evidence_type is None or entity_type in contract.UNMAPPABLE_ENTITY_TYPES:
            result.reason = f"unmappable_entity_type:{entity_type!r}"
            return result

        # -- 1. licence gate (before any parsing work) -----------------------
        licence_raw = str(record.get("licence_status") or "unknown")
        atlas_licence = _map_licence_status(licence_raw)
        if not self.policy.may_ingest(source_id, licence_raw):
            result.reason = (
                f"licence_blocked:{licence_raw!r} under policy "
                f"{self.policy.payload.get('policy_id')!r}"
            )
            return result

        # -- 2. identifiers --------------------------------------------------
        identifiers, id_decisions, id_warnings = self._convert_identifiers(record)
        result.identifier_decisions = id_decisions
        result.warnings.extend(id_warnings)

        # -- 3. clocks -------------------------------------------------------
        time_block, time_warnings = clock.build_time_block(
            record, import_run_started_at=run_started
        )
        result.warnings.extend(time_warnings)

        # -- 4. quality flags ------------------------------------------------
        source_flags = [str(f) for f in (record.get("quality_flags") or [])]
        atlas_flags, untranslated = _map_quality_flags(source_flags)
        if untranslated:
            result.warnings.append(
                "quality_flags_preserved_without_atlas_equivalent:" + ",".join(sorted(untranslated))
            )
        if not self.policy.may_redistribute(source_id, licence_raw):
            atlas_flags.add("licence_restricted")
        if not time_block.get("source_public_at"):
            atlas_flags.add("missing_time")
        if not record.get("manufacturer"):
            atlas_flags.add("missing_company")
        if record.get("identity_status") not in {None, "CONFIRMED"}:
            atlas_flags.add("unverified_identity")
        if contract.IDENTITY_BLOCKING_FLAGS & set(source_flags):
            atlas_flags.add("unverified_identity")
        if not identifiers:
            atlas_flags.add("missing_primary_identifier")

        # -- 5. relations (claims only; never identity) ----------------------
        relation_claims = self._grade_relations(record)
        result.relation_claims = relation_claims
        relation_status = _aggregate_relation_status(relation_claims)

        # -- 6. preserve the source record losslessly ------------------------
        normalized = {
            "horizon": dict(record),
            "convergence": {
                "contract_id": contract.CONTRACT_ID,
                "contract_version": contract.CONTRACT_VERSION,
                "mapping_version": self.mapping_version,
                "source_schema": contract.SOURCE_SCHEMA,
                "source_entity_type": entity_type,
                "target_evidence_type": evidence_type,
                "source_record_status": {
                    k: record.get(k) for k in contract.RECORD_STATUS_FIELDS
                },
                "source_quality_flags": source_flags,
                "identifier_decisions": id_decisions,
                "relation_grades": relation_claims,
                "licence_raw_status": licence_raw,
                "time_basis": {
                    "observation_basis": time_block.get("observation_basis"),
                    "source_public_at_basis": time_block.get("source_public_at_basis"),
                },
            },
        }
        result.preserved_fields = list(contract.PRESERVED_ONLY_FIELDS)
        declared_fields = set(record.keys())
        result.extension_fields = sorted(declared_fields - contract.DECLARED_SOURCE_FIELDS)

        # -- 7. content hashes ------------------------------------------------
        upstream_hash = str(record.get("content_hash") or "")
        if atlas_schema._HEX64.match(upstream_hash):  # noqa: SLF001 - documented reuse
            source_content_hash = upstream_hash
            hash_basis = "upstream_source_content_hash"
        else:
            source_content_hash = _sha256(_canonical(record).encode("utf-8"))
            hash_basis = "recomputed_from_parsed_record"
        raw_bytes = len(raw_line) if raw_line is not None else len(_canonical(record).encode("utf-8"))
        if raw_line is not None:
            line_hash = _sha256(raw_line)
        else:
            line_hash = source_content_hash

        # -- 8. build the ATLAS record ---------------------------------------
        try:
            evidence = atlas_schema.make_evidence(
                source_id=source_id,
                source_record_id=source_record_id,
                evidence_type=evidence_type,
                source_url=str(record.get("source_url") or ""),
                raw_content_hash=source_content_hash,
                raw_bytes=raw_bytes,
                normalized=normalized,
                time=time_block,
                identifiers=identifiers,
                entity_refs=(),
                canonical_entity_id="",
                # Imported records have NOT been identity-resolved.  This is the
                # single most important line in the adapter.
                identity_resolution_status="not_attempted",
                relation_status=relation_status,
                licence_status=atlas_licence,
                quality_flags=sorted(atlas_flags),
                provenance={
                    "source_name": source_id,
                    "attribution": str(record.get("licence_note") or ""),
                    "evidence_reference": str(record.get("raw_ref") or ""),
                    "source_time_quality": time_block.get("source_public_at_quality", "unknown"),
                    "raw_bytes": raw_bytes,
                    "raw_path": str(record.get("raw_ref") or ""),
                    "upstream_authority": source_id,
                },
                collection_run_id=run_id,
            )
        except atlas_schema.EvidenceError as exc:
            result.reason = f"contract_violation:{exc}"
            return result

        # Extra provenance that ATLAS's fixed provenance block does not carry.
        evidence["provenance"].update(
            {
                "source_content_hash_basis": hash_basis,
                "ingested_line_sha256": line_hash,
                "source_licence_status": licence_raw,
                "adapter_mapping_version": self.mapping_version,
                "conversion_warnings": result.warnings,
                "source_entity_type": entity_type,
            }
        )

        if record_discriminator:
            # Distinct records share a source_record_id; keep both, with a
            # deterministic id basis that includes the content discriminator.
            evidence["evidence_id"] = atlas_schema.deterministic_id(
                "ev",
                source_id,
                evidence_type,
                f"{source_record_id}#{record_discriminator}",
            )
            evidence["provenance"]["source_record_id_original"] = source_record_id
            evidence["provenance"]["record_identity_disambiguator"] = record_discriminator
            evidence["provenance"]["record_identity_disambiguated"] = True

        problems = atlas_schema.validate_evidence(evidence)
        if problems:
            result.reason = "contract_violation:" + "; ".join(problems)
            return result

        result.evidence = evidence
        result.status = "degraded" if result.warnings else "converted"
        if result.status == "degraded" and not result.reason:
            result.reason = "converted_with_warnings"
        return result

    # ---------------------------------------------------------------- helpers
    def _convert_identifiers(
        self, record: Mapping[str, Any]
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[str]]:
        """Translate identifiers, deciding scheme by value where required."""
        out: list[dict[str, Any]] = []
        decisions: list[dict[str, Any]] = []
        warnings: list[str] = []
        seen: set[tuple[str, str]] = set()
        for ident in record.get("identifiers") or []:
            if not isinstance(ident, Mapping):
                warnings.append("identifier_not_an_object")
                continue
            raw_scheme = str(ident.get("scheme") or "").strip()
            raw_value = ident.get("value")
            value = str(raw_value).strip() if raw_value is not None else ""
            if not raw_scheme or not value:
                warnings.append("identifier_without_scheme_or_value")
                continue
            is_primary = bool(ident.get("is_primary"))
            atlas_scheme, derivation = contract.classify_identifier(
                raw_scheme, value, is_primary=is_primary
            )
            key = (atlas_scheme, value)
            if key in seen:
                decisions.append(
                    {
                        "source_scheme": raw_scheme,
                        "value": value,
                        "atlas_scheme": atlas_scheme,
                        "skipped": "duplicate_within_record",
                    }
                )
                continue
            seen.add(key)
            if derivation.get("role") == "classification":
                warnings.append(f"classification_carried_as_identifier:{atlas_scheme}")
            out.append(
                {
                    "scheme": atlas_scheme,
                    "value": value,
                    "issuer": str(ident.get("issuing_authority") or ""),
                    "scope": str(ident.get("scope") or ""),
                    "is_primary": is_primary,
                }
            )
            decisions.append(
                {
                    "source_scheme": raw_scheme,
                    "value": value,
                    "atlas_scheme": atlas_scheme,
                    "is_primary": is_primary,
                    "gtin14_valid": derivation.get("gtin14_valid"),
                    "derivation": derivation.get("derivation"),
                    "role": derivation.get("role", "identifier"),
                }
            )
        return out, decisions, warnings

    def _grade_relations(self, record: Mapping[str, Any]) -> list[dict[str, Any]]:
        """Convert source relations into graded claims; never into identity."""
        claims: list[dict[str, Any]] = []
        for rel in record.get("relations") or []:
            if not isinstance(rel, Mapping):
                continue
            rel_type = str(rel.get("relation_type") or rel.get("type") or "")
            grade = contract.RELATION_TYPE_GRADE.get(rel_type, "UNVERIFIED_RELATION")
            if rel_type in contract.NON_PROMOTABLE_RELATION_TYPES and grade == "AUTHORITATIVE_ID_MATCH":
                # Belt and braces: the guard must hold even if the table changes.
                grade = "CANDIDATE_RELATION"
            effects = contract.IDENTITY_GRADE_EFFECTS[grade]
            claims.append(
                {
                    "relation_type": rel_type,
                    "grade": grade,
                    "atlas_relation_status": effects["atlas_relation_status"],
                    "atlas_identity_status": effects["atlas_identity_status"],
                    "may_set_confirmed_identity": effects["may_set_confirmed_identity"],
                    "basis": {k: v for k, v in rel.items() if k not in {"relation_type", "type"}},
                    "raw": dict(rel),
                }
            )
        return claims


# ---------------------------------------------------------------------------
# module-level helpers
# ---------------------------------------------------------------------------
def _map_licence_status(raw: str) -> str:
    """HORIZON/registry licence vocabulary → ATLAS ``LICENCE_STATUSES``."""
    mapping = {
        "public_domain": "public_domain",
        "open_licence": "open_licence",
        "open": "open_licence",
        "open_no_explicit_licence": "open_no_explicit_licence",
        "terms_restricted": "restricted",
        "restricted": "restricted",
        "unknown": "unknown",
    }
    mapped = mapping.get(raw, "unknown")
    return mapped if mapped in atlas_schema.LICENCE_STATUSES else "unknown"


def _map_quality_flags(source_flags: Iterable[str]) -> tuple[set[str], set[str]]:
    """Translate flags; return (atlas_flags, untranslated_source_flags)."""
    atlas: set[str] = set()
    untranslated: set[str] = set()
    for flag in source_flags:
        mapped = contract.QUALITY_FLAG_MAP.get(flag)
        if mapped and mapped in _KNOWN_ATLAS_FLAGS:
            atlas.add(mapped)
        elif flag in _KNOWN_ATLAS_FLAGS:
            atlas.add(flag)
        else:
            untranslated.add(flag)
    return atlas, untranslated


def _aggregate_relation_status(claims: list[Mapping[str, Any]]) -> str:
    """Record-level relation status: the weakest grade present, never the strongest.

    A record that contains one candidate relation is a record with a candidate
    relation, regardless of how many asserted relations it also carries.  Taking
    the maximum here would let a single soft link launder a whole record.
    """
    if not claims:
        return "none"
    statuses = {str(c.get("atlas_relation_status")) for c in claims}
    for weakest in ("contradicted", "unknown", "candidate", "asserted_by_source", "none"):
        if weakest in statuses:
            return weakest
    return "unknown"


__all__ = ["ConversionResult", "HorizonToAtlasAdapter", "MAPPING_VERSION"]
