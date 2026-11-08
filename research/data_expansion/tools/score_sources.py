#!/usr/bin/env python
"""Score data sources against the frozen rubric.

Inputs
------
``registry/source_scores.json`` — per-source, per-dimension ratings (0-4) with a
one-line justification each.  Ratings are authored from the register record and
the probe evidence, never from record volume.
``registry/../GLOBAL_DATA_SOURCE_REGISTER.json`` — connection status.
``experiments/exp_a/EXP_A.json`` (optional) — EXP-A verdict per source.

Output
------
A ranked table with the weighted score and the assigned category, plus the
precondition checks that forced a downgrade.  The tool refuses to award
``ADOPT NOW`` to a source that is not verified or has no EXP-A verdict.

    python research/data_expansion/tools/score_sources.py --check
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parents[1]
sys.path.insert(0, str(REPO))

RUBRIC = ROOT / "registry" / "SOURCE_SCORING_RUBRIC.json"
SCORES = ROOT / "registry" / "source_scores.json"
REGISTER = ROOT / "GLOBAL_DATA_SOURCE_REGISTER.json"
EXP_A = ROOT / "experiments" / "exp_a" / "EXP_A.json"


def load_json(path: Path, default=None):
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def weighted_score(ratings: dict, rubric: dict) -> tuple[float, list[str]]:
    problems: list[str] = []
    lo = int(rubric.get("scale", {}).get("min", 0))
    hi = int(rubric.get("scale", {}).get("max", 4))
    total = 0.0
    for dim in rubric["dimensions"]:
        key = dim["id"]
        if key not in ratings:
            problems.append(f"missing rating for {key}")
            continue
        raw = ratings[key]
        value = raw["score"] if isinstance(raw, dict) else raw
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            problems.append(f"{key}: rating is not a number: {value!r}")
            continue
        if not (lo <= float(value) <= hi):
            problems.append(f"{key}: rating out of range [{lo},{hi}]: {value!r}")
            continue
        effective = (hi - float(value)) if dim["direction"] == "negative" else float(value)
        total += float(dim["weight"]) * (effective / float(hi))
    return round(total * 100, 2), problems


def assign_category(score: float, status: str, exp_a: str | None, rubric: dict) -> tuple[str, list[str]]:
    cats = rubric["categories"]
    reasons: list[str] = []
    adopt = cats["ADOPT NOW"]
    if status in adopt["requires_status"] and score >= adopt["min_score"]:
        if exp_a == adopt["requires_exp_a"]:
            return "ADOPT NOW", reasons
        reasons.append(f"EXP-A not INCREMENTAL ({exp_a or 'missing'}) -> cannot ADOPT NOW")

    if status in {"VERIFIED_API", "VERIFIED_BULK_DOWNLOAD", "VERIFIED_PUBLIC_QUERY"}:
        if score >= cats["PILOT"]["min_score"]:
            return "PILOT", reasons
        if score >= cats["RESEARCH ONLY"]["min_score"]:
            return "RESEARCH ONLY", reasons
    if status == "PAID_ONLY":
        if score >= cats["COMMERCIAL CANDIDATE"]["min_score"]:
            return "COMMERCIAL CANDIDATE", reasons
        return "REJECT", reasons + ["paid and low value"]
    if status in {"BLOCKED_BY_POLICY", "REQUIRES_REGISTRATION"}:
        return "BLOCKED", reasons
    if score < cats["REJECT"]["max_score"]:
        return "REJECT", reasons
    return "RESEARCH ONLY", reasons + ["unverified access; treated as research-only until probed"]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json-out", default=str(ROOT / "registry" / "source_priority_scores.json"))
    parser.add_argument("--check", action="store_true", help="validate inputs, do not write")
    args = parser.parse_args(argv)

    rubric = load_json(RUBRIC)
    if rubric is None:
        print(f"missing rubric: {RUBRIC}", file=sys.stderr)
        return 1
    scores = load_json(SCORES, {"sources": {}})
    register = load_json(REGISTER, {"sources": []})
    exp_a = load_json(EXP_A, {})
    status_by_source = {r["source_id"]: r.get("connection_status", "NOT_TESTED") for r in register.get("sources", [])}
    exp_a_by_source = (exp_a or {}).get("verdicts", {})

    rows = []
    problems: list[str] = []
    for source_id, entry in sorted(scores.get("sources", {}).items()):
        ratings = entry.get("ratings", {})
        score, dim_problems = weighted_score(ratings, rubric)
        problems.extend(f"{source_id}: {p}" for p in dim_problems)
        status = status_by_source.get(source_id, "NOT_TESTED")
        category, reasons = assign_category(score, status, exp_a_by_source.get(source_id), rubric)
        rows.append(
            {
                "source_id": source_id,
                "score": score,
                "category": category,
                "connection_status": status,
                "exp_a": exp_a_by_source.get(source_id, "NOT_RUN"),
                "downgrade_reasons": reasons,
                "ratings": {k: (v["score"] if isinstance(v, dict) else v) for k, v in ratings.items()},
                "justification": {k: (v.get("why", "") if isinstance(v, dict) else "") for k, v in ratings.items()},
            }
        )
    rows.sort(key=lambda r: (-r["score"], r["source_id"]))
    unregistered = sorted(set(scores.get("sources", {})) - set(status_by_source))
    if unregistered:
        problems.extend(f"scored but not in register: {s}" for s in unregistered)

    payload = {
        "schema": "medradar.external.priority_scores.v1",
        "rubric_frozen_at": rubric.get("frozen_at"),
        "weight_sum": round(sum(d["weight"] for d in rubric["dimensions"]), 6),
        "n_sources_scored": len(rows),
        "problems": problems,
        "rows": rows,
    }
    if args.check:
        for p in problems:
            print(f"PROBLEM: {p}", file=sys.stderr)
        print(json.dumps({r["category"]: sum(1 for x in rows if x["category"] == r["category"]) for r in rows}, indent=2))
        return 1 if problems else 0

    out = Path(args.json_out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"wrote {out}: {len(rows)} sources")
    for row in rows:
        flag = f"  [{'; '.join(row['downgrade_reasons'])}]" if row["downgrade_reasons"] else ""
        print(f"  {row['score']:6.2f}  {row['category']:<22} {row['source_id']}{flag}")
    if problems:
        print(f"\n{len(problems)} input problems", file=sys.stderr)
        for p in problems[:20]:
            print(f"  - {p}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
