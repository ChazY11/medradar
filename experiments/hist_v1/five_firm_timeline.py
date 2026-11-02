"""hist_v1 — five deep-case descriptive timelines from the frozen panel.

READ-ONLY consumer of out/hist_v1/panel.json. No model, no inference: this script only counts what
the panel records, so the five-company case studies cannot become unsupported strategy stories.

Output:
    experiments/hist_v1/five_firm_timeline.json
    experiments/hist_v1/FIVE_FIRM_TIMELINE.md

Usage:
    python experiments/hist_v1/five_firm_timeline.py
"""
from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PANEL = ROOT / "out" / "hist_v1" / "panel.json"
OUT_JSON = ROOT / "experiments" / "hist_v1" / "five_firm_timeline.json"
OUT_MD = ROOT / "experiments" / "hist_v1" / "FIVE_FIRM_TIMELINE.md"
DEEP = ["medtronic", "ge_healthcare", "philips", "draeger", "mindray"]
ERAS = [(0, 79, "1976-1995"), (80, 119, "1996-2005"), (120, 159, "2006-2015"), (160, 201, "2016-2026")]


def load():
    payload = json.loads(PANEL.read_text(encoding="utf-8"))
    quarters = payload["quarters"]
    cat = {t["id"]: t["category"] for t in payload["tracks"]}
    companies = {c["key"]: c for c in payload["companies"]}
    return payload, quarters, cat, companies


def quarter_label(quarters, qidx):
    return quarters[qidx]


def build(payload, quarters, cat, companies):
    pairs = payload["pairs"]
    # per company: list of (track, first_qidx, n_events)
    entries = defaultdict(list)
    per_firm_events = Counter()
    per_firm_tracks = defaultdict(set)
    for pair in pairs:
        qidx = pair["event_qidx"]
        counts = pair.get("event_counts") or [1] * len(qidx)
        ck = pair["company_key"]
        per_firm_events[ck] += sum(counts)
        per_firm_tracks[ck].add(pair["track_id"])
        if qidx:
            entries[ck].append((pair["track_id"], min(qidx), sum(counts)))

    # industry entries per track-quarter, for the co-entry statistic
    entry_quarter_index = defaultdict(list)
    for ck, rows in entries.items():
        for track, qidx, _ in rows:
            entry_quarter_index[(track, qidx)].append(ck)

    def co_entries(track, qidx, exclude):
        found = []
        for dq in range(-4, 5):
            found.extend(c for c in entry_quarter_index.get((track, qidx + dq), []) if c != exclude)
        return sorted(set(found))

    firms = {}
    for ck in DEEP:
        rows = sorted(entries.get(ck, []), key=lambda r: r[1])
        by_era = Counter()
        for track, qidx, _ in rows:
            for lo, hi, label in ERAS:
                if lo <= qidx <= hi:
                    by_era[label] += 1
        # adjacency at entry: did the firm already have a material event in the same category?
        prior_by_era = defaultdict(set)
        for track, qidx, _ in rows:
            prior_by_era[qidx].add(track)
        adjacent_at_entry = 0
        for track, qidx, _ in rows:
            prior_tracks = set()
            for other_track, other_qidx, _ in rows:
                if other_qidx < qidx:
                    prior_tracks.add(other_track)
            if any(cat.get(t) == cat.get(track) for t in prior_tracks):
                adjacent_at_entry += 1
        firms[ck] = {
            "display_name": companies[ck]["display_name"],
            "cohort": companies[ck]["cohort"],
            "material_events": per_firm_events[ck],
            "tracks_entered": len(rows),
            "entries_by_era": dict(by_era),
            "first_entry": quarter_label(quarters, rows[0][1]) if rows else None,
            "last_entry": quarter_label(quarters, rows[-1][1]) if rows else None,
            "entries_with_same_category_prior_activity": adjacent_at_entry,
            "entries": [
                {
                    "track": track,
                    "category": cat.get(track),
                    "entry_quarter": quarter_label(quarters, qidx),
                    "material_events": n,
                    "co_entrant_firms_within_4q": co_entries(track, qidx, ck),
                }
                for track, qidx, n in rows
            ],
        }

    # comparative matrix: roster firms x category, entries 1996-2026 (grid indices 80..201)
    matrix = defaultdict(Counter)
    recent_entries = Counter()
    for ck, rows in entries.items():
        for track, qidx, _ in rows:
            if qidx >= 80:
                matrix[ck][cat.get(track) or "unknown"] += 1
                recent_entries[track] += 1
    matrix_rows = []
    for ck in sorted(matrix):
        row = {"company_key": ck, "display_name": companies[ck]["display_name"],
               "cohort": companies[ck]["cohort"], "entries_by_category": dict(matrix[ck])}
        matrix_rows.append(row)
    matrix_rows.sort(key=lambda r: (-sum(r["entries_by_category"].values()),
                                    -per_firm_events[r["company_key"]]))

    return {
        "schema": "hist_v1.five_firm_timeline.v1",
        "source_panel": "out/hist_v1/panel.json",
        "n_companies": len(companies),
        "n_tracks": len(cat),
        "deep_cases": firms,
        "comparative_matrix_1996_2026": matrix_rows[:53],
        "track_entry_counts_1996_2026": dict(recent_entries.most_common()),
        "notes": [
            "entries are FIRST-EVER observed material clearances in a track within the 1976-2026 store; "
            "a pair whose entry predates 1976 is left-censored and does not appear",
            "co-entrant firms are other panel companies that entered the same track within +/-4 quarters",
            "no causal or strategic claim is made here; counts only",
        ],
    }


