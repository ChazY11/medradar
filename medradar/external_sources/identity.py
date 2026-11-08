"""Company and product identity for external evidence.

The rule this module enforces
-----------------------------
**A keyword in common is not an identity.**  A record is linked to a MedRadar
company only when one of these holds, in this order:

1. ``official_id`` — an authoritative identifier was matched (e.g. a known CIK,
   a UDI-DI already mapped to the company, a trial sponsor id).
2. ``exact_alias`` — the source's company string normalises to a registered
   alias of exactly one company, after token alignment and negative guards.
3. ``multi_field`` — two or more independent fields agree (name *and* country,
   or name *and* a product model already mapped to that company).

Anything weaker is stored as ``candidate`` with confidence < 0.9 and is
reported separately.  Candidates never enter a confirmed-link denominator.

The five firms targeted by DATA-EXPANSION-001
---------------------------------------------
Medtronic · GE HealthCare · Philips · Dräger · Mindray.  Their alias sets here
are deliberately broader than the openFDA submitter strings in
``config/companies_device.json``, because external sources use marketing names
("Philips Healthcare") rather than legal submitter entities.
"""

from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

#: The five firms this expansion round is anchored on.
TARGET_FIRM_KEYS: tuple[str, ...] = (
    "medtronic",
    "ge_healthcare",
    "philips",
    "draeger",
    "mindray",
)

#: Extra aliases observable in *external* sources (regulators, patents,
#: procurement, hiring).  Each alias must be distinctive enough not to collide
#: with an unrelated company; the guards below are part of the rule, not a
#: suggestion.
TARGET_FIRM_ALIASES: dict[str, tuple[str, ...]] = {
    "medtronic": (
        "MEDTRONIC",
        "MEDTRONIC PLC",
        "MEDTRONIC INC",
        "MEDTRONIC INTERNATIONAL",
        "MEDTRONIC INTERNATIONAL TRADING",
        "MEDTRONIC VASCULAR",
        "MEDTRONIC MINIMED",
        "MEDTRONIC SOFAMOR DANEK",
        "MEDTRONIC NEUROMODULATION",
        "MEDTRONIC CRYOCATH",
        "MEDTRONIC XOMED",
        "MEDTRONIC PUERTO RICO",
        "MEDTRONIC BAKKEN",
        "COVIDIEN",
        "COVIDIEN LP",
        "TYCO HEALTHCARE",
        "美敦力",
        "美敦力(上海)管理有限公司",
    ),
    "ge_healthcare": (
        "GE HEALTHCARE",
        "GE HEALTHCARE TECHNOLOGIES",
        "GE MEDICAL SYSTEMS",
        "GE HEALTHCARE GLOBAL",
        "GE MEDICAL SYSTEMS ULTRASOUND AND PRIMARY CARE DIAGNOSTICS",
        "GE HEALTHCARE FINLAND",
        "GE HEALTHCARE JAPAN",
        "GE医疗",
        "通用电气医疗",
        "通用电气医疗系统",
    ),
    "philips": (
        "PHILIPS",
        "KONINKLIJKE PHILIPS",
        "ROYAL PHILIPS",
        "PHILIPS HEALTHCARE",
        "PHILIPS MEDICAL SYSTEMS",
        "PHILIPS MEDICAL SYSTEMS NEDERLAND",
        "PHILIPS ELECTRONICS",
        "PHILIPS CONSUMER LIFESTYLE",
        "飞利浦",
        "皇家飞利浦",
    ),
    "draeger": (
        "DRAEGER",
        "DRAGER",
        "DRÄGER",
        "DRAEGERWERK",
        "DRÄGERWERK",
        "DRAEGER MEDICAL",
        "DRÄGER MEDICAL",
        "DRAEGER MEDICAL SYSTEMS",
        "DRÄGER MEDICAL SYSTEMS",
        "DRAEGER SAFETY",
        "德尔格",
        "德尔格医疗",
    ),
    "mindray": (
        "MINDRAY",
        "SHENZHEN MINDRAY",
        "SHENZHEN MINDRAY BIO MEDICAL ELECTRONICS",
        "MINDRAY BIO MEDICAL",
        "MINDRAY MEDICAL",
        "MINDRAY DS",
        "迈瑞",
        "深圳迈瑞",
        "深圳迈瑞生物医疗电子",
    ),
}

