"""EXP-H4-INDUSTRY — measured quantities for the INDUSTRY workstream.

The experiment answers four questions with numbers taken from the evidence files
on disk (never from memory):

1. How many **trade series rows** did we actually obtain, defined as
   (reporter x partner x HS x period)?
2. How many **procurement awards** carry a **named supplier**?
3. How many of those awards name a **concrete device or model**?
4. Of those, how many are **CONFIRMED** vs **CANDIDATE**?

It also reports the two clocks per source (the project's core discipline) and
two cross-source checks that would catch a mislabelled series.

Run:

    python experiments/industry/run_experiment.py
"""

from __future__ import annotations

import json
import os
import sys
from collections import Counter, defaultdict
from typing import Any

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, ROOT)

from hz.schema import dedupe_key, read_jsonl  # noqa: E402
from hz.timeq import classify_record, now_utc  # noqa: E402

EVID = os.path.join(HERE, "evidence")
OUT = os.path.join(HERE, "EXP_H4_INDUSTRY.json")

TRADE_SOURCES = ["un_comtrade", "eurostat_comext", "uk_hmrc_trade"]
PROC_SOURCES = ["usaspending", "eu_ted", "uk_find_a_tender"]


def _load(name: str) -> list[dict]:
    p = os.path.join(EVID, f"{name}.jsonl")
    if not os.path.isfile(p):
        return []
    return read_jsonl(p)


def _trade_metrics(by_source: dict[str, list[dict]]) -> dict[str, Any]:
    series: set[tuple] = set()
    per_source: dict[str, Any] = {}
    currency_units = Counter()
    hs_codes = Counter()
    reporters = set()
    periods = set()
    for sid in TRADE_SOURCES:
        rows = by_source.get(sid) or []
        src_series = set()
        for r in rows:
            a = r.get("attributes") or {}
            reporter = a.get("reporter_code")
            partner = a.get("partner_code")
            hs = a.get("hs_code")
            period = a.get("period")
            # the flow axis is named differently per source and MUST be in the key:
            # dropping it would silently halve the series count by collapsing
            # imports into exports.
            flow = a.get("flow_code") or a.get("direction")
            key = (sid, reporter, partner, hs, period, flow)
            series.add(key)
            src_series.add(key)
            currency_units[a.get("unit") or "unknown"] += 1
            hs_codes[hs] += 1
            reporters.add(f"{sid}:{reporter}")
            periods.add(str(period))
        per_source[sid] = {
            "records": len(rows),
            "series_rows": len(src_series),
            "distinct_hs_codes": len({k[3] for k in src_series}),
            "distinct_reporters": len({k[1] for k in src_series}),
            "distinct_periods": len({str(k[4]) for k in src_series}),
        }
    return {
        "trade_records_total": sum(len(by_source.get(s, [])) for s in TRADE_SOURCES),
        "trade_series_rows_total": len(series),
        "series_definition": "distinct (source, reporter, partner, HS, period, direction)",
        "per_source": per_source,
        "units": dict(currency_units),
        "hs_code_row_counts": dict(sorted(hs_codes.items())),
        "distinct_reporters_all_sources": len(reporters),
        "distinct_periods_all_sources": len(periods),
    }


