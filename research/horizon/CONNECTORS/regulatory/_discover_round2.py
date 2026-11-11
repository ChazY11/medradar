"""Discovery round 2 — follow the leads from round 1.

Run:  python CONNECTORS/regulatory/_discover_round2.py
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
    # AccessGUDID v3 documentation for the endpoints we actually need
    ("agudid_v3_lookup_doc", "https://accessgudid.nlm.nih.gov/resources/developers/v3/device_lookup_api"),
    ("agudid_v3_history_doc", "https://accessgudid.nlm.nih.gov/resources/developers/v3/device_history_api"),
    ("agudid_v3_implant_download_doc", "https://accessgudid.nlm.nih.gov/resources/developers/v3/implant_list_download"),
    # Canada: where does the API live now?
    ("hc_api_root", "https://health-products.canada.ca/api/"),
    ("hc_mdall_root", "https://health-products.canada.ca/mdall-limh/"),
    ("hc_open_gov", "https://open.canada.ca/data/en/dataset?q=medical+device"),
    # Australia: what ARTG datasets does data.gov.au actually hold?
    ("datagov_devices", "https://data.gov.au/data/api/3/action/package_search?q=medical+device&rows=10"),
    ("datagov_artg2", "https://data.gov.au/data/api/3/action/package_search?q=therapeutic+goods&rows=10"),
    # EUDAMED official machine API route named by its own 429 body
    ("eudamed_api_portal", "https://developer.datalake.sante.service.ec.europa.eu/api-details"),
    # Brazil ANVISA open-data index
    ("anvisa_dados_index", "https://dados.anvisa.gov.br/dados/"),
    # Japan: PMDA machine-readable?
    ("pmda_english_data", "https://www.pmda.go.jp/english/review-services/reviews/0001.html"),
    # UK MHRA (owned source id) - is there a machine path?
    ("mhra_devices", "https://www.gov.uk/government/publications/medical-devices-great-britain-market-surveillance"),
]


def main() -> int:
    summary: list[dict] = []
    with make_client("regulatory-discovery-2", max_requests=20,
                     max_bytes_per_response=4_000_000, max_total_bytes=20_000_000,
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
            body = res.body
            ext = ".html" if "html" in (res.headers.get("content-type") or "") else ".txt"
            if "json" in (res.headers.get("content-type") or ""):
                ext = ".json"
            fn = os.path.join(OUT, name + ext)
            with open(fn, "wb") as fh:
                fh.write(body)
            rec.update({
                "status": res.status,
                "outcome": "OK" if res.ok else "HTTP_ERROR",
                "bytes": len(body),
                "sha256": res.content_hash,
                "content_type": res.headers.get("content-type"),
                "final_url": res.final_url,
                "saved": fn,
            })
            summary.append(rec)
            print(json.dumps(rec, ensure_ascii=False))

        budget = c.budget_report()

    with open(os.path.join(OUT, "round2.json"), "w", encoding="utf-8", newline="\n") as fh:
        json.dump({"generated_at": utc_now(), "budget": budget, "targets": summary},
                  fh, indent=2, ensure_ascii=False)
        fh.write("\n")
    print("\nBUDGET:", json.dumps(budget, ensure_ascii=False)[:400])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
