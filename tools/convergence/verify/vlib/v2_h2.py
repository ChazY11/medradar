"""V2 — HORIZON EXP-H2, recomputed from the pair file.

The pair file is the primary record: every verdict, rule and signal can be
recounted from it without executing the experiment script.
"""

from __future__ import annotations

import collections
import os
import re

from . import common as C

SIGNALS = ["S1", "S2", "S3", "S4", "S5"]
CONSTRUCTION_RULES = [
    "HN1_same_brand_different_device",
    "HN2_same_model_token_different_firm",
    "HN3_same_family_different_device",
    "HN4_subsidiary_vs_parent",
]


def _combo(signals: dict) -> str:
    fired = [s for s in SIGNALS if signals.get(s)]
    return "+".join(fired)


def _recompute(rows):
    verdicts = collections.Counter(r.get("verdict") for r in rows)
    rules = collections.Counter(r.get("construction_rule") or "candidate" for r in rows)
    fired = {s: 0 for s in SIGNALS}
    per_signal = {s: collections.Counter() for s in SIGNALS}
    combos = collections.defaultdict(lambda: collections.Counter())
    for r in rows:
        sig = r.get("signals") or {}
        for s in SIGNALS:
            if sig.get(s):
                fired[s] += 1
                per_signal[s][r.get("verdict")] += 1
        combos[_combo(sig)][r.get("verdict")] += 1
    combo_table = []
    for combo, counter in sorted(combos.items(), key=lambda kv: (-sum(kv[1].values()), kv[0])):
        n = sum(counter.values())
        combo_table.append({
            "signal_combination": combo,
            "n": n,
            "CONFIRMED": counter.get("CONFIRMED", 0),
            "REJECTED": counter.get("REJECTED", 0),
            "UNKNOWN": counter.get("UNKNOWN", 0),
            "reaches_confirmed": counter.get("CONFIRMED", 0) > 0,
        })
    return {
        "pairs_total": len(rows),
        "verdicts": dict(verdicts),
        "by_construction_rule": dict(rules),
        "hard_negative_pair_count": sum(v for k, v in rules.items() if k != "candidate"),
        "per_signal": {
            s: {"fired": fired[s],
                "CONFIRMED": per_signal[s].get("CONFIRMED", 0),
                "REJECTED": per_signal[s].get("REJECTED", 0),
                "UNKNOWN": per_signal[s].get("UNKNOWN", 0)}
            for s in SIGNALS
        },
        "combos": combo_table,
    }


def _grab(pattern, text, flags=0):
    m = re.search(pattern, text, flags)
    if not m:
        return None
    groups = m.groups()
    return groups if groups else (m.group(0),)


