"""Deterministic cross-record links: paper <-> trial, paper <-> grant.

Rules
-----
A link is **deterministic** only when it is derived from an authoritative
identifier that the source publishes in a structured field:

* a ClinicalTrials.gov ``NCT`` id found in a publication record's structured
  identifier/association fields;
* a grant/award number found in a publication's structured funder metadata
  (Crossref ``funder[].award[]``, Europe PMC ``grantsList.grant[].grantId``,
  OpenAlex ``awards[].funder_award_id``);
* the same normalised award number appearing on a grant record
  (NIH ``project_num``, CORDIS project id, SBIR award number).

Anything weaker — a shared keyword, a title similarity, a company name in an
abstract — is **not** a link here.  Those remain candidates and must be reported
separately; this module never produces them.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, Sequence

from ._common import nct_ids_in_text

NCT_EXACT = re.compile(r"^NCT\d{8}$")

#: Prefixes that carry no identity: NIH leading support-year codes (``5R01…``)
#: and the trailing support-year / amendment suffix (``-05``, ``-05A1``).
_GRANT_AMENDMENT = re.compile(r"[-_]\d{2}[A-Z]\d?$")
_GRANT_YEAR_SUFFIX = re.compile(r"[-_]\d{1,2}$")
_GRANT_LEADING_YEAR = re.compile(r"^(\d)(?=[A-Z])")


def normalize_grant_number(value: Any) -> str:
    """Canonical award number for cross-source matching, or ``""``.

    Conservative: strips whitespace/punctuation, the trailing support-year and
    amendment suffix, and the NIH leading support-year digit, so
    ``5R01DK064567-02`` and ``R01 DK064567`` both become ``R01DK064567``.  It
    never invents digits or reorders letters, so a failed match stays a
    non-link rather than a false positive.
    """
    if value is None:
        return ""
    text = str(value).strip().upper()
    if not text:
        return ""
    text = re.sub(r"[\s,;/]+", "", text)
    text = _GRANT_AMENDMENT.sub("", text)
    text = _GRANT_YEAR_SUFFIX.sub("", text)
    text = _GRANT_LEADING_YEAR.sub("", text)
    return text.strip("-_ ")


@dataclass
class Link:
    kind: str  # "trial" | "grant"
    value: str
    basis: str  # deterministic evidence field
    evidence_id: str = ""
    source_id: str = ""
    target_evidence_id: str = ""
    detail: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "value": self.value,
            "basis": self.basis,
            "evidence_id": self.evidence_id,
            "source_id": self.source_id,
            "target_evidence_id": self.target_evidence_id,
            "detail": self.detail,
            "deterministic": True,
        }


def trial_ids_from_record(record: Mapping[str, Any]) -> list[dict[str, Any]]:
    """NCT ids published in a publication record's structured fields."""
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for ident in record.get("identifiers", []) or []:
        scheme = str(ident.get("scheme", "")).lower()
        value = str(ident.get("value", "")).strip()
        if scheme == "nct" and NCT_EXACT.match(value) and value not in seen:
            seen.add(value)
            out.append({"value": value, "field": "identifiers.nct"})
    for entry in (record.get("normalized", {}) or {}).get("trial_ids", []) or []:
        value = str(entry.get("value", "")).strip()
        if NCT_EXACT.match(value) and value not in seen:
            seen.add(value)
            out.append({"value": value, "field": str(entry.get("field", "normalized.trial_ids"))})
    return out


def grant_numbers_from_record(record: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Award numbers published in a publication's structured funder metadata."""
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for entry in (record.get("normalized", {}) or {}).get("grant_numbers", []) or []:
        raw = str(entry.get("value", "")).strip()
        if not raw or raw in seen:
            continue
        seen.add(raw)
        out.append(
            {
                "value": raw,
                "normalized": normalize_grant_number(raw),
                "funder": str(entry.get("funder", "")),
                "field": str(entry.get("field", "")),
            }
        )
    return out


def publication_trial_links(publications: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """All deterministic publication -> trial links, one row per (record, NCT)."""
    links: list[dict[str, Any]] = []
    for record in publications:
        for entry in trial_ids_from_record(record):
            links.append(
                Link(
                    kind="trial",
                    value=entry["value"],
                    basis=f"structurally_published_nct ({entry['field']})",
                    evidence_id=str(record.get("evidence_id", "")),
                    source_id=str(record.get("source_id", "")),
                    detail={"nct": entry["value"]},
                ).to_dict()
            )
    return links


def publication_grant_links(publications: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """All deterministic publication -> grant-number links."""
    links: list[dict[str, Any]] = []
    for record in publications:
        for entry in grant_numbers_from_record(record):
            if not entry["normalized"]:
                continue
            links.append(
                Link(
                    kind="grant",
                    value=entry["value"],
                    basis=f"funder_award_id ({entry['field']})",
                    evidence_id=str(record.get("evidence_id", "")),
                    source_id=str(record.get("source_id", "")),
                    detail={
                        "normalized_award": entry["normalized"],
                        "funder_name": entry["funder"],
                    },
                ).to_dict()
            )
    return links


def grant_award_index(
    grant_records: Iterable[Mapping[str, Any]],
) -> dict[str, dict[str, Any]]:
    """``normalized award number -> grant record`` index (deterministic only)."""
    index: dict[str, dict[str, Any]] = {}
    for record in grant_records:
        for ident in record.get("identifiers", []) or []:
            if str(ident.get("scheme", "")).lower() != "award_id":
                continue
            normalized = normalize_grant_number(ident.get("value"))
            if normalized:
                index.setdefault(normalized, dict(record))
    return index


def resolve_grant_links(
    publication_links: Sequence[Mapping[str, Any]],
    grant_records: Iterable[Mapping[str, Any]],
) -> dict[str, Any]:
    """Match publication grant numbers against collected grant records.

    Returns resolved links (with ``target_evidence_id``) and the unmatched award
    numbers, so a low match rate is visible instead of hidden.
    """
    index = grant_award_index(grant_records)
    resolved: list[dict[str, Any]] = []
    unmatched: list[str] = []
    for link in publication_links:
        normalized = str((link.get("detail") or {}).get("normalized_award", ""))
        target = index.get(normalized)
        if target is None:
            if normalized and normalized not in unmatched:
                unmatched.append(normalized)
            continue
        enriched = dict(link)
        enriched["target_evidence_id"] = str(target.get("evidence_id", ""))
        enriched["basis"] = link.get("basis", "") + " + grant_record_award_id_match"
        resolved.append(enriched)
    return {
        "resolved": resolved,
        "unmatched_award_numbers": unmatched,
        "grant_records_indexed": len(index),
    }


def _trailing_nct(values: Iterable[Any]) -> list[str]:
    out: list[str] = []
    for value in values:
        for nct in nct_ids_in_text(value):
            if nct not in out:
                out.append(nct)
    return out
