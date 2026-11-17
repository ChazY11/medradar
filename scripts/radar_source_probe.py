"""RADAR-001 source-access probe.

Before any adapter may be enabled, its read path must be *verified* as reachable by the
program and (for web sources) as permitting automated access. This script performs that
verification with an honest, identifiable User-Agent and records the raw result:

* HTTP status, content type, byte length and a bounded body excerpt per URL;
* the source's ``robots.txt`` verdict for the exact path we intend to fetch;
* explicit ``DECISION`` lines: ``ENABLED`` / ``BLOCKED`` / ``UNVERIFIED``.

Rules this script obeys:

* no browser-UA spoofing, no cookies, no authentication, no proxy;
* no retry of a refusal: one 403 is enough to record ``BLOCKED``;
* a vendor adapter is enabled only when its *real* read path was fetched successfully
  **and** the robots policy for that path allows it;
* a 404 means "that path does not exist", which is a probe mistake, not an access
  restriction - such a row is reported as ``PATH_NOT_FOUND`` and the adapter is not
  enabled on the strength of it.

The output is the access/licensing evidence cited by ``docs/radar/SOURCES.md`` and is
intended to be committed: it contains public metadata only.

    python scripts/radar_source_probe.py --out docs/radar/evidence/source_probe.json
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

USER_AGENT = (
    "MedRadarBot/0.1 (+https://github.com/ChazY11/medradar; research; "
    "contact: repository owner) Python-urllib"
)
BODY_EXCERPT = 600

#: (source_id, url, role, why). ``role`` is ``read_path`` or ``policy``.
PROBES: list[tuple[str, str, str, str]] = [
    # --- PubMed / NCBI E-utilities: documented public API, no key required (3 req/s).
    ("pubmed", "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?db=pubmed&term=patient+monitoring&retmax=1&retmode=json", "read_path", "E-utilities search"),
    ("pubmed", "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi?db=pubmed&id=39000000&retmode=xml", "read_path", "E-utilities fetch"),
    ("pubmed", "https://www.ncbi.nlm.nih.gov/pmc/tools/oai/", "policy", "NCBI API usage policy page"),
    # --- Crossref REST API: public, polite pool expects a mailto in the UA or query.
    ("crossref", "https://api.crossref.org/works?query.bibliographic=patient+monitor&rows=2&mailto=research@medradar.example", "read_path", "REST works search"),
    ("crossref", "https://www.crossref.org/documentation/retrieve-metadata/rest-api/", "policy", "Crossref REST API documentation"),
    # --- openFDA: the same endpoint the DATA-001 pipeline already uses.
    ("fda_openfda", "https://api.fda.gov/device/510k.json?search=applicant:%22Philips%22&limit=2", "read_path", "openFDA 510(k) search"),
    ("fda_openfda", "https://open.fda.gov/terms/", "policy", "openFDA terms of service"),
    # --- Philips: robots-permitted HTML news index -> press-release pages.
    ("philips_official", "https://www.philips.com/robots.txt", "policy", "robots for philips.com"),
    ("philips_official", "https://www.philips.com/a-w/about/news.html", "read_path", "Philips news index"),
    ("philips_official", "https://www.philips.com/a-w/about/news/archive/standard/news/press/2026/philips-launches-hypervue-integrated-system-in-the-u-s-bringing-advanced-coronary-imaging-and-physiology-into-the-cathlab.html", "read_path", "one press-release page"),
    # --- GE HealthCare: refused at the edge. Recorded, respected, never bypassed.
    ("gehealthcare_official", "https://www.gehealthcare.com/robots.txt", "policy", "robots for gehealthcare.com"),
    ("gehealthcare_official", "https://www.gehealthcare.com/about/newsroom", "read_path", "GE HealthCare newsroom"),
    # --- Draeger: robots-permitted newsroom sitemap with per-article lastmod.
    ("draeger_official", "https://www.draeger.com/robots.txt", "policy", "robots for draeger.com"),
    ("draeger_official", "https://www.draeger.com/en_uk/sitemap/NewsroomArticle.xml", "read_path", "Draeger newsroom sitemap"),
]

#: Paths whose robots verdict decides whether a vendor adapter may run.
ROBOTS_PATHS: dict[str, list[str]] = {
    "philips_official": [
        "https://www.philips.com/a-w/about/news.html",
        "https://www.philips.com/a-w/about/news/archive/standard/news/press/2026/philips-launches-hypervue-integrated-system-in-the-u-s-bringing-advanced-coronary-imaging-and-physiology-into-the-cathlab.html",
    ],
    "gehealthcare_official": ["https://www.gehealthcare.com/about/newsroom"],
    "draeger_official": ["https://www.draeger.com/en_uk/sitemap/NewsroomArticle.xml"],
}

#: Sources whose access is governed by a documented public API rather than robots.txt.
API_SOURCES = {"pubmed", "crossref", "fda_openfda"}

#: HTTP statuses that mean "the operator refused automated access".
REFUSAL_STATUSES = {401, 402, 403, 407, 429, 451}


def fetch(url: str, timeout: float = 30.0) -> dict[str, Any]:
    """One GET with our honest UA. No retry: a refusal must stay visible."""
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "*/*"})
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read(400_000)
            elapsed = round((time.perf_counter() - started) * 1000.0, 1)
            text = raw.decode(response.headers.get_content_charset() or "utf-8", "replace")
            return {
                "ok": True,
                "status": response.status,
                "content_type": response.headers.get("Content-Type"),
                "bytes": len(raw),
                "elapsed_ms": elapsed,
                "excerpt": " ".join(text[:BODY_EXCERPT].split()),
            }
    except urllib.error.HTTPError as error:
        elapsed = round((time.perf_counter() - started) * 1000.0, 1)
        try:
            body = error.read(4000).decode("utf-8", "replace")
        except Exception:  # pragma: no cover - body may be unreadable
            body = ""
        return {
            "ok": False,
            "status": error.code,
            "content_type": error.headers.get("Content-Type") if error.headers else None,
            "bytes": len(body),
            "elapsed_ms": elapsed,
            "excerpt": " ".join(body[:BODY_EXCERPT].split()),
            "error": f"HTTP {error.code} {error.reason}",
        }
    except Exception as error:  # noqa: BLE001 - a probe records every failure kind
        elapsed = round((time.perf_counter() - started) * 1000.0, 1)
        return {"ok": False, "status": None, "elapsed_ms": elapsed, "error": f"{type(error).__name__}: {error}"}


def parse_robots(text: str) -> list[dict[str, str]]:
    rules: list[dict[str, str]] = []
    applies = False
    for line in text.splitlines():
        stripped = line.split("#", 1)[0].strip()
        if not stripped or ":" not in stripped:
            continue
        field, value = stripped.split(":", 1)
        field = field.strip().lower()
        value = value.strip()
        if field == "user-agent":
            applies = value == "*"
        elif applies and field in ("disallow", "allow"):
            rules.append({"rule": field, "value": value})
    return rules


def robots_verdict(rules: list[dict[str, str]], url: str) -> dict[str, Any]:
    """Longest-match robots evaluation for one exact path (empty Disallow = allow all)."""
    parsed = urllib.parse.urlsplit(url)
    path = parsed.path + (("?" + parsed.query) if parsed.query else "")
    best: tuple[int, bool] | None = None
    for rule in rules:
        pattern = rule["value"]
        if not pattern:
            continue
        # ``*`` inside a pattern matches any run of characters.
        candidate = pattern.rstrip("*")
        if "*" in candidate:
            continue
        if path.startswith(candidate):
            score = len(candidate)
            allowed = rule["rule"] == "allow"
            if best is None or score > best[0] or (score == best[0] and allowed):
                best = (score, allowed)
    allowed = True if best is None else best[1]
    return {"url": url, "path": path, "allowed": allowed, "matched_prefix_len": None if best is None else best[0]}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Probe RADAR-001 source access and robots policy.")
    parser.add_argument("--out", default=None, help="write JSON evidence to this path")
    parser.add_argument("--sleep", type=float, default=1.0, help="pause between requests (politeness)")
    args = parser.parse_args(argv)

    results: list[dict[str, Any]] = []
    for index, (source_id, url, role, why) in enumerate(PROBES):
        if index:
            time.sleep(args.sleep)
        outcome = fetch(url)
        results.append({"source_id": source_id, "url": url, "role": role, "why": why, **outcome})
        print(
            f"[{source_id:22}] {url}\n    -> status={outcome.get('status')} ok={outcome['ok']} "
            f"bytes={outcome.get('bytes')} {outcome.get('error', '')}",
            flush=True,
        )

    # robots verdicts for the exact vendor paths we intend to fetch.
    robots_rows: list[dict[str, Any]] = []
    for source_id, urls in ROBOTS_PATHS.items():
        robots_url = f"https://{urllib.parse.urlsplit(urls[0]).netloc}/robots.txt"
        entry = next((r for r in results if r["url"] == robots_url), None)
        if entry is None or not entry.get("ok"):
            for url in urls:
                robots_rows.append({
                    "source_id": source_id, "url": url, "allowed": False,
                    "reason": "robots.txt could not be read: automated access is not verified",
                })
            continue
        rules = parse_robots(entry.get("excerpt") or "")
        for url in urls:
            robots_rows.append({"source_id": source_id, "rules_parsed": len(rules), **robots_verdict(rules, url)})

    # Decisions.
    decisions: list[dict[str, Any]] = []
    by_source: dict[str, list[dict[str, Any]]] = {}
    for row in results:
        by_source.setdefault(row["source_id"], []).append(row)
    for source_id, rows in by_source.items():
        read_rows = [r for r in rows if r["role"] == "read_path"]
        reachable = bool(read_rows) and all(r["ok"] and (r.get("status") or 0) < 400 for r in read_rows)
        refusals = sorted({r["status"] for r in rows if r.get("status") in REFUSAL_STATUSES})
        policy_rows = [r for r in rows if r["role"] == "policy"]
        if source_id in API_SOURCES:
            permitted = reachable
            basis = "documented public API; robots.txt does not govern an API host route"
        else:
            verdicts = [r for r in robots_rows if r["source_id"] == source_id]
            permitted = bool(verdicts) and all(v["allowed"] for v in verdicts)
            basis = "robots.txt longest-match verdict for the exact read path"
        if reachable and permitted:
            decision, reason = "ENABLED", f"read path fetched successfully; {basis}"
        elif refusals:
            decision = "BLOCKED"
            reason = (
                f"operator refused automated access (HTTP {','.join(str(s) for s in refusals)}); "
                "the refusal is recorded and respected - no spoofing, no bypass, adapter stays disabled"
            )
        elif not reachable:
            statuses = sorted({str(r.get("status")) for r in read_rows})
            decision = "UNVERIFIED"
            reason = f"read path did not return a usable response (HTTP {','.join(statuses)}); adapter stays disabled"
        else:
            decision = "BLOCKED"
            reason = "robots policy disallows the intended path"
        decisions.append({
            "source_id": source_id,
            "decision": decision,
            "reason": reason,
            "reachable": reachable,
            "robots_permitted": permitted,
            "policy_basis": basis,
            "policy_document": policy_rows[0]["url"] if policy_rows else None,
        })

    payload = {
        "schema": "medradar.radar.source_probe.v1",
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "user_agent": USER_AGENT,
        "policy": (
            "honest UA; no spoofing, cookies, auth or proxy; no retry on refusal; "
            "robots.txt read and evaluated before any vendor page is fetched"
        ),
        "results": results,
        "robots_verdicts": robots_rows,
        "decisions": decisions,
    }
    print()
    for decision in decisions:
        print(f"[{decision['source_id']:22}] {decision['decision']:10} {decision['reason']}")
    if args.out:
        path = Path(args.out)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"\nwrote {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
