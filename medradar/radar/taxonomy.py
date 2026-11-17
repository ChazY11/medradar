"""Versioned ICU-monitoring taxonomy and the deterministic rule layer.

Everything in this module is *configuration interpreted by code*, not knowledge baked into
code. A new company, a new technology topic or a new verified FDA product code is a JSON
edit; the schema, the ledger and the adapters do not change.

Three things this module refuses to do:

1. **It does not invent FDA product codes.** A code is listed only when an openFDA
   classification query returned it; ``config/radar/topics.json`` records that query.
2. **It does not turn a keyword hit into a capability claim.** ``match_text`` returns a
   ``TOPIC_RELATED`` candidate with the exact matched span, and the graph layer decides
   what, if anything, may be asserted from it.
3. **It does not guess an organisation.** An alias is an exact published string with an
   identity-confidence score; below the configured thresholds the result stays a
   candidate that forms no confirmed edge.

The taxonomy fingerprint is stored on every graph assertion, so a remap is visible as a
version change rather than as a technology change.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable, Mapping

from ..config import resolve_config_dir
from .records import (
    CONFIRMED,
    CANDIDATE,
    METHOD_RULE_ALIAS,
    METHOD_RULE_PRODUCT_CODE,
    METHOD_RULE_TEXT,
    canonical_json,
    sha256_hex,
)


class TaxonomyError(RuntimeError):
    """The taxonomy configuration is missing or internally inconsistent."""


@dataclass(frozen=True)
class Topic:
    id: str
    family: str
    label_en: str
    label_zh: str
    description: str
    product_codes: tuple[str, ...]
    terms: tuple[re.Pattern[str], ...]

    def public(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "family": self.family,
            "label_en": self.label_en,
            "label_zh": self.label_zh,
            "description": self.description,
            "product_codes": list(self.product_codes),
        }


@dataclass(frozen=True)
class Organization:
    id: str
    canonical_name: str
    display_name: str
    label_zh: str
    country: str
    aliases: tuple[tuple[str, float], ...]
    notes: str

    def public(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "canonical_name": self.canonical_name,
            "display_name": self.display_name,
            "label_zh": self.label_zh,
            "country": self.country,
            "alias_count": len(self.aliases),
            "notes": self.notes,
        }


def _radar_config_dir() -> Path:
    override = str(os.environ.get("MEDRADAR_RADAR_CONFIG_DIR") or "").strip()
    if override:
        return Path(override).expanduser()
    return resolve_config_dir() / "radar"


def _load_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise TaxonomyError(
            f"radar configuration is missing: {path}. The radar CLI is unusable without "
            "config/radar/{topics,organizations,sources}.json."
        )
    try:
        # utf-8-sig tolerates a byte-order mark, which a hand-edited file may legitimately have.
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except ValueError as error:
        raise TaxonomyError(f"{path}: invalid JSON: {error}") from error


class Taxonomy:
    """Immutable, fingerprinted view of the committed taxonomy."""

    def __init__(self, config_dir: Path | None = None) -> None:
        self.config_dir = Path(config_dir) if config_dir is not None else _radar_config_dir()
        topics_doc = _load_json(self.config_dir / "topics.json")
        orgs_doc = _load_json(self.config_dir / "organizations.json")
        sources_path = self.config_dir / "sources.json"
        self.sources_doc = _load_json(sources_path) if sources_path.is_file() else {"sources": []}

        self.version = str(topics_doc.get("taxonomy_version") or "unversioned")
        self.registry_version = str(orgs_doc.get("registry_version") or "unversioned")
        self.scope = dict(topics_doc.get("scope") or {})
        self.verified_notes = dict(topics_doc.get("verified") or {})
        thresholds = orgs_doc.get("confidence_thresholds") or {}
        self.confirmed_threshold = float(thresholds.get("confirmed_at_or_above", 0.9))
        self.candidate_threshold = float(thresholds.get("candidate_at_or_above", 0.6))

        self.topics: tuple[Topic, ...] = self._build_topics(topics_doc.get("topics") or [])
        self.organizations: tuple[Organization, ...] = self._build_organizations(orgs_doc.get("organizations") or [])
        self._topic_by_id = {topic.id: topic for topic in self.topics}
        self._org_by_id = {org.id: org for org in self.organizations}
        self._code_topics: dict[str, tuple[str, ...]] = {}
        for topic in self.topics:
            for code in topic.product_codes:
                self._code_topics.setdefault(code, ())
                self._code_topics[code] = (*self._code_topics[code], topic.id)
        # Longest alias first so "Philips Medizin Systeme Boeblingen GmbH" wins over "Philips".
        self._aliases: tuple[tuple[str, str, float], ...] = tuple(
            sorted(
                ((alias.upper(), org.id, confidence) for org in self.organizations for alias, confidence in org.aliases),
                key=lambda item: (-len(item[0]), item[0]),
            )
        )
        self.fingerprint = sha256_hex(canonical_json({
            "topics_version": self.version,
            "orgs_version": self.registry_version,
            "topics": [t.public() | {"terms": [p.pattern for p in t.terms]} for t in self.topics],
            "organizations": [
                {"id": o.id, "canonical_name": o.canonical_name, "aliases": [[a, c] for a, c in o.aliases]}
                for o in self.organizations
            ],
        }))

    # ------------------------------------------------------------------- builders
    def _build_topics(self, rows: Iterable[Mapping[str, Any]]) -> tuple[Topic, ...]:
        topics: list[Topic] = []
        seen: set[str] = set()
        for row in rows:
            topic_id = str(row.get("id") or "").strip()
            if not topic_id:
                raise TaxonomyError("a topic entry has no id")
            if topic_id in seen:
                raise TaxonomyError(f"duplicate topic id: {topic_id}")
            seen.add(topic_id)
            codes: list[str] = []
            for entry in row.get("product_codes") or []:
                code = str(entry.get("code") or "").strip().upper()
                if not re.fullmatch(r"[A-Z]{3}", code):
                    raise TaxonomyError(f"{topic_id}: product code {code!r} is not a 3-letter FDA code")
                if not entry.get("device_name"):
                    raise TaxonomyError(f"{topic_id}: product code {code} has no verified device_name")
                codes.append(code)
            patterns: list[re.Pattern[str]] = []
            for term in row.get("terms") or []:
                try:
                    patterns.append(re.compile(str(term), re.IGNORECASE))
                except re.error as error:
                    raise TaxonomyError(f"{topic_id}: bad term regex {term!r}: {error}") from error
            if not patterns and not codes:
                raise TaxonomyError(f"{topic_id}: a topic needs at least one term or one product code")
            topics.append(Topic(
                id=topic_id,
                family=str(row.get("family") or "unknown"),
                label_en=str(row.get("label_en") or topic_id),
                label_zh=str(row.get("label_zh") or topic_id),
                description=str(row.get("description") or ""),
                product_codes=tuple(codes),
                terms=tuple(patterns),
            ))
        if not topics:
            raise TaxonomyError("the taxonomy declares no topics")
        return tuple(topics)

    def _build_organizations(self, rows: Iterable[Mapping[str, Any]]) -> tuple[Organization, ...]:
        organizations: list[Organization] = []
        seen: set[str] = set()
        for row in rows:
            org_id = str(row.get("id") or "").strip()
            if not org_id:
                raise TaxonomyError("an organization entry has no id")
            if org_id in seen:
                raise TaxonomyError(f"duplicate organization id: {org_id}")
            seen.add(org_id)
            aliases: list[tuple[str, float]] = []
            for entry in row.get("aliases") or []:
                text = " ".join(str(entry.get("text") or "").split())
                if not text:
                    raise TaxonomyError(f"{org_id}: empty alias")
                confidence = float(entry.get("confidence"))
                if not 0.0 < confidence <= 1.0:
                    raise TaxonomyError(f"{org_id}: alias confidence out of range for {text!r}")
                aliases.append((text, confidence))
            if not aliases:
                raise TaxonomyError(f"{org_id}: no aliases, so it can never be resolved")
            organizations.append(Organization(
                id=org_id,
                canonical_name=str(row.get("canonical_name") or org_id),
                display_name=str(row.get("display_name") or org_id),
                label_zh=str(row.get("label_zh") or row.get("display_name") or org_id),
                country=str(row.get("country") or ""),
                aliases=tuple(aliases),
                notes=str(row.get("notes") or ""),
            ))
        return tuple(organizations)

    # -------------------------------------------------------------------- accessors
    def topic(self, topic_id: str) -> Topic | None:
        return self._topic_by_id.get(topic_id)

    def organization(self, org_id: str) -> Organization | None:
        return self._org_by_id.get(org_id)

    def topics_for_code(self, code: str | None) -> tuple[str, ...]:
        if not code:
            return ()
        return self._code_topics.get(str(code).strip().upper(), ())

    def sources(self) -> tuple[dict[str, Any], ...]:
        return tuple(self.sources_doc.get("sources") or [])

    def source(self, source_id: str) -> dict[str, Any] | None:
        return next((row for row in self.sources() if row.get("id") == source_id), None)

    def public_catalog(self) -> dict[str, Any]:
        """The taxonomy as the API and the UI see it (no regexes, no scores)."""
        return {
            "taxonomy_version": self.version,
            "registry_version": self.registry_version,
            "fingerprint": self.fingerprint,
            "scope": self.scope,
            "verified": self.verified_notes,
            "topics": [topic.public() | {"families": topic.family} for topic in self.topics],
            "organizations": [org.public() for org in self.organizations],
            "sources": list(self.sources()),
            "confidence_thresholds": {
                "confirmed_at_or_above": self.confirmed_threshold,
                "candidate_at_or_above": self.candidate_threshold,
            },
        }

    # ----------------------------------------------------------------- rule layer
    def match_text(self, text: str | None, *, limit: int = 8) -> list[dict[str, Any]]:
        """Technology-topic candidates supported by a text match, with the exact span.

        Returns ``TOPIC_RELATED`` candidates only. A caller must never render one of these
        as a confirmed capability: a keyword says what a text is about.
        """
        if not text:
            return []
        haystack = str(text)
        found: dict[str, dict[str, Any]] = {}
        for topic in self.topics:
            hits: list[str] = []
            for pattern in topic.terms:
                for match in pattern.finditer(haystack):
                    span = match.group(0)
                    if span and span not in hits:
                        hits.append(span)
                    if len(hits) >= 4:
                        break
                if len(hits) >= 4:
                    break
            if hits:
                found[topic.id] = {
                    "topic_id": topic.id,
                    "method": METHOD_RULE_TEXT,
                    "confirmation": "TOPIC_RELATED",
                    "matched_terms": hits[:4],
                    "family": topic.family,
                    "confidence": round(min(0.9, 0.55 + 0.1 * len(hits)), 3),
                }
        ordered = sorted(found.values(), key=lambda item: (-item["confidence"], item["topic_id"]))
        return ordered[:limit]

    def topics_for_product_codes(self, codes: Iterable[str]) -> list[dict[str, Any]]:
        """Topic candidates implied by official FDA product codes (strongest rule)."""
        out: dict[str, dict[str, Any]] = {}
        for code in codes:
            normalized = str(code or "").strip().upper()
            for topic_id in self.topics_for_code(normalized):
                entry = out.setdefault(topic_id, {
                    "topic_id": topic_id,
                    "method": METHOD_RULE_PRODUCT_CODE,
                    "confirmation": "TOPIC_RELATED",
                    "matched_terms": [],
                    "product_codes": [],
                    "confidence": 0.85,
                })
                if normalized not in entry["product_codes"]:
                    entry["product_codes"].append(normalized)
        for entry in out.values():
            topic = self.topic(entry["topic_id"])
            entry["family"] = topic.family if topic else None
            entry["matched_terms"] = [f"FDA product code {code}" for code in entry["product_codes"]]
        return sorted(out.values(), key=lambda item: item["topic_id"])

    def resolve_organization(self, name: str | None) -> list[dict[str, Any]]:
        """Organisation candidates for a published organisation string.

        Matching is exact-then-prefix over the committed alias table; fuzzy matching is
        deliberately absent because a false merge silently poisons the graph.
        """
        if not name:
            return []
        needle = " ".join(str(name).split()).upper()
        if not needle:
            return []
        matches: list[dict[str, Any]] = []
        for alias, org_id, confidence in self._aliases:
            if needle == alias or needle.startswith(alias) or alias in needle:
                level = (
                    CONFIRMED if confidence >= self.confirmed_threshold
                    else CANDIDATE if confidence >= self.candidate_threshold
                    else "UNKNOWN"
                )
                matches.append({
                    "organization_id": org_id,
                    "matched_alias": alias,
                    "method": METHOD_RULE_ALIAS,
                    "confidence": confidence,
                    "confirmation": level,
                    "published_name": str(name),
                })
                break  # aliases are ordered longest-first; the first hit is the most specific
        return matches


@lru_cache(maxsize=4)
def load_taxonomy(config_dir: str | None = None) -> Taxonomy:
    """Process-wide taxonomy, cached per configuration directory."""
    return Taxonomy(Path(config_dir) if config_dir else None)


def clear_cache() -> None:
    load_taxonomy.cache_clear()
