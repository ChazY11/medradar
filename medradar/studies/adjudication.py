"""Deterministic agent pre-adjudication rubric (ADJUDICATION_AMENDMENT_002.md).

Three checks, first-match rule table, no human truth claimed:

  * ``device_relevance``      — do the track's keyword phrases (or their tokens) appear in the trial text?
  * ``taxonomy_consistency``  — does the packet's product code map to the same track in the store?
  * ``third_source_strength`` — map the cross-check status/distance to NEAR_SUPPORT / DISTANT_SUPPORT / AFTER / ...

A ``RUBRIC_VERSION`` is attached to every output so a later reader can tell which rules produced a label.
"""
from __future__ import annotations

import re
from typing import Iterable, Mapping, Sequence

RUBRIC_VERSION = "agent_rubric_v1"
TIER = "AGENT_PRE_ADJUDICATION"

#: machine labels (the human vocabulary stays untouched)
CONFIRMED = "Confirmed Shift (agent-preliminary)"
ROUTINE = "Routine Iteration (agent-preliminary)"
FALSE_SIGNAL = "False Signal / No Confirmed Shift (agent-preliminary)"
UNCERTAIN = "Uncertain (agent-preliminary)"
NOT_ASSESSABLE = "Not Assessable (agent-preliminary)"

TOKEN = re.compile(r"[^A-Za-z0-9]+")


def normalise(text: str | None) -> str:
    return f" {' '.join(TOKEN.sub(' ', str(text or '').upper()).split())} "


def device_relevance(trial_text: str, track_keywords: Sequence[str]) -> dict:
    """STRONG if a full keyword phrase appears, WEAK if only individual tokens do, NONE otherwise."""
    haystack = normalise(trial_text)
    phrases = [normalise(keyword) for keyword in track_keywords if normalise(keyword).strip()]
    matched_phrases = [phrase.strip() for phrase in phrases if phrase in haystack]
    if matched_phrases:
        return {"score": "STRONG", "matched_theses": matched_phrases[:5]}
    tokens = {token for phrase in phrases for token in phrase.split() if len(token) >= 5}
    matched_tokens = sorted(token for token in tokens if f" {token} " in haystack)
    if matched_tokens:
        return {"score": "WEAK", "matched_tokens": matched_tokens[:5]}
    return {"score": "NONE", "matched_theses": [], "matched_tokens": []}


def taxonomy_consistency(packet_track: str, mapped_track: str | None) -> str:
    """CONSISTENT / INCONSISTENT / UNKNOWN from the store's product-code mapping."""
    if not mapped_track:
        return "UNKNOWN"
    return "CONSISTENT" if mapped_track == packet_track else "INCONSISTENT"


def third_source_strength(third_source: Mapping | None) -> str:
    """Map the Europe PMC cross-check result to a rubric strength."""
    if not third_source:
        return "NOT_CHECKED"
    status = str(third_source.get("status") or "")
    distance = str(third_source.get("distance_class") or "")
    if status == "SUPPORTED_BEFORE":
        return "NEAR_SUPPORT" if distance == "NEAR" else "DISTANT_SUPPORT"
    if status == "AFTER_CLEARANCE":
        return "AFTER"
    if status == "AMBIGUOUS":
        return "AMBIGUOUS"
    if status == "NO_RECORD":
        return "NO_RECORD"
    return "NOT_CHECKED"


def relevance_from_mapping(packet_track: str, mapped_track: str | None) -> dict:
    """Device relevance for a *regulatory* packet: judged from the product code's own track mapping.

    The first rubric application used trial text for these packets, which is the wrong field — regulatory events carry
    no trial conditions, so every candidate was scored NONE and the resulting distribution was an artefact. Recorded as
    S-030 before any distribution was published.
    """
    if not mapped_track:
        return {"score": "UNKNOWN", "reason": "no product code and no checkable mapping"}
    if mapped_track == packet_track:
        return {"score": "STRONG", "reason": f"product code maps to {mapped_track}"}
    return {"score": "MISMATCH", "reason": f"product code maps to {mapped_track}, not {packet_track}"}


def preliminary_label(*, relevance: Mapping, consistency: str, third_source: str,
                      stratum: str | None = None) -> dict:
    """Apply the frozen first-match rule table. Returns the label and the rule that fired."""
    score = relevance.get("score")
    if score == "STRONG" and consistency == "CONSISTENT" and third_source == "NEAR_SUPPORT":
        return {"label": CONFIRMED, "rule": "strong+consistent+near third source"}
    if score == "STRONG" and consistency == "INCONSISTENT":
        return {"label": FALSE_SIGNAL, "rule": "strong relevance but taxonomy mismatch"}
    if score == "MISMATCH":
        return {"label": FALSE_SIGNAL, "rule": "taxonomy mapping points at a different track"}
    if score == "NONE":
        return {"label": FALSE_SIGNAL, "rule": "no device-relevant keyword in the record"}
    if score == "STRONG" and (stratum or "").lower() == "routine":
        return {"label": ROUTINE, "rule": "strong relevance in the routine stratum"}
    if score == "STRONG" and consistency == "CONSISTENT":
        return {"label": UNCERTAIN, "rule": "strong relevance, consistent taxonomy, no near third source"}
    if score == "WEAK":
        return {"label": UNCERTAIN, "rule": "only single tokens matched"}
    if consistency == "UNKNOWN" and score == "STRONG":
        return {"label": UNCERTAIN, "rule": "strong relevance but no checkable mapping"}
    return {"label": NOT_ASSESSABLE, "rule": "no rule matched"}


def summarise(rows: Iterable[Mapping]) -> dict:
    """Count labels and rules; accepts either the packet rows produced by b096 or bare {label, rule} dicts."""
    counts: dict[str, int] = {}
    rules: dict[str, int] = {}
    for row in rows:
        label = row.get("agent_preliminary_label", row.get("label"))
        rule = row.get("rule_fired", row.get("rule"))
        if label is not None:
            counts[label] = counts.get(label, 0) + 1
        if rule is not None:
            rules[rule] = rules.get(rule, 0) + 1
    return {"counts": counts, "rules": rules, "total": sum(counts.values())}


def relevance_from_mapping(packet_track: str, mapped_track: str | None) -> dict:
    """Device relevance for a *regulatory* packet: judged from the product code's own track mapping.

    The first rubric application used trial text for these packets, which is the wrong field — regulatory events carry
    no trial conditions, so every candidate was scored NONE and the distribution was an artefact. Recorded as S-030.
    """
    if not mapped_track:
        return {"score": "UNKNOWN", "reason": "no product code and no checkable mapping"}
    if mapped_track == packet_track:
        return {"score": "STRONG", "reason": f"product code maps to {mapped_track}"}
    return {"score": "MISMATCH", "reason": f"product code maps to {mapped_track}, not {packet_track}"}
