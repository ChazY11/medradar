"""Paths, source registry and target-firm configuration for ATLAS.

Everything is resolved from the repository root so that a checkout and an
installed wheel behave the same way.  No environment variable is required and
no network call is made here.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Mapping

#: Repository root (the directory that contains ``medradar/`` and ``config/``).
ROOT = Path(__file__).resolve().parents[2]

#: Committed configuration (small, human-reviewable JSON).
CONFIG_DIR = ROOT / "config"

#: Generated research artefacts.  ``atlas/`` is git-ignored except for the
#: bounded, explicitly-redistributable samples listed in .gitignore rules.
RESEARCH_DIR = ROOT / "research" / "atlas"
STAGING_DIR = RESEARCH_DIR / "staging"
REPORTS_DIR = RESEARCH_DIR / "reports"
CACHE_DIR = RESEARCH_DIR / "cache"

#: Default database location.  Never inside ``data/`` (that belongs to the
#: legacy MedRadar runtime and must not be touched by ATLAS).
DEFAULT_DB = STAGING_DIR / "atlas.sqlite"

#: Run lock so two collectors cannot interleave writes into one database.
RUN_LOCK = STAGING_DIR / ".atlas.lock"


def env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def load_json(path: Path | str) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def load_firms(path: Path | str | None = None) -> dict[str, dict[str, Any]]:
    """Load the five target firms keyed by stable firm key.

    The file is committed under ``config/atlas_firms.json``.  Aliases are a
    *claim registry*: a string in a source only links to a firm when it matches
    one of these deliberately-curated aliases, never by fuzzy similarity.
    """
    payload = load_json(path or CONFIG_DIR / "atlas_firms.json")
    shared_terms = payload.get("search_terms") or {}
    firms: dict[str, dict[str, Any]] = {}
    for item in payload["firms"]:
        key = str(item["key"])
        firm = dict(item)
        # Merge the shared per-source search-term table into each firm so a
        # caller never has to know that it lives at the top level.
        firm["search_terms"] = {**dict(shared_terms.get(key) or {}), **dict(item.get("search_terms") or {})}
        firms[key] = firm
    return firms


def load_sources(path: Path | str | None = None) -> dict[str, dict[str, Any]]:
    """Load the ATLAS source register (access basis, licence, clocks)."""
    payload = load_json(path or CONFIG_DIR / "atlas_sources.json")
    return {str(item["source_id"]): dict(item) for item in payload["sources"]}


def ensure_dirs() -> None:
    for directory in (STAGING_DIR, REPORTS_DIR, CACHE_DIR):
        directory.mkdir(parents=True, exist_ok=True)


def relative(path: Path | str) -> str:
    """Repository-relative POSIX path, for stable report output."""
    p = Path(path).resolve()
    try:
        return p.relative_to(ROOT).as_posix()
    except ValueError:
        return p.as_posix()


__all__ = [
    "CACHE_DIR",
    "CONFIG_DIR",
    "DEFAULT_DB",
    "REPORTS_DIR",
    "RESEARCH_DIR",
    "ROOT",
    "STAGING_DIR",
    "ensure_dirs",
    "env",
    "load_firms",
    "load_json",
    "load_sources",
    "relative",
]