#: Strings that contain an alias token but are a *different* company.  Checked
#: before an alias match is accepted, and the alias match is demoted to
#: ``candidate`` (never dropped silently) when a guard fires.
NEGATIVE_GUARDS: dict[str, tuple[str, ...]] = {
    "philips": ("PHILIPS LIGHTING", "SIGNIFY", "PHILIPS MORRIS", "PHILIPS 66"),
    "medtronic": ("MEDTRONIC ENGINEERING CONSULTANTS",),
    "ge_healthcare": ("GE AVIATION", "GE VERNOVA", "GENERAL ELECTRIC AIRCRAFT", "GE RENEWABLE"),
    "mindray": ("MINDRAY SCIENCE AND TECHNOLOGY",),
    "draeger": ("DRAEGER SAFETY AG",),  # safety division: same group, not medical device
}

_LEGAL_SUFFIXES = (
    "PLC",
    "INC",
    "INCORPORATED",
    "LTD",
    "LIMITED",
    "LLC",
    "LP",
    "LLP",
    "GMBH",
    "BV",
    "B V",
    "NV",
    "N V",
    "AG",
    "SA",
    "SAS",
    "SE",
    "AB",
    "AS",
    "A S",
    "OY",
    "KG",
    "CO",
    "CORP",
    "CORPORATION",
    "COMPANY",
    "HOLDINGS",
    "GROUP",
)

_PUNCT = re.compile(r"[^\w\s\u4e00-\u9fff]", re.UNICODE)
_WS = re.compile(r"\s+")


def normalize_name(value: Any) -> str:
    """Uppercase, strip diacritics/punctuation and trailing legal suffixes."""
    if value is None:
        return ""
    text = unicodedata.normalize("NFKD", str(value))
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.upper().replace("&", " AND ")
    text = _PUNCT.sub(" ", text)
    text = _WS.sub(" ", text).strip()
    # Drop one trailing legal suffix; repeat for "CO LTD".
    for _ in range(2):
        parts = text.split()
        if len(parts) > 1 and parts[-1] in _LEGAL_SUFFIXES:
            text = " ".join(parts[:-1]).strip()
    return text


def _tokens(value: str) -> list[str]:
    return [t for t in normalize_name(value).split() if t]


def _is_token_subsequence(alias_tokens: Sequence[str], candidate_tokens: Sequence[str]) -> bool:
    """Alias tokens must appear consecutively (allowing legal-suffix gaps)."""
    if not alias_tokens:
        return False
    n = len(alias_tokens)
    for start in range(len(candidate_tokens) - n + 1):
        if list(candidate_tokens[start : start + n]) == list(alias_tokens):
            return True
    return False