def render_md(result, quarters) -> str:
    lines = ["# Five-company entry timelines (descriptive, from the frozen hist_v1 panel)", ""]
    lines.append("Generated by `experiments/hist_v1/five_firm_timeline.py` from `out/hist_v1/panel.json`; "
                 "counts only, no model, no inference. Entries are first-ever observed material clearances "
                 "in a technology track, 1976-Q2..2026-Q2.")
    lines.append("")
    lines.append("## Deep cases")
    lines.append("")
    lines.append("| firm | material events | tracks entered | first entry | last entry | entries 1976-1995 | 1996-2005 | 2006-2015 | 2016-2026 | entries with same-category prior activity |")
    lines.append("|---|---:|---:|---|---|---:|---:|---:|---:|---:|")
    for ck, f in result["deep_cases"].items():
        e = f["entries_by_era"]
        lines.append(
            f"| {f['display_name']} | {f['material_events']:,} | {f['tracks_entered']} | {f['first_entry']} | "
            f"{f['last_entry']} | {e.get('1976-1995',0)} | {e.get('1996-2005',0)} | {e.get('2006-2015',0)} | "
            f"{e.get('2016-2026',0)} | {f['entries_with_same_category_prior_activity']}/{f['tracks_entered']} |")
    lines.append("")
    for ck, f in result["deep_cases"].items():
        lines.append(f"### {f['display_name']} ({ck})")
        lines.append("")
        for row in f["entries"]:
            co = ", ".join(row["co_entrant_firms_within_4q"]) or "none"
            lines.append(f"- **{row['track']}** ({row['category']}) — first clearance {row['entry_quarter']}, "
                         f"{row['material_events']} material events; co-entrants within 4 quarters: {co}")
        lines.append("")
    lines.append("## Comparative matrix (entries 1996-2026 by category, top 15 firms)")
    lines.append("")
    lines.append("| firm | cohort | entries | categories entered |")
    lines.append("|---|---|---:|---|")
    for row in result["comparative_matrix_1996_2026"][:15]:
        cats = row["entries_by_category"]
        lines.append(f"| {row['display_name']} | {row['cohort']} | {sum(cats.values())} | "
                     f"{', '.join(f'{k}:{v}' for k, v in sorted(cats.items(), key=lambda kv: -kv[1]))} |")
    lines.append("")
    lines.append("## Not claimed")
    lines.append("")
    lines.append("- No entry here is a strategic shift; it is a first public clearance in a track.")
    lines.append("- The taxonomy is current and applied to history; a track's age may be overstated.")
    lines.append("- Co-entry within four quarters is a descriptive coincidence count, not evidence of diffusion.")
    return "\n".join(lines) + "\n"


def main() -> int:
    payload, quarters, cat, companies = load()
    result = build(payload, quarters, cat, companies)
    OUT_JSON.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    OUT_MD.write_text(render_md(result, quarters), encoding="utf-8")
    for ck, f in result["deep_cases"].items():
        print(f"{ck:14s} events={f['material_events']:5d} tracks={f['tracks_entered']:2d} "
              f"first={f['first_entry']} last={f['last_entry']} eras={f['entries_by_era']}")
    print(f"wrote {OUT_JSON.name} and {OUT_MD.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
