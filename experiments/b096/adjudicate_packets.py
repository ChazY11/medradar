"""Apply the agent pre-adjudication rubric to all 69 packets (ADJUDICATION_AMENDMENT_002.md).

For each packet: pull the referenced trial text and product-code mapping from the frozen store (read-only), score R1/R2/R3,
apply the frozen rule table, and record the evidence and the preliminary label. Human fields are untouched.

Emits ADJUDICATION_AGENT_V1.json / .md. Nothing here is human truth, and nothing here may be used to score the study's
detectors.

    python experiments/b096/adjudicate_packets.py
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from medradar.studies.adjudication import (  # noqa: E402
    RUBRIC_VERSION,
    TIER,
    device_relevance,
    relevance_from_mapping,
    preliminary_label,
    summarise,
    taxonomy_consistency,
    third_source_strength,
)

STUDY = Path("research/studies/early_signal_5firms")
STORE = Path("D:/DEPPSKK/medradar/data/medradar.sqlite")
CANDIDATES = STUDY / "CASE_CANDIDATES.json"
SMALL = STUDY / "CASE_PACKETS_SMALL_SAMPLE_V2.json"


def track_keywords(con: sqlite3.Connection, track: str) -> list[str]:
    row = con.execute("select keywords from tracks where id = ?", (track,)).fetchone()
    if not row or not row[0]:
        return []
    try:
        return [str(item) for item in json.loads(row[0]) or []]
    except (TypeError, ValueError):
        return []


def trial_text(con: sqlite3.Connection, event_id: str | None) -> str:
    if not event_id:
        return ""
    row = con.execute("select payload from events where event_id = ?", (event_id,)).fetchone()
    if not row or not row[0]:
        return ""
    data = json.loads(row[0])
    conditions = data.get("conditions") or []
    return " ".join([str(item) for item in conditions] + [str(data.get("brief_title") or ""),
                                                          str(data.get("brief_summary") or "")])


def product_track(con: sqlite3.Connection, product_code: str | None) -> str | None:
    if not product_code:
        return None
    row = con.execute("select track_id from product_codes where product_code = ?",
                      (product_code,)).fetchone()
    return row[0] if row else None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", default=str(STUDY))
    args = parser.parse_args(argv)

    con = sqlite3.connect(f"file:{STORE}?mode=ro", uri=True)
    rows: list[dict] = []

    candidates = json.loads(CANDIDATES.read_text(encoding="utf-8"))["cases"]
    for packet in candidates:
        track = str(packet["technology_track"])
        keywords = track_keywords(con, track)
        event_id = (packet.get("evidence") or {}).get("event_id")
        text = trial_text(con, event_id)
        # regulatory packets carry no trial text: relevance comes from the product code's own track mapping
        mapped = product_track(con, (packet.get("evidence") or {}).get("product_code"))
        relevance = relevance_from_mapping(track, mapped)
        consistency = taxonomy_consistency(track, mapped)
        verdict = preliminary_label(relevance=relevance, consistency=consistency,
                                    third_source="NOT_CHECKED",
                                    stratum=packet.get("stratum_by_gap_rule"))
        rows.append({
            "packet_id": packet["case_id"], "origin": "candidate",
            "company": packet["company"], "track": track,
            "stratum": packet.get("stratum_by_gap_rule"),
            "rules": {"R1_device_relevance": relevance, "R2_taxonomy_consistency": consistency,
                      "R3_third_source": "NOT_CHECKED"},
            "agent_preliminary_label": verdict["label"], "rule_fired": verdict["rule"],
            "human_review_status": "PENDING_HUMAN_REVIEW", "final_label": None,
        })

    small = json.loads(SMALL.read_text(encoding="utf-8"))["packets"]
    for packet in small:
        track = str(packet["technology_track"])
        keywords = track_keywords(con, track)
        trial_id = ((packet.get("representative_trial") or {}).get("id"))
        text = trial_text(con, trial_id)
        relevance = device_relevance(text, keywords)
        consistency = taxonomy_consistency(track, None)   # synthetic clearance id: no product code
        strength = third_source_strength(packet.get("third_source"))
        verdict = preliminary_label(relevance=relevance, consistency=consistency,
                                    third_source=strength)
        rows.append({
            "packet_id": packet["event_id"], "origin": "small_sample",
            "company": packet["company"], "track": track, "stratum": None,
            "rules": {"R1_device_relevance": relevance,
                      "R2_taxonomy_consistency": consistency,
                      "R3_third_source": strength},
            "agent_preliminary_label": verdict["label"], "rule_fired": verdict["rule"],
            "human_review_status": "PENDING_HUMAN_REVIEW", "final_label": None,
        })
    con.close()

    summary = summarise(rows)
    payload = {
        "schema": "adjudication_agent_v1",
        "tier": TIER,
        "rubric_version": RUBRIC_VERSION,
        "amendment": "ADJUDICATION_AMENDMENT_002.md",
        "authorisation": ("project owner instructed the agent to adjudicate the packets (2026-11-03); this tier exists "
                          "because the study forbids the agent from producing human truth"),
        "generated_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "packets_assessed": len(rows),
        "summary": summary,
        "meaning": {
            "agent_preliminary_label": "how a fixed text/mapping rubric classifies the packet",
            "not_human_truth": ("these labels may not be used as ground truth, may not score the study's detectors, "
                                "and must be redone by a named human before any Target B claim"),
            "human_review_status": "still PENDING_HUMAN_REVIEW on every packet",
        },
        "rows": rows,
    }
    out_dir = Path(args.out_dir)
    (out_dir / "ADJUDICATION_AGENT_V1.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")

    lines = ["# AGENT PRE-ADJUDICATION OF THE 69 PACKETS — not human truth", "",
             f"**Tier `{TIER}` · rubric `{RUBRIC_VERSION}` · amendment `ADJUDICATION_AMENDMENT_002.md`.** Authorised by the "
             f"owner's instruction to adjudicate the packets; created because the study forbids the agent from producing "
             f"human truth.", "",
             f"Packets assessed: **{len(rows)}**. Human fields untouched: every packet is still "
             f"`PENDING_HUMAN_REVIEW` with `final_label = null`.", "",
             "**What these numbers are not.** They are not human labels, they may not be used as ground truth, and they "
             "may not be used to score the study's own detectors — doing so would be the circularity this programme "
             "already retracted once (a post-hoc nomination evaluated on the data that produced it).", "",
             "## Distribution", "", "| preliminary label | packets |", "|---|---:|"]
    for label, count in sorted(summary["counts"].items(), key=lambda item: -item[1]):
        lines.append(f"| {label} | {count} |")
    lines += ["", "## Rules that fired", "", "| rule | packets |", "|---|---:|"]
    for rule, count in sorted(summary["rules"].items(), key=lambda item: -item[1]):
        lines.append(f"| {rule} | {count} |")
    lines += ["", "## Per packet", "",
              "| packet | origin | firm | track | R1 | R2 | R3 | preliminary label |",
              "|---|---|---|---|---|---|---|---|"]
    for row in rows:
        rules = row["rules"]
        lines.append(f"| {row['packet_id']} | {row['origin']} | {row['company']} | {row['track']} | "
                     f"{rules['R1_device_relevance'].get('score')} | {rules['R2_taxonomy_consistency']} | "
                     f"{rules['R3_third_source']} | {row['agent_preliminary_label']} |")
    (out_dir / "ADJUDICATION_AGENT_V1.md").write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")

    print(f"packets assessed: {len(rows)}")
    print(f"labels: {summary['counts']}")
    print(f"rules: {summary['rules']}")
    print(f"wrote {out_dir}/ADJUDICATION_AGENT_V1.{{json,md}}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
