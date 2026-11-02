"""Deterministic therapy-area -> device-track crosswalk from the store's own keyword lists.

The trial lane assigns therapy-area tracks (`t_oncology`, `t_cardiometabolic`, …) while the study's technology tracks are
device tracks (`imaging_us`, `cardiac_rhythm`, …). The two taxonomies cannot be joined by id, so this module joins them
by **text**: a trial's condition/title is matched against each device track's own keyword list (the `tracks.keywords`
column already used by the product-code mapper).

Rules, all deterministic:

  * keywords are upper-cased and must be at least ``MIN_KEYWORD_CHARS`` long (short tokens like `COIL` are excluded to
    avoid matching ordinary words);
  * a track is a candidate only if its keyword occurs as a whole token sequence in the text;
  * the trial is assigned only when exactly **one** track has the highest number of matched keywords; ties are
    reported as ``ambiguous`` and left unassigned — the crosswalk never force-fits;
  * the matched keyword is returned as evidence, so every assignment is explainable.
"""
from __future__ import annotations

import re
from typing import Iterable, Mapping, Sequence

MIN_KEYWORD_CHARS = 5
TOKEN = re.compile(r"[^A-Z0-9]+")


def normalise(text: str | None) -> str:
    """Upper-case and collapse non-alphanumeric characters to single spaces."""
    if not text:
        return ""
    return " " + TOKEN.sub(" ", text.upper()).strip() + " "


def load_keywords(rows: Iterable[Sequence[str]]) -> dict[str, list[str]]:
    """rows = (track_id, keywords_json). Returns track -> usable keyword phrases (upper case, long enough)."""
    import json

    keywords: dict[str, list[str]] = {}
    for track_id, raw in rows:
        try:
            parsed = json.loads(raw) if raw else []
        except (TypeError, ValueError):
            parsed = []
        usable = []
        for keyword in parsed or []:
            phrase = normalise(str(keyword)).strip()
            if len(phrase.replace(" ", "")) >= MIN_KEYWORD_CHARS:
                usable.append(phrase)
        if usable:
            keywords[track_id] = usable
    return keywords


def assign_device_track(text: str, keywords: Mapping[str, Sequence[str]]) -> dict:
    """Assign one text to at most one device track, returning the evidence used.

    Result: ``{"track": str|None, "status": "assigned"|"ambiguous"|"no_match", "matched": [..], "scores": {..}}``.
    """
    haystack = normalise(text)
    if not haystack.strip():
        return {"track": None, "status": "no_match", "matched": [], "scores": {}}
    scores: dict[str, int] = {}
    matched: dict[str, list[str]] = {}
    for track_id, phrases in keywords.items():
        hits = [phrase for phrase in phrases if f" {phrase} " in haystack]
        if hits:
            scores[track_id] = len(hits)
            matched[track_id] = hits
    if not scores:
        return {"track": None, "status": "no_match", "matched": [], "scores": {}}
    best = max(scores.values())
    winners = sorted(track for track, score in scores.items() if score == best)
    if len(winners) > 1:
        return {"track": None, "status": "ambiguous", "matched": [], "scores": scores,
                "tied": winners}
    winner = winners[0]
    return {"track": winner, "status": "assigned", "matched": matched[winner], "scores": scores}


def coverage(assignments: Iterable[Mapping]) -> dict:
    """Summarise assignment outcomes, so coverage can never be reported without its denominators."""
    counts = {"assigned": 0, "ambiguous": 0, "no_match": 0}
    for assignment in assignments:
        counts[assignment.get("status", "no_match")] = counts.get(assignment.get("status", "no_match"), 0) + 1
    total = sum(counts.values())
    counts["total"] = total
    counts["assigned_share"] = round(counts["assigned"] / total, 3) if total else None
    return counts
