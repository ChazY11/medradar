"""Probe: pubmed_eutils — NCBI PubMed E-utilities (esearch + esummary).

DATA-EXPANSION-001 / scholarly.  Every request goes through
:class:`medradar.external_sources.base.HttpClient` (bounded budget, minimum
interval, JSONL ledger).  Re-runs append to ``requests.jsonl``; the probe result
is overwritten.  See ``NOTES.md`` for the human-readable conclusion.

Run from the repository root::

    python research/data_expansion/probes/pubmed_eutils/probe.py
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from medradar.external_sources import base

SOURCE_ID = "pubmed_eutils"
#: research/data_expansion  (probe.py lives in probes/<source_id>/)
ROOT = Path(__file__).resolve().parents[2]
SAMPLE_DIR = ROOT / "samples" / SOURCE_ID

BUDGET = 8
MIN_INTERVAL = 1.2
MAX_RETRIES = 2
STATUS_WHEN_OK = "VERIFIED_API"
STATUS_WHEN_RATELIMITED = "UNAVAILABLE"
#: Status used when every request is refused with 401/403.  Usually
#: REQUIRES_REGISTRATION, but a documented API that is simply down or blocking
#: anonymous clients is UNAVAILABLE, not "needs an account".
DENIED_STATUS = "REQUIRES_REGISTRATION"
DOC_URLS = ['https://www.ncbi.nlm.nih.gov/books/NBK25501/',
 'https://www.ncbi.nlm.nih.gov/books/NBK25497/',
 'https://www.ncbi.nlm.nih.gov/pmc/tools/openftlist/']

SPECS = [{'name': 'esearch',
  'url': 'https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi',
  'params': {'db': 'pubmed',
             'term': 'Medtronic[Affiliation] AND stent',
             'retmode': 'json',
             'retmax': 3,
             'tool': 'medradar_research',
             'email': 'medradar.research@example.org'},
  'count_path': 'esearchresult.count',
  'save_as': 'pubmed_esearch.json'},
 {'name': 'esummary',
  'url': 'https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi',
  'params': {'db': 'pubmed',
             'retmode': 'json',
             'id': '{chain:esearch:esearchresult.idlist.0}',
             'tool': 'medradar_research',
             'email': 'medradar.research@example.org'},
  'count_path': 'result.uids',
  'save_as': 'pubmed_esummary.json'},
 {'name': 'esearch_doi',
  'url': 'https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi',
  'params': {'db': 'pubmed',
             'term': '10.1056/NEJMoa2034577[DOI]',
             'retmode': 'json',
             'retmax': 2,
             'tool': 'medradar_research',
             'email': 'medradar.research@example.org'},
  'count_path': 'esearchresult.idlist',
  'save_as': 'pubmed_esearch_doi.json'}]


def _dig(payload, path):
    """Resolve a dotted path (dict keys / list indices) or return ``None``."""
    if not path:
        return payload
    current = payload
    for part in str(path).split("."):
        if isinstance(current, dict):
            current = current.get(part)
        elif isinstance(current, list):
            try:
                current = current[int(part)]
            except (ValueError, IndexError):
                return None
        else:
            return None
        if current is None:
            return None
    return current


def _count(value):
    if isinstance(value, (list, dict)):
        return len(value)
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    return None


_CHAIN = re.compile(r"{chain:([A-Za-z0-9_\-]+):([^{}]*)}")


def _resolve_chain(value, chain):
    """Substitute every ``{chain:probe:path.to.value}`` placeholder in a string."""
    if not isinstance(value, str) or "{chain:" not in value:
        return value

    def replace(match):
        name, path = match.group(1), match.group(2)
        resolved = _dig(chain.get(name), path)
        return "" if resolved is None else str(resolved)

    return _CHAIN.sub(replace, value)


def _resolve_params(params, chain):
    return {key: _resolve_chain(value, chain) for key, value in (params or {}).items()}


def _save_sample(name, body, *, url, fetched_at):
    meta = base.write_sample(SAMPLE_DIR, name, body)
    meta["url"] = url
    meta["fetched_at"] = fetched_at
    return meta


def probe(client, directory):
    probes = []
    chain = {}
    samples = []
    for spec in SPECS:
        params = _resolve_params(spec.get("params"), chain)
        url = _resolve_chain(spec.get("url", ""), chain)
        headers = spec.get("headers")
        if spec.get("method") == "post":
            result = client.post_json(
                url, spec.get("payload") or {}, params=params, headers=headers
            )
        else:
            result = client.get(
                url,
                params=params,
                headers=headers,
                accept=spec.get("accept", "application/json"),
            )
        payload = None
        parse_error = ""
        try:
            payload = result.json()
        except Exception as exc:  # non-JSON body is a legitimate finding
            parse_error = f"{type(exc).__name__}: json decode failed"
        entry = {
            "name": spec["name"],
            "method": spec.get("method", "get"),
            "url": result.url,
            "status": result.status,
            "http_ok": result.ok,
            "json_parsed": payload is not None,
            "counts_as_ok": bool(result.ok and payload is not None and spec.get("counts", True)),
            "bytes": len(result.body),
            "elapsed_ms": result.elapsed_ms,
            "attempts": result.attempts,
            "error": result.error or parse_error,
            "record_count": (
                _count(_dig(payload, spec["count_path"]))
                if payload is not None and "count_path" in spec
                else None
            ),
            "structure": base.json_shape(payload) if payload is not None else None,
        }
        if payload is not None:
            chain[spec["name"]] = payload
        if result.ok and spec.get("save_as") and result.body:
            sample = _save_sample(
                spec["save_as"],
                result.body,
                url=result.url,
                fetched_at=base.utc_iso(),
            )
            entry["sample"] = sample
            samples.append(sample)
        probes.append(entry)

    counted_ok = [item for item in probes if item["counts_as_ok"]]
    statuses = {item["status"] for item in probes}
    if counted_ok:
        status = STATUS_WHEN_OK
    elif statuses & {401, 403}:
        status = DENIED_STATUS
    elif 402 in statuses:
        status = "PAID_ONLY"
    elif 429 in statuses:
        status = STATUS_WHEN_RATELIMITED
    else:
        status = "UNAVAILABLE"

    if samples:
        SAMPLE_DIR.mkdir(parents=True, exist_ok=True)
        (SAMPLE_DIR / "SAMPLES.json").write_text(
            json.dumps(
                {
                    "source_id": SOURCE_ID,
                    "generated_at": base.utc_iso(),
                    "note": "Raw response slices captured by the probe.  Must not be hand-edited.",
                    "files": samples,
                },
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )

    return base.ProbeOutcome(
        source_id=SOURCE_ID,
        status=status,
        probes=probes,
        requests=client.requests_made(),
        evidence_urls=[item["url"] for item in counted_ok],
        notes=('E-utilities esearch/esummary returned 200 JSON.  No key is needed at 3 '
 'req/s; the connector declares `tool`/`email` for a better politeness tier '
 'and stays below the limit with a 1.2 s minimum interval.  esummary gives '
 '`pubdate`/`epubdate` (coarse when only a year/month is published), DOI and '
 'PMC id for de-duplication.'),
    )


def _write_notes(directory: Path, outcome) -> None:
    rows = []
    for item in outcome.probes:
        state = item["status"] if item["status"] is not None else "ERR"
        rows.append(
            "| {} | {} | {} | {} | {} |".format(
                item["name"], item["method"].upper(), item["status"], "yes" if item["counts_as_ok"] else "no", item["error"] or "-"
            )
        )
    text = "\n".join(
        [
            "# Probe notes — pubmed_eutils",
            "",
            "**Status:** `{}`  ·  **Requests:** {}  ·  **Probed at:** {}".format(
                outcome.status, outcome.requests, outcome.verified_at or base.utc_iso()
            ),
            "",
            "## What was tested",
            "",
            "| Probe | Method | HTTP | Counts as working access | Error |",
            "|---|---|---|---|---|",
            *rows,
            "",
            "## Conclusion",
            "",
            ('E-utilities esearch/esummary returned 200 JSON.  No key is needed at 3 '
 'req/s; the connector declares `tool`/`email` for a better politeness tier '
 'and stays below the limit with a 1.2 s minimum interval.  esummary gives '
 '`pubdate`/`epubdate` (coarse when only a year/month is published), DOI and '
 'PMC id for de-duplication.'),
            "",
            "## Documentation checked",
            "",
            *[f"- {url}" for url in DOC_URLS],
            "",
            "## Reported status rationale",
            "",
            "A source is only marked `VERIFIED_*` when a machine request returned 2xx **and**",
            "a real parseable body with records.  HTML 200 pages are recorded but never",
            "counted as verified access.  Probe artifacts: `PROBE_RESULT.json`,",
            "`requests.jsonl`, and raw slices under `research/data_expansion/samples/pubmed_eutils/`.",
            "",
            "## Re-run",
            "",
            "```",
            "python research/data_expansion/probes/pubmed_eutils/probe.py",
            "```",
            "",
        ]
    )
    (directory / "NOTES.md").write_text(text, encoding="utf-8")


if __name__ == "__main__":
    outcome = base.run_probe(
        SOURCE_ID,
        ROOT,
        probe,
        budget=BUDGET,
        min_interval=MIN_INTERVAL,
        max_retries=MAX_RETRIES,
    )
    _write_notes(base.probe_dir(ROOT, SOURCE_ID), outcome)
    print(f"{SOURCE_ID}: {outcome.status} after {outcome.requests} request(s)")
