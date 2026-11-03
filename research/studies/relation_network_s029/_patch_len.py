import pathlib
p=pathlib.Path("code/s029_07_claims.py"); s=p.read_text(encoding="utf-8")
s=s.replace('''                "first_seen_at": p.get("first_seen_at"),
                "time_basis": "SOURCE_PUBLISHED",''','''                "first_seen_at": p.get("first_seen_at"),
                "observed_lag_days": lag_days(p.get("first_seen_at"),
                                              p.get("first_index_date") or p.get("first_publication_date")),
                "time_basis": "SOURCE_PUBLISHED",''')
p.write_text(s,encoding="utf-8")
q=pathlib.Path("code/s029_08_quality_metrics.py"); t=q.read_text(encoding="utf-8")
t=t.replace('''    lenient = [c for c in claims if c.get("time_basis") == "ACTUAL_OBSERVATION"]''',
'''    # lenient definition, computed from the clocks rather than from a label, so a hard-coded
    # family label cannot hide a near-real-time fetch (the temporal auditor found 16 such claims)
    lenient = [c for c in claims
               if isinstance(c.get("observed_lag_days"), int)
               and 0 <= c["observed_lag_days"] <= 7]
    lenient_records = {c["source_record_id"] for c in lenient}
    lenient_le1 = [c for c in lenient if c["observed_lag_days"] <= 1]''')
t=t.replace('''        "actual_observation_claims_lenient_this_study": len(lenient),''',
'''        "actual_observation_claims_lenient_this_study": len(lenient),
        "lenient_distinct_source_records": len(lenient_records),
        "lenient_lag_le_1_day": len(lenient_le1),
        "lenient_breakdown": dict(Counter(c["predicate"] for c in lenient)),''')
t=t.replace('''            "lenient_near_realtime_claims_this_study": len(lenient),''',
'''            "lenient_near_realtime_claims_this_study": len(lenient),
            "lenient_distinct_source_records": len(lenient_records),
            "lenient_lag_le_1_day": len(lenient_le1),''')
q.write_text(t,encoding="utf-8")
import ast; ast.parse(s); ast.parse(t); print("patched lag field + lenient definition")
