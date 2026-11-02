"""Phase 0 (round 2): entity-resolution audit + data-driven domain amendment inputs.

Two blocking questions for any firm-level claim:

  1. **Entity resolution.** Dräger and Mindray have no `company_key` in the store's roster, so their events are
     matched on `applicant_raw`. How many distinct raw strings are involved, what do they look like, and which
     matches are plausible false positives? For GE HealthCare the risk is different: the store's roster key spans a
     corporate restructuring (GE Medical Systems -> GE HealthCare, listed 2023), so pre-2023 events must be checked
     for continuity rather than assumed to belong to today's legal entity.

  2. **Domain amendment.** The five candidate domains leave Medtronic with 113 usable observations out of 18,147
     events. Which tracks are shared by enough firms to support cross-company validation (RQ4)? This script
     measures that from coverage alone, before any outcome is examined.

Read-only over the frozen store. Writes JSON only; the human-readable amendment is written separately.

    python experiments/b081/entity_and_domain_audit.py
"""
from __future__ import annotations

import json
import sqlite3
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from medradar.studies.coverage import FIVE_FIRMS, quarter_of  # noqa: E402

STORE = Path("D:/DEPPSKK/medradar/data/medradar.sqlite")
OUT = Path("research/studies/early_signal_5firms/ENTITY_AND_DOMAIN_AUDIT.json")
WINDOW = ("2018-01-01", "2025-12-31")
FLOOR_OBS = 40
FLOOR_QUARTERS = 12
MIN_FIRMS_PER_TRACK = 3

ALIASES = {
    "draeger": ("DRAGER", "DRÄGER", "DRAEGERWERK"),
    "mindray": ("MINDRAY",),
    "ge_healthcare": ("GE HEALTHCARE", "GE MEDICAL", "GE HFS", "GEHC"),
    "philips": ("PHILIPS",),
    "medtronic": ("MEDTRONIC",),
}

#: raw strings that contain an alias but plausibly belong to a different manufacturer or product line
SUSPICION_TOKENS = ("SAFETY", "SERVICE", "RENTAL", "SALES", "DISTRIBUT", "REPAIR", "PARTS")


def connect() -> sqlite3.Connection:
    return sqlite3.connect(f"file:{STORE}?mode=ro", uri=True)


def alias_strings(con: sqlite3.Connection, firm: str, aliases: tuple[str, ...]) -> dict:
    """Distinct raw applicant strings matching a firm's aliases, with counts and a suspicion flag."""
    clause = " or ".join("upper(applicant_raw) like ?" for _ in aliases)
    params = [f"%{alias}%" for alias in aliases]
    rows = con.execute(
        f"select applicant_raw, count(*), min(event_date), max(event_date) from events "
        f"where ({clause}) group by applicant_raw order by count(*) desc", params).fetchall()
    strings = []
    for raw, count, first, last in rows:
        upper = (raw or "").upper()
        flagged = [token for token in SUSPICION_TOKENS if token in upper]
        strings.append({"applicant_raw": raw, "observations": count,
                        "first": first, "last": last,
                        "suspicion_tokens": flagged,
                        "verdict": "REVIEW" if flagged else "plausible"})
    return {"distinct_strings": len(strings), "observations": sum(item["observations"] for item in strings),
            "strings": strings}


def ge_continuity(con: sqlite3.Connection) -> dict:
    """GE HealthCare: does the roster key cover the pre-2023 GE Medical Systems era, and how is it split?"""
    groups = {
        "ge_healthcare": ("GE HEALTHCARE", "GEHC", "GE HFS"),
        "ge_medical_systems": ("GE MEDICAL SYSTEMS", "GE MEDICAL"),
        "other_ge": ("GE ",),
    }
    per_year: dict[str, Counter] = {name: Counter() for name in groups}
    for name, aliases in groups.items():
        clause = " or ".join("upper(applicant_raw) like ?" for _ in aliases)
        params = [f"%{alias}%" for alias in aliases]
        rows = con.execute(
            f"select substr(event_date,1,4) as year, count(*) from events where ({clause}) "
            f"group by year", params).fetchall()
        for year, count in rows:
            per_year[name][year] += count
    roster = con.execute("select key, name_en, ticker from companies where key like 'ge%'").fetchall()
    return {"roster_rows": roster,
            "per_year_by_alias_group": {name: dict(sorted(counter.items()))
                                        for name, counter in per_year.items()},
            "reading": ("the roster key ge_healthcare is mapped to raw applicants from several corporate eras; the "
                        "continuity of 'the same legal entity' across 1978-2026 is NOT established by these strings "
                        "and must not be assumed in a firm-level claim")}


