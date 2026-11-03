"""S-028 audit 12: Q-C - what relational evidence actually exists.

Enumerates every relation type in temporal_edges, proves which company->X and
company<->company relations do NOT exist, and measures edge coverage against events.
"""
from __future__ import annotations

from collections import Counter, defaultdict

from audit_common import RESEARCH, ro, now_iso, dump, pct


def main():
    c = ro(RESEARCH)
    out = {"generated_at": now_iso()}

    # ---- 1. full inventory of temporal_edges
    inv = []
    for rel, st, ot, n, nsub, nobj, vt_null, av_null, av_min, av_max, conf_min, conf_max in c.execute("""
            select relation, subject_type, object_type, count(*), count(distinct subject_id),
                   count(distinct object_id), sum(valid_time is null or valid_time=''),
                   sum(available_at is null or available_at=''),
                   min(available_at), max(available_at), min(confidence), max(confidence)
            from temporal_edges group by 1,2,3 order by 4 desc"""):
        inv.append({
            "relation": rel, "subject_type": st, "object_type": ot, "n_edges": n,
            "distinct_subjects": nsub, "distinct_objects": nobj,
            "valid_time_null": vt_null, "available_at_null": av_null,
            "available_at_min": av_min, "available_at_max": av_max,
            "confidence_min": conf_min, "confidence_max": conf_max,
        })
    out["temporal_edges_inventory"] = inv
    out["temporal_edges_total"] = sum(r["n_edges"] for r in inv)
    out["subject_types"] = [r[0] for r in c.execute("select distinct subject_type from temporal_edges")]
    out["object_types"] = [r[0] for r in c.execute("select distinct object_type from temporal_edges")]

    print("=" * 100)
    print("Q-C  temporal_edges inventory")
    for r in inv:
        print(f"  {r['relation']:32s} {r['subject_type']:8s}->{r['object_type']:20s} n={r['n_edges']:5d}"
              f" subj={r['distinct_subjects']:4d} obj={r['distinct_objects']:5d}"
              f" vt_null={r['valid_time_null']:5d} av=[{r['available_at_min']} .. {r['available_at_max']}]")
    print("  distinct subject_type:", out["subject_types"], " object_type:", out["object_types"])

    # ---- 2. explicit absence tests
    def q(sql, *a):
        return c.execute(sql, a).fetchone()[0]

    self_edge = q("select count(*) from temporal_edges where subject_type=object_type")
    company_company = q("select count(*) from temporal_edges where subject_type='Company' and object_type='Company'")
    # does any object_id resolve to a second company key?
    obj_is_company = q("""select count(*) from temporal_edges e join companies cc on cc.key = e.object_id""")
    subj_is_company = q("""select count(*) from temporal_edges e join companies cc on cc.key = e.subject_id""")
    # is any company key nested inside another company's alias list (= implicit ownership)?
    alias_owner = {}
    for k, js in c.execute("select key, aliases from companies"):
        import json as _json
        for a in _json.loads(js or "[]"):
            alias_owner.setdefault(a.upper(), set()).add(k)
    keys_upper = {k.upper(): k for k, _ in c.execute("select key, aliases from companies")}
    alias_names_are_other_companies = {a: sorted(s) for a, s in alias_owner.items() if a in keys_upper and keys_upper[a] not in s}
    out["absence"] = {
        "self_typed_edges": self_edge,
        "company_to_company_edges": company_company,
        "object_id_matching_a_company_key": obj_is_company,
        "subject_id_matching_a_company_key": subj_is_company,
        "alias_strings_that_are_another_companys_canonical_key": alias_names_are_other_companies,
        "company_to_technology_direct_edges": q(
            "select count(*) from temporal_edges where subject_type='Company' and object_type='Technology'"),
        "company_to_track_edges": q(
            "select count(*) from temporal_edges where object_type in ('Technology','Track') and subject_type='Company'"),
        "company_to_trial_edges": q(
            "select count(*) from temporal_edges where object_type in ('Trial','TrialSponsor')"),
        "company_to_publication_edges": q(
            "select count(*) from temporal_edges where object_type in ('Publication','Paper','Author')"),
        "company_to_event_edges": q(
            "select count(*) from temporal_edges where object_type in ('Event','RegulatoryEvent')"),
        "object_types_present": out["object_types"],
    }
    print("\n  absence tests:")
    for k, v in out["absence"].items():
        print(f"    {k}: {v}")

    # ---- 3. edge coverage vs the underlying evidence
    edges_products = q("select count(distinct object_id) from temporal_edges where relation='COMPANY_DEVELOPS_PRODUCT'")
    events_company = q("select count(*) from events where company_key is not null and company_key<>''")
    events_company_track = q("""select count(*) from events where company_key is not null and company_key<>''
                                and track_id is not null and track_id<>''""")
    out["edge_coverage"] = {
        "events_rows_total": q("select count(*) from events"),
        "events_with_company_key": events_company,
        "events_with_company_pct": pct(events_company, q("select count(*) from events")),
        "events_with_company_and_track": events_company_track,
        "events_with_company_and_track_pct": pct(events_company_track, q("select count(*) from events")),
        "company_develops_product_edges": q("select count(*) from temporal_edges where relation='COMPANY_DEVELOPS_PRODUCT'"),
        "distinct_products_in_edges": edges_products,
        "edge_to_event_ratio": pct(q("select count(*) from temporal_edges where relation='COMPANY_DEVELOPS_PRODUCT'"),
                                   events_company),
        "company_track_pairs_from_events": q("""select count(*) from (select distinct company_key, track_id from events
             where company_key<>'' and track_id<>'')"""),
    }
    print("\n  edge coverage:", out["edge_coverage"])

    # ---- 4. do edge valid_time / available_at inherit the event's?
    rows = c.execute("""select e.valid_time, e.available_at, ev.event_date, ev.published_at, ev.available_at
                        from temporal_edges e join events ev on ev.event_id = e.evidence_id
                        where e.relation='COMPANY_DEVELOPS_PRODUCT'""").fetchall()
    eq_vt = sum(1 for r in rows if (r[0] or "")[:10] == (r[2] or "")[:10])
    eq_av = sum(1 for r in rows if (r[1] or "") == (r[4] or ""))
    out["edge_time_inheritance"] = {
        "joined_edges": len(rows),
        "valid_time_equals_event_event_date": eq_vt,
        "available_at_equals_event_available_at": eq_av,
    }
    print("  edge time inheritance:", out["edge_time_inheritance"])

    # ---- 5. per-year edge counts (only relations that carry a usable date)
    peryear = defaultdict(Counter)
    for vt, rel in c.execute("""select substr(valid_time,1,4), relation from temporal_edges"""):
        peryear[rel][vt if vt else "NULL"] += 1
    out["edges_per_year"] = {rel: dict(sorted(c2.items())) for rel, c2 in peryear.items()}
    print("\n  edges per year:")
    for rel, d in out["edges_per_year"].items():
        print(f"    {rel}: {d}")

    # ---- 6. procurement_awards: the evidence table behind COMPANY_WINS_CONTRACT
    pa = c.execute("""select count(*), sum(company_key is null or company_key=''),
       sum(award_date is null or award_date=''), sum(announcement_date is null or announcement_date=''),
       sum(available_at is null or available_at=''), sum(pit_usable),
       min(available_at), max(available_at), avg(match_confidence),
       sum(buyer is null or buyer=''), sum(supplier is null or supplier='')
       from procurement_awards""").fetchone()
    out["procurement_awards"] = {
        "rows": pa[0], "company_key_null": pa[1],
        "award_date_null": pa[2], "announcement_date_null": pa[3],
        "available_at_null": pa[4], "pit_usable_sum": pa[5],
        "available_at_min": pa[6], "available_at_max": pa[7],
        "match_confidence_avg": round(pa[8], 6),
        "buyer_null": pa[9], "supplier_null": pa[10],
        "distinct_available_at": c.execute("select count(distinct available_at) from procurement_awards").fetchone()[0],
        "matched_alias_null": c.execute("select sum(matched_alias is null or matched_alias='') from procurement_awards").fetchone()[0],
        "company_keys_with_contracts": c.execute("select count(distinct company_key) from procurement_awards where company_key<>''").fetchone()[0],
        "distinct_buyers": c.execute("select count(distinct buyer) from procurement_awards").fetchone()[0],
    }
    print("\n  procurement_awards:", out["procurement_awards"])

    # ---- 7. financial_facts: evidence behind COMPANY_FILES_FINANCIAL_FACT
    ff = c.execute("""select count(*), count(distinct company_key), sum(valid_time is null or valid_time=''),
       sum(available_at is null or available_at=''), min(valid_time), max(valid_time),
       min(available_at), max(available_at), sum(payload is null or payload='')
       from financial_facts""").fetchone()
    out["financial_facts"] = {
        "rows": ff[0], "companies": ff[1], "valid_time_null": ff[2], "available_at_null": ff[3],
        "valid_time_range": [ff[4], ff[5]], "available_at_range": [ff[6], ff[7]], "payload_null": ff[8],
        "distinct_available_at": c.execute("select count(distinct available_at) from financial_facts").fetchone()[0],
        "company_identifiers_schemes": [list(r) for r in c.execute(
            "select scheme, count(*) from company_identifiers group by 1")],
    }
    print("  financial_facts:", out["financial_facts"])

    # ---- 8. other company-anchored evidence that is NOT an edge
    out["non_edge_company_evidence"] = {
        "company_identifiers": c.execute("select count(*) from company_identifiers").fetchone()[0],
        "publication_counts": c.execute("select count(*) from publication_counts").fetchone()[0],
        "publication_counts_companies": c.execute("select count(distinct company_key) from publication_counts").fetchone()[0],
        "publication_counts_year_range": list(c.execute("select min(year), max(year) from publication_counts").fetchone()),
        "publication_counts_grain": "company_key x year aggregate only (source=openalex_group_by_publication_year)",
        "companies": c.execute("select count(*) from companies").fetchone()[0],
        "companies_with_alias_list": c.execute(
            "select sum(aliases is not null and aliases<>'' and aliases<>'[]') from companies").fetchone()[0],
        "mean_aliases_per_company": round(c.execute(
            "select avg(json_array_length(aliases)) from companies where aliases<>''").fetchone()[0] or 0, 3),
        "max_aliases_per_company": c.execute(
            "select max(json_array_length(aliases)) from companies where aliases<>''").fetchone()[0],
    }
    print("\n  non-edge company evidence:", out["non_edge_company_evidence"])

    c.close()
    dump("12_relations", out)


if __name__ == "__main__":
    main()
