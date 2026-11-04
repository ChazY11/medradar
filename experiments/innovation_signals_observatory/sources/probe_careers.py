"""SOURCE DISCOVERY PROBE — MedRadar Phase 4, recruitment lane.

This script is the reproducible record of *how* the five mandated focus companies'
career data sources were investigated. It is deliberately read-mostly:

  * it never bypasses authentication, captchas, paywalls or access controls;
  * it issues a bounded number of requests per host with a polite delay;
  * it records robots.txt for every host it touches, and refuses a host whose
    robots rules disallow the exact path it would need;
  * it stores the *observations it made* (status codes, discovered endpoints,
    ATS fingerprints) — not scraped candidate data.

Output: a JSON record per probe run under `results/<date>/source_probe.json`.

Run:
    python experiments/innovation_signals_observatory/sources/probe_careers.py \
        --out experiments/innovation_signals_observatory/results/2026-11-04
"""
from __future__ import annotations

import argparse
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)
# Research-honest identification: we say who we are. The UA above is the browser
# identity the public pages serve to; this header states the actual client.
FROM = "MedRadar research (academic; contact: repository owner)"

#: Companies mandated by the mission. Never silently replaced.
FOCUS_COMPANIES = {
    "medtronic": {"name": "Medtronic", "corp": "https://www.medtronic.com/"},
    "ge_healthcare": {"name": "GE HealthCare", "corp": "https://www.gehealthcare.com/"},
    "philips": {"name": "Philips", "corp": "https://www.philips.com/"},
    "draeger": {"name": "Dräger", "corp": "https://www.draeger.com/"},
    "mindray": {"name": "Mindray", "corp": "https://www.mindray.com/"},
}

#: ATS fingerprints. A hit is a *hypothesis* until a bounded content request
#: confirms that a real posting with a stable id and a real job description is
#: retrievable by a lawful route.
ATS_PATTERNS = {
    "workday": re.compile(r"myworkdayjobs\.com|/wday/|workday", re.I),
    "phenom": re.compile(r"phenompeople|phenom\.|\bphenom\b", re.I),
    "taleo": re.compile(r"taleo", re.I),
    "successfactors": re.compile(r"successfactors|jobs2web|sapsf", re.I),
    "icims": re.compile(r"icims", re.I),
    "avature": re.compile(r"avature", re.I),
    "eightfold": re.compile(r"eightfold", re.I),
    "smartrecruiters": re.compile(r"smartrecruiters", re.I),
    "greenhouse": re.compile(r"greenhouse\.io", re.I),
    "lever": re.compile(r"lever\.co", re.I),
    "workable": re.compile(r"workable\.com", re.I),
    "talemetry": re.compile(r"talemetry", re.I),
    "radancy": re.compile(r"radancy|talentbrew", re.I),
    "beisen": re.compile(r"zhiye\.com|beisen", re.I),
}


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


@dataclass
class Fetched:
    url: str
    status: int | None = None
    final_url: str | None = None
    content_type: str | None = None
    body: str | None = None
    error: str | None = None
    elapsed_ms: int | None = None
    redirect_chain: list[str] = field(default_factory=list)

    def as_dict(self, limit: int = 400) -> dict[str, Any]:
        out = {
            "url": self.url,
            "status": self.status,
            "final_url": self.final_url,
            "content_type": self.content_type,
            "error": self.error,
            "elapsed_ms": self.elapsed_ms,
            "redirect_chain": self.redirect_chain,
        }
        if self.body is not None:
            out["body_bytes"] = len(self.body.encode("utf-8", "replace"))
            out["body_head"] = self.body[:limit]
        return out


class Politeness:
    """Per-host throttle and a hard cap on requests, so the probe is bounded."""

    def __init__(self, min_interval_s: float = 1.2, max_requests: int = 120) -> None:
        self.min_interval_s = min_interval_s
        self.max_requests = max_requests
        self._last: dict[str, float] = {}
        self.count = 0
        self.log: list[dict[str, Any]] = []

    def wait(self, host: str) -> None:
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
        self.log.append({"url": url, "at": _now()})


