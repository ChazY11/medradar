"""Discovery round 4 — settle sizes and the last open questions.

  * MDALL: does the documented `medical-devices` base answer, and how big is
    the active-licence payload?
  * GUDID: how big is the weekly release ZIP (a bounded, real GUDID sample)?
  * openFDA: what rate limit does the official docs page state for keyless use?

Run:  python CONNECTORS/regulatory/_discover_round4.py
"""

from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from hz.http import BudgetExceeded  # noqa: E402

from CONNECTORS.regulatory._util import ROOT, make_client, probe_size, utc_now  # noqa: E402

OUT = os.path.join(ROOT, "DATASETS", "regulatory", "_discovery")

GETS = [
    ("hc_company_medtronic",
     "https://health-products.canada.ca/api/medical-devices/company/?company_name=medtronic&lang=en&type=json"),
    ("openfda_auth_docs", "https://open.fda.gov/apis/authentication/"),
]
SIZES = [
    ("size_hc_active_licences",
     "https://health-products.canada.ca/api/medical-devices/licence/?state=active&lang=en&type=json"),
    ("size_gudid_weekly_zip",
     "https://accessgudid.nlm.nih.gov/release_files/download/gudid_weekly_update_20261026_20261030.zip"),
]


def main() -> int:
    summary: list[dict] = []
    with make_client("regulatory-discovery-4", max_requests=10,
                     max_bytes_per_response=3_000_000, max_total_bytes=10_000_000,
                     rps=1.2) as c:
        for name, url in GETS:
            rec = {"name": name, "url": url}
            try:
                res = c.get(url)
            except BudgetExceeded as exc:
                rec.update({"outcome": "BUDGET_EXCEEDED", "error": str(exc)})
                summary.append(rec)
                break
            except Exception as exc:  # noqa: BLE001
                rec.update({"outcome": "TRANSPORT_ERROR",
                            "error": f"{type(exc).__name__}: {exc}"[:300]})
                summary.append(rec)
                print(json.dumps(rec, ensure_ascii=False))
                continue
            ct = res.headers.get("content-type") or ""
            ext = ".json" if "json" in ct else (".html" if "html" in ct else ".txt")
            fn = os.path.join(OUT, name + ext)
            with open(fn, "wb") as fh:
                fh.write(res.body)
            rec.update({
                "status": res.status, "outcome": "OK" if res.ok else "HTTP_ERROR",
                "bytes": len(res.body), "sha256": res.content_hash,
                "content_type": ct, "final_url": res.final_url, "saved": fn,
            })
            summary.append(rec)
            print(json.dumps(rec, ensure_ascii=False))

        for name, url in SIZES:
            rec = {"name": name}
            rec.update(probe_size(c, url))
            summary.append(rec)
            print(json.dumps(rec, ensure_ascii=False))

        budget = c.budget_report()

    with open(os.path.join(OUT, "round4.json"), "w", encoding="utf-8", newline="\n") as fh:
        json.dump({"generated_at": utc_now(), "budget": budget, "targets": summary},
                  fh, indent=2, ensure_ascii=False)
        fh.write("\n")
    print("\nBUDGET:", json.dumps(budget, ensure_ascii=False)[:300])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
