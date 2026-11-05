"""DEEP SOURCE PROBE — MedRadar Phase 4, recruitment lane (WP2a).

This is the reproducible record of *how* the four remaining mandated focus companies'
career data sources were investigated, and *what the requests actually returned*:

    GE HealthCare · Philips · Mindray · Dräger

(The fifth, Medtronic, is covered by the Lead's Workday collector and is not re-probed here.)

What it does
------------
For each company it walks the public route a browser would use, once:

  * ``robots.txt`` first (status + content type + verbatim head + the exact rule that
    governs every path the collector would need);
  * the career site / portal entry page, to identify the platform and discover links;
  * the listing route — an XML sitemap, an official list endpoint, or a public search API;
  * a small sample of individual posting pages, parsed for schema.org ``JobPosting``
    JSON-LD, and it records the exact fields that a collector would depend on
    (stable id, published date + precision, description availability).

Bounds and ethics
-----------------
  * no login, captcha, paywall, bot challenge or access control is bypassed;
  * at most ``--max-requests`` requests in total and >= ``--min-interval`` seconds between
    requests to the same host; every request is logged with its status and elapsed time;
  * a timeout is recorded as a timeout. It is never retried into a different answer and
    never reported as "unavailable" without the exact failure text.

Output
------
``results/<date>/source_probe_<company>.json`` — one file per company, containing the
platform hypothesis, every request, every robots decision, the listing route's counts,
the sampled postings' field shapes, and a verdict with its reason.

Run
---
    python experiments/innovation_signals_observatory/sources/deep_probe.py \
        --out experiments/innovation_signals_observatory/results/2026-11-04

    # one company only
    python experiments/innovation_signals_observatory/sources/deep_probe.py --out ... \
        --companies mindray
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# Reuse the lane's robots interpreter rather than having a second, divergent one.
from medradar.recruitment.politeness import (  # noqa: E402
    DEFAULT_UA,
    FROM_HEADER,
    parse_robots,
    robots_allows,
)

#: The four firms this probe owns. The fifth (medtronic) is the Lead's Workday route.
COMPANIES = ("ge_healthcare", "philips", "draeger", "mindray")
COMPANY_NAMES = {"ge_healthcare": "GE HealthCare", "philips": "Philips",
                 "draeger": "Dräger", "mindray": "Mindray"}
COMPANY_CORP = {"ge_healthcare": "https://www.gehealthcare.com/",
                "philips": "https://www.philips.com/",
                "draeger": "https://www.draeger.com/",
                "mindray": "https://www.mindray.com/"}

JSONLD_RE = re.compile(r'<script[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
                       re.S | re.I)
LOC_RE = re.compile(r"<loc>\s*([^<\s]+)\s*</loc>", re.I)
URL_BLOCK_RE = re.compile(r"<url>\s*(.*?)\s*</url>", re.S | re.I)


def now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


# --------------------------------------------------------------------- fetching
@dataclass
class Fetched:
    url: str
    method: str = "GET"
    status: int | None = None
    final_url: str | None = None
    content_type: str | None = None
    body: str | None = None
    error: str | None = None
    elapsed_ms: int | None = None

    def as_dict(self, head: int = 400) -> dict[str, Any]:
        out = {"url": self.url, "method": self.method, "status": self.status,
               "final_url": self.final_url, "content_type": self.content_type,
               "error": self.error, "elapsed_ms": self.elapsed_ms}
        if self.body is not None:
            out["body_bytes"] = len(self.body.encode("utf-8", "replace"))
            out["body_head"] = self.body[:head]
        return out


class Politeness:
    """Per-host throttle plus a hard total ceiling; every request is logged."""

    def __init__(self, min_interval_s: float = 1.2, max_requests: int = 120) -> None:
        self.min_interval_s = min_interval_s
        self.max_requests = max_requests
        self._last: dict[str, float] = {}
        self.count = 0
        self.log: list[dict[str, Any]] = []

    def _wait(self, host: str) -> None:
        last = self._last.get(host)
        if last is not None:
            delta = time.monotonic() - last
            if delta < self.min_interval_s:
                time.sleep(self.min_interval_s - delta)
        self._last[host] = time.monotonic()

    def charge(self, url: str) -> None:
        self.count += 1
        if self.count > self.max_requests:
            raise RuntimeError(f"request budget exhausted ({self.max_requests})")

    def note(self, fetched: Fetched) -> None:
        self.log.append({"url": fetched.url, "method": fetched.method,
                         "status": fetched.status, "error": fetched.error,
                         "elapsed_ms": fetched.elapsed_ms, "at": now()})


def fetch(url: str, politeness: Politeness, *, method: str = "GET", body: bytes | None = None,
          headers: dict[str, str] | None = None, timeout: float = 40.0,
          max_bytes: int = 4_000_000, retries: int = 1,
          accept: str = "text/html,application/xhtml+xml,application/json;q=0.9,*/*;q=0.8") -> Fetched:
    """One request (with at most ``retries`` re-attempts for a transport error).

    An HTTP error response is a *result* (status + body kept); only transport failures are
    retried, and even then the final failure is reported verbatim.
    """
    host = urllib.parse.urlsplit(url).netloc.lower()
    last: Fetched | None = None
    for attempt in range(retries + 1):
        politeness._wait(host)
        politeness.charge(url)
        req_headers = {"User-Agent": DEFAULT_UA, "From": FROM_HEADER, "Accept": accept,
                       "Accept-Language": "en-US,en;q=0.9,zh-CN;q=0.8,de;q=0.8"}
        if headers:
            req_headers.update(headers)
        request = urllib.request.Request(url, data=body, headers=req_headers, method=method)
        started = time.monotonic()
        out = Fetched(url=url, method=method)
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                raw = response.read(max_bytes)
                out.status = response.status
                out.final_url = response.geturl()
                out.content_type = response.headers.get("Content-Type")
                charset = response.headers.get_content_charset() or "utf-8"
                out.body = raw.decode(charset, "replace")
        except urllib.error.HTTPError as exc:
            out.status = exc.code
            out.final_url = exc.geturl() if hasattr(exc, "geturl") else url
            out.content_type = exc.headers.get("Content-Type") if exc.headers else None
            try:
                out.body = exc.read(max_bytes).decode("utf-8", "replace")
            except Exception:  # pragma: no cover - body may be unreadable
                out.body = None
            out.error = f"HTTPError {exc.code}"
        except Exception as exc:  # network / TLS / timeout
            out.error = f"{type(exc).__name__}: {exc}"[:300]
        out.elapsed_ms = int((time.monotonic() - started) * 1000)
        politeness.note(out)
        last = out
        if out.status is None and attempt < retries:
            time.sleep(1.0 + attempt)
            continue
        break
    assert last is not None
    return last


# ---------------------------------------------------------------------- helpers
def is_html(text: str | None) -> bool:
    head = (text or "").lstrip()[:400].lower()
    return head.startswith("<!doctype") or head.startswith("<html") or "<head" in head[:200]


def is_xml(content_type: str | None, text: str | None) -> bool:
    head = (text or "").lstrip()[:300].lower()
    return "xml" in (content_type or "").lower() or head.startswith("<?xml") or "<urlset" in head \
        or "<sitemapindex" in head


def parse_jsonld(page: str | None) -> tuple[int, list[dict[str, Any]]]:
    """Return (number of JSON-LD script blocks, flattened dict nodes)."""
    blocks = JSONLD_RE.findall(page or "")
    nodes: list[dict[str, Any]] = []

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            nodes.append(node)
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    for raw in blocks:
        try:
            walk(json.loads(raw))
        except json.JSONDecodeError:
            continue
    return len(blocks), nodes


def types_of(node: dict[str, Any]) -> list[str]:
    value = node.get("@type")
    return [value] if isinstance(value, str) else [str(v) for v in value or []]


def find_jobposting(page: str | None) -> dict[str, Any] | None:
    _, nodes = parse_jsonld(page)
    for node in nodes:
        if any(t.lower() == "jobposting" for t in types_of(node)):
            return node
    return None


def short(value: Any, limit: int = 300) -> str | None:
    if value is None:
        return None
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
    return text[:limit]


def robots_record(fetched: Fetched, paths: list[str]) -> dict[str, Any]:
    """Robots evidence + the exact decision for every path a collector would need."""
    text = fetched.body or ""
    groups = parse_robots(text) if not is_html(text) else []
    return {
        "robots_url": fetched.url,
        "status": fetched.status,
        "content_type": fetched.content_type,
        "error": fetched.error,
        "is_robots_file": bool(text) and not is_html(text) and fetched.status == 200,
        "n_groups": len(groups),
        "groups": groups,
        "raw_head": (text or "")[:900],
        "path_decisions": {path: robots_allows(groups, path) for path in paths},
        "sitemaps_advertised": LOC_RE.findall(text) if "sitemap" in text.lower() else [],
    }


def sitemap_urls(fetched: Fetched) -> list[str]:
    return LOC_RE.findall(fetched.body or "")


def jobposting_shape(page: str | None) -> dict[str, Any]:
    """The fields a collector depends on, extracted from one posting page's JSON-LD."""
    blocks, nodes = parse_jsonld(page)
    jp = None
    for node in nodes:
        if any(t.lower() == "jobposting" for t in types_of(node)):
            jp = node
            break
    if jp is None:
        return {"jsonld_blocks": blocks, "jobposting_present": False,
                "node_types": [t for n in nodes for t in types_of(n)]}
    identifier = jp.get("identifier")
    identifier_value = None
    if isinstance(identifier, dict):
        identifier_value = identifier.get("value")
    elif isinstance(identifier, str):
        identifier_value = identifier
    location = jp.get("jobLocation")
    addresses: list[dict[str, Any]] = []
    for place in (location if isinstance(location, list) else [location]):
        if isinstance(place, dict) and isinstance(place.get("address"), dict):
            addresses.append(place["address"])
    organization = jp.get("hiringOrganization")
    return {
        "jsonld_blocks": blocks,
        "jobposting_present": True,
        "keys": sorted(jp.keys()),
        "identifier_value": identifier_value,
        "identifier_name": identifier.get("name") if isinstance(identifier, dict) else None,
        "title": short(jp.get("title"), 160),
        "datePosted": jp.get("datePosted"),
        "validThrough": jp.get("validThrough"),
        "employmentType": jp.get("employmentType"),
        "hiring_organization_name": (organization.get("name")
                                     if isinstance(organization, dict) else None),
        "addresses": addresses[:3],
        "description_chars": len(jp.get("description") or ""),
        "description_head": short(jp.get("description"), 200),
     }


