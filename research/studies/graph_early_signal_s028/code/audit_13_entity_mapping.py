"""S-028 audit 13: Q-D - company mapping governance and entity look-ahead.

Rebuilds the alias->company assignment the frozen input must have used, measures
which alias each event was attributed through, and compares alias event dates with
externally sourced acquisition close dates.
"""
from __future__ import annotations

import json
import re
from collections import Counter, defaultdict

from audit_common import RESEARCH, CFG, ro, now_iso, dump, pct

# Acquisition close dates looked up OUTSIDE this audit (marked as external). Where the
# source only fixes month/year, precision says so; the comparison below uses YYYY-MM.
ACQUISITIONS = [
    {"subsidiary_alias": "COVIDIEN", "parent": "medtronic", "close": "2015-01", "precision": "month",
     "url": "https://www.sec.gov/Archives/edgar/data/1613103/000119312515020681/d859999dex991.htm"},
    {"subsidiary_alias": "C R BARD", "parent": "bd", "close": "2017-12", "precision": "month",
     "url": "https://investors.bd.com/sec-filings/all-sec-filings/content/0001193125-17-383523/d517273dex991.htm"},
    {"subsidiary_alias": "BARD ACCESS SYSTEMS", "parent": "bd", "close": "2017-12", "precision": "month",
     "url": "https://investors.bd.com/sec-filings/all-sec-filings/content/0001193125-17-383523/d517273dex991.htm"},
    {"subsidiary_alias": "CAREFUSION", "parent": "bd", "close": "2015-03", "precision": "month",
     "url": "https://news.bd.com/2015-03-17-Becton-Dickinson-Completes-Acquisition-Of-CareFusion"},
    {"subsidiary_alias": "ST JUDE MEDICAL", "parent": "abbott", "close": "2017-01", "precision": "month",
     "url": "https://abbott.mediaroom.com/2017-01-04-Abbott-Completes-the-Acquisition-of-St-Jude-Medical"},
    {"subsidiary_alias": "WRIGHT MEDICAL", "parent": "stryker", "close": "2020-11", "precision": "month",
     "url": "https://www.nasdaq.com/press-release/stryker-completes-acquisition-of-wright-medical-2020-11-11"},
    {"subsidiary_alias": "MAKO SURGICAL", "parent": "stryker", "close": "2013-12", "precision": "month",
     "url": "https://investors.stryker.com/press-releases/news-details/2013/Stryker-Completes-Acquisition-of-MAKO-Surgical-Corp/default.aspx"},
    {"subsidiary_alias": "VARIAN MEDICAL SYSTEMS", "parent": "siemens_healthineers", "close": "2021-04",
     "precision": "month", "url": "https://www.siemens-healthineers.com/press/releases/varian-closing"},
    {"subsidiary_alias": "SHOCKWAVE MEDICAL", "parent": "johnson_johnson_medtech", "close": "2024-05",
     "precision": "month",
     "url": "https://www.investor.jnj.com/investor-news/news-details/2024/Johnson--Johnson-Completes-Acquisition-of-Shockwave-Medical/"},
    {"subsidiary_alias": "TOSHIBA MEDICAL", "parent": "canon_medical", "close": "2016-12", "precision": "month",
     "url": "https://global.canon/en/news/2016/20161219.html"},
    {"subsidiary_alias": "AXONICS", "parent": "boston_scientific", "close": "2024-11", "precision": "month",
     "url": "https://www.sec.gov/Archives/edgar/data/885725/000088572524000078/bsx-20241115.htm"},
    # NOT verified in this audit (no source fetched): listed so the residual risk is explicit.
    {"subsidiary_alias": "TYCO HEALTHCARE", "parent": "medtronic", "close": "2007-06", "precision": "unverified",
     "url": None},
    {"subsidiary_alias": "NUVASIVE", "parent": "globus_medical", "close": None, "precision": "unverified",
     "url": None},
    {"subsidiary_alias": "SMITHS MEDICAL", "parent": "icu_medical", "close": "2023-01", "precision": "unverified",
     "url": None},
    {"subsidiary_alias": "BIOMET", "parent": "zimmer_biomet", "close": "2015-06", "precision": "unverified",
     "url": None},
    {"subsidiary_alias": "AESCULAP", "parent": "bbraun", "close": None, "precision": "unverified",
     "url": None},
]


