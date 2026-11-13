"""C — controls: keyword baseline, matched decoys, time placebo, concentration.

Every control is mechanical and seeded from ``FROZEN_RULES.json``. Nothing here is tuned
after seeing a result: the statistics are fixed by protocol §8 and the thresholds by §10.

Writes ``results/c_controls.json``.
"""
from __future__ import annotations

import argparse
import collections
import json
import math
import random
import sys
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import phoenix003_common as pc
import b_links as bl
import b2_novelty as b2


def load_corpora(resolver):
    ctgov, ct_stats = bl.load_ctgov(resolver)
    epmc, ep_stats = bl.load_epmc(resolver)
    by_firm = collections.defaultdict(list)   # firm -> [(src, idx)]
    for i, r in enumerate(ctgov):
        for f in r["firms"]:
            if f in r["firm_verified"]:
                by_firm[f].append(("ctgov", i))
    for i, r in enumerate(epmc):
        for f in r["firms"]:
            if f in r["firm_verified"]:
                by_firm[f].append(("epmc", i))
    return ctgov, epmc, by_firm, {"ctgov": ct_stats, "epmc": ep_stats}


def record_of(src, i, ctgov, epmc):
    return ctgov[i] if src == "ctgov" else epmc[i]


def window_dates(by_firm, firm, ctgov, epmc, w_start, w_end):
    """All public dates of the firm's verified records inside [w_start, w_end)."""
    out = []
    for src, i in by_firm.get(firm, []):
        d = pc.parse_date(record_of(src, i, ctgov, epmc)["date"])
        if d is not None and w_start <= d < w_end:
            out.append(d)
    out.sort()
    return out


def token_match_dates(by_firm, firm, tokens, ctgov, epmc):
    """Sorted public dates of verified records containing ANY of the given tokens."""
    if not tokens:
        return []
    dates = []
    for src, i in by_firm.get(firm, []):
        rec = record_of(src, i, ctgov, epmc)
        if rec["all_tokens"] & set(tokens) if src == "epmc" else rec["name_tokens"] & set(tokens):
            d = pc.parse_date(rec["date"])
            if d is not None:
                dates.append(d)
    dates.sort()
    return dates