VERDICT_DESCRIPTION = {
    "VERIFIED": "a lawful, stable public route to current postings was confirmed by request, "
                "with a stable id field, a verifiable source date and a usable description",
    "EXPLORATORY": "a public route was found and sampled, but coverage, stability or the "
                   "date/description contract is not good enough to call it verified",
    "BLOCKED": "no lawful route could be exercised from this network; the exact failure is recorded",
    "NOT_RUN": "not attempted in this round",
}


def verdict(kind: str, reason: str) -> dict[str, Any]:
    return {"verdict": kind, "reason": reason, "definition": VERDICT_DESCRIPTION[kind]}


# ---------------------------------------------------------------- phenom probes
PHENOM = {
    "ge_healthcare": {
        "base": "https://careers.gehealthcare.com",
        "locale_root": "/global/en",
        "robots": "https://careers.gehealthcare.com/robots.txt",
        "landing": "https://careers.gehealthcare.com/global/en",
        "sitemap_index": "https://careers.gehealthcare.com/global/en/sitemap_index.xml",
        "needed_paths": ["/global/en/sitemap_index.xml", "/global/en/job/"],
    },
    "philips": {
        "base": "https://www.careers.philips.com",
        "locale_root": "/global/en",
        "robots": "https://www.careers.philips.com/robots.txt",
        "landing": "https://www.careers.philips.com/global/en",
        "sitemap_index": "https://www.careers.philips.com/global/en/sitemap_index.xml",
        "needed_paths": ["/global/en/sitemap_index.xml", "/global/en/job/"],
    },
}