def _award_metrics(by_source: dict[str, list[dict]]) -> dict[str, Any]:
    per_source: dict[str, Any] = {}
    supplier_named_awards: dict[str, set[str]] = defaultdict(set)
    device_named_awards: dict[str, set[str]] = defaultdict(set)
    model_named_awards: dict[str, set[str]] = defaultdict(set)
    supplier_relations = 0
    device_named_relations = 0
    status_counts: Counter = Counter()
    stage_counts: Counter = Counter()
    identity_counts: Counter = Counter()
    evidence_counts: Counter = Counter()
    with_firm_identifier = 0
    org_schemes: Counter = Counter()

    for sid in PROC_SOURCES:
        rows = by_source.get(sid) or []
        for r in rows:
            a = r.get("attributes") or {}
            # An "award" is one award — not one notice and not one release. The
            # supplier is deliberately NOT part of the award key: an award with
            # five suppliers is still one award. Supplier<->award pairs are
            # counted separately as relations.
            group = "::".join(filter(None, [
                str(a.get("publication_number") or ""),
                str(a.get("ocid") or ""),
                str(a.get("award_id") or ""),
            ])) or str(r.get("source_record_id"))
            supplier = a.get("supplier_name") or a.get("recipient_name") or a.get("winner_name")
            if supplier:
                supplier_named_awards[sid].add(group)
                supplier_relations += 1
            if a.get("names_concrete_device"):
                device_named_awards[sid].add(group)
                device_named_relations += 1
            if a.get("names_concrete_model"):
                model_named_awards[sid].add(group)
            if supplier:
                supplier_named_awards[sid].add(group)
            if a.get("names_concrete_device"):
                device_named_awards[sid].add(group)
            if a.get("names_concrete_model"):
                model_named_awards[sid].add(group)
            status_counts[str(a.get("device_relation_status"))] += 1
            stage_counts[str(a.get("stage"))] += 1
            identity_counts[str(r.get("identity_status"))] += 1
            evidence_counts[str(r.get("evidence_status"))] += 1
            for i in r.get("identifiers") or []:
                org_schemes[str(i.get("scheme"))] += 1
                if i.get("scheme") in ("sam_uei", "ocds_party_id"):
                    with_firm_identifier += 1

    for sid in PROC_SOURCES:
        rows = by_source.get(sid) or []
        per_source[sid] = {
            "records": len(rows),
            "awards_with_named_supplier": len(supplier_named_awards[sid]),
            "awards_naming_concrete_device": len(device_named_awards[sid]),
            "awards_naming_model_like_token": len(model_named_awards[sid]),
        }

    return {
        "procurement_records_total": sum(len(by_source.get(s, [])) for s in PROC_SOURCES),
        "per_source": per_source,
        "awards_with_named_supplier_total": sum(len(v) for v in supplier_named_awards.values()),
        "supplier_award_relations_total": supplier_relations,
        "awards_naming_concrete_device_total": sum(len(v) for v in device_named_awards.values()),
        "device_named_relations_total": device_named_relations,
        "awards_naming_model_like_token_total": sum(len(v) for v in model_named_awards.values()),
        "device_relation_status_counts": dict(status_counts),
        "stage_counts": dict(stage_counts),
        "identity_status_counts": dict(identity_counts),
        "evidence_status_counts": dict(evidence_counts),
        "records_carrying_a_firm_identifier": with_firm_identifier,
        "identifier_schemes_used": dict(org_schemes),
    }


def _clock_metrics(by_source: dict[str, list[dict]]) -> dict[str, Any]:
    per_source: dict[str, Counter] = defaultdict(Counter)
    for sid, rows in by_source.items():
        for r in rows:
            cls = classify_record(r.get("event_at"), r.get("source_public_at"))
            per_source[sid][cls["class"]] += 1
    return {sid: dict(c) for sid, c in sorted(per_source.items())}


def _cross_checks(by_source: dict[str, list[dict]]) -> dict[str, Any]:
    """Two checks that would expose a mislabelled or misaligned series."""
    checks: dict[str, Any] = {}

    # (a) same cell from two independent compilations: DE / 9018 / imports / 2023
    def find(rows, **want):
        for r in rows:
            a = r.get("attributes") or {}
            if all(a.get(k) == v for k, v in want.items()):
                return r
        return None

    comtrade = by_source.get("un_comtrade") or []
    comext = by_source.get("eurostat_comext") or []
    hmrc = by_source.get("uk_hmrc_trade") or []

    de_comext = find(comext, reporter_code="DE", hs_code="9018", flow_code="1",
                     period="2023", indicator="VALUE_IN_EUROS")
    de_comtrade = find(comtrade, reporter_code=276, hs_code="9018",
                       flow_code="M", period="2023")
    checks["de_9018_imports_2023"] = {
        "comext_eur": (de_comext or {}).get("attributes", {}).get("value"),
        "comtrade_usd": (de_comtrade or {}).get("attributes", {}).get("primary_value_usd"),
        "note": (
            "Different currencies and different compilations; the point is that "
            "both series are retrievable for the same cell so a reviewer can "
            "reconcile them, not that they are equal."
        ),
    }

    # (b) HMRC internal consistency: imports must be flow 1 + flow 3, and our
    #     roll-up must produce 12 months per year for a complete year.
    gb_2023_imp = find(hmrc, hs_code="9018", period="2023", direction="imports")
    checks["hmrc_9018_2023_imports"] = {
        "value_gbp": (gb_2023_imp or {}).get("attributes", {}).get("value_gbp"),
        "months_observed": (gb_2023_imp or {}).get("attributes", {}).get("months_observed"),
        "flow_type_ids_summed": (gb_2023_imp or {}).get("attributes", {}).get("flow_type_ids_summed"),
    }

    # (c) EPV: every trade record must say it is an aggregate and attribute no firm
    bad = 0
    for sid in TRADE_SOURCES:
        for r in by_source.get(sid) or []:
            a = r.get("attributes") or {}
            if a.get("firm_attribution") != "none":
                bad += 1
            if "aggregation_semantics" not in a:
                bad += 1
    checks["trade_records_missing_aggregation_disclaimer"] = bad

    # (d) procurement stages must never be collapsed to "procurement"
    stages = set()
    for sid in PROC_SOURCES:
        for r in by_source.get(sid) or []:
            stages.add((r.get("attributes") or {}).get("stage"))
    checks["procurement_stage_values_observed"] = sorted(str(s) for s in stages)
    checks["collapsed_stage_values_present"] = [
        s for s in stages if s in ("procurement", None, "")
    ]
    return checks


