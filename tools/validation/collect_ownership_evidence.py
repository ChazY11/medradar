#!/usr/bin/env python3
"""Collect reproducible ownership evidence for the MedRadar organization registry.

The product may claim that an applicant spelling belongs to a tracked organization only when a
deterministic rule or an independent source justifies it. This collector gathers the independent
part for the five featured companies: the list of subsidiaries / registrant entities that a
company files with a regulator (SEC EDGAR exhibits such as "Exhibit 21 - List of Subsidiaries").

What it is and is not
---------------------
* Reproducible collector: it records the filing URL, accession number, filing date and the exact
  matched exhibit line, so a reviewer can re-run and re-check the evidence.
* NOT a licensed feed, NOT a human review. Its output is the evidence input to
  medradar/product/identity/ownership.json; the decision record states who reviewed it and whether
  that reviewer is a human or an agent (reviewer_kind).

Usage
-----
    python tools/validation/collect_ownership_evidence.py                 # human-readable report
    python tools/validation/collect_ownership_evidence.py --json build/ownership_evidence.json

Network: SEC EDGAR only (public domain, no API key). SEC requires a User-Agent with contact
details; set MEDRADAR_SEC_USER_AGENT.
"""
from __future__ import annotations

import argparse
import gzip
import html
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[2]
REGISTRY = ROOT / "medradar" / "product" / "identity" / "organizations.json"

DEFAULT_USER_AGENT = "MedRadar PRODUCT-002 evidence collector (contact: repository owner)"
SEC_HEADERS = {
    "User-Agent": os.environ.get("MEDRADAR_SEC_USER_AGENT") or DEFAULT_USER_AGENT,
    "Accept-Encoding": "gzip, deflate",
}

#: (organization_key, ticker, accepted form types)
TARGETS: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("medtronic", "MDT", ("10-K",)),
    ("ge_healthcare", "GEHC", ("10-K",)),
    ("philips", "PHG", ("20-F",)),
    ("mindray", "", ("20-F",)),
    ("draeger", "", ("20-F",)),
)

#: Applicant families whose ownership needs a corporate document. Matching is whole-token.
KEY_ENTITIES = (
    "COVIDIEN", "TYCO HEALTHCARE", "MEDTRONIC MINIMED", "MEDTRONIC VASCULAR",
    "MEDTRONIC SOFAMOR DANEK", "MINIMED", "GE MEDICAL SYSTEMS", "GE HEALTHCARE",
    "PHILIPS MEDICAL SYSTEMS", "PHILIPS NORTH AMERICA", "PHILIPS ELECTRONICS NORTH AMERICA",
    "MINIMED", "MINDRAY DS USA", "DATASCOPE", "INVIVO", "NEUSOFT", "DRAGER", "DRAEGER",
)

EXHIBIT_NAME_RE = re.compile(r"(subsidiar|ex-?21|ex21|ex_21|exhibit21|exhibit 21)", re.IGNORECASE)
EXHIBIT_GENERIC_RE = re.compile(r"(exx?[0-9]|ex-?[0-9]|exhibit)", re.IGNORECASE)
BLOCK_TAG_RE = re.compile(r"</?(?:tr|p|div|td|th|li|br|table|h[1-6])[^>]*>", re.IGNORECASE)
TAG_RE = re.compile(r"<[^>]+>")
WS_RE = re.compile(r"[ \t\xa0]+")
SUBSIDIARY_WORD_RE = re.compile(r"subsidiar", re.IGNORECASE)


def fetch(url: str, *, retries: int = 3) -> bytes:
    last: Exception | None = None
    for attempt in range(retries):
        try:
            request = urllib.request.Request(url, headers=SEC_HEADERS)
            with urllib.request.urlopen(request, timeout=60) as response:
                data = response.read()
                if response.headers.get("Content-Encoding") == "gzip":
                    data = gzip.decompress(data)
                return data
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as error:
            last = error
            time.sleep(1.5 + attempt)
    raise RuntimeError("failed to fetch " + url + ": " + str(last))


def resolve_ciks() -> dict[str, str]:
    payload = json.loads(fetch("https://www.sec.gov/files/company_tickers.json").decode("utf-8"))
    by_ticker: dict[str, str] = {}
    for row in payload.values():
        ticker = str(row.get("ticker") or "").upper()
        if ticker:
            by_ticker[ticker] = str(int(row.get("cik_str"))).zfill(10)
    resolved: dict[str, str] = {}
    for organization_key, ticker, _forms in TARGETS:
        if ticker and ticker in by_ticker:
            resolved[organization_key] = by_ticker[ticker]
    return resolved


def latest_filings(cik: str, forms: Iterable[str]) -> list[dict[str, Any]]:
    payload = json.loads(fetch("https://data.sec.gov/submissions/CIK" + cik + ".json").decode("utf-8"))
    recent = payload.get("filings", {}).get("recent", {})
    wanted = set(forms)
    rows = []
    for index, form in enumerate(recent.get("form", [])):
        if form not in wanted:
            continue
        rows.append({
            "form": form,
            "accession": str(recent["accessionNumber"][index]),
            "filed": str(recent["filingDate"][index]),
            "report_date": str(recent.get("reportDate", [""])[index] or ""),
        })
        if len(rows) >= 3:
            break
    return rows


