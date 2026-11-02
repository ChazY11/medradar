"""Company technology profiles: the Understand layer, as pure computation.

A profile answers *what does this company's public evidence support about its technology position,
and what would change the answer* — it is not a dashboard and not a score. It has exactly seven
required fields, and one of them must always be **contradictory evidence**: the observations that
count against the profile's own reading. A profile that lacks it is rejected by
:func:`validate_profile` rather than rendered.

The module is deliberately pure: it takes plain event lists and returns plain dicts. Database
access lives in the experiment scripts, so the logic is fully unit-testable and reproducible.

Seven fields (recorded in research/DECISIONS.md D-032):

1. ``identity``               company, resolved entities, as-of date, coverage window
2. ``technology_footprint``   tracks with counts, first/last dates and shares
3. ``momentum``               recent vs prior activity rate, with direction and evidence
4. ``concentration``          top-track share and HHI over tracks
5. ``independent_corroboration`` per-track trial support; explicit where absent
6. ``contradictory_evidence`` checks run and observations that cut against the reading
7. ``limits_and_provenance``  what would change the conclusion, sources, coverage caveats

Every statement is generated from the numbers in the same structure, so the prose cannot drift from
the evidence.

    python -m medradar.intelligence.profile --help
"""
from __future__ import annotations

import argparse
import json
import math

from medradar.intelligence.promotion import CONFIRMATION_QUARTERS, decide_promotion
from collections import Counter, defaultdict
from typing import Any, Iterable, Mapping, Sequence

SCHEMA_VERSION = "profile_v1"

SEVEN_FIELDS: tuple[str, ...] = (
    "identity",
    "technology_footprint",
    "momentum",
    "concentration",
    "independent_corroboration",
    "contradictory_evidence",
    "limits_and_provenance",
)

MATERIAL_MONTHS = 24          # momentum compares the last 24 months with the 24 before them
CHURN_LOOKBACK_MONTHS = 18    # share of events on codes first seen this recently
SPARSE_MONTH_FRACTION = 0.5   # a company silent in more than half the window is flagged
DECLINE_RATIO = 0.5           # a track below half its prior rate is flagged as declining
MIN_TRACK_EVENTS = 2          # one event is an anecdote, not a footprint
MOMENTUM_ALPHA = 0.05         # significance level for the momentum test
MOMENTUM_POWER = 0.80         # target power for the minimum detectable ratio
Z_ALPHA = 1.959963985         # two-sided 5 %
Z_POWER = 0.841621234         # 80 % power

# deployment detection, fixed by B-039 (DECISIONS D-044/D-045): the layer runs quarterly, the detector
# is the rolling z-score, and the threshold is the one that achieved a 2 % false-alarm budget in the
# controlled-truth sweep. These values are measurements, not preferences, and must never be re-tuned
# here; if the resolution changes, the detector must be re-measured (at monthly it ranks last).
DEPLOYMENT_RESOLUTION_MONTHS = 3
DEPLOYMENT_MEMORY_MONTHS = 12
DEPLOYMENT_BASELINE_MONTHS = 24
DEPLOYMENT_Z_THRESHOLD = 3.5
DEPLOYMENT_FALSE_ALARM_RATE = 0.0179
DEPLOYMENT_SENSITIVITY = 0.147
ALERT_RECENCY_QUARTERS = 8    # only alerts in the last two years are reported as live


# --------------------------------------------------------------------- helpers
def _normal_cdf(value: float) -> float:
    """Standard normal CDF via the error function (stdlib only)."""
    return 0.5 * (1.0 + math.erf(value / math.sqrt(2.0)))


def _binom_two_sided_p(successes: int, trials: int, p_null: float) -> float:
    """Exact two-sided binomial p-value (sum of outcomes no more likely than observed)."""
    if trials <= 0:
        return 1.0
    p_null = min(max(p_null, 1e-12), 1 - 1e-12)
    probabilities = [math.comb(trials, k) * (p_null ** k) * ((1 - p_null) ** (trials - k))
                     for k in range(trials + 1)]
    observed = probabilities[successes]
    tolerance = observed * (1 + 1e-9)
    return min(1.0, sum(prob for prob in probabilities if prob <= tolerance))


