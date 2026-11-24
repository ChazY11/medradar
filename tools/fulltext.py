"""Fetch open-access full text into the same sidecar shape the 510(k) corpus uses.

    python3 tools/fulltext.py --source europepmc --query catheter --limit 200
    python3 tools/fulltext.py --source preprints --days 14 --limit 300
    python3 tools/fulltext.py --status

Why full text is the scarce thing
---------------------------------
Metadata is cheap and everywhere: a title, a date and a DOI answer "there is a paper". What a
device engineer cannot get from metadata is what was actually done - the parameters, the bench
setup, the failure modes, the numbers. Measured 2026-11-24: Europe PMC serves JATS full text for
274,206 open-access, in-PMC records matching a single term, and both preprint servers publish a
JATS URL per record. Both are free and need no credential.

Output
------
One JSON sidecar per record plus a sibling ``.txt``, byte-for-byte the shape of
``510k_summary_*.json`` so the same readers work:

    {"kind": "paper", "identifier": "PMC13787585", "url": ..., "status": "text",
     "sections": {...}, "canonical": {...}, "licence": ..., "char_count": ...}
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Iterable

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from medradar.radar.http import HostPolicy, PoliteFetcher, RateLimited, Refused
from medradar.radar.jats import JatsError, parse_jats

EUROPEPMC_SEARCH = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"
#: Full text does NOT come from EBI. Measured 2026-11-24: ``/rest/{PMCID}/fullTextXML`` serves
#: ~2.5 KB/s from this host *and* from a European client (23-25 s for a 50 KB article), and half
#: the requests return 503. The same article from the PMC Open Access mirror on S3 takes 0.32 s
#: (163 KB/s) and never 503'd - about 70x faster, which is the difference between a crawl that
#: works and one that does not exist. Discovery still uses Europe PMC: its search endpoint answers
#: in seconds and is the only place that knows which PMCIDs are open access.
PMC_OA_BUCKET = "https://pmc-oa-opendata.s3.amazonaws.com/{pmcid}.1/{pmcid}.1.xml"
#: Kept as an explicit fallback so a record missing from the S3 mirror is still attempted once.
EUROPEPMC_FULLTEXT = "https://www.ebi.ac.uk/europepmc/webservices/rest/{pmcid}/fullTextXML"
PREPRINT_DETAILS = "https://api.{server}.org/details/{server}/{start}/{end}/{offset}"
DEFAULT_OUT = "/srv/medradar/intel/papers"
PAGE = 100
SECONDS_BETWEEN = 0.4
USER_AGENT = "MedRadar/0.1 (+https://github.com/ChazY11/medradar; research)"


def _fetcher() -> PoliteFetcher:
    return PoliteFetcher(
        user_agent=USER_AGENT,
        policies={
            # Discovery. EBI answers a search page in ~15 s on its own; 2/s is already more than
            # the host can deliver and keeps us from stacking requests behind that latency.
            "www.ebi.ac.uk": HostPolicy(requests_per_second=2.0, timeout_seconds=60.0),
            # Full text. Measured 163 KB/s per article and no 503s, and every S3 GET is a distinct
            # object, so pacing here is about being a good citizen rather than about capacity.
            "pmc-oa-opendata.s3.amazonaws.com": HostPolicy(requests_per_second=10.0,
                                                          timeout_seconds=45.0),
            "api.medrxiv.org": HostPolicy(requests_per_second=1.0),
            "api.biorxiv.org": HostPolicy(requests_per_second=1.0),
            # The publisher hosts serve the JATS XML and they rate-limit hard: measured
            # 2026-11-24, fetching 400 preprints at 1 req/s produced 429s and then 403s, and the
            # 403 was earned rather than declared. Two seconds between requests is what keeps the
            # run under their threshold.
            "www.medrxiv.org": HostPolicy(requests_per_second=0.5, max_attempts=4,
                                         backoff_base_seconds=5.0, timeout_seconds=45.0),
            "www.biorxiv.org": HostPolicy(requests_per_second=0.5, max_attempts=4,
                                          backoff_base_seconds=5.0, timeout_seconds=45.0),
        },
        max_requests=100_000,
    )


def _payload_bytes(response: Any) -> bytes:
    """The bytes live in ``payload``, not ``body``.

    ``PoliteFetcher.get_bytes`` documents this deliberately: ``body`` stays empty so that a caller
    reading it first cannot mistake a decoded PDF for text. Reading ``body`` here is what made the
    first run report ten open-access articles as "served no full text".
    """
    payload = getattr(response, "payload", None)
    if isinstance(payload, (bytes, bytearray)):
        return bytes(payload)
    return b""


def _slug(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", name)[:120]


def _out_path(out_dir: Path, identifier: str) -> Path:
    return out_dir / f"paper_{_slug(identifier)}.json"


def _store(out_dir: Path, identifier: str, *, url: str, journal: str, licence: str,
           title: str, published_at: str, document, extra: dict[str, Any]) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    sections = document.sections
    payload = {
        "kind": "paper",
        "identifier": identifier,
        "url": url,
        "status": "text",
        "http_status": 200,
        "bytes": extra.get("bytes", 0),
        "char_count": document.body_chars,
        "text_chars": document.body_chars + len(document.abstract),
        "sections": sections,
        "canonical": document.canonical,
        "headings": document.headings,
        "abstract": document.abstract,
        "title": title or document.title,
        "journal": journal or document.journal,
        "licence": licence or document.licence,
        "published_at": published_at,
        "reference_count": document.reference_count,
        "from_cache": extra.get("from_cache", False),
        "note": extra.get("note"),
    }
    path = _out_path(out_dir, identifier)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    text_path = path.with_suffix(".txt")
    body = "\n\n".join(f"{heading}\n{body}"
                       for heading, body in sections.items())
    if document.abstract:
        body = f"ABSTRACT\n{document.abstract}\n\n{body}"
    text_path.write_text(body, encoding="utf-8")
    return payload


def _store_failure(out_dir: Path, identifier: str, *, url: str, status: str, reason: str) -> None:
    """Record why a record has no full text, in a vocabulary that says which kind of absence it is.

    ``failed`` is a fault in this tool or a transient upstream problem. ``access_restricted`` is
    the operator refusing automated clients - measured 2026-11-24: www.medrxiv.org answers 403 to
    the project user agent, to ``Python-urllib``, and to both XML Accept headers, so it is a
    client-type block and not an identity problem. ``empty_record`` is a record that carries only
    front matter. Collapsing those three into "failed" would misreport a documented refusal as a
    bug, which is exactly what this repository refuses to do.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    payload = {"kind": "paper", "identifier": identifier, "url": url, "status": status,
               "sections": {}, "char_count": 0, "note": reason}
    _out_path(out_dir, identifier).write_text(
        json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def fetch_europepmc(fetcher: PoliteFetcher, out_dir: Path, query: str, limit: int) -> dict[str, int]:
    stats = {"candidates": 0, "stored": 0, "skipped_cached": 0, "no_fulltext": 0, "failed": 0}
    cursor = "*"
    while stats["candidates"] < limit:
        term = f"({query}) AND OPEN_ACCESS:y AND IN_PMC:y"
        data = fetcher.get_json(EUROPEPMC_SEARCH, params={
            "query": term, "format": "json", "pageSize": PAGE, "resultType": "core",
            "cursorMark": cursor,
        }, allow_not_found=True) or {}
        rows = ((data.get("resultList") or {}).get("result") or [])
        if not rows:
            break
        for row in rows:
            if stats["candidates"] >= limit:
                break
            pmcid = str(row.get("pmcid") or "").strip()
            if not pmcid:
                continue
            stats["candidates"] += 1
            identifier = pmcid
            if _out_path(out_dir, identifier).exists():
                stats["skipped_cached"] += 1
                continue
            url = PMC_OA_BUCKET.format(pmcid=pmcid)
            body = b""
            source_url = url
            try:
                body = _payload_bytes(fetcher.get_bytes(url, allow_not_found=True))
            except RateLimited:
                stats["retry_later"] = stats.get("retry_later", 0) + 1
                continue
            except Exception:  # noqa: BLE001 - a mirror miss falls through to the EBI attempt
                body = b""
            if not body:
                # The S3 mirror lags the index for very recent articles, so the EBI endpoint gets
                # exactly one attempt. It is slow, which is why it is not the primary.
                time.sleep(SECONDS_BETWEEN)
                source_url = EUROPEPMC_FULLTEXT.format(pmcid=pmcid)
                try:
                    body = _payload_bytes(fetcher.get_bytes(source_url, allow_not_found=True))
                except RateLimited:
                    stats["retry_later"] = stats.get("retry_later", 0) + 1
                    continue
                except Exception as error:  # noqa: BLE001
                    _store_failure(out_dir, identifier, url=source_url, status="failed",
                                   reason=f"{type(error).__name__}: {error}")
                    stats["failed"] += 1
                    continue
            if not body:
                _store_failure(out_dir, identifier, url=source_url, status="not_published",
                               reason=("absent from the PMC Open Access S3 mirror and from the "
                                       "Europe PMC full-text endpoint"))
                stats["no_fulltext"] += 1
                continue
            try:
                document = parse_jats(body)
            except JatsError as error:
                status = ("empty_record"
                          if "no body text or abstract" in str(error) else "failed")
                _store_failure(out_dir, identifier, url=source_url, status=status,
                               reason=str(error))
                if status == "failed":
                    stats["failed"] += 1
                else:
                    stats["no_fulltext"] += 1
                continue
            _store(out_dir, identifier, url=source_url,
                   journal=str((row.get("journalInfo") or {}).get("journal", {}).get("title") or ""),
                   licence=str(row.get("license") or ""),
                   title=str(row.get("title") or ""),
                   published_at=str(row.get("firstPublicationDate") or ""),
                   document=document,
                   extra={"bytes": len(body)})
            stats["stored"] += 1
        cursor = data.get("nextCursorMark")
        if not cursor or cursor == "*":
            break
    return stats


def fetch_preprints(fetcher: PoliteFetcher, out_dir: Path, days: int, limit: int,
                    servers: Iterable[str] = ("medrxiv", "biorxiv")) -> dict[str, int]:
    stats = {"candidates": 0, "stored": 0, "skipped_cached": 0, "no_fulltext": 0, "failed": 0,
             "access_restricted": 0}
    end = date.today()
    start = end - timedelta(days=max(1, days))
    #: Consecutive refusals from one host before the whole server is abandoned for this run.
    #: Measured: the very first request already returns 403, so continuing would mean issuing
    #: hundreds of requests that are known to be refused.
    REFUSAL_BREAKER = 3
    for server in servers:
        offset = 0
        refusals = 0
        abandon_server = False
        while stats["candidates"] < limit and not abandon_server:
            data = fetcher.get_json(
                PREPRINT_DETAILS.format(server=server, start=start.isoformat(),
                                        end=end.isoformat(), offset=offset),
                allow_not_found=True) or {}
            rows = data.get("collection") or []
            if not rows:
                break
            for row in rows:
                if stats["candidates"] >= limit:
                    break
                jats = str(row.get("jatsxml") or "").strip()
                doi = str(row.get("doi") or "").strip()
                if not jats or not doi:
                    continue
                stats["candidates"] += 1
                identifier = f"{server}:{doi}"
                if _out_path(out_dir, identifier).exists():
                    stats["skipped_cached"] += 1
                    continue
                try:
                    response = fetcher.get_bytes(jats, allow_not_found=True)
                except Refused as error:
                    # A 403 from the publisher host is treated as rate-induced, because measured
                    # behaviour is 429 first and 403 after: at 1 req/s, 400 preprints produced 429s
                    # that escalated. Calling that "the operator refuses automated access" would
                    # blame the source for our own pacing, so the note says which one it was.
                    status = "rate_limited_block"
                    _store_failure(
                        out_dir, identifier, url=jats, status=status,
                        reason=("publisher answered 403 after rate limiting; our pacing, not a "
                                f"stated refusal: {error}"))
                    stats["access_restricted"] += 1
                    refusals += 1
                    if refusals >= REFUSAL_BREAKER:
                        abandon_server = True
                        break
                    continue
                except RateLimited:
                    # Transient by definition: no sidecar is written, so the next run retries this
                    # record instead of finding a permanent "failed" marker and skipping it.
                    stats["retry_later"] = stats.get("retry_later", 0) + 1
                    continue
                except Exception as error:  # noqa: BLE001
                    _store_failure(out_dir, identifier, url=jats, status="failed",
                                   reason=f"{type(error).__name__}: {error}")
                    stats["failed"] += 1
                    continue
                refusals = 0
                body = _payload_bytes(response)
                if not body:
                    _store_failure(out_dir, identifier, url=jats, status="not_published",
                                   reason="preprint server served no JATS for this DOI")
                    stats["no_fulltext"] += 1
                    continue
                try:
                    document = parse_jats(body)
                except JatsError as error:
                    # "no body text" is a property of the record (front matter only), not a fault
                    # in this tool. One status is honest; the other blames the pipeline.
                    status = ("empty_record"
                              if "no body text or abstract" in str(error) else "failed")
                    _store_failure(out_dir, identifier, url=jats, status=status,
                                   reason=str(error))
                    if status == "failed":
                        stats["failed"] += 1
                    else:
                        stats["no_fulltext"] += 1
                    continue
                _store(out_dir, identifier, url=f"https://doi.org/{doi}",
                       journal=server, licence=str(row.get("license") or ""),
                       title=str(row.get("title") or ""),
                       published_at=str(row.get("date") or ""),
                       document=document, extra={"bytes": len(body)})
                stats["stored"] += 1
            offset += len(rows)
            total = int(((data.get("messages") or [{}])[0]).get("total") or 0)
            if offset >= total:
                break
    return stats


def status(out_dir: Path) -> dict[str, Any]:
    files = sorted(out_dir.glob("paper_*.json")) if out_dir.exists() else []
    counts: dict[str, int] = {}
    chars = 0
    sections = 0
    for path in files:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        counts[payload.get("status") or "?"] = counts.get(payload.get("status") or "?", 0) + 1
        chars += int(payload.get("char_count") or 0)
        sections += len(payload.get("sections") or {})
    return {"records": len(files), "by_status": counts, "body_chars": chars,
            "sections": sections, "dir": str(out_dir)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", choices=("europepmc", "preprints"), default="europepmc")
    parser.add_argument("--query", default="catheter")
    parser.add_argument("--days", type=int, default=14)
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--out", default=DEFAULT_OUT)
    parser.add_argument("--status", action="store_true")
    args = parser.parse_args()

    out_dir = Path(args.out)
    if args.status:
        print(json.dumps(status(out_dir), ensure_ascii=False, indent=2))
        return 0

    fetcher = _fetcher()
    if args.source == "europepmc":
        stats = fetch_europepmc(fetcher, out_dir, args.query, args.limit)
    else:
        stats = fetch_preprints(fetcher, out_dir, args.days, args.limit)
    print(json.dumps(stats, ensure_ascii=False, indent=2))
    print(json.dumps(status(out_dir), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
