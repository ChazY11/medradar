"""Identity comparison: what may be called the same thing, and on what basis.

The resolver answers a narrow, auditable question: given two records that each
describe a device (or a company), what relation — if any — is supported, and
which *kind of authority* supports it?

Three authorities, never mixed
------------------------------
``source_declared``
    Both records carry the same official identifier (same scheme, same value).
    The sources themselves assert the identifier; ATLAS only compares strings.
``derived``
    Two or more independent fields agree (company + model, company + product
    code).  Structured inference, reproducible from the records.
``inferred``
    Name/semantic similarity only.  Always a candidate, never confirmed.

Relation types
--------------
``SAME_DEVICE_IDENTITY``  same regulatory device record (needs an official id)
``SAME_MODEL``            same manufacturer model string, different device id
``SAME_PRODUCT_FAMILY``   same family/product-code grouping, not one device
``RELATED_TECHNOLOGY``    same technology category, different products
``POSSIBLE_MATCH``        unresolved candidate
``UNRELATED``             positive evidence of non-identity (a negative control)
``UNKNOWN``               insufficient fields to decide

Important negative rule: a matching *name* is never evidence of identity.  Two
different manufacturers can sell the same brand string; the resolver returns
``UNRELATED`` for that case and records the reason, which is what makes the
hard-negative tests meaningful.
"""

from __future__ import annotations

import difflib
from dataclasses import dataclass, field
from typing import Any, Mapping

from .normalize import is_placeholder_label, name_tokens, normalize_name

SAME_DEVICE_IDENTITY = "SAME_DEVICE_IDENTITY"
SAME_MODEL = "SAME_MODEL"
SAME_PRODUCT_FAMILY = "SAME_PRODUCT_FAMILY"
RELATED_TECHNOLOGY = "RELATED_TECHNOLOGY"
POSSIBLE_MATCH = "POSSIBLE_MATCH"
UNRELATED = "UNRELATED"
UNKNOWN = "UNKNOWN"

RELATION_TYPES = frozenset(
    {
        SAME_DEVICE_IDENTITY,
        SAME_MODEL,
        SAME_PRODUCT_FAMILY,
        RELATED_TECHNOLOGY,
        POSSIBLE_MATCH,
        UNRELATED,
        UNKNOWN,
    }
)

CONFIRMED = "CONFIRMED"
CANDIDATE = "CANDIDATE"
REJECTED = "REJECTED"
UNDECIDED = "UNKNOWN"

STATUSES = frozenset({CONFIRMED, CANDIDATE, REJECTED, UNDECIDED})

SOURCE_DECLARED = "source_declared"
DERIVED = "derived"
INFERRED = "inferred"
AUTHORITIES = frozenset({SOURCE_DECLARED, DERIVED, INFERRED})

#: Relation types a caller may treat as identity.  Everything else is either
#: weaker than identity or an explicit non-identity.
IDENTITY_CONFIRMING_TYPES = frozenset({SAME_DEVICE_IDENTITY})


@dataclass(frozen=True)
class DeviceView:
    """The identity-bearing fields of one record, flattened for comparison."""

    ref: str
    source_id: str
    evidence_id: str = ""
    firm_key: str = ""
    company_raw: str = ""
    brand: str = ""
    model: str = ""
    product_codes: tuple[str, ...] = ()
    di: str = ""
    device_class: str = ""
    country: str = ""
    identifiers: tuple[tuple[str, str], ...] = ()

    @property
    def normalized_brand(self) -> str:
        normalized = normalize_name(self.brand)
        return "" if is_placeholder_label(normalized) else normalized

    @property
    def brand_tokens(self) -> tuple[str, ...]:
        if not self.normalized_brand:
            return ()
        return tuple(t for t in self.normalized_brand.split() if t)

    @property
    def normalized_model(self) -> str:
        normalized = normalize_name(self.model)
        return "" if is_placeholder_label(normalized) else normalized

    def has_identity_anchor(self) -> bool:
        return bool(self.di) or any(
            scheme in {"510k", "pma", "denovo", "licence_no"} for scheme, _ in self.identifiers
        )


@dataclass
class MatchDecision:
    left_ref: str
    right_ref: str
    relation_type: str
    status: str
    method: str
    authority: str
    confidence: float
    basis: dict[str, Any] = field(default_factory=dict)
    contradictions: list[str] = field(default_factory=list)
    rejection_reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "left_ref": self.left_ref,
            "right_ref": self.right_ref,
            "relation_type": self.relation_type,
            "status": self.status,
            "method": self.method,
            "authority": self.authority,
            "confidence": round(self.confidence, 3),
            "basis": self.basis,
            "contradictions": self.contradictions,
            "rejection_reason": self.rejection_reason,
        }


def _shared_scheme(left: DeviceView, right: DeviceView, scheme: str) -> list[str]:
    left_values = {v for s, v in left.identifiers if s == scheme}
    if scheme == "di" and left.di:
        left_values.add(left.di)
    right_values = {v for s, v in right.identifiers if s == scheme}
    if scheme == "di" and right.di:
        right_values.add(right.di)
    return sorted(left_values & right_values)


