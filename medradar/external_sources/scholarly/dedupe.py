"""Cross-source de-duplication of scholarly records.

Why this exists
---------------
One paper is routinely present in OpenAlex, Europe PMC, Crossref and PubMed at
the same time.  Counting each row as a separate observation inflates every
downstream number (publication counts, company counts, lead-time samples).  The
DATA-EXPANSION-001 contract says: *an aggregator re-publishing another source's
record is 1 piece of evidence, not 2.*  This module implements that rule.

Two layers, on purpose
----------------------
``canonical_key`` (from :mod:`medradar.external_sources.schema`) is the cheap
first answer: DOI beats PMID beats nothing.  But the three identifiers are not
always present in the same source — Europe PMC may return a DOI+PMID while a
Crossref record has only the DOI.  Taking one key per record would therefore
miss real duplicates.

So clustering is done by **identifier union**: records are nodes, and any two
records sharing *any* authoritative publication identifier (DOI, PMID, PMCID)
are joined.  Connected components are the unique works.  This is still
deterministic (no titles, no fuzzy matching, no thresholds), and it degrades
honestly: a record with no publication identifier stays its own singleton and is
counted as *non-deduplicable* rather than silently merged.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Iterable, Mapping, Sequence

#: Identifier schemes that identify a *publication* (not a device, trial, …).
PUBLICATION_SCHEMES: tuple[str, ...] = ("doi", "pmid", "pmcid")

#: Schemes that can never be used for cross-source publication de-duplication.
EXCLUDED_SCHEMES: frozenset[str] = frozenset(
    {"nct", "di", "510k", "pma", "patent_no", "award_id", "openalex"}
)


def _normalise(scheme: str, value: Any) -> tuple[str, str] | None:
    scheme = str(scheme or "").strip().lower()
    if scheme not in PUBLICATION_SCHEMES:
        return None
    text = str(value or "").strip()
    if not text:
        return None
    if scheme == "doi":
        lowered = text.lower()
        for prefix in ("https://doi.org/", "http://doi.org/", "https://dx.doi.org/", "doi:"):
            if lowered.startswith(prefix):
                lowered = lowered[len(prefix) :]
        text = lowered.strip()
        if not text:
            return None
    elif scheme == "pmid":
        text = text.lstrip("0") or "0"
        if not text.isdigit():
            return None
    elif scheme == "pmcid":
        text = text.upper()
        if text.startswith("PMC"):
            text = text[3:]
        if not text.isdigit():
            return None
        text = text.lstrip("0") or "0"
    return scheme, text


def publication_identifiers(record: Mapping[str, Any]) -> list[tuple[str, str]]:
    """Every usable ``(scheme, value)`` publication identifier on a record."""
    pairs: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for ident in record.get("identifiers", []) or []:
        pair = _normalise(str(ident.get("scheme", "")), ident.get("value"))
        if pair and pair not in seen:
            seen.add(pair)
            pairs.append(pair)
    return pairs


@dataclass
class Cluster:
    """One unique work and the records that describe it."""

    records: list[dict[str, Any]] = field(default_factory=list)
    shared: list[tuple[str, str]] = field(default_factory=list)

    @property
    def sources(self) -> list[str]:
        out: list[str] = []
        for record in self.records:
            source = str(record.get("source_id", ""))
            if source and source not in out:
                out.append(source)
        return sorted(out)

    @property
    def canonical_keys(self) -> list[str]:
        keys: list[str] = []
        for record in self.records:
            key = record.get("canonical_key")
            if key and key not in keys:
                keys.append(str(key))
        return sorted(keys)

    def representative(
        self, preference: Sequence[str] = ()
    ) -> dict[str, Any]:
        """Deterministically choose the record whose timestamp we trust most."""
        rank = {source: index for index, source in enumerate(preference)}

        def sort_key(record: Mapping[str, Any]) -> tuple[int, str, str]:
            source = str(record.get("source_id", ""))
            return (
                rank.get(source, len(rank)),
                str(record.get("source_public_at") or record.get("time", {}).get("source_public_at") or ""),
                str(record.get("evidence_id", "")),
            )

        return sorted(self.records, key=sort_key)[0]


def cluster_publications(
    records: Iterable[Mapping[str, Any]],
    *,
    extra_key: Callable[[Mapping[str, Any]], str | None] | None = None,
) -> list[Cluster]:
    """Group records into unique works by identifier union (deterministic).

    ``extra_key`` is an escape hatch for identifiers a caller derived itself
    (e.g. a normalised grant number); it is never used by default.
    """
    items = [dict(record) for record in records]
    parent = list(range(len(items)))

    def find(index: int) -> int:
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    def union(left: int, right: int) -> None:
        root_left, root_right = find(left), find(right)
        if root_left != root_right:
            if root_left < root_right:
                parent[root_right] = root_left
            else:
                parent[root_left] = root_right

    owner: dict[tuple[str, str], int] = {}
    for index, record in enumerate(items):
        pairs = publication_identifiers(record)
        if extra_key is not None:
            derived = extra_key(record)
            if derived:
                pairs.append(("extra", str(derived)))
        for pair in pairs:
            if pair in owner:
                union(owner[pair], index)
            else:
                owner[pair] = index

    groups: dict[int, Cluster] = {}
    for index, record in enumerate(items):
        root = find(index)
        groups.setdefault(root, Cluster()).records.append(record)

    for cluster in groups.values():
        counts: dict[tuple[str, str], int] = {}
        for record in cluster.records:
            for pair in publication_identifiers(record):
                counts[pair] = counts.get(pair, 0) + 1
        cluster.shared = sorted(
            (pair for pair, count in counts.items() if count >= 2),
            key=lambda pair: (PUBLICATION_SCHEMES.index(pair[0]), pair[1]),
        )

    ordered = sorted(
        groups.values(),
        key=lambda cluster: (
            str(cluster.representative(TIME_SOURCE_PREFERENCE).get("canonical_key") or ""),
            str(cluster.representative(TIME_SOURCE_PREFERENCE).get("evidence_id") or ""),
        ),
    )
    return ordered


#: Re-exported here so callers do not need to import from ``_common``.
TIME_SOURCE_PREFERENCE: tuple[str, ...] = (
    "europepmc",
    "crossref",
    "openalex",
    "pubmed_eutils",
    "semantic_scholar",
    "openaire",
)


def _source_pair_label(sources: Sequence[str]) -> str:
    return "+".join(sorted(set(sources)))


def dedupe_report(
    records: Iterable[Mapping[str, Any]],
    *,
    source_order: Sequence[str] | None = None,
) -> dict[str, Any]:
    """Full, explicit de-duplication statistics for one collected batch.

    The report separates *collected records* from *independent works*; the latter
    is the only number that may be used as an evidence count.
    """
    items = [dict(record) for record in records]
    clusters = cluster_publications(items)
    preference = tuple(source_order or TIME_SOURCE_PREFERENCE)

    by_source: dict[str, int] = {}
    for record in items:
        source = str(record.get("source_id", ""))
        by_source[source] = by_source.get(source, 0) + 1

    size_histogram: dict[str, int] = {}
    source_sets: dict[str, int] = {}
    shared_keys: dict[str, int] = {}
    representatives: list[dict[str, Any]] = []
    duplicate_records = 0
    no_identifier = 0
    for cluster in clusters:
        representative = cluster.representative(preference)
        representatives.append(representative)
        size_histogram[str(len(cluster.records))] = (
            size_histogram.get(str(len(cluster.records)), 0) + 1
        )
        label = _source_pair_label(cluster.sources)
        source_sets[label] = source_sets.get(label, 0) + 1
        for key in cluster.canonical_keys:
            shared_keys[key] = shared_keys.get(key, 0) + 1
        duplicate_records += len(cluster.records) - 1
        if not publication_identifiers(representative):
            no_identifier += 1

    total = len(items)
    unique = len(clusters)
    multi_source = sum(1 for cluster in clusters if len(cluster.sources) > 1)
    return {
        "records_collected": total,
        "unique_works": unique,
        "duplicate_records": duplicate_records,
        "duplicate_ratio": round(duplicate_records / total, 4) if total else 0.0,
        "unique_ratio": round(unique / total, 4) if total else 0.0,
        "multi_source_works": multi_source,
        "works_by_record_count": dict(sorted(size_histogram.items())),
        "works_by_source_set": dict(sorted(source_sets.items(), key=lambda kv: (-kv[1], kv[0]))),
        "records_by_source": dict(sorted(by_source.items())),
        "records_without_publication_identifier": no_identifier,
        "representative_sources": _count_sources(representatives),
        "identifier_priority": "doi > pmid > pmcid; records sharing ANY of them are one work",
        "excluded_schemes": sorted(EXCLUDED_SCHEMES),
        "counts_as_independent_evidence": unique,
        "note": (
            "unique_works is the only valid evidence count; records_collected counts "
            "aggregator re-publications of the same work and must not be summed."
        ),
    }


def _count_sources(records: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    out: dict[str, int] = {}
    for record in records:
        source = str(record.get("source_id", "?"))
        out[source] = out.get(source, 0) + 1
    return dict(sorted(out.items()))


def unique_publications(
    records: Iterable[Mapping[str, Any]],
    *,
    source_order: Sequence[str] | None = None,
) -> list[dict[str, Any]]:
    """One representative record per unique work (the de-duplicated evidence set).

    Each representative gains two reporting-only fields:

    * ``duplicate_of`` — ``""`` for the representative itself;
    * ``dedupe`` — ``{"records": n, "sources": [...], "shared_identifiers": [...]}``.

    The record is a *copy*; the caller's originals are never mutated.
    """
    preference = tuple(source_order or TIME_SOURCE_PREFERENCE)
    out: list[dict[str, Any]] = []
    for cluster in cluster_publications(records):
        representative = dict(cluster.representative(preference))
        representative["duplicate_of"] = ""
        representative["dedupe"] = {
            "records": len(cluster.records),
            "sources": cluster.sources,
            "shared_identifiers": [f"{scheme}:{value}" for scheme, value in cluster.shared],
        }
        out.append(representative)
    return out


def duplicate_pairs(
    records: Iterable[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Explicit list of ``(kept, dropped, shared identifier)`` duplicate pairs."""
    preference = tuple(TIME_SOURCE_PREFERENCE)
    pairs: list[dict[str, Any]] = []
    for cluster in cluster_publications(records):
        representative = cluster.representative(preference)
        for record in cluster.records:
            if record is representative:
                continue
            pairs.append(
                {
                    "kept_evidence_id": representative.get("evidence_id"),
                    "kept_source": representative.get("source_id"),
                    "dropped_evidence_id": record.get("evidence_id"),
                    "dropped_source": record.get("source_id"),
                    "shared_identifiers": [
                        f"{scheme}:{value}" for scheme, value in cluster.shared
                    ],
                }
            )
    return pairs
