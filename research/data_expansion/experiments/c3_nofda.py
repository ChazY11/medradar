#!/usr/bin/env python
"""C3 — does a non-FDA registry already contain the device before the FDA decision?

This is the incremental experiment PHOENIX-003's ``NEXT_EXPERIMENT.md`` called N3:
its "pre-regulatory" classification used a 510(k)/PMA-only corpus, so a device
that was already licensed in Canada would look brand new.  We can now test one
non-FDA registry, because Health Canada MDALL turned out to expose a keyless JSON
API.

What this measures, precisely
-----------------------------
For each anchor, does MDALL hold an **active licence whose name matches the
anchor's distinctive product tokens**, with a ``first_licence_status_dt``
**earlier** than the FDA decision date?

What this does NOT measure
--------------------------
MDALL is a *current* snapshot.  It records the licence's own dates, but it does
not prove that the licence was **publicly discoverable** on that date.  So this
is a test of "an earlier regulatory footprint existed", not of "an earlier
publicly observable signal existed".  The distinction is exactly the one
PHOENIX-003 spent a whole round establishing, and it is preserved here.

Coverage is also partial by construction: only Canada is checkable, so
"no earlier Canadian licence" does not mean "no earlier regulatory footprint
anywhere".  EUDAMED is registration-gated, MHRA has no public register, and TGA
blocked automated access in this round.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(ROOT / "experiments"))

from medradar.external_sources import base, timeq  # noqa: E402

import anchor_search as A  # noqa: E402

SAMPLES = ROOT / "samples" / "canada_mdall"
OUT = ROOT / "experiments" / "exp_c" / "C3_NON_FDA_FOOTPRINT.json"
BASE = "https://health-products.canada.ca/api/medical-devices"

FIRM_QUERY = {
    "medtronic": "MEDTRONIC",
    "ge_healthcare": "GE HEALTHCARE",
    "philips": "PHILIPS",
    "draeger": "DRAEGER",
    "mindray": "MINDRAY",
}


def company_ids_from_samples() -> dict[str, list[int]]:
    """Read the company ids the probe already retrieved (no new requests)."""
    out: dict[str, list[int]] = {}
    for firm_key, _query in FIRM_QUERY.items():
        path = SAMPLES / f"company_search_{firm_key}.json"
        if not path.exists():
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        items = payload if isinstance(payload, list) else payload.get("data", [])
        ids = []
        for item in items if isinstance(items, list) else []:
            if isinstance(item, dict):
                company_id = item.get("company_id") or item.get("companyid")
                if isinstance(company_id, int):
                    ids.append(company_id)
        out[firm_key] = sorted(set(ids))
    return out


def fetch_licences(client, company_id: int) -> list[dict]:
    result = client.get(f"{BASE}/licence/", params={"company_id": company_id, "state": "active", "lang": "en", "type": "json"})
    if not result.ok:
        return []
    try:
        payload = result.json()
    except json.JSONDecodeError:
        return []
    return payload if isinstance(payload, list) else payload.get("data", [])


def token_match(name: str, terms: list[str]) -> list[str]:
    matched = []
    for term in terms:
        if re.search(rf"(?<![A-Za-z0-9]){re.escape(term)}(?![A-Za-z0-9])", name, re.IGNORECASE):
            matched.append(term)
    return matched


def main() -> int:
    anchors = A.load_anchors()
    pcs = A.load_product_codes()
    ids = company_ids_from_samples()
    ledger = base.HttpLedger(ROOT / "probes" / "canada_mdall" / "c3_requests.jsonl")
    client = base.HttpClient("canada_mdall_c3", ledger, budget=25, min_interval=1.0, timeout=45.0)

    licences: dict[str, list[dict]] = {}
    fetch_log: list[dict] = []
    for firm_key, company_ids in ids.items():
        collected: list[dict] = []
        for company_id in company_ids[:3]:  # bounded: at most 3 legal entities per firm
            items = fetch_licences(client, company_id)
            fetch_log.append({"firm": firm_key, "company_id": company_id, "licences": len(items)})
            collected.extend(items)
        licences[firm_key] = collected

    rows: list[dict] = []
    for anchor in anchors:
        terms = A.distinctive_terms(anchor, pcs)
        firm_licences = licences.get(anchor["firm_key"], [])
        best = None
        for licence in firm_licences:
            name = str(licence.get("licence_name") or "")
            matched = token_match(name, terms)
            if not matched:
                continue
            licence_date = timeq.parse_date(licence.get("first_licence_status_dt"))
            decision = timeq.parse_date(anchor["decision_date"])
            if not licence_date or not decision:
                continue
            delta = (decision - licence_date).days
            strong = len(matched) >= 2 or any(ch.isdigit() for ch in "".join(matched))
            candidate = {
                "licence_no": licence.get("original_licence_no"),
                "licence_name": name,
                "first_licence_status_dt": licence_date.isoformat(),
                "matched_terms": matched,
                "days_fda_after_canada": delta,
                "match_strength": "strong" if strong else "weak_single_brand_token",
            }
            if delta > 0 and (best is None or delta > best["days_fda_after_canada"]):
                best = candidate
        rows.append(
            {
                "anchor_id": anchor["anchor_id"],
                "firm_key": anchor["firm_key"],
                "decision_date": anchor["decision_date"],
                "terms": terms,
                "licences_available_for_firm": len(firm_licences),
                "earlier_canadian_licence": best,
                "reclassify_pre_regulatory": bool(best),
            }
        )

    checkable = [r for r in rows if r["licences_available_for_firm"] > 0]
    reclassified = [r for r in checkable if r["reclassify_pre_regulatory"]]
    payload = {
        "schema": "medradar.external.c3.v1",
        "computed_at": timeq.utc_iso(),
        "question": "did a non-FDA registry hold a matching device with an earlier regulatory footprint date?",
        "source": "Health Canada MDALL JSON API (keyless)",
        "requests": client.requests_made(),
        "fetch_log": fetch_log,
        "coverage": {
            "anchors_total": len(rows),
            "anchors_checkable_in_canada": len(checkable),
            "anchors_not_checkable": len(rows) - len(checkable),
            "reason_not_checkable": "no MDALL active licence list could be retrieved for that firm (entity mapping or empty list)",
            "registries_not_checkable": [
                "EUDAMED (registration required)",
                "UK MHRA (no public product register exists)",
                "TGA ARTG (automated access blocked this round)",
                "Japan PMDA / Brazil ANVISA / China NMPA (no usable public machine interface)",
            ],
        },
        "result": {
            "anchors_with_earlier_canadian_token_match": len(reclassified),
            "strong_matches": sum(
                1 for r in reclassified if r["earlier_canadian_licence"]["match_strength"] == "strong"
            ),
            "weak_matches_single_brand_token": sum(
                1
                for r in reclassified
                if r["earlier_canadian_licence"]["match_strength"] == "weak_single_brand_token"
            ),
            "share_of_checkable": round(len(reclassified) / len(checkable), 4) if checkable else None,
            "examples": [
                {
                    "anchor_id": r["anchor_id"],
                    "firm": r["firm_key"],
                    "fda_decision": r["decision_date"],
                    "canada_licence": r["earlier_canadian_licence"]["licence_no"],
                    "canada_name": r["earlier_canadian_licence"]["licence_name"][:90],
                    "canada_first_status": r["earlier_canadian_licence"]["first_licence_status_dt"],
                    "days_fda_after_canada": r["earlier_canadian_licence"]["days_fda_after_canada"],
                }
                for r in sorted(reclassified, key=lambda r: -r["earlier_canadian_licence"]["days_fda_after_canada"])[:8]
            ],
        },
        "interpretation": [
            "This counts an EARLIER REGULATORY FOOTPRINT, not an earlier publicly observable signal: MDALL is a current snapshot and does not prove the licence was queryable on that date.",
            "Only Canada is checkable, so absence of a Canadian licence is not evidence of absence of an earlier EU/UK/JP/CN footprint.",
            "A match is a product-token match against a licence name, i.e. tier B evidence, not a confirmed identical device.",
        ],
        "rows": rows,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(payload["coverage"], indent=2))
    print(json.dumps(payload["result"], indent=2)[:1200])
    print(f"requests={payload['requests']} -> {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
