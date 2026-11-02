"""Independence and representative selection for the nine-event lead-time description.

Pure logic, testable without artifacts:

  * ``group_by_later`` — collapse pairs so the unit is the distinct later clearance;
  * ``representative`` — the *latest* paired trial (minimum lead), the conservative choice fixed in the protocol;
  * ``describe_leads`` — median, IQR, range, and the share at or above one and two quarters;
  * ``packet`` — a human-review evidence packet for one event, never a label.

Nothing here computes a confidence interval: the frozen protocol forbids one at n = 9 across three firms.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Iterable, Mapping, Sequence

INDEPENDENCE_FLOOR = 10


def group_by_later(pairs: Iterable[Mapping]) -> dict[str, list[Mapping]]:
    """Group candidate pairs by their later clearance id."""
    grouped: dict[str, list[Mapping]] = defaultdict(list)
    for pair in pairs:
        grouped[str(pair.get("later_id"))].append(pair)
    return dict(grouped)


def representative(candidates: Sequence[Mapping]) -> Mapping:
    """The candidate pair with the *smallest* lead (latest trial): cannot inflate the lead time."""
    return min(candidates, key=lambda pair: (float(pair.get("lead_quarters") or 0.0),
                                             str(pair.get("earlier_id"))))


def upper_bound(candidates: Sequence[Mapping]) -> Mapping:
    """The candidate pair with the largest lead: reported only as an upper bound."""
    return max(candidates, key=lambda pair: (float(pair.get("lead_quarters") or 0.0),
                                             str(pair.get("earlier_id"))))


def _quantile(sorted_values: Sequence[float], fraction: float) -> float | None:
    if not sorted_values:
        return None
    index = min(len(sorted_values) - 1, max(0, int(round(fraction * (len(sorted_values) - 1)))))
    return sorted_values[index]


def describe_leads(values: Sequence[float]) -> dict:
    """Descriptive summary of representative leads; no interval, by design."""
    ordered = sorted(float(value) for value in values)
    if not ordered:
        return {"n": 0, "median": None, "iqr": [None, None], "range": [None, None],
                "share_ge_1q": None, "share_ge_2q": None}
    return {
        "n": len(ordered),
        "median": _quantile(ordered, 0.5),
        "iqr": [_quantile(ordered, 0.25), _quantile(ordered, 0.75)],
        "range": [ordered[0], ordered[-1]],
        "share_ge_1q": round(sum(1 for value in ordered if value >= 1.0) / len(ordered), 3),
        "share_ge_2q": round(sum(1 for value in ordered if value >= 2.0) / len(ordered), 3),
    }


def underpowered_statement(n_events: int, floor: int = INDEPENDENCE_FLOOR) -> str:
    """The mandatory wording, generated so it cannot drift from the count."""
    return (f"descriptive only; n = {n_events} independent event(s), below the floor of {floor}, therefore "
            f"underpowered and not a lead-time estimate.")


def packet(*, event_id: str, company: str, track: str, clearance_id: str, clearance_date: str,
           clearance_kind: str, representative_pair: Mapping, candidates: Sequence[Mapping],
           matched_keywords: Iterable[str] = ()) -> dict:
    """One human-review packet: evidence to adjudicate, never a label."""
    return {
        "event_id": event_id,
        "company": company,
        "technology_track": track,
        "later_clearance": {"id": clearance_id, "date": clearance_date, "kind": clearance_kind},
        "representative_trial": {"id": representative_pair.get("earlier_id"),
                                 "date": representative_pair.get("earlier_date"),
                                 "matched_keywords": list(matched_keywords)},
        "lead_quarters": representative_pair.get("lead_quarters"),
        "lead_days": representative_pair.get("lead_days"),
        "candidate_trials": len(candidates),
        "candidate_leads": sorted(float(pair.get("lead_quarters") or 0.0) for pair in candidates),
        "upper_bound_lead_quarters": upper_bound(candidates).get("lead_quarters"),
        "human_review_status": "PENDING_HUMAN_REVIEW",
        "review_questions": [
            "is the trial genuinely device-relevant for this track (not a drug trial matched by keyword accident)?",
            "does the clearance belong to the same firm and track as the trial?",
            "could the lead be an artefact of the post-hoc keyword crosswalk?",
            "does a third source (publication, 8-K) independently place the programme before the clearance?",
        ],
        "final_label": None,
    }
