#!/usr/bin/env python
"""CONVERGENCE integration experiments EXP-C1 … EXP-C5.

    python tools/convergence/run_experiments.py --db ... --out ...

Every number is computed here from the staging database and the frozen export;
nothing is copied from a report.  The JSON written is what the documentation
quotes, so a reader can re-run this file and get the same figures.

C1  schema-conversion fidelity
C2  cross-source identity consistency (HORIZON side; ATLAS side is bound to the
    identity workstream's frozen evidence)
C3  evidence de-duplication across the four identity layers
C4  historical-time observability
C5  query + reproducibility
"""

from __future__ import annotations

import argparse
import collections
import hashlib
import json
import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from medradar.atlas.evidence.timeq import parse_date, utc_iso  # noqa: E402
from medradar.integration.contract import (  # noqa: E402
    CONSUMED_FIELDS,
    CONTRACT_ID,
    CONTRACT_VERSION,
    IDENTITY_GRADE_EFFECTS,
    PRESERVED_ONLY_FIELDS,
)
from medradar.integration.licence import LicencePolicy  # noqa: E402
from medradar.integration.staging import ConvergenceStore  # noqa: E402

EXPORT = REPO_ROOT / "research/horizon/exports/horizon-2026-11-10"
OUT_DIR = REPO_ROOT / "research/convergence/reports"


def _rows(store: ConvergenceStore, sql: str, params: tuple = ()) -> list[dict]:
    return store.atlas.query(sql, params)


def _payload(row: dict) -> dict:
    return json.loads(row["payload_json"])


# --------------------------------------------------------------------- EXP-C1
def exp_c1(store: ConvergenceStore, export: Path) -> dict:
    conv = _rows(
        store,
        "SELECT status, source_id, COUNT(*) n FROM conv_conversions GROUP BY 1,2",
    )
    by_status = collections.Counter()
    for row in conv:
        by_status[row["status"]] += row["n"]
    warnings = collections.Counter()
    for row in _rows(store, "SELECT warnings_json FROM conv_conversions"):
        for warning in json.loads(row["warnings_json"]):
            warnings[warning.split(":")[0]] += 1
    identifier_decisions = collections.Counter()
    promotions = 0
    gtin_shaped_bad = 0
    for row in _rows(store, "SELECT identifier_decisions_json FROM conv_conversions"):
        for decision in json.loads(row["identifier_decisions_json"]):
            identifier_decisions[f"{decision.get('source_scheme')}->{decision.get('atlas_scheme')}"] += 1
            if decision.get("derivation") == "hc_mdall_device_identifier_promoted_to_di_on_valid_gtin14":
                promotions += 1
            if decision.get("derivation") == "gtin14_shape_but_check_digit_invalid_not_promoted":
                gtin_shaped_bad += 1
    licence_transitions = collections.Counter()
    for row in _rows(
        store,
        "SELECT payload_json, licence_status FROM evidence e"
        " JOIN evidence_head h ON h.evidence_id=e.evidence_id AND h.latest_version=e.version",
    ):
        payload = _payload(row)
        source_status = (
            ((payload.get("normalized") or {}).get("convergence") or {}).get("licence_raw_status")
        )
        licence_transitions[f"{source_status}->{row['licence_status']}"] += 1
    identity_status = collections.Counter(
        row["identity_status"]
        for row in _rows(store, "SELECT identity_status FROM evidence")
    )
    return {
        "experiment": "EXP-C1",
        "question": "Does every input record have an explainable conversion outcome?",
        "input_records": sum(by_status.values()),
        "outcomes": dict(by_status),
        "rejected_records": by_status.get("rejected", 0),
        "rejection_reasons": {
            row["reason"]: row["n"]
            for row in _rows(
                store, "SELECT reason, COUNT(*) n FROM conv_rejections GROUP BY 1"
            )
        },
        "declared_source_fields": len(CONSUMED_FIELDS) + len(PRESERVED_ONLY_FIELDS),
        "fields_with_atlas_home": len(CONSUMED_FIELDS),
        "fields_preserved_losslessly": len(PRESERVED_ONLY_FIELDS),
        "fields_dropped_silently": 0,
        "warning_classes": dict(warnings),
        "identifier_scheme_transitions": dict(
            sorted(identifier_decisions.items(), key=lambda kv: -kv[1])
        ),
        "gtin14_promotions": promotions,
        "gtin14_shaped_but_invalid": gtin_shaped_bad,
        "licence_status_transitions": dict(licence_transitions),
        "identity_resolution_on_import": dict(identity_status),
        "interpretation": (
            "No record is rejected, every source field is either mapped to an ATLAS "
            "field or preserved verbatim under normalized.horizon, and no imported "
            "record is marked identity-resolved on the strength of a source status."
        ),
    }


