"""STEP 1 — independent re-derivation of the canonical milestone set and Target-A anchors.

Everything is rebuilt from data/medradar.sqlite (read-only) with the verifier's own brand-token
resolver and tokenizer. The committed REGULATORY_ANCHORS.jsonl is compared only on identity
fields: (firm, product_code, milestone_key).

Run:  python experiments/phoenix003/verify/verify_anchors.py
"""
from __future__ import annotations

import collections
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import vcommon as vc

OUT = Path(__file__).resolve().parent / "out_anchors.json"


def main():
    rules = vc.load_json(vc.EXP / "FROZEN_RULES.json")
    resolver = vc.Resolver()
    tokz = vc.Tokenizer()
    con = vc.connect_ro()

    ms, supp, raw, missing = vc.load_milestones(con)

    # ---------------------------------------------------------------- raw counts
    print("=" * 78)
    print("ANCHOR CONSTRUCTION — independent re-derivation")
    print("=" * 78)
    print(f"raw 510k rows                       : {raw['510k']}")
    print(f"raw pma rows                        : {raw['pma']}")
    print(f"raw rows total                      : {raw['510k'] + raw['pma']}")
    print(f"rows without identifier (excluded)  : {missing['missing_identifier']}")
    print(f"pma rows that are supplements       : {len(supp)}")
    print(f"supplement decision codes           : {dict(collections.Counter(s['decision_code'] or '<none>' for s in supp).most_common(10))}")

    # --------------------------------------------------- identity-key integrity
    k510 = [m for m in ms if m["kind"] == "510k"]
    kpma = [m for m in ms if m["kind"] == "pma"]
    kcnt = collections.Counter(m["official_id"] for m in k510)
    dup_k = {k: c for k, c in kcnt.items() if c > 1}
    print(f"distinct k_number (canonical 510k)  : {len(kcnt)}   duplicate values: {len(dup_k)}"
          f"   extra rows: {sum(c - 1 for c in dup_k.values())}")
    if dup_k:
        print("  duplicate k_number examples       :", list(dup_k.items())[:5])

    # PMA pairs over ALL pma rows (originals + supplements)
    con2 = con
    pair_rows = []
    for r in con2.execute("""
        select json_extract(payload,'$.pma_number') as pn,
               json_extract(payload,'$.supplement_number') as sn
        from events where kind='pma'"""):
        pair_rows.append(((r["pn"] or "").strip(), (r["sn"] or "").strip()))
    pcnt = collections.Counter(pair_rows)
    dup_p = {k: c for k, c in pcnt.items() if c > 1}
    pnum = collections.Counter(p for p, s in pair_rows if p)
    dup_pnum = {k: c for k, c in pnum.items() if c > 1}
    print(f"distinct (pma_number,supplement_number): {len(pcnt)}   duplicate tuples: {len(dup_p)}"
          f"   extra rows: {sum(c - 1 for c in dup_p.values())}")
    print(f"distinct pma_number (all pma rows)  : {len(pnum)}   pma_numbers with >1 row: {len(dup_pnum)}"
          f"   extra rows: {sum(c - 1 for c in dup_pnum.values())}")
    if dup_pnum:
        print("  most repeated pma_number          :",
              sorted(dup_pnum.items(), key=lambda kv: -kv[1])[:3])
    orig_cnt = collections.Counter(m["official_id"] for m in kpma)
    dup_orig = {k: c for k, c in orig_cnt.items() if c > 1}
    print(f"distinct pma_number (originals only) : {len(orig_cnt)}   duplicate originals: {len(dup_orig)}")

    mkey = collections.Counter(m["milestone_key"] for m in ms)
    dup_mkey = {k: c for k, c in mkey.items() if c > 1}
    print(f"canonical milestones loaded         : {len(ms)}  (510k {len(k510)}, pma orig {len(kpma)})")
    print(f"distinct milestone_key              : {len(mkey)}   repeated keys: {len(dup_mkey)}"
          f"   extra rows: {sum(c - 1 for c in dup_mkey.values())}")

    # natural-key collisions (same definition as the committed audit)
    natural = collections.Counter(
        (m["applicant_raw"].upper(), vc.norm(m["name_raw"]), m["decision_date"], m["product_code"])
        for m in ms)
    nat_coll = {k: c for k, c in natural.items() if c > 1}
    print(f"natural-key collisions              : {len(nat_coll)}   extra rows: {sum(c - 1 for c in nat_coll.values())}")

    # ------------------------------------------------------------- attribution
    attr = collections.Counter()
    per_firm = collections.Counter()
    per_firm_strict = collections.Counter()   # brand token at position <= 1 and no parentheses
    collisions = []
    lineage = vc.load_json(vc.DATASET / "firm_lineage.json")
    for m in ms:
        firm, matched = resolver.resolve(m["applicant_raw"])
        m["firm"] = firm
        m["matched_token"] = matched
        toks = vc.tokens(m["applicant_raw"])
        if firm:
            per_firm[firm] += 1
            brand = set(lineage["brand_tokens"][firm]["any_token"])
            pos = [i for i, t in enumerate(toks) if t in brand]
            strict = bool(pos) and min(pos) <= 1 and not ("(" in m["applicant_raw"] and ")" in m["applicant_raw"])
            m["strict"] = strict
            if strict:
                per_firm_strict[firm] += 1
        else:
            m["strict"] = False
        multi = resolver.all_matching_firms(m["applicant_raw"])
        if len(multi) > 1:
            collisions.append((m["applicant_raw"], multi))
    attributed = [m for m in ms if m["firm"]]
    print(f"attributed milestones               : {len(attributed)}  (unknown {len(ms)-len(attributed)}, "
          f"rate {(len(ms)-len(attributed))/len(ms):.6f})")
    print("attribution per firm (inclusive)    :", dict(sorted(per_firm.items())))
    print("attribution per firm (strict)       :", dict(sorted(per_firm_strict.items())))
    print(f"applicants matching >1 brand rule   : {len(collisions)}", collisions[:5])

    # ------------------------------------------------------- token + anchor build
    subst = rules["anchor"]["substantive_decision_codes"]
    win_start, win_end = rules["anchor"]["window_start"], rules["anchor"]["window_end"]

    def tokenise(m):
        m["distinctive_tokens"] = tokz.distinctive(m["name_raw"])
        m["all_tokens"] = tokz.all_tokens(m["name_raw"])
        return m

    variants = {}

    # Variant A (the committed reading): decision-code -> product-code -> token filters first,
    # then the first milestone inside each (firm, product code) cell.
    keep = [m for m in attributed if (m["decision_code"] or "") in subst[m["source"]]]
    keep = [m for m in keep if m["product_code"]]
    keep = [tokenise(m) for m in keep]
    keep = [m for m in keep if m["distinctive_tokens"]]
    by_fc = collections.defaultdict(list)
    for m in keep:
        d = vc.parse_date(m["decision_date"])
        if d:
            by_fc[(m["firm"], m["product_code"])].append((d, m))
    anchorsA = []
    for (firm, code), items in by_fc.items():
        items.sort(key=lambda x: (x[0], x[1]["milestone_key"]))
        d, m = items[0]
        if win_start <= d.isoformat() <= win_end:
            a = dict(m)
            a["anchor_date"] = d.isoformat()
            a["anchor_year"] = d.year
            a["anchor_id"] = vc.sha256_text(f"{firm}|{code}|{m['milestone_key']}")
            a["prior_in_code"] = len(items)
            anchorsA.append(a)
    variants["A_filters_then_first"] = anchorsA

    # Variant B (literal protocol 4.3): first canonical milestone in the cell, then filter.
    attrib_by_fc = collections.defaultdict(list)
    for m in attributed:
        d = vc.parse_date(m["decision_date"])
        if d:
            attrib_by_fc[(m["firm"], m["product_code"])].append((d, m))
    anchorsB = []
    for (firm, code), items in attrib_by_fc.items():
        items.sort(key=lambda x: (x[0], x[1]["milestone_key"]))
        d, m = items[0]
        if not (win_start <= d.isoformat() <= win_end):
            continue
        if (m["decision_code"] or "") not in subst[m["source"]]:
            continue
        if not code:
            continue
        tokenise(m)
        if not m["distinctive_tokens"]:
            continue
        a = dict(m)
        a["anchor_date"] = d.isoformat()
        a["anchor_year"] = d.year
        a["anchor_id"] = vc.sha256_text(f"{firm}|{code}|{m['milestone_key']}")
        anchorsB.append(a)
    variants["B_first_then_filters"] = anchorsB

    committed = vc.committed_anchors()
    ckey = {(a["firm"], a["product_code"], a["milestone_key"]): a for a in committed}

    print("\n" + "-" * 78)
    print("ANCHOR SET COMPARISON BY (firm, product_code, milestone_key)")
    print("-" * 78)
    print(f"committed REGULATORY_ANCHORS.jsonl rows : {len(committed)}")
    for name, got in list(variants.items()):
        gkey = {(a["firm"], a["product_code"], a["milestone_key"]): a for a in got}
        missing = sorted(set(ckey) - set(gkey))
        extra = sorted(set(gkey) - set(ckey))
        print(f"variant {name}: my anchors={len(got)}  identical={len(set(gkey) & set(ckey))}"
              f"  missing-in-mine={len(missing)}  extra-in-mine={len(extra)}")
        if name == "A_filters_then_first":
            variants["A_missing"] = missing
            variants["A_extra"] = extra

    A = variants["A_filters_then_first"]
    gkey = {(a["firm"], a["product_code"], a["milestone_key"]): a for a in A}
    missing = variants["A_missing"]
    extra = variants["A_extra"]
    if missing:
        print("MISSING-in-mine examples:", missing[:8])
    if extra:
        print("EXTRA-in-mine examples  :", extra[:8])

    # per-firm / per-year / per-kind side by side (variant A)
    def dist(rows, field):
        return dict(sorted(collections.Counter(r[field] for r in rows).items()))
    mine_pf = dist(A, "firm")
    com_pf = dist(committed, "firm")
    print("\nper-firm anchors  mine vs committed:")
    for f in sorted(set(mine_pf) | set(com_pf)):
        flag = "" if mine_pf.get(f) == com_pf.get(f) else "   <-- DIFF"
        print(f"  {f:22s} mine={mine_pf.get(f):3d}  committed={com_pf.get(f):3d}{flag}")
    mine_py = collections.Counter(a["anchor_year"] for a in A)
    com_py = collections.Counter(a["anchor_year"] for a in committed)
    print("per-year anchors  mine vs committed:",
          {y: (mine_py.get(y, 0), com_py.get(y, 0)) for y in sorted(set(mine_py) | set(com_py))})
    print("per-kind anchors  mine vs committed:",
          {k: (sum(1 for a in A if a["kind"] == k), sum(1 for a in committed if a["kind"] == k))
           for k in ("510k", "pma")})
    print("distinct product codes mine vs committed:",
          len({a["product_code"] for a in A}), len({a["product_code"] for a in committed}))
    mine_strict = sum(1 for a in A if a.get("strict"))
    print(f"strict attribution share mine={mine_strict/len(A):.6f}  committed="
          f"{sum(1 for a in committed if a.get('strict_attribution'))/len(committed):.6f}")

    # anchor_id check + token-set agreement on the intersection
    id_ok = sum(1 for a in A if a["anchor_id"] == ckey[(a["firm"], a["product_code"], a["milestone_key"])]["anchor_id"])
    print(f"anchor_id recomputed equal          : {id_ok}/{len(A)}")
    tok_diff = []
    for a in A:
        k = (a["firm"], a["product_code"], a["milestone_key"])
        c = ckey.get(k)
        if c and sorted(a["distinctive_tokens"]) != sorted(c.get("distinctive_tokens") or []):
            tok_diff.append((k, a["distinctive_tokens"], c.get("distinctive_tokens")))
    print(f"distinctive_tokens identical        : {len(A)-len(tok_diff)}/{len(A)}")
    for x in tok_diff[:5]:
        print("  token diff:", x)
    # extra-stoplist sensitivity: does ignoring name_stoplist_extra.txt change any anchor token?
    extra_only = {t for t in tokz.extra if t not in tokz.generic and t not in tokz.stop_a}
    tok_without_extra = []
    for a in A:
        t2 = tokz.distinctive(a["name_raw"], use_extra=False)
        if sorted(t2) != sorted(a["distinctive_tokens"]):
            tok_without_extra.append((a["milestone_key"], a["distinctive_tokens"], t2))
    print(f"anchors whose token set differs if name_stoplist_extra.txt is ignored: {len(tok_without_extra)}")
    for x in tok_without_extra[:5]:
        print("   ", x)
    print(f"name_stoplist_extra tokens not already in generic/partA: {len(extra_only)}; sample {sorted(extra_only)[:10]}")

    # ---------------------------------------------------------------- persist
    payload = {
        "raw_rows": raw,
        "rows_without_identifier": missing,
        "pma_supplement_rows": len(supp),
        "supplement_decision_codes": dict(collections.Counter(s["decision_code"] or "<none>" for s in supp)),
        "canonical_milestones": len(ms),
        "canonical_510k": len(k510),
        "canonical_pma_originals": len(kpma),
        "distinct_k_number": len(kcnt),
        "duplicate_k_number_values": len(dup_k),
        "duplicate_k_number_extra_rows": sum(c - 1 for c in dup_k.values()),
        "distinct_pma_pairs_all_rows": len(pcnt),
        "duplicate_pma_pair_tuples": len(dup_p),
        "duplicate_pma_pair_extra_rows": sum(c - 1 for c in dup_p.values()),
        "distinct_pma_number_all_rows": len(pnum),
        "distinct_pma_number_originals": len(orig_cnt),
        "duplicate_originals": len(dup_orig),
        "duplicate_milestone_keys": {k: c for k, c in dup_mkey.items()},
        "natural_key_collision_count": len(nat_coll),
        "natural_key_collision_extra_rows": sum(c - 1 for c in nat_coll.values()),
        "attribution_inclusive": dict(sorted(per_firm.items())),
        "attribution_strict": dict(sorted(per_firm_strict.items())),
        "attributed_total": len(attributed),
        "unknown_total": len(ms) - len(attributed),
        "multi_brand_applicants": collisions[:20],
        "anchors_variant_A": len(A),
        "anchors_variant_B": len(variants["B_first_then_filters"]),
        "committed_anchors": len(committed),
        "missing_in_mine": [list(x) for x in missing],
        "extra_in_mine": [list(x) for x in extra],
        "per_firm_mine": mine_pf,
        "per_firm_committed": com_pf,
        "anchor_id_ok": id_ok,
        "token_diffs": [list(x) for x in tok_diff],
        "token_diff_without_extra_stoplist": len(tok_without_extra),
    }
    OUT.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"\nwrote {OUT}")

    # detail: variant B differences vs committed (to show the protocol ambiguity is immaterial)
    if variants["B_first_then_filters"]:
        bk = {(a["firm"], a["product_code"], a["milestone_key"]) for a in variants["B_first_then_filters"]}
        print(f"variant B vs committed: missing={len(set(ckey)-bk)} extra={len(bk-set(ckey))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
