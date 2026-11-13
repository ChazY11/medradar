"""STEP 6 — end-to-end scientific audit of the highest-lead-time PRE_REGULATORY
product-specific link, the study's single most quotable case.

Case selection (from the committed EVIDENCE_LINKS.jsonl):
    tier in {VERIFIED_L1, VERIFIED_L2}, regulatory_status == PRE_REGULATORY,
    product_specific == True, maximum lead_days.

Every step is checked against the raw store and the frozen corpus, and then the case is attacked
from the angles the protocol itself names (dual clock, post-approval status, store coverage).

Run:  python experiments/phoenix003/verify/verify_case.py
"""
from __future__ import annotations

import collections
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import vcommon as vc

OUT = Path(__file__).resolve().parent / "out_case.json"


def main():
    links = vc.committed_links()
    anchors = {a["anchor_id"]: a for a in vc.committed_anchors()}

    cand = [r for r in links if r["tier"] in ("VERIFIED_L1", "VERIFIED_L2")
            and r.get("regulatory_status") == "PRE_REGULATORY"
            and r.get("product_specific")]
    case = max(cand, key=lambda r: r["lead_days"])
    a = anchors[case["anchor_id"]]
    print("=" * 78)
    print("CASE AUDIT — highest-lead PRE_REGULATORY product-specific link")
    print("=" * 78)
    print(json.dumps({k: case[k] for k in ("anchor_id", "firm", "milestone_key", "product_code",
                                            "anchor_date", "milestone_name", "matched_token",
                                            "token_applicant_df", "evidence_id", "evidence_date",
                                            "evidence_date_sensitivity", "evidence_title",
                                            "lead_days", "regulatory_status", "product_specific")},
                     indent=1, ensure_ascii=False))

    checks = []

    # ---------------------------------------------------------------- 1. milestone in store
    con = vc.connect_ro()
    row = con.execute("""
        select event_date, applicant_raw, product_code,
               json_extract(payload,'$.pma_number') as pma,
               json_extract(payload,'$.supplement_number') as supp,
               json_extract(payload,'$.trade_name') as trade,
               json_extract(payload,'$.generic_name') as generic,
               json_extract(payload,'$.decision_code') as code,
               json_extract(payload,'$.decision_date') as dec_date,
               json_extract(payload,'$.date_received') as recv
        from events where kind='pma' and json_extract(payload,'$.pma_number') = ?
    """, (a["official_id"],)).fetchone()
    milestone = dict(row) if row else None
    ok1 = bool(milestone and milestone["event_date"] == a["anchor_date"]
               and milestone["code"] == "APPR" and not (milestone["supp"] or ""))
    checks.append(("1 milestone record in store matches anchor",
                   ok1, f"P140017 original: date={milestone['event_date']} code={milestone['code']} "
                        f"supp={milestone['supp']!r} pc={milestone['product_code']} "
                        f"applicant={milestone['applicant_raw']!r}"))
    print(f"\nCHECK 1 milestone in store               : {'PASS' if ok1 else 'FAIL'}")
    print(f"   store: {milestone}")

    # ---------------------------------------------------------- 2. first Medtronic record in NPV
    cell = con.execute("""
        select event_date, json_extract(payload,'$.pma_number'), json_extract(payload,'$.k_number'),
               json_extract(payload,'$.supplement_number'), json_extract(payload,'$.trade_name'),
               json_extract(payload,'$.decision_code')
        from events where kind in ('510k','pma') and product_code='NPV'
          and upper(applicant_raw) like '%MEDTRONIC%'
          and (kind='510k' or coalesce(json_extract(payload,'$.supplement_number'),'')='')
        order by event_date
    """).fetchall()
    first = cell[0] if cell else None
    ok2 = bool(first and first[0] == a["anchor_date"])
    checks.append(("2 anchor is first-in-product-code for the firm",
                   ok2, f"earliest Medtronic 510k/PMA in NPV = {tuple(first) if first else None}"))
    print(f"CHECK 2 first-in-code (Medtronic/NPV)    : {'PASS' if ok2 else 'FAIL'}  "
          f"earliest={tuple(first) if first else None}")

    # ------------------------------------------------- 3. evidence record in frozen corpus
    corpus = None
    for r in vc.read_jsonl_gz(vc.DATASET / "ctgov_compact.jsonl.gz"):
        if r.get("nct_id") == case["evidence_id"]:
            corpus = r
            break
    ok3 = bool(corpus and corpus.get("first_posted") == case["evidence_date"]
               and case["evidence_title"].strip() == (corpus.get("brief_title") or "").strip())
    checks.append(("3 evidence record in frozen corpus with exact date/title",
                   ok3, f"first_posted={corpus.get('first_posted') if corpus else None} "
                        f"title={corpus.get('brief_title') if corpus else None!r}"))
    print(f"CHECK 3 record in corpus                 : {'PASS' if ok3 else 'FAIL'}")
    if corpus:
        print(f"   first_posted={corpus['first_posted']} last_update_posted={corpus['last_update_posted']}")
        print(f"   brief_title={corpus['brief_title']!r}")
        print(f"   official_title={corpus['official_title']!r}")
        print(f"   lead_sponsor={corpus['lead_sponsor']!r} source_firm={corpus['source_firm']!r}")
        print(f"   interventions={[x.get('name') for x in corpus['interventions']]}")
        print(f"   start_date={corpus['start_date']} results_first_posted={corpus['results_first_posted']}")

    # ------------------------------------------------------------- 4. token match + firm
    resolver = vc.Resolver()
    tokz = vc.Tokenizer()
    tok = case["matched_token"]
    title_tokens = set(vc.tokens(corpus.get("brief_title") if corpus else ""))
    iv_tokens = set()
    for x in (corpus.get("interventions") if corpus else []) or []:
        iv_tokens |= set(vc.tokens(x.get("name") or ""))
    tok_in_title = tok in title_tokens
    tok_in_iv = tok in iv_tokens
    sponsor_firm, sponsor_tok = resolver.resolve(corpus.get("lead_sponsor") if corpus else "")
    token_distinctive = (tok in (a.get("distinctive_tokens") or [])
                         and tok not in tokz.generic and tok not in tokz.stop_a
                         and tok not in tokz.brand and len(tok) >= 4 and tok.isalpha())
    df = tokz.applicant_df.get(tok, 0)
    ok4 = tok_in_iv and token_distinctive and sponsor_firm == a["firm"]
    checks.append(("4 exact whole-token identity + same-firm sponsor",
                   ok4, f"MELODY in intervention={tok_in_iv} in brief_title={tok_in_title} "
                        f"distinctive={token_distinctive} applicant_df={df} "
                        f"sponsor_firm={sponsor_firm}"))
    print(f"CHECK 4 token identity / firm            : {'PASS' if ok4 else 'FAIL'}")
    print(f"   token={tok} in intervention={tok_in_iv} in brief_title={tok_in_title} "
          f"distinctive={token_distinctive} applicant_df={df}")
    print(f"   sponsor resolver: '{corpus['lead_sponsor']}' -> {sponsor_firm} (token {sponsor_tok})")

    # ------------------------------------------------------- 5. no earlier regulatory record
    hist = []
    for r in con.execute("""
        select kind, event_date, applicant_raw, product_code,
               json_extract(payload,'$.k_number'), json_extract(payload,'$.pma_number'),
               json_extract(payload,'$.supplement_number') as supp,
               coalesce(json_extract(payload,'$.device_name'), json_extract(payload,'$.trade_name'),
                        json_extract(payload,'$.generic_name')) as name
        from events where kind in ('510k','pma')
        order by event_date
    """):
        if r["kind"] == "pma" and (r["supp"] or "").strip():
            continue
        nm = r["name"] or ""
        if tok in vc.tokens(nm):
            hist.append(tuple(r))
    earliest = min(h[1] for h in hist) if hist else None
    earlier = [h for h in hist if h[1] <= case["evidence_date"]]
    ok5 = len(earlier) == 0
    checks.append(("5 no earlier canonical record contains the token",
                   ok5, f"earliest MELODY-named canonical record={earliest}; "
                        f"records at/before evidence date={len(earlier)}"))
    print(f"CHECK 5 no earlier MELODY regulatory record: {'PASS' if ok5 else 'FAIL'}")
    print(f"   earliest MELODY record: {earliest}; count named MELODY: {len(hist)}; "
          f"names before/equal evidence date: {len(earlier)}")

    # --------------------------------------------------------------- 6. window + lead
    from datetime import date, timedelta
    adate = vc.parse_date(a["anchor_date"])
    edate = vc.parse_date(case["evidence_date"])
    w0 = vc.years_before(adate, 5)
    ok6 = w0 <= edate < adate
    checks.append(("6 evidence strictly before milestone inside 5y window",
                   ok6, f"window=[{w0},{adate}); evidence={edate}; lead={(adate-edate).days}"))
    print(f"CHECK 6 window / lead                    : {'PASS' if ok6 else 'FAIL'}  "
          f"w0={w0} evidence={edate} lead={(adate-edate).days}")

    # ================================================================== BREAK ATTEMPTS
    print("\n" + "-" * 78)
    print("BREAK ATTEMPTS")
    print("-" * 78)
    breaks = []

    # B1: the record says it is a post-approval study
    tl = ((corpus.get("brief_title") or "") + " " + (corpus.get("official_title") or "")).upper()
    post = any(x in tl for x in ("POST-APPROVAL", "POST APPROVAL", "POST-MARKET APPROVAL",
                                 "POST MARKET APPROVAL", "POST-MARKET", "POST MARKET",
                                 "PAS ", "POST-APPROVAL"))
    breaks.append(("B1 evidence title self-declares prior approval", post,
                   f"brief={corpus.get('brief_title')!r}; official={corpus.get('official_title')!r}"))
    print(f"B1 title self-declares prior approval    : {'BREAKS' if post else 'no'}")

    # B2: dual clock — protocol 9.4 requires the latest plausible public date
    sens = vc.parse_date(case.get("evidence_date_sensitivity"))
    sens_lead = (adate - sens).days if sens else None
    breaks.append(("B2 latest-plausible clock lead is negative", sens is not None and sens_lead < 0,
                   f"last_update_posted={case.get('evidence_date_sensitivity')} "
                   f"sensitivity_lead={sens_lead} days (headline lead={case['lead_days']})"))
    print(f"B2 dual clock                            : sensitivity_date={sens} "
          f"sensitivity_lead={sens_lead} (headline {case['lead_days']})")

    # B3: store coverage — no HDE / IDE table, so prior approvals of that class are invisible
    kinds = [r[0] for r in con.execute("select distinct kind from events order by kind")]
    breaks.append(("B3 prior approval invisible to the store (no HDE kind)",
                   "hde" not in [k.lower() for k in kinds], f"event kinds={kinds}"))
    print(f"B3 store coverage                        : event kinds={kinds}")
    print("   analyst knowledge: the Melody TPV was approved under FDA HDE H070003 in 2006;")
    print("   HDE/IDE approvals are not an event kind in this store, so they cannot be seen")
    print("   by the PRE_REGULATORY rule. The corpus title itself ('Post-Market Approval Study')")
    print("   is independent evidence that the approval predates the trial.")

    # B4: other product-specific pre-regulatory cases — how many are post-approval studies?
    print("\nB4 all product-specific PRE_REGULATORY cases:")
    ps_rows = [r for r in links if r["tier"] in ("VERIFIED_L1", "VERIFIED_L2")
               and r.get("regulatory_status") == "PRE_REGULATORY" and r.get("product_specific")]
    for r in sorted(ps_rows, key=lambda r: -r["lead_days"]):
        post_flag = any(x in r["evidence_title"].upper() for x in
                        ("POST-APPROVAL", "POST APPROVAL", "POST-MARKET", "POST MARKET",
                         "POST MARKETING", "POST-MARKETING"))
        print(f"   lead={r['lead_days']:5d} {r['milestone_key']:10s} {r['matched_token']:14s} "
              f"{r['evidence_id']} post_approval_title={post_flag}  {r['evidence_title'][:70]}")
    n_post = sum(1 for r in ps_rows if any(x in r["evidence_title"].upper() for x in
                 ("POST-APPROVAL", "POST APPROVAL", "POST-MARKET", "POST MARKET",
                  "POST MARKETING", "POST-MARKETING")))
    print(f"   -> {n_post}/{len(ps_rows)} product-specific PRE_REGULATORY rows are self-declared "
          f"post-approval/post-market studies")

    # B5: is MELODY used by another applicant before the evidence date? (token collision)
    others = [(h[3], h[1], h[2], h[7]) for h in hist
              if "MEDTRONIC" not in vc.norm(h[2])][:5]
    print(f"B5 other applicants using MELODY        : {others}")

    print("\n" + "-" * 78)
    print("CASE RESULT")
    print("-" * 78)
    mech = all(c[1] for c in checks)
    print(f"mechanical checks 1-6                    : {'ALL PASS' if mech else 'FAILURES: ' + str([c[0] for c in checks if not c[1]])}")
    print(f"substantive 'pre-regulatory' claim       : {'SURVIVES' if not any(b[1] for b in breaks[:2]) else 'BROKEN'}")
    print("The link is machine-verifiable, but the PRE_REGULATORY interpretation is not: the")
    print("evidence is a post-approval study of a device that was already approved, and the")
    print("1618-day lead exists only on the optimistic first_posted clock (negative on the")
    print("frozen latest-plausible clock).")

    payload = {
        "case": case,
        "anchor": a,
        "milestone_store": milestone,
        "corpus_record": corpus,
        "checks": [{"name": c[0], "pass": c[1], "detail": c[2]} for c in checks],
        "breaks": [{"name": b[0], "triggered": b[1], "detail": b[2]} for b in breaks],
        "product_specific_pre_reg_rows": ps_rows,
        "melody_history": hist,
        "latest_plausible_lead": sens_lead,
        "event_kinds": kinds,
    }
    OUT.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    print(f"\nwrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