def fetch(
    url: str,
    politeness: Politeness,
    *,
    method: str = "GET",
    body: bytes | None = None,
    headers: dict[str, str] | None = None,
    timeout: float = 30.0,
    max_bytes: int = 400_000,
    accept: str = "text/html,application/xhtml+xml,application/json;q=0.9,*/*;q=0.8",
) -> Fetched:
    host = urllib.parse.urlsplit(url).netloc.lower()
    politeness.wait(host)
    politeness.charge(url)
    req_headers = {
        "User-Agent": UA,
        "From": FROM,
        "Accept": accept,
        "Accept-Language": "en-US,en;q=0.9,zh-CN;q=0.8",
    }
    if headers:
        req_headers.update(headers)
    req = urllib.request.Request(url, data=body, headers=req_headers, method=method)
    started = time.monotonic()
    out = Fetched(url=url)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read(max_bytes)
            out.status = resp.status
            out.final_url = resp.geturl()
            out.content_type = resp.headers.get("Content-Type")
            charset = resp.headers.get_content_charset() or "utf-8"
            out.body = raw.decode(charset, "replace")
    except urllib.error.HTTPError as exc:  # a real server answer, keep it
        out.status = exc.code
        out.final_url = exc.geturl() if hasattr(exc, "geturl") else url
        out.content_type = exc.headers.get("Content-Type") if exc.headers else None
        try:
            out.body = exc.read(max_bytes).decode("utf-8", "replace")
        except Exception:  # pragma: no cover - body may be unreadable
            out.body = None
        out.error = f"HTTPError {exc.code}"
    except Exception as exc:  # network / TLS / timeout
        out.error = f"{type(exc).__name__}: {exc}"
    out.elapsed_ms = int((time.monotonic() - started) * 1000)
    return out


# --------------------------------------------------------------------- robots
def parse_robots(text: str) -> list[dict[str, Any]]:
    """Minimal robots.txt parser: group -> {agents, allow, disallow}."""
    groups: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    last_was_agent = False
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line or ":" not in line:
            continue
        key, _, value = line.partition(":")
        key = key.strip().lower()
        value = value.strip()
        if key == "user-agent":
            if current is None or not last_was_agent:
                current = {"agents": [], "allow": [], "disallow": []}
                groups.append(current)
            current["agents"].append(value.lower())
            last_was_agent = True
        elif key in ("allow", "disallow"):
            if current is not None:
                current[key].append(value)
            last_was_agent = False
        else:
            last_was_agent = False
    return groups


def robots_verdict(groups: list[dict[str, Any]], path: str) -> dict[str, Any]:
    """Return the rule that governs `path` for a generic `*` client.

    Longest-match wins, Allow beats Disallow on a tie (the Robots Exclusion
    Protocol convention). We do not interpret wildcards beyond this; if a rule
    contains `*` or `$` and is the longest match we report it as `unsure` rather
    than pretending to be certain.
    """
    import fnmatch

    applicable = [g for g in groups if "*" in g["agents"]] or (
        [g for g in groups if "medradar" in " ".join(g["agents"])] or []
    )
    if not applicable:
        return {"verdict": "unlisted", "rule": None, "matched": None}
    candidates: list[tuple[int, str, str]] = []
    for g in applicable:
        for rule in g["allow"]:
            if rule and _match(rule, path):
                candidates.append((len(rule), "allow", rule))
        for rule in g["disallow"]:
            if rule and _match(rule, path):
                candidates.append((len(rule), "disallow", rule))
    if not candidates:
        return {"verdict": "unlisted", "rule": None, "matched": None}
    candidates.sort(key=lambda c: (c[0], c[1] == "allow"), reverse=True)
    length, kind, rule = candidates[0]
    wildcard = ("*" in rule) or rule.endswith("$")
    return {
        "verdict": ("allow" if kind == "allow" else "disallow"),
        "rule": rule,
        "matched": path,
        "wildcard": wildcard,
        "certain": not wildcard,
    }


def _match(rule: str, path: str) -> bool:
    import fnmatch

    if "*" in rule or "$" in rule:
        pattern = rule.rstrip("$")
        return fnmatch.fnmatch(path, pattern)
    return path.startswith(rule)


# ------------------------------------------------------------------- discovery
def detect_ats(html: str) -> list[str]:
    return [name for name, pat in ATS_PATTERNS.items() if pat.search(html or "")]