class CompanyIndex:
    """Alias index over ``config/companies_device.json`` plus the target firms."""

    def __init__(self, companies: Sequence[Mapping[str, Any]]) -> None:
        self._aliases: list[tuple[tuple[str, ...], str]] = []
        self._companies: dict[str, Mapping[str, Any]] = {}
        for company in companies:
            key = str(company.get("key", "")).strip()
            if not key:
                continue
            self._companies[key] = company
            names = [company.get("name_en", ""), company.get("name_zh", "")]
            names.extend(company.get("aliases", []) or [])
            for name in names:
                toks = tuple(_tokens(str(name)))
                if toks:
                    self._aliases.append((toks, key))
        for key, extra in TARGET_FIRM_ALIASES.items():
            for name in extra:
                toks = tuple(_tokens(name))
                if toks:
                    self._aliases.append((toks, key))
        # Longest alias first so "PHILIPS MEDICAL SYSTEMS" beats "PHILIPS".
        self._aliases.sort(key=lambda item: (-len(item[0]), item[0]))

    @classmethod
    def from_config(cls, path: Path | str | None = None) -> "CompanyIndex":
        if path is None:
            path = Path(__file__).resolve().parents[2] / "config" / "companies_device.json"
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls(payload.get("companies", []))

    def company(self, key: str) -> Mapping[str, Any] | None:
        return self._companies.get(key)

    def keys(self) -> list[str]:
        return sorted(self._companies)

    def guard_hit(self, key: str, normalized: str) -> str:
        """Return the guard phrase that disqualifies an alias match.

        Containment is token-aligned and one-directional: the guard phrase must
        appear inside the candidate name.  The reverse direction ("the name is a
        truncation of a guard phrase") is only allowed when the name itself has
        two or more tokens, so that a bare ``PHILIPS`` is not demoted merely
        because ``PHILIPS 66`` exists.
        """
        name_tokens = normalized.split()
        for guard in NEGATIVE_GUARDS.get(key, ()):
            guard_tokens = normalize_name(guard).split()
            if _is_token_subsequence(guard_tokens, name_tokens):
                return guard
            if len(name_tokens) >= 2 and _is_token_subsequence(name_tokens, guard_tokens):
                return guard
        return ""

    def resolve(self, raw_name: Any, *, country: str = "") -> dict[str, Any]:
        """Resolve one source company string into a deterministic or candidate link."""
        normalized = normalize_name(raw_name)
        if not normalized:
            return _none_resolution(raw_name, "empty name")
        candidate_tokens = normalized.split()
        for alias_tokens, key in self._aliases:
            if _is_token_subsequence(alias_tokens, candidate_tokens):
                guard = self.guard_hit(key, normalized)
                if guard:
                    return {
                        "entity_type": "company",
                        "name_raw": str(raw_name),
                        "resolved_key": key,
                        "method": "candidate",
                        "confidence": 0.55,
                        "evidence": {
                            "matched_alias": " ".join(alias_tokens),
                            "negative_guard": guard,
                            "country_field": country,
                            "normalized": normalized,
                        },
                        "note": "alias matched but a negative guard fired; kept as a candidate only",
                    }
                return {
                    "entity_type": "company",
                    "name_raw": str(raw_name),
                    "resolved_key": key,
                    "method": "exact_alias",
                    "confidence": 0.95,
                    "evidence": {
                        "matched_alias": " ".join(alias_tokens),
                        "registry": "config/companies_device.json + target-firm aliases",
                        "normalized": normalized,
                    },
                    "note": "",
                }
        return _candidate_resolution(raw_name, normalized, self, country)


def _none_resolution(raw_name: Any, note: str) -> dict[str, Any]:
    return {
        "entity_type": "company",
        "name_raw": "" if raw_name is None else str(raw_name),
        "resolved_key": None,
        "method": "none",
        "confidence": 0.0,
        "evidence": {},
        "note": note,
    }


def _candidate_resolution(
    raw_name: Any, normalized: str, index: CompanyIndex, country: str
) -> dict[str, Any]:
    """Token-overlap suggestion.  Always ``candidate``, never confirmed."""
    tokens = set(normalized.split())
    if not tokens:
        return _none_resolution(raw_name, "no tokens")
    best: tuple[float, str, tuple[str, ...]] | None = None
    for alias_tokens, key in index._aliases:  # noqa: SLF001 - same module
        if len(alias_tokens) < 2:  # a single common token is not a candidate basis
            continue
        overlap = len(tokens & set(alias_tokens)) / len(alias_tokens)
        if overlap >= 0.75 and (best is None or overlap > best[0]):
            best = (overlap, key, alias_tokens)
    if best is None:
        return _none_resolution(raw_name, "no alias overlap >= 0.75")
    overlap, key, alias_tokens = best
    return {
        "entity_type": "company",
        "name_raw": str(raw_name),
        "resolved_key": key,
        "method": "candidate",
        "confidence": round(min(0.75, 0.4 + 0.3 * overlap), 3),
        "evidence": {
            "overlap": round(overlap, 3),
            "alias": " ".join(alias_tokens),
            "country_field": country,
            "normalized": normalized,
        },
        "note": "semantic candidate — must not be counted as a confirmed link",
    }


