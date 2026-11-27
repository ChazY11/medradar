"""Discovery round 3 — Canada MDALL official API + GUDID bulk + TGA.

Leads from round 2 / public documentation:
  * MDALL API guide   https://health-products.canada.ca/api/documentation/mdall-documentation-en.html
  * MDALL open data   https://open.canada.ca/data/dataset/c801a084-210b-4cd2-8513-26a00b66eb6f
  * AccessGUDID bulk  https://accessgudid.nlm.nih.gov/download

Run:  python CONNECTORS/regulatory/_discover_round3.py
"""

from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from hz.http import BudgetExceeded, ResponseTooLarge  # noqa: E402

from CONNECTORS.regulatory._util import ROOT, make_client, utc_now  # noqa: E402

OUT = os.path.join(ROOT, "DATASETS", "regulatory", "_discovery")
os.makedirs(OUT, exist_ok=True)

TARGETS = [
    ("hc_mdall_api_doc", "https://health-products.canada.ca/api/documentation/mdall-documentation-en.html"),
    ("hc_ckan_mdall",
     "https://open.canada.ca/data/api/3/action/package_show?id=c801a084-210b-4cd2-8513-26a00b66eb6f"),
    ("agudid_download_page", "https://accessgudid.nlm.nih.gov/download"),
    ("tga_apps_root", "https://apps.tga.gov.au/"),
    ("tga_artg_html", "https://www.tga.gov.au/resources/artg"),
]


def main() -> int:
    summary: list[dict] = []
    with make_client("regulatory-discovery-3", max_requests=10,
                     max_bytes_per_response=4_000_000, max_total_bytes=16_000_000,
                     rps=1.2) as c:
        for name, url in TARGETS:
            rec = {"name": name, "url": url}
            try:
                res = c.get(url)
            except BudgetExceeded as exc:
                rec.update({"outcome": "BUDGET_EXCEEDED", "error": str(exc)})
                summary.append(rec)
                break
            except ResponseTooLarge as exc:
                rec.update({"outcome": "TOO_LARGE", "error": str(exc)[:200]})
                summary.append(rec)
                continue
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
                "status": res.status,
                "outcome": "OK" if res.ok else "HTTP_ERROR",
                "bytes": len(res.body),
                "sha256": res.content_hash,
                "content_type": ct,
                "final_url": res.final_url,
                "saved": fn,
            })
            summary.append(rec)
            print(json.dumps(rec, ensure_ascii=False))
        budget = c.budget_report()

    with open(os.path.join(OUT, "round3.json"), "w", encoding="utf-8", newline="\n") as fh:
        json.dump({"generated_at": utc_now(), "budget": budget, "targets": summary},
                  fh, indent=2, ensure_ascii=False)
        fh.write("\n")
    print("\nBUDGET:", json.dumps(budget, ensure_ascii=False)[:300])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