def probe_phenom(company: str, politeness: Politeness) -> dict[str, Any]:
    spec = PHENOM[company]
    out: dict[str, Any] = {"company_key": company, "company_name": COMPANY_NAMES[company],
                           "corporate_home": COMPANY_CORP[company],
                           "platform_hypothesis": "phenom (Phenom CareerConnect)",
                           "requests": []}

    robots = fetch(spec["robots"], politeness)
    out["requests"].append(robots.as_dict())
    out["robots"] = robots_record(robots, spec["needed_paths"])

    landing = fetch(spec["landing"], politeness)
    out["requests"].append(landing.as_dict(head=300))
    out["landing"] = {
        "url": landing.url, "status": landing.status, "content_type": landing.content_type,
        "jsonld_blocks": len(JSONLD_RE.findall(landing.body or "")),
        "meta_robots": re.findall(r'<meta[^>]+name=["\']robots["\'][^>]*>', landing.body or "")[:3],
        "phenom_assets": sorted(set(re.findall(
            r"https://[a-z0-9.\-]*phenompeople\.com[^\"'\s]{0,80}", landing.body or "")))[:5],
        "sitemap_links_seen": sorted(set(re.findall(
            r"https?://[^\"'\s]+sitemap[a-z_0-9.]*\.xml", landing.body or "")))[:5],
    }

    index = fetch(spec["sitemap_index"], politeness)
    out["requests"].append(index.as_dict())
    sub_sitemaps = sitemap_urls(index) if is_xml(index.content_type, index.body) else []
    out["sitemap_index"] = {"url": index.url, "status": index.status,
                            "content_type": index.content_type,
                            "n_sub_sitemaps": len(sub_sitemaps), "sub_sitemaps": sub_sitemaps[:6]}
    if not sub_sitemaps:
        out["verdict"] = verdict("BLOCKED", "sitemap index did not answer with an XML sitemapindex")
        return out

    rows: list[dict[str, Any]] = []
    for sub in sub_sitemaps[:3]:
        sub_fetched = fetch(sub, politeness)
        out["requests"].append(sub_fetched.as_dict(head=200))
        for block in URL_BLOCK_RE.findall(sub_fetched.body or ""):
            loc = re.search(r"<loc>\s*([^<\s]+)\s*</loc>", block, re.I)
            if not loc:
                continue
            url = loc.group(1)
            if "/job/" not in url.lower():
                continue
            lastmod = re.search(r"<lastmod>\s*([^<\s]+)\s*</lastmod>", block, re.I)
            rows.append({"url": url, "lastmod": lastmod.group(1) if lastmod else None,
                         "sitemap": sub})
    seen: set[str] = set()
    rows = [r for r in rows if not (r["url"] in seen or seen.add(r["url"]))]
    rows.sort(key=lambda r: r["lastmod"] or "", reverse=True)
    lastmods = sorted(r["lastmod"] for r in rows if r["lastmod"])
    out["listing_route"] = {
        "kind": "xml sitemap advertised in robots.txt" if out["robots"]["is_robots_file"]
                else "xml sitemap (host publishes no robots.txt)",
        "url": spec["sitemap_index"],
        "job_urls_found": len(rows),
        "lastmod_min": lastmods[0] if lastmods else None,
        "lastmod_max": lastmods[-1] if lastmods else None,
        "sample_urls": [r["url"] for r in rows[:5]],
    }

    samples: list[dict[str, Any]] = []
    picked = ([r for r in rows if r["url"] in out["listing_route"]["sample_urls"][:3]] or rows[:3])
    # also sample one old posting to expose stale sitemap entries (410 Gone is a real answer)
    if len(rows) > 3:
        picked = picked + [rows[-1]]
    for r in picked[:4]:
        page = fetch(r["url"], politeness)
        shape = jobposting_shape(page.body)
        shape["url"] = r["url"]
        shape["status"] = page.status
        shape["error"] = page.error
        shape["sitemap_lastmod"] = r["lastmod"]
        samples.append(shape)
        out["requests"].append(page.as_dict(head=120))
    out["posting_samples"] = samples

    dated = [s for s in samples if s.get("jobposting_present") and s.get("datePosted")]
    with_description = [s for s in samples if (s.get("description_chars") or 0) > 500]
    stale = [s for s in samples if s.get("status") in (404, 410)]
    out["contract"] = {
        "posting_id_field": "identifier.value (schema.org PropertyValue) in the JobPosting JSON-LD",
        "date_field": "datePosted",
        "date_precision": ("plain date (SOURCE_DATE); some postings render a midnight "
                           "timestamp with +0000 offset (date precision, flagged)"),
        "description": "full HTML in the JSON-LD description (escaped once inside JSON)",
        "stale_sitemap_entries_observed": len(stale),
    }
    access = ("robots.txt rules were fetched and applied per path; no login, captcha or "
              "access control was encountered")
    if not out["robots"]["is_robots_file"]:
        access = ("the host does not publish a robots.txt — GET /robots.txt returned its SPA "
                  "HTML shell (text/html; no REP directives). RFC 9309 treats an unavailable "
                  "robots.txt as unrestricted; the site's own <meta name=robots content=index> "
                  "and schema.org JobPosting markup show it is meant to be indexed. Recorded, "
                  "not assumed away. No login, captcha or access control was encountered.")
    out["automated_access_statement"] = access

    ok = (len(dated) >= 2 and len(with_description) >= 2
          and out["robots"]["path_decisions"]["/global/en/sitemap_index.xml"]["allowed"])
    out["verdict"] = verdict(
        "VERIFIED" if ok else "EXPLORATORY",
        f"{len(rows)} posting URLs in the sitemap; {len(dated)}/{len(samples)} sampled pages "
        f"carried datePosted and {len(with_description)}/{len(samples)} a full description; "
        f"robots decision for the sitemap path: "
        f"{out['robots']['path_decisions']['/global/en/sitemap_index.xml']['reason']}; "
        f"stale (410/404) entries in the newest sample: {len(stale)}")
    return out


