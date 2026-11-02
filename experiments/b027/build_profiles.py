"""B-027: build company technology profiles from the frozen evidence.

Library logic lives in `medradar/intelligence/profile.py` (pure, unit-tested). This script does the
I/O: it reads the regulatory lane, the device-trial lane and the curated company roster, resolves
each company's legal entities exactly as the rest of the programme does, and emits one profile JSON
plus one Markdown profile per mandated deep-case company.

Usage:
    python experiments/b027/build_profiles.py
"""
from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from experiments.cycle2_coverage.panel import load_regulatory_events, write_json  # noqa: E402
from experiments.detect_v1.streams import month_index  # noqa: E402
from medradar.intelligence.profile import build_profile, render_markdown  # noqa: E402
from medradar.intelligence.taxonomy import regime as taxonomy_regime  # noqa: E402
from medradar.intelligence.universe import entity_key, normalise_applicant, resolve_entities  # noqa: E402

LANE = Path("data/research.sqlite")
TRIALS = Path("data/b040_device_trials.sqlite")
COMPANIES = Path("config/companies_device.json")
UNIVERSE = Path("config/universe_v1.json")
OUT_DIR = Path("experiments/b027")
WINDOW = ("2016-11", "2026-09")
FOCUS = ("medtronic", "ge_healthcare", "philips", "draeger", "mindray")
AS_OF = "2026-11-02"


def month_label(index: int) -> str:
    year, month = divmod(index, 12)
    return f"{2016 + year:04d}-{month + 1:02d}"


def load_families() -> dict[str, dict[str, Any]]:
    roster = json.loads(COMPANIES.read_text(encoding="utf-8"))["companies"]
    universe = json.loads(UNIVERSE.read_text(encoding="utf-8"))["entities"]
    families = {}
    for company in roster:
        key = str(company.get("key") or "")
        aliases = [company.get("name_en") or "", *(company.get("aliases") or [])]
        entities = resolve_entities(universe, aliases)
        families[key] = {"display_name": company.get("name_en") or key,
                         "aliases": [alias for alias in aliases if alias],
                         "entities": entities}
    # MISSION mandates five deep cases; two of them (Draeger, Mindray) are not in the device
    # roster, so they are resolved from the universe module's focus list instead of being dropped.
    from medradar.intelligence.universe import FOCUS_COMPANIES

    for key, block in FOCUS_COMPANIES.items():
        if key in families:
            continue
        aliases = [block.get("display_name") or key, *(block.get("aliases") or [])]
        families[key] = {"display_name": block.get("display_name") or key,
                         "aliases": [alias for alias in aliases if alias],
                         "entities": resolve_entities(universe, aliases)}
    return families


def resolve_regulatory(events: list[dict[str, Any]], families: dict[str, dict[str, Any]],
                       codes: dict[str, str]) -> dict[str, list[dict[str, Any]]]:
    entity_to_company = {entity: key for key, family in families.items()
                         for entity in family["entities"]}
    per_company: dict[str, list[dict[str, Any]]] = {key: [] for key in families}
    for event in events:
        normalised = normalise_applicant(event.get("applicant_raw"))
        if not normalised:
            continue
        company = entity_to_company.get(entity_key(normalised))
        if not company:
            continue
        index = month_index(event["day"])
        if index is None:
            continue
        per_company[company].append({
            "date": str(event["day"])[:10],
            "track": event.get("track_id") or "",
            "code": codes.get(str(event.get("event_id")), ""),
        })
    return per_company


def code_first_seen(events: list[dict[str, Any]], codes: dict[str, str]) -> dict[str, str]:
    first: dict[str, int] = {}
    for event in events:
        code = codes.get(str(event.get("event_id")), "")
        index = month_index(event["day"])
        if not code or index is None:
            continue
        if code not in first or index < first[code]:
            first[code] = index
    return {code: month_label(index) for code, index in first.items()}


