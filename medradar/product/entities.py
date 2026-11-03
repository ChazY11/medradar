"""Entity resolution for MedRadar 2.0.

Two layers, kept deliberately separate:

1. **Roster mapping** — the store already assigns ``events.company_key`` using
   ``config/companies_device.json``. The product reuses that mapping verbatim;
   it never re-derives or overrides it.
2. **Supplemental exact aliases** — Dräger and Mindray are absent from that
   roster, so every one of their events has ``company_key = NULL``. For those
   two firms the product applies a *curated, reviewed, exact-string* alias set
   vendored from ``research/full-history-v1:config/hist_entity_aliases.json``
   (``entity_aliases.json`` in this package). Matching is exact string equality
   only — no substring, prefix or fuzzy matching — so the rule is auditable.

Every event returned to the product also carries ``company_match`` metadata so
the UI can tell the user *how* an event was attributed (roster key, exact alias,
or unmapped) and surface disputed mappings instead of hiding them.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable, Mapping

from ..config import load_companies
from .catalog import EXTRA_ALIAS_COMPANIES, FEATURED_BY_KEY, FEATURED_KEYS

ALIAS_FILE = Path(__file__).with_name("entity_aliases.json")


@lru_cache(maxsize=1)
def alias_payload() -> dict[str, Any]:
    with ALIAS_FILE.open("r", encoding="utf-8") as handle:
        return json.load(handle)


@lru_cache(maxsize=1)
def roster() -> dict[str, dict[str, Any]]:
    """Curated device-company roster (store config) keyed by company key."""
    registry = load_companies("device")
    out: dict[str, dict[str, Any]] = {}
    for company in registry.all():
        key = str(company["key"])
        entry = dict(company)
        featured = FEATURED_BY_KEY.get(key)
        if featured:
            entry.update(
                {
                    "featured": True,
                    "name_zh": featured["name_zh"],
                    "name_en": featured["name_en"],
                    "ticker": featured["ticker"],
                    "exchange": featured["exchange"],
                    "hq_zh": featured["hq_zh"],
                    "profile_zh": featured["profile_zh"],
                }
            )
        else:
            entry.setdefault("featured", False)
        out[key] = entry
    # Two featured firms are not in the roster: add them from the curated
    # catalog plus the vendored exact-alias payload.
    for key in EXTRA_ALIAS_COMPANIES:
        featured = FEATURED_BY_KEY[key]
        payload = alias_payload()["companies"].get(key, {})
        out[key] = {
            "key": key,
            "name_en": featured["name_en"],
            "name_zh": featured["name_zh"],
            "ticker": featured["ticker"],
            "exchange": featured["exchange"],
            "hq_zh": featured["hq_zh"],
            "profile_zh": featured["profile_zh"],
            "sector": "device",
            "is_major": True,
            "featured": True,
            "roster_present": False,
            "aliases": list(payload.get("accept_exact") or []),
        }
    return out


@lru_cache(maxsize=1)
def exact_alias_map() -> dict[str, str]:
    """``applicant_raw`` (exact) -> company key, for roster-absent firms only."""
    mapping: dict[str, str] = {}
    companies = alias_payload().get("companies") or {}
    for key in EXTRA_ALIAS_COMPANIES:
        for alias in companies.get(key, {}).get("accept_exact") or []:
            mapping[str(alias)] = key
    return mapping


@lru_cache(maxsize=1)
def alias_review_pending() -> dict[str, Any]:
    payload = alias_payload()
    pending: dict[str, Any] = {
        "review_status": payload.get("review_status"),
        "source": payload.get("source"),
        "matching_rule": payload.get("matching_rule"),
    }
    for key in EXTRA_ALIAS_COMPANIES:
        entry = (payload.get("companies") or {}).get(key) or {}
        pending[key] = {
            "aliases": len(entry.get("accept_exact") or []),
            "reject_exact": list(entry.get("reject_exact") or []),
            "decision_notes": list(entry.get("decision_notes") or []),
            "confidence": entry.get("confidence"),
        }
    return pending


def company_meta(key: str) -> dict[str, Any] | None:
    return roster().get(key)


def display_name(key: str, zh: bool = True) -> str:
    meta = company_meta(key) or {}
    if zh:
        return str(meta.get("name_zh") or meta.get("name_en") or key)
    return str(meta.get("name_en") or key)


def featured_keys() -> list[str]:
    return list(FEATURED_KEYS)


def all_keys() -> list[str]:
    return sorted(roster())


def resolve_applicant(applicant: str | None, company_key: str | None) -> tuple[str | None, str, str]:
    """Return ``(company_key, method, matched_alias)``.

    ``method`` is one of ``roster`` / ``exact_alias`` / ``unmapped``.
    """
    if company_key:
        return str(company_key), "roster", ""
    text = (applicant or "").strip()
    if text:
        key = exact_alias_map().get(text)
        if key:
            return key, "exact_alias", text
    return None, "unmapped", ""


def company_predicate(keys: Iterable[str], alias: str = "e") -> tuple[str, list[Any]]:
    """SQL predicate selecting events belonging to ``keys``.

    Roster companies match on ``events.company_key`` (the store's own mapping).
    Roster-absent firms match on the curated exact alias strings. The returned
    SQL uses positional ``?`` placeholders.
    """
    clauses: list[str] = []
    params: list[Any] = []
    for key in dict.fromkeys(keys):
        if not key:
            continue
        meta = company_meta(key)
        if meta and meta.get("roster_present", True) is False:
            aliases = list(meta.get("aliases") or [])
            sub = [f"{alias}.company_key = ?"]
            params.append(key)
            if aliases:
                marks = ",".join("?" for _ in aliases)
                sub.append(f"{alias}.applicant_raw IN ({marks})")
                params.extend(aliases)
            clauses.append("(" + " OR ".join(sub) + ")")
        else:
            clauses.append(f"{alias}.company_key = ?")
            params.append(key)
    if not clauses:
        return "0", []
    return "(" + " OR ".join(clauses) + ")", params


def company_alias_review(keys: Iterable[str]) -> list[dict[str, Any]]:
    """Per-company entity-resolution review metadata for the UI."""
    out: list[dict[str, Any]] = []
    for key in keys:
        meta = company_meta(key) or {}
        if meta.get("roster_present", True) is False:
            entry = (alias_payload().get("companies") or {}).get(key) or {}
            out.append(
                {
                    "company": key,
                    "method": "exact_alias",
                    "method_zh": "逐条精确名称匹配（补充映射）",
                    "status": "PENDING_HUMAN_REVIEW",
                    "note_zh": (
                        "该企业不在仓库原有企业名册中，事件的企业归属由人工整理的精确申请人字符串匹配得到；"
                        "已排除含义不明确的字符串，仍建议人工复核。"
                    ),
                    "accept_exact": list(entry.get("accept_exact") or []),
                    "reject_exact": list(entry.get("reject_exact") or []),
                    "confidence": entry.get("confidence"),
                }
            )
        else:
            out.append(
                {
                    "company": key,
                    "method": "roster",
                    "method_zh": "仓库既有企业名册映射（company_key）",
                    "status": "roster",
                    "note_zh": "事件归属复用仓库 config/companies_device.json 的企业别名映射，产品未做二次改写。",
                    "confidence": "high",
                }
            )
    return out


def event_company_fields(row: Mapping[str, Any]) -> dict[str, Any]:
    """Enrich a raw event row with attribution metadata."""
    key, method, matched = resolve_applicant(row.get("applicant_raw"), row.get("company_key"))
    return {
        "company_key": key,
        "company_name_zh": display_name(key) if key else None,
        "company_match": method,
        "company_match_alias": matched,
    }
