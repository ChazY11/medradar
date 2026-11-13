"""FINAL-STATE verification of PHOENIX-003 (post-fix run, manifest generated_at 2026-11-09T05:16:11+08).

Deliberately reads the pinned snapshot `verify/final_snapshot/` (not the live tree) so the result is
reproducible even if the author iterates again. Covers every fix claimed after the independent
verification report:

  1. L1 5-year evidence window        -> all L1 rows inside window; max lead <= window span
  2. EPMC match field                 -> title+abstract only; no keyword/MeSH-only verified row
  3. Amendment 6 post-approval markers-> reclassifications counted; marker list audited for
                                         over-breadth (esp. "continued access")
  4. Amendment 5 literature rarity    -> strict ladder 28; rare set recomputed from the corpus;
                                         ordinary-word survival audit
  5. ZIMMER exclusion                 -> anchors 266, Zimmer Biomet 12, no MEDIZINSYSTEME anchor
  6. Emission cap                     -> every verified row present; no __emission_capped_l1l2
  7. Reporting defects                -> matched-denominator specificity, c4b=2000, note text
  8. Process                          -> manifest matches disk; anchors exactly reproducible

plus: re-derive k / ladder / medians / specificity / placebo p / verdict, and audit the current
largest admissible strict case end-to-end.

Run:  python experiments/phoenix003/verify/verify_final.py
"""
from __future__ import annotations

import collections
import hashlib
import itertools
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import vcommon as vc

HERE = Path(__file__).resolve().parent
PIN = HERE / "final_snapshot"
REPO = vc.REPO
NCT_RE = re.compile(r"NCT\d{8}")
EPMC_SKIP = {"PAT"}


def load_pin(name):
    return json.load(open(PIN / name, encoding="utf-8"))


def load_pin_jsonl(name):
    return [json.loads(x) for x in open(PIN / name, encoding="utf-8") if x.strip()]


def short(s, n=100):
    return (s or "")[:n]


# ------------------------------------------------------------------ 1. manifest
def check_manifest():
    m = load_pin("manifest.json")
    print("=" * 78)
    print(f"1. MANIFEST   generated_at={m['generated_at']} stages_rc={ {k:v['returncode'] for k,v in m['stages'].items()} }")
    print("=" * 78)
    bad, missing = [], 0
    for f in m["files"]:
        p = REPO / f["path"]
        if not p.exists():
            missing += 1
            bad.append((f["path"], "MISSING"))
            continue
        h = hashlib.sha256(p.read_bytes()).hexdigest()
        if h != f["sha256"] or p.stat().st_size != f["bytes"]:
            bad.append((f["path"], "MISMATCH"))
    print(f"manifest files={len(m['files'])} missing={missing} mismatches={len(bad)}")
    for b in bad[:10]:
        print("  ", b)
    print(f"FROZEN_RULES sha (pinned)={hashlib.sha256((PIN/'FROZEN_RULES.json').read_bytes()).hexdigest()[:16]}")
    return {"generated_at": m["generated_at"], "files": len(m["files"]),
            "missing": missing, "mismatches": bad}


# ------------------------------------------------------------------ 2. anchors
def rebuild_anchors(ms, rules, resolver, tokz):
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
        toks = tokz.distinctive(m["name_raw"])
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
        if not (rules["anchor"]["window_start"] <= d.isoformat() <= rules["anchor"]["window_end"]):
            continue
        a = dict(m)
        a["anchor_date"] = d.isoformat()
        a["anchor_id"] = vc.sha256_text(f"{firm}|{code}|{m['milestone_key']}")
        anchors[(firm, code, m["milestone_key"])] = a
    funnel["first_in_code_inside_window"] = len(anchors)
    funnel["anchors"] = len(anchors)
    return anchors, funnel


