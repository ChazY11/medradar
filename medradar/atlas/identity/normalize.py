"""Deterministic normalisation of names and official identifiers.

Nothing in this module guesses identity.  It only makes two *representations*
comparable: text is case/diacritic/punctuation folded, and identifier values are
canonicalised **within their own scheme**.  A normalised DI and a normalised
510(k) number are still two different identifiers and are never interchangeable
(see :mod:`medradar.atlas.identity.resolver`).

Ported from ``medradar.external_sources.identity`` (DATA-EXPANSION-001,
``origin/research/data-expansion-001``) and reduced to the pure functions so
that ATLAS has exactly one alias registry (``config/atlas_firms.json``).
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any, Mapping

#: Identifier schemes ATLAS understands.  ``issuer`` is part of the identity of
#: the *scheme*: ``di`` values are only comparable to other ``di`` values, and a
#: national licence number is not a model number even when the strings match.
SCHEMES: dict[str, dict[str, str]] = {
    "di": {"label": "UDI Device Identifier (DI)", "issuer": "GS1 / HIBCC / ICCBBA", "scope": "global"},
    "basic_udi_di": {"label": "Basic UDI-DI", "issuer": "EUDAMED", "scope": "eu"},
    "510k": {"label": "FDA 510(k) clearance number", "issuer": "FDA", "scope": "us"},
    "pma": {"label": "FDA PMA number", "issuer": "FDA", "scope": "us"},
    "denovo": {"label": "FDA De Novo number", "issuer": "FDA", "scope": "us"},
    "product_code": {"label": "FDA product code", "issuer": "FDA", "scope": "us-category"},
    "licence_no": {"label": "Health Canada MDALL licence number", "issuer": "Health Canada", "scope": "ca"},
    "mdall_device_id": {"label": "MDALL internal device id", "issuer": "Health Canada", "scope": "ca"},
    "mdall_company_id": {"label": "MDALL internal company id", "issuer": "Health Canada", "scope": "ca"},
    "duns": {"label": "DUNS number (labeler)", "issuer": "Dun & Bradstreet / FDA", "scope": "us"},
    "nct": {"label": "ClinicalTrials.gov NCT id", "issuer": "NLM", "scope": "global"},
    "doi": {"label": "DOI", "issuer": "Crossref", "scope": "global"},
    "pmid": {"label": "PubMed id", "issuer": "NLM", "scope": "global"},
    "patent_no": {"label": "Patent number", "issuer": "varies", "scope": "varies"},
    "ocid": {"label": "Open Contracting id", "issuer": "OCDS publisher", "scope": "varies"},
}

_LEGAL_SUFFIXES = frozenset(
    {
        "PLC", "INC", "INCORPORATED", "LTD", "LIMITED", "LLC", "LP", "LLP",
        "GMBH", "BV", "NV", "AG", "SA", "SAS", "SE", "AB", "AS", "OY", "KG",
        "CO", "CORP", "CORPORATION", "COMPANY", "HOLDINGS", "GROUP",
    }
)

_PUNCT = re.compile(r"[^\w\s\u4e00-\u9fff]", re.UNICODE)
_WS = re.compile(r"\s+")
_DI_SEP = re.compile(r"[\s\-]")
_510K_RE = re.compile(r"^K(\d{6})$", re.IGNORECASE)
_PMA_RE = re.compile(r"^P(\d{6})$", re.IGNORECASE)
_DENOVO_RE = re.compile(r"^(DEN\d{6}|N\d{6})$", re.IGNORECASE)


class IdentifierError(ValueError):
    """Raised when an identifier cannot be canonicalised for its scheme."""


#: German umlauts must transliterate to two letters (``ä`` -> ``ae``), not to a
#: bare vowel.  Otherwise "Drägerwerk" folds to "DRAGERWERK" and no longer
#: matches the ASCII alias "DRAEGERWERK" — a real false negative in the pilot.
_UMLAUTS = str.maketrans({"ä": "ae", "ö": "oe", "ü": "ue", "Ä": "AE", "Ö": "OE", "Ü": "UE", "ß": "ss"})


def normalize_name(value: Any) -> str:
    """Fold a company/brand string for comparison (never for display)."""
    if value is None:
        return ""
    text = unicodedata.normalize("NFKD", str(value).translate(_UMLAUTS))
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.upper().replace("&", " AND ")
    text = _PUNCT.sub(" ", text)
    text = _WS.sub(" ", text).strip()
    for _ in range(2):
        parts = text.split()
        if len(parts) > 1 and parts[-1] in _LEGAL_SUFFIXES:
            text = " ".join(parts[:-1]).strip()
    return text


#: Registry placeholders that look like labels but carry no information.  A
#: GUDID record with ``brand_name="NA"`` must not be treated as sharing a brand
#: with another ``NA`` record: that would manufacture a false "identical brand"
#: collision (and was a real defect found by the independent audit).
_PLACEHOLDER_LABELS = frozenset(
    {"NA", "N A", "N/A", "NONE", "NULL", "UNKNOWN", "NOT APPLICABLE", "NOT AVAILABLE", "0", "-"}
)


def is_placeholder_label(value: Any) -> bool:
    normalized = normalize_name(value)
    return normalized in _PLACEHOLDER_LABELS or len(normalized) < 2


def name_tokens(value: Any) -> tuple[str, ...]:
    return tuple(t for t in normalize_name(value).split() if t)


def token_subsequence(needle: tuple[str, ...], haystack: tuple[str, ...]) -> bool:
    """True when ``needle`` appears as consecutive tokens of ``haystack``."""
    if not needle:
        return False
    n = len(needle)
    for start in range(len(haystack) - n + 1):
        if haystack[start : start + n] == needle:
            return True
    return False


def normalize_di(value: Any) -> str:
    """UDI-DI: digits only, separators removed.

    A DI is an opaque numeric string assigned by an issuing agency.  We do not
    strip leading zeros: GS1 GTINs are 14 digits and the leading zeros are part
    of the value.
    """
    if value is None:
        return ""
    text = _DI_SEP.sub("", str(value)).strip()
    return text


def is_gtin_like(value: Any) -> bool:
    """True for 14-digit numeric DIs (the only shape three issuers share)."""
    text = normalize_di(value)
    return len(text) == 14 and text.isdigit()


def normalize_regulatory_number(value: Any) -> str:
    """FDA clearance numbers are case-insensitive: ``k123456`` -> ``K123456``."""
    if value is None:
        return ""
    text = str(value).strip().upper().replace(" ", "")
    if _510K_RE.match(text) or _PMA_RE.match(text) or _DENOVO_RE.match(text):
        return text
    return text


def normalize_licence_number(value: Any) -> str:
    """Health Canada licence numbers are integers; normalise to digits."""
    if value is None:
        return ""
    text = str(value).strip()
    return text if text.isdigit() else text.upper()


def normalize_product_code(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip().upper()


def normalize_doi(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip().lower()
    for prefix in ("https://doi.org/", "http://doi.org/", "doi:", "https://dx.doi.org/"):
        if text.startswith(prefix):
            text = text[len(prefix) :]
    return text


def normalize_patent_number(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip().upper()
    text = re.sub(r"\s+", "", text).replace(",", "")
    text = re.sub(r"[/\-]", "", text)
    return re.sub(r"([A-Z]{2}\d+)[A-Z]\d?$", r"\1", text)


def normalize_identifier(scheme: str, value: Any) -> str:
    """Canonicalise one value *within its scheme*."""
    scheme = str(scheme).strip().lower()
    if scheme not in SCHEMES:
        raise IdentifierError(f"unknown identifier scheme: {scheme!r}")
    if scheme == "di":
        return normalize_di(value)
    if scheme in {"510k", "pma", "denovo"}:
        return normalize_regulatory_number(value)
    if scheme == "licence_no":
        return normalize_licence_number(value)
    if scheme == "product_code":
        return normalize_product_code(value)
    if scheme == "doi":
        return normalize_doi(value)
    if scheme == "patent_no":
        return normalize_patent_number(value)
    if scheme in {"mdall_device_id", "mdall_company_id"}:
        return "" if value is None else str(value).strip()
    if scheme == "duns":
        return re.sub(r"\D", "", str(value or ""))
    return "" if value is None else str(value).strip()


def build_identifier(
    scheme: str, value: Any, *, is_primary: bool = False, note: str = ""
) -> dict[str, Any] | None:
    """Build one identifier dict, or ``None`` when the value is empty/invalid."""
    canonical = normalize_identifier(scheme, value)
    if not canonical:
        return None
    meta = SCHEMES[str(scheme).strip().lower()]
    return {
        "scheme": str(scheme).strip().lower(),
        "value": canonical,
        "raw_value": "" if value is None else str(value),
        "issuer": meta["issuer"],
        "scope": meta["scope"],
        "is_primary": bool(is_primary),
        "note": note,
    }


def identifiers_by_scheme(record: Mapping[str, Any]) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for ident in record.get("identifiers", []) or []:
        scheme = str(ident.get("scheme", "")).lower()
        value = str(ident.get("value", ""))
        if scheme and value:
            out.setdefault(scheme, []).append(value)
    return out


__all__ = [
    "IdentifierError",
    "SCHEMES",
    "build_identifier",
    "identifiers_by_scheme",
    "is_gtin_like",
    "name_tokens",
    "normalize_di",
    "normalize_doi",
    "normalize_identifier",
    "normalize_licence_number",
    "normalize_name",
    "normalize_patent_number",
    "normalize_product_code",
    "normalize_regulatory_number",
    "token_subsequence",
]
