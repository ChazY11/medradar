"""Versioned technology taxonomy: make a code remap visible as a version change, not as a technology change.

The detection layer's noise controls require this: the product-code-to-track mapping is unversioned, so if a code is
reassigned the event counts move without anything changing in the world, and a detector cannot tell the two apart.

This module gives the taxonomy a **version**, an **effective date**, and a **fingerprint** of the mapping itself:

  * `TAXONOMY_VERSION` names the current regime;
  * `EFFECTIVE_FROM` is the date the regime applies from;
  * `code_map_fingerprint()` hashes the committed mapping file, so an edit changes the fingerprint even if nobody
    remembers to bump the version;
  * `stamp(payload)` attaches the regime to any artifact that assigns tracks;
  * `regime_changed(recorded)` reports whether an artifact was produced under a different regime, which is the check a
    reader (or a snapshot diff) needs before comparing two periods.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, Mapping

TAXONOMY_VERSION = "tracks_device_2026-11"
EFFECTIVE_FROM = "2026-11-03"
CODE_MAP_PATH = Path("config/product_code_tracks.json")
TRACKS_PATH = Path("config/tracks_device.json")


def code_map_fingerprint(path: Path | None = None) -> str:
    """SHA-256 of the committed code map, so a remap is visible without relying on a manual version bump."""
    target = CODE_MAP_PATH if path is None else path
    data = target.read_bytes()
    return hashlib.sha256(data).hexdigest()


def track_fingerprint(path: Path | None = None) -> str:
    target = TRACKS_PATH if path is None else path
    return hashlib.sha256(target.read_bytes()).hexdigest()


def regime(*, code_map: Path | None = None, tracks: Path | None = None) -> dict[str, Any]:
    """The taxonomy regime: version, effective date and fingerprints of both mapping files."""
    return {
        "version": TAXONOMY_VERSION,
        "effective_from": EFFECTIVE_FROM,
        "code_map_fingerprint": code_map_fingerprint(code_map),
        "track_list_fingerprint": track_fingerprint(tracks),
        "note": ("a change in either fingerprint without a version bump is a taxonomy remap; artifacts produced "
                 "under different fingerprints are not directly comparable"),
    }


def stamp(payload: Mapping[str, Any], **kwargs: Any) -> dict[str, Any]:
    """Return a copy of `payload` with a `taxonomy` block attached."""
    stamped = dict(payload)
    stamped["taxonomy"] = regime(**kwargs)
    return stamped


def regime_changed(recorded: Mapping[str, Any] | None, **kwargs: Any) -> bool:
    """True when a recorded taxonomy block differs from the current regime in either fingerprint."""
    if not recorded:
        return False
    current = regime(**kwargs)
    return (recorded.get("code_map_fingerprint") != current["code_map_fingerprint"]
            or recorded.get("track_list_fingerprint") != current["track_list_fingerprint"])


def compare(recorded: Mapping[str, Any] | None, **kwargs: Any) -> dict[str, Any]:
    """Explain the comparison, for a snapshot diff or a manifest reader."""
    current = regime(**kwargs)
    if not recorded:
        return {"comparability": "unstated", "current": current,
                "reason": "the artifact records no taxonomy block, so its regime is unknown"}
    changed = regime_changed(recorded, **kwargs)
    return {
        "comparability": "regime changed" if changed else "same regime",
        "recorded": dict(recorded),
        "current": current,
        "reason": ("the code map or track list changed since the artifact was produced; counts across the two are "
                   "not directly comparable" if changed else
                   "both artifacts were produced under the same taxonomy fingerprints"),
    }
