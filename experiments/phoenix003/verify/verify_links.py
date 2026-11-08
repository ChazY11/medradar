"""STEP 3 — independent re-implementation of the L1/L2 link tiers.

Protocol 6.1, implemented from the frozen text (not from the author's code):

    L2: same firm lineage on the evidence record (lead_sponsor / firm_affiliations)
        AND exact whole-token identity of at least one anchor distinctive token with a whole
            token of the evidence record's intervention name or title (CT.gov) or title or
            abstract (EPMC)
        AND evidence public date strictly before the milestone, inside [a-5y, a-1d].
    L1: the evidence record cites an NCT identifier present in the CT.gov corpus whose sponsor
        is the firm's lineage, and the L2 name identity also holds.

The anchor file supplies ``distinctive_tokens`` verbatim (token selection is the author's frozen
rule; token matching here is the verifier's).

Two readings are computed for each source, because the protocol and the author's implementation
differ on which text fields count:
  * PROTOCOL — CT.gov: brief+official title + interventions; EPMC: title + abstract
  * AUTHOR   — CT.gov: brief title + interventions;           EPMC: title+abstract+keywords+mesh
  * L1 always follows the author's identifier-chain construction (it is the only one defined).

In snapshot mode only the corpus that existed when the snapshot was taken is used
(ctgov_compact.jsonl.gz); live mode uses all four frozen corpora.

Run:  PHOENIX_VERIFY_MODE=snapshot python .../verify_links.py   (or live, the default)
"""
from __future__ import annotations

import collections
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import vcommon as vc

OUT = Path(__file__).resolve().parent / ("out_links.json" if vc.MODE == "live"
                                         else "out_links_snapshot.json")
BRAND = set(vc.load_json(vc.DATASET / "frozen_vocab.json")["brand_tokens"])
NCT_RE = re.compile(r"NCT\d{8}")

SNAPSHOT_CORPORA = ["ctgov_compact.jsonl.gz"]
LIVE_CORPORA = ["ctgov_compact.jsonl.gz", "ctgov_ext_compact.jsonl.gz",
                "epmc_compact.jsonl.gz", "epmc_ext_compact.jsonl.gz"]
CTGOV_FILES = [f for f in LIVE_CORPORA if f.startswith("ctgov")]
EPMC_FILES = [f for f in LIVE_CORPORA if f.startswith("epmc")]
if vc.MODE == "snapshot":
    CTGOV_FILES = [f for f in CTGOV_FILES if f in SNAPSHOT_CORPORA]
    EPMC_FILES = [f for f in EPMC_FILES if f in SNAPSHOT_CORPORA]
EPMC_EXCLUDED_SOURCES = {"PAT"}


def pctl(sv, q):
    pos = q * (len(sv) - 1)
    lo = int(pos)
    hi = min(lo + 1, len(sv) - 1)
    frac = pos - lo
    return sv[lo] * (1 - frac) + sv[hi] * frac


def statsv(vals):
    sv = sorted(vals)
    n = len(sv)
    if not n:
        return {}
    return {"n": n, "ge_90": sum(1 for v in sv if v >= 90),
            "ge_180": sum(1 for v in sv if v >= 180),
            "ge_365": sum(1 for v in sv if v >= 365),
            "share_ge_90": round(sum(1 for v in sv if v >= 90) / n, 6),
            "median": pctl(sv, 0.5), "q1": pctl(sv, 0.25), "q3": pctl(sv, 0.75),
            "min": sv[0], "max": sv[-1]}


def load_ctgov(resolver):
    recs, stats = [], collections.Counter()
    for name in CTGOV_FILES:
        p = vc.DATASET / name
        if not p.exists():
            stats["missing::" + name] += 1
            continue
        for r in vc.read_jsonl_gz(p):
            stats["records"] += 1
            firms = [f for f in str(r.get("source_firm") or "").split("+") if f]
            sponsor_fields = [r.get("lead_sponsor") or ""] + list(r.get("collaborators") or [])
            firm_verified = set()
            for s in sponsor_fields:
                f, _ = resolver.resolve(str(s))
                if f:
                    firm_verified.add(f)
            iv = [x.get("name") or "" for x in (r.get("interventions") or [])
                  if isinstance(x, dict)]
            rec = {
                "source": "ctgov", "id": r.get("nct_id"), "firms": firms,
                "firm_verified": firm_verified, "title": r.get("brief_title") or "",
                "date": vc.parse_date(r.get("first_posted")),
                "date_str": r.get("first_posted"),
                "date_sens": r.get("last_update_posted"),
                "tok_author": set(), "tok_protocol": set(),
            }
            for chunk in [r.get("brief_title") or ""] + iv:
                rec["tok_author"] |= set(vc.tokens(chunk))
            for chunk in [r.get("brief_title") or "", r.get("official_title") or ""] + iv:
                rec["tok_protocol"] |= set(vc.tokens(chunk))
            recs.append(rec)
            stats["file::" + name] += 1
    return recs, dict(stats)


