"""Organization identity, applicant attribution and organization search.

The registry (medradar/product/identity/organizations.json) is the reviewed source of truth for
which applicant spellings belong to which tracked organization. This module loads it, enforces
its integrity rules, and exposes the *only* attribution function the rest of the product may
use.

Rules enforced here (see docs/product/DATA_CONTRACT.md section 4):

* exact match only, after Unicode NFC + casefold + whitespace collapse;
* the verbatim applicant string is preserved for evidence;
* one applicant string cannot be accepted by two organizations (load-time error);
* one string cannot be both accepted and rejected (load-time error);
* unattributed strings stay unattributed; nothing is guessed.
"""
from __future__ import annotations

import json
import unicodedata
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable, Iterator

REGISTRY_PATH = Path(__file__).with_name("identity") / "organizations.json"

BASIS_LABELS = {
    "legal_name": "legal name",
    "brand": "brand name",
    "subsidiary": "subsidiary or operating entity",
    "historical_name": "historical name",
    "division": "division",
}


def normalise_applicant(value: str) -> str:
    text = unicodedata.normalize("NFC", value or "")
    return " ".join(text.casefold().split())


@dataclass(frozen=True)
class Decision:
    applicant_name: str
    organization_key: str
    basis: str
    review: str
    source: str


@dataclass(frozen=True)
class Rejection:
    applicant_name: str
    organization_key: str
    reason: str


@dataclass(frozen=True)
class Organization:
    key: str
    display_name: str
    display_name_zh: str | None
    legal_name: str | None
    ticker: str | None
    exchange: str | None
    country: str | None
    country_name: str | None
    organization_type: str
    featured: bool
    description: str
    brands: tuple[str, ...]
    registry_review: str
    metadata_source: str
    ownership_note: str
    accept_exact: tuple[Decision, ...]
    reject_exact: tuple[Rejection, ...]
    search_tokens: tuple[str, ...]

    def to_public(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "display_name": self.display_name,
            "display_name_zh": self.display_name_zh,
            "legal_name": self.legal_name,
            "ticker": self.ticker,
            "exchange": self.exchange,
            "country": self.country,
            "country_name": self.country_name,
            "organization_type": self.organization_type,
            "featured": self.featured,
            "description": self.description,
            "brands": list(self.brands),
            "registry_review": self.registry_review,
            "metadata_source": self.metadata_source,
            "ownership_note": self.ownership_note,
            "search_tokens": list(self.search_tokens),
        }


@dataclass
class Registry:
    updated_at: str
    matching_rule: str
    organizations: tuple[Organization, ...]
    by_key: dict[str, Organization]
    decisions: dict[str, Decision]
    rejections: dict[str, Rejection]
    accepted_spellings_by_org: dict[str, tuple[Decision, ...]]
    warnings: list[str] = field(default_factory=list)

    def organization(self, key: str) -> Organization | None:
        return self.by_key.get(key)

    def decide(self, applicant_name: str) -> tuple[Decision | None, Rejection | None]:
        normalised = normalise_applicant(applicant_name)
        return self.decisions.get(normalised), self.rejections.get(normalised)

    def all_keys(self) -> list[str]:
        return [org.key for org in self.organizations]


def _build_registry(payload: dict[str, Any]) -> Registry:
    organizations: list[Organization] = []
    decisions: dict[str, Decision] = {}
    rejections: dict[str, Rejection] = {}
    accepted_by_org: dict[str, list[Decision]] = {}
    warnings: list[str] = []

    for raw in payload.get("organizations") or []:
        key = str(raw["key"]).strip()
        accept: list[Decision] = []
        for item in raw.get("accept_exact") or []:
            value = str(item["value"]).strip()
            if not value:
                continue
            normalised = normalise_applicant(value)
            decision = Decision(
                applicant_name=value,
                organization_key=key,
                basis=str(item.get("basis") or "brand"),
                review=str(item.get("review") or "pending_review"),
                source=str(item.get("source") or ""),
            )
            existing = decisions.get(normalised)
            if existing is not None:
                if existing.organization_key != key:
                    raise ValueError(
                        "applicant spelling claimed by two organizations: "
                        + repr(value)
                        + " -> "
                        + existing.organization_key
                        + " and "
                        + key
                    )
                # A case-variant duplicate inside one organization is noise, not a decision:
                # keep the first entry and drop the duplicate.
                warnings.append("duplicate applicant spelling inside " + key + ": " + repr(value))
                continue
            decisions[normalised] = decision
            accept.append(decision)
        reject: list[Rejection] = []
        for item in raw.get("reject_exact") or []:
            value = str(item["value"]).strip()
            if not value:
                continue
            normalised = normalise_applicant(value)
            if normalised in decisions:
                raise ValueError("applicant spelling both accepted and rejected: " + repr(value))
            rejection = Rejection(
                applicant_name=value,
                organization_key=key,
                reason=str(item.get("reason") or "rejected by registry review"),
            )
            rejections[normalised] = rejection
            reject.append(rejection)
        accepted_by_org[key] = accept
        organizations.append(
            Organization(
                key=key,
                display_name=str(raw.get("display_name") or key),
                display_name_zh=raw.get("display_name_zh"),
                legal_name=raw.get("legal_name"),
                ticker=raw.get("ticker"),
                exchange=raw.get("exchange"),
                country=raw.get("country"),
                country_name=raw.get("country_name"),
                organization_type=str(raw.get("organization_type") or "unknown"),
                featured=bool(raw.get("featured")),
                description=str(raw.get("description") or ""),
                brands=tuple(raw.get("brands") or [raw.get("display_name") or key]),
                registry_review=str(raw.get("registry_review") or "pending_review"),
                metadata_source=str(raw.get("metadata_source") or ""),
                ownership_note=str(raw.get("ownership_note") or ""),
                accept_exact=tuple(accept),
                reject_exact=tuple(reject),
                search_tokens=tuple(raw.get("search_tokens") or ()),
            )
        )

    pending = sum(1 for org in organizations if org.registry_review == "pending_review")
    if pending:
        warnings.append(str(pending) + " organization(s) have pending-review attribution and must be labelled provisional in the UI")

    return Registry(
        updated_at=str(payload.get("updated_at") or ""),
        matching_rule=str(payload.get("matching_rule") or ""),
        organizations=tuple(organizations),
        by_key={org.key: org for org in organizations},
        decisions=decisions,
        rejections=rejections,
        accepted_spellings_by_org={key: tuple(values) for key, values in accepted_by_org.items()},
        warnings=warnings,
    )


