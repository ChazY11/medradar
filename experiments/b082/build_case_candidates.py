"""Phase 0 (round 3): build 60 candidate case packets by a pre-declared stratified rule.

The directive forbids selecting cases by fame, and forbids the agent from producing human labels. This script
therefore samples **by a prospective rule that never looks at the outcome**:

  * a candidate is a regulatory event (510(k) or PMA) in one of the study tracks for one of the five firms;
  * it is classified by the **gap since that firm's previous event in the same track**:
      - ``novel_entry``      gap >= 12 months (or no previous event): a plausible technology entry
      - ``ambiguous``        4..11 months: unclear whether it is a new direction
      - ``routine``          <= 3 months: a control case that should NOT be a shift
  * sampling is stratified by track, firm and era (2018-2021 vs 2022-2025) with a fixed seed.

Every packet is written with ``human_review_status = PENDING_HUMAN_REVIEW`` and **no label**. Labels are the human
reviewer's job; the packet only assembles the evidence a reviewer needs.

    python experiments/b082/build_case_candidates.py
"""
from __future__ import annotations

import argparse
import json
import random
import sqlite3
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from medradar.studies.coverage import quarter_of  # noqa: E402

STORE = Path("D:/DEPPSKK/medradar/data/medradar.sqlite")
OUT_DIR = Path("research/studies/early_signal_5firms")
SEED = 8080
TARGET_TOTAL = 60
WINDOW = ("2018-01-01", "2025-12-31")
TIER_B_LAG_DAYS = 30          # declared reconstruction lag for openFDA bulk extracts (EVIDENCE_TIME_AUDIT.json)

#: confirmatory tracks (DOMAIN_AMENDMENT_001) plus the exploratory per-firm tracks that carry usable volume
TRACKS = {
    "imaging_us": ("confirmatory", ("ge_healthcare", "philips", "mindray")),
    "respiratory": ("confirmatory", ("ge_healthcare", "philips", "medtronic")),
    "patient_monitoring": ("exploratory", ("philips", "ge_healthcare", "mindray")),
    "medical_ai": ("exploratory", ("ge_healthcare", "philips", "medtronic")),
    "cardiac_rhythm": ("exploratory", ("medtronic",)),
    "imaging_mr_ct": ("exploratory", ("ge_healthcare", "philips")),
}

ALIASES = {
    "medtronic": ("MEDTRONIC",),
    "ge_healthcare": ("GE HEALTHCARE", "GE MEDICAL", "GE HFS", "GEHC"),
    "philips": ("PHILIPS",),
    "mindray": ("MINDRAY",),
    "draeger": ("DRAGER", "DRAEGERWERK"),
}
#: raw strings known (from the entity audit) to be substring false positives
EXCLUDED_RAW = ("SURGE MEDICAL",)

STRATA = ("novel_entry", "ambiguous", "routine")


def parse_date(text: str) -> date | None:
    try:
        return date.fromisoformat(str(text)[:10])
    except (TypeError, ValueError):
        return None


def add_days(text: str, days: int) -> str | None:
    value = parse_date(text)
    if value is None:
        return None
    from datetime import timedelta
    return (value + timedelta(days=days)).isoformat()


def load_events(con: sqlite3.Connection) -> dict[tuple[str, str], list[dict]]:
    events: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for track, (_, firms) in TRACKS.items():
        for firm in firms:
            aliases = ALIASES[firm]
            clause = " or ".join("upper(applicant_raw) like ?" for _ in aliases)
            params = [f"%{alias}%" for alias in aliases]
            rows = con.execute(
                f"select event_id, event_date, kind, product_code, applicant_raw, source, url "
                f"from events where ({clause}) and track_id = ? "
                f"and event_date between ? and ? order by event_date",
                params + [track, WINDOW[0], WINDOW[1]]).fetchall()
            for event_id, event_date, kind, product_code, applicant, source, url in rows:
                if any(token in (applicant or "").upper() for token in EXCLUDED_RAW):
                    continue
                if kind not in ("510k", "pma"):
                    continue
                events[(firm, track)].append({
                    "event_id": event_id, "event_date": event_date, "kind": kind,
                    "product_code": product_code, "applicant_raw": applicant,
                    "source": source, "url": url,
                })
    return events


def classify_gap(previous: date | None, current: date) -> str:
    if previous is None:
        return "novel_entry"
    months = (current.year - previous.year) * 12 + (current.month - previous.month)
    if months >= 12:
        return "novel_entry"
    if months >= 4:
        return "ambiguous"
    return "routine"