def _brand_agreement(left: DeviceView, right: DeviceView) -> float:
    """Token Jaccard over brand strings; 0.0 when either side has no brand."""
    a, b = set(left.brand_tokens), set(right.brand_tokens)
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def compare_devices(left: DeviceView, right: DeviceView) -> MatchDecision:
    """Classify one device-record pair.  Pure and deterministic."""
    if left.ref == right.ref:
        return MatchDecision(
            left.ref, right.ref, UNKNOWN, UNDECIDED, "self", DERIVED, 0.0,
            basis={"note": "a record compared with itself is not evidence"},
        )

    shared_di = _shared_scheme(left, right, "di")
    if shared_di:
        model_conflict = bool(
            left.normalized_model
            and right.normalized_model
            and left.normalized_model != right.normalized_model
        )
        brand_overlap = _brand_agreement(left, right)
        contradictions: list[str] = []
        if model_conflict:
            contradictions.append("same DI but different model number")
        if left.brand and right.brand and brand_overlap == 0.0:
            contradictions.append("same DI but disjoint brand names")
        basis = {
            "shared_identifier": f"di:{shared_di[0]}",
            "shared_fields": ["di"],
            "model_left": left.model,
            "model_right": right.model,
            "brand_left": left.brand,
            "brand_right": right.brand,
        }
        if contradictions:
            # The identifier says same; the descriptive fields disagree.  Do not
            # silently pick a winner: keep the identifier evidence, flag the
            # conflict, and leave the relation as a candidate.
            return MatchDecision(
                left.ref, right.ref, SAME_DEVICE_IDENTITY, CANDIDATE, "official_identifier",
                SOURCE_DECLARED, 0.6, basis=basis, contradictions=contradictions,
                rejection_reason="identifier agrees but descriptive fields conflict",
            )
        return MatchDecision(
            left.ref, right.ref, SAME_DEVICE_IDENTITY, CONFIRMED, "official_identifier",
            SOURCE_DECLARED, 0.99, basis=basis,
        )

    for scheme in ("510k", "pma", "denovo", "licence_no", "basic_udi_di", "mdall_device_id"):
        shared = _shared_scheme(left, right, scheme)
        if not shared:
            continue
        # A shared clearance/licence means "same regulatory grouping", not the
        # same device: many models can sit under one 510(k) or one licence.
        return MatchDecision(
            left.ref, right.ref, SAME_PRODUCT_FAMILY, CONFIRMED, "official_identifier",
            SOURCE_DECLARED, 0.9,
            basis={
                "shared_identifier": f"{scheme}:{shared[0]}",
                "shared_fields": [scheme],
                "note": "a shared regulatory number groups products; it does not identify one device",
            },
        )

    same_firm = bool(left.firm_key) and left.firm_key == right.firm_key
    same_model = bool(left.normalized_model) and left.normalized_model == right.normalized_model
    codes_left, codes_right = set(left.product_codes), set(right.product_codes)
    shared_codes = sorted(codes_left & codes_right)

    if same_firm and same_model:
        return MatchDecision(
            left.ref, right.ref, SAME_MODEL, CONFIRMED, "field_agreement", DERIVED, 0.85,
            basis={"shared_fields": ["firm_key", "model"], "firm_key": left.firm_key,
                   "model": left.model},
        )

    if same_firm and shared_codes:
        return MatchDecision(
            left.ref, right.ref, SAME_PRODUCT_FAMILY, CONFIRMED, "field_agreement", DERIVED, 0.8,
            basis={"shared_fields": ["firm_key", "product_code"], "firm_key": left.firm_key,
                   "shared_product_codes": shared_codes},
        )

    if same_firm and (codes_left or codes_right) and not shared_codes:
        return MatchDecision(
            left.ref, right.ref, UNRELATED, REJECTED, "field_agreement", DERIVED, 0.75,
            basis={"firm_key": left.firm_key, "product_codes_left": sorted(codes_left),
                   "product_codes_right": sorted(codes_right)},
            rejection_reason="same company but disjoint FDA product codes: different device categories",
        )

    if left.normalized_brand and left.normalized_brand == right.normalized_brand and not same_firm:
        return MatchDecision(
            left.ref, right.ref, UNRELATED, REJECTED, "name_only", INFERRED, 0.7,
            basis={"normalized_brand": left.normalized_brand, "firm_left": left.firm_key,
                   "firm_right": right.firm_key},
            rejection_reason="identical brand name but different manufacturers: brand strings are not identities",
        )

    if shared_codes and not same_firm:
        return MatchDecision(
            left.ref, right.ref, RELATED_TECHNOLOGY, CANDIDATE, "field_agreement", DERIVED, 0.5,
            basis={"shared_product_codes": shared_codes, "firm_left": left.firm_key,
                   "firm_right": right.firm_key},
        )

    # A shared distinctive brand token across different firms is a *candidate*
    # signal, nothing more: "CONTROL" or "SYSTEM" can be shared vocabulary.
    # It must never be promoted; it exists so the ambiguity is visible.
    shared_tokens = sorted(
        {t for t in left.brand_tokens if len(t) >= 5}
        & {t for t in right.brand_tokens if len(t) >= 5}
    )
    if shared_tokens and not same_firm:
        return MatchDecision(
            left.ref, right.ref, POSSIBLE_MATCH, CANDIDATE, "label_token_overlap", INFERRED, 0.6,
            basis={"shared_brand_tokens": shared_tokens, "firm_left": left.firm_key,
                   "firm_right": right.firm_key,
                   "note": "shared name token only; not an identity signal"},
        )

    similarity = name_similarity(left, right)
    if similarity >= 0.85:
        return MatchDecision(
            left.ref, right.ref, POSSIBLE_MATCH, CANDIDATE, "name_similarity", INFERRED,
            round(min(0.8, similarity), 3),
            basis={"name_similarity": round(similarity, 3),
                   "note": "semantic only; cannot become confirmed without an official identifier"},
        )

    if not left.has_identity_anchor() and not right.has_identity_anchor():
        return MatchDecision(
            left.ref, right.ref, UNKNOWN, UNDECIDED, "insufficient_fields", DERIVED, 0.0,
            basis={"note": "neither record carries an official identifier"},
        )

    return MatchDecision(
        left.ref, right.ref, UNRELATED, REJECTED, "field_agreement", DERIVED, 0.6,
        basis={},
        rejection_reason="no shared official identifier, firm, model, product code or brand",
    )


