"""D — lead-time measurement, identifiability (Q3), and the mechanical verdict.

Reads the committed artefacts only (plus the read-only store for the product-code catalogue
already embedded in the anchors). Writes ``results/d_leadtime.json`` and
``results/verdict.json``.

No number in this file is invented: every statistic is either a count, a percentile of a
committed list, or an interval computed from the frozen rules.
"""
from __future__ import annotations

import argparse
import collections
import json
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import phoenix003_common as pc
import b_links as bl


def load_links():
    rows = []
    for line in open(pc.EXPERIMENT_DIR / "EVIDENCE_LINKS.jsonl", encoding="utf-8"):
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows


def bootstrap_median_ci(values, resamples, seed, confidence):
    if not values:
        return None
    rng = random.Random(seed)
    n = len(values)
    meds = []
    for _ in range(resamples):
        sample = [values[rng.randrange(n)] for _ in range(n)]
        sample.sort()
        meds.append(pc.percentile(sample, 0.5))
    meds.sort()
    alpha = (1.0 - confidence) / 2.0
    return [pc.percentile(meds, alpha), pc.percentile(meds, 1.0 - alpha)]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default="data/medradar.sqlite")
    args = ap.parse_args(argv)

    rules = pc.load_rules()
    stats_cfg = rules["stats"]
    bootstrap_n = int(stats_cfg["bootstrap_resamples"])
    confidence = float(stats_cfg["confidence"])
    seed = int(stats_cfg["seed"])
    win_years = int(rules["evidence"]["window_years_before_anchor"])

    anchors = [json.loads(line) for line in
               open(pc.EXPERIMENT_DIR / "REGULATORY_ANCHORS.jsonl", encoding="utf-8")]
    anchors.sort(key=lambda a: a["anchor_id"])
    links = load_links()
    b = json.loads((pc.RESULTS / "b_links.json").read_text(encoding="utf-8"))
    c = json.loads((pc.RESULTS / "c_controls.json").read_text(encoding="utf-8"))
    b2 = json.loads((pc.RESULTS / "b2_novelty.json").read_text(encoding="utf-8"))
    summary_by_id = {s["anchor_id"]: s for s in b["anchor_summaries"]}

    verified = {t: [] for t in ("VERIFIED_L1", "VERIFIED_L2")}
    for r in links:
        if r["tier"] in verified:
            verified[r["tier"]].append(r)

    # ------------------------------------------------------------ per-anchor lead times
    def lead_records():
        out = {}
        for r in links:
            if r["tier"] not in ("VERIFIED_L1", "VERIFIED_L2"):
                continue
            out.setdefault(r["anchor_id"], []).append(r)
        return out

    by_anchor = lead_records()
    primary = {}      # anchor_id -> max lead (earliest evidence)
    sensitivity = {}
    per_source = {}
    for aid, rows in by_anchor.items():
        dates = sorted(pc.parse_date(r["evidence_date"]) for r in rows if r["evidence_date"])
        if not dates:
            continue
        adate = pc.parse_date(rows[0]["anchor_date"])
        primary[aid] = (adate - dates[0]).days
        srcs = sorted({r["evidence_source"] for r in rows})
        per_source[aid] = "+".join(srcs)
        sens_dates = []
        for r in rows:
            d = pc.parse_date(r["evidence_date"])
            s = pc.parse_date(r["evidence_date_sensitivity"])
            if d is None:
                continue
            sens_dates.append(max([x for x in (d, s) if x]) if s else d)
        if sens_dates:
            sensitivity[aid] = (adate - min(sens_dates)).days

    def summarise(lead_map, label):
        vals = sorted(lead_map.values())
        n = len(vals)
        out = {
            "label": label,
            "anchors_with_verified_link": n,
            "ge_90_days": sum(1 for v in vals if v >= 90),
            "ge_180_days": sum(1 for v in vals if v >= 180),
            "ge_365_days": sum(1 for v in vals if v >= 365),
            "share_ge_90_days": round(sum(1 for v in vals if v >= 90) / n, 6) if n else None,
            "median": pc.percentile(vals, 0.5) if n else None,
            "q1": pc.percentile(vals, 0.25) if n else None,
            "q3": pc.percentile(vals, 0.75) if n else None,
            "min": vals[0] if n else None,
            "max": vals[-1] if n else None,
            "median_ci95": bootstrap_median_ci(vals, bootstrap_n, seed, confidence),
            "negative_lead": sum(1 for v in vals if v < 0),
        }
        if n:
            lo, hi = pc.cp_interval(sum(1 for v in vals if v >= 90), n, confidence)
            out["share_ge_90_days_ci95"] = [lo, hi]
        return out

    overall = summarise(primary, "earliest verified evidence, publication clock")
    sens_overall = summarise(sensitivity, "earliest verified evidence, latest-plausible clock")

    # ---------------------------------------------------------------- stratum split
    stratum_of = {a["anchor_id"]: a["stratum"] for a in anchors}
    strata = {}
    for st in sorted(set(stratum_of.values())):
        sub = {k: v for k, v in primary.items() if stratum_of.get(k) == st}
        strata[st] = summarise(sub, st)

    # ------------------------------------------------------------- coverage & failures
    n_anchors = len(anchors)
    cov_window = {s["anchor_id"]: s["evidence_in_window"] for s in b["anchor_summaries"]}
    no_cov = [aid for aid, n in cov_window.items() if n == 0]
    date_unresolved = sum(1 for r in links if r["tier"] == "AMBIGUOUS_L4")
    per_firm = collections.Counter()
    per_firm_verified = collections.Counter()
    per_year_verified = collections.Counter()
    for a in anchors:
        per_firm[a["firm"]] += 1
        if a["anchor_id"] in primary:
            per_firm_verified[a["firm"]] += 1
            per_year_verified[a["anchor_year"]] += 1
    coverage = {
        "anchors": n_anchors,
        "anchors_with_any_firm_evidence_in_window": n_anchors - len(no_cov),
        "anchor_coverage_rate": round((n_anchors - len(no_cov)) / max(n_anchors, 1), 6),
        "anchors_with_no_firm_evidence": len(no_cov),
        "anchors_with_no_candidate_link": b["anchors_with_no_candidate"],
        "ambiguous_records": date_unresolved,
        "per_firm": {f: {"anchors": per_firm[f], "verified": per_firm_verified[f]}
                     for f in sorted(per_firm)},
        "verified_per_year": {str(y): per_year_verified[y] for y in sorted(per_year_verified)},
        "source_mix": dict(collections.Counter(per_source.values())),
    }

    # ------------------------------------------------- Q3 hindsight-free identifiability
    lineage = pc.load_lineage()
    resolver = pc.FirmResolver(lineage, rules)
    ctgov, ct_stats = bl.load_ctgov(resolver)
    epmc, ep_stats = bl.load_epmc(resolver)
    by_firm = collections.defaultdict(list)
    for i, r in enumerate(ctgov):
        for f in r["firms"]:
            if f in r["firm_verified"]:
                by_firm[f].append(("ctgov", i))
    for i, r in enumerate(epmc):
        for f in r["firms"]:
            if f in r["firm_verified"]:
                by_firm[f].append(("epmc", i))

    hf_rows = []
    for a in anchors:
        aid = a["anchor_id"]
        if aid not in primary:
            continue
        adate = pc.parse_date(a["anchor_date"])
        w0 = pc.years_before(adate, win_years)
        hf_tokens = [t for t in a.get("procode_generic_tokens", []) if len(t) >= 4 and t.isalpha()]
        hf_token_set = set(hf_tokens)
        hf_ids = set()
        burden = 0
        for src, i in by_firm.get(a["firm"], []):
            rec = ctgov[i] if src == "ctgov" else epmc[i]
            d = pc.parse_date(rec["date"])
            if d is None or not (w0 <= d < adate):
                continue
            if rec["all_tokens"] & hf_token_set:
                burden += 1
                hf_ids.add(f"{src}:{rec['id']}")
        linked_ids = {f"{r['evidence_source']}:{r['evidence_id']}"
                      for r in links
                      if r["anchor_id"] == aid and r["tier"] in ("VERIFIED_L1", "VERIFIED_L2")}
        recall = 1 if (linked_ids & hf_ids) else 0
        hf_rows.append({
            "anchor_id": aid, "firm": a["firm"], "stratum": a["stratum"],
            "hf_tokens": hf_tokens[:8], "hf_burden": burden,
            "hf_recall": recall, "lead_days": primary[aid],
        })
    hf_summary = {
        "definition": "frozen hindsight-free rule (protocol §7): firm + the product code's "
                      "official generic device name, records published before the milestone",
        "anchors": len(hf_rows),
        "hf_recall_1": sum(1 for r in hf_rows if r["hf_recall"] == 1),
        "hf_recall_rate": round(sum(1 for r in hf_rows if r["hf_recall"] == 1)
                                / max(len(hf_rows), 1), 6),
        "median_burden": pc.percentile(sorted(r["hf_burden"] for r in hf_rows), 0.5) if hf_rows else None,
        "burden_q1": pc.percentile(sorted(r["hf_burden"] for r in hf_rows), 0.25) if hf_rows else None,
        "burden_q3": pc.percentile(sorted(r["hf_burden"] for r in hf_rows), 0.75) if hf_rows else None,
        "hindsight_only_anchors": sum(1 for r in hf_rows if r["hf_recall"] == 0),
        "rows": hf_rows,
    }

    # -------------------------------------------------- validity ladder (descriptive)
    def level_leads(predicate):
        out = {}
        for r in links:
            if r["tier"] not in ("VERIFIED_L1", "VERIFIED_L2"):
                continue
            if not predicate(r):
                continue
            d = pc.parse_date(r["evidence_date"])
            if d is None:
                continue
            adate = pc.parse_date(r["anchor_date"])
            lead = (adate - d).days
            out[r["anchor_id"]] = max(out.get(r["anchor_id"], -10 ** 9), lead)
        return out

    ladder_defs = [
        ("L2_any_distinctive_token", lambda r: True,
         "pooled rule as frozen: any distinctive token identity"),
        ("L2_product_specific_token", lambda r: bool(r.get("product_specific")),
         "token used by at most 3 distinct applicants in device names (Amendment 2)"),
        ("L2_pre_regulatory", lambda r: r.get("regulatory_status") == "PRE_REGULATORY",
         "no regulatory record of that product name existed before the evidence date"),
        ("L2_product_specific_pre_regulatory",
         lambda r: bool(r.get("product_specific")) and r.get("regulatory_status") == "PRE_REGULATORY",
         "product-specific token AND no prior regulatory record"),
        ("L2_strict_literature_rare",
         lambda r: bool(r.get("product_specific")) and r.get("literature_rare")
         and r.get("regulatory_status") == "PRE_REGULATORY",
         "the strictest conjunction: product-specific AND literature-rare token (not an ordinary "
         "word of the field) AND no prior regulatory record (Amendment 5)"),
    ]
    ladder = {}
    for name, pred, desc in ladder_defs:
        leads = level_leads(pred)
        vals = sorted(leads.values())
        n = len(vals)
        ladder[name] = {
            "definition": desc,
            "anchors": n,
            "ge_90_days": sum(1 for v in vals if v >= 90),
            "ge_180_days": sum(1 for v in vals if v >= 180),
            "ge_365_days": sum(1 for v in vals if v >= 365),
            "share_ge_90_days": round(sum(1 for v in vals if v >= 90) / n, 6) if n else None,
            "median": pc.percentile(vals, 0.5) if n else None,
            "median_ci95": bootstrap_median_ci(vals, bootstrap_n, seed, confidence),
            "per_stratum": {st: sum(1 for aid in leads
                                    if stratum_of.get(aid) == st)
                            for st in sorted(set(stratum_of.values()))},
            "per_firm": {f: sum(1 for aid in leads
                                if next((a["firm"] for a in anchors if a["anchor_id"] == aid), None) == f)
                         for f in sorted({a["firm"] for a in anchors})},
        }

    # ------------------------------------------------------------------ verdict
    k = len(primary)
    share90 = overall["share_ge_90_days"]
    spec = c["c3_decoy"]["specificity"]
    spec_effective = float("inf") if spec is None else float(spec)
    p_placebo = c["c4b_date_permutation"]["p_median_lead"]
    firms_in = {a["firm"] for a in anchors if a["anchor_id"] in primary}
    years_in = {a["anchor_year"] for a in anchors if a["anchor_id"] in primary}

    blocked_cfg = rules["verdict"]["blocked"]
    go = rules["verdict"]["go"]
    limited = rules["verdict"]["limited_go"]
    pilot_cfg = rules["pilot"]["scaling_conditions"]

    pilot_ids = sorted(anchors, key=lambda a: pc.sha256_bytes(a["anchor_id"].encode()))[: int(rules["pilot"]["max_anchors"])]
    pilot_set = {a["anchor_id"] for a in pilot_ids}
    pilot_verified = sum(1 for a in pilot_ids if a["anchor_id"] in primary)
    pilot_cov = sum(1 for a in pilot_ids if cov_window.get(a["anchor_id"], 0) > 0)

    if (coverage["anchor_coverage_rate"] < pilot_cfg["min_anchor_coverage"]
            or n_anchors < blocked_cfg["min_anchors"]):
        verdict = "BLOCKED"
        why = ["pilot scaling condition failed or anchor sample too small"]
    elif (k >= go["min_k"] and share90 is not None and share90 >= go["min_p90_share_ge_90d"]
          and spec_effective >= go["min_specificity"] and p_placebo is not None
          and p_placebo < go["max_placebo_p"] and len(firms_in) >= go["min_firms"]
          and len(years_in) >= go["min_years"]):
        verdict = "GO"
        why = ["all GO gates met"]
    elif (k >= limited["min_k"] and share90 is not None and share90 >= limited["min_p90_share_ge_90d"]
          and spec_effective >= limited["min_specificity"] and p_placebo is not None
          and p_placebo < limited["max_placebo_p"]):
        verdict = "LIMITED GO"
        why = ["LIMITED GO gates met; GO gates not met"]
    else:
        verdict = "NO-GO"
        why = []

    gates = {
        "n_anchors": n_anchors,
        "k_verified_links": k,
        "share_ge_90_days": share90,
        "specificity": spec,
        "specificity_effective": None if spec is None else spec,
        "p_placebo_median_lead": p_placebo,
        "firms_represented": sorted(firms_in),
        "years_represented": sorted(years_in),
        "coverage_rate": coverage["anchor_coverage_rate"],
    }
    for name, cfg in (("go", go), ("limited_go", limited)):
        gates[f"{name}_checks"] = {
            "k>=": [k, cfg["min_k"], k >= cfg["min_k"]],
            "share_ge_90>=": [share90, cfg["min_p90_share_ge_90d"],
                              share90 is not None and share90 >= cfg["min_p90_share_ge_90d"]],
            "specificity>=": [spec, cfg["min_specificity"], spec_effective >= cfg["min_specificity"]],
            "placebo_p<": [p_placebo, cfg["max_placebo_p"],
                           p_placebo is not None and p_placebo < cfg["max_placebo_p"]],
        }
    gates["go_checks"]["firms>="] = [len(firms_in), go["min_firms"], len(firms_in) >= go["min_firms"]]
    gates["go_checks"]["years>="] = [len(years_in), go["min_years"], len(years_in) >= go["min_years"]]

    verdict_payload = {
        "generated_at": pc.utc_now_iso(),
        "verdict": verdict,
        "why": why,
        "gates": gates,
        "pilot": {
            "n": len(pilot_ids),
            "selection": rules["pilot"]["selection"],
            "anchors_with_firm_evidence": pilot_cov,
            "coverage_rate": round(pilot_cov / max(len(pilot_ids), 1), 6),
            "verified": pilot_verified,
            "verified_rate": round(pilot_verified / max(len(pilot_ids), 1), 6),
        },
        "rules_used": {"verdict": rules["verdict"], "pilot": rules["pilot"]},
    }

    out = {
        "generated_at": pc.utc_now_iso(),
        "overall_publication_clock": overall,
        "overall_latest_plausible_clock": sens_overall,
        "per_stratum": strata,
        "coverage": coverage,
        "identifiability": {k2: v for k2, v in hf_summary.items() if k2 != "rows"},
        "identifiability_rows": hf_summary["rows"],
        "validity_ladder": ladder,
        "target_b": {
            "anchors_globally_novel_name": b2["anchors_target_b_novel"],
            "anchors_globally_novel_with_verified_link": b2["anchors_target_b_novel_with_verified_link"],
        },
        "corpus": {"ctgov": ct_stats, "epmc": ep_stats},
        "tier_counts": b["tier_counts"],
        "note": "lead_days = milestone decision date minus the earliest verified evidence date. "
                "The publication clock uses first_posted / firstPublicationDate; the "
                "latest-plausible clock uses the largest available date field per evidence record.",
    }
    pc.write_json(pc.RESULTS / "d_leadtime.json", out)
    pc.write_json(pc.RESULTS / "verdict.json", verdict_payload)
    print(json.dumps({
        "verdict": verdict,
        "k": k,
        "share_ge_90": share90,
        "median_lead": overall["median"],
        "specificity": spec,
        "p_placebo": p_placebo,
        "firms": sorted(firms_in),
        "anchors": n_anchors,
        "coverage_rate": coverage["anchor_coverage_rate"],
        "hf_recall_rate": hf_summary["hf_recall_rate"],
        "hf_median_burden": hf_summary["median_burden"],
        "ladder": {k: {"anchors": v["anchors"], "share_ge_90": v["share_ge_90_days"],
                       "median": v["median"]} for k, v in ladder.items()},
    }, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