def _minimum_detectable_ratio(n_prior: int, n_recent: int) -> float | None:
    """Smallest rate ratio detectable at the configured alpha and power, given these counts.

    Uses the log-scale standard error sqrt(1/n_prior + 1/n_recent); returned as a ratio in
    (1, +inf). ``None`` when either count is zero, because the ratio is then unbounded.
    """
    if n_prior <= 0 or n_recent <= 0:
        return None
    standard_error = math.sqrt(1.0 / n_prior + 1.0 / n_recent)
    return math.exp((Z_ALPHA + Z_POWER) * standard_error)
def _month_labels(start: str, end: str) -> list[str]:
    """Inclusive list of ``YYYY-MM`` labels from ``start`` to ``end``."""
    start_year, start_month = (int(part) for part in start.split("-"))
    end_year, end_month = (int(part) for part in end.split("-"))
    labels = []
    year, month = start_year, start_month
    while (year, month) <= (end_year, end_month):
        labels.append(f"{year:04d}-{month:02d}")
        month += 1
        if month > 12:
            year, month = year + 1, 1
    return labels


def _count_by_track(events: Iterable[Mapping[str, Any]]) -> dict[str, list[str]]:
    by_track: dict[str, list[str]] = defaultdict(list)
    for event in events:
        track = str(event.get("track") or "")
        date = str(event.get("date") or "")
        if track and len(date) >= 7:
            by_track[track].append(date[:7])
    for months in by_track.values():
        months.sort()
    return dict(by_track)


def _rate(months: Sequence[str], labels: Sequence[str]) -> tuple[int, int, float | None]:
    allowed = set(labels)
    count = sum(1 for month in months if month in allowed)
    if not labels:
        return count, 0, None
    return count, len(labels), count / len(labels)


def _quarter_label(quarter_index: int) -> str:
    year, quarter = divmod(quarter_index, 4)
    return f"{year:04d}-Q{quarter + 1}"


def _quarter_index(date: str) -> int | None:
    """Calendar quarter index from an ISO date; None if the date cannot be parsed."""
    text = str(date or "")[:10]
    if len(text) < 7 or text[4] != "-":
        return None
    try:
        year = int(text[:4])
        month = int(text[5:7])
    except ValueError:
        return None
    if not 1 <= month <= 12:
        return None
    return year * 4 + (month - 1) // 3