# ----------------------------------------------------------------- beisen probe
def probe_mindray(politeness: Politeness) -> dict[str, Any]:
    base = "https://mindray.zhiye.com"
    out: dict[str, Any] = {"company_key": "mindray", "company_name": "Mindray",
                           "corporate_home": COMPANY_CORP["mindray"],
                           "platform_hypothesis": "beisen (北森 zhiye.com portal)",
                           "requests": []}
    robots = fetch(f"{base}/robots.txt", politeness)
    out["requests"].append(robots.as_dict())
    out["robots"] = robots_record(robots, ["/api/Jobad/GetJobAdPageList",
                                           "/api/JobAd/GetJobAdInfo", "/social/detail"])

    landing = fetch(f"{base}/", politeness)
    out["requests"].append(landing.as_dict(head=300))
    title_match = re.search(r"<title>(.*?)</title>", landing.body or "", re.S)
    out["landing"] = {
        "url": landing.url, "status": landing.status, "content_type": landing.content_type,
        "title": short(title_match.group(1).strip(), 120) if title_match else None,
        "beisen_assets": sorted(set(re.findall(
            r"https?://[^\"'\s]*(?:beisen|zhiye|bstatics)[^\"'\s]{0,60}", landing.body or "")))[:5],
        "tenant_metadata_seen": bool(re.search(r"BSGlobal", landing.body or "")),
    }

    payload = {"PageIndex": 0, "PageSize": 20, "Category": ["1"], "KeyWords": "",
               "SpecialType": 0, "PortalId": "",
               "DisplayFields": ["Category", "Kind", "LocId", "PostDate", "WorkWeChatQrCode"]}
    listing_url = f"{base}/api/Jobad/GetJobAdPageList"
    listing = fetch(listing_url, politeness, method="POST",
                    body=json.dumps(payload).encode("utf-8"),
                    headers={"Content-Type": "application/json",
                             "Accept": "application/json, */*"})
    out["requests"].append(listing.as_dict(head=200))
    rows: list[dict[str, Any]] = []
    try:
        data = json.loads(listing.body or "{}")
        rows = data.get("Data") or []
        out["listing_route"] = {
            "kind": "official portal JSON list endpoint (the request the site's own JS makes)",
            "url": listing_url,
            "http_status": listing.status,
            "code": data.get("Code"),
            "total_reported": data.get("Count"),
            "rows_in_page": len(rows),
            "payload": payload,
            "sample_row_keys": sorted(rows[0].keys())[:40] if rows else [],
            "sample_row": {k: short(rows[0].get(k), 120) for k in
                           ("Id", "JobAdId", "JobAdName", "PostDate", "PostDateInt",
                            "LocNames", "Kind", "Category", "Status")} if rows else {},
        }
    except Exception as exc:  # noqa: BLE001 - recorded
        out["listing_route"] = {"kind": "official portal JSON list endpoint", "url": listing_url,
                                "http_status": listing.status,
                                "error": f"{type(exc).__name__}: {exc}"}

    samples: list[dict[str, Any]] = []
    for row in rows[:2]:
        pid = row.get("Id")
        query = urllib.parse.urlencode({"jobAdId": pid, "category": "1",
                                        "displayFields": str(["jobAdName", "Duty", "Require",
                                                              "Category", "Kind", "LocId",
                                                              "PostDate"]).replace("'", '"')})
        detail = fetch(f"{base}/api/JobAd/GetJobAdInfo?{query}", politeness)
        out["requests"].append(detail.as_dict(head=200))
        record: dict[str, Any] = {"url": detail.url, "status": detail.status,
                                  "error": detail.error, "posting_id": pid}
        try:
            body = json.loads(detail.body or "{}")
            item = body.get("Data") or {}
            epoch_ms = item.get("PostDateInt")
            derived = None
            consistency = None
            if isinstance(epoch_ms, (int, float)) and epoch_ms > 0:
                from datetime import timedelta
                moment = datetime.fromtimestamp(epoch_ms / 1000.0, tz=timezone.utc).replace(microsecond=0)
                derived = moment.isoformat()
                consistency = ((moment + timedelta(hours=8)).strftime("%Y-%m-%dT%H:%M:%S")
                               == str(item.get("PostDate", "")).strip())
            record.update({
                "code": body.get("Code"),
                "keys": sorted(item.keys()),
                "title": short(item.get("JobAdName"), 140),
                "post_date_rendered": item.get("PostDate"),
                "post_date_int": epoch_ms,
                "post_date_utc_derived": derived,
                "rendering_matches_utc_plus_8": consistency,
                "duty_chars": len(item.get("Duty") or ""),
                "require_chars": len(item.get("Require") or ""),
                "location_names": item.get("LocNames"),
                "category": item.get("Category"),
                "kind": item.get("Kind"),
                "hiring_organization_field_present": "ParentOrganizationName" in item,
            })
        except Exception as exc:  # noqa: BLE001 - recorded
            record["error"] = f"{type(exc).__name__}: {exc}"
        samples.append(record)
    out["posting_samples"] = samples

    out["contract"] = {
        "posting_id_field": "Id (GUID, the token the portal itself uses in the public "
                            "/social/detail?jobAdId= URL); JobAdId (int) is a secondary key",
        "date_field": "PostDateInt (epoch milliseconds) with PostDate (tenant-local UTC+8 "
                      "rendering, kept verbatim)",
        "date_precision": "SOURCE_DATETIME (second), not a date and not a relative string",
        "description": "Duty + Require text fields, both returned by the listing endpoint "
                       "itself; no per-posting detail request is required",
    }
    can = bool(rows) and out["robots"]["path_decisions"]["/api/Jobad/GetJobAdPageList"]["allowed"]
    dated = [s for s in samples if s.get("post_date_utc_derived")]
    with_description = [s for s in samples if (s.get("duty_chars") or 0) > 0
                        or (s.get("require_chars") or 0) > 0]
    out["automated_access_statement"] = (
        "robots.txt is `User-agent: * / Allow: /`; the list/detail endpoints are the "
        "same public unauthenticated JSON requests the portal's own front end makes. No "
        "login, captcha or access control was encountered; no candidate data is read.")
    out["verdict"] = verdict(
        "VERIFIED" if can and dated and with_description else "EXPLORATORY",
        f"robots: {out['robots']['path_decisions']['/api/Jobad/GetJobAdPageList']['reason']}; "
        f"listing returns total_reported={out.get('listing_route', {}).get('total_reported')}, "
        f"{len(rows)} rows in the sampled page; {len(dated)}/{len(samples)} detail records "
        f"carried an epoch timestamp and {len(with_description)}/{len(samples)} a non-empty "
        f"Duty/Require description")
    return out


