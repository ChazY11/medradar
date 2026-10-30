"""Project paths, JSON configuration and the two fuzzy registries.

The whole product hinges on two normalisation problems:

1. **Applicant names.** openFDA stores whatever the submitter typed -
   ``MEDTRONIC MINIMED``, ``Medtronic Sofamor Danek USA, Inc.``,
   ``Covidien (Part of Medtronic)``. A token-containment match against a
   curated alias list resolves the vast majority; anything below the confidence
   floor is deliberately left unmatched instead of guessed.
2. **Product codes.** ~6,500 openFDA device product codes are mapped to a
   curated Chinese track dictionary (手术机器人 / 结构性心脏 / CGM ...). The
   mapping lives in ``config/tracks_device.json`` and can be extended without
   touching code.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Iterable, Mapping

from .util import (
    contains_alias,
    norm_text,
    read_json,
    token_similarity,
    tokens,
)

ROOT = Path(__file__).resolve().parents[1]
CONFIG_DIR = ROOT / "config"
DATA_DIR = ROOT / "data"
OUT_DIR = ROOT / "out"
DOCS_DIR = ROOT / "docs"
CACHE_DIR = DATA_DIR / "cache"

DEFAULT_DB = DATA_DIR / "medradar.sqlite"
DEFAULT_METRICS = OUT_DIR / "metrics.json"


def load_config(name: str, default: Any = None) -> Any:
    """Load ``config/<name>.json`` (name may include a sub-directory)."""
    path = CONFIG_DIR / (name if name.endswith(".json") else f"{name}.json")
    payload = read_json(path)
    if payload is None:
        return default if default is not None else {}
    return payload


class CompanyRegistry:
    """Resolve messy applicant strings to curated company keys."""

    def __init__(self, companies: Iterable[Mapping[str, Any]]) -> None:
        self.companies: dict[str, dict[str, Any]] = {}
        self._alias_index: list[tuple[str, str]] = []  # (normalized alias, key)
        for company in companies:
            key = company["key"]
            entry = dict(company)
            entry.setdefault("aliases", [])
            self.companies[key] = entry
            for alias in [entry.get("name_en", ""), key, *entry["aliases"]]:
                if norm_text(alias):
                    self._alias_index.append((norm_text(alias), key))
        # Longest alias first so "MEDTRONIC MINIMED" wins over "MEDTRONIC".
        self._alias_index.sort(key=lambda pair: len(pair[0]), reverse=True)

    # ------------------------------------------------------------------ lookups
    def get(self, key: str | None) -> dict[str, Any] | None:
        return self.companies.get(key or "")

    def all(self) -> list[dict[str, Any]]:
        return list(self.companies.values())

    def keys(self) -> list[str]:
        return list(self.companies)

    def major_keys(self) -> list[str]:
        return [key for key, value in self.companies.items() if value.get("is_major")]

    def tickers(self) -> dict[str, str]:
        return {
            key: value["ticker"]
            for key, value in self.companies.items()
            if value.get("ticker")
        }

    def resolve(self, applicant: str, min_score: float = 0.82) -> tuple[str | None, float, str]:
        """Return ``(company_key, confidence, matched_alias)``.

        Confidence ``1.0`` = exact alias, ``0.95`` = all alias tokens present in
        the applicant string, otherwise token Jaccard. Unmatched stays
        unmatched on purpose: false negatives are visible, false positives
        silently poison every downstream metric.
        """
        raw = norm_text(applicant)
        if not raw:
            return None, 0.0, ""
        best_key, best_score, best_alias = None, 0.0, ""
        for alias, key in self._alias_index:
            if raw == alias:
                return key, 1.0, alias
            if contains_alias(raw, alias):
                score = 0.95 + min(0.04, 0.001 * len(tokens(alias)))
                if score > best_score:
                    best_key, best_score, best_alias = key, score, alias
                continue
            score = token_similarity(raw, alias)
            if score > best_score:
                best_key, best_score, best_alias = key, score, alias
        if best_key and best_score >= min_score:
            return best_key, round(best_score, 3), best_alias
        return None, round(best_score, 3), best_alias


class TrackRegistry:
    """Map product codes and free text to a curated Chinese track id."""

    def __init__(
        self,
        tracks: Iterable[Mapping[str, Any]],
        product_codes: Iterable[Mapping[str, Any]] | None = None,
    ) -> None:
        self.tracks: dict[str, dict[str, Any]] = {}
        self._code_map: dict[str, str] = {}
        self._keyword_map: list[tuple[str, str]] = []
        for track in tracks:
            track_id = track["id"]
            entry = dict(track)
            entry.setdefault("keywords", [])
            self.tracks[track_id] = entry
            for keyword in entry["keywords"]:
                normalized = norm_text(keyword)
                if normalized:
                    self._keyword_map.append((normalized, track_id))
        self._keyword_map.sort(key=lambda pair: len(pair[0]), reverse=True)
        for code in product_codes or []:
            code_id = str(code.get("product_code", "")).strip()
            if code_id and code.get("track_id"):
                self._code_map[code_id] = code["track_id"]

    def all(self) -> list[dict[str, Any]]:
        return list(self.tracks.values())

    def ids(self) -> list[str]:
        return list(self.tracks)

    def get(self, track_id: str | None) -> dict[str, Any] | None:
        return self.tracks.get(track_id or "")

    def name_zh(self, track_id: str | None, fallback: str = "未分类") -> str:
        entry = self.get(track_id)
        return entry.get("name_zh") or fallback if entry else fallback

    def for_product_code(self, product_code: str | None) -> str | None:
        return self._code_map.get(str(product_code or "").strip())

    def match_text(self, text: str | None) -> str | None:
        """Longest-keyword containment match, used for trial conditions."""
        haystack = f" {norm_text(text)} "
        if not haystack.strip():
            return None
        for keyword, track_id in self._keyword_map:
            if f" {keyword} " in haystack:
                return track_id
        return None


def load_companies(kind: str = "device") -> CompanyRegistry:
    payload = load_config(f"companies_{kind}", {"companies": []})
    return CompanyRegistry(payload.get("companies", []))


def load_tracks(kind: str = "device") -> TrackRegistry:
    payload = load_config(f"tracks_{kind}", {"tracks": []})
    product_codes = payload.get("product_codes", [])
    return TrackRegistry(payload.get("tracks", []), product_codes)
