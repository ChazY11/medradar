"""STEP 1 (continued) — anchor-set state audit for BOTH states of the experiment directory:

  * SNAPSHOT — the artefacts as they stood when independent verification started
    (04:16:48-04:26:50: 268 anchors, ctgov-core-only links, provisional results), saved under
    verify/committed_snapshot/ before the author's re-run could overwrite them;
  * LIVE — whatever exists in results/ and REGULATORY_ANCHORS.jsonl now (the re-run started at
    04:57:26; A1 is the first stage it rewrites).

It proves which frozen-input state each anchor set was built from by rebuilding both from the
raw store with the verifier's own tokenizer:
    core-brand state  = exclude the five CORE firms' brand tokens only (Amendment 1 as written)
    v2 state          = exclude every brand token listed in current frozen_vocab.json
and compares the full integrity funnel with the matching results/a1_canonical.json.

Run:  python experiments/phoenix003/verify/verify_anchor_state.py
"""
from __future__ import annotations

import collections
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import vcommon as vc

HERE = Path(__file__).resolve().parent
SNAP = HERE / "committed_snapshot"
OUT = HERE / "out_anchor_state.json"


def load_jsonl_path(p):
    return [json.loads(x) for x in open(p, encoding="utf-8") if x.strip()]


def build(brandset, tokz, resolver, ms, rules):
    subst = rules["anchor"]["substantive_decision_codes"]
    funnel = collections.Counter()
    funnel["milestones_loaded"] = len(ms)
    attributed = []
    for m in ms:
        firm, tok = resolver.resolve(m["applicant_raw"])
        m = dict(m)
        m["firm"] = firm
        m["firm_matched_token"] = tok
        if firm:
            attributed.append(m)
    funnel["attributed_to_core_firm"] = len(attributed)
    keep = [m for m in attributed if (m["decision_code"] or "") in subst[m["source"]]]
    funnel["excluded_decision_code"] = len(attributed) - len(keep)
    funnel["after_decision_code"] = len(keep)
    keep2 = [m for m in keep if m["product_code"]]
    funnel["excluded_missing_product_code"] = len(keep) - len(keep2)
    funnel["after_product_code"] = len(keep2)

    with_tokens = []
    for m in keep2:
        toks = []
        for t in vc.tokens(m["name_raw"]):
            if len(t) < tokz.min_len or not t.isalpha():
                continue
            if t in vc._ROMAN or t in vc._UNITS:
                continue
            if t in tokz.stop_a or t in tokz.generic or t in brandset:
                continue
            if t not in toks:
                toks.append(t)
        m["distinctive_tokens"] = toks
        if toks:
            with_tokens.append(m)
    funnel["excluded_no_distinctive_token"] = len(keep2) - len(with_tokens)
    funnel["after_distinctive_token"] = len(with_tokens)

    by_fc = collections.defaultdict(list)
    for m in with_tokens:
        d = vc.parse_date(m["decision_date"])
        if d:
            by_fc[(m["firm"], m["product_code"])].append((d, m))
    funnel["firm_product_code_pairs"] = len(by_fc)

    anchors = {}
    for (firm, code), items in by_fc.items():
        items.sort(key=lambda x: (x[0], x[1]["milestone_key"]))
        d, m = items[0]
        if not (rules["anchor"]["window_start"] <= d.isoformat()
                <= rules["anchor"]["window_end"]):
            continue
        a = dict(m)
        a["anchor_date"] = d.isoformat()
        a["anchor_id"] = vc.sha256_text(f"{firm}|{code}|{m['milestone_key']}")
        anchors[(firm, code, m["milestone_key"])] = a
    funnel["first_in_code_inside_window"] = len(anchors)
    funnel["anchors"] = len(anchors)
    return anchors, funnel


def compare(committed, got, label):
    ck = set(committed)
    gk = set(got)
    print(f"  {label:34s} committed={len(ck)} mine={len(gk)} identical={len(ck & gk)} "
          f"missing-in-mine={len(ck - gk)} extra-in-mine={len(gk - ck)}")
    if ck - gk:
        print("    missing:", sorted(ck - gk))
    if gk - ck:
        print("    extra  :", sorted(gk - ck))
    id_ok = sum(1 for k in (ck & gk) if committed[k]["anchor_id"] == got[k]["anchor_id"])
    tok_ok = sum(1 for k in (ck & gk)
                 if sorted(committed[k]["distinctive_tokens"])
                 == sorted(got[k]["distinctive_tokens"]))
    print(f"    anchor_id equal {id_ok}/{len(ck & gk)}; distinctive_tokens equal {tok_ok}/{len(ck & gk)}")
    return ck, gk