def load_epmc(resolver):
    recs, stats = [], collections.Counter()
    for name in EPMC_FILES:
        p = vc.DATASET / name
        if not p.exists():
            stats["missing::" + name] += 1
            continue
        for r in vc.read_jsonl_gz(p):
            stats["records"] += 1
            src_type = str(r.get("source") or "UNKNOWN").upper()
            stats["source::" + src_type] += 1
            if src_type in EPMC_EXCLUDED_SOURCES:
                stats["excluded_patent"] += 1
                continue
            firms = [f for f in str(r.get("source_firm") or "").split("+") if f]
            firm_verified = set()
            for a in (r.get("firm_affiliations") or []):
                f, _ = resolver.resolve(str(a))
                if f:
                    firm_verified.add(f)
            title = r.get("title") or ""
            abstract = r.get("abstract") or ""
            keywords = r.get("keywords") or []
            mesh = r.get("mesh_terms") or []
            d = (vc.parse_date(r.get("first_publication_date"))
                 or vc.parse_date(r.get("electronic_publication_date"))
                 or vc.parse_date(r.get("first_index_date")))
            if d is None and r.get("pub_year"):
                d = vc.parse_date(str(r["pub_year"]))
            rec = {
                "source": "epmc", "id": r.get("pmid") or r.get("doi") or r.get("id"),
                "firms": firms, "firm_verified": firm_verified,
                "title": title, "date": d,
                "date_str": d.isoformat() if d else None,
                "date_sens": r.get("first_index_date") or r.get("electronic_publication_date"),
                "date_basis": r.get("date_basis"),
                "journal": r.get("journal_title"),
                "nct_ids": sorted(set(NCT_RE.findall(title + " " + abstract))),
                "tok_author": set(), "tok_protocol": set(),
            }
            for chunk in [title, abstract] + list(keywords) + list(mesh):
                rec["tok_author"] |= set(vc.tokens(chunk))
            for chunk in (title, abstract):
                rec["tok_protocol"] |= set(vc.tokens(chunk))
            recs.append(rec)
            stats["file::" + name] += 1
    return recs, dict(stats)


def derive(anchors, pools, field, years, firm_ncts, ct_by_id, ct_tok_field):
    """Return (per_anchor_max_lead, rows, tier_counts) for one text-field reading."""
    index = collections.defaultdict(list)
    for (src, firm), recs in pools.items():
        for r in recs:
            for t in r[field]:
                index[(src, firm, t)].append(r)
    per_anchor, rows, tiers = {}, [], collections.Counter()
    for a in anchors:
        firm = a["firm"]
        adate = vc.parse_date(a["anchor_date"])
        w0 = vc.years_before(adate, years)
        seen, best = set(), None
        for tok in (a.get("distinctive_tokens") or []):
            for src in ("ctgov", "epmc"):
                for r in index.get((src, firm, tok), []):
                    d = r["date"]
                    if d is None:
                        continue
                    if d >= adate:
                        continue
                    key = (src, r["id"], tok)
                    if key in seen:
                        continue
                    seen.add(key)
                    # L1 identifier chain (EPMC -> NCT id present in a firm-verified CT.gov trial
                    # that itself carries the token in its author field)
                    tier = None
                    if src == "epmc":
                        for nct in r.get("nct_ids", []):
                            ct = ct_by_id.get(nct)
                            if ct and firm in ct["firm_verified"] and firm in ct["firms"] \
                                    and tok in ct[ct_tok_field]:
                                tier = "VERIFIED_L1"
                                break
                    if tier is None:
                        tier = "VERIFIED_L2" if d >= w0 else "REJECTED_L5"
                    if tier == "REJECTED_L5":
                        continue
                    lead = (adate - d).days
                    tiers[tier] += 1
                    rows.append({"anchor_id": a["anchor_id"], "firm": firm,
                                 "milestone_key": a["milestone_key"],
                                 "product_code": a["product_code"],
                                 "anchor_date": a["anchor_date"], "tier": tier,
                                 "evidence_source": src, "evidence_id": r["id"],
                                 "evidence_date": r["date_str"],
                                 "evidence_title": r["title"][:200], "matched_token": tok,
                                 "lead_days": lead, "brand_token": tok in BRAND})
                    best = lead if best is None else max(best, lead)
        if best is not None:
            per_anchor[a["anchor_id"]] = best
    return per_anchor, rows, tiers


