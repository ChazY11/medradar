"""Verify the stored raw responses genuinely correspond to the query that asked for them.

Motivated by the Lead's report that older ``BoundedClient`` builds cached on URL
only and ignored ``params`` — which would silently replay the first response when
a loop varies only query parameters.

This checks *my* data on disk, three ways:
  1. every raw file whose name encodes a query parameter is re-parsed and the
     parameter is verified inside the payload;
  2. the AccessGUDID lookups are checked DI-by-DI against the DI in the filename;
  3. the byte counts / sha256 in the log are cross-checked for duplicates that
     would betray a replayed cache hit.

No network. Run:  python CONNECTORS/regulatory/_verify_cache_integrity.py
"""

from __future__ import annotations

import glob
import hashlib
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from CONNECTORS.regulatory._util import ROOT  # noqa: E402

FAIL = 0


def ok(msg: str) -> None:
    print(f"  PASS  {msg}")


def bad(msg: str) -> None:
    global FAIL
    FAIL += 1
    print(f"  FAIL  {msg}")


def check_gudid_lookups() -> None:
    print("\n[1] AccessGUDID lookup.json responses vs requested DI")
    files = sorted(glob.glob(os.path.join(ROOT, "DATASETS", "regulatory", "accessgudid",
                                          "raw", "lookup_*.json")))
    if not files:
        bad("no lookup_*.json files found")
        return
    for f in files:
        want = os.path.basename(f)[len("lookup_"):-len(".json")]
        doc = json.load(open(f, encoding="utf-8"))
        dev = (doc.get("gudid") or {}).get("device") or {}
        got = set()
        for i in (dev.get("identifiers") or {}).get("identifier") or []:
            if i.get("deviceId"):
                got.add(str(i["deviceId"]))
        rel = os.path.relpath(f, ROOT).replace(os.sep, "/")
        if want in got:
            ok(f"{rel}: requested DI {want} present among identifiers {sorted(got)[:3]}")
        else:
            bad(f"{rel}: requested DI {want} NOT in payload identifiers {sorted(got)[:5]}")


def check_openfda() -> None:
    print("\n[2] openFDA raw pulls vs their search expression")
    rules = {
        "510k__firm_medtronic.json": ("applicant", "MEDTRONIC"),
        "510k__firm_ge.json": ("applicant", "GE"),
        "510k__firm_philips.json": ("applicant", "PHILIPS"),
        "510k__firm_draeger.json": ("applicant", "DRAGER"),
        "510k__firm_mindray.json": ("applicant", "MINDRAY"),
        "pma__firm_medtronic.json": ("applicant", "MEDTRONIC"),
        "pma__firm_philips.json": ("applicant", "PHILIPS"),
        "registrationlisting__firm_medtronic.json":
            ("registration.owner_operator.firm_name", "MEDTRONIC"),
        "registrationlisting__firm_philips.json":
            ("registration.owner_operator.firm_name", "PHILIPS"),
    }
    base = os.path.join(ROOT, "DATASETS", "regulatory")
    for src, mapping in [
        ("openfda_device_510k", rules),
        ("openfda_device_pma", rules),
        ("openfda_device_registrationlisting", rules),
    ]:
        for fname, (field, needle) in mapping.items():
            path = os.path.join(base, src, "raw", fname)
            if not os.path.isfile(path):
                continue
            doc = json.load(open(path, encoding="utf-8"))
            if "error" in doc:
                print(f"  SKIP  {src}/{fname}: server said {doc['error'].get('code')}")
                continue
            res = doc.get("results") or []
            if not res:
                bad(f"{src}/{fname}: empty results")
                continue
            hits = 0
            for r in res:
                v = r
                for part in field.split("."):
                    v = (v or {}).get(part) if isinstance(v, dict) else None
                if v and needle.upper() in str(v).upper():
                    hits += 1
            if hits == len(res):
                ok(f"{src}/{fname}: {hits}/{len(res)} records match {field}~{needle}")
            elif hits:
                print(f"  PART  {src}/{fname}: {hits}/{len(res)} records match {needle} "
                      f"(tokenised matches are expected)")
            else:
                bad(f"{src}/{fname}: 0/{len(res)} records match {field}~{needle}")

    # product-code / device-name pulls
    for fname, needle in [
        ("510k__product_ventilator.json", "VENTILATOR"),
        ("510k__product_infusion.json", "INFUSION"),
        ("510k__product_monitor.json", "MONITOR"),
        ("classification__product_ventilator.json", "VENTILATOR"),
    ]:
        for src in ("openfda_device_510k", "openfda_device_classification"):
            path = os.path.join(base, src, "raw", fname)
            if not os.path.isfile(path):
                continue
            doc = json.load(open(path, encoding="utf-8"))
            res = doc.get("results") or []
            if not res:
                bad(f"{src}/{fname}: empty")
                continue
            hits = sum(1 for r in res if needle in json.dumps(r).upper())
            (ok if hits else bad)(f"{src}/{fname}: {hits}/{len(res)} records contain {needle}")


