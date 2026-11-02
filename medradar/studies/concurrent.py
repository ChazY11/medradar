"""Concurrent multi-source change detection: pure logic (study O1).

Everything here is testable without a database:

  * ``sustained_onsets`` — the amended positive definition from PHASE1B_PROTOCOL.md: a firm-track quarter that opens
    an episode with >= 2 events within 4 quarters after >= 12 months of silence;
  * ``rolling_zscore`` — the validated quarterly detector applied to one stream;
  * ``calibrate_threshold`` — pick the threshold that hits a declared false-alert budget on a calibration window;
  * ``evaluate`` — recall / false alerts / precision for one model at a threshold, with censoring handled explicitly;
  * ``wilson_interval`` — the interval used for a recall proportion.

A single clearance is never a positive; a positive requires a *sustained* change.
"""
from __future__ import annotations

import math
from collections import defaultdict
from typing import Iterable, Mapping, Sequence

MIN_SILENCE_QUARTERS = 4        # 12 months of silence before an onset
EPISODE_QUARTERS = 4            # the episode window that defines "sustained"
MIN_EVENTS_IN_EPISODE = 2       # sustained = at least two events in the episode
MIN_BASELINE_QUARTERS = 8       # the detector's baseline, as in the deployed configuration
DETECTION_SLACK_QUARTERS = 1    # an alert at q or q+1 counts as concurrent detection of an onset at q


def quarter_index(label: str) -> int:
    year, quarter = label.split("-Q")
    return int(year) * 4 + int(quarter) - 1


def quarter_label(index: int) -> str:
    year, remainder = divmod(index, 4)
    return f"{year:04d}-Q{remainder + 1}"


def sustained_onsets(events_by_quarter: Mapping[str, int], *,
                     min_silence_quarters: int = MIN_SILENCE_QUARTERS,
                     episode_quarters: int = EPISODE_QUARTERS,
                     min_events: int = MIN_EVENTS_IN_EPISODE) -> dict[str, object]:
    """Return onset quarters, censored quarters and the list of episodes.

    A quarter q is an onset when the track was silent for `min_silence_quarters` before q and at least `min_events`
    occur in q..q+episode_quarters-1. Quarters whose episode window is not fully observed are *censored*, not negative.
    """
    quarters = sorted(events_by_quarter)
    if not quarters:
        return {"onsets": [], "censored": [], "episodes": []}
    first, last = quarter_index(quarters[0]), quarter_index(quarters[-1])
    onset_labels: list[str] = []
    censored: list[str] = []
    episodes: list[dict] = []
    index = first
    while index <= last:
        label = quarter_label(index)
        window = [quarter_label(index + offset) for offset in range(episode_quarters)]
        complete = all(quarter_index(w) <= last for w in window)
        in_window = sum(events_by_quarter.get(w, 0) for w in window)
        # the silence must be fully observed, otherwise a series that simply starts here would look like an onset
        observed_silence = index - min_silence_quarters >= first
        silent_before = observed_silence and all(
            events_by_quarter.get(quarter_label(index - offset), 0) == 0
            for offset in range(1, min_silence_quarters + 1))
        if not complete:
            if in_window >= 1:
                censored.append(label)
            index += 1
            continue
        # an onset must itself carry activity: an empty quarter cannot open a sustained episode
        if silent_before and events_by_quarter.get(label, 0) >= 1 and in_window >= min_events:
            onset_labels.append(label)
            episode_quarters_list = [w for w in window if events_by_quarter.get(w)]
            episodes.append({"onset": label, "events": in_window, "quarters": episode_quarters_list})
            # skip the whole episode so overlapping windows cannot double-count the same burst
            last_event = max(quarter_index(w) for w in episode_quarters_list)
            index = max(index + 1, last_event + 1)
            continue
        index += 1
    return {"onsets": onset_labels, "censored": censored, "episodes": episodes}


def rolling_zscore(events_by_quarter: Mapping[str, int], *, baseline: int = MIN_BASELINE_QUARTERS
                   ) -> dict[str, float]:
    """Quarterly rolling z-score against the mean of the previous `baseline` quarters (deployed configuration)."""
    labels = sorted(events_by_quarter)
    if not labels:
        return {}
    first, last = quarter_index(labels[0]), quarter_index(labels[-1])
    scores: dict[str, float] = {}
    for index in range(first + baseline, last + 1):
        label = quarter_label(index)
        window = [events_by_quarter.get(quarter_label(index - offset), 0)
                  for offset in range(baseline, 0, -1)]
        mean = sum(window) / baseline
        current = events_by_quarter.get(label, 0)
        if mean <= 0:
            # a zero baseline cannot produce a z-score; record it as a large-but-undefined signal
            scores[label] = float("inf") if current > 0 else 0.0
            continue
        scores[label] = (current - mean) / math.sqrt(mean)
    return scores


