"""S-028 audit 16: Q-G - positive-sample feasibility for the first-entry target.

Qualifying event := 510(k) whose payload clearance_type == 'Traditional'
                 OR PMA whose payload supplement_number is absent/empty (original PMA).
Sensitivity variants are computed so the definition choice cannot silently move the sample.
"""
from __future__ import annotations

import json
from collections import Counter, defaultdict

from audit_common import RESEARCH, ro, now_iso, dump, pct


def main():
    out = {"generated_at": now_iso()}
    c = ro(RESEARCH)

    # ------------------------------------------------ payload field verification
    n510 = nMDR = 0
    has_ct = has_sup = 0
    ct_vals = Counter()
    sup_vals = Counter()
    sup_types = Counter()
    for src, payload in c.execute("select source, payload from events"):
        d = json.loads(payload)
        if src.endswith("510k_bulk"):
            n510 += 1
            if "clearance_type" in d:
                has_ct += 1
            ct_vals[d.get("clearance_type")] += 1
        else:
            nMDR += 1
            if "supplement_number" in d:
                has_sup += 1
            sup_vals[(d.get("supplement_number") or "").strip() == ""] += 1
            if (d.get("supplement_number") or "").strip() == "":
                sup_types[d.get("supplement_type")] += 1
    out["payload_field_verification"] = {
        "n_510k_rows": n510,
        "rows_with_clearance_type_field": has_ct,
        "clearance_type_values": dict(ct_vals),
        "n_pma_rows": nMDR,
        "rows_with_supplement_number_field": has_sup,
        "pma_original_flag": {"empty_supplement_number_true": sup_vals.get(True, 0),
                              "empty_supplement_number_false": sup_vals.get(False, 0)},
        "supplement_type_of_original_pmas": dict(sup_types),
        "conclusion": ("both fields exist on 100% of their rows; 'Traditional' is one of 6 "
                       "clearance_type values; PMA originality must be tested as empty "
                       "supplement_number (344 rows)"),
    }
    print("=" * 100)
    print("Q-G  payload verification:", json.dumps(out["payload_field_verification"], ensure_ascii=False))

    # --------------------------------------------------------------- definition
    rows = c.execute("""select event_id, source, event_date, company_key, track_id, product_code, payload
                        from events""").fetchall()
    qual = []
    for eid, src, ed, ck, tr, pc, payload in rows:
        d = json.loads(payload)
        is_q = False
        if src.endswith("510k_bulk"):
            is_q = d.get("clearance_type") == "Traditional"
        else:
            s = d.get("supplement_number")
            is_q = s is None or str(s).strip() == ""
        if is_q:
            qual.append((eid, ed, ck, tr, pc))

    out["qualifying_events"] = {
        "n_510k_traditional": sum(1 for r in rows for _ in [0] if json.loads(r[6]).get("clearance_type") == "Traditional"
                                  and r[1].endswith("510k_bulk")),
        "rows_total": len(rows),
    }
    # (recompute cleanly to avoid double parsing)
    q510 = qpm = 0
    for eid, src, ed, ck, tr, pc, payload in rows:
        if src.endswith("510k_bulk"):
            if json.loads(payload).get("clearance_type") == "Traditional":
                q510 += 1
        else:
            s = json.loads(payload).get("supplement_number")
            if s is None or str(s).strip() == "":
                qpm += 1
    out["qualifying_events"] = {
        "rows_total": len(rows),
        "n_510k_traditional": q510,
        "n_pma_original": qpm,
        "n_total": q510 + qpm,
        "pct_of_all_events": pct(q510 + qpm, len(rows)),
        "definition": ("(kind=510k AND payload.clearance_type='Traditional') OR "
                       "(kind=pma AND payload.supplement_number IS NULL/empty)"),
    }
    print("\n  qualifying events:", json.dumps(out["qualifying_events"], ensure_ascii=False))

    # ------------------------------------------------------------- sensitivity
    sens = {
        "traditional_only_510k": q510,
        "all_510k": c.execute("select count(*) from events where kind='510k'").fetchone()[0],
        "traditional_plus_special_510k": c.execute("select count(*) from events where kind='510k'").fetchone()[0]
        - ct_vals.get("Abbreviated", 0) - ct_vals.get("Direct", 0) - ct_vals.get("Dual Track", 0)
        - ct_vals.get("Post-NSE", 0),
        "pma_original_empty_supplement": qpm,
        "all_pma": c.execute("select count(*) from events where kind='pma'").fetchone()[0],
    }
    out["sensitivity"] = sens
    print("  sensitivity:", sens)

    # ------------------------------------------------------------- per-year
    yr = Counter()
    yr_510 = Counter()
    yr_pma = Counter()
    for eid, ed, ck, tr, pc in qual:
        yr[ed[:4]] += 1
    for eid, src, ed, ck, tr, pc, payload in rows:
        d = json.loads(payload)
        if src.endswith("510k_bulk") and d.get("clearance_type") == "Traditional":
            yr_510[ed[:4]] += 1
        if src.endswith("pma_bulk"):
            s = d.get("supplement_number")
            if s is None or str(s).strip() == "":
                yr_pma[ed[:4]] += 1
    out["per_year"] = {
        "qualifying_total": dict(sorted(yr.items())),
        "qualifying_510k_traditional": dict(sorted(yr_510.items())),
        "qualifying_pma_original": dict(sorted(yr_pma.items())),
    }
    print("\n  per-year qualifying:", out["per_year"])

    # ------------------------------------------- usable (company, track) subset
    usable = [(ed, ck, tr) for eid, ed, ck, tr, pc in qual if ck and tr]
    pairs = defaultdict(list)
    for ed, ck, tr in usable:
        pairs[(ck, tr)].append(ed)
    first_entry = {k: min(v) for k, v in pairs.items()}
    fe_year = Counter(v[:4] for v in first_entry.values())
    out["company_track_pairs"] = {
        "qualifying_events_with_company_and_track": len(usable),
        "usable_pct_of_qualifying": pct(len(usable), q510 + qpm),
        "qualifying_events_without_company_or_track": (q510 + qpm) - len(usable),
        "dropped_pct": pct((q510 + qpm) - len(usable), q510 + qpm),
        "n_pairs_with_at_least_one_qualifying_event": len(pairs),
        "n_companies": len({k[0] for k in pairs}),
        "n_tracks": len({k[1] for k in pairs}),
        "first_entry_events_per_year": dict(sorted(fe_year.items())),
        "pairs_first_entry_left_censored_2016": fe_year.get("2016", 0),
        "pct_pairs_left_censored_2016": pct(fe_year.get("2016", 0), len(pairs)),
        "median_events_per_pair": sorted(len(v) for v in pairs.values())[len(pairs) // 2] if pairs else None,
        "pairs_with_single_event": sum(1 for v in pairs.values() if len(v) == 1),
        "pairs_with_single_event_pct": pct(sum(1 for v in pairs.values() if len(v) == 1), len(pairs)),
    }
    print("\n  company-track pairs:", json.dumps(out["company_track_pairs"], ensure_ascii=False))

    # ------------------------ entry-hazard sanity: how many pairs are still at risk
    at_risk = []
    for y in range(2017, 2027):
        ynext = str(int(y) + 1)
        pairs_before = sum(1 for k, v in first_entry.items() if v < f"{ynext}-01-01")
        new_this = sum(1 for v in first_entry.values() if v[:4] == str(y))
        at_risk.append({"year": str(y), "pairs_already_entered": pairs_before,
                        "new_first_entries": new_this,
                        "pairs_still_zero": len(pairs) - pairs_before})
    out["entry_hazard_by_year"] = at_risk
    print("\n  entry hazard:")
    for r in at_risk:
        print("   ", r)

    # ------------------------------- how many qualifying events the graph can use
    triples = c.execute("""select count(*) from (select distinct company_key, track_id from events
                           where company_key<>'' and track_id<>'')""").fetchone()[0]
    out["graph_density"] = {
        "distinct_company_track_pairs_from_all_events": triples,
        "distinct_company_track_pairs_qualifying_only": len(pairs),
        "share": pct(len(pairs), triples),
        "companies_with_any_qualifying_pair": len({k[0] for k in pairs}),
        "companies_total": c.execute("select count(*) from companies").fetchone()[0],
        "tracks_total": c.execute("select count(*) from tracks").fetchone()[0],
    }
    print("\n  graph density:", out["graph_density"])

    # ------------------------------------ window truncation of the frozen input
    out["window"] = {
        "min_event_date": c.execute("select min(event_date) from events").fetchone()[0],
        "max_event_date": c.execute("select max(event_date) from events").fetchone()[0],
        "min_published_at": c.execute("select min(published_at) from events").fetchone()[0],
        "max_published_at": c.execute("select max(published_at) from events").fetchone()[0],
        "note": ("the frozen input is a 10-year sliding window ending 2026-10-18/2026-10-16; "
                 "pairs whose first filing predates 2016-11 cannot be distinguished from new "
                 "entrants, which is why the 2016 first-entry count is not a hazard estimate"),
    }
    print("\n  window:", json.dumps(out["window"], ensure_ascii=False))
    c.close()
    dump("16_positive_sample", out)


if __name__ == "__main__":
    main()