def main():
    rules = vc.load_json(vc.EXP / "FROZEN_RULES.json")
    resolver = vc.Resolver()
    years = int(rules["evidence"]["window_years_before_anchor"])
    anchors = vc.committed_anchors()
    anchors.sort(key=lambda a: a["anchor_id"])
    print("=" * 78)
    print(f"LINK RE-IMPLEMENTATION  [mode={vc.MODE}]")
    print("=" * 78)
    print(f"anchors: {len(anchors)}   corpora used: ctgov={CTGOV_FILES} epmc={EPMC_FILES}")

    ctgov, ct_stats = load_ctgov(resolver)
    epmc, ep_stats = load_epmc(resolver)
    print(f"ctgov records={len(ctgov)} stats={ct_stats}")
    print(f"epmc  records={len(epmc)} stats={ep_stats}")

    pools = collections.defaultdict(list)
    for r in ctgov:
        for f in r["firms"]:
            if f in r["firm_verified"]:
                pools[("ctgov", f)].append(r)
    for r in epmc:
        for f in r["firms"]:
            if f in r["firm_verified"]:
                pools[("epmc", f)].append(r)

    firm_ncts = collections.defaultdict(set)
    ct_by_id = {}
    for r in ctgov:
        ct_by_id[r["id"]] = r
        for f in r["firms"]:
            if f in r["firm_verified"]:
                firm_ncts[f].add(r["id"])

    # reading A: author's fields.  reading B: protocol fields.
    a_auth, rows_auth, tiers_auth = derive(anchors, pools, "tok_author", years,
                                           firm_ncts, ct_by_id, "tok_author")
    a_prot, rows_prot, tiers_prot = derive(anchors, pools, "tok_protocol", years,
                                           firm_ncts, ct_by_id, "tok_author")

    print(f"\nINDEPENDENT AUTHOR-field reading : k={len(a_auth)} tiers={dict(tiers_auth)} "
          f"{statsv(list(a_auth.values()))}")
    print(f"INDEPENDENT PROTOCOL-field reading: k={len(a_prot)} tiers={dict(tiers_prot)} "
          f"{statsv(list(a_prot.values()))}")

    links = vc.committed_links()
    com_v = [r for r in links if r["tier"] in ("VERIFIED_L1", "VERIFIED_L2")]
    com_by_anchor = collections.defaultdict(list)
    for r in com_v:
        com_by_anchor[r["anchor_id"]].append(r)
    com_lead = {aid: max(x["lead_days"] for x in rs) for aid, rs in com_by_anchor.items()}
    com_tiers = collections.Counter(r["tier"] for r in com_v)
    print(f"\nCOMMITTED EVIDENCE_LINKS verified rows: {len(com_v)} tiers={dict(com_tiers)}"
          f"  k={len(com_lead)}")
    print(f"COMMITTED lead stats: {statsv(list(com_lead.values()))}")
    b = vc.result_json("b_links.json")
    print(f"b_links.json: anchors_with_verified_link={b['anchors_with_verified_link']}"
          f" link_rows={b.get('link_rows')} tier_counts={b.get('tier_counts')}")

    out = {}
    for label, per_anchor, rows in (("AUTHOR_fields", a_auth, rows_auth),
                                    ("PROTOCOL_fields", a_prot, rows_prot)):
        only_mine = sorted(set(per_anchor) - set(com_lead))
        only_com = sorted(set(com_lead) - set(per_anchor))
        diff = sorted((aid, per_anchor[aid], com_lead[aid])
                      for aid in set(per_anchor) & set(com_lead) if per_anchor[aid] != com_lead[aid])
        row_set = {(r["anchor_id"], r["evidence_id"], r["matched_token"], r["tier"]) for r in rows}
        com_set = {(r["anchor_id"], r["evidence_id"], r["matched_token"], r["tier"]) for r in com_v}
        print(f"\n--- {label} vs committed ---")
        print(f"anchor sets: mine={len(per_anchor)} committed={len(com_lead)}"
              f" identical={len(set(per_anchor)&set(com_lead))} only-mine={len(only_mine)}"
              f" only-committed={len(only_com)} lead-diff={len(diff)}")
        print(f"row sets  : mine={len(row_set)} committed={len(com_set)}"
              f" identical={len(row_set&com_set)} mine-only={len(row_set-com_set)}"
              f" com-only={len(com_set-row_set)}")
        for aid in only_mine[:8]:
            r = next(x for x in rows if x["anchor_id"] == aid)
            print(f"  only-mine {aid[:12]} {r['firm']:20s} {r['milestone_key']:10s}"
                  f" {r['tier']} tok={r['matched_token']:16s} {r['evidence_source']}:"
                  f"{r['evidence_id']} lead={r['lead_days']}")
        for aid in only_com[:8]:
            r = com_by_anchor[aid][0]
            print(f"  only-com  {aid[:12]} {r['firm']:20s} {r['milestone_key']:10s}"
                  f" {r['tier']} tok={r['matched_token']:16s} {r['evidence_source']}:"
                  f"{r['evidence_id']} lead={r['lead_days']}")
        for x in diff[:12]:
            print(f"  lead-diff {x[0][:12]} mine={x[1]} committed={x[2]}")
        for x in sorted(com_set - row_set)[:12]:
            r = next(y for y in com_v
                     if (y["anchor_id"], y["evidence_id"], y["matched_token"], y["tier"]) == x)
            print(f"  com-row-only {x[0][:12]} {r['milestone_key']:10s} {r['tier']}"
                  f" {r['matched_token']:16s} {r['evidence_source']}:{r['evidence_id']}"
                  f" {r['evidence_date']} {r['evidence_title'][:55]}")
        out[label] = {"k": len(per_anchor), "tiers": dict(
                          collections.Counter(r["tier"] for r in rows)),
                      "stats": statsv(list(per_anchor.values())),
                      "only_mine": only_mine, "only_committed": only_com,
                      "lead_diff": diff,
                      "row_mine_only": [list(x) for x in sorted(row_set - com_set)],
                      "row_committed_only": [list(x) for x in sorted(com_set - row_set)]}

    # coverage with the corpora available in this mode
    cov = collections.Counter()
    per_firm = {}
    for a in anchors:
        firm = a["firm"]
        adate = vc.parse_date(a["anchor_date"])
        w0 = vc.years_before(adate, years)
        n = sum(1 for src in ("ctgov", "epmc") for r in pools.get((src, firm), [])
                if r["date"] is not None and w0 <= r["date"] < adate)
        if n > 0:
            cov["anchors_with_evidence"] += 1
        per_firm.setdefault(firm, {"anchors": 0, "with_window_evidence": 0,
                                   "corpus_records": 0})
        per_firm[firm]["anchors"] += 1
        if n > 0:
            per_firm[firm]["with_window_evidence"] += 1
    for f in per_firm:
        per_firm[f]["corpus_records"] = sum(len(pools.get((s, f), []))
                                            for s in ("ctgov", "epmc"))
    print(f"\nanchors with >=1 firm-verified record in window: "
          f"{cov['anchors_with_evidence']}/{len(anchors)}")
    for f in sorted(per_firm):
        d = per_firm[f]
        print(f"  {f:22s} anchors={d['anchors']:3d} with_window_evidence="
              f"{d['with_window_evidence']:3d} corpus_records={d['corpus_records']:5d}")

    brand_rows = [r for r in com_v if r["matched_token"] in BRAND]
    print(f"\ncommitted verified rows matched on a brand token: {len(brand_rows)}")

    payload = {
        "mode": vc.MODE, "anchors": len(anchors),
        "ctgov_files": CTGOV_FILES, "epmc_files": EPMC_FILES,
        "ctgov_stats": ct_stats, "epmc_stats": ep_stats,
        "author_fields": out["AUTHOR_fields"],
        "protocol_fields": out["PROTOCOL_fields"],
        "committed": {"k": len(com_lead), "tiers": dict(com_tiers),
                      "stats": statsv(list(com_lead.values())),
                      "rows": len(com_v)},
        "b_links": {"k": b["anchors_with_verified_link"], "tier_counts": b.get("tier_counts")},
        "coverage": {"anchors_with_evidence": cov["anchors_with_evidence"],
                     "anchors": len(anchors)},
        "per_firm": per_firm,
        "brand_token_rows": len(brand_rows),
        "rows_author": rows_auth,
    }
    OUT.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"\nwrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