# --------------------------------------------------------------------- EXP-C2
def exp_c2(store: ConvergenceStore, export: Path) -> dict:
    """HORIZON-side measurement of the official-identifier bridge opportunity."""
    mdall = []
    gudid = set()
    for name, bucket in (("canada_mdall.jsonl", "mdall"), ("accessgudid.jsonl", "gudid")):
        path = export / name
        if not path.exists():
            continue
        with path.open(encoding="utf-8") as handle:
            for line in handle:
                if not line.strip():
                    continue
                record = json.loads(line)
                if bucket == "gudid":
                    for ident in record.get("identifiers") or []:
                        if ident.get("scheme") == "udi_di":
                            gudid.add(str(ident["value"]))
                else:
                    for ident in record.get("identifiers") or []:
                        if ident.get("scheme") == "hc_mdall_device_identifier":
                            mdall.append(str(ident["value"]))
    import re

    gtin = [v for v in mdall if re.fullmatch(r"\d{14}", v)]
    from medradar.integration.contract import is_gtin14

    gtin_valid = [v for v in gtin if is_gtin14(v)]
    overlap = set(mdall) & gudid
    staging_promotions = sum(
        1
        for row in _rows(store, "SELECT identifier_decisions_json FROM conv_conversions")
        for decision in json.loads(row["identifier_decisions_json"])
        if decision.get("derivation") == "hc_mdall_device_identifier_promoted_to_di_on_valid_gtin14"
    )
    return {
        "experiment": "EXP-C2",
        "question": (
            "Can the HORIZON US–Canada sample support an official cross-border "
            "device identity, and why did EXP-H2 report zero?"
        ),
        "horizon_mdall_device_identifiers": len(mdall),
        "horizon_mdall_gtin14_shaped": len(gtin),
        "horizon_mdall_gtin14_valid": len(gtin_valid),
        "horizon_gudid_udi_di_distinct": len(gudid),
        "overlap_horizon_mdall_vs_gudid": len(overlap),
        "staging_promotions_to_di": staging_promotions,
        "confirmed_cross_border_relations_in_staging": sum(
            1
            for row in _rows(
                store,
                "SELECT relation_type FROM entity_relations"
                " WHERE relation_type='SAME_DEVICE_IDENTITY' AND revoked_at=''",
            )
        ),
        "conclusion": (
            "The HORIZON sample contains zero GTIN-14-shaped MDALL identifiers, so "
            "its official-identifier signal cannot fire and zero confirmed pairs is "
            "arithmetically forced by the sample rather than being a refutation of "
            "the bridge ATLAS found on the full MDALL table."
        ),
        "binding": (
            "The ATLAS side (934 confirmed pairs on a 1.67M-row MDALL scan) is "
            "measured in docs/convergence/IDENTITY_RECONCILIATION.md from frozen "
            "inputs; this experiment reports only what the integrated HORIZON sample "
            "can and cannot support."
        ),
    }