def norm(s: str) -> str:
    s = (s or "").upper()
    s = re.sub(r"[^A-Z0-9 ]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def main():
    out = {"generated_at": now_iso()}
    c = ro(RESEARCH)

    # ---------------------------------------------------------------- roster
    companies = {}
    for k, js in c.execute("select key, aliases from companies"):
        companies[k] = json.loads(js or "[]")
    out["companies"] = len(companies)
    out["aliases_total"] = sum(len(v) for v in companies.values())
    out["aliases_per_company"] = {k: len(v) for k, v in companies.items()}
    out["alias_list_carries_no_metadata"] = (
        "companies.aliases is a bare JSON string array: no parent/child direction, no "
        "acquisition date, no evidence id, no confidence, no source for any element")

    # -------------------------------------------------- reconstruct assignment
    pairs = c.execute("""select applicant_raw, company_key, count(*), min(event_date), max(event_date)
                         from events where company_key is not null and company_key<>''
                         group by 1,2""").fetchall()
    rule = Counter()
    assigned = []  # (applicant, company, matched_alias, n, first, last)
    for app, ck, n, f, l in pairs:
        na = norm(app)
        cands = [(a, norm(a)) for a in companies[ck]]
        hits = [(norm(a), a) for a, na2 in cands if na2 and na2 in na]
        if not hits:
            rule["no_alias_substring"] += 1
            assigned.append((app, ck, "__NO_ALIAS_SUBSTRING__", n, f, l))
            continue
        hits.sort(key=lambda x: -len(x[0]))
        matched = hits[0][1]
        rule["prefix_match" if na.startswith(norm(matched)) else "substring_only"] += 1
        assigned.append((app, ck, matched, n, f, l))

    out["alias_assignment_validation"] = {
        "mapped_applicant_company_pairs": len(pairs),
        "pairs_matched_by_alias_prefix": rule.get("prefix_match", 0),
        "pairs_matched_by_substring_only": rule.get("substring_only", 0),
        "pairs_with_no_alias_substring": rule.get("no_alias_substring", 0),
        "note": ("the 8-ish pairs with no alias substring prove the frozen build used an "
                 "additional rule not stored in the database, e.g. token match on 'BD'"),
    }
    print("=" * 100)
    print("Q-D  alias assignment validation:", out["alias_assignment_validation"])

    # events per alias
    per_alias = defaultdict(lambda: {"n": 0, "first": None, "last": None, "n_applicants": 0})
    for app, ck, alias, n, f, l in assigned:
        d = per_alias[(ck, alias)]
        d["n"] += n
        d["n_applicants"] += 1
        d["first"] = f if d["first"] is None else min(d["first"], f)
        d["last"] = l if d["last"] is None else max(d["last"], l)

    alias_rows = [{"company": k[0], "alias": k[1], "n_events": v["n"],
                   "n_applicant_strings": v["n_applicants"],
                   "first_event_date": v["first"], "last_event_date": v["last"],
                   "acquisition": None}
                  for k, v in per_alias.items()]
    for r in alias_rows:
        for a in ACQUISITIONS:
            if a["subsidiary_alias"] == r["alias"] and a["parent"] == r["company"]:
                r["acquisition"] = a
    alias_rows.sort(key=lambda r: -r["n_events"])
    out["alias_event_ranges_top40"] = alias_rows[:40]
    out["aliases_with_events"] = len(alias_rows)
    out["aliases_without_events"] = out["aliases_total"] - len(alias_rows)
    print(f"  aliases carrying events: {len(alias_rows)} / {out['aliases_total']}")
    for r in alias_rows[:12]:
        print(f"    {r['company']:24s} <= {r['alias']:34s} n={r['n_events']:5d} "
              f"{r['first_event_date']} .. {r['last_event_date']}")

    # ------------------------------------------- look-ahead against acquisitions
    # NOTE: counts must come from the reconstructed alias assignment, not SQL LIKE:
    # raw applicants write "C. R. Bard" / "C.R. Bard", which LIKE '%C R BARD%' misses.
    applicant_alias = {(app, ck): alias for app, ck, alias, n, f, l in assigned}
    acquisition_check = []
    total_pre = 0
    for a in ACQUISITIONS:
        rows = [r for r in alias_rows if r["alias"] == a["subsidiary_alias"] and r["company"] == a["parent"]]
        if not rows:
            continue
        r = rows[0]
        rec = dict(a)
        rec.update({"n_events": r["n_events"], "first_event_date": r["first_event_date"],
                    "last_event_date": r["last_event_date"]})
        if a["precision"] != "unverified" and a["close"]:
            close_ym = a["close"]
            npre = 0
            codes_pre = set()
            for app, ed, pc in c.execute(
                    "select applicant_raw, event_date, product_code from events where company_key=?",
                    (a["parent"],)):
                if applicant_alias.get((app, a["parent"])) != a["subsidiary_alias"]:
                    continue
                if ed[:7] < close_ym:
                    npre += 1
                    codes_pre.add(pc)
            rec["events_before_acquisition_close"] = npre
            rec["pre_acquisition_product_codes"] = len(codes_pre)
            total_pre += npre
        acquisition_check.append(rec)
    out["acquisition_lookahead"] = {
        "rule": ("an event filed by a still-independent subsidiary BEFORE the parent's "
                 "acquisition close is attributed to the parent by the frozen build"),
        "verified_entries": acquisition_check,
        "total_pre_acquisition_events_attributed_to_parents": total_pre,
    }
    print("\n  acquisition look-ahead:")
    for r in acquisition_check:
        print(f"    {r['parent']:24s} <= {r['subsidiary_alias']:24s} close={r['close']} "
              f"({r['precision']}) events={r['n_events']:5d} "
              f"pre_close={r.get('events_before_acquisition_close','n/a')} first={r['first_event_date']}")

    # ------------------------------------- how much of each company is non-organic
    per_company = defaultdict(lambda: {"total": 0, "acquired_alias_events": 0, "aliases": []})
    for r in alias_rows:
        per_company[r["company"]]["total"] += r["n_events"]
    for a in ACQUISITIONS:
        if a["precision"] == "unverified":
            continue
        rows = [r for r in alias_rows if r["alias"] == a["subsidiary_alias"] and r["company"] == a["parent"]]
        if rows:
            per_company[a["parent"]]["acquired_alias_events"] += rows[0]["n_events"]
            per_company[a["parent"]]["aliases"].append({"alias": a["subsidiary_alias"],
                                                        "n": rows[0]["n_events"],
                                                        "close": a["close"]})
    out["company_alias_composition"] = {
        k: {"total_events": v["total"], "events_via_acquired_aliases": v["acquired_alias_events"],
            "pct_via_acquired_aliases": pct(v["acquired_alias_events"], v["total"]),
            "acquired_aliases": v["aliases"]}
        for k, v in per_company.items() if v["aliases"]}
    out["n_parents_with_verified_acquired_aliases"] = len(out["company_alias_composition"])
    print("\n  share of each parent's events that arrive through an acquired alias:")
    for k, v in out["company_alias_composition"].items():
        print(f"    {k:24s} {v['events_via_acquired_aliases']:5d}/{v['total_events']:5d} "
              f"= {v['pct_via_acquired_aliases']}%  {[a['alias'] for a in v['acquired_aliases']]}")

    # --------------------------- applicant strings that themselves declare parentage
    markers = ["SUBSIDIARY", "WHOLLY OWNED", "PART OF", "A DIVISION OF", "NOW PART OF", "(AKA"]
    declared = Counter()
    for app, n in c.execute("""select applicant_raw, count(*) from events group by 1"""):
        ua = (app or "").upper()
        for m in markers:
            if m in ua:
                declared[m] += n
                break
    out["applicant_strings_declaring_parentage"] = {
        "marker_hits": dict(declared),
        "total_events_with_declared_parentage": sum(declared.values()),
        "pct_of_all_events": pct(sum(declared.values()), 55090),
    }
    print("\n  applicant strings that declare parentage:",
          out["applicant_strings_declaring_parentage"])

    # ------------------------------------------- mapping null rates (governance)
    nulls = {}
    for src, n, cnull, tnull, pcnull in c.execute("""select source, count(*),
            sum(company_key is null or company_key=''), sum(track_id is null or track_id=''),
            sum(product_code is null or product_code='') from events group by 1"""):
        nulls[src] = {"rows": n, "company_key_null": cnull,
                      "company_key_null_pct": pct(cnull, n),
                      "track_id_null": tnull, "track_id_null_pct": pct(tnull, n),
                      "product_code_null": pcnull, "product_code_null_pct": pct(pcnull, n)}
    out["mapping_null_rates"] = nulls
    out["applicant_strings"] = {
        "distinct_applicant_raw_510k": c.execute(
            "select count(distinct applicant_raw) from events where source='openfda_device_510k_bulk'").fetchone()[0],
        "distinct_applicant_raw_pma": c.execute(
            "select count(distinct applicant_raw) from events where source='openfda_device_pma_bulk'").fetchone()[0],
        "companies_table": c.execute("select count(*) from companies").fetchone()[0],
        "companies_with_ticker": c.execute("select sum(ticker is not null and ticker<>'') from companies").fetchone()[0],
        "companies_with_cik_column": c.execute("select sum(cik is not null and cik<>'') from companies").fetchone()[0],
        "company_identifiers_rows": c.execute("select count(*) from company_identifiers").fetchone()[0],
    }
    print("\n  mapping null rates:", json.dumps(nulls, ensure_ascii=False))
    print("  applicant/roster:", out["applicant_strings"])

    # ------------- ambiguity check: same applicant string under two companies?
    amb = c.execute("""select applicant_raw, count(distinct company_key) nn from events
                       where company_key<>'' group by 1 having nn>1""").fetchall()
    out["ambiguous_applicant_strings"] = {"n": len(amb), "examples": amb[:10]}

    c.close()
    dump("13_entity_mapping", out)


if __name__ == "__main__":
    main()
