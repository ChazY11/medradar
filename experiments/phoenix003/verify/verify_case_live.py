"""STEP 6 (live artefacts) — end-to-end audit of the two highest-lead-time PRE_REGULATORY
product-specific links in the finished re-run:

  CASE A — the correct top case over the FULL verified-link set (6,532 rows = b_links tier
           counts; EVIDENCE_LINKS.jsonl itself is truncated, see report):
           Medtronic PP220026 (product code QYI), token SYMPLICITY, EPMC 24858423,
           2014-05-20, lead 3,468 days.
  CASE B — the top case *inside the committed, truncated EVIDENCE_LINKS.jsonl*:
           Boston Scientific KK172565 (PWJ), token OBTRYX, CT.gov NCT01784588,
           2013-02-06, lead 1,778 days.

Each step is checked against the raw store and the frozen corpora, then attacked from the
angles the protocol itself names (dual clock, post-approval status, IDE/HDE store coverage,
sponsor-authored trials, token collision).

Run:  PHOENIX_VERIFY_MODE=live python experiments/phoenix003/verify/verify_case_live.py
"""
from __future__ import annotations

import collections
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import vcommon as vc
import verify_novelty as vn

OUT = Path(__file__).resolve().parent / "out_case_live.json"
NCT_RE = re.compile(r"NCT\d{8}")
POST_KW = ("POST-APPROVAL", "POST APPROVAL", "POST-MARKET", "POST MARKET", "POST MARKETING",
           "POST-MARKETING", "POST-MARKET", "POSTMARKET")


def find_anchor(aid):
    for a in vc.committed_anchors():
        if a["anchor_id"] == aid:
            return a
    return None


def milestone_from_store(con, a):
    if a["milestone_key"].startswith("K"):
        k = a["official_id"]
        r = con.execute("""select event_date, applicant_raw, product_code,
              json_extract(payload,'$.k_number') as kid,
              json_extract(payload,'$.device_name') as name,
              json_extract(payload,'$.decision_code') as code,
              json_extract(payload,'$.date_received') as recv
            from events where kind='510k' and json_extract(payload,'$.k_number')=?""", (k,)).fetchone()
    else:
        p = a["official_id"]
        r = con.execute("""select event_date, applicant_raw, product_code,
              json_extract(payload,'$.pma_number') as pid,
              json_extract(payload,'$.supplement_number') as supp,
              json_extract(payload,'$.trade_name') as name,
              json_extract(payload,'$.decision_code') as code,
              json_extract(payload,'$.date_received') as recv
            from events where kind='pma' and json_extract(payload,'$.pma_number')=?""", (p,)).fetchone()
    return dict(r) if r else None


def first_in_code(con, firm, code, resolver):
    best = None
    for r in con.execute("""
        select kind, event_date, applicant_raw, product_code,
               json_extract(payload,'$.k_number') as k,
               json_extract(payload,'$.pma_number') as p,
               json_extract(payload,'$.supplement_number') as supp
        from events where kind in ('510k','pma') and product_code=?
        order by event_date""", (code,)):
        if r["kind"] == "pma" and (r["supp"] or "").strip():
            continue
        f, _ = resolver.resolve(r["applicant_raw"] or "")
        if f != firm:
            continue
        best = (r["event_date"], r["k"], r["p"])
        break
    return best


def find_record(files, eid):
    for name in files:
        p = vc.DATASET / name
        if not p.exists():
            continue
        for r in vc.read_jsonl_gz(p):
            rid = r.get("nct_id") if name.startswith("ctgov") else (
                r.get("pmid") or r.get("doi") or r.get("id"))
            if rid == eid:
                return name, r
    return None, None


