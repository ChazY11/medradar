"""Nine-event lead-time description (scope S1-crosswalk-effective, protocol amendment frozen first).

Reads LEAD_LAG_PROBE_CROSSWALK.json, collapses pairs to distinct later clearances, takes the conservative
representative (latest trial = minimum lead), and emits:

  * LEAD_TIME_SMALL_SAMPLE.json / .md — the descriptive distribution, per-firm and per-track breakdowns, and the
    mandatory underpowering wording in every headline;
  * CASE_PACKETS_SMALL_SAMPLE.json — nine human-review packets, all PENDING_HUMAN_REVIEW, no labels.

No confidence interval is computed: the frozen protocol forbids one at n = 9 across three firms.

    python experiments/b094/small_sample_lead_time.py
"""
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from medradar.studies.leadtimedesc import (  # noqa: E402
    INDEPENDENCE_FLOOR,
    describe_leads,
    group_by_later,
    packet,
    representative,
    underpowered_statement,
    upper_bound,
)

STUDY = Path("research/studies/early_signal_5firms")
SOURCE = STUDY / "LEAD_LAG_PROBE_CROSSWALK.json"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", default=str(SOURCE))
    parser.add_argument("--out-dir", default=str(STUDY))
    args = parser.parse_args(argv)

    payload = json.loads(Path(args.source).read_text(encoding="utf-8"))
    pairs = payload.get("pairs") or []
    if not pairs:
        print("ABORT: the crosswalk artifact contains no pair details to describe")
        return 1

    grouped = group_by_later(pairs)
    events = []
    for later_id, candidates in sorted(grouped.items()):
        chosen = representative(candidates)
        bound = upper_bound(candidates)
        events.append({
            "later_id": later_id,
            "company": chosen.get("company"),
            "track": chosen.get("track"),
            "later_date": chosen.get("later_date"),
            "representative_trial": chosen.get("earlier_id"),
            "representative_trial_date": chosen.get("earlier_date"),
            "lead_quarters": chosen.get("lead_quarters"),
            "lead_days": chosen.get("lead_days"),
            "candidate_trials": len(candidates),
            "upper_bound_lead_quarters": bound.get("lead_quarters"),
        })

    leads = [float(event["lead_quarters"]) for event in events]
    summary = describe_leads(leads)
    statement = underpowered_statement(len(events), INDEPENDENCE_FLOOR)

    by_firm = defaultdict(list)
    by_track = defaultdict(list)
    for event in events:
        by_firm[str(event["company"])].append(float(event["lead_quarters"]))
        by_track[str(event["track"])].append(float(event["lead_quarters"]))

    packets = []
    for index, event in enumerate(sorted(events, key=lambda item: (item["company"], item["track"],
                                                                  item["later_date"] or "")), start=1):
        candidates = grouped[event["later_id"]]
        packets.append(packet(event_id=f"LT-{index:02d}", company=str(event["company"]),
                              track=str(event["track"]), clearance_id=str(event["later_id"]),
                              clearance_date=str(event["later_date"]),
                              clearance_kind="510k/pma",
                              representative_pair=representative(candidates), candidates=candidates))

    result = {
        "schema": "lead_time_small_sample_v1",
        "protocol": "LEAD_TIME_SMALL_SAMPLE_PROTOCOL.md (frozen before this run)",
        "source": str(args.source).replace("\\", "/"),
        "independence": {"unit": "distinct later clearance", "pairs_in_source": len(pairs),
                         "distinct_events": len(events), "independence_floor": INDEPENDENCE_FLOOR},
        "representative_rule": "latest paired trial per event (minimum lead); maximum reported only as upper bound",
        "summary": summary,
        "underpowered_statement": statement,
        "conditioning": {
            "note": ("every event entered this description only because its lead was already >= 2 quarters, which is "
                     "the G1 eligibility rule. The share 'lead >= 2 quarters = 1.0' is therefore a tautology, not a "
                     "finding, and the median is a median of a truncated distribution."),
            "truncation_point_quarters": 2.0,
            "implication": "the distribution says nothing about how often leads are shorter than two quarters",
        },
        "events": events,
        "by_firm": {firm: describe_leads(values) for firm, values in sorted(by_firm.items())},
        "by_track": {track: describe_leads(values) for track, values in sorted(by_track.items())},
        "not_claimed": [
            "not a lead-time estimate: nine events, below the independence floor of ten",
            "no confidence interval is computed, by protocol",
            "the crosswalk is a post-hoc text heuristic; a reviewer must confirm each packet",
            "a trial preceding a clearance is compatible with an earlier signal and with the same R&D programme "
            "being filed in that order",
        ],
    }
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "LEAD_TIME_SMALL_SAMPLE.json").write_text(
        json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    (out_dir / "CASE_PACKETS_SMALL_SAMPLE.json").write_text(
        json.dumps({"schema": "case_packets_small_sample_v1", "count": len(packets),
                    "note": "all packets are PENDING_HUMAN_REVIEW; final_label is null by design",
                    "packets": packets}, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8", newline="\n")

    lines = ["# NINE-EVENT LEAD-TIME DESCRIPTION (S1-crosswalk-effective)", "",
             f"**{statement}**", "",
             f"Source pairs: {len(pairs)} → distinct later clearances: **{len(events)}**. "
             f"Representative = latest paired trial per event (minimum lead); the maximum is reported only as an "
             f"upper bound.", "",
             "## Distribution of representative leads (quarters)", "",
             f"- median **{summary['median']}**, IQR {summary['iqr']}, range {summary['range']}",
             f"- share with lead ≥ 1 quarter: **{summary['share_ge_1q']}** (see the conditioning note: this is not a "
             f"finding)",
             f"- share with lead ≥ 2 quarters: **{summary['share_ge_2q']}** — **a tautology**, every event was admitted "
             f"only because its lead was already ≥ 2 quarters", "",
             "**Conditioning caveat.** The distribution is truncated at 2 quarters by the G1 eligibility rule, so the "
             "median describes a selected sample and the shares are artefacts of selection. It says nothing about how "
             "often leads are shorter than two quarters.",
             "## Per event", "",
             "| event | firm | track | clearance date | representative trial | lead (q) | candidates | upper bound (q) |",
             "|---|---|---|---|---|---:|---:|---:|"]
    for index, event in enumerate(events, start=1):
        lines.append(f"| E{index:02d} | {event['company']} | {event['track']} | {event['later_date']} | "
                     f"{event['representative_trial_date']} | {event['lead_quarters']} | "
                     f"{event['candidate_trials']} | {event['upper_bound_lead_quarters']} |")
    lines += ["", "## By firm", "", "| firm | n | median | range |", "|---|---:|---|---|"]
    for firm, block in result["by_firm"].items():
        lines.append(f"| {firm} | {block['n']} | {block['median']} | {block['range']} |")
    lines += ["", "## By track", "", "| track | n | median | range |", "|---|---:|---|---|"]
    for track, block in result["by_track"].items():
        lines.append(f"| {track} | {block['n']} | {block['median']} | {block['range']} |")
    lines += ["", "## Not claimed", ""] + [f"- {item}" for item in result["not_claimed"]]
    (out_dir / "LEAD_TIME_SMALL_SAMPLE.md").write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")

    print(statement)
    print(f"pairs {len(pairs)} -> events {len(events)}; median {summary['median']} q, "
          f"IQR {summary['iqr']}, range {summary['range']}")
    print(f"share >= 1 quarter: {summary['share_ge_1q']}, >= 2 quarters: {summary['share_ge_2q']}")
    print(f"wrote {out_dir}/LEAD_TIME_SMALL_SAMPLE.{{json,md}} and CASE_PACKETS_SMALL_SAMPLE.json ({len(packets)} packets)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