def domain_sharing(con: sqlite3.Connection) -> dict:
    """For every track, which of the five firms meet the coverage floors inside the window?"""
    placeholders = ",".join("?" for _ in FIVE_FIRMS)
    rows = con.execute(
        f"select company_key, track_id, event_date from events "
        f"where company_key in ({placeholders}) and track_id is not null", FIVE_FIRMS).fetchall()
    alias_rows = []
    for firm, aliases in ALIASES.items():
        clause = " or ".join("upper(applicant_raw) like ?" for _ in aliases)
        params = [f"%{alias}%" for alias in aliases]
        alias_rows += con.execute(
            f"select ? as firm, track_id, event_date from events where ({clause}) and track_id is not null "
            f"and (company_key is null or company_key not in ({placeholders}))",
            [firm] + params + list(FIVE_FIRMS)).fetchall()

    cells: dict[tuple[str, str], dict] = defaultdict(lambda: {"observations": 0, "quarters": set()})
    for firm, track, date in list(rows) + [(r[0], r[1], r[2]) for r in alias_rows]:
        quarter = quarter_of(date)
        if not quarter:
            continue
        if not (WINDOW[0][:4] <= quarter[:4] <= WINDOW[1][:4]):
            continue
        cell = cells[(track, firm)]
        cell["observations"] += 1
        cell["quarters"].add(quarter)

    per_track: dict[str, dict] = defaultdict(dict)
    for (track, firm), cell in cells.items():
        per_track[track][firm] = {"observations": cell["observations"],
                                  "quarters": len(cell["quarters"]),
                                  "meets_floor": cell["observations"] >= FLOOR_OBS
                                                 and len(cell["quarters"]) >= FLOOR_QUARTERS}
    shared = {}
    for track, firms in per_track.items():
        qualified = sorted(firm for firm, block in firms.items() if block["meets_floor"])
        if len(qualified) >= MIN_FIRMS_PER_TRACK:
            shared[track] = {"firms_meeting_floor": qualified, "count": len(qualified),
                             "detail": firms}
    return {"floors": {"min_observations": FLOOR_OBS, "min_quarters": FLOOR_QUARTERS,
                       "min_firms_per_track": MIN_FIRMS_PER_TRACK},
            "shared_tracks": dict(sorted(shared.items(), key=lambda item: -item[1]["count"])),
            "all_tracks_touched": sorted(per_track)}


def main() -> int:
    con = connect()
    payload = {
        "schema": "entity_and_domain_audit_v1",
        "study": "early_signal_5firms",
        "window": list(WINDOW),
        "entity_resolution": {firm: alias_strings(con, firm, aliases) for firm, aliases in ALIASES.items()},
        "ge_continuity": ge_continuity(con),
        "domain_sharing": domain_sharing(con),
        "limitations": [
            "alias matching on applicant_raw is substring matching: it can match distributors, service arms or "
            "product-line names, which is why suspicion tokens are flagged for human review",
            "a matched string does not establish legal-entity identity for a firm-level claim",
            "the store records no per-record publication timestamp, so this audit says nothing about availability "
            "time; see EVIDENCE_TIME_AUDIT.json",
        ],
    }
    con.close()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")

    for firm, block in payload["entity_resolution"].items():
        review = sum(1 for item in block["strings"] if item["verdict"] == "REVIEW")
        print(f"{firm:14s} distinct strings {block['distinct_strings']:>3}  observations {block['observations']:>6}"
              f"  flagged for review {review}")
    print("\nshared tracks (>= 3 firms meeting floors):")
    for track, block in payload["domain_sharing"]["shared_tracks"].items():
        print(f"  {track:24s} {block['count']} firms: {', '.join(block['firms_meeting_floor'])}")
    print(f"\nwrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