def check_anchors(rules):
    print("\n" + "=" * 78)
    print("2. ANCHORS — exact reproduction from store + current frozen inputs")
    print("=" * 78)
    con = vc.connect_ro()
    ms, supp, raw, missing = vc.load_milestones(con)
    resolver = vc.Resolver()
    tokz = vc.Tokenizer()
    mine, funnel = rebuild_anchors(ms, rules, resolver, tokz)
    committed = load_pin_jsonl("REGULATORY_ANCHORS.jsonl")
    ck = {(a["firm"], a["product_code"], a["milestone_key"]): a for a in committed}
    print(f"my anchors={len(mine)} committed={len(ck)} identical={len(set(mine)&set(ck))}"
          f" missing-in-mine={len(set(ck)-set(mine))} extra-in-mine={len(set(mine)-set(ck))}")
    if set(ck) - set(mine):
        print("  missing:", sorted(set(ck) - set(mine))[:5])
    if set(mine) - set(ck):
        print("  extra:", sorted(set(mine) - set(ck))[:5])
    id_ok = sum(1 for k in set(mine) & set(ck) if mine[k]["anchor_id"] == ck[k]["anchor_id"])
    tok_ok = sum(1 for k in set(mine) & set(ck)
                 if sorted(mine[k]["distinctive_tokens"]) == sorted(ck[k]["distinctive_tokens"]))
    print(f"anchor_id equal {id_ok}/{len(set(mine)&set(ck))}; tokens equal {tok_ok}/{len(set(mine)&set(ck))}")
    a1 = load_pin("a1_canonical.json")
    keys = ["milestones_loaded", "attributed_to_core_firm", "excluded_decision_code",
            "after_decision_code", "excluded_missing_product_code", "after_product_code",
            "excluded_no_distinctive_token", "after_distinctive_token",
            "firm_product_code_pairs", "first_in_code_inside_window", "anchors"]
    same = True
    for k in keys:
        a, b = a1["funnel"].get(k), funnel.get(k)
        if a != b:
            same = False
            print(f"  FUNNEL DIFF {k}: committed={a} mine={b}")
    print(f"funnel identical: {same}")
    print(f"per-firm: {dict(sorted(collections.Counter(a['firm'] for a in committed).items()))}")
    z = [a for a in committed if a["firm"] == "zimmer_biomet"]
    print(f"zimmer_biomet anchors={len(z)}; MEDIZINSYSTEME applicants: "
          f"{[a['applicant_raw'] for a in committed if 'MEDIZINSYSTEME' in vc.norm(a['applicant_raw'])]}")
    print(f"attributed milestones committed={a1['attribution']['attributed_to_core_firm']} "
          f"unknown={a1['attribution']['unknown']} rate={a1['attribution']['unknown_rate']}")
    return {"my_anchors": len(mine), "committed": len(ck),
            "identical": len(set(mine) & set(ck)),
            "missing": [list(x) for x in sorted(set(ck) - set(mine))],
            "extra": [list(x) for x in sorted(set(mine) - set(ck))],
            "funnel_identical": same, "committed_funnel": a1["funnel"],
            "my_funnel": dict(funnel), "per_firm": dict(collections.Counter(a['firm'] for a in committed))}


# ------------------------------------------------------------------ corpora
def load_corpora(resolver):
    ct, ep = [], []
    for name in ("ctgov_compact.jsonl.gz", "ctgov_ext_compact.jsonl.gz"):
        p = vc.DATASET / name
        if not p.exists():
            continue
        for r in vc.read_jsonl_gz(p):
            iv = [x.get("name") or "" for x in (r.get("interventions") or []) if isinstance(x, dict)]
            firms = [f for f in str(r.get("source_firm") or "").split("+") if f]
            fv = set()
            for s in [r.get("lead_sponsor") or ""] + list(r.get("collaborators") or []):
                f, _ = resolver.resolve(str(s))
                if f:
                    fv.add(f)
            ct.append({
                "src": "ctgov", "id": r["nct_id"], "firms": firms, "firm_verified": fv,
                "title": r.get("brief_title") or "", "date": vc.parse_date(r.get("first_posted")),
                "date_str": r.get("first_posted"),
                "date_sens": r.get("last_update_posted"),
                "match_tokens": set(vc.tokens(r.get("brief_title") or "")) | {
                    t for x in iv for t in vc.tokens(x)},
                "all_tokens": set(vc.tokens(" ".join([r.get("brief_title") or "",
                                                      r.get("official_title") or ""] + iv + [
                                                          str(c) for c in (r.get("conditions") or [])]))),
                "text": " ".join([r.get("brief_title") or "", r.get("official_title") or ""] + iv),
            })
    df = collections.Counter()
    for name in ("epmc_compact.jsonl.gz", "epmc_ext_compact.jsonl.gz"):
        p = vc.DATASET / name
        if not p.exists():
            continue
        for r in vc.read_jsonl_gz(p):
            if str(r.get("source") or "").upper() in EPMC_SKIP:
                continue
            title = r.get("title") or ""
            abstract = r.get("abstract") or ""
            keywords = r.get("keywords") or []
            firms = [f for f in str(r.get("source_firm") or "").split("+") if f]
            fv = set()
            for a in r.get("firm_affiliations") or []:
                f, _ = resolver.resolve(str(a))
                if f:
                    fv.add(f)
            toks = set(vc.tokens(title)) | set(vc.tokens(abstract))
            for t in keywords:
                toks |= set(vc.tokens(str(t)))
            for t in toks:
                df[t] += 1
            ep.append({
                "src": "epmc", "id": r.get("pmid") or r.get("doi") or r.get("id"),
                "firms": firms, "firm_verified": fv, "title": title,
                "date": vc.parse_date(r.get("first_publication_date")),
                "date_str": r.get("first_publication_date"),
                "date_sens": r.get("first_index_date") or r.get("electronic_publication_date"),
                "match_tokens": set(vc.tokens(title)) | set(vc.tokens(abstract)),
                "all_tokens": (set(vc.tokens(title)) | set(vc.tokens(abstract)) |
                               set(t for k in keywords for t in vc.tokens(str(k))) |
                               set(t for k in (r.get("mesh_terms") or []) for t in vc.tokens(str(k)))),
                "text": title + " " + abstract,
                "nct_ids": sorted(set(NCT_RE.findall(title + " " + abstract))),
            })
    return ct, ep, df