def audit_case(label, case, anchor, con, resolver, tokz, first_global, ct_ids, ct_by_id):
    print("\n" + "=" * 78)
    print(f"{label}")
    print("=" * 78)
    checks = []
    a = anchor
    adate = vc.parse_date(a["anchor_date"])
    edate = vc.parse_date(case["evidence_date"])
    tok = case["matched_token"]

    # 1 milestone
    ms = milestone_from_store(con, a)
    ok1 = bool(ms and ms["event_date"] == a["anchor_date"]
               and ms["code"] == ("APPR" if a["kind"] == "pma" else "SESE"))
    checks.append(("1 milestone in store", ok1,
                   f"{a['milestone_key']} {ms}"))
    print(f"CHECK 1 milestone in store            : {'PASS' if ok1 else 'FAIL'}  {ms}")

    # 2 first in code
    fic = first_in_code(con, a["firm"], a["product_code"], resolver)
    ok2 = bool(fic and fic[0] == a["anchor_date"])
    checks.append(("2 first-in-code", ok2, f"earliest {a['firm']} 510k/PMA in "
                                           f"{a['product_code']} = {fic}"))
    print(f"CHECK 2 first-in-code                  : {'PASS' if ok2 else 'FAIL'}  {fic}")

    # 3 evidence record in frozen corpus
    ctf = ["ctgov_compact.jsonl.gz", "ctgov_ext_compact.jsonl.gz"]
    epf = ["epmc_compact.jsonl.gz", "epmc_ext_compact.jsonl.gz"]
    files = ctf if case["evidence_source"] == "ctgov" else epf
    fname, rec = find_record(files, case["evidence_id"])
    ok3 = rec is not None
    checks.append(("3 evidence record in frozen corpus", ok3, f"{fname}"))
    print(f"CHECK 3 record in frozen corpus        : {'PASS' if ok3 else 'FAIL'}  file={fname}")
    if rec:
        if case["evidence_source"] == "ctgov":
            print(f"   first_posted={rec['first_posted']} last_update_posted={rec['last_update_posted']}")
            print(f"   brief_title={rec['brief_title']!r}")
            print(f"   official_title={rec['official_title']!r}")
            print(f"   lead_sponsor={rec['lead_sponsor']!r} source_firm={rec['source_firm']!r}")
            print(f"   interventions={[x.get('name') for x in rec['interventions']]}")
            pubdate = rec.get("first_posted")
        else:
            print(f"   first_publication_date={rec['first_publication_date']} "
                  f"electronic={rec['electronic_publication_date']} first_index={rec['first_index_date']}")
            print(f"   title={rec['title']!r}")
            print(f"   journal={rec.get('journal_title')!r} pub_types={rec.get('pub_types')}")
            print(f"   firm_affiliations={rec.get('firm_affiliations')}")
            print(f"   abstract[:160]={(rec.get('abstract') or '')[:160]!r}")
            pubdate = rec.get("first_publication_date")
        ok3b = pubdate == case["evidence_date"]
        print(f"   publication date matches link row: {ok3b}")
        checks.append(("3b exact publication date", ok3b, str(pubdate)))

    # 4 token identity + firm
    ok4 = False
    detail4 = ""
    if rec and case["evidence_source"] == "ctgov":
        title_toks = set(vc.tokens(rec.get("brief_title") or "")) | set(vc.tokens(rec.get("official_title") or ""))
        iv_toks = set()
        for x in rec.get("interventions") or []:
            iv_toks |= set(vc.tokens(x.get("name") or ""))
        infield = tok in title_toks or tok in iv_toks
        firms = set()
        for s in [rec.get("lead_sponsor") or ""] + list(rec.get("collaborators") or []):
            f, _ = resolver.resolve(str(s))
            if f:
                firms.add(f)
        ok4 = infield and a["firm"] in firms
        detail4 = f"token in title/interventions={infield}; sponsor firms={sorted(firms)}"
    elif rec:
        tt = set(vc.tokens(rec.get("title") or "")) | set(vc.tokens(rec.get("abstract") or ""))
        infield = tok in tt
        firms = set()
        for aff in rec.get("firm_affiliations") or []:
            f, _ = resolver.resolve(str(aff))
            if f:
                firms.add(f)
        ok4 = infield and a["firm"] in firms
        detail4 = f"token in title/abstract={infield}; affiliation firms={sorted(firms)}"
    checks.append(("4 token identity + same firm", ok4, detail4))
    print(f"CHECK 4 token in record + firm         : {'PASS' if ok4 else 'FAIL'}  {detail4}")

    # token quality
    df = tokz.applicant_df.get(tok, 0)
    distinctive = (tok in (a.get("distinctive_tokens") or [])
                   and tok not in tokz.generic and tok not in tokz.stop_a
                   and tok not in tokz.brand and len(tok) >= 4 and tok.isalpha())
    print(f"   token={tok} in anchor distinctive_tokens={tok in (a.get('distinctive_tokens') or [])} "
          f"generic={tok in tokz.generic} brand={tok in tokz.brand} applicant_df={df} "
          f"product_specific={0 < df <= tokz.product_specific_max}")

    # 5 novelty: no earlier regulatory record with the token
    hist = []
    for r in con.execute("""
        select kind, event_date, applicant_raw, product_code,
               json_extract(payload,'$.k_number') as k,
               json_extract(payload,'$.pma_number') as p,
               coalesce(json_extract(payload,'$.supplement_number'),'') as supp,
               coalesce(json_extract(payload,'$.device_name'),
                        json_extract(payload,'$.trade_name'),
                        json_extract(payload,'$.generic_name')) as name
        from events where kind in ('510k','pma') order by event_date"""):
        if r["kind"] == "pma" and (r["supp"] or "").strip():
            continue
        if tok in vc.tokens(r["name"] or ""):
            hist.append(tuple(r))
    earlier = [h for h in hist if h[1] <= case["evidence_date"]]
    ok5 = len(earlier) == 0
    checks.append(("5 no earlier regulatory record with token", ok5,
                   f"earliest={min((h[1] for h in hist), default=None)}; "
                   f"records<=evidence={len(earlier)}"))
    print(f"CHECK 5 no earlier token record        : {'PASS' if ok5 else 'FAIL'}  "
          f"earliest={min((h[1] for h in hist), default=None)} count={len(hist)} "
          f"<=evidence={len(earlier)}")

    # 6 window + lead
    w0 = vc.years_before(adate, 5)
    ok6 = edate is not None and w0 <= edate < adate
    checks.append(("6 window / lead", ok6,
                   f"w0={w0} evidence={edate} anchor={adate} lead={(adate - edate).days if edate else None}"))
    print(f"CHECK 6 window / lead                  : {'PASS' if ok6 else 'FAIL'}  "
          f"w0={w0} evidence={edate} lead={(adate - edate).days if edate else None} "
          f"(committed row lead={case['lead_days']})")

    # L1 chain
    if case["evidence_source"] == "epmc" and rec:
        ncts = NCT_RE.findall((rec.get("title") or "") + " " + (rec.get("abstract") or ""))
        chain = []
        for nct in sorted(set(ncts)):
            ct = ct_by_id.get(nct)
            if ct and a["firm"] in ct["firm_verified"] and a["firm"] in ct["firms"]:
                chain.append((nct, tok in ct["tok_author"], ct["title"][:60]))
        print(f"   L1 chain NCT ids={sorted(set(ncts))} firm-verified trial hits={chain}")

    # ------------------------------------------------------------- break attempts
    print("   BREAK ATTEMPTS:")
    title = ((rec.get("brief_title") or "") + " " + (rec.get("official_title") or "")
             if case["evidence_source"] == "ctgov" and rec
             else (rec.get("title") or "") if rec else "").upper()
    post = any(x in title for x in POST_KW)
    print(f"     B1 post-approval/post-market title : {'BREAKS' if post else 'no'}  {title[:110]!r}")
    sens = None
    if rec:
        if case["evidence_source"] == "ctgov":
            sens = vc.parse_date(rec.get("last_update_posted"))
        else:
            sens = (vc.parse_date(rec.get("first_index_date"))
                    or vc.parse_date(rec.get("electronic_publication_date")))
    sens_lead = (adate - sens).days if sens else None
    print(f"     B2 latest-plausible clock           : sensitivity={sens} lead={sens_lead} "
          f"(headline {case['lead_days']})")
    kinds = [r[0] for r in con.execute("select distinct kind from events order by kind")]
    print(f"     B3 store coverage                   : event kinds={kinds}  (no HDE/IDE table)")
    print(f"     B4 sponsorship                      : the linked record is a {a['firm']}-affiliated"
          f" publication; a firm's own trial of its own device is not an independent signal")
    return {"label": label, "case": case, "anchor": a,
            "checks": [{"name": c[0], "pass": c[1], "detail": c[2]} for c in checks],
            "record": rec, "record_file": fname,
            "title_post_approval": post, "latest_plausible_lead": sens_lead,
            "token": tok, "applicant_df": df, "distinctive": distinctive}