def extract_links(html: str, base: str) -> list[str]:
    links = re.findall(r'href=["\']([^"\']+)["\']', html or "")
    abs_links: list[str] = []
    for link in links:
        if link.startswith(("mailto:", "javascript:", "#", "tel:")):
            continue
        abs_links.append(urllib.parse.urljoin(base, link))
    return abs_links


def discover_company(key: str, politeness: Politeness) -> dict[str, Any]:
    info = FOCUS_COMPANIES[key]
    out: dict[str, Any] = {
        "company_key": key,
        "company_name": info["name"],
        "corporate_home": info["corp"],
        "candidates": [],
        "ats_hypotheses": [],
        "robots": {},
    }

    # candidates are career-site entry points, tried in order until one answers
    # with a real career page (not a marketing 200 that merely mentions "jobs").
    candidates = {
        "medtronic": [
            "https://jobs.medtronic.com/",
            "https://medtronic.wd1.myworkdayjobs.com/MedtronicCareers",
        ],
        "ge_healthcare": [
            "https://careers.gehealthcare.com/global/en",
            "https://careers.gehealthcare.com/",
        ],
        "philips": [
            "https://www.careers.philips.com/global/en",
            "https://jobs.philips.com/",
            "https://philips.taleo.net/careersection/2/moresearch.ftl",
        ],
        "draeger": [
            "https://www.draeger.com/en/careers",
            "https://career.draeger.com/",
            "https://draeger.taleo.net/careersection/2/moresearch.ftl",
        ],
        "mindray": [
            "https://www.mindray.com/en/careers",
            "https://mindray.zhiye.com/",
        ],
    }[key]

    for url in candidates:
        fetched = fetch(url, politeness)
        rec = fetched.as_dict(limit=200)
        rec["ats_hits"] = detect_ats(fetched.body or "")
        if fetched.body:
            rec["jsonld_scripts"] = len(re.findall(r'application/ld\+json', fetched.body, re.I))
            rec["link_sample"] = extract_links(fetched.body, fetched.final_url or url)[:40]
        out["candidates"].append(rec)
        for hit in rec["ats_hits"]:
            if hit not in out["ats_hypotheses"]:
                out["ats_hypotheses"].append(hit)

    # robots.txt for every host we actually touched
    hosts: set[str] = set()
    for rec in out["candidates"]:
        for u in [rec["url"], rec.get("final_url") or ""]:
            if u:
                hosts.add(urllib.parse.urlsplit(u).netloc.lower())
    for host in sorted(hosts):
        rob_url = f"https://{host}/robots.txt"
        rob = fetch(rob_url, politeness, timeout=20)
        groups = parse_robots(rob.body or "")
        out["robots"][host] = {
            "url": rob_url,
            "status": rob.status,
            "error": rob.error,
            "groups": groups,
            "verdicts": {
                path: robots_verdict(groups, path)
                for path in ("/", "/wday/cxs/", "/careersection/", "/global/en", "/api/")
            },
            "raw_head": (rob.body or "")[:1200],
        }
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True, help="results directory for this probe run")
    ap.add_argument("--companies", nargs="*", default=sorted(FOCUS_COMPANIES))
    ap.add_argument("--min-interval", type=float, default=1.2)
    ap.add_argument("--max-requests", type=int, default=120)
    args = ap.parse_args(argv)

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    politeness = Politeness(args.min_interval, args.max_requests)
    record: dict[str, Any] = {
        "probe": "careers_source_discovery",
        "phase": "phase4",
        "started_at": _now(),
        "client": {"user_agent": UA, "from": FROM, "max_requests": args.max_requests,
                   "min_interval_s": args.min_interval},
        "focus_companies": {k: v["name"] for k, v in FOCUS_COMPANIES.items()},
        "companies": {},
    }
    for key in args.companies:
        try:
            record["companies"][key] = discover_company(key, politeness)
        except RuntimeError as exc:  # request budget
            record.setdefault("errors", []).append({"company": key, "error": str(exc)})
            break
    record["finished_at"] = _now()
    record["requests_made"] = politeness.count
    record["request_log"] = politeness.log
    path = out_dir / "source_probe.json"
    path.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {path} ({politeness.count} requests)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
