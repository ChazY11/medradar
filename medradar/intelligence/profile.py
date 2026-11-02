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


# --------------------------------------------------------------------- helpers
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


def _momentum(events: Sequence[Mapping[str, Any]], labels: Sequence[str]) -> dict[str, Any]:
    """Compare the most recent MATERIAL_MONTHS with the EQUAL window before it."""
    if len(labels) < 2 * MATERIAL_MONTHS:
        return {"status": "insufficient_window", "recent": 0, "prior": 0, "ratio": None,
                "statement": "window shorter than two comparison periods; momentum not estimated"}
    recent_labels = labels[-MATERIAL_MONTHS:]
    prior_labels = labels[-2 * MATERIAL_MONTHS:-MATERIAL_MONTHS]
    months = [str(event.get("date") or "")[:7] for event in events]
    recent, _, recent_rate = _rate(months, recent_labels)
    prior, _, prior_rate = _rate(months, prior_labels)
    if prior_rate in (None, 0):
        ratio = None
    else:
        ratio = recent_rate / prior_rate
    if ratio is None:
        direction = "undefined"
        statement = (f"{recent} material events in the last {MATERIAL_MONTHS} months against "
                     f"{prior} in the prior {MATERIAL_MONTHS}; no prior activity to compare with")
    elif ratio >= 1.25:
        direction = "increasing"
        statement = (f"activity rising: {recent} events in the last {MATERIAL_MONTHS} months vs "
                     f"{prior} in the prior {MATERIAL_MONTHS} (ratio {ratio:.2f})")
    elif ratio <= DECLINE_RATIO:
        direction = "decreasing"
        statement = (f"activity falling: {recent} events in the last {MATERIAL_MONTHS} months vs "
                     f"{prior} in the prior {MATERIAL_MONTHS} (ratio {ratio:.2f})")
    else:
        direction = "stable"
        statement = (f"activity broadly stable: {recent} events in the last {MATERIAL_MONTHS} "
                     f"months vs {prior} in the prior {MATERIAL_MONTHS} (ratio {ratio:.2f})")
    return {"status": "estimated", "recent": recent, "prior": prior,
            "recent_rate": recent_rate, "prior_rate": prior_rate, "ratio": ratio,
            "direction": direction, "statement": statement}


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
        "momentum": _momentum(regulatory_events, labels),
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
    lines += ["", "## 3. Momentum", "", f"- {momentum['statement']}", "",
              "## 4. Concentration", "", f"- {concentration['statement']}", ""]
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
