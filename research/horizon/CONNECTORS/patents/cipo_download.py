"""Step 1 — resolve and download CIPO patent bulk files (bounded, hashed).

Downloads only the tables the connector actually joins on. Every file is hashed
and recorded in PROVENANCE.json before it is used, so the ETL output can be tied
to the exact bytes received.

    python CONNECTORS/patents/cipo_download.py --list
    python CONNECTORS/patents/cipo_download.py
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import sys
import time
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)

import requests  # noqa: E402

import cipo_canada as C  # noqa: E402
from hz.tls import complete_chain  # noqa: E402

RAW = os.path.join(ROOT, "DATASETS", "patents", "cipo_canada", "raw")
TLS_DIR = os.path.join(ROOT, "DATASETS", "_tls")

# Table name -> substring that identifies its resource in the CKAN record.
# Two range splits per table (1-2M / 2-4M record ids); both are required for
# complete firm coverage, so neither is skipped.
WANTED = [
    ("PT_main", "PT_main_1_to_2000000"),
    ("PT_main", "PT_main_2000001_to_4000000"),
    ("PT_interested_party", "PT_interested_party_1_to_2000000"),
    ("PT_interested_party", "PT_interested_party_2000001_to_4000000"),
    ("PT_IPC_classification", "PT_IPC_classification_1_to_2000000"),
    ("PT_IPC_classification", "PT_IPC_classification_2000001_to_4000000"),
    ("PT_priority_claim", "PT_priority_claim_1_to_2000000"),
    ("PT_priority_claim", "PT_priority_claim_2000001_to_4000000"),
]


def resolve() -> dict[str, dict]:
    """Read the CKAN package record, with bounded backoff on 429/5xx."""
    last = None
    for attempt, wait_s in enumerate((0, 10, 30, 60)):
        if wait_s:
            time.sleep(wait_s)
        try:
            r = requests.get(
                C.CKAN_API,
                params={"id": C.CKAN_PACKAGE_ID},
                timeout=60,
                headers={"User-Agent": "MedRadar-HORIZON-001/1.0 (bounded research)"},
            )
            if r.status_code in (429, 500, 502, 503, 504):
                last = f"HTTP {r.status_code}"
                continue
            r.raise_for_status()
            pkg = r.json()["result"]
            by_name = {}
            for res in pkg["resources"]:
                name = res.get("name") or ""
                by_name[name] = {
                    "name": name,
                    "url": res.get("url"),
                    "format": res.get("format"),
                    "last_modified": res.get("last_modified"),
                    "size": res.get("size"),
                }
            return by_name
        except Exception as exc:
            last = f"{type(exc).__name__}: {exc}"[:200]
    raise RuntimeError(f"CKAN package_show failed after retries: {last}")


def pick(by_name: dict, needle: str) -> dict | None:
    for name, meta in by_name.items():
        if needle in name and meta.get("url"):
            return meta
    return None


def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--list", action="store_true", help="list resolved resources and exit")
    args = ap.parse_args(argv)

    os.makedirs(RAW, exist_ok=True)
    by_name = resolve()
    plan: list[tuple[str, dict]] = []
    for table, needle in WANTED:
        meta = pick(by_name, needle)
        print(f"{table:24} {needle:46} -> {'OK' if meta else 'MISSING'}")
        if meta:
            plan.append((table, meta))
    if args.list:
        return 0
    missing = len(WANTED) - len(plan)
    if missing:
        print(f"WARNING: {missing} expected resource(s) not resolvable")

    chain = complete_chain(C.BULK_HOST, TLS_DIR)
    if not chain.ok:
        print("TLS chain completion FAILED:", chain.error)
        return 2
    print("TLS chain completed:", chain.intermediates, "bundle:", chain.bundle_path)

    prov_path = os.path.join(RAW, "PROVENANCE.json")
    prov = {"source_id": C.SOURCE_ID, "ckan_package_id": C.CKAN_PACKAGE_ID,
            "licence": C.LICENCE_NAME, "licence_url": C.LICENCE_URL,
            "tls": {"leaf_subject": chain.leaf_subject, "leaf_issuer": chain.leaf_issuer,
                    "intermediates": chain.intermediates, "ai_uris": chain.ai_uris,
                    "note": "server omits intermediate; obtained from leaf AIA and "
                            "verified against platform roots (verification NOT disabled)"},
            "files": [], "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}

    for table, meta in plan:
        url = meta["url"]
        fname = os.path.basename(url.split("?")[0])
        dest = os.path.join(RAW, fname)
        if os.path.exists(dest) and os.path.getsize(dest) > 0:
            digest = hashlib.sha256()
            with open(dest, "rb") as fh:
                for chunk in iter(lambda: fh.read(1 << 20), b""):
                    digest.update(chunk)
            size = os.path.getsize(dest)
            print(f"cached  {fname:60} {size/1048576:8.1f} MB")
        else:
            t0 = time.time()
            got = 0
            with requests.get(url, verify=chain.bundle_path, timeout=300, stream=True) as r:
                r.raise_for_status()
                h = hashlib.sha256()
                with open(dest + ".part", "wb") as fh:
                    for chunk in r.iter_content(chunk_size=1 << 20):
                        if not chunk:
                            continue
                        fh.write(chunk)
                        h.update(chunk)
                        got += len(chunk)
                os.replace(dest + ".part", dest)
            size = got
            digest_sum = h.hexdigest()
            print(f"fetched {fname:60} {size/1048576:8.1f} MB  {time.time()-t0:6.1f}s")
            prov["files"].append(
                {"table": table, "file": fname, "url": url, "bytes": size,
                 "sha256": digest_sum, "last_modified": meta.get("last_modified")}
            )
            with open(prov_path, "w", encoding="utf-8", newline="\n") as fh:
                json.dump(prov, fh, indent=2, ensure_ascii=False)
                fh.write("\n")
            continue
        # rebuild hash for cached file
        h = hashlib.sha256()
        with open(dest, "rb") as fh:
            for chunk in iter(lambda: fh.read(1 << 20), b""):
                h.update(chunk)
        if not any(f["file"] == fname for f in prov["files"]):
            prov["files"].append(
                {"table": table, "file": fname, "url": url, "bytes": size,
                 "sha256": h.hexdigest(), "last_modified": meta.get("last_modified")}
            )
            with open(prov_path, "w", encoding="utf-8", newline="\n") as fh:
                json.dump(prov, fh, indent=2, ensure_ascii=False)
                fh.write("\n")

    total = sum(f["bytes"] for f in prov["files"])
    prov["total_bytes"] = total
    with open(prov_path, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(prov, fh, indent=2, ensure_ascii=False)
        fh.write("\n")
    print(f"total {total/1048576:.1f} MB across {len(prov['files'])} files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
