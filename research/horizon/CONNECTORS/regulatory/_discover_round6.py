"""Discovery round 6 — the last three unknown shapes.

Run:  python CONNECTORS/regulatory/_discover_round6.py
"""

from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from hz.http import BudgetExceeded, ResponseTooLarge  # noqa: E402

from CONNECTORS.regulatory._util import ROOT, make_client, utc_now  # noqa: E402

OUT = os.path.join(ROOT, "DATASETS", "regulatory", "_discovery")

TARGETS = [
    ("agudid_download_query", "https://accessgudid.nlm.nih.gov/download/query"),
    ("hc_devices_infusion",
     "https://health-products.canada.ca/api/medical-devices/device/?device_name=infusion&state=active&lang=en&type=json"),
    ("anvisa_produtos_index", "https://dados.anvisa.gov.br/dados/CONSULTAS/PRODUTOS/"),
]


def main() -> int:
    summary: list[dict] = []
    with make_client("regulatory-discovery-6", max_requests=6,
                     max_bytes_per_response=3_000_000, max_total_bytes=8_000_000,
                     rps=1.2) as c:
        for name, url in TARGETS:
            rec = {"name": name, "url": url}
            try:
                res = c.get(url)
            except BudgetExceeded as exc:
                rec.update({"outcome": "BUDGET_EXCEEDED", "error": str(exc)})
                summary.append(rec)
                break
            except (ResponseTooLarge, Exception) as exc:  # noqa: BLE001
                rec.update({"outcome": type(exc).__name__, "error": str(exc)[:200]})
                summary.append(rec)
                print(json.dumps(rec, ensure_ascii=False))
                continue
            ct = res.headers.get("content-type") or ""
            ext = ".json" if "json" in ct else (".html" if "html" in ct else ".txt")
            fn = os.path.join(OUT, name + ext)
            with open(fn, "wb") as fh:
                fh.write(res.body)
            rec.update({"status": res.status, "outcome": "OK" if res.ok else "HTTP_ERROR",
                        "bytes": len(res.body), "sha256": res.content_hash,
                        "content_type": ct, "saved": fn})
            summary.append(rec)
            print(json.dumps(rec, ensure_ascii=False))
        budget = c.budget_report()

    with open(os.path.join(OUT, "round6.json"), "w", encoding="utf-8", newline="\n") as fh:
        json.dump({"generated_at": utc_now(), "budget": budget, "targets": summary},
                  fh, indent=2, ensure_ascii=False)
        fh.write("\n")
    print("\nBUDGET:", json.dumps(budget, ensure_ascii=False)[:300])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