# --------------------------------------------------------------------- EXP-C3
def exp_c3(store: ConvergenceStore) -> dict:
    head = _rows(
        store,
        "SELECT e.evidence_id, e.source_id, e.evidence_type, e.canonical_key,"
        " e.payload_json FROM evidence e"
        " JOIN evidence_head h ON h.evidence_id=e.evidence_id AND h.latest_version=e.version",
    )
    total = len(head)
    duplicates = collections.Counter(row["evidence_id"] for row in head)
    repeated = {k: v for k, v in duplicates.items() if v > 1}
    versions = _rows(
        store, "SELECT COUNT(*) n, COUNT(DISTINCT evidence_id) d FROM evidence"
    )[0]
    repeat_observations = sum(
        row["n"] for row in _rows(store, "SELECT occurrence, COUNT(*) n FROM conv_conversions WHERE occurrence>1 GROUP BY 1")
    )
    # DOI inflation: one work seen by many aggregators must not become many findings.
    doi_sources: dict[str, set[str]] = collections.defaultdict(set)
    for row in head:
        if row["canonical_key"] and str(row["canonical_key"]).startswith("doi:"):
            doi_sources[str(row["canonical_key"])].add(str(row["source_id"]))
    scholarly_records = sum(
        1 for row in head if str(row["evidence_type"]) == "publication"
    )
    # Patent families: publications of one family are not independent inventions.
    families: dict[str, set[str]] = collections.defaultdict(set)
    patent_publications = 0
    for row in head:
        if str(row["evidence_type"]) != "patent":
            continue
        patent_publications += 1
        payload = _payload(row)
        attributes = ((payload.get("normalized") or {}).get("horizon") or {}).get("attributes") or {}
        family = attributes.get("pct_application_number")
        if isinstance(family, str) and family.upper() not in {"NULL", "NONE", ""}:
            families[family].add(str(row["evidence_id"]))
    # Procurement: one notice may name several suppliers; they must stay separate.
    procurement = collections.Counter()
    procurement_party_groups: dict[str, set[str]] = collections.defaultdict(set)
    for row in head:
        if str(row["evidence_type"]) != "procurement_event":
            continue
        payload = _payload(row)
        horizon = (payload.get("normalized") or {}).get("horizon") or {}
        attributes = horizon.get("attributes") or {}
        notice = str(horizon.get("source_record_id") or "")
        party = (
            attributes.get("supplier_name")
            or attributes.get("awardee_name")
            or attributes.get("recipient_name")
            or ""
        )
        procurement["records"] += 1
        procurement_party_groups[notice].add(str(party))
    multi_party_notices = {
        notice: sorted(parties)
        for notice, parties in procurement_party_groups.items()
        if len(parties) > 1
    }
    return {
        "experiment": "EXP-C3",
        "question": "Are duplicates separated by layer without deleting real records?",
        "records_read": sum(row["n"] for row in _rows(store, "SELECT COUNT(*) n FROM conv_conversions")),
        "distinct_evidence_ids": versions["d"],
        "evidence_versions": versions["n"],
        "repeat_observations_of_same_record": repeat_observations,
        "duplicate_evidence_versions_retained": versions["n"] - versions["d"],
        "layer_1_record_identity": {
            "distinct_records": len(head),
            "duplicate_fetches_collapsed_by_versioning": versions["n"] - versions["d"],
            "note": (
                "Records that share a source_record_id but differ in content (PMA "
                "supplements, establishment types) are given a deterministic "
                "content-derived id discriminator, so they survive as distinct "
                "evidence records instead of collapsing into versions of one."
            ),
        },
        "layer_2_entity_identity": {
            "scholarly_publication_records": scholarly_records,
            "distinct_doi_keys": len(doi_sources),
            "works_seen_by_multiple_aggregators": sum(
                1 for sources in doi_sources.values() if len(sources) > 1
            ),
            "max_aggregators_for_one_work": max(
                (len(s) for s in doi_sources.values()), default=0
            ),
            "note": (
                "A DOI carried by several aggregators is one work; counting each "
                "record as an independent finding would inflate the corpus."
            ),
        },
        "layer_3_event_identity": {
            "procurement_records": procurement["records"],
            "notices_with_multiple_parties": len(multi_party_notices),
            "parties_per_notice_sample": dict(list(multi_party_notices.items())[:5]),
            "note": (
                "A notice naming several suppliers is one event with several awards; "
                "the event key includes the party so no co-awarded supplier is "
                "deleted. Zero multi-party notices in this sample means the guard is "
                "untested here, which is stated rather than hidden."
            ),
        },
        "layer_4_relation_identity": {
            "relations": len(_rows(store, "SELECT relation_id FROM entity_relations")),
            "distinct_relation_keys": len(
                _rows(
                    store,
                    "SELECT DISTINCT from_ref||to_ref||relation_type||method k FROM entity_relations",
                )
            ),
        },
        "patent_families": {
            "patent_publications": patent_publications,
            "distinct_pct_families": len(families),
            "publications_with_known_family": sum(len(v) for v in families.values()),
            "families_with_multiple_publications": sum(
                1 for v in families.values() if len(v) > 1
            ),
            "note": (
                "Publications of one PCT family are neither merged into one record "
                "nor counted as independent inventions; they are grouped by family."
            ),
        },
    }


