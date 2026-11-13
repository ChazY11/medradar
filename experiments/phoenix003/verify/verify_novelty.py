"""STEP 4 — independent re-derivation of the regulatory-novelty classification.

Protocol amendment 3 / b2_novelty: for a verified link with distinctive token T published at
date d,

    PRE_REGULATORY      iff no canonical regulatory record of ANY applicant whose device name
                        contains T has a decision date <= d
    PRE_EXISTING_PRODUCT otherwise

Token history is rebuilt from data/medradar.sqlite (read-only) by the verifier: canonical
milestones = 510(k) by k_number + original PMA (supplement_number empty); the "device name" is
the record's own name (510k.device_name / pma.trade_name with generic_name fallback); a token
"contains" for the history means whole-token equality after the verifier's own normalisation
(length >= 4, alphabetic), exactly as the protocol's question is phrased over device names.

`product_specific` is re-derived from dataset/frozen_vocab.json applicant_df <= 3
(FROZEN_RULES.json name_vocab.product_specific_max_applicant_df).

Run:  python experiments/phoenix003/verify/verify_novelty.py
"""
from __future__ import annotations

import collections
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import vcommon as vc

OUT = Path(__file__).resolve().parent / "out_novelty.json"


def token_history():
    """token -> (first global decision date, first date per firm), canonical milestones only."""
    rules = vc.load_json(vc.EXP / "FROZEN_RULES.json")
    resolver = vc.Resolver()
    con = vc.connect_ro()
    first_global, first_firm = {}, collections.defaultdict(dict)
    n = 0
    q = """
      select json_extract(payload,'$.device_name') as dn,
             json_extract(payload,'$.trade_name')  as tn,
             json_extract(payload,'$.generic_name') as gn,
             json_extract(payload,'$.supplement_number') as supp,
             applicant_raw, event_date, kind
      from events where kind in ('510k','pma')
    """
    for r in con.execute(q):
        if r["kind"] == "pma" and (r["supp"] or "").strip():
            continue
        name = r["dn"] or r["tn"] or r["gn"] or ""
        d = vc.parse_date(r["event_date"])
        if not name or d is None:
            continue
        n += 1
        firm, _ = resolver.resolve(r["applicant_raw"] or "")
        toks = {t for t in vc.tokens(name) if len(t) >= 4 and t.isalpha()}
        for tok in toks:
            if tok not in first_global or d < first_global[tok]:
                first_global[tok] = d
            if firm:
                cur = first_firm[tok].get(firm)
                if cur is None or d < cur:
                    first_firm[tok][firm] = d
    con.close()
    return first_global, first_firm, n


def classify(links, first_global, df, ps_max):
    status = collections.Counter()
    for r in links:
        tok = r.get("matched_token")
        ed = vc.parse_date(r.get("evidence_date"))
        fg = first_global.get(tok)
        r["_first_global"] = fg.isoformat() if fg else None
        r["_product_specific"] = 0 < df.get(tok, 0) <= ps_max
        if fg is None or ed is None:
            r["_status"] = "unknown"
        elif fg <= ed:
            r["_status"] = "PRE_EXISTING_PRODUCT"
        else:
            r["_status"] = "PRE_REGULATORY"
        status[r["_status"]] += 1
    return status


def anchor_rollup(links):
    per = {}
    for r in links:
        st = r["_status"]
        cur = per.setdefault(r["anchor_id"], {"pre_reg": False, "specific_pre_reg": False})
        cur["pre_reg"] = cur["pre_reg"] or st == "PRE_REGULATORY"
        cur["specific_pre_reg"] = cur["specific_pre_reg"] or (
            st == "PRE_REGULATORY" and r["_product_specific"])
    return per


