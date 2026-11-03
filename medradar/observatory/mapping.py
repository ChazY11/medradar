"""Entity and technology attribution for observed records — with explicit doubt.

The product's scientific integrity depends on attribution being *stated*, not
implied. Every mapping therefore carries both an identifier and a status:

* ``MAPPED`` — the source record itself carries a verified identifier (a SEC CIK
  resolved from the issuer's own submissions document) or an exact roster match.
* ``PENDING_REVIEW`` — a plausible but unverified match (literature affiliation
  query strings). The record is kept and shown, clearly flagged, never silently
  promoted to a company fact.
* ``UNMAPPED`` — no defensible attribution; the record is kept with a null
  entity, so "no attribution" can never be mistaken for "zero activity".
* ``AMBIGUOUS`` — more than one roster entity could claim it; deliberately not
  resolved by name similarity.

Mapping is versioned (``MAPPING_VERSION``) and stored as append-only history in
the ledger, so improving a mapping never rewrites the source evidence.
"""

from __future__ import annotations

from typing import Any, Iterable, Mapping

from ..config import load_companies, load_tracks
from .records import (
    ENTITY_AMBIGUOUS,
    ENTITY_MAPPED,
    ENTITY_PENDING_REVIEW,
    ENTITY_UNMAPPED,
    TRACK_MAPPED,
    TRACK_PENDING_REVIEW,
    TRACK_UNMAPPED,
    MappingResult,
)

MAPPING_VERSION = "obs-mapping-v1"

#: Minimum confidence for promoting a fuzzy name match to ``MAPPED``. The
#: existing registry returns 1.0 for exact aliases and 0.95 for full token
#: containment; anything below is advisory only.
_MAPPED_CONFIDENCE = 0.95


class _Lazy:
    def __init__(self) -> None:
        self._companies = None
        self._tracks = None

    @property
    def companies(self):
        if self._companies is None:
            self._companies = load_companies("device")
        return self._companies

    @property
    def tracks(self):
        if self._tracks is None:
            self._tracks = load_tracks("device")
        return self._tracks


_LAZY = _Lazy()


def _no_track(note: str | None = None) -> dict[str, Any]:
    return {"track_id": None, "track_status": TRACK_UNMAPPED, "track_method": None, "note_zh": note}


def entity_from_name(name: str | None, *, source: str) -> dict[str, Any]:
    """Resolve a sponsor/applicant string against the curated roster."""
    if not name:
        return {
            "entity_id": None,
            "entity_status": ENTITY_UNMAPPED,
            "entity_method": None,
            "entity_confidence": None,
            "note_zh": "来源未提供可映射的主体名称",
        }
    key, confidence, alias = _LAZY.companies.resolve(name)
    if key and confidence >= _MAPPED_CONFIDENCE:
        return {
            "entity_id": key,
            "entity_status": ENTITY_MAPPED,
            "entity_method": f"{source}_roster_alias",
            "entity_confidence": float(confidence),
            "note_zh": None if confidence >= 1.0 else f"名称包含别名 {alias}，置信度 {confidence:.2f}",
        }
    if key:
        return {
            "entity_id": None,
            "entity_status": ENTITY_PENDING_REVIEW,
            "entity_method": f"{source}_roster_fuzzy",
            "entity_confidence": float(confidence),
            "note_zh": f"疑似 {key}（匹配 {alias}，置信度 {confidence:.2f}）；未经人工确认，不升格为企业事实",
        }
    return {
        "entity_id": None,
        "entity_status": ENTITY_UNMAPPED,
        "entity_method": None,
        "entity_confidence": None,
        "note_zh": f"主体名称 {name!r} 未匹配任何已核验企业别名",
    }


def track_from_text(text: str | None, *, source: str) -> dict[str, Any]:
    """Map free text (trial interventions / conditions) to a curated track."""
    if not text:
        return _no_track("没有可用于赛道映射的文本")
    track_id = _LAZY.tracks.match_frontier_text(text)
    if track_id:
        return {
            "track_id": track_id,
            "track_status": TRACK_MAPPED,
            "track_method": f"{source}_keyword",
            "note_zh": None,
        }
    return _no_track("文本未命中任何已审技术赛道关键词")


def track_from_product_codes(codes: Iterable[str] | None) -> dict[str, Any]:
    codes = [str(code).strip() for code in (codes or []) if str(code).strip()]
    hits = {_LAZY.tracks.for_product_code(code) for code in codes}
    hits.discard(None)
    if len(hits) == 1:
        track = hits.pop()
        return {
            "track_id": track,
            "track_status": TRACK_MAPPED,
            "track_method": "product_code_track_map",
            "note_zh": None,
        }
    if len(hits) > 1:
        return {
            "track_id": None,
            "track_status": TRACK_PENDING_REVIEW,
            "track_method": "product_code_track_map",
            "note_zh": f"多个产品代码映射到不同赛道（{', '.join(sorted(hits))}），不做单值推断",
        }
    return _no_track("产品代码未映射到已审技术赛道")