def derive_verified(anchors, ct, ep, rules):
    years = int(rules["evidence"]["window_years_before_anchor"])
    pools = collections.defaultdict(list)
    for r in ct:
        for f in r["firms"]:
            if f in r["firm_verified"]:
                pools[("ctgov", f)].append(r)
    for r in ep:
        for f in r["firms"]:
            if f in r["firm_verified"]:
                pools[("epmc", f)].append(r)
    ct_by_id = {r["id"]: r for r in ct}
    firm_ncts = collections.defaultdict(set)
    for r in ct:
        for f in r["firms"]:
            if f in r["firm_verified"]:
                firm_ncts[f].add(r["id"])
    index = collections.defaultdict(list)
    for (src, firm), recs in pools.items():
        for r in recs:
            for t in r["match_tokens"]:
                index[(src, firm, t)].append(r)
    rows = []
    for a in anchors:
        firm = a["firm"]
        adate = vc.parse_date(a["anchor_date"])
        w0 = vc.years_before(adate, years)
        seen = set()
        for tok in (a.get("distinctive_tokens") or []):
            for src in ("ctgov", "epmc"):
                for r in index.get((src, firm, tok), []):
                    d = r["date"]
                    if d is None or d >= adate or d < w0:
                        continue  # protocol 5: window applies to every tier
                    key = (src, r["id"], tok)
                    if key in seen:
                        continue
                    seen.add(key)
                    tier = "VERIFIED_L2"
                    if src == "epmc":
                        for nct in r.get("nct_ids", []):
                            c = ct_by_id.get(nct)
                            if (c and firm in c["firm_verified"] and firm in c["firms"]
                                    and tok in c["match_tokens"]):
                                tier = "VERIFIED_L1"
                                break
                    rows.append({"anchor_id": a["anchor_id"], "firm": firm,
                                 "milestone_key": a["milestone_key"],
                                 "product_code": a["product_code"], "anchor_date": a["anchor_date"],
                                 "tier": tier, "source": src, "evidence_id": r["id"],
                                 "evidence_date": r["date_str"], "matched_token": tok,
                                 "lead_days": (adate - d).days, "record": r,
                                 "_in_window": True})
    return rows