def main():
    rules = vc.load_json(vc.EXP / "FROZEN_RULES.json")
    vocab = vc.load_json(vc.DATASET / "frozen_vocab.json")
    df = {k: int(v) for k, v in vocab.get("applicant_df", {}).items()}
    ps_max = int(rules["name_vocab"]["product_specific_max_applicant_df"])

    first_global, first_firm, n_ms = token_history()
    print("=" * 78)
    print("NOVELTY / PRE-REGULATORY CLASSIFICATION")
    print("=" * 78)
    print(f"canonical milestones used for token history: {n_ms}  tokens: {len(first_global)}")

    links = vc.committed_links()
    verified = [r for r in links if r["tier"] in ("VERIFIED_L1", "VERIFIED_L2")]
    status = classify(verified, first_global, df, ps_max)
    per = anchor_rollup(verified)

    print(f"\nINDEPENDENT link status counts: {dict(status)}")
    print(f"  anchors with >=1 PRE_REGULATORY link              : "
          f"{sum(1 for v in per.values() if v['pre_reg'])}")
    print(f"  anchors with product-specific PRE_REGULATORY link : "
          f"{sum(1 for v in per.values() if v['specific_pre_reg'])}")

    # row-level comparison with the committed regulatory_status field
    mismatch = []
    for r in verified:
        com = r.get("regulatory_status")
        mine = r["_status"]
        if com != mine:
            mismatch.append((r["anchor_id"][:12], r["milestone_key"], r["evidence_id"],
                             r["matched_token"], r["evidence_date"], com, mine,
                             r["_first_global"]))
    print(f"\nrow-level regulatory_status mismatches vs committed: {len(mismatch)}")
    for m in mismatch[:20]:
        print("   ", m)
    # product_specific field comparison
    ps_mismatch = [(r["anchor_id"][:12], r["matched_token"], r.get("product_specific"),
                    r["_product_specific"], df.get(r["matched_token"]))
                   for r in verified if bool(r.get("product_specific")) != r["_product_specific"]]
    print(f"row-level product_specific mismatches vs committed: {len(ps_mismatch)}")
    for m in ps_mismatch[:20]:
        print("   ", m)

    b2 = vc.result_json("b2_novelty.json")
    print(f"\nCOMMITTED b2_novelty.json: link_status_counts={b2['link_status_counts']}"
          f"  anchors_with_pre_regulatory_link={b2['anchors_with_pre_regulatory_link']}"
          f"  anchors_with_product_specific_pre_regulatory_link="
          f"{b2['anchors_with_product_specific_pre_regulatory_link']}")
    # recompute the committed aggregates from the committed rows themselves
    com_per = {}
    for r in verified:
        cur = com_per.setdefault(r["anchor_id"], {"pre_reg": False, "specific_pre_reg": False})
        cur["pre_reg"] = cur["pre_reg"] or r.get("regulatory_status") == "PRE_REGULATORY"
        cur["specific_pre_reg"] = cur["specific_pre_reg"] or (
            r.get("regulatory_status") == "PRE_REGULATORY" and bool(r.get("product_specific")))
    print(f"recomputed from committed rows: pre_reg anchors="
          f"{sum(1 for v in com_per.values() if v['pre_reg'])}"
          f"  product-specific pre_reg anchors="
          f"{sum(1 for v in com_per.values() if v['specific_pre_reg'])}"
          f"  rows PRE_REGULATORY={sum(1 for r in verified if r.get('regulatory_status')=='PRE_REGULATORY')}"
          f"  rows PRE_EXISTING={sum(1 for r in verified if r.get('regulatory_status')=='PRE_EXISTING_PRODUCT')}")

    # per-anchor set comparison
    com_ids = {aid for aid, v in com_per.items() if v["pre_reg"]}
    my_ids = {aid for aid, v in per.items() if v["pre_reg"]}
    print(f"\nanchors pre_reg: mine={len(my_ids)} committed={len(com_ids)}"
          f" identical={len(my_ids & com_ids)} only-mine={sorted(my_ids-com_ids)}"
          f" only-committed={sorted(com_ids-my_ids)}")
    com_ps = {aid for aid, v in com_per.items() if v["specific_pre_reg"]}
    my_ps = {aid for aid, v in per.items() if v["specific_pre_reg"]}
    print(f"anchors specific pre_reg: mine={len(my_ps)} committed={len(com_ps)}"
          f" identical={len(my_ps & com_ps)} only-mine={sorted(my_ps-com_ps)}"
          f" only-committed={sorted(com_ps-my_ps)}")

    # target B novelty flags (protocol 4.4) — independently recomputed
    anchors = vc.committed_anchors()
    tb = []
    for a in anchors:
        adate = vc.parse_date(a["anchor_date"])
        ok = True
        for tok in (a.get("distinctive_tokens") or []):
            fg = first_global.get(tok)
            ff = first_firm.get(tok, {}).get(a["firm"])
            if not (fg is None or fg >= adate):
                ok = False
                break
            if not (ff is None or ff >= adate):
                ok = False
                break
        if ok:
            tb.append(a["anchor_id"])
    print(f"\nTarget-B novel anchors: mine={len(tb)} committed={b2['anchors_target_b_novel']}"
          f" identical={len(set(tb) & set(b2['target_b_anchor_ids']))}"
          f" only-mine={len(set(tb)-set(b2['target_b_anchor_ids']))}"
          f" only-committed={len(set(b2['target_b_anchor_ids'])-set(tb))}")
    tb_link = [aid for aid in tb if aid in per]
    print(f"Target-B novel anchors with a verified link: mine={len(tb_link)}"
          f" committed={b2['anchors_target_b_novel_with_verified_link']}")

    # ------------------------------------- full verified-link set (live mode only)
    # EVIDENCE_LINKS.jsonl is capped at 100 rows per anchor, sorted with VERIFIED last, so it
    # can drop verified links. My independent L1/L2 derivation (verify_links.py -> rows_author)
    # reproduces b_links.json peer tier counts exactly; classify that full set too.
    full = None
    rows_path = Path(__file__).resolve().parent / ("out_links.json" if vc.MODE == "live"
                                                   else "out_links_snapshot.json")
    if rows_path.exists():
        data = vc.load_json(rows_path)
        full_rows = data.get("rows_author") or []
        if full_rows:
            full_status = classify(full_rows, first_global, df, ps_max)
            full_per = anchor_rollup(full_rows)
            print(f"\nFULL verified-link set ({len(full_rows)} rows, b_links tier counts):"
                  f" {dict(full_status)}")
            print(f"  anchors with >=1 PRE_REGULATORY link              : "
                  f"{sum(1 for v in full_per.values() if v['pre_reg'])}")
            print(f"  anchors with product-specific PRE_REGULATORY link : "
                  f"{sum(1 for v in full_per.values() if v['specific_pre_reg'])}")
            post_kw = ("POST-APPROVAL", "POST APPROVAL", "POST-MARKET", "POST MARKET",
                       "POST MARKETING", "POST-MARKETING", "POST-MARKET")
            pr_rows = [r for r in full_rows if r["_status"] == "PRE_REGULATORY"]
            ps_pr = [r for r in pr_rows if r["_product_specific"]]
            def is_post(r):
                t = (r.get("evidence_title") or "").upper()
                return any(x in t for x in post_kw)
            print(f"  rows PRE_REGULATORY={len(pr_rows)} of which self-declared post-approval/market"
                  f" titles: {sum(1 for r in pr_rows if is_post(r))}")
            print(f"  product-specific PRE_REGULATORY rows={len(ps_pr)} of which post-approval/market"
                  f" titles: {sum(1 for r in ps_pr if is_post(r))}")
            full = {"rows": len(full_rows), "status_counts": dict(full_status),
                    "anchors_pre_reg": sum(1 for v in full_per.values() if v["pre_reg"]),
                    "anchors_specific_pre_reg": sum(1 for v in full_per.values()
                                                    if v["specific_pre_reg"]),
                    "pre_reg_rows": len(pr_rows),
                    "pre_reg_post_approval_rows": sum(1 for r in pr_rows if is_post(r)),
                    "ps_pre_reg_rows": len(ps_pr),
                    "ps_pre_reg_post_approval_rows": sum(1 for r in ps_pr if is_post(r)),
                    "per_anchor": full_per,
                    "status_by_row": [(r["anchor_id"], r["evidence_source"], r["evidence_id"],
                                       r["matched_token"], r["evidence_date"], r["_status"],
                                       r["_product_specific"]) for r in full_rows]}

    payload = {
        "full_verified_set": full,
        "canonical_milestones": n_ms,
        "tokens": len(first_global),
        "my_status_counts": dict(status),
        "my_anchors_pre_reg": len(my_ids),
        "my_anchors_specific_pre_reg": len(my_ps),
        "committed_status_counts": b2["link_status_counts"],
        "committed_anchors_pre_reg": b2["anchors_with_pre_regulatory_link"],
        "committed_anchors_specific_pre_reg":
            b2["anchors_with_product_specific_pre_regulatory_link"],
        "row_status_mismatches": mismatch,
        "product_specific_mismatches": ps_mismatch,
        "target_b": {"mine": len(tb), "committed": b2["anchors_target_b_novel"],
                     "mine_with_link": len(tb_link),
                     "committed_with_link": b2["anchors_target_b_novel_with_verified_link"]},
        "pre_reg_anchor_ids": sorted(my_ids),
        "verified_rows": [{k: v for k, v in r.items()} for r in verified],
    }
    OUT.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    print(f"\nwrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
