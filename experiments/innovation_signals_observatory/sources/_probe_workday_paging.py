"""Workday CXS pagination study: can the full posting population be enumerated lawfully?

The first bounded collection returned 40 postings while the site reports ~992. The
listing endpoint accepted two pages and then stopped, which is the difference
between "the company advertises 40 technical roles" and "we could only read 40".
This script measures the paging behaviour instead of guessing.
"""
from __future__ import annotations

import json
import sys
import time
import urllib.request

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")
BASE = "https://medtronic.wd1.myworkdayjobs.com"
TENANT, SITE = "medtronic", "MedtronicCareers"
LIST = f"{BASE}/wday/cxs/{TENANT}/{SITE}/jobs"


def post(body):
    data = json.dumps(body).encode()
    req = urllib.request.Request(LIST, data=data, method="POST",
                                headers={"User-Agent": UA, "Content-Type": "application/json",
                                         "Accept": "application/json"})
    t0 = time.monotonic()
    try:
        with urllib.request.urlopen(req, timeout=40) as r:
            payload = json.loads(r.read().decode())
            return r.status, payload, int((time.monotonic() - t0) * 1000)
    except urllib.error.HTTPError as e:
        return e.code, {"error": e.read().decode()[:200]}, int((time.monotonic() - t0) * 1000)
    except Exception as e:  # noqa: BLE001
        return None, {"error": f"{type(e).__name__}: {e}"}, int((time.monotonic() - t0) * 1000)


def summarize(tag, status, payload, ms):
    if isinstance(payload, dict) and "jobPostings" in payload:
        posts = payload["jobPostings"]
        print(f"{tag:44s} {status} total={payload.get('total')} n={len(posts)} ms={ms} "
              f"first={posts[0]['title'][:34] if posts else '-'}")
    else:
        print(f"{tag:44s} {status} {str(payload)[:120]} ms={ms}")
    return payload


def main() -> int:
    out = {}
    # A. what paging looks like without searchText
    for offset in (0, 20, 40, 60, 100, 500):
        st, p, ms = post({"appliedFacets": {}, "limit": 20, "offset": offset})
        out[f"nosearch_offset_{offset}"] = {"status": st, "total": p.get("total") if isinstance(p, dict) else None,
                                           "n": len(p.get("jobPostings", [])) if isinstance(p, dict) else 0}
        summarize(f"no searchText offset={offset}", st, p, ms)
        time.sleep(1.0)

    # B. does a broad searchText page through the population?
    for term in ("engineer", "a", "the"):
        st, p, ms = post({"appliedFacets": {}, "limit": 20, "offset": 0, "searchText": term})
        total = p.get("total") if isinstance(p, dict) else None
        summarize(f"searchText={term!r} offset=0", st, p, ms)
        if isinstance(p, dict) and total:
            for offset in (20, 40, total - 1):
                time.sleep(1.0)
                st2, p2, ms2 = post({"appliedFacets": {}, "limit": 20, "offset": max(0, offset), "searchText": term})
                summarize(f"searchText={term!r} offset={offset}", st2, p2, ms2)
        out[f"search_{term}"] = {"status": st, "total": total}
        time.sleep(1.0)

    # C. limit ceiling: does limit>20 work?
    for limit in (50, 100):
        st, p, ms = post({"appliedFacets": {}, "limit": limit, "offset": 0})
        summarize(f"no searchText limit={limit}", st, p, ms)
        out[f"limit_{limit}"] = {"status": st, "n": len(p.get("jobPostings", [])) if isinstance(p, dict) else 0}
        time.sleep(1.0)

    # D. empty searchText (the 500 we saw earlier), now with proper Accept
    st, p, ms = post({"appliedFacets": {}, "limit": 20, "offset": 0, "searchText": ""})
    summarize("empty searchText", st, p, ms)
    out["empty_search"] = {"status": st}

    with open(sys.argv[1], "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=2)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
