"""Rollback replay: carry post-cutover observations from a v3 ledger back into a v2 ledger.

FINAL-PREFLIGHT-001, rollback data protection. The v2->v3 migration is one-way, so rolling back
after a cutover means restoring the pre-cutover v2 backup. Everything the new version observed
after that backup would be lost - including first_observed_at, which cannot be re-derived by
re-collecting (the source only knows when it published, not when MedRadar first saw it).

The ledger is append-only and the observation identity is (source, source_record_id), so the
post-cutover rows can be replayed through the old code with their original capture timestamps.
This tool does exactly that and nothing else: it does not copy admissions, watermarks or run
audit rows, because those are re-derived by the old version once it resumes.

Usage:
  python rollback_replay.py export  --db <v3 radar.db> --out <file.json> [--since <iso>]
  python rollback_replay.py import  --db <v2 radar.db> --in  <file.json> [--dry-run]
  python rollback_replay.py compare --before <v2 baseline.db> --after <v2 restored.db>

Run "export" with the NEW build and "import" with the OLD build: each writes only the schema it
knows. Mixing them would defeat the point of the exercise.
"""
from __future__ import annotations

import argparse, json, sqlite3, sys


def export(db, out, since=None):
    con = sqlite3.connect("file:" + db + "?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    where = "WHERE first_observed_at >= ?" if since else ""
    params = (since,) if since else ()
    rows = con.execute(
        "SELECT observation_id, source, source_record_id, record_type, official_identifier,"
        " title, source_url, first_observed_at, observation_origin, backfill_reason,"
        " discovery_phase, event_at, event_at_precision, published_at, published_at_precision,"
        " source_updated_at, source_updated_at_precision, observation_status, current_change_state,"
        " latest_version_id, version_count, content_hash"
        " FROM observation " + where + " ORDER BY first_observed_at, observation_id", params)
    payload = {"since": since, "observations": []}
    for row in rows:
        oid = row["observation_id"]
        versions = [dict(v) for v in con.execute(
            "SELECT version_id, version_seq, captured_at, change_state, content_hash, payload,"
            " changed_fields, source_updated_at FROM observation_version"
            " WHERE observation_id=? ORDER BY version_seq", (oid,))]
        facets = [dict(f) for f in con.execute(
            "SELECT kind, value, confirmation, method, confidence FROM observation_facet"
            " WHERE observation_id=? ORDER BY kind, value", (oid,))]
        entry = dict(row)
        entry["versions"] = versions
        entry["facets"] = facets
        payload["observations"].append(entry)
    con.close()
    with open(out, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False)
    print(json.dumps({"exported": len(payload["observations"]), "out": out}))


def _candidates(facets, kind, key):
    out = []
    for facet in facets:
        if facet["kind"] != kind:
            continue
        item = {key: facet["value"], "confirmation": facet["confirmation"],
                "method": facet["method"]}
        if facet.get("confidence") is not None:
            item["confidence"] = facet["confidence"]
        out.append(item)
    return tuple(out)


def import_(db, path, dry_run):
    from medradar.radar.ledger import ObservationLedger
    from medradar.radar.records import MAPPING_VERSION, MappingResult, RawRecord

    payload = json.load(open(path, encoding="utf-8"))
    ledger = ObservationLedger(db)
    inserted = updated = unchanged = 0
    skipped = []
    try:
        for entry in payload["observations"]:
            facets = entry.get("facets") or []
            mapping = MappingResult(
                organization_candidates=_candidates(facets, "organization", "organization_id"),
                product_candidates=_candidates(facets, "product", "product_key"),
                technology_topics=_candidates(facets, "topic", "topic_id"),
            )
            versions = entry.get("versions") or []
            if not versions:
                skipped.append({"observation_id": entry["observation_id"], "why": "no versions"})
                continue
            outcome = None
            for version in versions:
                body = version.get("payload")
                if isinstance(body, str):
                    body = json.loads(body)
                record = RawRecord(
                    source=entry["source"],
                    source_record_id=entry["source_record_id"],
                    official_identifier=entry.get("official_identifier"),
                    record_type=entry["record_type"],
                    title=entry["title"],
                    url=entry.get("source_url"),
                    event_at=entry.get("event_at"),
                    event_at_precision=entry.get("event_at_precision") or "unknown",
                    published_at=entry.get("published_at"),
                    published_at_precision=entry.get("published_at_precision") or "unknown",
                    source_updated_at=version.get("source_updated_at") or entry.get("source_updated_at"),
                    source_updated_at_precision=entry.get("source_updated_at_precision") or "unknown",
                    payload=body or {},
                    text=" ".join(filter(None, [str(entry.get("title") or ""),
                                                str((body or {}).get("abstract") or ""),
                                                str((body or {}).get("description") or "")])),
                    extra={"official_identifier": entry.get("official_identifier")},
                )
                if dry_run:
                    continue
                outcome = ledger.record_observation(
                    record, mapping,
                    run_id="rollback-replay",
                    adapter_version="rollback-replay",
                    mapping_version=MAPPING_VERSION,
                    seen_at=version.get("captured_at"),
                    origin=entry.get("observation_origin") or "LIVE",
                    backfill_reason=entry.get("backfill_reason"),
                    phase=entry.get("discovery_phase"),
                )
            if dry_run:
                continue
            if outcome is not None:
                if outcome.state == "NEW":
                    inserted += 1
                elif outcome.state == "UPDATED":
                    updated += 1
                else:
                    unchanged += 1
    finally:
        ledger.close()
    print(json.dumps({"replayed": len(payload["observations"]), "new": inserted,
                      "updated": updated, "unchanged": unchanged, "skipped": skipped[:5],
                      "dry_run": dry_run}, indent=2))


def compare(before, after):
    def stats(path):
        con = sqlite3.connect("file:" + path + "?mode=ro", uri=True)
        con.row_factory = sqlite3.Row
        out = {
            "observations": con.execute("SELECT COUNT(*) FROM observation").fetchone()[0],
            "versions": con.execute("SELECT COUNT(*) FROM observation_version").fetchone()[0],
            "first_observed_min": con.execute("SELECT MIN(first_observed_at) FROM observation").fetchone()[0],
            "first_observed_max": con.execute("SELECT MAX(first_observed_at) FROM observation").fetchone()[0],
        }
        con.close()
        return out
    print(json.dumps({"before": stats(before), "after": stats(after)}, indent=2))


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    p_export = sub.add_parser("export")
    p_export.add_argument("--db", required=True)
    p_export.add_argument("--out", required=True)
    p_export.add_argument("--since", default=None)
    p_import = sub.add_parser("import")
    p_import.add_argument("--db", required=True)
    p_import.add_argument("--in", dest="path", required=True)
    p_import.add_argument("--dry-run", action="store_true")
    p_cmp = sub.add_parser("compare")
    p_cmp.add_argument("--before", required=True)
    p_cmp.add_argument("--after", required=True)
    args = parser.parse_args()
    if args.command == "export":
        export(args.db, args.out, args.since)
    elif args.command == "import":
        import_(args.db, args.path, args.dry_run)
    else:
        compare(args.before, args.after)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())