# ------------------------------------------------------------------ main
def main():
    rules = json.load(open(PIN / "FROZEN_RULES.json", encoding="utf-8"))
    anchors_list = load_pin_jsonl("REGULATORY_ANCHORS.jsonl")
    anchors = {a["anchor_id"]: a for a in anchors_list}
    links = load_pin_jsonl("EVIDENCE_LINKS.jsonl")
    out = {}
    out["manifest"] = check_manifest()
    out["anchors"] = check_anchors(rules)

    resolver = vc.Resolver()
    tokz = vc.Tokenizer()
    con = vc.connect_ro()
    ms, _, _, _ = vc.load_milestones(con)
    ct, ep, epmc_df = load_corpora(resolver)
    print(f"\ncorpora: ctgov={len(ct)} epmc={len(ep)} (PAT excluded); EPMC distinct tokens={len(epmc_df)}")
    mine_rows = derive_verified(anchors_list, ct, ep, rules)
    print(f"my verified rows={len(mine_rows)} anchors={len({r['anchor_id'] for r in mine_rows})}"
          f" tiers={dict(collections.Counter(r['tier'] for r in mine_rows))}")

    # ------------------------------------------------ 3. link comparison / cap / fields
    com_v = [r for r in links if r["tier"] in ("VERIFIED_L1", "VERIFIED_L2")]
    b = load_pin("b_links.json")
    print("\n" + "=" * 78)
    print("3. LINKS — completeness, L1 window, EPMC field")
    print("=" * 78)
    print(f"committed verified rows={len(com_v)} (L1={sum(1 for r in com_v if r['tier']=='VERIFIED_L1')},"
          f" L2={sum(1 for r in com_v if r['tier']=='VERIFIED_L2')}); file rows={len(links)}")
    print(f"b_links tier_counts={b['tier_counts']} AWVL={b['anchors_with_verified_link']}")
    cap = b["tier_counts"].get("__emission_capped_l1l2", 0)
    cap_rows = b["tier_counts"].get("__emission_capped_rows", 0)
    print(f"__emission_capped_l1l2={cap}  __emission_capped_rows={cap_rows} (expect 0 / only L4-L5)")
    my_set = {(r["anchor_id"], r["evidence_id"], r["matched_token"], r["tier"]) for r in mine_rows}
    com_set = {(r["anchor_id"], r["evidence_id"], r["matched_token"], r["tier"]) for r in com_v}
    print(f"row sets: mine={len(my_set)} committed={len(com_set)} identical={len(my_set&com_set)}"
          f" mine-only={len(my_set-com_set)} com-only={len(com_set-my_set)}")
    for x in sorted(com_set - my_set)[:5]:
        print("  com-only", x)
    for x in sorted(my_set - com_set)[:5]:
        print("  mine-only", x)
    my_lead = {aid: max(r["lead_days"] for r in rows)
               for aid, rows in itertools.groupby(sorted(mine_rows, key=lambda r: r["anchor_id"]),
                                                    key=lambda r: r["anchor_id"])}
    com_lead = {}
    for r in com_v:
        com_lead[r["anchor_id"]] = max(com_lead.get(r["anchor_id"], -10**9), r["lead_days"])
    lead_diff = sorted((a, my_lead[a], com_lead[a]) for a in set(my_lead) & set(com_lead)
                       if my_lead[a] != com_lead[a])
    print(f"k: mine={len(my_lead)} committed={len(com_lead)} identical={len(set(my_lead)&set(com_lead))}"
          f" only-mine={sorted(set(my_lead)-set(com_lead))} only-committed={sorted(set(com_lead)-set(my_lead))}"
          f" lead-diff={len(lead_diff)}")
    for d in lead_diff[:8]:
        print("  lead-diff", d)

    # L1 window
    viol = []
    for r in com_v:
        if r["tier"] != "VERIFIED_L1":
            continue
        a = anchors[r["anchor_id"]]
        adate = vc.parse_date(a["anchor_date"])
        w0 = vc.years_before(adate, 5)
        d = vc.parse_date(r["evidence_date"])
        if d is None or not (w0 <= d < adate):
            viol.append((r["milestone_key"], r["matched_token"], r["evidence_date"], r["lead_days"]))
    max_lead = max(r["lead_days"] for r in com_v)
    spans = []
    for r in com_v:
        a = anchors[r["anchor_id"]]
        adate = vc.parse_date(a["anchor_date"])
        spans.append((adate - vc.years_before(adate, 5)).days)
    print(f"L1 rows={sum(1 for r in com_v if r['tier']=='VERIFIED_L1')} outside-window={len(viol)}; "
          f"max lead={max_lead} (max legal window span={max(spans)}); L1 max lead="
          f"{max((r['lead_days'] for r in com_v if r['tier']=='VERIFIED_L1'), default=None)}")
    # EPMC field-only check
    rec_by = {(r["src"], r["id"]): r for r in ct + ep}
    kw_only = []
    for r in com_v:
        if r["evidence_source"] != "epmc":
            continue
        rec = rec_by.get(("epmc", r["evidence_id"]))
        if rec and r["matched_token"] not in rec["match_tokens"]:
            kw_only.append((r["milestone_key"], r["matched_token"], r["evidence_id"],
                            r["matched_token"] in rec["all_tokens"]))
    print(f"EPMC verified rows whose token is NOT in title+abstract: {len(kw_only)} "
          f"(in keywords/MeSH: {sum(1 for x in kw_only if x[3])})")

    # ------------------------------------------------ 4. literature rarity
    print("\n" + "=" * 78)
    print("4. LITERATURE RARITY (Amendment 5)")
    print("=" * 78)
    rare_thr = int(rules["name_vocab"]["literature_rare_max_epmc_df"])
    rare_file = {ln.strip() for ln in (PIN / "epmc_rare_tokens.txt").read_text(encoding="utf-8").splitlines()
                 if ln.strip()}
    tokens = {r["matched_token"] for r in com_v} | {t for a in anchors_list for t in a["distinctive_tokens"]}
    my_rare = {t: (epmc_df.get(t, 0) <= rare_thr and epmc_df.get(t, 0) > 0) for t in tokens}
    file_mismatch = sum(1 for t in tokens if my_rare[t] != (t in rare_file))
    flag_mismatch = sum(1 for r in com_v if bool(r.get("literature_rare")) != my_rare.get(r["matched_token"], False))
    print(f"rare threshold={rare_thr} docs; my rare-file mismatch over {len(tokens)} tokens: {file_mismatch}")
    print(f"committed literature_rare flags vs my recomputation: {flag_mismatch} mismatches / {len(com_v)} rows")
    survivors = sorted({r["matched_token"] for r in com_v if my_rare.get(r["matched_token"])})
    # ordinary-word heuristic: rare token that is also a normal English word cannot be detected
    # without a dictionary; report the strict tokens for human review instead.
    print(f"rare tokens used by verified links: {len(survivors)}")

    # ------------------------------------------------ 5. novelty incl Amendment 6
    first_global, first_firm = novelty_history(con, resolver)
    markers = [m.lower() for m in rules["novelty"]["post_approval_markers"]]
    reclassified = collections.Counter()
    status_mismatch = []
    reason_mismatch = []
    for r in com_v:
        rec = rec_by.get((r["evidence_source"], r["evidence_id"]))
        text = ((rec.get("text") if rec else "") or "").lower()
        marker = next((m for m in markers if m in text), None)
        if marker:
            st, reason = "PRE_EXISTING_PRODUCT", f"self_declared_post_approval:{marker}"
        else:
            d = vc.parse_date(r["evidence_date"])
            fg = first_global.get(r["matched_token"])
            if fg is None or d is None:
                st, reason = "unknown", "no_token_history_or_date"
            elif fg <= d:
                st, reason = "PRE_EXISTING_PRODUCT", "earlier_regulatory_record_of_token"
            else:
                st, reason = "PRE_REGULATORY", "no_earlier_regulatory_record_of_token"
        if marker:
            reclassified[marker] += 1
        if st != r.get("regulatory_status"):
            status_mismatch.append((r["anchor_id"][:12], r["milestone_key"], r["matched_token"],
                                    r.get("regulatory_status"), st, marker,
                                    short(r.get("evidence_title"), 60)))
        if reason and str(r.get("status_reason") or "").startswith("self_declared") != bool(marker):
            reason_mismatch.append((r["milestone_key"], r.get("status_reason"), reason))
    print("\n" + "=" * 78)
    print("5. NOVELTY — Amendment 6 markers (independent full-text scan)")
    print("=" * 78)
    print(f"reclassified rows by marker (my scan): {dict(reclassified)}")
    print(f"status mismatches vs committed: {len(status_mismatch)}")
    for x in status_mismatch[:10]:
        print("  ", x)
    b2 = load_pin("b2_novelty.json")
    print(f"b2 committed: {b2['link_status_counts']} anchors_pre={b2['anchors_with_pre_regulatory_link']}"
          f" anchors_ps_pre={b2['anchors_with_product_specific_pre_regulatory_link']}")
    # over-breadth audit: show titles for each marker (deduplicated)
    print("marker over-breadth audit (distinct title examples per marker):")
    seen = collections.defaultdict(set)
    for r in com_v:
        rec = rec_by.get((r["evidence_source"], r["evidence_id"]))
        text = ((rec.get("text") if rec else "") or "").lower()
        for m in markers:
            if m in text:
                seen[m].add(short(r.get("evidence_title"), 90))
    for m, titles in sorted(seen.items()):
        print(f"  [{m}] rows={reclassified.get(m,0)}")
        for t in list(titles)[:3]:
            print(f"      {t}")
    # over-breadth: rows reclassified by a marker whose token had NO earlier regulatory record
    # (i.e. the old rule would have called them PRE_REGULATORY). For "continued access" this is
    # the dangerous case: FDA continued-access programmes can run BEFORE approval.
    breadth = collections.Counter()
    breadth_ex = collections.defaultdict(list)
    for r in com_v:
        rec = rec_by.get((r["evidence_source"], r["evidence_id"]))
        text = ((rec.get("text") if rec else "") or "").lower()
        marker = next((m for m in markers if m in text), None)
        if not marker:
            continue
        d = vc.parse_date(r["evidence_date"])
        fg = first_global.get(r["matched_token"])
        if fg is None or (d is not None and fg > d):
            breadth[marker] += 1
            if len(breadth_ex[marker]) < 6:
                breadth_ex[marker].append((r["firm"], r["milestone_key"], r["matched_token"],
                                           r["evidence_date"], short(r.get("evidence_title"), 80)))
    print("over-breadth: reclassified rows with NO earlier token record (would have been PRE_REG):")
    for m, c in sorted(breadth.items()):
        print(f"  [{m}] {c} rows")
        for x in breadth_ex[m]:
            print("      ", x)
    out["over_breadth"] = {"counts": dict(breadth), "examples": {m: list(v) for m, v in breadth_ex.items()}}
    out["novelty"] = {"reclassified": dict(reclassified), "status_mismatches": status_mismatch,
                      "over_breadth": {"counts": dict(breadth)},
                      "over_breadth_examples": {m: list(v) for m, v in breadth_ex.items()},
                      "markers": markers, "examples": {m: list(v)[:5] for m, v in seen.items()}}

    # ------------------------------------------------ 6. ladder + verdict
    print("\n" + "=" * 78)
    print("6. LADDER + VERDICT (independent)")
    print("=" * 78)
    # independent status per row
    ind_status = {}
    for r in com_v:
        rec = rec_by.get((r["evidence_source"], r["evidence_id"]))
        text = ((rec.get("text") if rec else "") or "").lower()
        marker = next((m for m in markers if m in text), None)
        if marker:
            ind_status[(r["anchor_id"], r["evidence_id"], r["matched_token"])] = "PRE_EXISTING_PRODUCT"
        else:
            d = vc.parse_date(r["evidence_date"])
            fg = first_global.get(r["matched_token"])
            ind_status[(r["anchor_id"], r["evidence_id"], r["matched_token"])] = (
                "PRE_EXISTING_PRODUCT" if (fg is not None and d is not None and fg <= d)
                else "PRE_REGULATORY")
    tokz_ps = lambda t: 0 < tokz.applicant_df.get(t, 0) <= tokz.product_specific_max
    levels = {
        "any": lambda r: True,
        "product_specific": lambda r: tokz_ps(r["matched_token"]),
        "pre_reg": lambda r: ind_status[(r["anchor_id"], r["evidence_id"], r["matched_token"])] == "PRE_REGULATORY",
        "ps_pre": lambda r: tokz_ps(r["matched_token"]) and ind_status[(r["anchor_id"], r["evidence_id"], r["matched_token"])] == "PRE_REGULATORY",
        "strict": lambda r: (tokz_ps(r["matched_token"])
                             and my_rare.get(r["matched_token"], False)
                             and ind_status[(r["anchor_id"], r["evidence_id"], r["matched_token"])] == "PRE_REGULATORY"),
    }
    ladder = {}
    for name, pred in levels.items():
        lead = {}
        for r in com_v:
            if pred(r):
                lead[r["anchor_id"]] = max(lead.get(r["anchor_id"], -10**9), r["lead_days"])
        vals = sorted(lead.values())
        n = len(vals)
        def pct(q):
            pos = q * (len(vals) - 1); lo = int(pos); hi = min(lo + 1, len(vals) - 1); fr = pos - lo
            return vals[lo] * (1 - fr) + vals[hi] * fr
        ladder[name] = {"anchors": n, "median": pct(0.5) if n else None,
                        "share90": round(sum(1 for v in vals if v >= 90) / n, 6) if n else None}
    print("independent ladder:", json.dumps(ladder, indent=1))
    print("committed ladder:", json.dumps({k: {"anchors": v["anchors"], "median": v["median"],
                                               "share90": v["share_ge_90_days"]}
                                           for k, v in load_pin("d_leadtime.json")["validity_ladder"].items()},
                                          indent=1))
    # verdict inputs
    c = load_pin("c_controls.json")
    k = len({r["anchor_id"] for r in com_v})
    leads = sorted({a: max(r["lead_days"] for r in com_v if r["anchor_id"] == a) for a in
                    {r["anchor_id"] for r in com_v}}.values())
    share90 = sum(1 for v in leads if v >= 90) / len(leads)
    decoy_rows = c["c3_decoy_rows"]
    decoy_ids = {r["anchor_id"] for r in decoy_rows}
    decoy_linked = sum(1 for r in decoy_rows if r["decoy_linked"])
    real_matched = sum(1 for a in decoy_ids if any(r["anchor_id"] == a for r in com_v))
    spec = (real_matched / decoy_linked) if decoy_linked else None
    spec_overall = k / len(anchors_list) / (decoy_linked / len(decoy_ids))
    p = c["c4b_date_permutation"]["p_median_lead"]
    print(f"k={k} share90={share90:.6f} median={load_pin('d_leadtime.json')['overall_publication_clock']['median']}")
    print(f"specificity: matched-denominator real={real_matched}/{len(decoy_ids)}="
          f"{real_matched/len(decoy_ids):.6f} decoy={decoy_linked}/{len(decoy_ids)}="
          f"{decoy_linked/len(decoy_ids):.6f} -> {spec:.4f} (committed {c['c3_decoy']['specificity']}, "
          f"field {c['c3_decoy'].get('specificity_matched_denominator')}); "
          f"old unmatched-denominator ratio={spec_overall:.4f}")
    print(f"c3 note: {c['c3_decoy'].get('specificity_note')[:120]}")
    print(f"c4b draws={c['c4b_date_permutation']['draws']} p={p}  c4a draws={c['c4a_time_shift']['draws']}")
    go, lim = rules["verdict"]["go"], rules["verdict"]["limited_go"]
    firms = {a["firm"] for a in anchors_list if a["anchor_id"] in {r["anchor_id"] for r in com_v}}
    years = {a["anchor_year"] for a in anchors_list if a["anchor_id"] in {r["anchor_id"] for r in com_v}}
    cov = load_pin("verdict.json")["gates"]["coverage_rate"]
    blocked = cov < rules["pilot"]["scaling_conditions"]["min_anchor_coverage"]
    go_ok = (k >= go["min_k"] and share90 >= go["min_p90_share_ge_90d"] and spec is not None
             and spec >= go["min_specificity"] and p < go["max_placebo_p"] and len(firms) >= go["min_firms"]
             and len(years) >= go["min_years"])
    lim_ok = (k >= lim["min_k"] and share90 >= lim["min_p90_share_ge_90d"] and spec is not None
              and spec >= lim["min_specificity"] and p < lim["max_placebo_p"])
    verdict = "BLOCKED" if blocked else ("GO" if go_ok else ("LIMITED GO" if lim_ok else "NO-GO"))
    print(f"my verdict: {verdict} (blocked={blocked} go={go_ok} limited={lim_ok}) "
          f"committed={load_pin('verdict.json')['verdict']}")
    out["ladder"] = ladder
    out["verdict"] = {"my": verdict, "committed": load_pin("verdict.json")["verdict"],
                      "k": k, "share90": share90, "specificity": spec, "p": p,
                      "c4b_draws": c["c4b_date_permutation"]["draws"]}

    # ------------------------------------------------ 7. top strict case audit
    strict_rows = [r for r in com_v if levels["strict"](r)]
    top = max(strict_rows, key=lambda r: r["lead_days"])
    print("\n" + "=" * 78)
    print(f"7. TOP STRICT CASE (independent): lead={top['lead_days']} {top['firm']} "
          f"{top['milestone_key']} token={top['matched_token']} {top['evidence_source']}:{top['evidence_id']} "
          f"date={top['evidence_date']}")
    print("=" * 78)
    a = anchors[top["anchor_id"]]
    rec = rec_by.get((top["evidence_source"], top["evidence_id"]))
    msr = store_milestone(con, a)
    adate = vc.parse_date(a["anchor_date"]); edate = vc.parse_date(top["evidence_date"])
    text = (rec.get("text") or "") if rec else ""
    ctx = [text[max(0, text.lower().find(top["matched_token"].lower()) - 140):
                text.lower().find(top["matched_token"].lower()) + 180]]
    fg = first_global.get(top["matched_token"])
    sens = rec.get("date_sens") if rec else None
    checks = {
        "milestone_matches_store": bool(msr and msr["event_date"] == a["anchor_date"]
                                        and msr["code"] == ("APPR" if a["kind"] == "pma" else "SESE")),
        "record_in_corpus": rec is not None,
        "publication_date_matches": rec is not None and rec["date_str"] == top["evidence_date"],
        "token_in_match_field": rec is not None and top["matched_token"] in rec["match_tokens"],
        "firm_attribution": rec is not None and top["firm"] in rec["firm_verified"],
        "inside_frozen_window": edate is not None and vc.years_before(adate, 5) <= edate < adate,
        "no_earlier_token_record": fg is None or (edate is not None and fg > edate),
        "no_post_approval_marker": not any(m in text.lower() for m in markers),
        "token_product_specific": tokz_ps(top["matched_token"]),
        "token_literature_rare": my_rare.get(top["matched_token"], False),
        "l1_chain_ok": (top["tier"] != "VERIFIED_L1"),
    }
    if top["tier"] == "VERIFIED_L1" and rec:
        ncts = sorted(set(NCT_RE.findall(text)))
        checks["l1_chain_ok"] = any(
            (lambda c2: c2 and top["firm"] in c2["firm_verified"] and top["firm"] in c2["firms"]
             and top["matched_token"] in c2["match_tokens"])({r["id"]: r for r in ct}.get(n))
            for n in ncts)
    print("milestone:", msr)
    print("record: id=%r date=%r title=%r" % (top["evidence_id"], rec["date_str"] if rec else None,
                                              short(rec["title"] if rec else "", 150)))
    print("text context around token:", short(ctx[0], 320))
    print("token: applicant_df=%s literature_df=%s rare=%s; latest-plausible date=%s lead=%s"
          % (tokz.applicant_df.get(top["matched_token"]), epmc_df.get(top["matched_token"]),
             my_rare.get(top["matched_token"]), sens,
             (adate - vc.parse_date(sens)).days if sens and vc.parse_date(sens) else None))
    print("checks:", json.dumps(checks, indent=1))
    print("all checks pass:", all(checks.values()))
    top_leads = sorted(strict_rows, key=lambda r: -r["lead_days"])
    seen_anchor = set()
    print("top strict cases (independent, distinct anchors):")
    for r in top_leads:
        if r["anchor_id"] in seen_anchor:
            continue
        seen_anchor.add(r["anchor_id"])
        print(f"   lead={r['lead_days']:5d} {r['firm']:22s} {r['milestone_key']:10s} "
              f"{r['matched_token']:16s} {r['evidence_source']}:{r['evidence_id']} {r['evidence_date']}"
              f" | {short(r['evidence_title'], 70)}")
        if len(seen_anchor) >= 8:
            break
    # SYMPLICITY anchor status in the strict set
    sym_anchor_rows = [r for r in strict_rows if r["firm"] == "medtronic" and r["milestone_key"] == "PP220026"]
    print(f"SYMPLICITY anchor rows in strict set: {len(sym_anchor_rows)}; max lead="
          f"{max((r['lead_days'] for r in sym_anchor_rows), default=None)}")

    # ------------------------------------------------ 8. SYMPLICITY inadmissible?
    sym = [r for r in links if r["matched_token"] == "SYMPLICITY"]
    sym_v = [r for r in sym if r["tier"] in ("VERIFIED_L1", "VERIFIED_L2")]
    print("\n8. SYMPLICITY rows in EVIDENCE_LINKS:", len(sym), "verified:", len(sym_v))
    for r in sorted(sym, key=lambda r: -r["lead_days"])[:5]:
        print("  ", r["tier"], r["reason"], r["evidence_date"], r["lead_days"], r["evidence_id"])
    out["case"] = {"checks": checks, "top": {k2: top[k2] for k2 in
                                             ("anchor_id", "firm", "milestone_key", "product_code",
                                              "tier", "evidence_source", "evidence_id", "evidence_date",
                                              "matched_token", "lead_days")},
                   "milestone": msr, "context": ctx,
                   "latest_plausible_lead": (adate - vc.parse_date(sens)).days if sens and vc.parse_date(sens) else None}
    out["symplicity"] = {"rows": len(sym), "verified": len(sym_v)}
    (HERE / "out_final.json").write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    print(f"\nwrote {HERE/'out_final.json'}")
    return 0


