"""One connector contract for every ATLAS source.

Each connector exposes the same six operations, so the runner can treat sources
identically and a new source cannot quietly invent a seventh behaviour:

``fetch``      bounded, logged HTTP (through :class:`HttpClient`)
``normalize``  projection onto the fields ATLAS actually reads
``validate``   reject records that break the evidence contract
``identify``   attach official identifiers and company candidate tiers
``version``    content hash + deterministic evidence id
``store``      append to the evidence store (never update in place)

A connector never writes to the database itself; it returns evidence records
and the runner stores them.  That keeps the write path single and auditable.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping

from .. import config
from ..evidence import schema as ev
from ..evidence.timeq import utc_iso
from ..identity import CompanyIndex


@dataclass(frozen=True)
class Provenance:
    source_name: str
    licence_status: str
    attribution: str
    evidence_reference: str
    upstream_authority: str
    source_time_quality: str = "day"

    def to_dict(self) -> dict[str, Any]:
        return dict(self.__dict__)


class Connector:
    """Base class: subclasses implement ``fetch``/``normalize``."""

    connector_id: str = ""
    source_id: str = ""
    evidence_type: str = ""
    rate_limit: str = ""
    provenance: Provenance

    def __init__(self, client: Any) -> None:
        self.client = client
        self.company_index = CompanyIndex.from_config()

    # ------------------------------------------------------------------ hooks
    def fetch(self, *args: Any, **kwargs: Any) -> Any:  # pragma: no cover - abstract
        raise NotImplementedError

    def normalize(self, raw: Mapping[str, Any]) -> dict[str, Any]:  # pragma: no cover
        raise NotImplementedError

    # --------------------------------------------------------------- evidence
    def evidence(
        self,
        raw: Mapping[str, Any],
        normalized: Mapping[str, Any],
        *,
        source_record_id: str,
        source_url: str,
        identifiers: Iterable[Mapping[str, Any]],
        time_block: Mapping[str, Any],
        collection_run_id: str,
        company_name: str = "",
        current_di: str = "",
        quality_flags: Iterable[str] = (),
        relation_status: str = "none",
        canonical_entity_id: str = "",
        source_record_bytes: bytes | None = None,
    ) -> dict[str, Any]:
        """Build one validated evidence record (content-addressed per record)."""
        record_bytes = source_record_bytes or ev.canonical_json(dict(raw)).encode("utf-8")
        raw_hash = ev.sha256_bytes(record_bytes)
        idents = [dict(i) for i in identifiers if i]
        refs = self._company_refs(company_name)
        identity_status = "none"
        if refs:
            identity_status = (
                "confirmed"
                if refs[0]["method"] in {"official_id", "exact_alias", "multi_field"}
                else "candidate"
            )
        flags = set(quality_flags)
        if not idents:
            flags.add("missing_primary_identifier")
        if company_name and not refs:
            flags.add("missing_company")
        if not time_block.get("source_public_at"):
            flags.add("missing_time")
        if time_block.get("source_public_at_quality") in {"coarse", "derived"}:
            flags.add("coarse_time" if time_block["source_public_at_quality"] == "coarse" else "derived_time")
        if self.provenance.licence_status == "restricted":
            flags.add("licence_restricted")

        record = ev.make_evidence(
            source_id=self.source_id,
            source_record_id=source_record_id,
            evidence_type=self.evidence_type,
            source_url=source_url,
            raw_content_hash=raw_hash,
            raw_bytes=len(record_bytes),
            normalized=normalized,
            time=time_block,
            identifiers=idents,
            entity_refs=refs,
            canonical_entity_id=canonical_entity_id,
            identity_resolution_status=identity_status,
            relation_status=relation_status,
            licence_status=self.provenance.licence_status,
            quality_flags=flags,
            provenance=self.provenance.to_dict(),
            collection_run_id=collection_run_id,
        )
        problems = ev.validate_evidence(record)
        if problems:
            raise ev.EvidenceError(f"{self.source_id}/{source_record_id}: {'; '.join(problems)}")
        _ = current_di  # retained for call-site readability
        return record

    def _company_refs(self, name: Any) -> list[dict[str, Any]]:
        if not name:
            return []
        resolution = self.company_index.resolve(name)
        if resolution.get("method") == "none":
            return []
        return [resolution]


# --------------------------------------------------------------------- helpers
def clean(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def provenance_of(source_id: str) -> Provenance:
    """Look up a source's licence/attribution in the committed register."""
    source = config.load_sources().get(source_id, {})
    return Provenance(
        source_name=str(source.get("name", source_id)),
        licence_status=str(source.get("licence_status", "unknown")),
        attribution=str(source.get("attribution", "")),
        evidence_reference=str(source.get("endpoint", "")),
        upstream_authority=str(source.get("upstream_authority", source_id)),
        source_time_quality=str(source.get("source_time_quality", "day")),
    )


def json_bytes(payload: Any) -> bytes:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")


__all__ = ["Connector", "Provenance", "clean", "json_bytes", "provenance_of"]