def deployment_alerts(events: Sequence[Mapping[str, Any]], *,
                      resolution_months: int = DEPLOYMENT_RESOLUTION_MONTHS,
                      memory_months: int = DEPLOYMENT_MEMORY_MONTHS,
                      baseline_months: int = DEPLOYMENT_BASELINE_MONTHS,
                      threshold: float = DEPLOYMENT_Z_THRESHOLD) -> dict[str, Any]:
    """Calibrated change alerts at the deployment resolution (quarterly rolling z-score).

    The detector, its threshold and its resolution are the ones measured in the controlled-truth sweep
    (DECISIONS D-044/D-045); this function applies them, it does not choose them. A track is flagged in
    a quarter when the count exceeds its own baseline mean by at least ``threshold`` Poisson standard
    deviations, with the baseline taken from the preceding ``baseline_months`` of history.
    """
    if resolution_months != DEPLOYMENT_RESOLUTION_MONTHS:
        raise ValueError("the deployment resolution is fixed by D-045; re-measure before changing it")
    memory_quarters = max(1, memory_months // resolution_months)
    baseline_quarters = max(2, baseline_months // resolution_months)

    per_track: dict[str, dict[int, int]] = {}
    for event in events:
        track = str(event.get("track") or "")
        quarter = _quarter_index(str(event.get("date") or ""))
        if not track or quarter is None:
            continue
        per_track.setdefault(track, {})
        per_track[track][quarter] = per_track[track].get(quarter, 0) + 1
    if not per_track:
        return {"resolution_months": resolution_months, "detector": "rolling_zscore",
                "threshold": threshold, "memory_months": memory_months,
                "false_alarm_rate": DEPLOYMENT_FALSE_ALARM_RATE,
                "sensitivity": DEPLOYMENT_SENSITIVITY,
                "flagged": [], "quarters_examined": 0,
                "statement": "no quarterly history to examine"}

    all_quarters = sorted({quarter for counts in per_track.values() for quarter in counts})
    latest = all_quarters[-1]
    first_examined = latest - ALERT_RECENCY_QUARTERS + 1
    flagged: list[dict[str, Any]] = []
    examined = 0
    for track, counts in sorted(per_track.items()):
        for quarter in range(max(first_examined, all_quarters[0] + baseline_quarters),
                             latest + 1):
            baseline_values = [counts.get(previous, 0)
                               for previous in range(quarter - baseline_quarters, quarter)]
            baseline_mean = sum(baseline_values) / len(baseline_values)
            if baseline_mean <= 0:
                continue
            examined += 1
            count = counts.get(quarter, 0)
            zscore = (count - baseline_mean) / math.sqrt(baseline_mean)
            if zscore >= threshold:
                alert = {"track": track, "quarter": _quarter_label(quarter),
                         "events": count, "baseline_mean": round(baseline_mean, 2),
                         "z": round(zscore, 2),
                         "memory_quarters": memory_quarters,
                         "detector": "rolling_zscore",
                         "resolution_months": resolution_months,
                         "threshold": threshold,
                         "false_alarm_rate": DEPLOYMENT_FALSE_ALARM_RATE}
                # the confirmed promotion rule (D-043, replicated D-048) applied to the two
                # quarters AFTER the alert; a human sign-off is still required and cannot be
                # simulated by data
                following = [counts.get(quarter + offset, 0)
                             for offset in range(1, CONFIRMATION_QUARTERS + 1)
                             if quarter + offset <= latest]
                alert["promotion"] = decide_promotion(alert, following)
                flagged.append(alert)
    flagged.sort(key=lambda item: (-item["z"], item["track"]))
    tracks = sorted({item["track"] for item in flagged})
    return {
        "resolution_months": resolution_months,
        "detector": "rolling_zscore",
        "threshold": threshold,
        "memory_months": memory_months,
        "baseline_months": baseline_months,
        "false_alarm_rate": DEPLOYMENT_FALSE_ALARM_RATE,
        "sensitivity": DEPLOYMENT_SENSITIVITY,
        "flagged": flagged,
        "flagged_tracks": tracks,
        "quarters_examined": examined,
        "recency_quarters": ALERT_RECENCY_QUARTERS,
        "statement": (f"{len(flagged)} calibrated alert(s) in the last "
                      f"{ALERT_RECENCY_QUARTERS} quarters across {len(tracks)} track(s)"
                      f" ({examined} track-quarters examined at {resolution_months}-month "
                      f"resolution, threshold z>={threshold}, measured FAR "
                      f"{DEPLOYMENT_FALSE_ALARM_RATE:.3f})"
                      if flagged else
                      f"no calibrated alert in the last {ALERT_RECENCY_QUARTERS} quarters "
                      f"({examined} track-quarters examined at {resolution_months}-month "
                      f"resolution, threshold z>={threshold}, measured FAR "
                      f"{DEPLOYMENT_FALSE_ALARM_RATE:.3f})"),
    }


def _momentum(events: Sequence[Mapping[str, Any]], labels: Sequence[str]) -> dict[str, Any]:
    """Compare the most recent MATERIAL_MONTHS with the equal window before it, with a test.

    A rate ratio alone is not a finding: 90 versus 66 events can be noise. The comparison is a
    two-sided exact binomial test of the recent count conditional on the total, which is the
    Poisson rate-ratio test under a constant-rate null. When the test does not reject, the field
    reports the **minimum detectable ratio** at 80 % power rather than calling the change real or
    absent.
    """
    if len(labels) < 2 * MATERIAL_MONTHS:
        return {"status": "insufficient_window", "recent": 0, "prior": 0, "ratio": None,
                "detected": False, "p_value": None, "mde_ratio": None,
                "statement": "window shorter than two comparison periods; momentum not estimated"}
    recent_labels = labels[-MATERIAL_MONTHS:]
    prior_labels = labels[-2 * MATERIAL_MONTHS:-MATERIAL_MONTHS]
    months = [str(event.get("date") or "")[:7] for event in events]
    recent, _, recent_rate = _rate(months, recent_labels)
    prior, _, prior_rate = _rate(months, prior_labels)
    total = recent + prior
    ratio = (recent_rate / prior_rate) if prior_rate else None
    mde = _minimum_detectable_ratio(prior, recent)

    if total == 0:
        return {"status": "estimated", "recent": 0, "prior": 0, "ratio": None,
                "recent_rate": 0.0, "prior_rate": 0.0, "detected": False, "p_value": 1.0,
                "mde_ratio": None, "alpha": MOMENTUM_ALPHA,
                "statement": (f"no material events in either {MATERIAL_MONTHS}-month period; "
                              "momentum not estimable")}

    p_value = _binom_two_sided_p(recent, total, 0.5)
    detected = p_value < MOMENTUM_ALPHA and ratio is not None and ratio != 1.0
    if detected:
        direction = "increasing" if (ratio or 0) > 1 else "decreasing"
        statement = (f"activity {direction}: {recent} events in the last {MATERIAL_MONTHS} months "
                     f"vs {prior} before (ratio {ratio:.2f}), exact two-sided p={p_value:.3f}")
    else:
        direction = "no_detectable_change"
        mde_text = f"{mde:.2f}x" if mde else "not estimable"
        statement = (f"no detectable change: {recent} events in the last {MATERIAL_MONTHS} months "
                     f"vs {prior} before (ratio {'n/a' if ratio is None else f'{ratio:.2f}'}), "
                     f"p={p_value:.3f}; minimum detectable ratio at {int(MOMENTUM_POWER * 100)}% "
                     f"power is {mde_text}")
    return {"status": "estimated", "recent": recent, "prior": prior,
            "recent_rate": recent_rate, "prior_rate": prior_rate, "ratio": ratio,
            "detected": detected, "p_value": p_value, "alpha": MOMENTUM_ALPHA,
            "mde_ratio": mde, "direction": direction, "statement": statement}


def _concentration(track_counts: Mapping[str, int]) -> dict[str, Any]:
    total = sum(track_counts.values())
    if not total:
        return {"status": "no_events", "top_share": None, "hhi": None,
                "statement": "no material events; concentration not defined"}
    shares = sorted((count / total for count in track_counts.values()), reverse=True)
    hhi = sum(share ** 2 for share in shares)
    top_share = shares[0]
    if hhi >= 0.5:
        label = "highly concentrated"
    elif hhi >= 0.25:
        label = "moderately concentrated"
    else:
        label = "diversified"
    top_track = max(track_counts, key=lambda track: track_counts[track])
    return {"status": "estimated", "top_track": top_track, "top_share": top_share,
            "tracks": len(shares), "hhi": hhi, "label": label,
            "statement": (f"{label}: top track {top_track} holds {top_share:.0%} of "
                          f"{total} material events across {len(shares)} tracks (HHI {hhi:.2f})")}


# ----------------------------------------------------------------------- fields
def field_identity(*, company_key: str, display_name: str, aliases: Sequence[str],
                   entity_keys: Sequence[str], as_of: str,
                   window: tuple[str, str], sources: Sequence[str]) -> dict[str, Any]:
    return {
        "field": "identity",
        "company_key": company_key,
        "display_name": display_name,
        "aliases_resolved": sorted(set(aliases)),
        "entity_count": len(set(entity_keys)),
        "entity_keys_sample": sorted(set(entity_keys))[:8],
        "as_of": as_of,
        "coverage_window": {"start": window[0], "end": window[1],
                            "months": len(_month_labels(*window))},
        "sources": list(sources),
        "statement": (f"{display_name}: {len(set(entity_keys))} resolved legal entities from "
                      f"{len(set(aliases))} aliases, observed {window[0]} to {window[1]}"),
    }


def field_footprint(events: Sequence[Mapping[str, Any]], labels: Sequence[str]) -> dict[str, Any]:
    by_track = _count_by_track(events)
    total = sum(len(months) for months in by_track.values())
    rows = []
    for track, months in sorted(by_track.items(), key=lambda item: -len(item[1])):
        rows.append({
            "track": track,
            "events": len(months),
            "first": months[0],
            "last": months[-1],
            "share": (len(months) / total) if total else None,
            "sufficient_evidence": len(months) >= MIN_TRACK_EVENTS,
        })
    return {"field": "technology_footprint", "total_events": total,
            "tracks": len(rows), "rows": rows,
            "statement": (f"{total} material events across {len(rows)} technology tracks "
                          f"({sum(1 for row in rows if not row['sufficient_evidence'])} tracks "
                          f"rest on a single event)")}


def field_corroboration(events: Sequence[Mapping[str, Any]],
                        trials: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    reg_tracks = set(_count_by_track(events))
    trial_tracks = _count_by_track(trials)
    supported = sorted(track for track in reg_tracks if trial_tracks.get(track))
    unsupported = sorted(track for track in reg_tracks if not trial_tracks.get(track))
    return {
        "field": "independent_corroboration",
        "trial_events": sum(len(months) for months in trial_tracks.values()),
        "tracks_with_trial_support": supported,
        "tracks_without_trial_support": unsupported,
        "statement": (f"{len(supported)} of {len(reg_tracks)} technology tracks have independent "
                      f"device-trial support; {len(unsupported)} do not"
                      if reg_tracks else "no regulatory tracks to corroborate"),
    }


def field_contradictions(events: Sequence[Mapping[str, Any]], labels: Sequence[str], *,
                         code_first_seen: Mapping[str, str] | None = None,
                         as_of: str | None = None) -> dict[str, Any]:
    """Checks that must be run, and the observations that cut against the reading."""
    checks = [
        "activity_decline_by_track",
        "single_event_tracks",
        "sparse_months",
        "taxonomy_churn_exposure",
    ]
    found: list[dict[str, Any]] = []
    months = [str(event.get("date") or "")[:7] for event in events]
    occupied = len(set(months))
    silent_fraction = 1 - (occupied / len(labels)) if labels else 1.0
    if silent_fraction > SPARSE_MONTH_FRACTION:
        found.append({
            "check": "sparse_months",
            "observation": (f"the company has material events in {occupied} of {len(labels)} "
                            f"months ({silent_fraction:.0%} silent)"),
            "implication": "monthly series are mostly zeros; rate estimates are unstable",
        })
    by_track = _count_by_track(events)
    singles = sorted(track for track, months_list in by_track.items()
                     if len(months_list) < MIN_TRACK_EVENTS)
    if singles:
        found.append({
            "check": "single_event_tracks",
            "observation": f"{len(singles)} track(s) rest on a single event: {', '.join(singles[:5])}",
            "implication": "a single filing is an anecdote; treat these tracks as unconfirmed",
        })
    if len(labels) >= 2 * MATERIAL_MONTHS:
        recent = set(labels[-MATERIAL_MONTHS:])
        prior = set(labels[-2 * MATERIAL_MONTHS:-MATERIAL_MONTHS])
        for track, months_list in by_track.items():
            recent_count = sum(1 for month in months_list if month in recent)
            prior_count = sum(1 for month in months_list if month in prior)
            if prior_count >= 3 and recent_count <= DECLINE_RATIO * prior_count:
                found.append({
                    "check": "activity_decline_by_track",
                    "observation": (f"{track}: {recent_count} events in the last "
                                    f"{MATERIAL_MONTHS} months vs {prior_count} before"),
                    "implication": "this track is retreating, which cuts against a growth reading",
                })
    if code_first_seen and as_of:
        recent_labels = set(labels[-CHURN_LOOKBACK_MONTHS:])
        on_recent_codes = sum(1 for event in events
                              if code_first_seen.get(str(event.get("code") or ""), "") in recent_labels)
        if events and on_recent_codes / len(events) > 0.2:
            found.append({
                "check": "taxonomy_churn_exposure",
                "observation": (f"{on_recent_codes} of {len(events)} events "
                                f"({on_recent_codes / len(events):.0%}) sit on product codes first "
                                f"seen in the classifier within {CHURN_LOOKBACK_MONTHS} months"),
                "implication": ("part of any recent 'new area' reading may be classification "
                                "churn rather than new activity"),
            })
    return {"field": "contradictory_evidence", "checks": checks, "found": found,
            "statement": (f"{len(found)} contradictory observation(s) out of {len(checks)} checks"
                          if found else
                          f"no contradictory observation found across the {len(checks)} checks run")}


def field_limits(*, window: tuple[str, str], sources: Sequence[str],
                 hiring_status: str | None = None,
                 as_of: str) -> dict[str, Any]:
    what_would_change = [
        "a sustained activity change beyond the detector's measured minimum detectable effect",
        "independent evidence (trials, hiring, publications) that contradicts the track reading",
        "taxonomy changes that reclassify existing activity into new product codes",
        "entity-resolution changes that move filings between legal entities",
    ]
    return {
        "field": "limits_and_provenance",
        "as_of": as_of,
        "sources": list(sources),
        "window": {"start": window[0], "end": window[1]},
        "hiring_status": hiring_status,
        "what_would_change_the_conclusion": what_would_change,
        "known_limits": [
            "a detection is a statement about public regulatory activity rate, never about intent, "
            "capability or internal R&D",
            "the lane holds ~0.2 events per cell-month, so monthly per-track rates are noisy",
            "product-code taxonomy is not versioned by effective date",
            "the final month of the window is partially observed",
            "a spike can be separated from a sustained change, but a ramp cannot be separated from a "
            "level shift at this counting rate: no confirmation window between 1 and 6 months recovered "
            "ramps (best recall 0.229, D-051)",
            "the alert detector is validated at quarterly resolution only; at monthly resolution the "
            "same detector ranks last (D-045)",
        ],
        "statement": ("conclusion would change under: " + "; ".join(what_would_change[:2])),
    }


def build_profile(*, company_key: str, display_name: str, aliases: Sequence[str],
                  entity_keys: Sequence[str], as_of: str, window: tuple[str, str],
                  sources: Sequence[str], regulatory_events: Sequence[Mapping[str, Any]],
                  trial_events: Sequence[Mapping[str, Any]] = (),
                  code_first_seen: Mapping[str, str] | None = None,
                  hiring_status: str | None = None) -> dict[str, Any]:
    """Assemble the seven fields. Every statement is derived from the same numbers."""
    labels = _month_labels(*window)
    profile = {
        "schema": SCHEMA_VERSION,
        "fields": SEVEN_FIELDS,
        "identity": field_identity(company_key=company_key, display_name=display_name,
                                   aliases=aliases, entity_keys=entity_keys, as_of=as_of,
                                   window=window, sources=sources),
        "technology_footprint": field_footprint(regulatory_events, labels),
        "momentum": {**_momentum(regulatory_events, labels),
                     "deployment_alerts": deployment_alerts(regulatory_events)},
        "concentration": _concentration(
            {row["track"]: row["events"]
             for row in field_footprint(regulatory_events, labels)["rows"]}),
        "independent_corroboration": field_corroboration(regulatory_events, trial_events),
        "contradictory_evidence": field_contradictions(
            regulatory_events, labels, code_first_seen=code_first_seen, as_of=as_of),
        "limits_and_provenance": field_limits(window=window, sources=sources,
                                             hiring_status=hiring_status, as_of=as_of),
    }
    problems = validate_profile(profile)
    if problems:
        raise ValueError("invalid profile: " + "; ".join(problems))
    return profile


def validate_profile(profile: Mapping[str, Any]) -> list[str]:
    """Return the list of structural problems; empty means the profile may be rendered."""
    problems: list[str] = []
    for field in SEVEN_FIELDS:
        if field not in profile:
            problems.append(f"missing field: {field}")
    contradictions = profile.get("contradictory_evidence")
    if isinstance(contradictions, Mapping):
        if not contradictions.get("checks"):
            problems.append("contradictory_evidence must list the checks that were run")
        if "found" not in contradictions:
            problems.append("contradictory_evidence must report its findings (possibly empty)")
    for name in ("identity", "technology_footprint", "momentum", "concentration",
                 "independent_corroboration", "limits_and_provenance"):
        block = profile.get(name)
        if isinstance(block, Mapping) and not block.get("statement"):
            problems.append(f"{name} has no statement")
    return problems


def render_markdown(profile: Mapping[str, Any]) -> str:
    """Render a profile as Markdown. Raises if the profile is structurally invalid."""
    problems = validate_profile(profile)
    if problems:
        raise ValueError("refusing to render an invalid profile: " + "; ".join(problems))
    identity = profile["identity"]
    footprint = profile["technology_footprint"]
    momentum = profile["momentum"]
    concentration = profile["concentration"]
    corroboration = profile["independent_corroboration"]
    contradictions = profile["contradictory_evidence"]
    limits = profile["limits_and_provenance"]

    lines = [f"# {identity['display_name']} — technology profile",
             "",
             f"*As of {identity['as_of']}. Evidence window {identity['coverage_window']['start']} "
             f"to {identity['coverage_window']['end']} "
             f"({identity['coverage_window']['months']} months). "
             f"Schema {profile['schema']}.*",
             "",
             "> A profile states what public evidence supports and what would change the answer. "
             "It is not a score, and it is only as good as the coverage below.",
             "",
             "## 1. Identity",
             "",
             f"- {identity['statement']}",
             f"- Sources: {', '.join(identity['sources'])}",
             ""]
    lines += ["## 2. Technology footprint", "",
              f"- {footprint['statement']}", "",
              "| track | events | first | last | share | evidence |",
              "|---|---:|---|---|---:|---|"]
    for row in footprint["rows"]:
        evidence = "sufficient" if row["sufficient_evidence"] else "single event"
        lines.append(f"| {row['track']} | {row['events']} | {row['first']} | {row['last']} | "
                     f"{(row['share'] or 0):.0%} | {evidence} |")
    lines += ["", "## 3. Momentum", "", f"- {momentum['statement']}"]
    if momentum.get("status") == "estimated" and momentum.get("p_value") is not None:
        mde = momentum.get("mde_ratio")
        mde_text = f"{mde:.2f}x" if mde else "not estimable"
        lines.append(
            f"- Test: exact two-sided binomial p={momentum['p_value']:.3f} "
            f"(alpha={momentum.get('alpha')}), minimum detectable ratio at 80 % power "
            f"{mde_text}, detected={momentum.get('detected')}")
    deployment = momentum.get("deployment_alerts")
    if deployment:
        lines.append(f"- Deployment detector: {deployment['detector']} at "
                     f"{deployment['resolution_months']}-month resolution, threshold "
                     f"z>={deployment['threshold']}, {deployment['statement']}")
        for alert in deployment["flagged"][:6]:
            lines.append(f"  - `{alert['track']}` {alert['quarter']}: {alert['events']} events "
                         f"against a baseline of {alert['baseline_mean']} (z={alert['z']})")
            promotion = alert.get("promotion")
            if promotion:
                lines.append(f"    - promotion: **{promotion['verdict']}** — shape "
                             f"{promotion['shape']} ({promotion['shape_reason']}); sign-off required="
                             f"{str(promotion['requires_signoff']).lower()}; "
                             f"promotion marks a change in public filing rate, not in technology")
        lines.append("  - these alerts are calibrated at the measured false-alarm rate "
                     f"{deployment['false_alarm_rate']:.3f} and sensitivity "
                     f"{deployment['sensitivity']:.3f}; they are statements about filing rate, "
                     "not about technology")
    lines += ["", "## 4. Concentration", "", f"- {concentration['statement']}", ""]
    lines += ["## 5. Independent corroboration", "", f"- {corroboration['statement']}"]
    if corroboration["tracks_without_trial_support"]:
        lines.append(f"- Tracks with **no** trial support: "
                     f"{', '.join(corroboration['tracks_without_trial_support'][:8])}")
    lines += ["", "## 6. Contradictory evidence", "",
              f"- {contradictions['statement']}"]
    for item in contradictions["found"]:
        lines.append(f"- `{item['check']}`: {item['observation']} — {item['implication']}")
    lines += ["", "## 7. Limits and provenance", ""]
    lines.append(f"- As of {limits['as_of']}; window {limits['window']['start']} to "
                 f"{limits['window']['end']}")
    if limits.get("hiring_status"):
        lines.append(f"- Hiring evidence: {limits['hiring_status']}")
    lines.append("- What would change the conclusion:")
    for item in limits["what_would_change_the_conclusion"]:
        lines.append(f"  - {item}")
    lines.append("- Known limits:")
    for item in limits["known_limits"]:
        lines.append(f"  - {item}")
    lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Render a company profile from a profile JSON.")
    parser.add_argument("--profile", required=True,
                        help="path to a profile JSON produced by build_profiles.py")
    parser.add_argument("--out", default=None, help="write Markdown here instead of stdout")
    args = parser.parse_args(argv)
    with open(args.profile, encoding="utf-8") as handle:
        profile = json.load(handle)
    markdown = render_markdown(profile)
    if args.out:
        with open(args.out, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(markdown)
        print(f"wrote {args.out}")
    else:
        print(markdown)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