def earliest_in_window(dates, w_start, w_end):
    for d in dates:
        if d >= w_start and d < w_end:
            return d
    return None


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default="data/medradar.sqlite")
    args = ap.parse_args(argv)

    rules = pc.load_rules()
    lineage = pc.load_lineage()
    resolver = pc.FirmResolver(lineage, rules)
    tokenizer = pc.DistinctiveTokenizer(rules, pc.load_frozen_vocab())
    rng = random.Random(int(rules["stats"]["seed"]))
    R_shift = int(rules["controls"]["c4_placebo"]["permutations"])
    shift_lo = int(rules["controls"]["c4_placebo"]["shift_days_min"])
    shift_hi = int(rules["controls"]["c4_placebo"]["shift_days_max"])
    decoy_win = int(rules["controls"]["c3_decoy"]["year_window_days"])
    min_pool = int(rules["controls"]["c3_decoy"]["min_pool_size"])
    win_years = int(rules["evidence"]["window_years_before_anchor"])

    anchors = [json.loads(line) for line in
               open(pc.EXPERIMENT_DIR / "REGULATORY_ANCHORS.jsonl", encoding="utf-8")]
    anchors.sort(key=lambda a: a["anchor_id"])
    b_links = json.loads((pc.RESULTS / "b_links.json").read_text(encoding="utf-8"))
    summary_by_id = {s["anchor_id"]: s for s in b_links["anchor_summaries"]}

    ctgov, epmc, by_firm, corpus_stats = load_corpora(resolver)
    print(f"corpus: ctgov={len(ctgov)} epmc={len(epmc)}")
    # token -> first regulatory date of any applicant, for the strict-level decoy control
    first_global, _first_firm, _n_ms = b2.load_token_history(args.db)

    # pre-compute match dates per anchor for its own tokens (cheap binary-search placebo)
    own = {}
    for a in anchors:
        adate = pc.parse_date(a["anchor_date"])
        w0 = pc.years_before(adate, win_years)
        own[a["anchor_id"]] = {
            "adate": adate,
            "dates": token_match_dates(by_firm, a["firm"], a["distinctive_tokens"], ctgov, epmc),
            "window_dates": window_dates(by_firm, a["firm"], ctgov, epmc, w0, adate),
        }

    # ------------------------------------------------------------------ C1 keyword
    c1 = {"anchors": 0, "linked": 0, "leads": [], "per_firm": collections.Counter(),
          "per_firm_linked": collections.Counter()}
    for a in anchors:
        adate = pc.parse_date(a["anchor_date"])
        w0 = pc.years_before(adate, win_years)
        generic = [t for t in a.get("procode_generic_tokens", [])
                   if len(t) >= 4 and t.isalpha()]
        brand = set(lineage["brand_tokens"][a["firm"]]["any_token"])
        hit_dates = []
        for src, i in by_firm.get(a["firm"], []):
            rec = record_of(src, i, ctgov, epmc)
            d = pc.parse_date(rec["date"])
            if d is None or not (w0 <= d < adate):
                continue
            if (rec["all_tokens"] & brand) or (rec["all_tokens"] & set(generic)):
                hit_dates.append(d)
        c1["anchors"] += 1
        c1["per_firm"][a["firm"]] += 1
        if hit_dates:
            c1["linked"] += 1
            c1["per_firm_linked"][a["firm"]] += 1
            c1["leads"].append((adate - min(hit_dates)).days)
    c1_out = {
        "definition": "keyword baseline: firm brand token or any >=4-char token of the product "
                      "code's generic device name appears in a firm-verified record inside the window",
        "anchors": c1["anchors"],
        "linked": c1["linked"],
        "link_rate": round(c1["linked"] / max(c1["anchors"], 1), 6),
        "median_lead_days": pc.percentile(sorted(c1["leads"]), 0.5) if c1["leads"] else None,
        "per_firm_link_rate": {f: round(c1["per_firm_linked"][f] / c1["per_firm"][f], 6)
                               for f in sorted(c1["per_firm"])},
    }

    # ------------------------------------------------------------------ C2 real
    real_linked = sum(1 for s in summary_by_id.values() if s["has_verified_link"])
    real_rate = real_linked / max(len(anchors), 1)

    # ------------------------------------------------------------------ C3 decoys
    by_firm_anchors = collections.defaultdict(list)
    for a in anchors:
        by_firm_anchors[a["firm"]].append(a)
    decoy_rows = []
    decoy_linked = 0
    decoy_linked_ps = 0
    decoy_linked_ps_pre = 0
    decoy_used = 0
    for a in anchors:
        adate = pc.parse_date(a["anchor_date"])
        pool = [x for x in by_firm_anchors[a["firm"]]
                if x["product_code"] != a["product_code"]
                and x["anchor_id"] != a["anchor_id"]
                and adate is not None
                and abs((pc.parse_date(x["anchor_date"]) - adate).days) <= decoy_win]
        if len(pool) < min_pool:
            continue
        donor = pool[rng.randrange(len(pool))]
        dtokens = list(donor["distinctive_tokens"])
        if not dtokens:
            continue
        decoy_used += 1
        dtok = dtokens[rng.randrange(len(dtokens))]
        mdates = token_match_dates(by_firm, a["firm"], [dtok], ctgov, epmc)
        w0 = pc.years_before(adate, win_years)
        date = earliest_in_window(mdates, w0, adate)
        if date is not None:
            decoy_linked += 1
        # strict-level decoy: is the decoy token product specific, and was the product
        # already regulated when the decoy evidence was published?
        dspec = tokenizer.is_product_specific(dtok)
        fg = first_global.get(dtok)
        dpre = (fg is not None and date is not None and fg > date)
        if date is not None and dspec:
            decoy_linked_ps += 1
        if date is not None and dspec and dpre:
            decoy_linked_ps_pre += 1
        decoy_rows.append({
            "anchor_id": a["anchor_id"], "firm": a["firm"],
            "decoy_token": dtok, "donor_anchor_id": donor["anchor_id"],
            "donor_product_code": donor["product_code"],
            "decoy_token_applicant_df": tokenizer.applicant_df_of(dtok),
            "decoy_product_specific": dspec,
            "decoy_token_first_reg_date": pc.iso(fg),
            "decoy_pre_regulatory": dpre,
            "decoy_linked": date is not None,
            "decoy_lead_days": (adate - date).days if date else None,
        })
    decoy_rate = decoy_linked / max(decoy_used, 1)
    # match the denominator: the real rate must be computed on the anchors that received a decoy
    decoy_anchor_ids = {r["anchor_id"] for r in decoy_rows}
    real_linked_matched = sum(1 for aid, s_ in summary_by_id.items()
                              if aid in decoy_anchor_ids and s_["has_verified_link"])
    real_rate_matched = real_linked_matched / max(len(decoy_anchor_ids), 1)
    specificity = (real_rate_matched / decoy_rate) if decoy_rate > 0 else None
    decoy_rate_ps = decoy_linked_ps / max(decoy_used, 1)
    decoy_rate_ps_pre = decoy_linked_ps_pre / max(decoy_used, 1)
    # real strict-level rates, computed directly from the committed link rows so this stage has
    # no dependency on d_leadtime having run
    verified_rows = [r for r in
                     (json.loads(line) for line in
                      open(pc.EXPERIMENT_DIR / "EVIDENCE_LINKS.jsonl", encoding="utf-8"))
                     if r["tier"] in ("VERIFIED_L1", "VERIFIED_L2")]
    real_ps_ids = {r["anchor_id"] for r in verified_rows if r.get("product_specific")}
    real_ps_pre_ids = {r["anchor_id"] for r in verified_rows
                       if r.get("product_specific")
                       and r.get("regulatory_status") == "PRE_REGULATORY"}
    real_ps = len(real_ps_ids) / max(len(anchors), 1)
    real_ps_pre = len(real_ps_pre_ids) / max(len(anchors), 1)
    real_ps_matched = len(real_ps_ids & decoy_anchor_ids) / max(len(decoy_anchor_ids), 1)
    real_ps_pre_matched = len(real_ps_pre_ids & decoy_anchor_ids) / max(len(decoy_anchor_ids), 1)
    spec_ps = (real_ps_matched / decoy_rate_ps) if decoy_rate_ps > 0 else None
    spec_ps_pre = (real_ps_pre_matched / decoy_rate_ps_pre) if decoy_rate_ps_pre > 0 else None
    c3_out = {
        "definition": "same firm, different product code, anchor date within the frozen window: "
                      "the donor's distinctive token replaces the milestone's token",
        "anchors_with_decoy": decoy_used,
        "decoy_linked": decoy_linked,
        "decoy_link_rate": round(decoy_rate, 6),
        "real_link_rate": round(real_rate, 6),
        "specificity": round(specificity, 4) if specificity is not None else None,
        "real_link_rate_product_specific": real_ps,
        "decoy_link_rate_product_specific": round(decoy_rate_ps, 6),
        "specificity_product_specific": round(spec_ps, 4) if spec_ps is not None else None,
        "real_link_rate_product_specific_pre_regulatory": real_ps_pre,
        "decoy_link_rate_product_specific_pre_regulatory": round(decoy_rate_ps_pre, 6),
        "specificity_product_specific_pre_regulatory": (
            round(spec_ps_pre, 4) if spec_ps_pre is not None else None),
        "specificity_note": (
            "specificity = real rate / decoy rate, both on the same denominator (anchors that "
            "received a decoy). A null value means the decoy rate was zero, which is unbounded "
            "above rather than a pass."),
        "specificity_matched_denominator": (
            round(real_linked_matched / decoy_used / (decoy_linked / decoy_used), 4)
            if decoy_linked > 0 and decoy_used > 0 else None),
        "rows": decoy_rows,
    }

    # ------------------------------------------------------------- C4a time shift
    def stat_for_shift(shift_days: int, rng_local):
        linked = 0
        leads = []
        for a in anchors:
            st = own[a["anchor_id"]]
            a2 = st["adate"] + timedelta(days=shift_days)
            w0 = pc.years_before(a2, win_years)
            date = earliest_in_window(st["dates"], w0, a2)
            if date is not None:
                linked += 1
                leads.append((a2 - date).days)
        return linked / max(len(anchors), 1), (pc.percentile(sorted(leads), 0.5) if leads else None)

    null_rates = []
    null_medians = []
    rng_shift = random.Random(int(rules["stats"]["seed"]) + 1)
    for _ in range(R_shift):
        lo = rng_shift.randint(shift_lo, shift_hi)
        sign = 1 if rng_shift.random() < 0.5 else -1
        rate, med = stat_for_shift(sign * lo, rng_shift)
        null_rates.append(rate)
        if med is not None:
            null_medians.append(med)
    real_median = None
    real_leads = [s["lead_days_max"] for s in summary_by_id.values()
                  if s["has_verified_link"] and s["lead_days_max"] is not None]
    if real_leads:
        real_median = pc.percentile(sorted(real_leads), 0.5)
    p_rate = (1 + sum(1 for x in null_rates if x >= real_rate)) / (len(null_rates) + 1)
    p_median = (1 + sum(1 for x in null_medians if x >= real_median)) / (len(null_medians) + 1) \
        if real_median is not None and null_medians else None
    c4a_out = {
        "definition": "anchor date shifted by a random offset in +/-[90,1095] days, evidence and "
                      "tokens held fixed, window recomputed around the shifted date",
        "draws": len(null_rates),
        "observed_link_rate": round(real_rate, 6),
        "null_link_rate_mean": round(sum(null_rates) / len(null_rates), 6),
        "null_link_rate_p95": round(pc.percentile(sorted(null_rates), 0.95), 6),
        "p_link_rate": round(p_rate, 6),
        "observed_median_lead_days": real_median,
        "null_median_lead_mean": round(sum(null_medians) / len(null_medians), 2) if null_medians else None,
        "p_median_lead": round(p_median, 6) if p_median is not None else None,
    }

    # ------------------------------------------------- C4b date permutation within year
    groups = collections.defaultdict(list)
    for a in anchors:
        groups[(a["firm"], a["anchor_year"])].append(a)
    perm_dates = {gid: [pc.parse_date(x["anchor_date"]) for x in items]
                  for gid, items in groups.items()}
    rng_perm = random.Random(int(rules["stats"]["seed"]) + 2)
    perm_medians = []
    perm_rates = []
    # the frozen rule fixes 2000 permutations for C4; both halves of C4 use it
    for _ in range(R_shift):
        linked = 0
        leads = []
        for gid, items in groups.items():
            ds = perm_dates[gid][:]
            rng_perm.shuffle(ds)
            for a, a2 in zip(items, ds):
                st = own[a["anchor_id"]]
                w0 = pc.years_before(a2, win_years)
                date = earliest_in_window(st["dates"], w0, a2)
                if date is not None:
                    linked += 1
                    leads.append((a2 - date).days)
        perm_rates.append(linked / max(len(anchors), 1))
        if leads:
            perm_medians.append(pc.percentile(sorted(leads), 0.5))
    c4b_out = {
        "definition": "anchor dates permuted among anchors of the same firm and year; tokens fixed",
        "draws": len(perm_rates),
        "observed_link_rate": round(real_rate, 6),
        "null_link_rate_mean": round(sum(perm_rates) / len(perm_rates), 6),
        "p_link_rate": round((1 + sum(1 for x in perm_rates if x >= real_rate)) / (len(perm_rates) + 1), 6),
        "null_median_lead_mean": round(sum(perm_medians) / len(perm_medians), 2) if perm_medians else None,
        "p_median_lead": (round((1 + sum(1 for x in perm_medians if x >= real_median)) / (len(perm_medians) + 1), 6)
                          if real_median is not None and perm_medians else None),
    }

    # ------------------------------------------------------------ C5 concentration
    per_firm = collections.Counter()
    per_firm_verified = collections.Counter()
    per_year_linked = collections.Counter()
    per_year_total = collections.Counter()
    per_code_linked = collections.Counter()
    for s in summary_by_id.values():
        per_firm[s["firm"]] += 1
        per_year_total[s["anchor_year"]] += 1
        if s["has_verified_link"]:
            per_firm_verified[s["firm"]] += 1
            per_year_linked[s["anchor_year"]] += 1
            per_code_linked[s["product_code"]] += 1
    loo = {}
    for f in per_firm:
        rest = [s for s in summary_by_id.values() if s["firm"] != f]
        loo[f] = {
            "anchors_without_firm": len(rest),
            "verified_without_firm": sum(1 for s in rest if s["has_verified_link"]),
            "link_rate_without_firm": round(
                sum(1 for s in rest if s["has_verified_link"]) / max(len(rest), 1), 6),
        }
    c5_out = {
        "per_firm": {f: {"anchors": per_firm[f], "verified": per_firm_verified[f],
                         "rate": round(per_firm_verified[f] / per_firm[f], 6)}
                     for f in sorted(per_firm)},
        "per_year": {str(y): {"anchors": per_year_total[y], "verified": per_year_linked[y]}
                     for y in sorted(per_year_total)},
        "top_product_codes": [[c, n] for c, n in per_code_linked.most_common(5)],
        "top_code_share_of_verified": round(
            (per_code_linked.most_common(1)[0][1] / max(sum(per_code_linked.values()), 1))
            if per_code_linked else 0.0, 6),
        "leave_one_firm_out": loo,
    }

    out = {
        "generated_at": pc.utc_now_iso(),
        "corpus": corpus_stats,
        "c1_keyword_baseline": c1_out,
        "c2_anchored": {"anchors": len(anchors), "verified_linked": real_linked,
                        "link_rate": round(real_rate, 6)},
        "c3_decoy": {k: v for k, v in c3_out.items() if k != "rows"},
        "c3_decoy_rows": c3_out["rows"],
        "c4a_time_shift": c4a_out,
        "c4b_date_permutation": c4b_out,
        "c5_concentration": c5_out,
    }
    pc.write_json(pc.RESULTS / "c_controls.json", out)
    print(json.dumps({
        "c1_link_rate": c1_out["link_rate"],
        "c2_link_rate": out["c2_anchored"]["link_rate"],
        "c3_decoy_rate": c3_out["decoy_link_rate"],
        "specificity": c3_out["specificity"],
        "specificity_ps": c3_out["specificity_product_specific"],
        "specificity_ps_pre": c3_out["specificity_product_specific_pre_regulatory"],
        "c4a": {k: c4a_out[k] for k in ("p_link_rate", "null_link_rate_mean", "observed_median_lead_days", "p_median_lead")},
        "c4b": {k: c4b_out[k] for k in ("p_link_rate", "p_median_lead")},
        "per_firm": c5_out["per_firm"],
    }, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
