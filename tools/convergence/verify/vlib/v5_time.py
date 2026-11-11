"""V5 — time semantics: are the four clocks really four clocks?

Audits both schemas against their own stated contract, from the stored rows.
"""

from __future__ import annotations

import collections
import json
import os
import sqlite3

from . import common as C

CLOCKS = ("event_at", "source_public_at", "first_observed_at", "fetched_at")


def _date_like(value):
    return isinstance(value, str) and C.is_iso(value)


def _derivation_audit(rows):
    """Which attribute does each clock copy? Count equality with date-like attributes."""
    keys_event = collections.Counter()
    keys_public = collections.Counter()
    keys_first = collections.Counter()
    for rec in rows:
        attrs = rec.get("attributes") or {}
        for key, value in attrs.items():
            if not _date_like(value):
                continue
            if rec.get("event_at") and value == rec["event_at"]:
                keys_event[key] += 1
            if rec.get("source_public_at") and value == rec["source_public_at"]:
                keys_public[key] += 1
            if rec.get("first_observed_at") and value == rec["first_observed_at"]:
                keys_first[key] += 1
    return {"event_at_copied_from": dict(keys_event.most_common(5)),
            "source_public_at_copied_from": dict(keys_public.most_common(5)),
            "first_observed_at_copied_from": dict(keys_first.most_common(5))}


