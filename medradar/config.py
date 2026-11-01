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

Paths are resolved, not hard-coded: ``MEDRADAR_CONFIG_DIR`` overrides the
config lookup (``config/`` in a checkout -> installed ``share/medradar/config``
-> in-package ``_config``) and ``MEDRADAR_HOME`` relocates every write
(``data/``, ``out/``, ``cache/``). A wheel install therefore never touches
``site-packages``. The public constants below keep their historical names so
``analyze``, ``report`` and ``live`` continue to work unchanged.
"""

from __future__ import annotations

import json
import os
import re
import site
import sys
import sysconfig
from pathlib import Path
from typing import Any, Iterable, Mapping

from .util import (
    contains_alias,
    norm_text,
    read_json,
    token_similarity,
    tokens,
)

# -------------------------------------------------------------------- path layout
# The package must run from three places: the git checkout (tests, `python -m
# medradar`), a normal/venv wheel install (`<prefix>/share/medradar/config`) and
# `pip install --target DIR` (data-files land beside the package). Resolution is
# therefore a chain, not a single constant.

#: This module's directory: ``<repo>/medradar`` or ``<site-packages>/medradar``.
PACKAGE_DIR = Path(__file__).resolve().parent
#: Repository root for a source checkout, otherwise the directory around the package.
SOURCE_ROOT = PACKAGE_DIR.parent
#: Optional last-resort config shipped *inside* the package (wheel fallback).
BUNDLED_CONFIG_DIR = PACKAGE_DIR / "_config"

_ENV_CONFIG_DIR = "MEDRADAR_CONFIG_DIR"
_ENV_HOME = "MEDRADAR_HOME"


def _data_prefixes() -> list[Path]:
    """Prefixes a wheel's ``data-files`` may have been installed under.

    * ``sysconfig.get_path("data")`` -- where ``pip install`` / virtualenvs put
      data-files (``<prefix>/share/medradar/...``).
    * ``sys.prefix`` -- belt and braces for exotic interpreters.
    * ``PACKAGE_DIR.parent`` -- ``pip install --no-deps --target DIR`` puts the
      data-files next to the package (``DIR/share/medradar/...``) rather than
      into an interpreter prefix, so a ``--target`` install stays importable
      and readable without any environment variable.
    * ``site.getuserbase()`` -- ``pip install --user`` puts them in the user base
      instead of the interpreter prefix.
    """
    raw: list[str | None] = []
    try:
        raw.append(sysconfig.get_path("data"))
    except (KeyError, OSError, TypeError):  # pragma: no cover - broken interpreter
        pass
    raw.extend([getattr(sys, "prefix", None), str(PACKAGE_DIR.parent)])
    try:
        raw.append(site.getuserbase() or None)
    except (AttributeError, OSError):  # pragma: no cover - exotic platform
        pass
    prefixes: list[Path] = []
    seen: set[str] = set()
    for item in raw:
        if not item:
            continue
        path = Path(item)
        key = os.path.normcase(str(path))
        if key not in seen:
            seen.add(key)
            prefixes.append(path)
    return prefixes


def share_candidates(name: str) -> list[Path]:
    """Candidate ``<prefix>/share/medradar/<name>`` directories (installed layouts)."""
    return [prefix / "share" / "medradar" / name for prefix in _data_prefixes()]


def _resolve_config(environ: Mapping[str, str] | None = None) -> tuple[Path, str]:
    """Resolve the config directory and report where it came from."""
    env = os.environ if environ is None else environ
    override = str(env.get(_ENV_CONFIG_DIR) or "").strip()
    if override:
        return Path(override).expanduser(), "env"
    source = SOURCE_ROOT / "config"
    if source.is_dir():
        return source, "source"
    for candidate in share_candidates("config"):
        if candidate.is_dir():
            return candidate, "installed"
    return BUNDLED_CONFIG_DIR, "package"


def resolve_config_dir(environ: Mapping[str, str] | None = None) -> Path:
    """Config directory for this interpreter.

    Chain: ``MEDRADAR_CONFIG_DIR`` -> source tree ``config/`` -> installed
    ``share/medradar/config`` -> in-package ``_config``.
    """
    return _resolve_config(environ)[0]


def resolve_home(environ: Mapping[str, str] | None = None) -> Path:
    """Writable data home.

    ``MEDRADAR_HOME`` wins; otherwise the repository root when running from a
    source checkout (so existing ``data/`` and ``out/`` keep working), else
    ``~/.medradar`` for an installed wheel. Nothing is ever written inside
    ``site-packages``.
    """
    env = os.environ if environ is None else environ
    override = str(env.get(_ENV_HOME) or "").strip()
    if override:
        return Path(override).expanduser()
    if (SOURCE_ROOT / "config").is_dir():
        return SOURCE_ROOT
    return Path(os.path.expanduser("~")) / ".medradar"


#: Data home: data/out/cache all live below it (``MEDRADAR_HOME``).
ROOT = resolve_home()
#: Resolved config directory and the rule that produced it
#: (``"env" | "source" | "installed" | "package"``).
CONFIG_DIR, CONFIG_ORIGIN = _resolve_config()
DATA_DIR = ROOT / "data"
OUT_DIR = ROOT / "out"
DOCS_DIR = ROOT / "docs"
CACHE_DIR = DATA_DIR / "cache"

DEFAULT_DB = DATA_DIR / "medradar.sqlite"
DEFAULT_METRICS = OUT_DIR / "metrics.json"
#: True when ``config/`` lives in the checkout (tests, developer CLI runs).
IS_SOURCE_TREE = (SOURCE_ROOT / "config").is_dir()


def load_config(name: str, default: Any = None) -> Any:
    """Load ``config/<name>.json`` (name may include a sub-directory).

    When the resolved config directory lacks a file (e.g. a stripped installed
    tree) the in-package ``_config`` copy is tried before falling back.
    """
    filename = name if name.endswith(".json") else f"{name}.json"
    payload = read_json(CONFIG_DIR / filename)
    if payload is None and BUNDLED_CONFIG_DIR != CONFIG_DIR:
        payload = read_json(BUNDLED_CONFIG_DIR / filename)
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
        self._frontier_keyword_map: list[tuple[str, str]] = []
        for track in tracks:
            track_id = track["id"]
            entry = dict(track)
            entry.setdefault("keywords", [])
            entry.setdefault("frontier_keywords", [])
            entry.setdefault("domain", entry.get("category") or "other")
            entry.setdefault("domain_zh", entry["domain"])
            self.tracks[track_id] = entry
            for keyword in entry["keywords"]:
                normalized = norm_text(keyword)
                if normalized:
                    self._keyword_map.append((normalized, track_id))
            for keyword in entry["frontier_keywords"]:
                normalized = norm_text(keyword)
                if normalized:
                    self._frontier_keyword_map.append((normalized, track_id))
        self._keyword_map.sort(key=lambda pair: len(pair[0]), reverse=True)
        self._frontier_keyword_map.sort(key=lambda pair: len(pair[0]), reverse=True)
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
        return self._match(text, self._keyword_map)

    def match_frontier_text(self, text: str | None) -> str | None:
        """Match emerging-technology vocabulary before ordinary device terms."""
        return self._match(text, self._frontier_keyword_map) or self.match_text(text)

    @staticmethod
    def _match(text: str | None, mapping: Iterable[tuple[str, str]]) -> str | None:
        haystack = f" {norm_text(text)} "
        if not haystack.strip():
            return None
        for keyword, track_id in mapping:
            if f" {keyword} " in haystack:
                return track_id
        return None

    def domain(self, track_id: str | None) -> dict[str, str]:
        entry = self.get(track_id) or {}
        return {
            "id": str(entry.get("domain") or "unclassified"),
            "name_zh": str(entry.get("domain_zh") or "未分类"),
        }


def load_companies(kind: str = "device") -> CompanyRegistry:
    payload = load_config(f"companies_{kind}", {"companies": []})
    return CompanyRegistry(payload.get("companies", []))


def load_tracks(kind: str = "device") -> TrackRegistry:
    """Load the curated track list plus the generated product-code mapping.

    ``config/product_code_tracks.json`` is produced by ``collect_device`` (about
    7,000 openFDA product codes mapped to a track). Keeping it separate from the
    hand-curated track list means the 7k-entry machine-generated file can be
    regenerated freely without touching reviewed knowledge.
    """
    payload = load_config(f"tracks_{kind}", {"tracks": []})
    product_codes = list(payload.get("product_codes", []))
    if kind == "device":
        generated = load_config("product_code_tracks", {})
        if isinstance(generated, dict):
            product_codes.extend(
                {"product_code": str(code), "track_id": track_id}
                for code, track_id in generated.items()
                if code and track_id
            )
    return TrackRegistry(payload.get("tracks", []), product_codes)
