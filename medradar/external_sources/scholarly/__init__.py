"""Scholarly-literature connectors for DATA-EXPANSION-001.

Verified live on 2026-11-09 (see ``research/data_expansion/probes/<id>/``):

=============  ======================  =========================================
source_id      module                  live status
=============  ======================  =========================================
openalex       :mod:`.openalex`        VERIFIED_API
europepmc      :mod:`.europepmc`       VERIFIED_API
crossref       :mod:`.crossref`        VERIFIED_API
pubmed_eutils  :mod:`.pubmed_eutils`   VERIFIED_API
=============  ======================  =========================================

Only those four have connectors: the contract allows connectors only for
verified sources.  ``semantic_scholar``, ``openaire`` are verified at probe level
but were de-prioritised by the lead; their probe evidence lives in
``research/data_expansion/probes/``.

Every connector returns records that satisfy
:func:`medradar.external_sources.schema.validate_evidence`; timestamps go through
:mod:`medradar.external_sources.timeq`, and company links are emitted at explicit
evidence tiers (funder vs author affiliation vs text mention).

The whole point of this package is that **one paper is one piece of evidence**:
:func:`dedupe.unique_publications` collapses aggregator re-publications before
anything is counted.
"""

from __future__ import annotations

from typing import Any, Iterable, Mapping

from . import crossref, dedupe, europepmc, linking, openalex, pubmed_eutils

__all__ = [
    "crossref",
    "dedupe",
    "europepmc",
    "linking",
    "openalex",
    "pubmed_eutils",
    "SOURCES",
    "collect_publications",
]

#: Connectors that are cleared to run (VERIFIED_API only).
SOURCES: dict[str, Any] = {
    "openalex": openalex,
    "europepmc": europepmc,
    "crossref": crossref,
    "pubmed_eutils": pubmed_eutils,
}

#: Per-connector query keyword, so one search phrase works across all four.
_QUERY_PARAM = {
    "openalex": "query",
    "europepmc": "query",
    "crossref": "query",
    "pubmed_eutils": "term",
}


def collect_publications(
    client: Any,
    *,
    query: str,
    limit_per_source: int = 25,
    sources: Iterable[str] | None = None,
    max_pages: int = 2,
) -> dict[str, Any]:
    """Collect from every cleared source, then de-duplicate across sources.

    Returns a dict with the raw records, the de-duplicated representatives and
    the :func:`dedupe.dedupe_report` statistics.  A failing source is reported
    in ``errors`` instead of aborting the batch, because a partial batch with an
    honest error list is still usable evidence.
    """
    chosen = list(sources) if sources else list(SOURCES)
    records: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    by_source: dict[str, int] = {}
    for source_id in chosen:
        module = SOURCES.get(source_id)
        if module is None:
            errors.append({"source_id": source_id, "error": "no verified connector"})
            continue
        kwargs: dict[str, Any] = {_QUERY_PARAM[source_id]: query, "limit": limit_per_source}
        if source_id != "pubmed_eutils":
            kwargs["max_pages"] = max_pages
        try:
            batch = module.collect(client, **kwargs)
        except Exception as exc:  # one source must not sink the batch
            errors.append({"source_id": source_id, "error": f"{type(exc).__name__}: {exc}"})
            continue
        by_source[source_id] = len(batch)
        records.extend(batch)
    report = dedupe.dedupe_report(records)
    return {
        "query": query,
        "limit_per_source": limit_per_source,
        "records_by_source": by_source,
        "records": records,
        "unique": dedupe.unique_publications(records),
        "dedupe": report,
        "errors": errors,
    }


def company_signal_report(records: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """Count company links by evidence tier, keeping candidates out of totals.

    Three signals are reported separately because they are not the same claim:
    ``funder`` (the firm paid for the work), ``author_affiliation`` (an author
    works there) and ``text_mention`` (the name merely appears).  Only the first
    two can be produced by the connectors in this package.
    """
    tiers: dict[str, dict[str, Any]] = {}
    for record in records:
        for ref in record.get("entity_refs", []) or []:
            evidence = ref.get("evidence") or {}
            tier = str(evidence.get("signal") or "unspecified")
            bucket = tiers.setdefault(
                tier, {"links": 0, "confirmed": 0, "candidates": 0, "by_company": {}}
            )
            bucket["links"] += 1
            if str(ref.get("method")) == "candidate":
                bucket["candidates"] += 1
            else:
                bucket["confirmed"] += 1
            company = str(ref.get("resolved_key"))
            bucket["by_company"][company] = bucket["by_company"].get(company, 0) + 1
    for bucket in tiers.values():
        bucket["by_company"] = dict(sorted(bucket["by_company"].items()))
    return dict(sorted(tiers.items()))
