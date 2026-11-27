"""Step 1b — download only a named subset of CIPO tables (budget control).

Used after the full download was stopped on purpose: ``PT_IPC_classification``
turned out to be >230 MB per range split, which is more disk and time than its
marginal value justifies this round. The small tables are still worth having.

    python CONNECTORS/patents/cipo_download_subset.py
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)

import requests  # noqa: E402

import cipo_canada as C  # noqa: E402
from hz.tls import complete_chain  # noqa: E402

RAW = os.path.join(ROOT, "DATASETS", "patents", "cipo_canada", "raw")
TLS_DIR = os.path.join(ROOT, "DATASETS", "_tls")

WANTED = [
    ("PT_priority_claim", "PT_priority_claim_1_to_2000000"),
    ("PT_priority_claim", "PT_priority_claim_2000001_to_4000000"),
]


def main() -> int:
    from cipo_download import resolve, pick

    os.makedirs(RAW, exist_ok=True)
    by_name = resolve()
    chain = complete_chain(C.BULK_HOST, TLS_DIR)
    if not chain.ok:
        print("TLS chain completion FAILED:", chain.error)
        return 2

    prov_path = os.path.join(RAW, "PROVENANCE.json")
    prov = json.load(open(prov_path, encoding="utf-8")) if os.path.isfile(prov_path) else {
        "source_id": C.SOURCE_ID, "files": []
    }
    prov.setdefault("skipped_by_budget", [])
    for table, needle in WANTED:
        meta = pick(by_name, needle)
        if not meta:
            print(f"MISSING {needle}")
            continue
        url = meta["url"]
        fname = os.path.basename(url.split("?")[0])
        dest = os.path.join(RAW, fname)
        if os.path.exists(dest):
            print(f"cached {fname}")
        else:
            with requests.get(url, verify=chain.bundle_path, timeout=300, stream=True) as r:
                r.raise_for_status()
                h = hashlib.sha256()
                got = 0
                with open(dest + ".part", "wb") as fh:
                    for chunk in r.iter_content(chunk_size=1 << 20):
                        if not chunk:
                            continue
                        fh.write(chunk)
                        h.update(chunk)
                        got += len(chunk)
                os.replace(dest + ".part", dest)
            print(f"fetched {fname} {got/1048576:.1f} MB")
            prov["files"] = [f for f in prov["files"] if f["file"] != fname]
            prov["files"].append(
                {"table": table, "file": fname, "url": url, "bytes": got,
                 "sha256": h.hexdigest(), "last_modified": meta.get("last_modified")}
            )
        with open(prov_path, "w", encoding="utf-8", newline="\n") as fh:
            json.dump(prov, fh, indent=2, ensure_ascii=False)
            fh.write("\n")

    prov.setdefault("skipped_by_budget", []).append(
        {
            "table": "PT_IPC_classification",
            "reason": ">230 MB per range split observed mid-download; stopped deliberately "
                      "to stay inside the round's disk/time budget",
            "measured_partial_bytes": None,
            "effect": "IPC/technology classification is absent for CIPO records; "
                      "medtech_ipc_subclasses is empty for cipo_canada and the records "
                      "carry MISSING_CLASSIFICATION",
        }
    )
    with open(prov_path, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(prov, fh, indent=2, ensure_ascii=False)
        fh.write("\n")
    print("files in provenance:", len(prov["files"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