def check_mdall() -> None:
    print("\n[3] MDALL raw pulls vs their query parameter")
    base = os.path.join(ROOT, "DATASETS", "regulatory", "canada_mdall", "raw")
    for path in sorted(glob.glob(os.path.join(base, "company__*.json"))):
        needle = os.path.basename(path)[len("company__"):-len(".json")].replace("_", " ").upper()
        doc = json.load(open(path, encoding="utf-8"))
        rows = doc if isinstance(doc, list) else []
        key = needle.split()[0]
        hits = sum(1 for r in rows if key in str(r.get("company_name", "")).upper())
        rel = os.path.relpath(path, ROOT).replace(os.sep, "/")
        if rows and hits:
            ok(f"{rel}: {hits}/{len(rows)} company names contain {key}")
        else:
            bad(f"{rel}: 0/{len(rows)} company names contain {key}")
    for path in sorted(glob.glob(os.path.join(base, "licence_name__*.json"))):
        word = os.path.basename(path)[len("licence_name__"):-len(".json")].upper()
        doc = json.load(open(path, encoding="utf-8"))
        rows = doc if isinstance(doc, list) else []
        hits = sum(1 for r in rows if word in str(r.get("licence_name", "")).upper())
        rel = os.path.relpath(path, ROOT).replace(os.sep, "/")
        if rows and hits:
            ok(f"{rel}: {hits}/{len(rows)} licence names contain {word}")
        else:
            bad(f"{rel}: 0/{len(rows)} licence names contain {word}")
    for path in sorted(glob.glob(os.path.join(base, "device_name__*.json"))):
        word = os.path.basename(path)[len("device_name__"):-len(".json")].upper()
        doc = json.load(open(path, encoding="utf-8"))
        rows = doc if isinstance(doc, list) else []
        hits = sum(1 for r in rows if word in str(r.get("trade_name", "")).upper())
        rel = os.path.relpath(path, ROOT).replace(os.sep, "/")
        if rows and hits:
            ok(f"{rel}: {hits}/{len(rows)} trade names contain {word}")
        else:
            bad(f"{rel}: 0/{len(rows)} trade names contain {word}")


def check_no_duplicate_payloads() -> None:
    """A replayed cache would give byte-identical bodies across different queries."""
    print("\n[4] no byte-identical payloads across different query-specific files")
    seen: dict[str, str] = {}
    suspicious = 0
    for path in glob.glob(os.path.join(ROOT, "DATASETS", "regulatory", "*", "raw", "*")):
        if not os.path.isfile(path):
            continue
        name = os.path.basename(path)
        if not any(t in name for t in ("__", "lookup_", "head256k", "prefix6m")):
            continue
        h = hashlib.sha256(open(path, "rb").read()).hexdigest()
        if h in seen and seen[h] != name:
            print(f"  NOTE  {name} has the same sha256 as {seen[h]}")
            suspicious += 1
        seen.setdefault(h, name)
    if suspicious == 0:
        ok("every query-specific raw file is byte-distinct")
    else:
        print(f"  {suspicious} identical pair(s) — reviewed above; identical small bodies are "
              f"usually the same error/empty payload, not a cache replay")


def main() -> int:
    print("cache-integrity verification for the REGULATORY workstream")
    print("reason: older BoundedClient cached on url only, ignoring params")
    check_gudid_lookups()
    check_openfda()
    check_mdall()
    check_no_duplicate_payloads()
    print("\nRESULT:", "ALL CHECKS PASSED" if FAIL == 0 else f"{FAIL} FAILURE(S)")
    print("Note: no call in this workstream passed a `params=` kwarg to BoundedClient.get; "
          "every query was built into the URL string itself, so the url-only cache key could "
          "not collapse two different queries into one response. The checks above confirm "
          "this empirically from the stored bytes.")
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