def name_similarity(left: DeviceView, right: DeviceView) -> float:
    """Naive label similarity used by the *baseline*, not by identity logic."""
    a = " ".join(x for x in (left.normalized_brand, left.normalized_model) if x)
    b = " ".join(x for x in (right.normalized_brand, right.normalized_model) if x)
    if not a or not b:
        return 0.0
    return difflib.SequenceMatcher(None, a, b).ratio()


def baseline_name_match(left: DeviceView, right: DeviceView, threshold: float = 0.85) -> bool:
    """The simple name-matching baseline this project must beat or bound.

    Deliberately generous: brand OR model similarity above the threshold counts
    as a match, which is roughly how a name-only entity resolver behaves.
    """
    if not left.brand and not right.brand and not left.model and not right.model:
        return False
    brand_ratio = difflib.SequenceMatcher(
        None, left.normalized_brand, right.normalized_brand
    ).ratio() if left.normalized_brand and right.normalized_brand else 0.0
    model_ratio = difflib.SequenceMatcher(
        None, left.normalized_model, right.normalized_model
    ).ratio() if left.normalized_model and right.normalized_model else 0.0
    return max(brand_ratio, model_ratio) >= threshold or name_similarity(left, right) >= threshold


def view_from_evidence(record: Mapping[str, Any]) -> DeviceView:
    """Build a :class:`DeviceView` from one ATLAS evidence record."""
    normalized = record.get("normalized") or {}
    identifiers = tuple(
        (str(i.get("scheme", "")), str(i.get("value", "")))
        for i in record.get("identifiers", []) or []
        if i.get("scheme") and i.get("value")
    )
    firm = ""
    for ref in record.get("entity_refs", []) or []:
        if ref.get("entity_type") == "company" and ref.get("method") in {
            "official_id", "exact_alias", "multi_field"
        }:
            firm = str(ref.get("firm_key") or ref.get("resolved_key") or "")
            break
    di = ""
    for scheme, value in identifiers:
        if scheme == "di":
            di = value
            break
    return DeviceView(
        ref=str(record.get("evidence_id", "")),
        source_id=str(record.get("source_id", "")),
        evidence_id=str(record.get("evidence_id", "")),
        firm_key=firm,
        company_raw=str(normalized.get("company_name") or normalized.get("applicant") or ""),
        brand=str(normalized.get("brand_name") or normalized.get("trade_name") or ""),
        model=str(
            normalized.get("version_or_model_number")
            or normalized.get("catalog_number")
            or normalized.get("device_identifier")
            or ""
        ),
        product_codes=tuple(
            sorted(
                {
                    *(str(c) for c in normalized.get("product_codes") or []),
                    *(v for s, v in identifiers if s == "product_code"),
                }
            )
        ),
        di=di,
        device_class=str(normalized.get("device_class") or ""),
        country=str(normalized.get("country") or ""),
        identifiers=identifiers,
    )


__all__ = [
    "AUTHORITIES",
    "CANDIDATE",
    "CONFIRMED",
    "DERIVED",
    "DeviceView",
    "IDENTITY_CONFIRMING_TYPES",
    "INFERRED",
    "MatchDecision",
    "POSSIBLE_MATCH",
    "REJECTED",
    "RELATED_TECHNOLOGY",
    "RELATION_TYPES",
    "SAME_DEVICE_IDENTITY",
    "SAME_MODEL",
    "SAME_PRODUCT_FAMILY",
    "SOURCE_DECLARED",
    "STATUSES",
    "UNDECIDED",
    "UNKNOWN",
    "UNRELATED",
    "baseline_name_match",
    "compare_devices",
    "name_similarity",
    "view_from_evidence",
]
