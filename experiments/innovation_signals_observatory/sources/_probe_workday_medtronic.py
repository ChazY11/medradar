"""Workday CXS probe: confirm which public endpoints yield postings + descriptions.

Writes small JSON artifacts and prints a one-line summary per probe.
"""
from __future__ import annotations

import json
import sys
import urllib.request

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
BASE = "https://medtronic.wd1.myworkdayjobs.com"
TENANT, SITE = "medtronic", "MedtronicCareers"


def req(url, method="GET", body=None, accept="application/json"):
    headers = {"User-Agent": UA, "Accept": accept, "Content-Type": "application/json"}
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(r, timeout=40) as resp:
            raw = resp.read(600_000)
            return resp.status, resp.headers.get("Content-Type"), raw.decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.headers.get("Content-Type") if e.headers else None, e.read(4000).decode("utf-8", "replace")
    except Exception as e:  # noqa
        return None, None, f"{type(e).__name__}: {e}"


def main() -> int:
    out = {}
    cxs = f"{BASE}/wday/cxs/{TENANT}/{SITE}/jobs"

    # 1. list without searchText
    st, ct, body = req(cxs, "POST", {"appliedFacets": {}, "limit": 5, "offset": 0})
    ok = st == 200 and body.strip().startswith("{")
    out["list_no_search"] = {"status": st, "ok_json": ok, "head": body[:300]}
    print("list_no_search", st, "json" if ok else body[:120].replace("\n", " "))

    # 2. list with a neutral searchText that matches everything common ("a")
    st, ct, body = req(cxs, "POST", {"appliedFacets": {}, "limit": 20, "offset": 0, "searchText": "engineer"})
    total = None
    sample = {}
    if st == 200:
        try:
            d = json.loads(body)
            total = d.get("total")
            posts = d.get("jobPostings") or []
            sample = {"total": total, "n": len(posts), "first": posts[0] if posts else None}
        except Exception as e:  # noqa
            sample = {"parse_error": str(e)}
    out["list_search_engineer"] = {"status": st, "sample": sample}
    print("list_search_engineer", st, total)

    # 3. job detail by externalPath (the SPA's own detail endpoint)
    ext = "/job/Fridley-Minnesota-United-States-of-America/Senior-Principal-Robotics---AMR-Automation-Platforms-Engineer_R73737-1"
    st, ct, body = req(f"{BASE}/wday/cxs/{TENANT}/{SITE}{ext}")
    detail_ok = st == 200 and body.strip().startswith("{")
    out["detail_cxs"] = {"status": st, "ok_json": detail_ok}
    if detail_ok:
        d = json.loads(body)
        info = d.get("jobPostingInfo") or {}
        out["detail_cxs"]["keys"] = sorted(info.keys())
        out["detail_cxs"]["startDate"] = info.get("startDate")
        out["detail_cxs"]["postedOn"] = info.get("postedOn")
        out["detail_cxs"]["desc_len"] = len(info.get("jobDescription") or "")
        out["detail_cxs"]["title"] = info.get("title")
        out["detail_cxs"]["jobReqId"] = info.get("jobReqId")
        out["detail_cxs"]["country"] = ((info.get("jobLocation") or {}).get("country") or {}).get("descriptor")
        out["detail_cxs"]["location"] = info.get("location")
        out["detail_cxs"]["timeType"] = info.get("timeType")
        out["detail_cxs"]["desc_head"] = (info.get("jobDescription") or "")[:300]
        print("detail_cxs", st, "startDate=", info.get("startDate"), "postedOn=", info.get("postedOn"),
              "desc_len=", out["detail_cxs"]["desc_len"], "req=", info.get("jobReqId"))
    else:
        print("detail_cxs", st, body[:150].replace("\n", " "))

    # 4. job page HTML: does it carry schema.org JobPosting JSON-LD (the public publishing contract)?
    page = f"{BASE}/{SITE}{ext}"
    st, ct, body = req(page, accept="text/html,application/xhtml+xml")
    import re
    blocks = re.findall(r'<script[^>]+application/ld\+json[^>]*>(.*?)</script>', body or "", re.S | re.I)
    found = []
    for b in blocks:
        try:
            d = json.loads(b)
        except Exception:
            continue
        items = d if isinstance(d, list) else [d]
        for it in items:
            if isinstance(it, dict) and it.get("@type") in ("JobPosting", ["JobPosting"]):
                found.append({k: it.get(k) for k in ("@type", "title", "datePosted", "validThrough", "employmentType",
                                                    "hiringOrganization", "jobLocation", "identifier")})
                desc = it.get("description") or ""
                found[-1]["description_len"] = len(desc)
    out["page_jsonld"] = {"status": st, "content_type": ct, "n_ld_blocks": len(blocks), "jobposting": found}
    print("page_jsonld", st, "ld_blocks=", len(blocks), "jobposting=", len(found),
          "datePosted=", found[0]["datePosted"] if found else None,
          "desc_len=", found[0]["description_len"] if found else None)

    # 5. sitemap: how many posting URLs, and does it carry lastmod?
    st, ct, body = req(f"{BASE}/{SITE}/siteMap.xml", accept="application/xml,text/xml")
    locs = re.findall(r"<loc>([^<]+)</loc>", body or "")
    lastmods = re.findall(r"<lastmod>([^<]+)</lastmod>", body or "")
    reqs = sorted({m.group(0) for m in re.finditer(r"_R\d+(?:-\d+)?", " ".join(locs))})
    out["sitemap"] = {"status": st, "n_locs": len(locs), "n_lastmod": len(lastmods), "n_req_ids": len(reqs),
                      "sample_loc": locs[0] if locs else None, "sample_lastmod": lastmods[0] if lastmods else None}
    print("sitemap", st, "locs=", len(locs), "lastmod=", len(lastmods), "reqids=", len(reqs))

    with open(sys.argv[1], "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=2)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