@lru_cache(maxsize=1)
def registry() -> Registry:
    payload = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    return _build_registry(payload)


# --------------------------------------------------------------------------- search
MATCH_RANK = {
    "legal_name": 0,
    "brand": 1,
    "ticker": 2,
    "alias": 3,
    "substring": 4,
    "applicant": 5,
}

MATCH_FIELD_ORDER = tuple(MATCH_RANK)


SHORT_QUERY_CHARS = 4


@dataclass
class SearchHit:
    organization: Organization
    match_field: str
    match_value: str
    rank: int


def search_organizations(query: str, applicant_names: Iterable[str]) -> tuple[list[SearchHit], list[str]]:
    """Rank tracked organizations for a query, with explicit match precedence.

    Precedence: exact legal name, exact brand, exact ticker, exact or prefix alias / brand,
    substring of the organization's own names, then substring of an attributed applicant name.

    Substring matching over *applicant strings* is disabled for very short queries because a
    two-letter query otherwise matches unrelated legal names. That is a deliberate anti-noise
    rule, documented in the API contract.
    """
    needle = normalise_applicant(query)
    if not needle:
        return [], []
    allow_applicant_substring = len(needle) >= SHORT_QUERY_CHARS
    hits: list[SearchHit] = []
    matched_applicants: list[str] = []
    for org in registry().organizations:
        best: SearchHit | None = None

        def consider(field: str, value: str) -> None:
            nonlocal best
            rank = MATCH_RANK[field]
            if best is None or rank < best.rank:
                best = SearchHit(organization=org, match_field=field, match_value=value, rank=rank)

        if org.legal_name and normalise_applicant(org.legal_name) == needle:
            consider("legal_name", org.legal_name)
        if normalise_applicant(org.display_name) == needle:
            consider("brand", org.display_name)
        if org.display_name_zh and normalise_applicant(org.display_name_zh) == needle:
            consider("brand", org.display_name_zh)
        if org.ticker and org.ticker.casefold() == needle:
            consider("ticker", org.ticker)

        if best is None:
            for decision in org.accept_exact:
                if normalise_applicant(decision.applicant_name) == needle:
                    consider("alias", decision.applicant_name)
                    break
        if best is None:
            own_names = [org.display_name, org.legal_name or "", *(org.brands or ())]
            for value in own_names:
                if value and normalise_applicant(value).startswith(needle):
                    consider("alias", value)
                    break
        if best is None:
            own_names = [org.display_name, org.legal_name or "", org.display_name_zh or "", *(org.brands or ())]
            for value in own_names:
                if value and needle in normalise_applicant(value):
                    consider("substring", value)
                    break
        if best is None and allow_applicant_substring:
            for decision in org.accept_exact:
                if needle in normalise_applicant(decision.applicant_name):
                    consider("applicant", decision.applicant_name)
                    break
        if best is not None:
            hits.append(best)
    hits.sort(key=lambda hit: (hit.rank, hit.organization.display_name.casefold()))

    if allow_applicant_substring:
        for name in applicant_names:
            if needle in normalise_applicant(name):
                matched_applicants.append(name)

    # Applicant-only matches already attributed to a hit organization are not interesting.
    attributed = {
        normalise_applicant(decision.applicant_name)
        for hit in hits
        for decision in hit.organization.accept_exact
    }
    applicant_only = [name for name in matched_applicants if normalise_applicant(name) not in attributed]
    return hits, applicant_only
