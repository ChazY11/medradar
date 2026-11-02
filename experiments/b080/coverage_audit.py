"""Phase 0 coverage + evidence-time audit for the five-firm study (Directive 001).

Produces, from the frozen stores and read-only:
  research/studies/early_signal_5firms/COVERAGE_MATRIX.json / .md
  research/studies/early_signal_5firms/EVIDENCE_TIME_AUDIT.json / .md
  research/studies/early_signal_5firms/CLOCK_AUDIT.json

Design rules taken from the directive:
  * a table existing is not evidence that a source is usable — tiering is computed from the timestamp columns the
    store actually carries, and `first_seen_at` written at collection time is not a publication time;
  * firm presence is probed twice: by `company_key` and by `applicant_raw` (the roster gap for Dräger and Mindray is
    recorded rather than reported as absent data);
  * the window is 2018-01-01 .. 2025-12-31; anything outside is counted, not silently dropped.

    python experiments/b080/coverage_audit.py
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from medradar.studies.coverage import (  # noqa: E402
    DOMAINS,
    FIVE_FIRMS,
    aggregate_coverage,
    classify_source,
    evaluability,
)

MAIN_STORE = Path("D:/DEPPSKK/medradar/data/medradar.sqlite")
RESEARCH_LANE = Path("data/research.sqlite")
TRIALS_LANE = Path("data/b040_device_trials.sqlite")
OUT_DIR = Path("research/studies/early_signal_5firms")
WINDOW = ("2018-01-01", "2025-12-31")

#: applicant_raw fragments that resolve each firm when the roster has no company_key
APPLICANT_ALIASES = {
    "medtronic": ("MEDTRONIC",),
    "ge_healthcare": ("GE HEALTHCARE", "GE MEDICAL", "GE HFS", "GEHC"),
    "philips": ("PHILIPS",),
    "draeger": ("DRAGER", "DRÄGER", "DRAEGERWERK"),
    "mindray": ("MINDRAY",),
}

#: declared availability assumptions for Tier B sources (days). Used only in sensitivity analysis, never as fact.
TIER_B_LAG_DAYS = {"openfda_device_510k": 30, "openfda_device_pma": 30, "openfda_device_recall": 30,
                   "ctgov": 30, "sec_edgar_corpus": 5, "openfda_device_510k_bulk": 30,
                   "openfda_device_pma_bulk": 30}


def connect(path: Path) -> sqlite3.Connection | None:
    if not path.exists():
        return None
    return sqlite3.connect(f"file:{path}?mode=ro", uri=True)


def table_columns(con: sqlite3.Connection, table: str) -> list[str]:
    return [row[1] for row in con.execute(f'PRAGMA table_info("{table}")')]


def source_inventory(con: sqlite3.Connection, label: str) -> dict:
    """Per source/kind row counts and date spans, with the tier computed from recorded columns."""
    present_columns = set(table_columns(con, "events"))
    rows = con.execute(
        "select source, kind, count(*), min(event_date), max(event_date) from events "
        "group by source, kind order by count(*) desc").fetchall()
    inventory = {}
    for source, kind, count, first, last in rows:
        tier = classify_source(present=source in present_columns or True, columns=present_columns,
                               first_seen_is_fetch=True)
        inventory[f"{source}|{kind}"] = {
            "store": label, "source": source, "kind": kind, "observations": count,
            "event_date_min": first, "event_date_max": last,
            "tier": tier["tier"], "tier_reasons": tier["reasons"],
            "tier_description": tier["description"],
            "availability_assumption_days": TIER_B_LAG_DAYS.get(source),
        }
    return inventory


def collect_observations(con: sqlite3.Connection, *, roster_only: bool) -> list[dict]:
    """Rows for the study universe: roster firms by company_key, plus alias-matched rows for the roster gap."""
    observations: list[dict] = []
    placeholders = ",".join("?" for _ in FIVE_FIRMS)
    rows = con.execute(
        f"select company_key, track_id, event_date, source, kind from events "
        f"where company_key in ({placeholders})", FIVE_FIRMS).fetchall()
    for company, track, date, source, kind in rows:
        observations.append({"company": company, "track": track, "date": date,
                             "source": source, "kind": kind, "resolved_by": "company_key"})
    if roster_only:
        return observations
    for firm, aliases in APPLICANT_ALIASES.items():
        clause = " or ".join("upper(applicant_raw) like ?" for _ in aliases)
        params = [f"%{alias}%" for alias in aliases]
        rows = con.execute(
            f"select track_id, event_date, source, kind, applicant_raw from events "
            f"where ({clause}) and (company_key is null or company_key not in ({placeholders}))",
            params + list(FIVE_FIRMS)).fetchall()
        for track, date, source, kind, applicant in rows:
            observations.append({"company": firm, "track": track, "date": date,
                                 "source": source, "kind": kind,
                                 "resolved_by": "applicant_alias"})
    return observations


def roster_status(con: sqlite3.Connection) -> dict:
    status = {}
    for firm in FIVE_FIRMS:
        row = con.execute("select key, name_en, ticker from companies where key = ?", (firm,)).fetchone()
        status[firm] = {"company_key_present": row is not None,
                        "name_en": row[1] if row else None,
                        "ticker": row[2] if row else None}
    return status


def clock_audit() -> dict:
    """The directive requires checking real execution time against documents and commits."""
    now_local = datetime.now().astimezone()
    now_utc = datetime.now(timezone.utc)
    try:
        git_head = subprocess.run(["git", "log", "-1", "--format=%H %cI %s"], capture_output=True,
                                  text=True, timeout=30).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        git_head = ""
    doc_dates = {}
    for path in sorted(Path("research").glob("*.md")):
        text = path.read_text(encoding="utf-8", errors="replace")
        candidates = [line for line in text.splitlines() if "202" in line and "-" in line][:1]
        doc_dates[path.name] = {"mtime": datetime.fromtimestamp(path.stat().st_mtime).astimezone().isoformat(),
                                "first_date_mention": candidates[0][:120] if candidates else None}
    future = [name for name, block in doc_dates.items()
              if block["mtime"] > now_local.isoformat()]
    return {
        "system_local_now": now_local.isoformat(timespec="seconds"),
        "system_utc_now": now_utc.isoformat(timespec="seconds"),
        "timezone": str(now_local.tzinfo),
        "git_head": git_head,
        "research_doc_mtimes": doc_dates,
        "docs_with_future_mtime": future,
        "conclusion": ("no document mtime is in the future relative to the system clock"
                       if not future else f"{len(future)} document(s) carry a future mtime"),
    }


def write_markdown(path: Path, payload: dict) -> None:
    lines = ["# COVERAGE MATRIX — five-firm early-signal study (Phase 0)", "",
             f"Window: **{payload['coverage']['window']['start']} .. {payload['coverage']['window']['end']}** "
             f"({payload['coverage']['window']['quarters']} quarters). "
             f"Unit: company × domain × quarter.", "",
             "Generated by `experiments/b080/coverage_audit.py`; machine-readable twin in `COVERAGE_MATRIX.json`.", "",
             "## Per-firm presence", "",
             "| firm | company_key in store | observations in window | domains non-empty |", "|---|---|---:|---:|"]
    for firm in FIVE_FIRMS:
        status = payload["roster"][firm]
        block = payload["coverage"]["per_firm"].get(firm, {"observations": 0, "domains_nonempty": 0})
        lines.append(f"| {firm} | {'yes' if status['company_key_present'] else '**no** (alias-resolved only)'} "
                     f"| {block['observations']} | {block['domains_nonempty']} |")
    lines += ["", "## Company × domain", "",
              "| company | domain | obs | quarters with obs | coverage | first | last | sources |",
              "|---|---|---:|---:|---:|---|---|---|"]
    for row in payload["coverage"]["matrix"]:
        sources = ", ".join(f"{k}:{v}" for k, v in sorted(row["sources"].items())) if row["sources"] else "—"
        lines.append(f"| {row['company']} | {row['domain']} | {row['observations_in_window']} "
                     f"| {row['quarters_with_observation']}/{row['expected_quarters']} "
                     f"| {('%.0f%%' % (100 * row['quarter_coverage'])) if row['quarter_coverage'] is not None else '—'} "
                     f"| {row['first_observation'] or '—'} | {row['last_observation'] or '—'} | {sources} |")
    lines += ["", "## Evaluability against pre-declared floors", "",
              f"Floors: ≥{payload['evaluability']['floors']['min_observations']} observations and "
              f"≥{payload['evaluability']['floors']['min_quarters']} quarters with observation.", ""]
    for row in payload["evaluability"]["evaluable"]:
        lines.append(f"- **EVALUABLE** {row['company']} × {row['domain']} "
                     f"({row['observations']} obs, {row['quarters']} quarters)")
    for row in payload["evaluability"]["not_evaluable"]:
        lines.append(f"- not evaluable: {row['company']} × {row['domain']} — {row['reason']}")
    lines += ["", "## Sources and tiers", "",
              "| source | kind | observations | event date span | tier | why |", "|---|---|---:|---|---|---|"]
    for entry in payload["sources"].values():
        lines.append(f"| {entry['source']} | {entry['kind']} | {entry['observations']} "
                     f"| {entry['event_date_min']} .. {entry['event_date_max']} | "
                     f"**{entry['tier']}** | {'; '.join(entry['tier_reasons'])} |")
    lines += ["", "Tier definitions: A = verifiable first-publication time; B = conservative reconstruction from the "
              "event date with a declared lag; C = descriptive only; D = unavailable.", ""]
    path.write_text("\n".join(lines), encoding="utf-8", newline="\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--store", default=str(MAIN_STORE))
    parser.add_argument("--out-dir", default=str(OUT_DIR))
    parser.add_argument("--min-observations", type=int, default=40)
    parser.add_argument("--min-quarters", type=int, default=12)
    args = parser.parse_args(argv)

    store = Path(args.store)
    con = connect(store)
    if con is None:
        print(f"store not found: {store}")
        return 1

    roster = roster_status(con)
    observations = collect_observations(con, roster_only=False)
    roster_only = collect_observations(con, roster_only=True)
    coverage = aggregate_coverage(observations, window=WINDOW, domains=DOMAINS, firms=FIVE_FIRMS)
    coverage_roster = aggregate_coverage(roster_only, window=WINDOW, domains=DOMAINS, firms=FIVE_FIRMS)
    sources = source_inventory(con, store.name)
    con.close()

    by_resolution = {}
    for observation in observations:
        key = observation["resolved_by"]
        by_resolution[key] = by_resolution.get(key, 0) + 1

    payload = {
        "schema": "coverage_matrix_v1",
        "study": "early_signal_5firms",
        "directive": "RESEARCH DIRECTIVE 001 (Phase 0)",
        "store": str(store).replace("\\", "/"),
        "windows": {"historical": list(WINDOW)},
        "roster": roster,
        "resolution": by_resolution,
        "coverage": coverage,
        "coverage_roster_only": coverage_roster,
        "sources": sources,
        "evaluability": evaluability(coverage["matrix"], min_observations=args.min_observations,
                                     min_quarters=args.min_quarters),
    }
    evidence = {
        "schema": "evidence_time_audit_v1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source_tiers": {key: {"tier": entry["tier"], "reasons": entry["tier_reasons"]}
                         for key, entry in sources.items()},
        "first_seen_at_semantics": (
            "first_seen_at is written at collection time for these stores, so it records OUR fetch date, not the "
            "source's publication date; it therefore cannot be used as a publication timestamp"),
        "tier_b_assumptions_days": TIER_B_LAG_DAYS,
        "unresolved": [
            "no recorded per-record publication timestamp for openFDA bulk extracts: availability must be "
            "reconstructed from the event date with a declared lag and sensitivity analysis",
            "the roster has no company_key for draeger or mindray: their events are alias-resolved, which "
            "requires an entity-resolution audit before any firm-level claim",
            "procurement_awards in the research lane records announcement_date/award_date as NULL for all rows and "
            "data_quality says first_publication_unknown, so that source is Tier C for this study",
            "patents are absent from all frozen stores (upstream access blocked); no patent claim can be made",
            "publication_counts is annual, company-level and limited to 616 rows, so it cannot supply quarterly "
            "lead-time evidence",
        ],
        "clock": clock_audit(),
    }

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "COVERAGE_MATRIX.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    (out_dir / "EVIDENCE_TIME_AUDIT.json").write_text(
        json.dumps(evidence, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    write_markdown(out_dir / "COVERAGE_MATRIX.md", payload)

    print(f"store: {store}  ({sum(entry['observations'] for entry in sources.values())} events)")
    print(f"roster: " + ", ".join(f"{firm}={'key' if block['company_key_present'] else 'ALIAS-ONLY'}"
                                  for firm, block in roster.items()))
    print(f"resolution: {by_resolution}")
    print(f"evaluable cells: {payload['evaluability']['counts']['evaluable']} / "
          f"{len(payload['coverage']['matrix'])}")
    for row in payload["evaluability"]["evaluable"]:
        print(f"  EVALUABLE {row['company']:14s} {row['domain']:26s} {row['observations']:>5} obs "
              f"{row['quarters']:>3} quarters")
    print(f"clock: {evidence['clock']['system_local_now']} / {evidence['clock']['system_utc_now']} — "
          f"{evidence['clock']['conclusion']}")
    print(f"wrote {out_dir}/COVERAGE_MATRIX.json, EVIDENCE_TIME_AUDIT.json, COVERAGE_MATRIX.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