def build_candidates(events: dict[tuple[str, str], list[dict]], rng: random.Random) -> list[dict]:
    pool: dict[str, list[dict]] = defaultdict(list)
    for (firm, track), rows in events.items():
        previous = None
        for row in rows:
            current = parse_date(row["event_date"])
            if current is None:
                continue
            stratum = classify_gap(previous, current)
            era = "2018-2021" if current.year <= 2021 else "2022-2025"
            pool[stratum].append({
                "company": firm, "track": track, "stratum": stratum, "era": era,
                "event_date": current.isoformat(), "quarter": quarter_of(current.isoformat()),
                "declared_available_at": add_days(current.isoformat(), TIER_B_LAG_DAYS),
                "days_since_previous_same_track": (current - previous).days if previous else None,
                **{key: row[key] for key in ("event_id", "kind", "product_code", "applicant_raw", "source", "url")},
            })
            previous = current

    per_stratum = TARGET_TOTAL // len(STRATA)
    selected: list[dict] = []
    for stratum in STRATA:
        rows = pool.get(stratum, [])
        # stratify by era then track so the sample is not dominated by one firm or one period
        buckets: dict[tuple[str, str], list[dict]] = defaultdict(list)
        for row in rows:
            buckets[(row["era"], row["track"])].append(row)
        keys = sorted(buckets)
        rng.shuffle(keys)
        take = min(per_stratum, len(rows))
        chosen: list[dict] = []
        index = 0
        while len(chosen) < take and keys:
            key = keys[index % len(keys)]
            bucket = buckets[key]
            if bucket:
                chosen.append(bucket.pop(rng.randrange(len(bucket))))
            index += 1
            if all(not bucket for bucket in buckets.values()):
                break
        selected.extend(chosen)

    packets = []
    for number, row in enumerate(sorted(selected, key=lambda item: (item["stratum"], item["event_date"])), start=1):
        packets.append({
            "case_id": f"ES5-{number:03d}",
            "company": row["company"],
            "technology_track": row["track"],
            "track_role": TRACKS[row["track"]][0],
            "stratum_by_gap_rule": row["stratum"],
            "era": row["era"],
            "candidate_alert": {
                "rule": "regulatory event in a study track, classified by gap to the firm's previous event in that track",
                "alert_quarter": row["quarter"],
                "event_date": row["event_date"],
                "days_since_previous_same_track": row["days_since_previous_same_track"],
            },
            "evidence": {
                "event_id": row["event_id"],
                "kind": row["kind"],
                "product_code": row["product_code"],
                "applicant_raw": row["applicant_raw"],
                "source": row["source"],
                "source_url": row["url"],
                "declared_available_at": row["declared_available_at"],
                "availability_basis": "Tier B: event date plus a declared 30-day lag; not a recorded publication time",
            },
            "counter_evidence": None,
            "independent_outcome": None,
            "human_review_status": "PENDING_HUMAN_REVIEW",
            "final_label": None,
            "review_note": None,
        })
    return packets


def write_markdown(path: Path, packets: list[dict], counts: dict) -> None:
    lines = ["# CASE CANDIDATES — 60 packets, all PENDING_HUMAN_REVIEW", "",
             "Selected by a **prospective gap rule** (never by fame, never by outcome): an event is",
             "`novel_entry` when the firm had no event in that track for ≥12 months, `ambiguous` for 4–11 months,",
             "`routine` for ≤3 months (the control group). Sampling is stratified by era and track with seed 8080.", "",
             f"Totals: **{counts['total']}** packets — " +
             ", ".join(f"{name} {counts[name]}" for name in STRATA) + ".", "",
             "**No packet carries a label.** `final_label` is null for all originals; adjudication is human, and any",
             "auto-filled label would be fabricated evidence.", "",
             "| case | company | track | stratum | era | quarter | event | kind | why a candidate |",
             "|---|---|---|---|---|---|---|---|---|"]
    for packet in packets:
        gap = packet["candidate_alert"]["days_since_previous_same_track"]
        why = "first event in track" if gap is None else f"{gap} days since previous"
        lines.append(f"| {packet['case_id']} | {packet['company']} | {packet['technology_track']} "
                     f"| {packet['stratum_by_gap_rule']} | {packet['era']} "
                     f"| {packet['candidate_alert']['alert_quarter']} | {packet['candidate_alert']['event_date']} "
                     f"| {packet['evidence']['kind']} | {why} |")
    lines += ["", "## What a reviewer must decide", "",
              "For each packet, the reviewer records one of: `Confirmed Shift`, `Routine Iteration`,",
              "`False Signal / No Confirmed Shift`, `Uncertain`, `Insufficient Observation` — with the evidence they",
              "used, and whether the confirmation is independent of the source that raised the candidate.", ""]
    path.write_text("\n".join(lines), encoding="utf-8", newline="\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", default=str(OUT_DIR))
    parser.add_argument("--seed", type=int, default=SEED)
    args = parser.parse_args(argv)

    con = sqlite3.connect(f"file:{STORE}?mode=ro", uri=True)
    events = load_events(con)
    con.close()

    packets = build_candidates(events, random.Random(args.seed))
    counts = {"total": len(packets)}
    for stratum in STRATA:
        counts[stratum] = sum(1 for packet in packets if packet["stratum_by_gap_rule"] == stratum)
    counts["by_track"] = {}
    for packet in packets:
        track = packet["technology_track"]
        counts["by_track"][track] = counts["by_track"].get(track, 0) + 1
    counts["by_company"] = {}
    for packet in packets:
        company = packet["company"]
        counts["by_company"][company] = counts["by_company"].get(company, 0) + 1

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    payload = {"schema": "case_candidates_v1", "seed": args.seed, "selection_rule": {
        "unit": "regulatory event in a study track for one of the five firms",
        "strata": {"novel_entry": ">= 12 months since previous event in the same track",
                   "ambiguous": "4..11 months", "routine": "<= 3 months (control)"},
        "stratified_by": ["era", "track"], "outcome_blind": True,
        "excluded_raw_strings": list(EXCLUDED_RAW),
    }, "counts": counts, "cases": packets}
    (out_dir / "CASE_CANDIDATES.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    write_markdown(out_dir / "CASE_CANDIDATES.md", packets, counts)

    print(f"packets: {counts['total']}  " + "  ".join(f"{name}={counts[name]}" for name in STRATA))
    print(f"by track: {counts['by_track']}")
    print(f"by company: {counts['by_company']}")
    print(f"wrote {out_dir}/CASE_CANDIDATES.json and .md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
