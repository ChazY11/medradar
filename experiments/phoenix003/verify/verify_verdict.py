"""STEP 5 — independent recomputation of the mechanical verdict.

Inputs: FROZEN_RULES.json verdict/pilot sections, the recomputed k / share>=90 (verify_links,
both title readings), the committed c_controls specificity and placebo p (which are themselves
recomputed where possible from the committed link / decoy rows), and the committed verdict.json.

The verdict tree is re-implemented from the frozen text; the published verdict is then compared
gate by gate and the alternative readings are quantified.

Run:  python experiments/phoenix003/verify/verify_verdict.py
"""
from __future__ import annotations

import collections
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import vcommon as vc

OUT = Path(__file__).resolve().parent / "out_verdict.json"


def main():
    rules = vc.load_json(vc.EXP / "FROZEN_RULES.json")
    anchors = vc.committed_anchors()
    links = vc.committed_links()
    b = vc.result_json("b_links.json")
    c = vc.result_json("c_controls.json")
    b2 = vc.result_json("b2_novelty.json")
    verdict = vc.result_json("verdict.json")
    mine_links = vc.load_json(Path(__file__).resolve().parent / ("out_links.json" if vc.MODE == "live" else "out_links_snapshot.json"))

    n_anchors = len(anchors)
    print("=" * 78)
    print("VERDICT RECOMPUTATION")
    print("=" * 78)
    print(f"anchors n = {n_anchors}")

    # ---------------------------------------------------------------- k / share90 / firms
    verified = [r for r in links if r["tier"] in ("VERIFIED_L1", "VERIFIED_L2")]
    by_anchor = collections.defaultdict(list)
    for r in verified:
        by_anchor[r["anchor_id"]].append(r)
    k = len(by_anchor)
    adate = {a["anchor_id"]: vc.parse_date(a["anchor_date"]) for a in anchors}
    lead = {}
    for aid, rows in by_anchor.items():
        dates = sorted(vc.parse_date(r["evidence_date"]) for r in rows if r["evidence_date"])
        lead[aid] = (adate[aid] - dates[0]).days
    vals = sorted(lead.values())
    share90 = sum(1 for v in vals if v >= 90) / len(vals)
    firms = sorted({a["firm"] for a in anchors if a["anchor_id"] in by_anchor})
    years = sorted({a["anchor_year"] for a in anchors if a["anchor_id"] in by_anchor})
    print(f"recomputed from committed links: k={k} share_ge_90={share90:.6f} firms={firms} years={years}")

    k_full = mine_links["protocol_fields"]["k"]
    share90_full = mine_links["protocol_fields"]["stats"]["share_ge_90"]
    k_brief = mine_links["author_fields"]["k"]
    share90_brief = mine_links["author_fields"]["stats"]["share_ge_90"]
    print(f"independent reproductions     : BRIEF k={k_brief} share90={share90_brief} | "
          f"FULL(protocol title) k={k_full} share90={share90_full}")

    # --------------------------------------------------------- specificity and placebo p
    spec = c["c3_decoy"]["specificity"]
    decoy_rows = c["c3_decoy_rows"]
    decoy_linked = sum(1 for r in decoy_rows if r["decoy_linked"])
    decoy_n = len(decoy_rows)
    real_rate = k / n_anchors
    decoy_rate = decoy_linked / decoy_n if decoy_n else None
    spec_arith = (real_rate / decoy_rate) if decoy_rate else None
    matched_real = sum(1 for aid in by_anchor
                       if any(r["anchor_id"] == aid for r in decoy_rows)) if False else None
    decoy_anchor_ids = {r["anchor_id"] for r in decoy_rows}
    real_rate_matched = (sum(1 for aid in by_anchor if aid in decoy_anchor_ids)
                         / len(decoy_anchor_ids)) if decoy_anchor_ids else None
    spec_matched = (real_rate_matched / decoy_rate) if decoy_rate else None
    p_placebo = c["c4b_date_permutation"]["p_median_lead"]
    print(f"\nspecificity committed field      : {spec}")
    print(f"  recomputed arithmetic          : real={k}/{n_anchors}={real_rate:.6f} / "
          f"decoy={decoy_linked}/{decoy_n}={decoy_rate:.6f} = {spec_arith:.4f}")
    print(f"  matched-denominator variant    : real={real_rate_matched:.6f} / decoy={decoy_rate:.6f}"
          f" = {spec_matched:.4f}")
    print(f"  staleness: c3_decoy.specificity_note says decoy link rate is zero / specificity null,")
    print(f"  but the same object carries decoy_link_rate={c['c3_decoy']['decoy_link_rate']} "
          f"and specificity={spec}  -> the note contradicts the values.")
    print(f"placebo p (c4b)                  : {p_placebo}  (draws={c['c4b_date_permutation']['draws']};"
          f" FROZEN_RULES controls.c4_placebo.permutations={rules['controls']['c4_placebo']['permutations']})")

    # --------------------------------------------------------------- BLOCKED evaluation
    cov = b["anchors"]['anchor_summaries'] if isinstance(b.get("anchors"), dict) else None
    summ = {s["anchor_id"]: s for s in b["anchor_summaries"]}
    anchors_with_evidence = sum(1 for s in b["anchor_summaries"] if s["evidence_in_window"] > 0)
    coverage_rate = anchors_with_evidence / n_anchors
    pilot_cfg = rules["pilot"]["scaling_conditions"]
    blocked_cfg = rules["verdict"]["blocked"]

    pilot_ids = sorted(anchors, key=lambda a: vc.sha256_text(a["anchor_id"]))[: int(rules["pilot"]["max_anchors"])]
    pilot_cov = sum(1 for a in pilot_ids if summ[a["anchor_id"]]["evidence_in_window"] > 0)
    pilot_rate = pilot_cov / len(pilot_ids)
    ambiguous = sum(1 for r in links if r["tier"] == "AMBIGUOUS_L4")
    unresolved_rate_proxy = ambiguous / len(links) if links else 0.0
    blocked_overall = coverage_rate < pilot_cfg["min_anchor_coverage"]
    blocked_pilot = pilot_rate < pilot_cfg["min_anchor_coverage"]
    blocked_small = n_anchors < blocked_cfg["min_anchors"]
    print(f"\nBLOCKED gates:")
    print(f"  anchor coverage overall {anchors_with_evidence}/{n_anchors} = {coverage_rate:.6f}"
          f"  < {pilot_cfg['min_anchor_coverage']}? {blocked_overall}")
    print(f"  pilot coverage (n={len(pilot_ids)}) {pilot_cov}/{len(pilot_ids)} = {pilot_rate:.6f}"
          f"  < {pilot_cfg['min_anchor_coverage']}? {blocked_pilot}")
    print(f"  ambiguous/unresolved date rows {ambiguous}/{len(links)} = {unresolved_rate_proxy:.6f}"
          f"  > {blocked_cfg['max_unresolved_evidence_date_rate']}? "
          f"{unresolved_rate_proxy > blocked_cfg['max_unresolved_evidence_date_rate']}")
    print(f"  anchors < {blocked_cfg['min_anchors']}: {blocked_small}")

    # --------------------------------------------------------------- GO / LIMITED / NO-GO
    go, lim = rules["verdict"]["go"], rules["verdict"]["limited_go"]

    def gate_report(cfg, label, k_use, share_use, firms_use=None, years_use=None):
        res = {
            "k": (k_use, cfg["min_k"], k_use >= cfg["min_k"]),
            "share_ge_90": (share_use, cfg["min_p90_share_ge_90d"],
                            share_use >= cfg["min_p90_share_ge_90d"]),
            "specificity": (spec, cfg["min_specificity"], spec is not None and spec >= cfg["min_specificity"]),
            "placebo_p": (p_placebo, cfg["max_placebo_p"],
                          p_placebo is not None and p_placebo < cfg["max_placebo_p"]),
        }
        if label == "GO":
            res["firms"] = (len(firms_use), go["min_firms"], len(firms_use) >= go["min_firms"])
            res["years"] = (len(years_use), go["min_years"], len(years_use) >= go["min_years"])
        return res

    go_res = gate_report(go, "GO", k, share90, firms, years)
    lim_res = gate_report(lim, "LIMITED", k, share90)
    go_all = all(v[2] for v in go_res.values())
    lim_all = all(v[2] for v in lim_res.values())
    print(f"\nGO gates (committed numbers):")
    for kk, v in go_res.items():
        print(f"   {kk:12s} value={v[0]} threshold={v[1]} pass={v[2]}")
    print(f"GO all pass: {go_all}")
    print(f"LIMITED GO gates:")
    for kk, v in lim_res.items():
        print(f"   {kk:12s} value={v[0]} threshold={v[1]} pass={v[2]}")
    print(f"LIMITED all pass: {lim_all}")

    def decide(k_use, share_use, firms_use, years_use, blocked):
        if blocked:
            return "BLOCKED"
        if (k_use >= go["min_k"] and share_use >= go["min_p90_share_ge_90d"]
                and spec is not None and spec >= go["min_specificity"]
                and p_placebo is not None and p_placebo < go["max_placebo_p"]
                and len(firms_use) >= go["min_firms"] and len(years_use) >= go["min_years"]):
            return "GO"
        if (k_use >= lim["min_k"] and share_use >= lim["min_p90_share_ge_90d"]
                and spec is not None and spec >= lim["min_specificity"]
                and p_placebo is not None and p_placebo < lim["max_placebo_p"]):
            return "LIMITED GO"
        return "NO-GO"

    my_verdict = decide(k, share90, firms, years, blocked_overall or blocked_pilot or blocked_small)
    my_verdict_pilot_only = decide(k, share90, firms, years, blocked_pilot or blocked_small)
    my_verdict_ignoring_block = decide(k, share90, firms, years, False)
    my_verdict_full_title = decide(k_full, share90_full, firms, years, blocked_overall or blocked_pilot or blocked_small)
    print(f"\nMY VERDICT (frozen tree)                 : {my_verdict}")
    print(f"  if BLOCKED were judged on the pilot only: {my_verdict_pilot_only}")
    print(f"  if the BLOCKED branch were ignored      : {my_verdict_ignoring_block}")
    print(f"  with the protocol-literal title reading : {my_verdict_full_title}")

    # ----------------------------------------------------------- compare with committed
    print("\n" + "-" * 78)
    print("COMPARISON WITH results/verdict.json")
    print("-" * 78)
    print(f"committed verdict: {verdict['verdict']}   why={verdict['why']}")
    print(f"committed gates  : k={verdict['gates']['k_verified_links']} "
          f"share90={verdict['gates']['share_ge_90_days']} spec={verdict['gates']['specificity']} "
          f"p={verdict['gates']['p_placebo_median_lead']} firms={verdict['gates']['firms_represented']} "
          f"years={len(verdict['gates']['years_represented'])} "
          f"coverage={verdict['gates']['coverage_rate']}")
    same = verdict["verdict"] == my_verdict
    print(f"verdict matches my recomputation: {same}")
    print(f"committed go_checks            : {json.dumps(verdict['gates']['go_checks'])}")
    print(f"my go gate passes              : { {kk: v[2] for kk, v in go_res.items()} }")
    print(f"committed limited_go_checks    : {json.dumps(verdict['gates']['limited_go_checks'])}")

    payload = {
        "n_anchors": n_anchors,
        "k": k, "share90": share90, "firms": firms, "years": years,
        "k_full_title": k_full, "share90_full_title": share90_full,
        "k_brief_title": k_brief, "share90_brief_title": share90_brief,
        "specificity_field": spec,
        "specificity_arith": spec_arith,
        "specificity_matched_denominator": spec_matched,
        "placebo_p": p_placebo,
        "coverage_rate": coverage_rate,
        "pilot_coverage_rate": pilot_rate,
        "go_checks": {kk: list(v) for kk, v in go_res.items()},
        "limited_go_checks": {kk: list(v) for kk, v in lim_res.items()},
        "go_all_pass": go_all, "limited_all_pass": lim_all,
        "my_verdict": my_verdict,
        "my_verdict_pilot_only": my_verdict_pilot_only,
        "my_verdict_ignoring_block": my_verdict_ignoring_block,
        "my_verdict_full_title": my_verdict_full_title,
        "committed_verdict": verdict,
    }
    OUT.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"\nwrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