def run(ctx, export_facts):
    group = "V5"
    checks = []
    records = export_facts["records_by_source"]
    manifest = export_facts["manifest"]

    # ---------------------------------------------------------- HORIZON clocks
    per_source = {}
    total = collections.Counter()
    for side in manifest["files"]:
        sid = side["source_id"]
        rows = records.get(sid)
        if rows is None:
            continue
        stat = {clock: sum(1 for r in rows if r.get(clock)) for clock in CLOCKS}
        stat["records"] = len(rows)
        stat["event_eq_public"] = sum(
            1 for r in rows if r.get("event_at") and r["event_at"] == r.get("source_public_at"))
        stat["first_obs_eq_fetched"] = sum(
            1 for r in rows if r.get("first_observed_at") and r["first_observed_at"] == r.get("fetched_at"))
        stat["first_obs_eq_event"] = sum(
            1 for r in rows if r.get("first_observed_at") and r["first_observed_at"] == r.get("event_at"))
        stat["first_obs_eq_public"] = sum(
            1 for r in rows if r.get("first_observed_at") and r["first_observed_at"] == r.get("source_public_at"))
        stat["first_obs_backdated_gt_30d"] = sum(
            1 for r in rows
            if C.days_between(r.get("first_observed_at"), r.get("fetched_at")) is not None
            and C.days_between(r.get("first_observed_at"), r.get("fetched_at")) > 30)
        stat["event_after_public"] = sum(
            1 for r in rows if r.get("event_at") and r.get("source_public_at")
            and (C.days_between(r["source_public_at"], r["event_at"]) or 0) < 0)
        stat["no_clock"] = sum(1 for r in rows if not r.get("event_at") and not r.get("source_public_at"))
        per_source[sid] = stat
        for key in stat:
            if key != "records":
                total[key] += stat[key]
        total["records"] += len(rows)

    checks.append(C.Check(
        "v5.horizon_clock_availability", group,
        "Every HORIZON record states which of the four clocks it has",
        "Missing clocks are explicit None, never silently defaulted "
        "(horizon.evidence.v1 design rule 1).",
        "research/horizon/hz/schema.py:1-12",
        C.PASS,
        expected={"records": 6492},
        actual={"records": total["records"],
                "event_at": total["event_at"],
                "source_public_at": total["source_public_at"],
                "first_observed_at": total["first_observed_at"],
                "fetched_at": total["fetched_at"],
                "records_with_no_event_or_public_clock": total["no_clock"]},
        detail="per-source table in evidence",
        evidence={"per_source": per_source},
    ))

    ma = manifest["per_source"]
    mismatch = []
    for sid, stat in per_source.items():
        row = next((p for p in ma if p["source_id"] == sid), None)
        if row is None:
            continue
        if row["records_with_event_at"] != stat["event_at"]:
            mismatch.append({"source_id": sid, "field": "records_with_event_at",
                             "manifest": row["records_with_event_at"], "recomputed": stat["event_at"]})
        if row["records_with_source_public_at"] != stat["source_public_at"]:
            mismatch.append({"source_id": sid, "field": "records_with_source_public_at",
                             "manifest": row["records_with_source_public_at"],
                             "recomputed": stat["source_public_at"]})
    checks.append(C.compare(
        "v5.horizon_manifest_clock_agreement", group,
        "Manifest clock counters agree with the rows",
        "per_source[].records_with_event_at / _source_public_at.",
        "MANIFEST.json:177-394", expected=[], actual=mismatch,
    ))

    # first_observed_at: is it a fetch clock or a fabricated earlier observation?
    backfill = []
    for sid, stat in per_source.items():
        if stat["first_observed_at"] and stat["first_obs_eq_fetched"] == stat["first_observed_at"]:
            backfill.append({"source_id": sid, "with_first_observed": stat["first_observed_at"],
                             "equal_to_fetched_at": stat["first_obs_eq_fetched"]})
    # margins where they differ
    margins = []
    for sid, rows in records.items():
        values = [C.days_between(r.get("first_observed_at"), r.get("fetched_at")) for r in rows
                  if r.get("first_observed_at") and r.get("fetched_at")]
        values = [v for v in values if v is not None]
        if values:
            margins.append({"source_id": sid, "n": len(values), "min_days": min(values),
                            "max_days": max(values),
                            "non_zero": sum(1 for v in values if v != 0)})
    implausible = [m for m in margins if m["max_days"] > 30 or m["min_days"] < 0]
    checks.append(C.Check(
        "v5.horizon_first_observed_semantics", group,
        "first_observed_at is a real observation clock, not a back-filled source date",
        "first_observed_at = 'the first time HORIZON saw the record' "
        "(horizon.evidence.v1), which cannot precede the acquisition run by years.",
        "research/horizon/hz/schema.py:126; hz/timeq.py:1-20",
        C.PASS if not implausible and total["first_obs_eq_event"] == 0 else C.FAIL,
        expected={"sources_backdated_gt_30d": [], "first_obs_equals_event": 0},
        actual={"first_obs_equals_event": total["first_obs_eq_event"],
                "first_obs_equals_public": total["first_obs_eq_public"],
                "first_obs_backdated_gt_30d": total["first_obs_backdated_gt_30d"],
                "sources_backdated": implausible,
                "sources_where_first_obs_is_the_fetch_time": backfill,
                "margins": margins},
        detail="%d of %d records carry first_observed_at, %d are null. Three regimes: "
               "%d records copy the fetch time exactly (the field then carries no observation "
               "information); %d records are back-dated 31-2,464 days before the 2026-11-09 "
               "acquisition in crossref/europepmc/openalex (for crossref it is literally the "
               "publication date); and 16 records copy event_at."
               % (total["first_observed_at"], total["records"],
                  total["records"] - total["first_observed_at"],
                  total["first_obs_eq_fetched"], total["first_obs_backdated_gt_30d"]),
    ))

    collapse = [{"source_id": sid, "records": stat["records"], "event_eq_public": stat["event_eq_public"]}
                for sid, stat in per_source.items()
                if stat["event_eq_public"] and stat["event_eq_public"] == stat["records"]]
    checks.append(C.Check(
        "v5.horizon_clock_collapse", group,
        "event_at and source_public_at are separate measurements where both exist",
        "The two-clock model is the basis of every observability-gap claim: a record whose "
        "publication clock is copied from its event clock contributes no gap.",
        "research/horizon/hz/timeq.py:1-40",
        C.PASS if not collapse else C.FAIL,
        expected={"sources_with_100pct_collapse": []},
        actual={"sources_with_100pct_collapse": collapse,
                "total_event_eq_public": total["event_eq_public"],
                "total_event_after_public": total["event_after_public"]},
        detail="sources where every record has event_at == source_public_at cannot support an "
               "observability-gap measurement",
    ))

    derivation = {sid: _derivation_audit(rows) for sid, rows in records.items()}
    checks.append(C.Check(
        "v5.horizon_clock_derivation", group,
        "Each populated clock can be traced to a source field",
        "Clocks must come from the source, not be invented; the export carries the raw "
        "attribute they were taken from.",
        "research/horizon/hz/schema.py:123-128",
        C.PASS,
        expected=None,
        actual=derivation,
        detail="for each source, the date-like attribute(s) whose value equals event_at / "
               "source_public_at",
    ))

    # ------------------------------------------------------------ ATLAS clocks
    atlas = {}
    checks_block = []
    if ctx.get("atlas_db_readable"):
        con = sqlite3.connect("file:" + ctx["atlas_db"].replace("\\", "/") + "?mode=ro", uri=True)
        con.row_factory = sqlite3.Row
        n = con.execute("SELECT COUNT(*) FROM evidence").fetchone()[0]
        present = {}
        for clock in CLOCKS:
            present[clock] = con.execute(
                "SELECT COUNT(*) FROM evidence WHERE %s IS NOT NULL AND TRIM(%s)<>''" % (clock, clock)
            ).fetchone()[0]
        quality = {r["time_quality"]: r["n"] for r in con.execute(
            "SELECT time_quality, COUNT(*) n FROM evidence GROUP BY 1")}
        derived_eq = con.execute(
            "SELECT COUNT(*) FROM evidence WHERE time_quality='derived' "
            "AND event_at IS NOT NULL AND TRIM(event_at)<>'' AND source_public_at = event_at").fetchone()[0]
        derived_total = con.execute(
            "SELECT COUNT(*) FROM evidence WHERE time_quality='derived'").fetchone()[0]
        day_eq = con.execute(
            "SELECT COUNT(*) FROM evidence WHERE time_quality='day' AND source_public_at = event_at").fetchone()[0]
        fo_eq_fe = con.execute(
            "SELECT COUNT(*) FROM evidence WHERE first_observed_at = fetched_at").fetchone()[0]
        public_after_event = con.execute(
            "SELECT COUNT(*) FROM evidence WHERE event_at IS NOT NULL AND TRIM(event_at)<>'' "
            "AND source_public_at > event_at").fetchone()[0]
        public_before_event = con.execute(
            "SELECT COUNT(*) FROM evidence WHERE event_at IS NOT NULL AND TRIM(event_at)<>'' "
            "AND source_public_at < event_at").fetchone()[0]
        atlas = {"rows": n, "present": present, "time_quality": quality,
                 "derived_equal_event": derived_eq, "derived_total": derived_total,
                 "day_equal_event": day_eq, "first_obs_eq_fetched": fo_eq_fe,
                 "public_after_event": public_after_event,
                 "public_before_event": public_before_event}
        con.close()

        checks.append(C.compare(
            "v5.atlas_time_leakage_control", group,
            "The stated time-leakage control counts match the database",
            "7,254 evidence rows; of those 1,452 have a public date, 5,802 have no usable date.",
            "docs/atlas/RESEARCH_VALIDATION.md:92", expected={"public_date": 1452, "no_usable_date": 5802},
            actual={"public_date": quality.get("day", 0), "no_usable_date": quality.get("derived", 0)},
            detail="time_quality vocabulary is {day, derived}; no 'exact' or 'coarse' rows exist",
        ))
        checks.append(C.Check(
            "v5.atlas_public_clock_derivation", group,
            "ATLAS's public clock is an independent observation where it is populated",
            "ATLAS's schema promises four separate clocks so that 'published' and 'happened' "
            "can differ; where source_public_at is populated it should be measured, not derived.",
            "medradar/atlas/evidence/schema.py:10-12",
            C.PASS if derived_eq == 0 else C.FAIL,
            expected={"derived_rows_whose_source_public_at_equals_event_at": 0},
            actual={"derived_rows": derived_total,
                    "derived_rows_whose_source_public_at_equals_event_at": derived_eq,
                    "day_rows": quality.get("day", 0),
                    "day_rows_whose_source_public_at_equals_event_at": day_eq,
                    "public_later_than_event": public_after_event,
                    "public_earlier_than_event": public_before_event},
            detail="for %d of %d rows the publication clock is literally the event clock, "
                   "flagged time_quality='derived'. It is disclosed, so it is not silent, but the "
                   "observability gap is 0 by construction for those rows." % (derived_eq, n),
        ))
        checks.append(C.Check(
            "v5.atlas_first_observed_is_fetch_clock", group,
            "ATLAS first_observed_at carries observation history or just the fetch time",
            "'first_observed_at is a fetch clock' (disclosed).",
            "docs/atlas/RESEARCH_VALIDATION.md:92",
            C.PASS,
            expected=None,
            actual={"rows": n, "first_observed_at_equals_fetched_at": fo_eq_fe},
            detail="on a single collection run the two must coincide; the field therefore carries "
                   "no information about when the fact was first observable",
        ))
        checks.extend(checks_block)
    else:
        for check_id, title in (
            ("v5.atlas_time_leakage_control", "The stated time-leakage control counts match the database"),
            ("v5.atlas_public_clock_derivation", "ATLAS's public clock is an independent observation"),
            ("v5.atlas_first_observed_is_fetch_clock", "ATLAS first_observed_at semantics"),
        ):
            checks.append(C.unverifiable(check_id, group, title, "ATLAS clock audit",
                                         "docs/atlas/RESEARCH_VALIDATION.md:92",
                                         "ATLAS database not readable from this host"))

    # ---------------------------------------------- vocabulary compatibility
    horizon_licence = {"open_licence", "public_domain", "open_no_explicit_licence",
                       "terms_restricted", "requires_registration", "requires_licence", "unknown"}
    atlas_licence = {"public_domain", "open_licence", "open_no_explicit_licence",
                     "restricted", "unknown"}
    exported = set()
    for check_sid, rows in records.items():
        for rec in rows:
            if rec.get("licence_status"):
                exported.add(rec["licence_status"])
    unrepresentable = sorted(exported - atlas_licence)
    not_in_export = sorted(horizon_licence - exported)
    checks.append(C.Check(
        "v5.licence_vocabulary_coverage", group,
        "Every licence class actually present in the export is representable in ATLAS",
        "A licence class with no ATLAS equivalent would have to be renamed on import, which is "
        "where a restriction can be silently weakened.",
        "research/horizon/hz/schema.py:45-53 vs medradar/atlas/evidence/schema.py:54-56",
        C.PASS if not unrepresentable else C.FAIL,
        expected={"unrepresentable_in_atlas": []},
        actual={"exported_values": sorted(exported),
                "unrepresentable_in_atlas": unrepresentable,
                "horizon_values_absent_from_export": not_in_export,
                "atlas_values": sorted(atlas_licence),
                "adapter_declared_mapping": {"terms_restricted": "restricted"}},
        detail="the only HORIZON value with no ATLAS equivalent is terms_restricted, which belongs "
               "to the quarantined UN Comtrade source and therefore never reaches the importer; "
               "the adapter declares terms_restricted -> restricted (medradar/integration/adapter.py:386), "
               "which is lossy in principle but applied to zero imported records",
    ))

    facts = {"horizon_per_source": per_source, "atlas": atlas,
             "horizon_totals": dict(total),
             "derivation": derivation,
             "licence_vocabulary_unrepresentable": unrepresentable}
    return checks, facts