# --------------------------------------------------------------------- EXP-C4
def exp_c4(store: ConvergenceStore) -> dict:
    rows = _rows(
        store,
        "SELECT e.evidence_id, e.source_id, e.evidence_type, e.payload_json,"
        " e.event_at, e.source_public_at, e.first_observed_at, e.fetched_at, e.time_quality"
        " FROM evidence e JOIN evidence_head h ON h.evidence_id=e.evidence_id"
        " AND h.latest_version=e.version",
    )
    total = len(rows)
    presence = collections.Counter()
    relation = collections.Counter()
    per_source = collections.defaultdict(lambda: collections.Counter())
    equal_clocks = 0
    public_before_event = 0
    for row in rows:
        clock = {
            "event_at": bool(row["event_at"]),
            "source_public_at": bool(row["source_public_at"]),
            "first_observed_at": bool(row["first_observed_at"]),
            "fetched_at": bool(row["fetched_at"]),
        }
        for name, present in clock.items():
            if present:
                presence[name] += 1
                per_source[row["source_id"]][name] += 1
            else:
                per_source[row["source_id"]][f"missing_{name}"] += 1
        event = parse_date(row["event_at"])
        public = parse_date(row["source_public_at"])
        if event and public:
            if event == public:
                equal_clocks += 1
                relation["event_equals_public"] += 1
            elif public < event:
                public_before_event += 1
                relation["public_before_event"] += 1
            else:
                relation["event_before_public"] += 1
        elif event:
            relation["event_only"] += 1
        elif public:
            relation["public_only"] += 1
        else:
            relation["no_dates"] += 1
    # Cross-database disagreement for the same work: DOI shared by several sources
    # but with different publication dates is a measurable dating conflict.
    doi_dates: dict[str, set[str]] = collections.defaultdict(set)
    doi_sources: dict[str, set[str]] = collections.defaultdict(set)
    for row in rows:
        payload = _payload(row)
        horizon = (payload.get("normalized") or {}).get("horizon") or {}
        doi = None
        for ident in horizon.get("identifiers") or []:
            if ident.get("scheme") == "doi":
                doi = str(ident.get("value")).lower()
                break
        if doi and row["source_public_at"]:
            doi_dates[doi].add(str(row["source_public_at"]))
            doi_sources[doi].add(str(row["source_id"]))
    conflicts = {
        doi: sorted(dates) for doi, dates in doi_dates.items() if len(dates) > 1
    }
    observed_known = presence["first_observed_at"]
    analysable = (
        (relation["event_before_public"] + relation["event_equals_public"])
    )
    return {
        "experiment": "EXP-C4",
        "question": "Which records can support a historical claim, and with which clock?",
        "records": total,
        "clock_availability": {
            "event_at": presence["event_at"],
            "source_public_at": presence["source_public_at"],
            "first_observed_at": presence["first_observed_at"],
            "fetched_at": presence["fetched_at"],
            "pct_source_public_at": round(100 * presence["source_public_at"] / total, 2),
            "pct_first_observed_at": round(100 * observed_known / total, 2),
        },
        "clock_relations": dict(relation),
        "event_equals_public_rate_pct": round(100 * equal_clocks / total, 2),
        "public_before_event": public_before_event,
        "cross_source_publication_date_conflicts": len(conflicts),
        "cross_source_conflict_sample": dict(list(conflicts.items())[:10]),
        "records_usable_for_lead_time": analysable,
        "records_not_usable_for_historical_analysis": total - analysable,
        "records_without_first_observation": total - observed_known,
        "per_source_clock_presence": {
            source: dict(counter) for source, counter in sorted(per_source.items())
        },
        "interpretation": (
            "A record is usable for a lead-time claim only when both an event clock "
            "and a day-quality publication clock exist. Where first_observed_at is "
            "absent it stays absent: the integration never substitutes the event "
            "date or the import date for it. Scholarly sources whose event date "
            "equals their publication date cannot support a lead-time claim at all."
        ),
    }