def novelty_history(con, resolver):
    first_global, first_firm = {}, collections.defaultdict(dict)
    q = """select json_extract(payload,'$.device_name') as dn,
                  json_extract(payload,'$.trade_name') as tn,
                  json_extract(payload,'$.generic_name') as gn,
                  json_extract(payload,'$.supplement_number') as supp,
                  applicant_raw, event_date, kind
           from events where kind in ('510k','pma')"""
    for r in con.execute(q):
        if r["kind"] == "pma" and (r["supp"] or "").strip():
            continue
        name = r["dn"] or r["tn"] or r["gn"] or ""
        d = vc.parse_date(r["event_date"])
        if not name or d is None:
            continue
        firm, _ = resolver.resolve(r["applicant_raw"] or "")
        for t in {x for x in vc.tokens(name) if len(x) >= 4 and x.isalpha()}:
            if t not in first_global or d < first_global[t]:
                first_global[t] = d
            if firm:
                cur = first_firm[t].get(firm)
                if cur is None or d < cur:
                    first_firm[t][firm] = d
    return first_global, first_firm


def store_milestone(con, a):
    if a["milestone_key"].startswith("K"):
        r = con.execute("""select event_date, applicant_raw, product_code,
             json_extract(payload,'$.decision_code') as code,
             json_extract(payload,'$.device_name') as name,
             json_extract(payload,'$.supplement_number') as supp
             from events where kind='510k' and json_extract(payload,'$.k_number')=?""",
                        (a["official_id"],)).fetchone()
    else:
        r = con.execute("""select event_date, applicant_raw, product_code,
             json_extract(payload,'$.decision_code') as code,
             json_extract(payload,'$.trade_name') as name,
             json_extract(payload,'$.supplement_number') as supp
             from events where kind='pma' and json_extract(payload,'$.pma_number')=?""",
                        (a["official_id"],)).fetchone()
    return dict(r) if r else None


if __name__ == "__main__":
    raise SystemExit(main())