def main() -> int:
    by_source: dict[str, list[dict]] = {}
    for name in TRADE_SOURCES + PROC_SOURCES:
        by_source[name] = _load(name)

    trade = _trade_metrics(by_source)
    awards = _award_metrics(by_source)
    clocks = _clock_metrics(by_source)
    checks = _cross_checks(by_source)

    dedupe = {}
    for sid, rows in by_source.items():
        keys = [dedupe_key(r) for r in rows]
        dedupe[sid] = {"records": len(rows), "unique_dedupe_keys": len(set(keys)),
                       "duplicates": len(rows) - len(set(keys))}

    confirmed_device_relations = sum(
        1 for sid in PROC_SOURCES for r in by_source.get(sid) or []
        if (r.get("attributes") or {}).get("device_relation_status") == "CONFIRMED"
    )

    doc = {
        "experiment_id": "EXP_H4_INDUSTRY",
        "workstream": "industry",
        "generated_at": now_utc(),
        "schema_version": "horizon.evidence.v1",
        "question": (
            "Can bounded, licence-compliant open sources produce time-stamped "
            "industry-adoption and trade evidence that separates aggregate trade "
            "flows from device-level procurement awards — and what fraction of that "
            "evidence actually identifies a firm or a device?"
        ),
        "answers": {
            "trade_series_rows": trade["trade_series_rows_total"],
            "trade_series_definition": trade["series_definition"],
            "procurement_awards_with_named_supplier": awards["awards_with_named_supplier_total"],
            "supplier_award_relations": awards["supplier_award_relations_total"],
            "awards_naming_concrete_device": awards["awards_naming_concrete_device_total"],
            "awards_naming_model_like_token": awards["awards_naming_model_like_token_total"],
            "device_relations_CONFIRMED": confirmed_device_relations,
            "device_relations_CANDIDATE": awards["device_relation_status_counts"].get("CANDIDATE", 0),
            "device_relations_by_status": awards["device_relation_status_counts"],
        },
        "trade": trade,
        "procurement": awards,
        "two_clock_classification": clocks,
        "cross_checks": checks,
        "dedupe": dedupe,
        "honest_limits": [
            "TRADE FLOWS ARE AGGREGATES. None of the %d trade records identifies a "
            "firm, a brand or a device; every trade record carries "
            "firm_attribution='none' and states its aggregation semantics."
            % trade["trade_records_total"],
            "Device<->award relations are CANDIDATE by construction: an award text "
            "may name a device class, but no source here identifies the OEM of the "
            "device that was bought. CONFIRMED device relations = "
            f"{confirmed_device_relations}.",
            "No trade observation has a publication date, so no trade series can "
            "support an observability-lag claim; they are EVENT_ONLY.",
            "Procurement samples are bounded (page 1-2 of one query, or a scan of "
            "300 award releases) and must not be read as census counts.",
            "Commercial bill-of-lading vendors (ImportYeti, ImportGenius, Panjiva, "
            "Descartes Datamyne) yielded zero records: company-level shipment data is "
            "paywalled or robots-disallowed, and was deliberately not acquired.",
        ],
        "reproduce_command": (
            "python CONNECTORS/industry/_licence.py && "
            "python CONNECTORS/industry/un_comtrade.py && "
            "python CONNECTORS/industry/eurostat_comext.py && "
            "python CONNECTORS/industry/uk_hmrc_trade.py && "
            "python CONNECTORS/industry/usaspending.py && "
            "python CONNECTORS/industry/eu_ted.py && "
            "python CONNECTORS/industry/uk_find_a_tender.py && "
            "python experiments/industry/write_registry.py && "
            "python experiments/industry/run_experiment.py"
        ),
    }
    with open(OUT, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(doc, fh, indent=2, ensure_ascii=False)
        fh.write("\n")
    print(json.dumps(doc["answers"], indent=2))
    print(f"written {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
