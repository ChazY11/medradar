"""Human adjudication vocabulary, validation and scoring (used only after a person fills the worksheet).

The five human labels are fixed by LABELING_PROTOCOL.md. This module validates a filled worksheet, so a reviewer cannot
accidentally submit an incomplete or out-of-vocabulary label, and computes the agreement between the human labels and the
agent's preliminary rubric — reported as a diagnostic, never used to tune the rubric.
"""
from __future__ import annotations

from typing import Iterable, Mapping, Sequence

CONFIRMED = "Confirmed Shift"
ROUTINE = "Routine Iteration"
FALSE_SIGNAL = "False Signal / No Confirmed Shift"
UNCERTAIN = "Uncertain"
INSUFFICIENT = "Insufficient Observation"
ALLOWED_LABELS = (CONFIRMED, ROUTINE, FALSE_SIGNAL, UNCERTAIN, INSUFFICIENT)

#: human labels must be entered exactly; these aliases exist only to be rejected with a helpful message
ALIASES = {
    "confirmed": CONFIRMED,
    "shift": CONFIRMED,
    "routine": ROUTINE,
    "iteration": ROUTINE,
    "false": FALSE_SIGNAL,
    "false signal": FALSE_SIGNAL,
    "no confirmed shift": FALSE_SIGNAL,
    "uncertain": UNCERTAIN,
    "insufficient": INSUFFICIENT,
    "insufficient observation": INSUFFICIENT,
}

#: labels that require the independent-confirmation field to be filled
REQUIRES_INDEPENDENCE = (CONFIRMED,)


def normalise_label(value: str | None) -> str:
    """Return the canonical label, or the cleaned input when it is not in the vocabulary."""
    text = " ".join(str(value or "").split())
    if text in ALLOWED_LABELS:
        return text
    return ALIASES.get(text.lower(), text)


def validate_row(row: Mapping[str, str]) -> list[str]:
    """Return the list of problems with one worksheet row (empty list means valid)."""
    problems: list[str] = []
    packet = row.get("packet_id") or ""
    if not packet:
        problems.append("row has no packet_id")
    label = normalise_label(row.get("human_label"))
    if not label:
        problems.append(f"{packet}: human_label is empty")
    elif label not in ALLOWED_LABELS:
        problems.append(f"{packet}: human_label {row.get('human_label')!r} is not one of the five labels")
    if not str(row.get("reviewer") or "").strip():
        problems.append(f"{packet}: reviewer name is required (a label without an author is not a label)")
    if not str(row.get("human_reason") or "").strip():
        problems.append(f"{packet}: human_reason is required (what evidence decided it)")
    if label in REQUIRES_INDEPENDENCE and not str(row.get("independent_confirmation") or "").strip():
        problems.append(f"{packet}: a Confirmed Shift needs an independent confirmation recorded")
    if label == INSUFFICIENT and not str(row.get("human_reason") or "").strip():
        problems.append(f"{packet}: Insufficient Observation needs a reason too")
    return problems


def validate_rows(rows: Iterable[Mapping[str, str]]) -> dict:
    problems: list[str] = []
    packets = []
    for row in rows:
        problems.extend(validate_row(row))
        packets.append(str(row.get("packet_id") or ""))
    duplicates = sorted({packet for packet in packets if packets.count(packet) > 1})
    if duplicates:
        problems.append(f"duplicate packet ids: {duplicates[:5]}")
    return {"problems": problems, "rows": len(packets), "valid": not problems}


def summarise_review(rows: Sequence[Mapping[str, str]]) -> dict:
    counts: dict[str, int] = {}
    for row in rows:
        label = normalise_label(row.get("human_label"))
        counts[label] = counts.get(label, 0) + 1
    reviewers = sorted({str(row.get("reviewer") or "").strip() for row in rows if row.get("reviewer")})
    return {"total": len(rows), "counts": counts, "reviewers": reviewers}


def agreement(rows: Sequence[Mapping[str, str]], *, agent_field: str = "agent_preliminary_label") -> dict:
    """Agreement between human labels and the agent's preliminary rubric, as a descriptive diagnostic."""
    compared = 0
    same = 0
    for row in rows:
        human = normalise_label(row.get("human_label"))
        agent = str(row.get(agent_field) or "")
        if not human or not agent:
            continue
        compared += 1
        if agent.startswith(human):
            same += 1
    return {"compared": compared, "same": same,
            "agreement": round(same / compared, 3) if compared else None,
            "note": ("descriptive only: agreement with an agent rubric says nothing about correctness, and the rubric "
                     "must not be tuned on these numbers")}