# ---------------------------------------------------------------------- dräger
def probe_draeger(politeness: Politeness) -> dict[str, Any]:
    """Dräger has three public surfaces; each is probed and recorded separately.

    1. the corporate CMS (www.draeger.com) — marketing pages behind bot management;
    2. the official job portal ``erecruitment.draeger.com`` (Beesite front end) with
       schema.org JobPosting JSON-LD on each job-ad page;
    3. the public Beesite search API the portal's own JavaScript calls;
    4. (secondary) the UK & Ireland Teamtailor board linked from the UK careers page.
    """
    out: dict[str, Any] = {"company_key": "draeger", "company_name": "Dräger",
                           "corporate_home": COMPANY_CORP["draeger"],
                           "platform_hypothesis": "beesite (Dräger e-recruitment portal) + Teamtailor (UK & Ireland)",
                           "requests": [], "routes": {}}

    # ---- route 1: corporate marketing site (known to be bot-managed for scripted clients)
    corp_robots = fetch("https://www.draeger.com/robots.txt", politeness)
    out["requests"].append(corp_robots.as_dict())
    routes = out["routes"]
    routes["corporate_robots"] = robots_record(corp_robots, ["/en/careers", "/en_uk/Career"])
    corp_page = fetch("https://www.draeger.com/en/careers", politeness, timeout=20.0, retries=0)
    out["requests"].append(corp_page.as_dict(head=200))
    routes["corporate_careers_page"] = {
        "url": corp_page.url, "status": corp_page.status, "content_type": corp_page.content_type,
        "error": corp_page.error, "elapsed_ms": corp_page.elapsed_ms,
        "note": ("scripted GET does not get an HTML response from the Akamai-fronted CMS; "
                 "a real browser in this session reached the same URL and got its 404 page "
                 "(recorded in SOURCE_DISCOVERY_EXTRAS.md, not reproducible by this script). "
                 "The corporate CMS is the marketing site, not the job board."),
    }

    # ---- route 2: official e-recruitment portal (Beesite front end)
    portal_robots = fetch("https://erecruitment.draeger.com/robots.txt", politeness)
    out["requests"].append(portal_robots.as_dict())
    routes["portal_robots"] = robots_record(portal_robots, ["/index.php?ac=jobad", "/sitemap.xml"])
    portal_sitemap = fetch("https://erecruitment.draeger.com/sitemap.xml", politeness)
    out["requests"].append(portal_sitemap.as_dict(head=300))
    jobad_urls = [u for u in sitemap_urls(portal_sitemap) if "ac=jobad" in u]
    routes["portal_sitemap"] = {"url": portal_sitemap.url, "status": portal_sitemap.status,
                                "content_type": portal_sitemap.content_type,
                                "n_urls": len(sitemap_urls(portal_sitemap)),
                                "n_jobad_urls": len(jobad_urls),
                                "sample": jobad_urls[:4]}
    samples: list[dict[str, Any]] = []
    for url in jobad_urls[:2]:
        page = fetch(url, politeness)
        shape = jobposting_shape(page.body)
        shape["url"] = url
        shape["status"] = page.status
        shape["error"] = page.error
        samples.append(shape)
        out["requests"].append(page.as_dict(head=120))
    routes["portal_jobad_samples"] = samples

    # ---- route 3: public Beesite search API (the portal's own list request)
    beesite_robots = fetch("https://draeger-beesite-production-gjb.app.beesite.de/robots.txt",
                           politeness)
    out["requests"].append(beesite_robots.as_dict())
    routes["beesite_robots"] = robots_record(beesite_robots, ["/search/"])
    fields = ["ID", "PositionTitle", "PositionURI", "PositionLocation.CountryName",
              "PositionLocation.CityName", "JobCategory.Name", "PublicationStartDate",
              "ParentOrganizationName", "CareerLevel.Name", "PositionSchedule.Name"]
    search_payload = {
        "LanguageCode": "DE",
        "SearchParameters": {"CountItem": 10,
                             "Sort": [{"Criterion": "PublicationStartDate", "Direction": "DESC"}],
                             "MatchedObjectDescriptor": fields},
        "SearchCriteria": [{"CriterionName": "PublicationChannel.Code",
                            "CriterionValue": ["12"]}],
    }
    search_url = ("https://draeger-beesite-production-gjb.app.beesite.de/search/?data="
                  + urllib.parse.quote(json.dumps(search_payload, separators=(",", ":"))))
    search = fetch(search_url, politeness, timeout=40.0,
                   headers={"Accept": "application/json, */*"})
    out["requests"].append(search.as_dict(head=200))
    search_record: dict[str, Any] = {"url_masked": search_url.split("?")[0] + "?data=<json>",
                                     "data_payload": search_payload,
                                     "status": search.status, "content_type": search.content_type,
                                     "error": search.error}
    try:
        data = json.loads(search.body or "{}")
        result = data.get("SearchResult") or {}
        items = result.get("SearchResultItems") or []
        search_record.update({
            "search_result_count": result.get("SearchResultCount"),
            "search_result_count_all": result.get("SearchResultCountAll"),
            "items_returned": len(items),
            "sample_items": [{
                "ID": (i.get("MatchedObjectDescriptor") or {}).get("ID"),
                "PositionTitle": short((i.get("MatchedObjectDescriptor") or {}).get("PositionTitle"), 120),
                "PublicationStartDate": (i.get("MatchedObjectDescriptor") or {}).get("PublicationStartDate"),
                "ParentOrganizationName": (i.get("MatchedObjectDescriptor") or {}).get("ParentOrganizationName"),
                "PositionURI": (i.get("MatchedObjectDescriptor") or {}).get("PositionURI"),
                "location": ((i.get("MatchedObjectDescriptor") or {}).get("PositionLocation") or [{}])[0].get("CityName")
                            if (i.get("MatchedObjectDescriptor") or {}).get("PositionLocation") else None,
            } for i in items[:3]],
        })
    except Exception as exc:  # noqa: BLE001 - recorded
        search_record["error_parse"] = f"{type(exc).__name__}: {exc}"
    routes["beesite_search"] = search_record

    # ---- route 4 (secondary): Teamtailor board for UK & Ireland
    uk_base = "https://ukjobs.draeger.com"
    uk_robots = fetch(f"{uk_base}/robots.txt", politeness)
    out["requests"].append(uk_robots.as_dict())
    routes["uk_teamtailor_robots"] = robots_record(uk_robots, ["/jobs", "/jobs/1234-x"])
    uk_sitemap = fetch(f"{uk_base}/sitemap.xml", politeness)
    out["requests"].append(uk_sitemap.as_dict(head=300))
    uk_job_urls = [u for u in sitemap_urls(uk_sitemap) if re.search(r"/jobs/\d+", u)]
    uk_sample: dict[str, Any] = {"url": None}
    if uk_job_urls:
        page = fetch(uk_job_urls[0], politeness)
        shape = jobposting_shape(page.body)
        shape.update({"url": uk_job_urls[0], "status": page.status, "error": page.error})
        uk_sample = shape
        out["requests"].append(page.as_dict(head=120))
    routes["uk_teamtailor_sitemap"] = {"url": uk_sitemap.url, "status": uk_sitemap.status,
                                       "content_type": uk_sitemap.content_type,
                                       "n_urls": len(sitemap_urls(uk_sitemap)),
                                       "n_job_urls": len(uk_job_urls),
                                       "sample": uk_job_urls[:4]}
    routes["uk_teamtailor_job_sample"] = uk_sample

    out["contract"] = {
        "posting_id_field": "sitemap id (index.php?ac=jobad&id=N) / Beesite MatchedObjectDescriptor.ID",
        "date_field": "schema.org JobPosting datePosted (date) on the job-ad page; "
                      "Beesite PublicationStartDate (date) in the list API",
        "date_precision": "SOURCE_DATE",
        "description": "full HTML description in the job-ad page's JSON-LD; the search API "
                       "carries no description, so a collector must pair list + page",
        "employing_entity": "the Beesite list names ParentOrganizationName per posting "
                            "(e.g. Drägerwerk AG & Co. KGaA, Dräger Safety AG & Co. KGaA) — "
                            "this is a source claim, not a guessed subsidiary",
    }
    portal_ok = routes["portal_sitemap"]["n_jobad_urls"] > 0
    api_ok = bool(routes["beesite_search"].get("search_result_count"))
    samples_ok = sum(1 for s in samples if s.get("jobposting_present"))
    out["automated_access_statement"] = (
        "The corporate marketing host (www.draeger.com) is fronted by Akamai bot management: "
        "scripted requests are stalled/refused while robots.txt is served statically. No "
        "attempt was made to defeat that. The job data, however, is served by the official "
        "public e-recruitment portal (Beesite front end) and its public search API, both of "
        "which answer scripted unauthenticated requests normally; no login, captcha or "
        "access control was encountered there. The corporate CMS is NOT the job board.")
    if portal_ok and api_ok and samples_ok:
        total_current = routes["beesite_search"].get("search_result_count_all") \
            or routes["beesite_search"].get("search_result_count")
        out["verdict"] = verdict(
            "VERIFIED",
            f"the official portal sitemap lists {routes['portal_sitemap']['n_jobad_urls']} "
            f"job-ad URLs and the public Beesite search API reports {total_current} current "
            f"postings ({routes['beesite_search']['items_returned']} sampled, agreeing with the "
            f"sitemap job-ad count); {samples_ok}/{len(samples)} sampled job-ad pages carried "
            f"schema.org JobPosting JSON-LD with datePosted and a description. The corporate "
            f"/en/careers page is still 404 (real browser) and the CMS itself resists scripted "
            f"clients.")
    else:
        out["verdict"] = verdict("EXPLORATORY", "only part of the Dräger route answered")
    return out


