#!/usr/bin/env python
"""Polite SEC documentation fetcher for MedRadar SCIENCE-001 evidence layer.

Usage:  python fetch.py manifest.json
Manifest: [{"id": "slug", "url": "https://...", "note": "why"}, ...]

Writes cached bytes to raw/<id>.<ext> and appends a record to raw/_meta.json.
Never writes outside evidence/sec_docs/.
"""
import hashlib, json, os, sys, time, io

import requests

UA = "MedRadar research science-001 (contact: research@medradar.invalid)"
HERE = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(os.path.dirname(HERE), "raw")
META = os.path.join(RAW, "_meta.json")
DELAY = 0.4  # ~2.5 req/s max


def load_meta():
    if os.path.exists(META):
        with open(META, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"records": []}


def save_meta(m):
    with open(META, "w", encoding="utf-8") as f:
        json.dump(m, f, indent=2)


def ext_for(ctype, url):
    c = (ctype or "").lower()
    if "pdf" in c:
        return "pdf"
    if "json" in c:
        return "json"
    if "xml" in c or "atom" in c or "rss" in c:
        return "xml"
    if "text/plain" in c:
        return "txt"
    if "html" in c:
        return "html"
    if url.lower().endswith(".pdf"):
        return "pdf"
    return "bin"


def main():
    man = json.load(open(sys.argv[1], "r", encoding="utf-8"))
    meta = load_meta()
    done = {r["id"] for r in meta["records"]}
    s = requests.Session()
    s.headers.update({
        "User-Agent": UA,
        "Accept": "*/*",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate",
    })
    for item in man:
        iid, url = item["id"], item["url"]
        if iid in done:
            print(f"SKIP (cached) {iid}")
            continue
        rec = {"id": iid, "requested_url": url, "note": item.get("note", "")}
        try:
            t0 = time.time()
            resp = s.get(url, timeout=60, allow_redirects=True)
            el = time.time() - t0
            ext = ext_for(resp.headers.get("Content-Type"), resp.url)
            fn = f"{iid}.{ext}"
            path = os.path.join(RAW, fn)
            with open(path, "wb") as f:
                f.write(resp.content)
            rec.update({
                "status": resp.status_code,
                "final_url": resp.url,
                "redirect_chain": [h.headers.get("Location") for h in resp.history],
                "content_type": resp.headers.get("Content-Type"),
                "content_length": len(resp.content),
                "sha256": hashlib.sha256(resp.content).hexdigest(),
                "file": fn,
                "retrieved_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "elapsed_s": round(el, 2),
                "last_modified": resp.headers.get("Last-Modified"),
                "server": resp.headers.get("Server"),
            })
            print(f"{resp.status_code} {iid} -> {fn} ({len(resp.content)} bytes, {el:.1f}s)")
        except Exception as e:
            rec.update({
                "status": None,
                "error": f"{type(e).__name__}: {e}",
                "retrieved_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            })
            print(f"ERROR {iid}: {type(e).__name__}: {e}")
        meta["records"].append(rec)
        save_meta(meta)
        time.sleep(DELAY)


if __name__ == "__main__":
    main()