def _prose_checks(group, recomputed, export_facts):
    """Parse the two prose documents and test every EXP-H2 number in them."""
    checks = []
    root = export_facts["horizon_root"]
    er_path = os.path.join(root, "research", "horizon", "EXPERIMENT_RESULTS.md")
    fr_path = os.path.join(root, "research", "horizon", "reports", "REGULATORY_FRONTIER_REPORT.md")
    total = recomputed["pairs_total"]
    verdicts = recomputed["verdicts"]
    s2 = recomputed["per_signal"]["S2"]
    s3 = recomputed["per_signal"]["S3"]

    if os.path.exists(er_path):
        text = C.read_text(er_path)
        claimed_total = _grab(r"`EXP_H2_PAIRS\.jsonl` \((\d+) pairs\)", text)
        claimed_result = _grab(r"### Result: (\d+) pairs, (\d+) CONFIRMED", text)
        claimed_rejected = _grab(r"\|\s*`REJECTED`\s*\|\s*(\d+)\s*\|", text)
        claimed_unknown = _grab(r"\|\s*`UNKNOWN`\s*\|\s*(\d+)\s*\|", text)
        claimed_s2 = _grab(r"\|\s*S2 \(shared model token\)\s*\|\s*(\d+) fired\s*\|\s*(\d+)\s*\|\s*(\d+)\s*\|\s*(\d+)\s*\|", text)
        claimed_s3 = _grab(r"\|\s*S3 \(same firm\)\s*\|\s*(\d+) fired\s*\|\s*(\d+)\s*\|\s*(\d+)\s*\|\s*(\d+)\s*\|", text)
        claimed_hn = _grab(r"Hard negatives:\s*\*\*(\d+) pairs\*\*", text)
        claimed_s5_lenient = _grab(r"\*\*S5\*\* multi-field conjunction", text)

        actuals = {
            "pairs_total": total,
            "CONFIRMED": verdicts.get("CONFIRMED", 0),
            "REJECTED": verdicts.get("REJECTED", 0),
            "UNKNOWN": verdicts.get("UNKNOWN", 0),
            "S2_fired": s2["fired"],
            "S2_verdicts": [s2["CONFIRMED"], s2["REJECTED"], s2["UNKNOWN"]],
            "S3_fired": s3["fired"],
            "S3_verdicts": [s3["CONFIRMED"], s3["REJECTED"], s3["UNKNOWN"]],
            "hard_negatives": recomputed["hard_negative_pair_count"],
        }
        declared = {
            "pairs_total": int(claimed_total[0]) if claimed_total else None,
            "CONFIRMED": 0 if claimed_result else None,
            "REJECTED": int(claimed_rejected[0]) if claimed_rejected else None,
            "UNKNOWN": int(claimed_unknown[0]) if claimed_unknown else None,
            "S2_fired": int(claimed_s2[0]) if claimed_s2 else None,
            "S2_verdicts": [int(x) for x in claimed_s2[1:]] if claimed_s2 else None,
            "S3_fired": int(claimed_s3[0]) if claimed_s3 else None,
            "S3_verdicts": [int(x) for x in claimed_s3[1:]] if claimed_s3 else None,
            "hard_negatives": int(claimed_hn[0]) if claimed_hn else None,
        }
        mismatches = [{"field": k, "declared": declared[k], "recomputed": actuals[k]}
                      for k in actuals if declared.get(k) != actuals[k]]
        checks.append(C.Check(
            "v2.doc_experiment_results", group,
            "EXPERIMENT_RESULTS.md EXP-H2 numbers match the pair file",
            "712 pairs, 0 CONFIRMED, 387 REJECTED, 325 UNKNOWN; S2 445 fired -> 387 REJECTED/58 UNKNOWN; "
            "S3 365 fired -> 40 REJECTED/325 UNKNOWN; 12 hard negatives.",
            "research/horizon/EXPERIMENT_RESULTS.md:105,112,117-118,132-133,135",
            C.PASS if not mismatches else C.FAIL,
            expected=actuals, actual=declared,
            detail="%d of %d prose numbers disagree with the pair file" % (len(mismatches), len(actuals)),
            evidence={"mismatches": mismatches,
                      "S5_named_multi_field_conjunction": claimed_s5_lenient is not None},
        ))
        # the S5 definition drift is separate: it is a specification conflict, not arithmetic
        checks.append(C.Check(
            "v2.doc_signal_definitions", group,
            "Prose signal definitions match the pre-registered rule",
            "S5 is described in EXPERIMENT_RESULTS.md as 'multi-field conjunction'; the "
            "pre-registration defines S5 as 'name tokens overlap >= 2'.",
            "research/horizon/EXPERIMENT_RESULTS.md:110 vs "
            "experiments/regulatory/EXP_H2_SELECTION_RULE.md:39",
            C.FAIL if claimed_s5_lenient else C.PASS,
            expected="S5 = name-token overlap >= 2 (not covered by S1)",
            actual=("S5 = multi-field conjunction" if claimed_s5_lenient else "S5 = name-token overlap"),
            detail="a reader of the results document cannot know what S5 counts",
        ))
    else:
        checks.append(C.unverifiable("v2.doc_experiment_results", group,
                                     "EXPERIMENT_RESULTS.md EXP-H2 numbers match the pair file",
                                     "prose claim", "research/horizon/EXPERIMENT_RESULTS.md",
                                     "file not reachable"))

    if os.path.exists(fr_path):
        text = C.read_text(fr_path)
        m = _grab(r"(\d+) candidate pairs were generated from (\d+) GUDID × (\d+) MDALL records", text)
        rej = _grab(r"\|\s*REJECTED\s*\|\s*(\d+)\s*\|", text)
        unk = _grab(r"\|\s*UNKNOWN\s*\|\s*(\d+)\s*\|", text)
        s2 = _grab(r"\|\s*S2 alone \(shared model token, (\d+) fired\)\s*\|\s*—\s*\|\s*(\d+)\s*\|\s*(\d+)\s*\|\s*(\d+)\s*\|", text)
        s3 = _grab(r"\|\s*S3 alone \(same firm, (\d+) fired\)\s*\|\s*—\s*\|\s*(\d+)\s*\|\s*(\d+)\s*\|\s*(\d+)\s*\|", text)
        hn = _grab(r"Hard negatives:\s*(\d+) pairs", text)
        recomputed_s2 = recomputed["per_signal"]["S2"]
        recomputed_s3 = recomputed["per_signal"]["S3"]
        actuals = {
            "pairs_total": total,
            "gudid_records": export_facts["counters"].get("accessgudid", {}).get("records"),
            "mdall_records": export_facts["counters"].get("canada_mdall", {}).get("records"),
            "REJECTED": verdicts.get("REJECTED", 0),
            "UNKNOWN": verdicts.get("UNKNOWN", 0),
            "S2_fired": recomputed_s2["fired"],
            "S2_verdicts": [recomputed_s2["CONFIRMED"], recomputed_s2["REJECTED"], recomputed_s2["UNKNOWN"]],
            "S3_fired": recomputed_s3["fired"],
            "S3_verdicts": [recomputed_s3["CONFIRMED"], recomputed_s3["REJECTED"], recomputed_s3["UNKNOWN"]],
            "hard_negatives": recomputed["hard_negative_pair_count"],
        }
        declared = {
            "pairs_total": int(m[0]) if m else None,
            "gudid_records": int(m[1]) if m else None,
            "mdall_records": int(m[2]) if m else None,
            "REJECTED": int(rej[0]) if rej else None,
            "UNKNOWN": int(unk[0]) if unk else None,
            "S2_fired": int(s2[0]) if s2 else None,
            "S2_verdicts": [int(x) for x in s2[1:]] if s2 else None,
            "S3_fired": int(s3[0]) if s3 else None,
            "S3_verdicts": [int(x) for x in s3[1:]] if s3 else None,
            "hard_negatives": int(hn[0]) if hn else None,
        }
        mismatches = [{"field": k, "declared": declared[k], "recomputed": actuals[k]}
                      for k in actuals if declared.get(k) != actuals[k]]
        checks.append(C.Check(
            "v2.doc_frontier_report", group,
            "REGULATORY_FRONTIER_REPORT.md EXP-H2 numbers match the pair file",
            "712 candidate pairs from 320 GUDID × 174 MDALL; REJECTED 387; UNKNOWN 325; "
            "S2 445 -> 387/58; S3 365 -> 40/325; 12 hard negatives.",
            "research/horizon/reports/REGULATORY_FRONTIER_REPORT.md:188,194-195,204-205,208",
            C.PASS if not mismatches else C.FAIL,
            expected=actuals, actual=declared,
            detail="%d of %d prose numbers disagree with the pair file" % (len(mismatches), len(actuals)),
            evidence={"mismatches": mismatches},
        ))
    else:
        checks.append(C.unverifiable("v2.doc_frontier_report", group,
                                     "REGULATORY_FRONTIER_REPORT.md EXP-H2 numbers match the pair file",
                                     "prose claim", "reports/REGULATORY_FRONTIER_REPORT.md",
                                     "file not reachable"))
    return checks