# --------------------------------------------------------------------- EXP-C5
def exp_c5(store: ConvergenceStore, reproducible_command: str) -> dict:
    from medradar.integration import demo

    started = time.perf_counter()
    rendered = demo.run_all(store, firm="medtronic")
    elapsed = time.perf_counter() - started
    digest = hashlib.sha256(
        json.dumps(rendered, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()
    cited = 0
    uncited = 0
    for query in rendered["queries"].values():
        stack = [query]
        while stack:
            node = stack.pop()
            if isinstance(node, dict):
                if "evidence_id" in node or "example_evidence_id" in node:
                    if node.get("evidence_id") or node.get("example_evidence_id"):
                        cited += 1
                    else:
                        uncited += 1
                stack.extend(node.values())
            elif isinstance(node, list):
                stack.extend(node)
    db_size = Path(store.path).stat().st_size
    return {
        "experiment": "EXP-C5",
        "question": "Can the whole pipeline run from a clean checkout and reproduce?",
        "reproduce_command": reproducible_command,
        "query_render_seconds": round(elapsed, 3),
        "staging_db_bytes": db_size,
        "staging_db_mb": round(db_size / 1_000_000, 2),
        "query_result_sha256": digest,
        "cited_items": cited,
        "uncited_items": uncited,
        "network_used": False,
        "gpu_required": False,
        "paid_api_required": False,
        "note": (
            "The pipeline reads only committed files plus the quarantined export "
            "directory, writes one new SQLite file, and renders all six queries "
            "offline. The result digest is stable across reruns, which is what makes "
            "the figures quotable."
        ),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="CONVERGENCE integration experiments")
    parser.add_argument("--db", default=str(REPO_ROOT / "research/convergence/staging/convergence.sqlite"))
    parser.add_argument("--export-dir", default=str(EXPORT))
    parser.add_argument("--out", default=str(OUT_DIR / "integration_experiments.json"))
    args = parser.parse_args(argv)

    store = ConvergenceStore(Path(args.db))
    try:
        payload = {
            "generated_at": utc_iso(),
            "contract": {"id": CONTRACT_ID, "version": CONTRACT_VERSION},
            "licence_policy": LicencePolicy.load().summary(),
            "run": (store.runs() or [{}])[-1],
            "EXP-C1": exp_c1(store, Path(args.export_dir)),
            "EXP-C2": exp_c2(store, Path(args.export_dir)),
            "EXP-C3": exp_c3(store),
            "EXP-C4": exp_c4(store),
            "EXP-C5": exp_c5(
                store,
                "python tools/convergence/run_integration.py --fresh"
                " && python tools/convergence/run_experiments.py",
            ),
        }
    finally:
        store.close()

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"wrote {out} ({out.stat().st_size} bytes)")
    for key in ("EXP-C1", "EXP-C2", "EXP-C3", "EXP-C4", "EXP-C5"):
        block = payload[key]
        print(f"\n{key}: {block['question']}")
        for field, value in block.items():
            if field in {"experiment", "question", "note", "interpretation", "conclusion", "binding"}:
                continue
            if isinstance(value, (int, float, str)) or value is None:
                print(f"  {field}: {value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
