"""Discovery round 1 — find the endpoints that actually work today.

Run:  python CONNECTORS/regulatory/_discover_round1.py

Every request goes through hz.http.BoundedClient, so REQUEST_LOG.jsonl under
SOURCE_PROBES/regulatory/records the whole round. Bodies we care about are
saved verbatim under DATASETS/regulatory/_discovery/.
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
    # ---- AccessGUDID docs + candidate API shapes --------------------------
    ("agudid_docs", "https://accessgudid.nlm.nih.gov/resources/developers"),
    ("agudid_search_api_doc", "https://accessgudid.nlm.nih.gov/resources/developers/search_api"),
    ("agudid_parse_api_doc", "https://accessgudid.nlm.nih.gov/resources/developers/parse_udi_api"),
    ("agudid_lookup_udi", "https://accessgudid.nlm.nih.gov/api/v3/devices/lookup.json?udi=(01)00643169718425(17)270331(10)9A12345"),
    ("agudid_lookup_di", "https://accessgudid.nlm.nih.gov/api/v3/devices/lookup.json?di=00643169718425"),
    ("agudid_search_desc", "https://accessgudid.nlm.nih.gov/api/v3/devices/search.json?deviceDescription=infusion%20pump"),
    ("agudid_search_desc_hits", "https://accessgudid.nlm.nih.gov/api/v3/devices/search.json?deviceDescription=infusion&pageSize=5"),
    # ---- openFDA device endpoints ----------------------------------------
    ("fda_510k", "https://api.fda.gov/device/510k.json?limit=1"),
    ("fda_pma", "https://api.fda.gov/device/pma.json?limit=1"),
    ("fda_reglist", "https://api.fda.gov/device/registrationlisting.json?limit=1"),
    ("fda_classification", "https://api.fda.gov/device/classification.json?limit=1"),
    ("fda_udi", "https://api.fda.gov/device/udi.json?limit=1"),
    # ---- Canada MDALL ----------------------------------------------------
    ("hc_device_json", "https://health-products.canada.ca/api/medical-device/device/?lang=en&type=json"),
    ("hc_licence_json", "https://health-products.canada.ca/api/medical-device/licence/?lang=en&type=json"),
    ("hc_licence_compact", "https://health-products.canada.ca/api/medical-device/licence/?lang=en&type=json&id=1"),
    # ---- Australia TGA ARTG ---------------------------------------------
    ("tga_home", "https://www.tga.gov.au"),
    ("datagov_artg_search", "https://data.gov.au/data/api/3/action/package_search?q=ARTG&rows=5"),
    # ---- EU EUDAMED ------------------------------------------------------
    ("eudamed_root", "https://ec.europa.eu/tools/eudamed/"),
    ("eudamed_api_guess", "https://ec.europa.eu/tools/eudamed/api/devices"),
    # ---- Japan PMDA ------------------------------------------------------
    ("pmda_home", "https://www.pmda.go.jp/english/"),
    # ---- Brazil ANVISA ---------------------------------------------------
    ("anvisa_dados", "https://dados.anvisa.gov.br/"),
    ("dadosgov_search", "https://dados.gov.br/api/publico/conjuntos-dados?nomeConjuntoDados=dispositivos"),
    # ---- robots.txt ------------------------------------------------------
    ("robots_agudid", "https://accessgudid.nlm.nih.gov/robots.txt"),
    ("robots_apifda", "https://api.fda.gov/robots.txt"),
    ("robots_hc", "https://health-products.canada.ca/robots.txt"),
    ("robots_tga", "https://www.tga.gov.au/robots.txt"),
    ("robots_eudamed", "https://ec.europa.eu/robots.txt"),
    ("robots_pmda", "https://www.pmda.go.jp/robots.txt"),
    ("robots_anvisa", "https://dados.anvisa.gov.br/robots.txt"),
]


def main() -> int:
    kept: list[dict] = []
    summary: list[dict] = []
    with make_client("regulatory-discovery-1", max_requests=40,
                     max_bytes_per_response=3_000_000, max_total_bytes=25_000_000,
                     rps=1.5) as c:
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
                rec.update({"outcome": "TRANSPORT_ERROR", "error": f"{type(exc).__name__}: {exc}"[:300]})
                summary.append(rec)
                print(json.dumps(rec, ensure_ascii=False))
                continue

            body = res.body
            rec.update({
                "status": res.status,
                "outcome": "OK" if res.ok else "HTTP_ERROR",
                "bytes": len(body),
                "sha256": res.content_hash,
                "content_type": res.headers.get("content-type"),
                "final_url": res.final_url,
            })
            # keep the body when it is a doc page or a failed/interesting response
            if name.startswith(("agudid_docs", "agudid_search_api", "agudid_parse_api")):
                fn = os.path.join(OUT, name + ".html")
                with open(fn, "wb") as fh:
                    fh.write(body)
                rec["saved"] = fn
            if not res.ok or len(body) < 4000:
                fn = os.path.join(OUT, name + ".txt")
                with open(fn, "wb") as fh:
                    fh.write(body)
                rec["saved"] = fn
            # rate-limit headers are first-class evidence
            rl = {k: v for k, v in res.headers.items()
                  if "ratelimit" in k or "rate-limit" in k or k in ("retry-after", "x-request-id")}
            if rl:
                rec["rate_limit_headers"] = rl
            summary.append(rec)
            kept.append(rec)
            print(json.dumps(rec, ensure_ascii=False))

        budget = c.budget_report()

    doc = {"generated_at": utc_now(), "budget": budget, "targets": summary}
    with open(os.path.join(OUT, "round1.json"), "w", encoding="utf-8", newline="\n") as fh:
        json.dump(doc, fh, indent=2, ensure_ascii=False)
        fh.write("\n")
    print("\nBUDGET:", json.dumps(budget, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
