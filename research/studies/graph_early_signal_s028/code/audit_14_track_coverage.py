"""S-028 audit 14: Q-E - technology-track mapping coverage and churn."""
from __future__ import annotations

import json
import re
from collections import Counter, defaultdict

from audit_common import RESEARCH, CFG, ro, now_iso, dump, pct

PCT_PATH = CFG + r"\product_code_tracks.json"
TD_PATH = CFG + r"\tracks_device.json"


def main():
    out = {"generated_at": now_iso()}
    c = ro(RESEARCH)
    pct_map = json.load(open(PCT_PATH, encoding="utf-8"))
    td = json.load(open(TD_PATH, encoding="utf-8"))
    kw = {t["id"]: [k.upper() for k in (t.get("keywords") or []) + (t.get("frontier_keywords") or [])]
          for t in td["tracks"]}

    out["mapping_artifacts"] = {
        "config/product_code_tracks.json": {
            "entries": len(pct_map), "shape": "dict product_code -> track_id (no dates, no confidence)",
            "sample": dict(list(pct_map.items())[:5]),
        },
        "config/tracks_device.json": {
            "tracks": len(td["tracks"]), "product_codes_embedded": len(td["product_codes"]),
            "keyword_lists": {k: len(v) for k, v in list(kw.items())[:6]},
            "note": td.get("notes"),
        },
        "research.sqlite.product_codes": {
            "rows": c.execute("select count(*) from product_codes").fetchone()[0],
            "meaning": "the frozen input ships an EMPTY product_codes table: code->track is not reproducible in-database",
        },
    }
    print("=" * 100)
    print("Q-E  mapping artifacts:", json.dumps(out["mapping_artifacts"], ensure_ascii=False)[:600])

    # ------------------------------------------------ event-level classification
    cls = Counter()
    cls_codes = defaultdict(set)
    for pc, tr, n in c.execute("select product_code, track_id, count(*) from events group by 1,2"):
        exp = pct_map.get(pc)
        if not tr:
            k = "track_null"
        elif exp is None:
            k = "track_set_but_code_absent_from_config"
        elif exp == tr:
            k = "config_code_to_track_agrees"
        else:
            k = "config_disagrees"
        cls[k] += n
        cls_codes[k].add(pc)
    out["event_track_classification"] = {
        k: {"events": v, "pct": pct(v, 55090), "distinct_codes": len(cls_codes[k])}
        for k, v in cls.items()}
    print("\n  event-level track classification:", json.dumps(out["event_track_classification"], ensure_ascii=False))

    # ----------------------------------- keyword fallback test for the odd bucket
    odd = [pc for pc in cls_codes["track_set_but_code_absent_from_config"]]
    rows = c.execute("""select product_code, track_id, payload from events
                        where track_id is not null and track_id<>''""").fetchall()
    hits = 0
    total = 0
    examples = []
    for pc, tr, payload in rows:
        if pct_map.get(pc) is not None:
            continue
        total += 1
        try:
            d = json.loads(payload)
        except Exception:  # noqa: BLE001
            continue
        text = " ".join(str(d.get(k) or "") for k in ("device_name", "generic_name", "trade_name")).upper()
        kws = kw.get(tr, [])
        ok = any(w in text for w in kws if len(w) > 3)
        if ok:
            hits += 1
        elif len(examples) < 8:
            examples.append({"product_code": pc, "track_id": tr, "device_name": (d.get("device_name") or d.get("generic_name") or "")[:90]})
    out["keyword_fallback"] = {
        "events_without_code_in_config_map": total,
        "events_whose_device_text_contains_an_assigned_track_keyword": hits,
        "events_not_explained_by_keywords": total - hits,
        "keyword_hit_pct": pct(hits, total),
        "counter_examples": examples,
        "interpretation": ("the residual track assignments cannot be reproduced from either shipped "
                           "mapping artifact; they look like a keyword/curation fallback whose rule "
                           "and version are not recorded in the frozen input"),
    }
    print("\n  keyword fallback test:", json.dumps(out["keyword_fallback"], ensure_ascii=False)[:900])

    # ------------------------------------------------------------- churn / late codes
    codes = defaultdict(lambda: {"n": 0, "first": None, "last": None, "tracks": set()})
    for pc, ed, tr in c.execute("select product_code, event_date, track_id from events where product_code<>''"):
        d = codes[pc]
        d["n"] += 1
        d["first"] = ed if d["first"] is None else min(d["first"], ed)
        d["last"] = ed if d["last"] is None else max(d["last"], ed)
        if tr:
            d["tracks"].add(tr)
    out["product_codes"] = {
        "distinct_codes_in_events": len(codes),
        "codes_in_config_map": len(pct_map),
        "codes_used_and_mapped": sum(1 for pc in codes if pc in pct_map),
        "codes_used_not_mapped": sum(1 for pc in codes if pc not in pct_map),
        "codes_used_not_mapped_pct": pct(sum(1 for pc in codes if pc not in pct_map), len(codes)),
    }
    late = {"2020+": "2020", "2022+": "2022", "2024+": "2024"}
    churn = {}
    for label, y in late.items():
        sel = {pc: d for pc, d in codes.items() if d["first"] >= y}
        churn[label] = {"codes": len(sel), "events": sum(d["n"] for d in sel.values()),
                        "pct_events": pct(sum(d["n"] for d in sel.values()), 55090)}
    out["late_appearing_codes"] = churn
    gone = {pc: d for pc, d in codes.items() if d["last"] < "2020-01-01"}
    out["codes_last_seen_before_2020"] = {"codes": len(gone), "events": sum(d["n"] for d in gone.values())}
    top_late = sorted([{"product_code": pc, "first": d["first"], "n": d["n"],
                        "track": sorted(d["tracks"])[:1]} for pc, d in codes.items()
                       if d["first"] >= "2022"], key=lambda x: -x["n"])[:12]
    out["top_late_codes"] = top_late
    print("\n  product-code churn:", json.dumps({k: out[k] for k in
          ("product_codes", "late_appearing_codes", "codes_last_seen_before_2020")}, ensure_ascii=False))

    # -------------------------------------------------------------- per-year nulls
    per_year = []
    for y, n, tnull, cn, cn2 in c.execute("""select substr(event_date,1,4) y, count(*),
            sum(track_id is null or track_id=''), sum(company_key is null or company_key=''),
            sum(company_key is null or company_key='' or track_id is null or track_id='')
            from events group by 1 order by 1"""):
        per_year.append({"year": y, "events": n, "track_id_null": tnull,
                         "track_id_null_pct": pct(tnull, n),
                         "company_key_null": cn, "company_key_null_pct": pct(cn, n),
                         "company_or_track_missing": cn2,
                         "company_or_track_missing_pct": pct(cn2, n)})
    out["per_year_missingness"] = per_year
    print("\n  per-year missingness:")
    for r in per_year:
        print("   ", r)

    # ----------------------------------------------------------- track structure
    track_counts = c.execute("""select track_id, count(*), count(distinct company_key),
                                min(event_date), max(event_date)
                                from events where track_id<>'' group by 1 order by 2 desc""").fetchall()
    out["tracks"] = {"n_tracks_in_table": c.execute("select count(*) from tracks").fetchone()[0],
                     "n_tracks_used": len(track_counts),
                     "tracks_unused": c.execute("""select count(*) from tracks where id not in
                          (select distinct track_id from events where track_id<>'')""").fetchone()[0],
                     "usage": [{"track_id": t, "events": n, "companies": nc,
                                "first": f, "last": l} for t, n, nc, f, l in track_counts]}
    print("\n  tracks used:", out["tracks"]["n_tracks_used"], "/", out["tracks"]["n_tracks_in_table"],
          " unused:", out["tracks"]["tracks_unused"])

    # ------------------------------------ taxonomy is a 2026 snapshot (anachronism)
    out["taxonomy_vintage"] = {
        "tracks_table_updated_at": c.execute("select max(updated_at) from tracks").fetchone()[0],
        "config_product_code_tracks_updated": None,
        "note": ("code->track is a single undated mapping shipped with the 2026 product; assigning "
                 "2016-2021 filings to today's 38-track taxonomy is an anachronism the study must "
                 "declare, although it does not leak future event values"),
    }
    c.close()
    dump("14_track_coverage", out)


if __name__ == "__main__":
    main()
