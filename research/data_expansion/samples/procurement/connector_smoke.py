"""Live smoke test for the four shipped procurement/hiring connectors.

Why this exists
---------------
The offline unit tests prove the normalisers and the clock semantics.  This
script proves the connectors actually *run* against the real endpoints through
``base.HttpClient`` (bounded budget, rate limit, request ledger) and produce
schema-valid evidence records.

It is deliberately tiny — one page per source, four requests total — because the
point is "the code path works on live data", not data collection.

Tokens used
-----------
* ``greenhouse`` / ``lever``: the **control** tokens (``stripe``, ``leverdemo``),
  because the five target firms have no board on either platform (see
  ``FIVE_FIRM_PROBE.json``).  Running a control proves the connector works; running
  a firm that 404s would prove nothing new.
* ``usaspending`` / ``uk_find_a_tender``: keyword / stage filters, no firm names,
  because firm-level retrieval differs per source and is documented in the
  probe notes.

Output: ``samples/procurement/CONNECTOR_SMOKE.json`` + the request ledger next to it.

Run:  python research/data_expansion/samples/procurement/connector_smoke.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve()
ROOT = HERE.parents[2]                       # research/data_expansion
REPO = ROOT.parents[1]
sys.path.insert(0, str(REPO))

from medradar.external_sources import base as ev_base
from medradar.external_sources import schema as ev_schema
from medradar.external_sources.procurement import greenhouse
from medradar.external_sources.procurement import lever
from medradar.external_sources.procurement import uk_find_a_tender
from medradar.external_sources.procurement import usaspending

OUT = HERE.parent / "CONNECTOR_SMOKE.json"
LEDGER = HERE.parent / "connector_smoke_requests.jsonl"


def _client(source_id: str, *, budget: int) -> ev_base.HttpClient:
    ledger = ev_base.HttpLedger(LEDGER)
    return ev_base.HttpClient(
        source_id=source_id, ledger=ledger, budget=budget, min_interval=1.0, max_retries=1
    )


def _summarise(source_id: str, records: list[dict], client: ev_base.HttpClient) -> dict:
    problems: list[str] = []
    for record in records:
        if record.get("source_id") != source_id:
            problems.append(f"{record.get('evidence_id')}: wrong source_id")
        problems.extend(ev_schema.validate_evidence(record))
    kinds: dict[str, int] = {}
    for record in records:
        kinds[record["kind"]] = kinds.get(record["kind"], 0) + 1
    first = records[0] if records else {}
    return {
        "source_id": source_id,
        "requests": client.requests_made(),
        "records": len(records),
        "kinds": kinds,
        "schema_problems": problems,
        "schema_valid": not problems,
        "first_record": {
            "evidence_id": first.get("evidence_id"),
            "kind": first.get("kind"),
            "source_record_id": first.get("source_record_id"),
            "source_public_at": (first.get("time") or {}).get("source_public_at"),
            "event_at": (first.get("time") or {}).get("event_at"),
            "first_observed_at": (first.get("time") or {}).get("first_observed_at"),
            "canonical_key": first.get("canonical_key"),
            "entity_refs": [
                {"name_raw": r.get("name_raw"), "resolved_key": r.get("resolved_key"), "method": r.get("method")}
                for r in (first.get("entity_refs") or [])
            ],
        },
    }


def main() -> int:
    results: list[dict] = []

    client = _client("usaspending", budget=2)
    records = usaspending.collect(client, limit=3, keywords=["stent"], page_size=3, max_pages=1)
    results.append(_summarise("usaspending", records, client))

    client = _client("uk_find_a_tender", budget=2)
    records = uk_find_a_tender.collect(
        client, limit=3, stages="award", page_size=3, max_pages=1
    )
    results.append(_summarise("uk_find_a_tender", records, client))
    if records:
        results[-1]["stage_split"] = uk_find_a_tender.split_by_stage(records)

    client = _client("greenhouse", budget=2)
    records = greenhouse.collect(client, token="stripe", limit=3)
    results.append(_summarise("greenhouse", records, client))
    if records:
        results[-1]["duplicate_report"] = greenhouse.duplicate_report(records)

    client = _client("lever", budget=2)
    records = lever.collect(client, company="leverdemo", limit=3)
    results.append(_summarise("lever", records, client))
    if records:
        results[-1]["department_coverage"] = lever.department_coverage(records)

    payload = {
        "schema": "medradar.procurement.connector_smoke.v1",
        "note": (
            "Live smoke test of the shipped connectors through base.HttpClient. "
            "Tiny by design: one bounded page per source. Greenhouse/Lever used the "
            "control tokens because the five target firms have no board there."
        ),
        "results": results,
    }
    OUT.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    for result in results:
        print(
            f"{result['source_id']:<20} requests={result['requests']} records={result['records']:>2} "
            f"kinds={result['kinds']} valid={result['schema_valid']}"
        )
    print(f"wrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
