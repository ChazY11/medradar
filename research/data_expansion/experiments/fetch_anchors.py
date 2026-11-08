#!/usr/bin/env python
"""Build the frozen regulatory anchor set used by EXP-A and EXP-C.

Pre-registered rule (``EXPERIMENT_DESIGN.md`` §1): per firm, per calendar year
2017-2024, the first openFDA 510(k)/PMA decision ordered by
``(decision_date, official number)``.  Company attribution uses the confirmed
tier of :class:`medradar.external_sources.identity.CompanyIndex` — a candidate
match is not allowed to create an anchor.

Retrieval strategy (documented so the set is reproducible):

* one request per (firm token, endpoint) with ``sort=decision_date:asc`` and
  ``limit=1000``; the token is a distinctive name fragment, not the full alias
  list, so the request count stays small;
* every returned ``applicant`` string is re-resolved locally; only confirmed
  matches survive, which is what protects against a token pulling in a
  lookalike firm;
* the first surviving record per (firm, year) becomes the anchor.

The output includes every query, its returned count and the response digest, so
a reviewer can re-run exactly the same retrieval.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parents[1]
sys.path.insert(0, str(REPO))

from medradar.external_sources import base, identity, timeq  # noqa: E402

OUT_DIR = ROOT / "experiments" / "anchors"
YEARS = tuple(range(2017, 2025))

#: Distinctive retrieval tokens per target firm.  Deliberately short: the
#: confirmed-match re-resolution below is what carries correctness, not the token.
FIRM_TOKENS: dict[str, tuple[str, ...]] = {
    "medtronic": ("medtronic", "covidien"),
    "ge_healthcare": ("ge medical", "ge healthcare"),
    "philips": ("philips",),
    "draeger": ("draeger", "dräger"),
    "mindray": ("mindray",),
}

ENDPOINTS = {
    "510k": ("https://api.fda.gov/device/510k.json", "k_number", "device_name"),
    "pma": ("https://api.fda.gov/device/pma.json", "pma_number", "trade_name"),
}


def canonical_hash(payload) -> str:
    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def fetch(limit: int, min_interval: float, allow_network: bool) -> dict:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    ledger = base.HttpLedger(OUT_DIR / "requests.jsonl")
    client = base.HttpClient(
        "anchor_builder",
        ledger,
        budget=40,
        min_interval=min_interval,
        timeout=45.0,
        allow_network=allow_network,
    )
    index = identity.CompanyIndex.from_config()
    retrieval: list[dict] = []
    candidates: dict[tuple[str, str, int], list[dict]] = {}

    for firm_key, tokens in FIRM_TOKENS.items():
        for token in tokens:
            for endpoint_name, (url, number_field, name_field) in ENDPOINTS.items():
                params = {
                    "search": f'applicant:"{token}"',
                    "sort": "decision_date:asc",
                    "limit": min(1000, limit),
                }
                result = client.get(url, params=params)
                entry = {
                    "firm_key": firm_key,
                    "token": token,
                    "endpoint": endpoint_name,
                    "url": result.url,
                    "status": result.status,
                    "bytes": len(result.body),
                    "sha256": base.sha256_bytes(result.body) if result.body else "",
                    "error": result.error,
                    "returned": 0,
                    "confirmed": 0,
                }
                if result.ok:
                    try:
                        payload = result.json()
                    except json.JSONDecodeError:
                        entry["error"] = "non-JSON response"
                        payload = {}
                    results = payload.get("results", []) if isinstance(payload, dict) else []
                    entry["returned"] = len(results)
                    for item in results:
                        applicant = item.get("applicant") or ""
                        resolution = index.resolve(applicant)
                        if resolution.get("method") not in {"official_id", "exact_alias", "multi_field"}:
                            continue
                        if resolution.get("resolved_key") != firm_key:
                            continue
                        decision = timeq.parse_date(item.get("decision_date"))
                        if decision is None or decision.year not in YEARS:
                            continue
                        number = identity.normalize_regulatory_number(item.get(number_field) or "")
                        if not number:
                            continue
                        entry["confirmed"] += 1
                        # Pre-registered rule keys on (firm, calendar year) only:
                        # 510(k) and PMA compete for the same slot, ordered by
                        # decision date then official number.
                        candidates.setdefault((firm_key, decision.year), []).append(
                            {
                                "anchor_id": f"{endpoint_name}:{number}",
                                "firm_key": firm_key,
                                "endpoint": endpoint_name,
                                "official_number": number,
                                "applicant_raw": applicant[:200],
                                "device_name": str(item.get(name_field) or item.get("device_name") or "")[:200],
                                "product_code": str(item.get("product_code") or "")[:20],
                                "decision_date": decision.isoformat(),
                                "decision_year": decision.year,
                                "resolution_method": resolution.get("method", ""),
                                "source_record_id": number,
                                "source_url": result.url,
                            }
                        )
                retrieval.append(entry)

    anchors: list[dict] = []
    for key in sorted(candidates):
        items = sorted(candidates[key], key=lambda a: (a["decision_date"], a["official_number"]))
        anchors.append(items[0])

    return {
        "schema": "medradar.external.anchors.v1",
        "built_at": timeq.utc_iso(),
        "rule": (
            "per firm, per calendar year 2017-2024, first openFDA 510(k)/PMA decision "
            "ordered by (decision_date, official number); company attribution via confirmed "
            "CompanyIndex match only"
        ),
        "retrieval": retrieval,
        "requests": client.requests_made(),
        "anchors": anchors,
        "counts": {
            "anchors": len(anchors),
            "by_firm": {f: sum(1 for a in anchors if a["firm_key"] == f) for f in FIRM_TOKENS},
            "by_endpoint": {
                e: sum(1 for a in anchors if a["endpoint"] == e) for e in ENDPOINTS
            },
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=1000)
    parser.add_argument("--min-interval", type=float, default=0.6)
    parser.add_argument("--offline", action="store_true", help="write an empty offline skeleton")
    args = parser.parse_args(argv)

    payload = fetch(args.limit, args.min_interval, allow_network=not args.offline)
    suffix = ".offline" if args.offline else ""
    anchors_path = OUT_DIR / f"ANCHORS{suffix}.json"
    anchors_path.parent.mkdir(parents=True, exist_ok=True)
    anchors_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    digest = canonical_hash(payload["anchors"])
    (OUT_DIR / f"ANCHORS{suffix}.sha256").write_text(
        f"{digest}  ANCHORS{suffix}.json:anchors\n", encoding="utf-8"
    )
    print(json.dumps(payload["counts"], indent=2))
    print(f"anchors sha256 = {digest}")
    print(f"requests = {payload['requests']}, wrote {anchors_path}")
    return 0 if payload["anchors"] or args.offline else 1


if __name__ == "__main__":
    raise SystemExit(main())
