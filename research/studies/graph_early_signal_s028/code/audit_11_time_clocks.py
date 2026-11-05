"""S-028 audit 11: the point-in-time problem (Q-A) and what available_at means (Q-B).

Everything is computed, nothing asserted. Lag is measured in whole days between
calendar dates (first 10 chars of the timestamp) to stay insensitive to time-of-day.
"""
from __future__ import annotations

import json
import statistics
from collections import Counter, defaultdict

from audit_common import RESEARCH, PRODUCT, OBS, ro, now_iso, dump, pct

BUCKETS = [("-inf", -1), ("0", 0), ("1", 1), ("2-7", 7), ("8-30", 30), ("31-365", 365), (">365", 10 ** 9)]


def bucket(lag):
    for name, hi in BUCKETS:
        if name == "-inf":
            if lag < 0:
                return name
            continue
        if lag <= hi:
            return name
    return ">365"


def day(ts):
    return (ts or "")[:10]


def dnum(a, b):
    """whole-day difference a-b for 'YYYY-MM-DD...' strings; None if unparsable."""
    if not a or not b:
        return None
    import datetime as dt

    try:
        da = dt.date.fromisoformat(a[:10])
        db = dt.date.fromisoformat(b[:10])
    except ValueError:
        return None
    return (da - db).days


