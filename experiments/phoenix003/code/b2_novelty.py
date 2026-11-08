"""B2 — regulatory novelty of the matched token: was the product already regulated?

This is the check that separates a genuine *pre-regulatory* public record from a follow-up
study of a device that already had an FDA record. For every verified link it asks one
question, using only the regulatory corpus:

    at the evidence record's publication date, did ANY canonical regulatory record of any
    applicant already carry this distinctive token?

* if yes -> ``PRE_EXISTING_PRODUCT``: the evidence is surveillance/extension of a device that
  was already public in the regulatory sense. It cannot be "early evidence of a technology the
  world had not yet seen".
* if no  -> ``PRE_REGULATORY``: the information existed before the product had any regulatory
  footprint. This is the only class that may be called early evidence.

It also computes the protocol §4.4 Target-B flags for the anchors:
``target_b_novel`` = the anchor's distinctive token appears in no earlier regulatory record of
the firm and in no earlier regulatory record of any applicant.

Writes ``results/b2_novelty.json`` and rewrites ``EVIDENCE_LINKS.jsonl`` with the added fields
(a byte-stable rewrite of the same rows).
"""
from __future__ import annotations

import argparse
import collections
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import phoenix003_common as pc


def load_token_history(db_path: str):
    """token -> (first global decision date, first date per firm)."""
    rules = pc.load_rules()
    lineage = pc.load_lineage()
    resolver = pc.FirmResolver(lineage, rules)
    con = pc.connect_db(db_path)
    q = """
      select json_extract(payload,'$.device_name') as dn,
             json_extract(payload,'$.trade_name')  as tn,
             json_extract(payload,'$.generic_name') as gn,
             json_extract(payload,'$.supplement_number') as supp,
             applicant_raw, event_date, kind
      from events where kind in ('510k','pma')
    """
    first_global = {}
    first_firm = collections.defaultdict(dict)
    n = 0
    for r in con.execute(q):
        if r["kind"] == "pma" and (r["supp"] or "").strip():
            continue  # supplements are not milestones
        name = r["dn"] or r["tn"] or r["gn"] or ""
        d = pc.parse_date(r["event_date"])
        if not name or d is None:
            continue
        n += 1
        res = resolver.resolve(r["applicant_raw"] or "")
        firm = res["firm"]
        for tok in set(pc.token_list(name)):
            if len(tok) < 4 or not tok.isalpha():
                continue
            if tok not in first_global or d < first_global[tok]:
                first_global[tok] = d
            if firm:
                cur = first_firm[tok].get(firm)
                if cur is None or d < cur:
                    first_firm[tok][firm] = d
    con.close()
    return first_global, first_firm, n


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default="data/medradar.sqlite")
    args = ap.parse_args(argv)

    first_global, first_firm, n_milestones = load_token_history(args.db)
    print(f"canonical milestones used for token history: {n_milestones}; tokens: {len(first_global)}")

    rules = pc.load_rules()
    post_markers = [m.lower() for m in
                    rules.get("novelty", {}).get("post_approval_markers", [])]

    rows = [json.loads(line) for line in
            open(pc.EXPERIMENT_DIR / "EVIDENCE_LINKS.jsonl", encoding="utf-8")]
    anchors = [json.loads(line) for line in
               open(pc.EXPERIMENT_DIR / "REGULATORY_ANCHORS.jsonl", encoding="utf-8")]

    # ------------------------------------------------------------ per-link novelty
    status_counts = collections.Counter()
    for r in rows:
        tok = r.get("matched_token")
        if not tok or r["tier"] not in ("VERIFIED_L1", "VERIFIED_L2"):
            r["token_first_reg_date_global"] = None
            r["regulatory_status"] = "not_verified"
            continue
        fg = first_global.get(tok)
        ed = pc.parse_date(r["evidence_date"])
        r["token_first_reg_date_global"] = pc.iso(fg)
        text = (r.get("evidence_text") or r.get("evidence_title") or "").lower()
        marker = next((m for m in post_markers if m in text), None)
        if marker:
            # the record says in its own words that the device was already approved
            r["regulatory_status"] = "PRE_EXISTING_PRODUCT"
            r["status_reason"] = f"self_declared_post_approval:{marker}"
        elif fg is None or ed is None:
            r["regulatory_status"] = "unknown"
            r["status_reason"] = "no_token_history_or_date"
        elif fg <= ed:
            r["regulatory_status"] = "PRE_EXISTING_PRODUCT"
            r["status_reason"] = "earlier_regulatory_record_of_token"
        else:
            r["regulatory_status"] = "PRE_REGULATORY"
            r["status_reason"] = "no_earlier_regulatory_record_of_token"
        status_counts[r["regulatory_status"]] += 1

    pc.write_jsonl(pc.EXPERIMENT_DIR / "EVIDENCE_LINKS.jsonl", rows)

    # --------------------------------------------------------------- target B flags
    for a in anchors:
        toks = a.get("distinctive_tokens") or []
        adate = pc.parse_date(a["anchor_date"])
        firm = a["firm"]
        novel_flags = {}
        for tok in toks:
            fg = first_global.get(tok)
            ff = first_firm.get(tok, {}).get(firm)
            novel_flags[tok] = {
                "first_global": pc.iso(fg),
                "first_firm": pc.iso(ff),
                "novel_at_anchor_global": bool(fg is None or fg >= adate),
                "novel_at_anchor_firm": bool(ff is None or ff >= adate),
            }
        a["token_novelty"] = novel_flags
        a["target_b_novel"] = bool(toks) and all(v["novel_at_anchor_global"] for v in novel_flags.values())

    fields = list(anchors[0].keys())
    pc.write_jsonl(pc.EXPERIMENT_DIR / "REGULATORY_ANCHORS.jsonl", anchors)

    # -------------------------------------------------------------------- summary
    b = json.loads((pc.RESULTS / "b_links.json").read_text(encoding="utf-8"))
    summ = {s["anchor_id"]: s for s in b["anchor_summaries"]}
    per_anchor_status = {}
    for r in rows:
        if r["tier"] not in ("VERIFIED_L1", "VERIFIED_L2"):
            continue
        aid = r["anchor_id"]
        cur = per_anchor_status.get(aid)
        # an anchor counts as PRE_REGULATORY if at least one product-specific link is
        st = r["regulatory_status"]
        if cur is None:
            per_anchor_status[aid] = {"has": True, "pre_reg": st == "PRE_REGULATORY",
                                      "specific_pre_reg": st == "PRE_REGULATORY" and r.get("product_specific", False)}
        else:
            cur["pre_reg"] = cur["pre_reg"] or st == "PRE_REGULATORY"
            cur["specific_pre_reg"] = cur["specific_pre_reg"] or (
                st == "PRE_REGULATORY" and r.get("product_specific", False))

    anchors_with_pre_reg = sum(1 for v in per_anchor_status.values() if v["pre_reg"])
    anchors_with_specific_pre_reg = sum(1 for v in per_anchor_status.values()
                                        if v["specific_pre_reg"])
    target_b = [a["anchor_id"] for a in anchors if a.get("target_b_novel")]
    target_b_with_link = [aid for aid in target_b if aid in per_anchor_status]

    per_stratum = {}
    for st in sorted({a["stratum"] for a in anchors}):
        ids = {a["anchor_id"] for a in anchors if a["stratum"] == st}
        per_stratum[st] = {
            "anchors": len(ids),
            "target_b_novel": sum(1 for a in anchors
                                  if a["stratum"] == st and a.get("target_b_novel")),
            "pre_regulatory_link": sum(1 for aid, v in per_anchor_status.items()
                                       if aid in ids and v["pre_reg"]),
            "product_specific_pre_regulatory_link": sum(
                1 for aid, v in per_anchor_status.items()
                if aid in ids and v["specific_pre_reg"]),
        }

    out = {
        "generated_at": pc.utc_now_iso(),
        "canonical_milestones_used_for_token_history": n_milestones,
        "tokens_with_history": len(first_global),
        "link_status_counts": dict(status_counts),
        "anchors_total": len(anchors),
        "anchors_target_b_novel": len(target_b),
        "anchors_target_b_novel_with_verified_link": len(target_b_with_link),
        "anchors_with_pre_regulatory_link": anchors_with_pre_reg,
        "anchors_with_product_specific_pre_regulatory_link": anchors_with_specific_pre_reg,
        "per_stratum": per_stratum,
        "per_anchor": per_anchor_status,
        "target_b_anchor_ids": target_b,
    }
    pc.write_json(pc.RESULTS / "b2_novelty.json", out)
    print(json.dumps({k: out[k] for k in
                      ("link_status_counts", "anchors_target_b_novel",
                       "anchors_target_b_novel_with_verified_link",
                       "anchors_with_pre_regulatory_link",
                       "anchors_with_product_specific_pre_regulatory_link",
                       "per_stratum")}, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
