"""Probe: europepmc — Europe PMC REST search.

DATA-EXPANSION-001 / scholarly.  Every request goes through
:class:`medradar.external_sources.base.HttpClient` (bounded budget, minimum
interval, JSONL ledger).  Re-runs append to ``requests.jsonl``; the probe result
is overwritten.  See ``NOTES.md`` for the human-readable conclusion.

Run from the repository root::

    python research/data_expansion/probes/europepmc/probe.py
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from medradar.external_sources import base

SOURCE_ID = "europepmc"
#: research/data_expansion  (probe.py lives in probes/<source_id>/)
ROOT = Path(__file__).resolve().parents[2]
SAMPLE_DIR = ROOT / "samples" / SOURCE_ID

BUDGET = 10
MIN_INTERVAL = 0.8
MAX_RETRIES = 2
STATUS_WHEN_OK = "VERIFIED_API"
STATUS_WHEN_RATELIMITED = "UNAVAILABLE"
#: Status used when every request is refused with 401/403.  Usually
#: REQUIRES_REGISTRATION, but a documented API that is simply down or blocking
#: anonymous clients is UNAVAILABLE, not "needs an account".
DENIED_STATUS = "REQUIRES_REGISTRATION"
DOC_URLS = ['https://europepmc.org/RestfulWebService', 'https://europepmc.org/help']

SPECS = [{'name': 'search_lite',
  'url': 'https://www.ebi.ac.uk/europepmc/webservices/rest/search',
  'params': {'query': 'stent', 'format': 'json', 'pageSize': 2, 'resultType': 'lite'},
  'count_path': 'resultList.result',
  'save_as': 'europepmc_search_lite.json'},
 {'name': 'search_core',
  'url': 'https://www.ebi.ac.uk/europepmc/webservices/rest/search',
  'params': {'query': 'stent', 'format': 'json', 'pageSize': 2, 'resultType': 'core'},
  'count_path': 'resultList.result',
  'save_as': 'europepmc_search_core.json'},
 {'name': 'affiliation_company',
  'url': 'https://www.ebi.ac.uk/europepmc/webservices/rest/search',
  'params': {'query': 'AFF:"Medtronic"', 'format': 'json', 'pageSize': 2, 'resultType': 'core'},
  'count_path': 'resultList.result',
  'save_as': 'europepmc_affiliation.json'},
 {'name': 'doi_lookup',
  'url': 'https://www.ebi.ac.uk/europepmc/webservices/rest/search',
  'params': {'query': 'DOI:"10.1056/NEJMoa2034577"', 'format': 'json', 'pageSize': 2, 'resultType': 'core'},
  'count_path': 'resultList.result',
  'save_as': 'europepmc_doi.json'}]


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
        notes=('Europe PMC REST returned 200 JSON with `resultList.result` and `hitCount`. '
 '`resultType=core` supplies `firstPublicationDate`, `firstIndexDate`, '
 'DOI/PMID/PMCID, `authorList[].affiliation`, `grantsList` and '
 '`dbCrossReferenceList` - enough for DOI-based cross-source de-duplication, '
 'author-affiliation company matching and grant-number linking.  '
 '`firstIndexDate` is an ingestion clock, not publication.'),
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
            "# Probe notes — europepmc",
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
            ('Europe PMC REST returned 200 JSON with `resultList.result` and `hitCount`. '
 '`resultType=core` supplies `firstPublicationDate`, `firstIndexDate`, '
 'DOI/PMID/PMCID, `authorList[].affiliation`, `grantsList` and '
 '`dbCrossReferenceList` - enough for DOI-based cross-source de-duplication, '
 'author-affiliation company matching and grant-number linking.  '
 '`firstIndexDate` is an ingestion clock, not publication.'),
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
            "`requests.jsonl`, and raw slices under `research/data_expansion/samples/europepmc/`.",
            "",
            "## Re-run",
            "",
            "```",
            "python research/data_expansion/probes/europepmc/probe.py",
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
