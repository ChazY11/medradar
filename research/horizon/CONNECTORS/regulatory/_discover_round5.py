"""Discovery round 5 — last size/shape questions before collection.

Run:  python CONNECTORS/regulatory/_discover_round5.py
"""

from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from hz.http import BudgetExceeded, ResponseTooLarge  # noqa: E402

from CONNECTORS.regulatory._util import ROOT, make_client, probe_size, utc_now  # noqa: E402

OUT = os.path.join(ROOT, "DATASETS", "regulatory", "_discovery")

GETS = [
    ("anvisa_consultas_index", "https://dados.anvisa.gov.br/dados/CONSULTAS/"),
]
SIZES = [
    ("size_gudid_monthly_oct2026",
     "https://accessgudid.nlm.nih.gov/release_files/download/gudid_monthly_update_october_2026.zip"),
    ("size_hc_devices_by_name",
     "https://health-products.canada.ca/api/medical-devices/device/?device_name=infusion&state=active&lang=en&type=json"),
    ("size_anvisa_tecnovigilancia", "https://dados.anvisa.gov.br/dados/DADOS_ABERTOS_TECNOVIGILANCIA.csv"),
]


def main() -> int:
    summary: list[dict] = []
    with make_client("regulatory-discovery-5", max_requests=8,
                     max_bytes_per_response=2_000_000, max_total_bytes=8_000_000,
                     rps=1.2) as c:
        for name, url in GETS:
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
            fn = os.path.join(OUT, name + ".html")
            with open(fn, "wb") as fh:
                fh.write(res.body)
            rec.update({"status": res.status, "outcome": "OK" if res.ok else "HTTP_ERROR",
                        "bytes": len(res.body), "sha256": res.content_hash, "saved": fn})
            summary.append(rec)
            print(json.dumps(rec, ensure_ascii=False))

        for name, url in SIZES:
            rec = {"name": name}
            rec.update(probe_size(c, url))
            summary.append(rec)
            print(json.dumps(rec, ensure_ascii=False))

        budget = c.budget_report()

    with open(os.path.join(OUT, "round5.json"), "w", encoding="utf-8", newline="\n") as fh:
        json.dump({"generated_at": utc_now(), "budget": budget, "targets": summary},
                  fh, indent=2, ensure_ascii=False)
        fh.write("\n")
    print("\nBUDGET:", json.dumps(budget, ensure_ascii=False)[:300])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