def funnel_compare(com, mine, label):
    keys = ["milestones_loaded", "attributed_to_core_firm", "excluded_decision_code",
            "after_decision_code", "excluded_missing_product_code", "after_product_code",
            "excluded_no_distinctive_token", "after_distinctive_token",
            "firm_product_code_pairs", "first_in_code_inside_window", "anchors"]
    print(f"\nfunnel: {label}")
    same = True
    for k in keys:
        a, b = com.get(k), mine.get(k)
        if a != b:
            same = False
        print(f"   {k:32s} committed={a!s:>8}  mine={b!s:>8}{'' if a == b else '   <-- DIFF'}")
    print(f"   identical: {same}")
    return same


def main():
    rules = vc.load_json(vc.EXP / "FROZEN_RULES.json")
    lineage = vc.load_json(vc.DATASET / "firm_lineage.json")
    vocab = vc.load_json(vc.DATASET / "frozen_vocab.json")
    tokz = vc.Tokenizer()
    resolver = vc.Resolver()
    con = vc.connect_ro()
    ms, supp, raw, missing = vc.load_milestones(con)

    core_brand = set()
    for f in rules["firms"]["core"]:
        core_brand |= set(lineage["brand_tokens"][f]["any_token"])
    all_brand = set(vocab["brand_tokens"])

    a_core, funnel_core = build(core_brand, tokz, resolver, ms, rules)
    a_v2, funnel_v2 = build(all_brand, tokz, resolver, ms, rules)
    print("=" * 78)
    print("ANCHOR-SET STATE AUDIT")
    print("=" * 78)
    print(f"my reconstruction, core-brand tokenizer : {len(a_core)} anchors")
    print(f"my reconstruction, frozen_vocab v2      : {len(a_v2)} anchors")
    print(f"raw rows 510k={raw['510k']} pma={raw['pma']}  supplements={len(supp)}  "
          f"canonical milestones={len(ms)}")
    print(f"distinct milestone_key={len(set(m['milestone_key'] for m in ms))}")

    results = {}
    # ------------------------------------------------------------------ SNAPSHOT state
    snap_anchors = load_jsonl_path(SNAP / "REGULATORY_ANCHORS.jsonl")
    snap_map = {(a["firm"], a["product_code"], a["milestone_key"]): a for a in snap_anchors}
    print(f"\nSNAPSHOT state (before re-run): {len(snap_anchors)} anchors")
    _, g1 = compare(snap_map, a_core, "snapshot vs core-brand rebuild")
    compare(snap_map, a_v2, "snapshot vs v2 rebuild")
    snap_a1 = json.load(open(SNAP / "a1_canonical.json", encoding="utf-8"))
    results["snapshot_funnel_identical_core"] = funnel_compare(
        snap_a1["funnel"], funnel_core, "snapshot a1_canonical vs core-brand rebuild")

    # ---------------------------------------------------------------------- LIVE state
    live_anchors = vc.committed_anchors()
    live_map = {(a["firm"], a["product_code"], a["milestone_key"]): a for a in live_anchors}
    print(f"\nLIVE state: {len(live_anchors)} anchors")
    if len(live_anchors) != len(snap_anchors) or set(live_map) != set(snap_map):
        print("  live anchor set DIFFERS from the snapshot (re-run in progress or finished)")
    _, g2 = compare(live_map, a_v2, "live vs v2 rebuild")
    compare(live_map, a_core, "live vs core-brand rebuild")
    live_a1_path = vc.RESULTS / "a1_canonical.json"
    if live_a1_path.exists():
        live_a1 = json.load(open(live_a1_path, encoding="utf-8"))
        results["live_funnel_identical_v2"] = funnel_compare(
            live_a1["funnel"], funnel_v2, "live a1_canonical vs v2 rebuild")
        results["live_a1"] = live_a1
    print(f"\nlive a1_canonical outputs block: "
          f"{json.dumps(live_a1.get('outputs'), indent=1) if live_a1_path.exists() else 'absent'}")

    # differences between snapshot and live anchor sets
    print("\nSNAPSHOT-only / LIVE-only anchors (the re-run's anchor delta):")
    for k in sorted(set(snap_map) - set(live_map)):
        print(f"   snapshot-only {k}  tokens={snap_map[k]['distinctive_tokens']}")
    for k in sorted(set(live_map) - set(snap_map)):
        print(f"   live-only     {k}  tokens={live_map[k]['distinctive_tokens']}")

    payload = {
        "my_core_brand_anchors": len(a_core),
        "my_v2_anchors": len(a_v2),
        "funnel_core_brand": dict(funnel_core),
        "funnel_v2": dict(funnel_v2),
        "snapshot_anchors": len(snap_anchors),
        "live_anchors": len(live_anchors),
        "snapshot_funnel_identical_core": results.get("snapshot_funnel_identical_core"),
        "live_funnel_identical_v2": results.get("live_funnel_identical_v2"),
        "snapshot_only": [list(k) for k in sorted(set(snap_map) - set(live_map))],
        "live_only": [list(k) for k in sorted(set(live_map) - set(snap_map))],
        "snapshot_a1_funnel": snap_a1["funnel"],
        "live_a1_funnel": results.get("live_a1", {}).get("funnel"),
    }
    OUT.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"\nwrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