def multi_field_link(
    name_resolution: Mapping[str, Any], *, agreeing_fields: Iterable[str]
) -> dict[str, Any]:
    """Promote an alias match to ``multi_field`` when independent fields agree."""
    fields = [f for f in agreeing_fields if f]
    out = dict(name_resolution)
    if out.get("method") == "exact_alias" and len(fields) >= 1:
        out["method"] = "multi_field"
        out["confidence"] = 0.97
        evidence = dict(out.get("evidence", {}))
        evidence["agreeing_fields"] = fields
        out["evidence"] = evidence
        out["note"] = "company string plus independent field agreement"
    return out


# ------------------------------------------------------------------ product ids
_DI_RE = re.compile(r"[\s\-]")
_510K_RE = re.compile(r"^K(\d{6})$", re.IGNORECASE)
_PMA_RE = re.compile(r"^P(\d{6})$", re.IGNORECASE)


def normalize_di(value: Any) -> str:
    """Device Identifier: digits only, no separators (GS1/HIBCC/ICCBBA)."""
    if value is None:
        return ""
    return _DI_RE.sub("", str(value)).strip()


def normalize_regulatory_number(value: Any) -> str:
    """Normalise 510(k)/PMA/De Novo style numbers: ``k123456`` -> ``K123456``."""
    if value is None:
        return ""
    text = str(value).strip().upper().replace(" ", "")
    if _510K_RE.match(text) or _PMA_RE.match(text):
        return text
    return text


def normalize_doi(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip().lower()
    for prefix in ("https://doi.org/", "http://doi.org/", "doi:", "https://dx.doi.org/"):
        if text.startswith(prefix):
            text = text[len(prefix) :]
    return text


def normalize_patent_number(value: Any) -> str:
    """Canonical patent number without kind code or punctuation: ``US 10,123,456 B2``."""
    if value is None:
        return ""
    text = str(value).strip().upper()
    text = re.sub(r"\s+", "", text)
    text = text.replace(",", "")
    text = re.sub(r"[/\-]", "", text)
    text = re.sub(r"([A-Z]{2}\d+)[A-Z]\d?$", r"\1", text)
    return text


def build_identifier(scheme: str, value: Any, *, is_primary: bool = False, note: str = "") -> dict[str, Any] | None:
    """Build one identifier entry, normalising by scheme.  ``None`` if empty."""
    raw = value
    if scheme == "di":
        value = normalize_di(value)
    elif scheme in {"510k", "pma", "denovo"}:
        value = normalize_regulatory_number(value)
    elif scheme == "doi":
        value = normalize_doi(value)
    elif scheme == "patent_no":
        value = normalize_patent_number(value)
    else:
        value = "" if value is None else str(value).strip()
    if not value:
        return None
    return {
        "scheme": scheme,
        "value": value,
        "raw_value": "" if raw is None else str(raw),
        "is_primary": bool(is_primary),
        "note": note,
    }


def identifiers_of(record: Mapping[str, Any]) -> dict[str, str]:
    """Flatten a record's identifiers into ``{scheme: value}``."""
    out: dict[str, str] = {}
    for ident in record.get("identifiers", []) or []:
        scheme = str(ident.get("scheme", "")).lower()
        value = str(ident.get("value", ""))
        if scheme and value:
            out.setdefault(scheme, value)
    return out
