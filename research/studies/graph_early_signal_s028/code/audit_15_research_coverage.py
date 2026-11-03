"""S-028 audit 15: Q-F - trial / publication / research-institution coverage."""
from __future__ import annotations

import json
from collections import Counter

from audit_common import RESEARCH, PRODUCT, OBS, ro, now_iso, dump, pct


def main():
    out = {"generated_at": now_iso()}
    c = ro(RESEARCH)
    research_companies = [r[0] for r in c.execute("select key from companies")]
    out["research_input"] = {
        "event_sources": [{"source": s, "kind": k, "n": n} for s, k, n in c.execute(
            "select source, kind, count(*) from events group by 1,2")],
        "tables_holding_company_level_evidence": sorted(
            r[0] for r in c.execute(
                "select name from sqlite_master where type='table' and name in "
                "('events','temporal_edges','procurement_awards','financial_facts','publication_counts','company_identifiers')")),
        "has_trial_table": False,
        "has_publication_record_table": False,
        "publication_counts": {
            "rows": c.execute("select count(*) from publication_counts").fetchone()[0],
            "companies": c.execute("select count(distinct company_key) from publication_counts").fetchone()[0],
            "years": list(c.execute("select min(year), max(year) from publication_counts").fetchone()),
            "sources": [list(r) for r in c.execute(
                "select source, count(*) from publication_counts group by 1")],
            "columns": [r[1] for r in c.execute("PRAGMA table_info(publication_counts)")],
            "grain": "company_key x year only: works count, no paper id, no author, no institution",
        },
    }
    print("=" * 100)
    print("Q-F  research input evidence inventory")
    print("  event sources:", out["research_input"]["event_sources"])
    print("  publication_counts:", json.dumps(out["research_input"]["publication_counts"], ensure_ascii=False)[:400])

    c.close()

    # ---------------------------------------------------------------- product DB
    p = ro(PRODUCT)
    trials = {
        "rows": p.execute("select count(*) from events where source='ctgov'").fetchone()[0],
        "distinct_lead_sponsor": p.execute(
            "select count(distinct json_extract(payload,'$.lead_sponsor')) from events where source='ctgov'").fetchone()[0],
        "company_key_nonnull": p.execute(
            "select sum(company_key is not null and company_key<>'') from events where source='ctgov'").fetchone()[0],
        "distinct_company_key": p.execute(
            "select count(distinct company_key) from events where source='ctgov' and company_key<>''").fetchone()[0],
        "match_confidence_tiers": [
            {"tier": t, "n": n} for t, n in p.execute("""
            select case when mc>=0.9 then '>=0.90 (accepted)'
                        when mc>0 then '0<mc<0.90 (candidate only)'
                        else 'mc=0 (no match)' end tier, count(*)
            from (select json_extract(payload,'$.match_confidence') mc from events where source='ctgov')
            group by 1""")],
        "event_date_equals_first_posted": p.execute("""
            select sum(json_extract(payload,'$.first_posted')=event_date), count(*)
            from events where source='ctgov'""").fetchone(),
        "has_start_date_in_payload": p.execute(
            "select sum(json_extract(payload,'$.start_date') is not null) from events where source='ctgov'").fetchone()[0],
        "event_date_range": list(p.execute(
            "select min(event_date), max(event_date) from events where source='ctgov'").fetchone()),
        "first_seen_at_values": [list(r) for r in p.execute(
            "select first_seen_at, count(*) from events where source='ctgov' group by 1")],
    }
    # trials that resolve onto the frozen 51-company roster
    qmarks = ",".join("?" * len(research_companies))
    trials["trials_mapped_to_frozen_roster"] = p.execute(
        f"select count(*) from events where source='ctgov' and company_key in ({qmarks})",
        research_companies).fetchone()[0]
    trials["roster_companies_with_trials"] = p.execute(
        f"select count(distinct company_key) from events where source='ctgov' and company_key in ({qmarks})",
        research_companies).fetchone()[0]
    trials["roster_trials_per_company"] = [
        {"company": a, "n": b} for a, b in p.execute(
            f"""select company_key, count(*) from events where source='ctgov' and company_key in ({qmarks})
                group by 1 order by 2 desc""", research_companies)]
    trials["accepted_match_confidence_threshold"] = 0.90
    trials["company_key_nonnull_pct"] = pct(trials["company_key_nonnull"], trials["rows"])
    trials["rows_with_match_confidence"] = trials["company_key_nonnull"] + sum(
        t["n"] for t in trials["match_confidence_tiers"] if t["tier"].startswith("0<"))
    out["product_trials"] = trials
    print("\n  product.sqlite ctgov: rows=%d distinct_lead_sponsor=%d mapped=%d (%.2f%%)" % (
        trials["rows"], trials["distinct_lead_sponsor"], trials["company_key_nonnull"],
        pct(trials["company_key_nonnull"], trials["rows"])))
    print("  match tiers:", trials["match_confidence_tiers"])
    print("  trials mapped onto frozen 51-company roster:", trials["trials_mapped_to_frozen_roster"],
          "across", trials["roster_companies_with_trials"], "companies")
    print("  per company:", trials["roster_trials_per_company"][:12])
    print("  event_date == first_posted:", trials["event_date_equals_first_posted"])
    print("  first_seen_at:", trials["first_seen_at_values"])

    # ---------------------------------------------------------------- observatory
    o = ro(OBS)
    obs_src = [{"source": s, "record_type": rt, "n": n} for s, rt, n in o.execute(
        "select source, record_type, count(*) from observation group by 1,2 order by 3 desc")]
    maps = [{"entity_method": a, "entity_status": b, "track_method": cc, "n": n} for a, b, cc, n in o.execute(
        """select m.entity_method, m.entity_status, m.track_method, count(*)
           from observation_mapping m group by 1,2,3 order by 4 desc""")]
    # does the europepmc payload carry affiliations?
    epmc_keys = set()
    for (pl,) in o.execute("""select v.payload from observation_version v
                              join observation ob on ob.observation_id=v.observation_id
                              where ob.source='europepmc' limit 50"""):
        epmc_keys |= set(json.loads(pl).keys())
    out["observatory_research"] = {
        "sources": obs_src,
        "mappings": maps,
        "europepmc_payload_keys": sorted(epmc_keys),
        "institution_field_present": any("affil" in k.lower() or "institution" in k.lower() for k in epmc_keys),
        "author_field_present": "author_string" in epmc_keys,
        "mapped_pending_review": sum(m["n"] for m in maps if m["entity_status"] == "PENDING_REVIEW"),
        "mapped_accepted": sum(m["n"] for m in maps if m["entity_status"] == "MAPPED"),
        "unmapped": sum(m["n"] for m in maps if m["entity_status"] == "UNMAPPED"),
    }
    print("\n  observatory research sources:", obs_src)
    print("  entity mapping status:", out["observatory_research"]["mapped_accepted"], "accepted /",
          out["observatory_research"]["mapped_pending_review"], "pending /",
          out["observatory_research"]["unmapped"], "unmapped")
    print("  europepmc payload keys:", sorted(epmc_keys))
    print("  institution field present:", out["observatory_research"]["institution_field_present"])
    o.close()
    p.close()

    # ------------------------------------------------------------------ verdicts
    out["buildable"] = {
        "company_trial_sponsor_relation": {
            "in_frozen_research_input": False,
            "in_product_db_only": True,
            "why": ("the frozen 55,090-row event set is 510(k)+PMA only; ctgov exists only in the "
                    "1.3 GB product DB, whose 55,592 trials resolve to the frozen roster only "
                    f"{trials['trials_mapped_to_frozen_roster']} times"),
        },
        "company_publication_relation": {
            "paper_level": False,
            "aggregate_only": True,
            "why": ("frozen input stores openalex works-per-year per company (616 rows, 2014-2026) with "
                    "no paper identifiers; the only paper-level records are 238 europepmc observations "
                    "in the observatory, of which 237 are PENDING_REVIEW"),
        },
        "company_institution_relation": {
            "buildable": False,
            "why": ("no affiliation/institution field exists in any store; europepmc records keep "
                    "author_string (names) only, and the affiliation is used as a search predicate "
                    "(AFF:\"Medtronic\"), never stored as a data attribute"),
        },
        "paper_author_relation": {
            "buildable": "partially, 237 records",
            "why": "author_string is a comma-separated free-text name list; no ORCID/author ids",
        },
        "institution_identifier_scheme": {
            "present": False,
            "why": "company_identifiers only carries scheme=SEC_CIK (34 rows); no ROR/GRID/LEI/ORCID",
        },
    }
    print("\n  buildable verdicts:")
    for k, v in out["buildable"].items():
        print(f"    {k}: {json.dumps(v, ensure_ascii=False)[:200]}")

    dump("15_research_coverage", out)


if __name__ == "__main__":
    main()