def filing_index(cik: str, accession: str) -> dict[str, Any]:
    bare = accession.replace("-", "")
    url = "https://www.sec.gov/Archives/edgar/data/" + str(int(cik)) + "/" + bare + "/index.json"
    return json.loads(fetch(url).decode("utf-8"))


def exhibit_candidates(index: dict[str, Any]) -> list[dict[str, str]]:
    """Exhibits plausibly containing a list of subsidiaries, most specific first."""
    specific: list[dict[str, str]] = []
    generic: list[dict[str, str]] = []
    for item in index.get("directory", {}).get("item", []):
        name = str(item.get("name") or "")
        if not name or not name.lower().endswith((".htm", ".html", ".txt")):
            continue
        entry = {"name": name, "type": str(item.get("type") or "")}
        if EXHIBIT_NAME_RE.search(name):
            specific.append(entry)
        elif EXHIBIT_GENERIC_RE.search(name) and not name.lower().endswith(".txt"):
            generic.append(entry)
    return specific + generic


def strip_markup(markup: str) -> str:
    """Turn an EDGAR HTML exhibit into one line per table row / block element."""
    text = BLOCK_TAG_RE.sub("\n", markup)
    text = TAG_RE.sub(" ", text)
    text = html.unescape(text)
    return "\n".join(WS_RE.sub(" ", line).strip() for line in text.splitlines())


def matched_entity_lines(text: str, limit: int = 40) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for line in text.splitlines():
        candidate = line.strip()
        if not 4 <= len(candidate) <= 220:
            continue
        upper = candidate.upper()
        hit = next((token for token in KEY_ENTITIES if token in upper), None)
        if hit is None and not re.search(r"\b(INC|LLC|LTD|GMBH|CORP|CORPORATION|LIMITED|B\.V\.|N\.V\.)\b", upper):
            continue
        if candidate in seen:
            continue
        seen.add(candidate)
        out.append(candidate)
        if len(out) >= limit:
            break
    return out


def collect_target(organization_key: str, cik: str, forms: tuple[str, ...]) -> dict[str, Any]:
    record: dict[str, Any] = {"organization_key": organization_key, "cik": cik, "filings": []}
    for filing in latest_filings(cik, forms):
        bare = filing["accession"].replace("-", "")
        base = "https://www.sec.gov/Archives/edgar/data/" + str(int(cik)) + "/" + bare + "/"
        entry = {
            "form": filing["form"],
            "accession": filing["accession"],
            "filed": filing["filed"],
            "index_url": base + filing["accession"] + "-index.htm",
            "exhibits": [],
        }
        try:
            index = filing_index(cik, filing["accession"])
        except RuntimeError as error:
            entry["error"] = str(error)
            record["filings"].append(entry)
            continue
        best: dict[str, Any] | None = None
        for candidate in exhibit_candidates(index)[:8]:
            url = base + candidate["name"]
            try:
                body = fetch(url).decode("utf-8", errors="replace")
            except RuntimeError as error:
                entry["exhibits"].append({"url": url, "name": candidate["name"], "type": candidate["type"], "error": str(error)})
                continue
            text = strip_markup(body)
            lines = matched_entity_lines(text)
            subsidiary_mentions = len(SUBSIDIARY_WORD_RE.findall(text))
            score = 3 * len(lines) + min(subsidiary_mentions, 50)
            exhibit_entry = {
                "url": url,
                "name": candidate["name"],
                "type": candidate["type"],
                "subsidiary_mentions": subsidiary_mentions,
                "matched_entity_lines": lines,
                "score": score,
            }
            entry["exhibits"].append(exhibit_entry)
            if lines and (best is None or score > best["score"]):
                best = exhibit_entry
        entry["selected_exhibit_url"] = best["url"] if best else None
        record["filings"].append(entry)
        if best is not None:
            break
    return record


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Collect SEC ownership evidence for the registry.")
    parser.add_argument("--json", default=None, help="write the full evidence report to this path")
    parser.add_argument("--only", default=None, help="comma separated organization keys")
    args = parser.parse_args(argv)

    targets = [target for target in TARGETS if not args.only or target[0] in args.only.split(",")]
    try:
        ciks = resolve_ciks()
    except RuntimeError as error:
        print("EDGAR unavailable: " + str(error), file=sys.stderr)
        return 2
    report: dict[str, Any] = {"collected_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "targets": []}
    for organization_key, ticker, forms in targets:
        cik = ciks.get(organization_key)
        print("== " + organization_key + " (" + (ticker or "-") + ") cik=" + str(cik))
        if not cik:
            print("   no SEC registrant with that ticker: UNKNOWN (no jurisdiction filing collected)")
            report["targets"].append({"organization_key": organization_key, "cik": None, "status": "unknown-no-registrant"})
            continue
        record = collect_target(organization_key, cik, forms)
        for filing in record["filings"]:
            print("   " + filing["form"] + " filed " + filing["filed"] + "  " + filing["index_url"])
            for exhibit in filing["exhibits"]:
                lines = exhibit.get("matched_entity_lines") or []
                print("     exhibit " + exhibit["name"] + " -> " + str(len(lines)) + " entity line(s)  " + exhibit["url"])
                for line in lines[:8]:
                    print("        | " + line[:150])
        report["targets"].append(record)
    if args.json:
        path = Path(args.json)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(report, indent=1, ensure_ascii=False), encoding="utf-8")
        print("wrote " + str(path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())