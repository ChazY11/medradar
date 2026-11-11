#!/usr/bin/env python
"""Check that the numbers quoted in the documentation match the machine results.

A scientific report drifts from its data the moment someone edits prose without
re-running the pipeline.  This checker makes that drift a build failure.

Documents declare the numbers they quote inside a fenced comment…

    <!-- convergence:numbers
    records_read=5884
    rejected=0
    -->

…and this script recomputes the authoritative value for every declared key from
the machine reports and fails on any mismatch, any unknown key, and any declared
number that the reports no longer support.  It also cross-checks the EXP-H2
figures against the H2 consistency gate's own recomputation, so the H2 report
cannot drift either.

Usage:
    python tools/convergence/check_report_consistency.py
    python tools/convergence/check_report_consistency.py --json
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DOCS = REPO_ROOT / "docs/convergence"
REPORTS = REPO_ROOT / "research/convergence/reports"
BLOCK_RE = re.compile(r"<!--\s*convergence:numbers\s*(.*?)-->", re.DOTALL)


def _latest(pattern: str) -> Path | None:
    """Newest report matching the pattern, ignoring test-slice reports."""
    ignore = ("integration_det_", "integration_e2e_test", "integration_experiments")
    candidates = [
        path
        for path in REPORTS.glob(pattern)
        if not any(token in path.name for token in ignore)
    ]
    candidates.sort(key=lambda p: p.stat().st_mtime)
    return candidates[-1] if candidates else None


def _truth() -> dict[str, int | float | str]:
    """Authoritative values, recomputed from the machine reports."""
    truth: dict[str, int | float | str] = {}
    experiments_path = REPORTS / "integration_experiments.json"
    if experiments_path.exists():
        exp = json.loads(experiments_path.read_text(encoding="utf-8"))
        c1, c2, c3, c4, c5 = (exp["EXP-C1"], exp["EXP-C2"], exp["EXP-C3"], exp["EXP-C4"], exp["EXP-C5"])
        truth.update(
            {
                "c1_input_records": c1["input_records"],
                "c1_converted": c1["outcomes"].get("converted", 0),
                "c1_degraded": c1["outcomes"].get("degraded", 0),
                "c1_rejected": c1["rejected_records"],
                "c1_fields_dropped_silently": c1["fields_dropped_silently"],
                "c1_declared_source_fields": c1["declared_source_fields"],
                "c1_fields_with_atlas_home": c1["fields_with_atlas_home"],
                "c1_fields_preserved_losslessly": c1["fields_preserved_losslessly"],
                "c1_gtin14_promotions": c1["gtin14_promotions"],
                "c2_mdall_identifiers": c2["horizon_mdall_device_identifiers"],
                "c2_mdall_gtin14_valid": c2["horizon_mdall_gtin14_valid"],
                "c2_gudid_udi_di": c2["horizon_gudid_udi_di_distinct"],
                "c2_overlap": c2["overlap_horizon_mdall_vs_gudid"],
                "c2_confirmed_cross_border": c2["confirmed_cross_border_relations_in_staging"],
                "c3_records_read": c3["records_read"],
                "c3_distinct_evidence": c3["distinct_evidence_ids"],
                "c3_evidence_versions": c3["evidence_versions"],
                "c3_repeat_observations": c3["repeat_observations_of_same_record"],
                "c4_records": c4["records"],
                "c4_usable_for_lead_time": c4["records_usable_for_lead_time"],
                "c4_not_usable": c4["records_not_usable_for_historical_analysis"],
                "c4_without_first_observation": c4["records_without_first_observation"],
                "c4_public_before_event": c4["public_before_event"],
                "c4_date_conflicts": c4["cross_source_publication_date_conflicts"],
                "c5_cited_items": c5["cited_items"],
                "c5_uncited_items": c5["uncited_items"],
                "c5_db_mb": c5["staging_db_mb"],
            }
        )
    integration_path = _latest("integration_*.json")
    if integration_path:
        report = json.loads(integration_path.read_text(encoding="utf-8"))
        truth.update(
            {
                "integrity_verified": report["integrity"]["state_counts"].get("verified", 0),
                "integrity_quarantined": report["integrity"]["state_counts"].get("quarantined", 0),
                "integrity_mismatch": report["integrity"]["state_counts"].get("mismatch", 0),
                "import_seen": report["import"]["seen"],
                "import_rejected": report["import"]["rejected"],
                "authoritative_links": report["graph"]["authoritative_links"]["created"],
                "company_links": report["graph"]["company_links"]["links"],
                "atlas_relations": report["graph"]["atlas_relations_total"],
                "declared_sources": report["integrity"]["declared_sources"],
                "declared_records": report["integrity"]["declared_records"],
            }
        )
        truth["permitted_records"] = (
            report["integrity"]["declared_records"] - report["import"]["seen"]
        ) if report["integrity"].get("declared_records") else 0
    h2_summary = REPO_ROOT / "research/horizon/experiments/regulatory/EXP_H2_SUMMARY.json"
    if h2_summary.exists():
        h2 = json.loads(h2_summary.read_text(encoding="utf-8"))
        truth.update(
            {
                "h2_pairs": h2["primary"]["pairs_total"],
                "h2_confirmed": h2["primary"]["verdicts"].get("CONFIRMED", 0),
                "h2_rejected": h2["primary"]["verdicts"].get("REJECTED", 0),
                "h2_unknown": h2["primary"]["verdicts"].get("UNKNOWN", 0),
                "h2_hard_negatives": h2["primary"]["pairs_hard_negative"],
                "h2_s4_fired": h2["per_signal_sufficiency"]["S4"]["fired"],
            }
        )
    return truth


def _run_h2_gate() -> tuple[bool, str]:
    gate = REPO_ROOT / "tools/convergence/h2/check_h2_consistency.py"
    if not gate.exists():
        return False, "h2 gate missing"
    proc = subprocess.run(
        [sys.executable, str(gate)], capture_output=True, text=True, timeout=600
    )
    tail = (proc.stdout or "").strip().splitlines()[-3:]
    return proc.returncode == 0, " | ".join(tail)


def check() -> dict:
    truth = _truth()
    problems: list[str] = []
    checked: list[dict] = []
    if not truth:
        problems.append("no machine reports found; run the pipeline and experiments first")
    for doc in sorted(DOCS.glob("*.md")):
        text = doc.read_text(encoding="utf-8")
        for match in BLOCK_RE.finditer(text):
            body = match.group(1)
            line_no = text[: match.start()].count("\n") + 1
            for raw in body.splitlines():
                line = raw.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" not in line:
                    problems.append(f"{doc.name}:{line_no}: malformed claim {line!r}")
                    continue
                key, _, value = line.partition("=")
                key, value = key.strip(), value.strip()
                if key not in truth:
                    problems.append(f"{doc.name}:{line_no}: unknown claim key {key!r}")
                    continue
                expected = truth[key]
                try:
                    actual = float(value)
                except ValueError:
                    problems.append(f"{doc.name}:{line_no}: non-numeric claim {key}={value!r}")
                    continue
                ok = abs(float(expected) - actual) < 1e-9
                checked.append(
                    {"doc": doc.name, "line": line_no, "key": key, "quoted": actual, "truth": expected, "ok": ok}
                )
                if not ok:
                    problems.append(
                        f"{doc.name}:{line_no}: {key} quoted {value} but truth is {expected}"
                    )
    h2_ok, h2_note = _run_h2_gate()
    if not h2_ok:
        problems.append(f"EXP-H2 consistency gate failed: {h2_note}")
    return {
        "status": "consistent" if not problems else "inconsistent",
        "claims_checked": len(checked),
        "problems": problems,
        "h2_gate": {"ok": h2_ok, "note": h2_note},
        "claims": checked,
        "truth_keys": sorted(truth),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    result = check()
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=1))
    else:
        print(f"claims checked: {result['claims_checked']}")
        print(f"EXP-H2 gate: {'PASS' if result['h2_gate']['ok'] else 'FAIL'} — {result['h2_gate']['note']}")
        for problem in result["problems"]:
            print(f"  PROBLEM: {problem}")
        print(f"RESULT: {result['status'].upper()}")
    return 0 if result["status"] == "consistent" else 1


if __name__ == "__main__":
    raise SystemExit(main())