def calibrate_threshold(scores: Mapping[str, float], onsets: Iterable[str], *,
                        positives: int, negatives: int, years: float,
                        budget_per_company_year: float = 2.0) -> dict:
    """Choose the smallest threshold whose calibration false-alert rate meets the declared budget.

    Returns ``NOT_EVALUABLE`` when the signal cannot reach the budget at any threshold.
    """
    onset_set = set(onsets)
    candidates = sorted({value for value in scores.values() if math.isfinite(value)}, reverse=True)
    if not candidates:
        return {"status": "NOT_EVALUABLE", "reason": "no finite scores", "threshold": None}
    allowed_false = budget_per_company_year * years
    best = None
    for threshold in candidates:
        fired = {label for label, value in scores.items() if value >= threshold}
        false_alerts = len([label for label in fired if label not in onset_set])
        if false_alerts <= allowed_false and fired:
            best = {"status": "OK", "threshold": threshold, "calibration_false_alerts": false_alerts,
                    "calibration_alerts": len(fired)}
            break
    if best is None:
        return {"status": "NOT_EVALUABLE",
                "reason": (f"even the highest observed threshold ({candidates[0]:.2f}) exceeds the budget of "
                           f"{allowed_false:.1f} false alerts"),
                "threshold": None}
    return best


def evaluate(scores: Mapping[str, float], onsets: Sequence[str], *,
             threshold: float, years: float,
             slack: int = DETECTION_SLACK_QUARTERS,
             negatives: Sequence[str] | None = None) -> dict:
    """Recall at a threshold, allowing the alert to land at q or q+slack, plus false alerts and precision."""
    fired = sorted(label for label, value in scores.items() if value >= threshold)
    onset_indices = {quarter_index(label) for label in onsets}
    hits = 0
    for onset in onsets:
        window = {quarter_index(onset) + offset for offset in range(slack + 1)}
        if any(label in fired for label in
               {quarter_label(index) for index in window}):
            hits += 1
    negative_set = set(negatives if negatives is not None else
                       [label for label in scores if quarter_index(label) not in onset_indices])
    false_alerts = len([label for label in fired if label in negative_set])
    recall = hits / len(onsets) if onsets else None
    precision = (hits / len(fired)) if fired else None
    return {"threshold": threshold, "alerts": len(fired), "hits": hits,
            "recall": recall, "recall_interval": wilson_interval(hits, len(onsets)) if onsets else None,
            "false_alerts": false_alerts,
            "false_alerts_per_company_year": (round(false_alerts / years, 3) if years else None),
            "precision": precision, "positives": len(onsets)}


def wilson_interval(successes: int, total: int, z: float = 1.96) -> list[float]:
    """Wilson score interval for a proportion; returns [low, high] rounded to 3 decimals."""
    if total <= 0:
        return [0.0, 1.0]
    phat = successes / total
    denominator = 1 + z ** 2 / total
    centre = (phat + z ** 2 / (2 * total)) / denominator
    half = z * math.sqrt(phat * (1 - phat) / total + z ** 2 / (4 * total ** 2)) / denominator
    return [round(max(0.0, centre - half), 3), round(min(1.0, centre + half), 3)]


def fuse(stream_a: Mapping[str, float], stream_b: Mapping[str, float]) -> dict[str, float]:
    """Equal-FAR fusion: the maximum of two standardised anomaly scores (not a union of tuned alerts)."""
    labels = set(stream_a) | set(stream_b)
    fused = {}
    for label in labels:
        a = stream_a.get(label, 0.0)
        b = stream_b.get(label, 0.0)
        if math.isinf(a) or math.isinf(b):
            fused[label] = float("inf")
            continue
        fused[label] = max(a, b)
    return fused


def counts_by_quarter(rows: Iterable[Mapping]) -> dict[str, int]:
    """Aggregate dated rows (each with a 'quarter' label) into a quarter -> count mapping."""
    counts: dict[str, int] = defaultdict(int)
    for row in rows:
        label = row.get("quarter")
        if label:
            counts[label] += 1
    return dict(counts)


def split_window(labels: Iterable[str], *, split: str) -> dict[str, list[str]]:
    """Split quarter labels into calibration (< split) and evaluation (>= split)."""
    calibration, evaluation = [], []
    for label in sorted(set(labels)):
        (calibration if label < split else evaluation).append(label)
    return {"calibration": calibration, "evaluation": evaluation}
