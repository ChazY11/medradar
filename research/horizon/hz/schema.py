"""horizon.evidence.v1 — the versioned data-exchange contract with ATLAS-001.

Design rules (enforced here, not merely documented):

1. A missing field is ``None``. It is never filled in with a guess.
2. Every record carries ``content_hash`` over a canonical subset of its own
   content, so ATLAS-001 can deduplicate without trusting our row order.
3. ``identity_status`` and ``evidence_status`` are separate axes.
   ACCESS SUCCESS != DATA SUCCESS != IDENTITY SUCCESS != RESEARCH SUCCESS.
4. Times are split into four clocks (see ``timeq``) because the whole point of
   the frontier work is that "published", "filed" and "we saw it" differ.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field, asdict
from typing import Any, Iterable

SCHEMA_VERSION = "horizon.evidence.v1"

# --------------------------------------------------------------------------
# controlled vocabularies (kept deliberately small and closed)
# --------------------------------------------------------------------------

ENTITY_TYPES = {
    "patent_publication",
    "regulatory_listing",       # a device as registered / listed by an authority
    "regulatory_clearance",     # 510(k), PMA, licence, certificate
    "product_identifier",       # UDI-DI, GTIN, device identifier
    "publication",              # scholarly work
    "clinical_trial",
    "grant",
    "procurement_award",
    "trade_flow",
    "organisation",
    "postmarket_event",
    "recall",
}

IDENTITY_STATUS = {"UNKNOWN", "CANDIDATE", "CONFIRMED"}
EVIDENCE_STATUS = {"CANDIDATE", "CONFIRMED", "REJECTED"}
LICENCE_STATUS = {
    "open_licence",              # explicit reuse licence (CC-BY etc.)
    "public_domain",
    "open_no_explicit_licence",  # publicly readable, no stated reuse licence
    "terms_restricted",          # terms allow some automated access, with limits
    "requires_registration",     # free but keyed
    "requires_licence",          # paid / contractual
    "unknown",
}

# quality_flags is free-form but these are the reserved, meaningful ones
QUALITY_FLAGS = {
    "MISSING_PUBLICATION_DATE",
    "MISSING_FILING_DATE",
    "MISSING_PRIORITY_DATE",
    "MISSING_IDENTIFIER",
    "MISSING_MANUFACTURER",
    "MISSING_TITLE",
    "MISSING_CLASSIFICATION",
    "NOT_MEDTECH_ON_FRONT_PAGE",
    "SITEMAP_ONLY",
    "DOCUMENT_IS_SEARCH_REPORT",
    "DOCUMENT_IS_CORRECTION",
    "NAME_MATCH_ONLY",
    "IDENTIFIER_SELF_ASSIGNED",     # e.g. a name we invented, never present in source
    "SNAPSHOT_ONLY",                # we only ever see the current state
    "RETROSPECTIVE_FIELD",          # field may have changed after publication
    "TRUNCATED_RESPONSE",
    "PARSED_FROM_PDF",
    "PARSED_FROM_HTML",
    "DUPLICATE_OF_OTHER_SOURCE",
    "LICENCE_UNCLEAR",
    "RATE_LIMITED",
    "PARTIAL_PAGE",
}

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_DATETIME_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$")


class SchemaError(ValueError):
    pass


@dataclass
class Identifier:
    """One externally verifiable identifier.

    ``scheme`` is the naming authority, not a description of the value.
    Examples: ``udi_di``, ``gtin``, ``epo_publication_number``,
    ``uspto_510k``, ``hc_device_licence``, ``doi``, ``pmid``, ``nct``,
    ``hs_code``, ``npi``.
    """

    scheme: str
    value: str
    issuing_authority: str | None = None
    scope: str | None = None          # e.g. "EP", "US", "CA"
    is_primary: bool = False

    def key(self) -> tuple[str, str]:
        return (self.scheme, self.value)


@dataclass
class EvidenceRecord:
    # ---- identity of the record itself --------------------------------
    schema_version: str = SCHEMA_VERSION
    source_id: str = ""
    source_record_id: str = ""
    entity_type: str = ""

    # ---- payload ------------------------------------------------------
    original_name: str = ""
    identifiers: list[Identifier] = field(default_factory=list)
    manufacturer: str | None = None
    attributes: dict[str, Any] = field(default_factory=dict)

    # ---- the four clocks ---------------------------------------------
    event_at: str | None = None        # when the described event happened
    source_public_at: str | None = None  # when the source made it public
    first_observed_at: str | None = None  # when HORIZON first saw it
    fetched_at: str | None = None      # this fetch

    # ---- provenance ---------------------------------------------------
    source_url: str = ""
    content_hash: str = ""
    licence_status: str = "unknown"
    licence_note: str | None = None

    # ---- epistemic state ----------------------------------------------
    identity_status: str = "UNKNOWN"
    evidence_status: str = "CANDIDATE"
    quality_flags: list[str] = field(default_factory=list)
    relations: list[dict[str, Any]] = field(default_factory=list)

    # ---- bookkeeping ---------------------------------------------------
    raw_ref: str | None = None          # path/offset into DATASETS/ raw evidence
    notes: str | None = None

    # ------------------------------------------------------------------
    def content_key(self) -> dict[str, Any]:
        """The canonical subset hashed into ``content_hash``.

        Excludes volatile bookkeeping (fetched_at, first_observed_at, raw_ref)
        so the same logical record hashes identically across fetch runs.
        """
        return {
            "schema_version": self.schema_version,
            "source_id": self.source_id,
            "source_record_id": self.source_record_id,
            "entity_type": self.entity_type,
            "original_name": self.original_name,
            "identifiers": sorted(
                ({"scheme": i.scheme, "value": i.value} for i in self.identifiers),
                key=lambda d: (d["scheme"], d["value"]),
            ),
            "manufacturer": self.manufacturer,
            "attributes": self.attributes,
            "event_at": self.event_at,
            "source_public_at": self.source_public_at,
            "source_url": self.source_url,
        }

    def compute_hash(self) -> str:
        payload = json.dumps(
            self.content_key(), sort_keys=True, ensure_ascii=False, separators=(",", ":")
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def validate(self) -> None:
        errs: list[str] = []
        if self.schema_version != SCHEMA_VERSION:
            errs.append(f"schema_version must be {SCHEMA_VERSION}")
        for f in ("source_id", "source_record_id", "entity_type", "original_name", "source_url"):
            if not getattr(self, f):
                errs.append(f"{f} is required")
        if self.entity_type and self.entity_type not in ENTITY_TYPES:
            errs.append(f"entity_type {self.entity_type!r} not in controlled vocabulary")
        if self.identity_status not in IDENTITY_STATUS:
            errs.append(f"identity_status {self.identity_status!r} invalid")
        if self.evidence_status not in EVIDENCE_STATUS:
            errs.append(f"evidence_status {self.evidence_status!r} invalid")
        if self.licence_status not in LICENCE_STATUS:
            errs.append(f"licence_status {self.licence_status!r} invalid")
        for f in ("event_at", "source_public_at"):
            v = getattr(self, f)
            if v is not None and not (_DATE_RE.match(v) or _DATETIME_RE.match(v)):
                errs.append(f"{f} {v!r} is not an ISO date/datetime")
        unknown_flags = set(self.quality_flags) - QUALITY_FLAGS
        if unknown_flags:
            errs.append(f"unknown quality_flags {sorted(unknown_flags)}")
        if not self.identifiers:
            if "MISSING_IDENTIFIER" not in self.quality_flags:
                errs.append("record has no identifiers and lacks MISSING_IDENTIFIER flag")
        if errs:
            raise SchemaError(f"{self.source_id}/{self.source_record_id}: " + "; ".join(errs))

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["identifiers"] = [asdict(i) for i in self.identifiers]
        if not self.content_hash:
            d["content_hash"] = self.compute_hash()
        return d

    def to_jsonl(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, sort_keys=False)


def build_record(**kw) -> EvidenceRecord:
    ids = kw.pop("identifiers", []) or []
    norm: list[Identifier] = []
    for i in ids:
        if isinstance(i, Identifier):
            norm.append(i)
        elif isinstance(i, dict):
            norm.append(Identifier(**i))
        elif isinstance(i, (tuple, list)) and len(i) >= 2:
            norm.append(Identifier(scheme=i[0], value=i[1]))
        else:
            raise SchemaError(f"cannot interpret identifier {i!r}")
    rec = EvidenceRecord(identifiers=norm, **kw)
    if not rec.content_hash:
        rec.content_hash = rec.compute_hash()
    return rec


def dedupe_key(rec: EvidenceRecord | dict) -> str:
    """Cross-source dedupe key.

    Prefers a strong external identifier; falls back to the content hash.
    Returns a string that ATLAS-001 can group on without re-implementing the
    precedence rules.
    """
    if isinstance(rec, dict):
        ids = rec.get("identifiers") or []
        ch = rec.get("content_hash") or ""
    else:
        ids = [asdict(i) for i in rec.identifiers]
        ch = rec.content_hash
    strength = [
        "udi_di", "gtin", "doi", "patent_family_id", "epo_publication_number",
        "uspto_patent_number", "uspto_510k", "uspto_pma", "hc_device_licence",
        "nct", "pmid", "pmcid",
    ]
    present = {(i["scheme"], i["value"]) for i in ids if i.get("scheme") and i.get("value")}
    for scheme in strength:
        for s, v in sorted(present):
            if s == scheme:
                return f"{scheme}:{v}"
    if present:
        s, v = sorted(present)[0]
        return f"{s}:{v}"
    return f"hash:{ch}"


def write_jsonl(path, records: Iterable[EvidenceRecord | dict]) -> int:
    n = 0
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        for r in records:
            if isinstance(r, EvidenceRecord):
                r.validate()
                fh.write(r.to_jsonl() + "\n")
            else:
                fh.write(json.dumps(r, ensure_ascii=False) + "\n")
            n += 1
    return n


def read_jsonl(path) -> list[dict]:
    out = []
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out
