"""Curated company registry and its *deliberately narrow* alias resolver.

The resolver answers one question: "does this source string name one of the
five target firms, and on what basis?"  It has four answer tiers:

``official_id``
    An authoritative identifier supplied by the source matched a registered id
    (none of the five firms expose this in FDA/MDALL record text, so the pilot
    does not claim it).

``exact_alias``
    The folded string equals, or contains as consecutive tokens, one curated
    alias; no negative guard fired.

``candidate``
    Fuzzy overlap.  Kept, counted separately, and never used to build a
    confirmed relation.

``none``
    No link.  Recorded as none, not omitted.
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from .. import config
from .normalize import name_tokens, normalize_name, token_subsequence


class CompanyIndex:
    """Alias index over ``config/atlas_firms.json``."""

    def __init__(self, firms: Sequence[Mapping[str, Any]]) -> None:
        self._firms: dict[str, Mapping[str, Any]] = {}
        self._aliases: list[tuple[tuple[str, ...], str, str]] = []
        for firm in firms:
            key = str(firm.get("key", "")).strip()
            if not key:
                continue
            self._firms[key] = firm
            for alias in [firm.get("canonical_name", ""), *list(firm.get("aliases") or [])]:
                tokens = name_tokens(alias)
                if tokens:
                    self._aliases.append((tokens, key, str(alias)))
        # Longest alias first: "PHILIPS MEDICAL SYSTEMS" must beat "PHILIPS".
        self._aliases.sort(key=lambda item: (-len(item[0]), item[0]))

    @classmethod
    def from_config(cls, path: str | None = None) -> "CompanyIndex":
        firms = config.load_firms(path)
        return cls(list(firms.values()))

    @classmethod
    def from_firms(cls, firms: Mapping[str, Mapping[str, Any]]) -> "CompanyIndex":
        return cls(list(firms.values()))

    def firm(self, key: str) -> Mapping[str, Any] | None:
        return self._firms.get(key)

    def keys(self) -> list[str]:
        return sorted(self._firms)

    def guard_hit(self, key: str, normalized: str) -> str:
        firm = self._firms.get(key) or {}
        candidate = tuple(normalized.split())
        for guard in firm.get("negative_guards") or []:
            guard_tokens = name_tokens(guard)
            if token_subsequence(guard_tokens, candidate):
                return str(guard)
            if len(candidate) >= 2 and token_subsequence(candidate, guard_tokens):
                return str(guard)
        return ""

    def resolve(self, raw_name: Any, *, country: str = "") -> dict[str, Any]:
        """Resolve one source company string into a typed, evidence-bearing tier."""
        normalized = normalize_name(raw_name)
        if not normalized:
            return _none(raw_name, "empty company name")
        candidate = tuple(normalized.split())
        for alias_tokens, key, alias_text in self._aliases:
            if not token_subsequence(alias_tokens, candidate):
                continue
            guard = self.guard_hit(key, normalized)
            if guard:
                return {
                    "entity_type": "company",
                    "firm_key": key,
                    "name_raw": str(raw_name),
                    "method": "candidate",
                    "confidence": 0.55,
                    "normalized": normalized,
                    "matched_alias": " ".join(alias_tokens),
                    "negative_guard": guard,
                    "note": "alias matched but a curated negative guard fired; candidate only",
                }
            return {
                "entity_type": "company",
                "firm_key": key,
                "name_raw": str(raw_name),
                "method": "exact_alias",
                "confidence": 0.95,
                "normalized": normalized,
                "matched_alias": " ".join(alias_tokens),
                "alias_registry_value": alias_text,
                "country_field": country,
                "note": "curated alias match; a name match is a company link, not device identity",
            }
        return _candidate(raw_name, normalized, country)


def _none(raw_name: Any, note: str) -> dict[str, Any]:
    return {
        "entity_type": "company",
        "firm_key": None,
        "name_raw": "" if raw_name is None else str(raw_name),
        "method": "none",
        "confidence": 0.0,
        "normalized": "",
        "note": note,
    }


def _candidate(raw_name: Any, normalized: str, country: str) -> dict[str, Any]:
    """Token-overlap suggestion; never confirmed, never silently dropped."""
    tokens = set(normalized.split())
    if not tokens:
        return _none(raw_name, "no name tokens")
    index = CompanyIndex.from_config()
    best: tuple[float, str, tuple[str, ...]] | None = None
    for alias_tokens, key, _ in index._aliases:  # noqa: SLF001 - same module
        if len(alias_tokens) < 2:
            continue
        overlap = len(tokens & set(alias_tokens)) / len(alias_tokens)
        if overlap >= 0.75 and (best is None or overlap > best[0]):
            best = (overlap, key, alias_tokens)
    if best is None:
        return _none(raw_name, "no alias overlap >= 0.75")
    overlap, key, alias_tokens = best
    return {
        "entity_type": "company",
        "firm_key": key,
        "name_raw": str(raw_name),
        "method": "candidate",
        "confidence": round(min(0.75, 0.4 + 0.3 * overlap), 3),
        "normalized": normalized,
        "overlap": round(overlap, 3),
        "matched_alias": " ".join(alias_tokens),
        "country_field": country,
        "note": "semantic candidate; must not be counted as a confirmed company link",
    }


__all__ = ["CompanyIndex"]