def mapping_result(entity: Mapping[str, Any], track: Mapping[str, Any]) -> MappingResult:
    return MappingResult(
        entity_id=entity.get("entity_id"),
        entity_status=entity.get("entity_status", ENTITY_UNMAPPED),
        entity_method=entity.get("entity_method"),
        entity_confidence=entity.get("entity_confidence"),
        track_id=track.get("track_id"),
        track_status=track.get("track_status", TRACK_UNMAPPED),
        track_method=track.get("track_method"),
        note_zh=entity.get("note_zh") or track.get("note_zh"),
    )


# ------------------------------------------------------------------- per-source
def sec_filing(company_key: str | None, issuer_name: str | None, cik: str | None) -> MappingResult:
    """SEC attribution is by verified CIK, not by issuer name similarity."""
    if company_key and cik:
        entity = {
            "entity_id": company_key,
            "entity_status": ENTITY_MAPPED,
            "entity_method": "sec_cik_exact",
            "entity_confidence": 1.0,
            "note_zh": f"SEC CIK {cik} 由该发行人的官方 submissions 文件核验",
        }
    elif company_key:
        entity = {
            "entity_id": company_key,
            "entity_status": ENTITY_PENDING_REVIEW,
            "entity_method": "sec_issuer_name",
            "entity_confidence": 0.6,
            "note_zh": "未取得官方 CIK 对应的名册企业，仅按发行人名称候选",
        }
    else:
        entity = {
            "entity_id": None,
            "entity_status": ENTITY_UNMAPPED,
            "entity_method": None,
            "entity_confidence": None,
            "note_zh": f"发行人 {issuer_name!r} 未匹配已核验企业标识",
        }
    track = _no_track("SEC 披露文件未做技术赛道分类：文件内容分类不属于本轮自动观察范围")
    return mapping_result(entity, track)


def ctgov_study(sponsor: str | None, interventions_text: str | None,
                product_codes: Iterable[str] | None = None) -> MappingResult:
    entity = entity_from_name(sponsor, source="ctgov")
    track = track_from_text(interventions_text, source="ctgov")
    if track["track_status"] != TRACK_MAPPED:
        alt = track_from_product_codes(product_codes)
        if alt["track_status"] == TRACK_MAPPED:
            track = alt
    return mapping_result(entity, track)


def europepmc_publication(company_key: str | None, affiliation_query: str | None) -> MappingResult:
    """Literature attribution by affiliation query is explicitly provisional."""
    if company_key:
        entity = {
            "entity_id": company_key,
            "entity_status": ENTITY_PENDING_REVIEW,
            "entity_method": "europepmc_affiliation_query",
            "entity_confidence": 0.5,
            "note_zh": (
                "该文献由包含企业名称的单位署名检索命中；单位署名不等于经核实的法人实体归属，"
                "仅作待复核（PENDING_REVIEW）展示"
            ),
        }
    else:
        entity = {
            "entity_id": None,
            "entity_status": ENTITY_UNMAPPED,
            "entity_method": None,
            "entity_confidence": None,
            "note_zh": "文献无企业检索范围归属",
        }
    track = _no_track("文献标题未做技术赛道映射；避免以标题相似度推断技术方向")
    return mapping_result(entity, track)


def company_display_name(entity_id: str) -> str:
    company = _LAZY.companies.get(entity_id) or {}
    return company.get("name_zh") or company.get("name_en") or entity_id


def track_display(track_id: str | None) -> dict[str, Any]:
    if not track_id:
        return {"track_id": None, "name_zh": None, "name_en": None, "domain": None}
    track = _LAZY.tracks.get(track_id) or {}
    return {
        "track_id": track_id,
        "name_zh": track.get("name_zh"),
        "name_en": track.get("name_en"),
        "domain": track.get("domain"),
    }


def ambiguous_candidates(name: str | None) -> list[str]:
    """Roster keys that could equally claim a name (used when refusing to guess)."""
    if not name:
        return []
    key, _confidence, _alias = _LAZY.companies.resolve(name)
    if not key:
        return []
    tokens = {token for token in name.upper().replace(",", " ").split() if len(token) > 3}
    hits: list[str] = []
    for company in _LAZY.companies.all():
        alias_tokens = {alias for alias in company.get("aliases", []) if alias in name.upper()}
        if alias_tokens and tokens:
            hits.append(company["key"])
    return sorted(set(hits)) if len(set(hits)) > 1 else []


__all__ = [
    "MAPPING_VERSION",
    "ambiguous_candidates",
    "company_display_name",
    "ctgov_study",
    "entity_from_name",
    "europepmc_publication",
    "mapping_result",
    "sec_filing",
    "track_display",
    "track_from_product_codes",
    "track_from_text",
]