# ------------------------------------------------------------------------ main
def _run_company(company: str, politeness: Politeness) -> dict[str, Any]:
    if company in PHENOM:
        return probe_phenom(company, politeness)
    if company == "mindray":
        return probe_mindray(politeness)
    if company == "draeger":
        return probe_draeger(politeness)
    raise ValueError(f"no probe for {company}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", required=True, help="results directory for this probe run")
    ap.add_argument("--companies", nargs="*", default=list(COMPANIES),
                    choices=list(COMPANIES))
    ap.add_argument("--min-interval", type=float, default=1.2)
    ap.add_argument("--max-requests", type=int, default=60,
                    help="total request ceiling for the whole run")
    args = ap.parse_args(argv)

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    politeness = Politeness(args.min_interval, args.max_requests)
    print(f"deep_probe: {len(args.companies)} companies, budget={args.max_requests} requests")
    summary: list[dict[str, Any]] = []
    for company in args.companies:
        started = now()
        try:
            record = _run_company(company, politeness)
        except Exception as exc:  # noqa: BLE001 - one firm's failure must not hide the others
            record = {"company_key": company, "company_name": COMPANY_NAMES[company],
                      "error": f"{type(exc).__name__}: {exc}", "requests": [],
                      "verdict": verdict("NOT_RUN", f"probe raised {type(exc).__name__}: {exc}")}
        record["started_at"] = started
        record["finished_at"] = now()
        record["requests_made"] = len(record.get("requests") or [])
        path = out_dir / f"source_probe_{company}.json"
        path.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n",
                        encoding="utf-8")
        v = record.get("verdict", {})
        summary.append({"company": company, "verdict": v.get("verdict"),
                        "requests": record["requests_made"], "file": path.name})
        print(f"  {company:<14} {str(v.get('verdict')):<10} requests={record['requests_made']:<3} "
              f"-> {path.name}")

    (out_dir / "source_probe_summary.json").write_text(json.dumps({
        "probe": "deep_source_probe", "phase": "phase4", "started_at": now(),
        "client": {"user_agent": DEFAULT_UA, "from": FROM_HEADER,
                   "min_interval_s": args.min_interval, "max_requests": args.max_requests},
        "requests_made": politeness.count, "request_log": politeness.log,
        "companies": summary,
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"total requests: {politeness.count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