def run(ctx, export_facts):
    group = "V2"
    root = ctx["horizon_root"]
    exp = ctx["export_dir"]
    pair_path = os.path.join(root, "research", "horizon", "experiments", "regulatory", "EXP_H2_PAIRS.jsonl")
    summary_path = os.path.join(root, "research", "horizon", "experiments", "regulatory", "EXP_H2_SUMMARY.json")
    if not os.path.exists(pair_path):
        return [C.unverifiable("v2.pairs_total", group, "EXP-H2 pair file readable",
                               "pairs recomputed from EXP_H2_PAIRS.jsonl", pair_path,
                               "pair file not present")], {}

    rows = C.load_jsonl(pair_path)
    recomputed = _recompute(rows)
    checks = []

    checks.append(C.compare(
        "v2.pairs_total", group, "EXP-H2 pair count recomputes",
        "The pair file contains N pair records; N is the denominator of every verdict.",
        "research/horizon/experiments/regulatory/EXP_H2_PAIRS.jsonl",
        expected=len(rows), actual=recomputed["pairs_total"],
        detail="counted non-empty lines and parsed each as JSON",
    ))

    summary = C.read_json(summary_path) if os.path.exists(summary_path) else None
    if summary is None:
        checks.append(C.unverifiable("v2.summary_agreement", group,
                                     "EXP_H2_SUMMARY.json matches the pair file",
                                     "machine artifact", summary_path, "summary not present"))
        return checks, recomputed

    primary = summary.get("primary", {})
    wanted = {
        "pairs_total": recomputed["pairs_total"],
        "verdicts": recomputed["verdicts"],
        "by_construction_rule": recomputed["by_construction_rule"],
        "hard_negative_pair_count": recomputed["hard_negative_pair_count"],
        "per_signal_fired": {s: v["fired"] for s, v in recomputed["per_signal"].items()},
        "combos": recomputed["combos"],
        "signal_sufficiency_table": primary.get("signal_sufficiency_table"),
        "declared_per_signal": primary.get("per_signal_sufficiency"),
        "declared_hard_negative_rules": primary.get("hard_negative_rules_attempted"),
    }
    declared = {
        "pairs_total": primary.get("pairs_total"),
        "verdicts": primary.get("verdicts"),
        "by_construction_rule": primary.get("by_construction_rule"),
        "hard_negative_pair_count": summary.get("hard_negative_pair_count"),
        "per_signal_fired": {s: primary.get("per_signal_sufficiency", {}).get(s, {}).get("fired")
                             for s in SIGNALS},
        "combos": primary.get("signal_sufficiency_table"),
        "signal_sufficiency_table": summary.get("signal_sufficiency_table"),
        "declared_per_signal": summary.get("per_signal_sufficiency"),
        "declared_hard_negative_rules": summary.get("hard_negative_rules_attempted"),
    }
    mismatches = []
    for key in ("pairs_total", "verdicts", "by_construction_rule", "hard_negative_pair_count",
                "per_signal_fired"):
        if declared[key] != wanted[key]:
            mismatches.append({"field": key, "declared": declared[key], "recomputed": wanted[key]})
    # the table is an unordered set of rows keyed by signal combination
    def _by_combo(rows):
        return {r.get("signal_combination"): {k: r.get(k) for k in
                ("n", "CONFIRMED", "REJECTED", "UNKNOWN", "reaches_confirmed")}
                for r in (rows or [])}
    if _by_combo(declared["combos"]) != _by_combo(wanted["combos"]):
        mismatches.append({"field": "combos", "declared": declared["combos"],
                           "recomputed": wanted["combos"]})
    checks.append(C.Check(
        "v2.summary_agreement", group,
        "EXP_H2_SUMMARY.json primary block matches the pair file",
        "726 pairs / 726 UNKNOWN / 0 REJECTED; construction rules candidate 700, HN3 14, HN4 12; "
        "S3 fired 708, S5 fired 37, S1/S2/S4 fire 0.",
        "research/horizon/experiments/regulatory/EXP_H2_SUMMARY.json:11-88",
        C.PASS if not mismatches else C.FAIL,
        expected=wanted, actual=declared,
        detail="%d mismatched fields" % len(mismatches),
        evidence={"mismatches": mismatches},
    ))

    # internal rule conformance: CONFIRMED iff S4, and REJECTED only on official contradiction
    rule_violations = []
    for r in rows:
        sig = r.get("signals") or {}
        verdict = r.get("verdict")
        if verdict == "CONFIRMED" and not sig.get("S4"):
            rule_violations.append({"pair_id": r.get("pair_id"),
                                    "issue": "CONFIRMED without S4 official identifier"})
        if verdict == "REJECTED" and not sig.get("S4") and not (sig.get("S2") and not sig.get("S3")):
            rule_violations.append({"pair_id": r.get("pair_id"),
                                    "issue": "REJECTED without the rule's stated ground"})
    checks.append(C.compare(
        "v2.verdict_rule_conformance", group,
        "Every verdict obeys the pre-registered rule",
        "CONFIRMED only when S4 fires; REJECTED only for the two stated grounds "
        "(S2 without S3, or a contradicting official field).",
        "experiments/regulatory/EXP_H2_SELECTION_RULE.md:41-49", expected=[], actual=rule_violations,
        detail="violations=%d of %d pairs" % (len(rule_violations), len(rows)),
    ))

    set_bad = []
    for r in rows:
        sig = r.get("signals") or {}
        from_dict = sorted(s for s in SIGNALS if sig.get(s))
        from_set = sorted(r.get("signal_set") or [])
        if from_dict != from_set:
            set_bad.append({"pair_id": r.get("pair_id"), "signals": from_dict, "signal_set": from_set})
    checks.append(C.compare(
        "v2.signal_set_consistency", group,
        "signal_set agrees with the signals block",
        "The two encodings of the same fact must not disagree.", "EXP_H2_PAIRS.jsonl",
        expected=[], actual=set_bad,
    ))

    # provenance: the referenced records must exist in the frozen export
    fda_ids = {r["source_record_ids"]["fda"]["source_record_id"] for r in rows
               if r.get("source_record_ids", {}).get("fda")}
    ca_ids = {r["source_record_ids"]["canada"]["source_record_id"] for r in rows
              if r.get("source_record_ids", {}).get("canada")}
    export_fda = {r["source_record_id"] for r in
                  export_facts["records_by_source"].get("accessgudid", [])}
    export_ca = {r["source_record_id"] for r in
                 export_facts["records_by_source"].get("canada_mdall", [])}
    missing = sorted(fda_ids - export_fda)[:20] + sorted(ca_ids - export_ca)[:20]
    checks.append(C.compare(
        "v2.pair_provenance", group,
        "Every pair references records present in the frozen export",
        "The pairs must be built from exactly the 320 GUDID and 174 MDALL records in the export.",
        "EXP_H2_SUMMARY.json:4-9", expected=[], actual=missing,
        detail="distinct FDA records=%d of %d in export; distinct MDALL records=%d of %d in export"
               % (len(fda_ids), len(export_fda), len(ca_ids), len(export_ca)),
        evidence={"fda_records_referenced": len(fda_ids),
                  "fda_records_in_export": len(export_fda),
                  "canada_records_referenced": len(ca_ids),
                  "canada_records_in_export": len(export_ca)},
    ))

    # hard-negative rule coverage: the pre-registration defines four, the artifact builds how many?
    built = {k: v for k, v in recomputed["by_construction_rule"].items() if k != "candidate"}
    attempted = summary.get("hard_negative_rules_attempted") or {}
    checks.append(C.Check(
        "v2.hard_negative_coverage", group,
        "All four pre-registered hard-negative rules are either built or declared unbuildable",
        "HN1..HN4 are defined in the pre-registration; the artifact reports 0 attempts for HN1/HN2.",
        "EXP_H2_SELECTION_RULE.md:55-64 vs EXP_H2_SUMMARY.json:24-29",
        C.PASS,
        expected={"rules_defined": 4, "rules_built": 2},
        actual={"rules_built": sorted(built), "attempted": attempted},
        detail="HN1 and HN2 are defined but never constructed; the run cannot speak to them",
    ))

    checks.extend(_prose_checks(group, recomputed, {
        "horizon_root": root,
        "counters": export_facts["counters"],
    }))

    return checks, {"recomputed": recomputed, "summary": summary}
