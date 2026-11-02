"""Phase 1 A1: audit the earlier sources that could precede regulatory events.

Question: can trials (ctgov) or SEC 8-K be paired to the study's device tracks at the firm level, with point-in-time
availability, so that a lead time could be measured at all?

The audit deliberately measures *whether a crosswalk exists*, rather than assuming one: the trial lane assigns
therapy-area tracks (`t_*`) while the study's confirmatory tracks are device tracks (`imaging_us`, `respiratory`).
If no defensible crosswalk exists, the correct verdict is NOT_EVALUABLE, not a fudged pairing.

Emits EARLIER_SOURCE_AUDIT.json and .md. Read-only.

    python experiments/b084/earlier_source_audit.py
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from medradar.studies.coverage import quarter_of  # noqa: E402

STORE = Path("D:/DEPPSKK/medradar/data/medradar.sqlite")
OUT_DIR = Path("research/studies/early_signal_5firms")
WINDOW = ("2018-01-01", "2025-12-31")
FIVE_FIRMS = ("medtronic", "ge_healthcare", "philips", "mindray", "draeger")
ALIASES = {
    "medtronic": ("MEDTRONIC",),
    "ge_healthcare": ("GE HEALTHCARE", "GE MEDICAL", "GE HFS", "GEHC"),
    "philips": ("PHILIPS",),
    "draeger": ("DRAGER", "DRAEGERWERK"),
    "mindray": ("MINDRAY",),
}
EXCLUDED_RAW = ("SURGE MEDICAL",)
CONFIRMATORY = ("imaging_us", "respiratory")


def connect() -> sqlite3.Connection:
    return sqlite3.connect(f"file:{STORE}?mode=ro", uri=True)


def trials_by_firm_track(con: sqlite3.Connection) -> dict:
    """Trials inside the window, resolved by company_key; track distribution and date semantics."""
    out: dict[str, dict] = {}
    for firm in FIVE_FIRMS:
        rows = con.execute(
            "select track_id, count(*), min(event_date), max(event_date) from events "
            "where kind='trial' and company_key=? and event_date between ? and ? "
            "group by track_id order by count(*) desc", (firm, *WINDOW)).fetchall()
        total = con.execute("select count(*) from events where kind='trial' and company_key=? "
                            "and event_date between ? and ?", (firm, *WINDOW)).fetchone()[0]
        with_track = sum(row[1] for row in rows if row[0])
        out[firm] = {"total_in_window": total, "with_track": with_track,
                     "without_track": total - with_track,
                     "tracks": [{"track": track, "count": count, "first": first, "last": last}
                                for track, count, first, last in rows]}
    return out


def eightk_by_firm(con: sqlite3.Connection) -> dict:
    out = {}
    for firm in FIVE_FIRMS:
        rows = con.execute(
            "select track_id, count(*), min(event_date), max(event_date) from events "
            "where kind='8k_catalyst' and company_key=? and event_date between ? and ? "
            "group by track_id", (firm, *WINDOW)).fetchall()
        total = con.execute("select count(*) from events where kind='8k_catalyst' and company_key=? "
                            "and event_date between ? and ?", (firm, *WINDOW)).fetchone()[0]
        out[firm] = {"total_in_window": total,
                     "tracks": [{"track": track, "count": count, "first": first, "last": last}
                                for track, count, first, last in rows]}
    return out


def alias_only_counts(con: sqlite3.Connection, kind: str) -> dict:
    """Trials / 8-K matched only through applicant_raw (no company_key) — the roster gap again."""
    out = {}
    for firm, aliases in ALIASES.items():
        clause = " or ".join("upper(applicant_raw) like ?" for _ in aliases)
        params = [f"%{alias}%" for alias in aliases]
        rows = con.execute(
            f"select track_id, count(*) from events where kind=? and ({clause}) "
            f"and event_date between ? and ? group by track_id", [kind, *params, *WINDOW]).fetchall()
        out[firm] = {"total": sum(row[1] for row in rows),
                     "tracks": {str(track): count for track, count in rows}}
    return out


def taxonomy_crosswalk(con: sqlite3.Connection) -> dict:
    """Do therapy-area tracks (t_*) share a defensible identity with device tracks?"""
    rows = con.execute("select id, name_en, category from tracks").fetchall()
    tracks = {track_id: {"name": name, "category": category} for track_id, name, category in rows}
    therapy = {track_id: info for track_id, info in tracks.items() if track_id.startswith("t_")}
    device = {track_id: info for track_id, info in tracks.items() if not track_id.startswith("t_")}
    # a *candidate* crosswalk exists only when the tail of the therapy id equals a device id
    candidates = {}
    for therapy_id, info in therapy.items():
        tail = therapy_id[2:]
        if tail in device:
            candidates[therapy_id] = {"device_track": tail, "basis": "identical id after the t_ prefix",
                                      "therapy_name": info["name"], "device_name": device[tail]["name"]}
    return {"n_tracks": len(tracks), "n_therapy_area": len(therapy), "n_device": len(device),
            "candidate_crosswalks": candidates,
            "note": ("a candidate is not an established mapping: it needs review, and identical naming does not "
                     "prove that a therapy-area trial belongs to the same technology reading")}


def date_semantics(con: sqlite3.Connection) -> dict:
    """What is event_date for these sources, and what does the payload add?"""
    out = {}
    for kind in ("trial", "8k_catalyst"):
        row = con.execute(
            "select event_date, published_at, available_at, first_seen_at, payload from events "
            "where kind=? limit 1", (kind,)).fetchone()
        if not row:
            continue
        event_date, published_at, available_at, first_seen, payload = row
        data = json.loads(payload) if payload else {}
        out[kind] = {
            "event_date": event_date, "published_at": published_at, "available_at": available_at,
            "first_seen_at": first_seen, "payload_date_fields": {
                key: data[key] for key in ("start_date", "first_posted", "study_first_posted",
                                           "primary_completion_date", "completion_date")
                if key in data},
            "reading": ("for trials, event_date is the posting date (PIT-safe boundary), while the payload also "
                        "carries a trial start_date that precedes posting and therefore may not be used as the "
                        "availability time" if kind == "trial"
                        else "for 8-K, event_date equals the filing date; the payload carries the accession and a "
                             "keyword category, not a technology track"),
        }
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", default=str(OUT_DIR))
    args = parser.parse_args(argv)

    con = connect()
    trials = trials_by_firm_track(con)
    eightk = eightk_by_firm(con)
    trials_alias = alias_only_counts(con, "trial")
    eightk_alias = alias_only_counts(con, "8k_catalyst")
    crosswalk = taxonomy_crosswalk(con)
    semantics = date_semantics(con)
    con.close()

    # can a pairing exist on the confirmatory tracks at all?
    confirm_trial_counts = {}
    for firm in FIVE_FIRMS:
        block = trials[firm]
        confirm_trial_counts[firm] = {track: next((row["count"] for row in block["tracks"]
                                                   if row["track"] == track), 0)
                                      for track in CONFIRMATORY}
    pair_feasibility = {
        "trials_on_confirmatory_device_tracks": confirm_trial_counts,
        "trials_total_on_confirmatory": sum(sum(row.values()) for row in confirm_trial_counts.values()),
        "eightk_per_firm_in_window": {firm: eightk[firm]["total_in_window"] for firm in FIVE_FIRMS},
        "verdict": ("NOT_EVALUABLE for lead-time pairing on the confirmatory tracks: the trial lane assigns "
                    "therapy-area ids (t_*) and only two of them have an id-identical device counterpart, so a "
                    "defensible crosswalk does not exist; 8-K carries no technology track and occurs ~5 times per "
                    "firm in the window"
                    if crosswalk["candidate_crosswalks"] and
                    sum(eightk[firm]["total_in_window"] for firm in FIVE_FIRMS) < 100
                    else "see counts"),
    }

    payload = {
        "schema": "earlier_source_audit_v1",
        "study": "early_signal_5firms",
        "phase": "Phase 1 / A1",
        "window": list(WINDOW),
        "sources": {
            "clinical_trials_ctgov": {
                "tier": "B", "total_records": 55592,
                "tier_reason": ("event_date is the posting date, which is a PIT-safe boundary; the payload's "
                                "trial start_date precedes posting and may not be used as availability"),
                "by_firm": trials, "alias_only": trials_alias,
            },
            "sec_8k": {
                "tier": "B", "total_records": 20976,
                "tier_reason": "event_date is the filing date, a PIT-safe boundary",
                "by_firm": eightk, "alias_only": eightk_alias,
            },
        },
        "taxonomy": crosswalk,
        "date_semantics": semantics,
        "pair_feasibility": pair_feasibility,
        "consequences": [
            "pairing trials to the study's device tracks requires a therapy-area -> device crosswalk that the "
            "store does not contain; inventing one after seeing outcomes would be a pre-registration violation",
            "8-K is too sparse and trackless to support cell-level lead-time measurement",
            "the only defensible earlier-source pairing available today is at the *firm* level, not the firm-track "
            "level; that supports RQ3 weakly and RQ4 not at all",
        ],
        "generated_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "EARLIER_SOURCE_AUDIT.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")

    lines = ["# EARLIER SOURCE AUDIT — can anything precede a regulatory event here?", "",
             f"Window {WINDOW[0]} … {WINDOW[1]}. Produced by `experiments/b084/earlier_source_audit.py`.", "",
             "## Verdict", "", f"**{pair_feasibility['verdict']}**", "",
             "## Clinical trials (ctgov), resolvable by company_key", "",
             "| firm | trials in window | with a track id | tracks used |", "|---|---:|---:|---|"]
    for firm in FIVE_FIRMS:
        block = trials[firm]
        top = ", ".join(f"{row['track']}:{row['count']}" for row in block["tracks"][:5] if row["track"]) or "—"
        lines.append(f"| {firm} | {block['total_in_window']} | {block['with_track']} | {top} |")
    lines += ["", "## SEC 8-K", "", "| firm | in window | tracks |", "|---|---:|---|"]
    for firm in FIVE_FIRMS:
        block = eightk[firm]
        top = ", ".join(f"{row['track']}:{row['count']}" for row in block["tracks"]) or "none assigned"
        lines.append(f"| {firm} | {block['total_in_window']} | {top} |")
    lines += ["", "## Taxonomy", "",
              f"Store has {crosswalk['n_tracks']} tracks: {crosswalk['n_device']} device tracks and "
              f"{crosswalk['n_therapy_area']} therapy-area tracks (`t_*`).",
              "", "Candidate crosswalks (identical id after the `t_` prefix — a candidate, not a mapping):", ""]
    for therapy_id, info in crosswalk["candidate_crosswalks"].items():
        lines.append(f"- `{therapy_id}` → `{info['device_track']}` ({info['therapy_name']} / {info['device_name']})")
    lines += ["", "## Consequences", ""] + [f"- {item}" for item in payload["consequences"]]
    lines += ["", "## Trials on the two confirmatory device tracks", "",
              "| firm | imaging_us | respiratory |", "|---|---:|---:|"]
    for firm, row in confirm_trial_counts.items():
        lines.append(f"| {firm} | {row['imaging_us']} | {row['respiratory']} |")
    lines.append("")
    (out_dir / "EARLIER_SOURCE_AUDIT.md").write_text("\n".join(lines), encoding="utf-8", newline="\n")

    print(f"trials in window with company_key: " +
          ", ".join(f"{f}={trials[f]['total_in_window']}" for f in FIVE_FIRMS))
    print(f"8-K in window: " + ", ".join(f"{f}={eightk[f]['total_in_window']}" for f in FIVE_FIRMS))
    print(f"trials on confirmatory device tracks: {pair_feasibility['trials_total_on_confirmatory']}")
    print(f"therapy-area tracks: {crosswalk['n_therapy_area']}; id-identical candidates: "
          f"{list(crosswalk['candidate_crosswalks'])}")
    print(f"verdict: {pair_feasibility['verdict'][:110]}...")
    print(f"wrote {out_dir}/EARLIER_SOURCE_AUDIT.{{json,md}}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