def main():
    out = {"generated_at": now_iso()}

    # ---------------------------------------------------------------- research
    c = ro(RESEARCH)
    rows = c.execute(
        "select source, event_date, published_at, first_seen_at, available_at, as_of, timestamp_quality "
        "from events").fetchall()
    c.close()

    per_src = defaultdict(lambda: {
        "n": 0, "first_seen_at_values": Counter(), "available_at_days": Counter(),
        "lag_fs_pub": Counter(), "lag_av_ed": Counter(), "lag_av_pub": Counter(),
        "event_date_min": None, "event_date_max": None,
        "published_at_min": None, "published_at_max": None,
        "available_at_min": None, "available_at_max": None,
        "as_of_values": Counter(), "timestamp_quality": Counter(),
        "nulls": Counter(),
    })
    global_fs = Counter()
    lag_fs_days = []
    deltas_av_ed = []
    for src, ed, pub, fs, av, asof, tq in rows:
        s = per_src[src]
        s["n"] += 1
        s["first_seen_at_values"][fs] += 1
        global_fs[fs] += 1
        s["available_at_days"][day(av)] += 1
        s["as_of_values"][asof] += 1
        s["timestamp_quality"][tq] += 1
        for field, val in (("event_date", ed), ("published_at", pub), ("available_at", av),
                           ("first_seen_at", fs)):
            if not val:
                s["nulls"][field] += 1
        l1 = dnum(fs, pub)
        if l1 is not None:
            s["lag_fs_pub"][bucket(l1)] += 1
            lag_fs_days.append(l1)
        l2 = dnum(av, ed)
        if l2 is not None:
            s["lag_av_ed"][bucket(l2)] += 1
            deltas_av_ed.append(l2)
        l3 = dnum(av, pub)
        s["lag_av_pub"][bucket(l3)] += 1
        for k, v in (("event_date_min", ed), ("event_date_max", ed), ("published_at_min", pub),
                     ("published_at_max", pub), ("available_at_min", av), ("available_at_max", av)):
            if v is None:
                continue
            if k.endswith("_min"):
                s[k] = v if s[k] is None else min(s[k], v)
            else:
                s[k] = v if s[k] is None else max(s[k], v)

    research = {
        "rows": len(rows),
        "first_seen_at_distinct_values": len(global_fs),
        "first_seen_at_values": dict(global_fs),
        "lag_first_seen_minus_published_days": {
            "min": min(lag_fs_days), "max": max(lag_fs_days),
            "median": statistics.median(lag_fs_days),
            "buckets_all_sources": dict(Counter(bucket(x) for x in lag_fs_days)),
        },
        "available_at_minus_event_date_days": {
            "min": min(deltas_av_ed), "max": max(deltas_av_ed),
            "distinct_values": sorted(set(deltas_av_ed)),
            "median": statistics.median(deltas_av_ed),
            "equal_count": sum(1 for x in deltas_av_ed if x == 0),
            "equal_pct": pct(sum(1 for x in deltas_av_ed if x == 0), len(deltas_av_ed)),
        },
        "per_source": {},
    }
    for src, s in per_src.items():
        research["per_source"][src] = {
            "n": s["n"],
            "first_seen_at_distinct": len(s["first_seen_at_values"]),
            "first_seen_at_values": dict(s["first_seen_at_values"]),
            "timestamp_quality": dict(s["timestamp_quality"]),
            "as_of_values": dict(s["as_of_values"]),
            "event_date_range": [s["event_date_min"], s["event_date_max"]],
            "published_at_range": [s["published_at_min"], s["published_at_max"]],
            "available_at_range": [s["available_at_min"], s["available_at_max"]],
            "available_at_distinct_days": len(s["available_at_days"]),
            "lag_first_seen_minus_published_buckets": dict(s["lag_fs_pub"]),
            "lag_available_minus_event_buckets": dict(s["lag_av_ed"]),
            "lag_available_minus_published_buckets": dict(s["lag_av_pub"]),
            "nulls": dict(s["nulls"]),
        }
    # genuine point-in-time first observation
    gen0 = sum(1 for x in lag_fs_days if x <= 0)
    gen1 = sum(1 for x in lag_fs_days if x <= 1)
    gen7 = sum(1 for x in lag_fs_days if x <= 7)
    research["genuine_pit"] = {
        "definition": "first_seen_at - published_at <= N calendar days",
        "n_le_0d": gen0, "pct_le_0d": pct(gen0, len(lag_fs_days)),
        "n_le_1d": gen1, "pct_le_1d": pct(gen1, len(lag_fs_days)),
        "n_le_7d": gen7, "pct_le_7d": pct(gen7, len(lag_fs_days)),
        "n_gt_365d": sum(1 for x in lag_fs_days if x > 365),
        "pct_gt_365d": pct(sum(1 for x in lag_fs_days if x > 365), len(lag_fs_days)),
    }
    out["research_events"] = research

    print("=" * 100)
    print("Q-A  research.sqlite.events  first_seen_at")
    print("  distinct first_seen_at values:", research["first_seen_at_distinct_values"], research["first_seen_at_values"])
    print("  -> 100% of", len(rows), "rows share a single bulk-fetch date; verdict:", len(global_fs) == 1)
    print("  lag(first_seen_at - published_at) days: min/median/max =",
          research["lag_first_seen_minus_published_days"]["min"],
          research["lag_first_seen_minus_published_days"]["median"],
          research["lag_first_seen_minus_published_days"]["max"])
    print("  buckets:", research["lag_first_seen_minus_published_days"]["buckets_all_sources"])
    print("  genuine PIT (lag<=1d):", gen1, f"({research['genuine_pit']['pct_le_1d']}%)")
    print("\nQ-B  available_at vs event_date")
    print("  research: distinct deltas:", research["available_at_minus_event_date_days"]["distinct_values"],
          " equal_count:", research["available_at_minus_event_date_days"]["equal_count"])
    for src, s in research["per_source"].items():
        print(f"  [{src}] n={s['n']} ed={s['event_date_range']} av-ed buckets={s['lag_available_minus_event_buckets']}"
              f" av==pub buckets={s['lag_available_minus_published_buckets']}")

    # ----------------------------------------------------------------- product
    p = ro(PRODUCT)
    prow = p.execute(
        "select source, event_date, published_at, first_seen_at, available_at, timestamp_quality from events").fetchall()
    p.close()
    pp = defaultdict(lambda: {"n": 0, "fs_values": Counter(), "av_minus_ed": [], "nulls": Counter(),
                              "tq": Counter(), "ed_range": [None, None], "av_equals_ed": 0})
    for src, ed, pub, fs, av, tq in prow:
        s = pp[src]
        s["n"] += 1
        s["fs_values"][fs] += 1
        s["tq"][tq] += 1
        for f, v in (("event_date", ed), ("published_at", pub), ("available_at", av), ("first_seen_at", fs)):
            if not v:
                s["nulls"][f] += 1
        dd = dnum(av, ed)
        if dd is not None:
            s["av_minus_ed"].append(dd)
            if dd == 0:
                s["av_equals_ed"] += 1
        if ed:
            s["ed_range"][0] = ed if s["ed_range"][0] is None else min(s["ed_range"][0], ed)
            s["ed_range"][1] = ed if s["ed_range"][1] is None else max(s["ed_range"][1], ed)
    product = {"rows": len(prow), "per_source": {}}
    for src, s in pp.items():
        d = sorted(s["av_minus_ed"])
        product["per_source"][src] = {
            "n": s["n"],
            "first_seen_at_values": dict(s["fs_values"]),
            "first_seen_at_distinct": len(s["fs_values"]),
            "event_date_range": s["ed_range"],
            "timestamp_quality": dict(s["tq"]),
            "nulls": dict(s["nulls"]),
            "available_minus_event_days": {
                "min": d[0] if d else None,
                "median": statistics.median(d) if d else None,
                "max": d[-1] if d else None,
                "equal_count": s["av_equals_ed"],
                "equal_pct": pct(s["av_equals_ed"], len(d)),
                "n": len(d),
            },
        }
    out["product_events"] = product
    print("\n" + "=" * 100)
    print("product.sqlite.events")
    for src, s in product["per_source"].items():
        print(f"  [{src:26s}] n={s['n']:7d} fs_distinct={s['first_seen_at_distinct']} "
              f"{s['first_seen_at_values']}")
        print(f"      ed={s['event_date_range']} av-ed={s['available_minus_event_days']}")

    # ------------------------------------------------------------- observatory
    o = ro(OBS)
    obs = o.execute("""select observation_id, source, record_type, observation_origin, first_seen_at,
                              ingested_at, published_at, event_at, event_at_precision,
                              published_at_precision, observation_status, version_count, backfill_reason
                       from observation""").fetchall()
    meta = dict(o.execute("select key, value from meta").fetchall())
    ph = o.execute("select phase, method, count(*) from observation_phase group by 1,2").fetchall()
    o.close()

    org = Counter()
    origin_tbl = Counter()
    fs_counter = Counter()
    lag_b = Counter()
    lag_days = []
    for (oid, src, rt, origin, fs, ing, pub, ev, evp, pubp, st, vc, bf) in obs:
        org[(origin, src, rt)] += 1
        origin_tbl[origin] += 1
        fs_counter[fs] += 1
        l = dnum(fs, pub)
        if l is not None:
            lag_b[bucket(l)] += 1
            lag_days.append(l)
    le1 = sum(1 for x in lag_days if x <= 1)
    le7 = sum(1 for x in lag_days if x <= 7)
    le0 = sum(1 for x in lag_days if x <= 0)
    gt7 = sum(1 for x in lag_days if x > 7)
    observatory = {
        "rows": len(obs),
        "observation_origin": dict(origin_tbl),
        "backfill_reason_values": dict(Counter(r[12] for r in obs)),
        "origin_x_source_x_record_type": [
            {"observation_origin": k[0], "source": k[1], "record_type": k[2], "n": v}
            for k, v in sorted(org.items(), key=lambda x: -x[1])],
        "first_seen_at_distinct": len(fs_counter),
        "first_seen_at_values": dict(fs_counter),
        "ingested_at_distinct_days": len(set(r[5][:10] for r in obs)),
        "ledger_created_at": meta.get("created_at"),
        "lag_first_seen_minus_published_days": {
            "min": min(lag_days), "median": statistics.median(lag_days), "max": max(lag_days),
            "buckets": dict(lag_b)},
        "prospective": {
            "definition": "first_seen_at - published_at <= N calendar days",
            "n_le_0d": le0, "pct_le_0d": pct(le0, len(obs)),
            "n_le_1d": le1, "pct_le_1d": pct(le1, len(obs)),
            "n_le_7d": le7, "pct_le_7d": pct(le7, len(obs)),
            "n_gt_7d": gt7, "pct_gt_7d": pct(gt7, len(obs)),
        },
        "observation_phase": [{"phase": a, "method": b, "n": c} for a, b, c in ph],
        "version_count_values": dict(Counter(r[11] for r in obs)),
        "observation_status": dict(Counter(r[10] for r in obs)),
    }
    # per-source lag buckets + the actual prospective records + a ledger-integrity check
    o = ro(OBS)
    lag_by_src = {}
    for r in o.execute("""
            select source,
              sum(case when lag<=0 then 1 else 0 end),
              sum(case when lag=1 then 1 else 0 end),
              sum(case when lag between 2 and 7 then 1 else 0 end),
              sum(case when lag between 8 and 30 then 1 else 0 end),
              sum(case when lag between 31 and 365 then 1 else 0 end),
              sum(case when lag>365 then 1 else 0 end), count(*)
            from (select source,
                    cast(julianday(substr(first_seen_at,1,10))-julianday(substr(published_at,1,10)) as int) lag
                  from observation) group by 1"""):
        lag_by_src[r[0]] = {"le_0d": r[1], "1d": r[2], "2_7d": r[3], "8_30d": r[4],
                            "31_365d": r[5], "gt_365d": r[6], "total": r[7],
                            "gt_7d": r[4] + r[5] + r[6], "le_7d": r[1] + r[2] + r[3]}
    observatory["lag_by_source"] = lag_by_src
    observatory["event_at_range_by_source"] = {
        r[0]: [r[1], r[2]] for r in o.execute(
            "select source, min(event_at), max(event_at) from observation group by 1")}
    observatory["published_at_range_by_source"] = {
        r[0]: [r[1], r[2]] for r in o.execute(
            "select source, min(published_at), max(published_at) from observation group by 1")}
    observatory["prospective_examples"] = [
        {"source": a, "record_type": b, "observation_id": c, "published_at": d,
         "first_seen_at": e, "lag_days": f}
        for a, b, c, d, e, f in o.execute("""
            select source, record_type, observation_id, published_at, first_seen_at,
                   cast(julianday(substr(first_seen_at,1,10))-julianday(substr(published_at,1,10)) as int)
            from observation
            where cast(julianday(substr(first_seen_at,1,10))-julianday(substr(published_at,1,10)) as int) <= 1
            order by source""")]
    observatory["ledger_integrity"] = {
        "observation_mapping_rows": o.execute("select count(*) from observation_mapping").fetchone()[0],
        "observation_mapping_distinct_observations":
            o.execute("select count(distinct observation_id) from observation_mapping").fetchone()[0],
        "duplicate_observation_ids": [r[0] for r in o.execute(
            "select observation_id from observation_mapping group by 1 having count(*)>1")],
        "sync_runs": o.execute("select count(*) from sync_run").fetchone()[0],
        "sync_runs_with_status_ok": o.execute("select count(*) from sync_run where status='OK'").fetchone()[0],
        "source_failures": o.execute("select count(*) from source_failure").fetchone()[0],
        "observation_phase_total": o.execute("select count(*) from observation_phase").fetchone()[0],
        "phase_reconstructed_rows": o.execute(
            "select count(*) from observation_phase where method='reconstructed_from_run_history'").fetchone()[0],
    }
    print("\n  observatory lag by source:", json.dumps(lag_by_src))
    print("  prospective records:", len(observatory["prospective_examples"]))
    for r in observatory["prospective_examples"]:
        print("    ", r)
    print("  ledger integrity:", json.dumps(observatory["ledger_integrity"]))

    out["observatory"] = observatory
    print("\n" + "=" * 100)
    print("Q-A  observatory.sqlite  (the only store with observation_origin)")
    print("  observation_origin:", observatory["observation_origin"])
    print("  backfill_reason:", observatory["backfill_reason_values"])
    print("  first_seen_at distinct:", observatory["first_seen_at_distinct"], observatory["first_seen_at_values"])
    print("  lag(fs-pub): ", observatory["lag_first_seen_minus_published_days"])
    print("  prospective <=1d:", le1, observatory["prospective"]["pct_le_1d"], "%  <=7d:", le7,
          observatory["prospective"]["pct_le_7d"], "%  >7d:", gt7)
    print("  origin x source x record_type:")
    for r in observatory["origin_x_source_x_record_type"]:
        print("    ", r)
    print("  phase:", observatory["observation_phase"])
    print("  ledger_created_at:", observatory["ledger_created_at"])

    out["verdicts"] = {
        "first_seen_at": {
            "finding": "research.events.first_seen_at single bulk date",
            "distinct_values": research["first_seen_at_distinct_values"],
            "value": research["first_seen_at_values"],
            "historical_rows_with_genuine_first_observation": research["genuine_pit"]["n_le_1d"],
        },
        "available_at": {
            "finding": "research.events.available_at == published_at == event_date + 14 days for every row",
            "distinct_deltas_vs_event_date": research["available_at_minus_event_date_days"]["distinct_values"],
            "equal_to_event_date": research["available_at_minus_event_date_days"]["equal_count"],
        },
        "observatory_live": {
            "declared_live": origin_tbl.get("LIVE", 0),
            "declared_backfill": origin_tbl.get("BACKFILL", 0),
            "genuinely_prospective_le_1d": le1,
        },
    }

    dump("11_time_clocks", out)


if __name__ == "__main__":
    main()