def main():
    rules = vc.load_json(vc.EXP / "FROZEN_RULES.json")
    resolver = vc.Resolver()
    tokz = vc.Tokenizer()
    con = vc.connect_ro()
    first_global, first_firm, n_ms = vn.token_history()
    print(f"token history: {n_ms} milestones, {len(first_global)} tokens")

    # ctgov index for the L1 chain and firm verification
    ct_by_id = {}
    for name in ("ctgov_compact.jsonl.gz", "ctgov_ext_compact.jsonl.gz"):
        p = vc.DATASET / name
        if not p.exists():
            continue
        for r in vc.read_jsonl_gz(p):
            firms = [f for f in str(r.get("source_firm") or "").split("+") if f]
            fv = set()
            for s in [r.get("lead_sponsor") or ""] + list(r.get("collaborators") or []):
                f, _ = resolver.resolve(str(s))
                if f:
                    fv.add(f)
            ct_by_id[r["nct_id"]] = {"firms": firms, "firm_verified": fv,
                                     "title": r.get("brief_title") or "",
                                     "tok_author": set(vc.tokens(r.get("brief_title") or ""))}
            for x in r.get("interventions") or []:
                ct_by_id[r["nct_id"]]["tok_author"] |= set(vc.tokens(x.get("name") or ""))

    anchors = {a["anchor_id"]: a for a in vc.committed_anchors()}
    results = []

    # CASE A: correct top case over the full verified-link set
    data = vc.load_json(Path(__file__).resolve().parent / "out_links.json")
    rows = data["rows_author"]
    vn.classify(rows, first_global, {k: int(v) for k, v in
                                     vc.load_json(vc.DATASET / "frozen_vocab.json")["applicant_df"].items()},
                int(rules["name_vocab"]["product_specific_max_applicant_df"]))
    ps = [r for r in rows if r["_status"] == "PRE_REGULATORY" and r["_product_specific"]]
    caseA = max(ps, key=lambda r: r["lead_days"])
    anchorA = anchors[caseA["anchor_id"]]
    results.append(audit_case("CASE A — correct top over the full verified-link set",
                              caseA, anchorA, con, resolver, tokz, first_global, None, ct_by_id))

    # CASE B: protocol-legal top case — the frozen 5-year evidence window applied
    for r in rows:
        ad = vc.parse_date(r["anchor_date"]); ed = vc.parse_date(r["evidence_date"])
        r["_in_window"] = (ed is not None and vc.years_before(ad, 5) <= ed < ad)
    legal = [r for r in ps if r["_in_window"] and r["tier"] == "VERIFIED_L2"]
    caseB = max(legal, key=lambda r: r["lead_days"])
    anchorB = anchors[caseB["anchor_id"]]
    results.append(audit_case("CASE B — protocol-legal top (L2, inside the frozen 5-year window)",
                              caseB, anchorB, con, resolver, tokz, first_global, None, ct_by_id))
    l1 = [r for r in rows if r["tier"] == "VERIFIED_L1"]
    print(f"\n[AUDIT] L1 rows={len(l1)}, of which outside the 5-year window: "
          f"{sum(1 for r in l1 if not r['_in_window'])} "
          f"(b_links.py assigns L1 before the window test)")

    # CASE C: top case inside the committed (truncated) EVIDENCE_LINKS.jsonl
    links = vc.committed_links()
    com = [r for r in links if r["tier"] in ("VERIFIED_L1", "VERIFIED_L2")
           and r.get("regulatory_status") == "PRE_REGULATORY" and r.get("product_specific")]
    caseC = max(com, key=lambda r: r["lead_days"])
    anchorC = anchors[caseC["anchor_id"]]
    results.append(audit_case("CASE C — top case inside the committed (truncated) EVIDENCE_LINKS.jsonl",
                              caseC, anchorC, con, resolver, tokz, first_global, None, ct_by_id))

    print("\n" + "=" * 78)
    print("SUMMARY")
    print("=" * 78)
    for r in results:
        mech = all(c["pass"] for c in r["checks"])
        print(f"{r['label']}:")
        print(f"   mechanical checks: {'ALL PASS' if mech else 'FAIL ' + str([c['name'] for c in r['checks'] if not c['pass']])}")
        print(f"   post-approval title: {r['title_post_approval']}   "
              f"latest-plausible lead: {r['latest_plausible_lead']}   "
              f"token={r['token']} df={r['applicant_df']} distinctive={r['distinctive']}")

    payload = {"cases": results, "full_set_candidate_count": len(ps), "protocol_legal_candidate_count": len(legal), "l1_rows": len(l1), "l1_outside_window": sum(1 for r in l1 if not r["_in_window"])}
    OUT.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    print(f"\nwrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