def resolve_trials(families: dict[str, dict[str, Any]],
                   cutoff: str | None = None) -> dict[str, list[dict[str, Any]]]:
    """Trials per company. ``cutoff`` enforces the point-in-time rule for the trial lane too."""
    per_company: dict[str, list[dict[str, Any]]] = {key: [] for key in families}
    if not TRIALS.exists():
        return per_company
    con = sqlite3.connect(f"file:{TRIALS}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    try:
        rows = con.execute(
            "select company_key, track_id, event_date from events where kind='trial'").fetchall()
    except sqlite3.Error:
        rows = []
    con.close()
    for row in rows:
        company = str(row["company_key"] or "")
        track = str(row["track_id"] or "")
        date = str(row["event_date"] or "")
        if cutoff is not None and date[:10] > cutoff:
            continue
        if company in per_company and track and len(date) >= 10:
            per_company[company].append({"date": date, "track": track})
    return per_company


def hiring_status(company_key: str) -> str:
    panel_path = Path("experiments/b030/hiring_panel_v2.json")
    if not panel_path.exists():
        return "hiring panel not available"
    panel = json.loads(panel_path.read_text(encoding="utf-8"))
    block = panel["companies"].get(company_key) or {}
    postings = block.get("distinct_postings") or 0
    months = block.get("months") or 0
    if not postings:
        return "no archived hiring board found for this company (coverage absence, not zero hiring)"
    return f"{postings} archived postings across {months} months (posting-flow proxy, not headcount)"


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Build company technology profiles.")
    parser.add_argument("--scope", choices=("focus", "roster"), default="roster",
                        help="focus = the five mandated deep cases; roster = every curated company")
    parser.add_argument("--as-of", default=AS_OF,
                        help="point-in-time cut: only evidence on or before this date is used")
    parser.add_argument("--out", default=str(OUT_DIR))
    args = parser.parse_args(argv)
    out_dir = Path(args.out)
    as_of = str(args.as_of)
    window_end = min(WINDOW[1], as_of[:7])
    window = (WINDOW[0], window_end)

    if not LANE.exists():
        print(f"lane database missing: {LANE}")
        return 1
    families = load_families()
    from experiments.detect_v1.streams import load_product_codes

    all_events = load_regulatory_events(LANE)
    codes = load_product_codes(LANE)
    # point-in-time cut: nothing after the as-of date may influence a profile
    events = [event for event in all_events if str(event["day"])[:10] <= as_of]
    print(f"regulatory events: {len(all_events)} total, {len(events)} on or before {as_of}")
    regulatory = resolve_regulatory(events, families, codes)
    first_seen = code_first_seen(events, codes)
    trials = resolve_trials(families, cutoff=as_of)

    targets = sorted(FOCUS) if args.scope == "focus" else sorted(
        set(families) | set(FOCUS))
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "profiles").mkdir(exist_ok=True)
    payload = {"schema": "profiles_v1", "as_of": as_of, "window": list(window),
               "scope": args.scope, "point_in_time": True,
               "taxonomy": taxonomy_regime(),
               "focus_companies": list(FOCUS), "profiles": {}}
    for company_key in targets:
        family = families.get(company_key)
        if not family:
            print(f"{company_key}: not in roster")
            continue
        profile = build_profile(
            company_key=company_key,
            display_name=family["display_name"],
            aliases=family["aliases"],
            entity_keys=family["entities"],
            as_of=as_of,
            window=window,
            sources=("data/research.sqlite (510(k)+PMA lane)", "data/b040_device_trials.sqlite",
                     "config/companies_device.json", "config/universe_v1.json"),
            regulatory_events=regulatory[company_key],
            trial_events=trials.get(company_key, []),
            code_first_seen=first_seen,
            hiring_status=hiring_status(company_key),
        )
        # leakage audit: record the latest evidence date that actually entered this profile
        latest_regulatory = max((row["date"] for row in regulatory[company_key]), default=None)
        latest_trial = max((row["date"] for row in trials.get(company_key, [])), default=None)
        profile["leakage_audit"] = {
            "as_of": as_of,
            "window": list(window),
            "latest_regulatory_event": latest_regulatory,
            "latest_trial_event": latest_trial,
            "latest_code_first_seen": max(first_seen.values(), default=None),
            "checked": True,
        }
        payload["profiles"][company_key] = profile
        markdown = render_markdown(profile)
        (out_dir / "profiles" / f"{company_key}.md").write_text(
            markdown, encoding="utf-8", newline="\n")
        momentum_label = (profile["momentum"].get("direction")
                          or profile["momentum"].get("status") or "unknown")
        print(f"{company_key:16s} events={profile['technology_footprint']['total_events']:4d} "
              f"tracks={profile['technology_footprint']['tracks']:3d} "
              f"momentum={momentum_label:12s} "
              f"contradictions={len(profile['contradictory_evidence']['found'])}")
    write_json(out_dir / "profiles.json", payload)
    print(f"wrote {out_dir / 'profiles.json'} and {len(payload['profiles'])} markdown profiles")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

