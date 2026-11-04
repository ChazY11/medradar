"""Duplicate detection: within one document, and across documents for leakage.

The benchmark needs two different duplicate notions:

* **Within-document duplication** -- one extractor emitted the same event twice.
  The second and later occurrences are quarantined with ``DUPLICATE_EVENT``; the
  first is judged normally.  This is a *model* error, so it belongs in the error
  taxonomy.
* **Cross-document duplication** -- the same event text appears in two documents
  that end up in different splits.  That is a *dataset* leak, not a model error,
  so it is reported by :func:`find_duplicate_clusters` to the split builder rather
  than by the validator.

What counts as "the same"
--------------------------
An exact duplicate pair shares ``(canonical_id, event_category, normalised
event_date)``.  That key is only usable when all three components are actually
asserted; the same company and category with *no* date is not automatically a
duplicate, because two distinct events with unknown dates are a legitimate
output.  Otherwise a pair is a duplicate when the Jaccard similarity of its
evidence-quote word shingles is at least ``duplicate_jaccard_threshold``.

Shingles are word 3-grams over NFC/whitespace-normalised, casefolded quote text
(whole-word unigrams for quotes shorter than three words).  This is deliberately
crude: it is a duplicate *detector*, not a semantic matcher, and it never repairs
or merges anything.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Sequence

from .evidence import normalise_text
from .timefields import parse_date_value

__all__ = [
    "SHINGLE_SIZE",
    "DuplicateMatch",
    "DuplicateClusterMember",
    "DuplicateCluster",
    "dedup_key",
    "quote_tokens",
    "quote_shingles",
    "event_shingles",
    "jaccard",
    "find_duplicates",
    "find_duplicate_clusters",
]

SHINGLE_SIZE = 3
"""Word shingle width used for quote-similarity duplicates."""


def _as_payload(value: Any) -> Mapping[str, Any]:
    """Accept either an event payload mapping or an event object with to_dict()."""
    if isinstance(value, Mapping):
        return value
    to_dict = getattr(value, "to_dict", None)
    if callable(to_dict):
        payload = to_dict()
        if isinstance(payload, Mapping):
            return payload
    raise TypeError(
        "duplicate detection expects event payload mappings or objects with a "
        f"to_dict() returning a mapping, got {type(value).__name__}"
    )


# ------------------------------------------------------------------ dedup key
def _normalised_date(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    parsed = parse_date_value(value)
    if parsed is not None:
        return parsed.iso
    return value.strip()


def _normalised_product(event_payload: Mapping[str, Any]) -> str:
    """Casefolded, whitespace-collapsed product string (may be empty)."""
    product = event_payload.get("product_or_technology")
    if not isinstance(product, str):
        return ""
    return " ".join(product.split()).casefold()


def dedup_key(event_payload: Mapping[str, Any]) -> str:
    """``canonical_id|category|normalised_date|normalised_product``.

    v2 fix: the product is part of the key.  In v1 two genuinely different
    products cleared by the same company on the same day collapsed into one
    ``DUPLICATE_EVENT`` and the second was quarantined -- a same-day
    different-product false duplicate.  Two *assertions of the same product* on
    the same day still collapse, which is what the duplicate rule is for.
    """
    company = event_payload.get("company")
    canonical_id = ""
    if isinstance(company, Mapping) and isinstance(company.get("canonical_id"), str):
        canonical_id = company["canonical_id"].strip()
    category = event_payload.get("event_category")
    category = category.strip() if isinstance(category, str) else ""
    date = _normalised_date(event_payload.get("event_date"))
    product = _normalised_product(event_payload)
    return f"{canonical_id}|{category}|{date}|{product}"


def _key_is_complete(event_payload: Mapping[str, Any]) -> bool:
    company = event_payload.get("company")
    canonical_id = ""
    if isinstance(company, Mapping) and isinstance(company.get("canonical_id"), str):
        canonical_id = company["canonical_id"].strip()
    category = event_payload.get("event_category")
    category = category.strip() if isinstance(category, str) else ""
    date = _normalised_date(event_payload.get("event_date"))
    return bool(canonical_id) and bool(category) and bool(date)


# --------------------------------------------------------------------- shingles
def quote_tokens(quote: str) -> tuple[str, ...]:
    """Normalised, casefolded word tokens of one quote."""
    return tuple(normalise_text(quote).casefold().split())


def quote_shingles(quote: str) -> frozenset[str]:
    """Word ``SHINGLE_SIZE``-grams of one quote (unigrams when it is short)."""
    tokens = quote_tokens(quote)
    if not tokens:
        return frozenset()
    if len(tokens) < SHINGLE_SIZE:
        return frozenset(tokens)
    return frozenset(
        " ".join(tokens[index : index + SHINGLE_SIZE])
        for index in range(len(tokens) - SHINGLE_SIZE + 1)
    )


def event_shingles(event_payload: Mapping[str, Any]) -> frozenset[str]:
    """Union of shingle sets over all evidence quotes of one event."""
    union: set[str] = set()
    evidence = event_payload.get("evidence")
    if isinstance(evidence, Sequence) and not isinstance(evidence, (str, bytes)):
        for span in evidence:
            if isinstance(span, Mapping) and isinstance(span.get("quote"), str):
                union.update(quote_shingles(span["quote"]))
    return frozenset(union)


def jaccard(left: Iterable[str], right: Iterable[str]) -> float:
    """Jaccard similarity of two sets; 0.0 when either is empty."""
    left_set, right_set = frozenset(left), frozenset(right)
    if not left_set or not right_set:
        return 0.0
    union = left_set | right_set
    if not union:
        return 0.0
    return len(left_set & right_set) / len(union)


# ----------------------------------------------------------------- within-document
@dataclass(frozen=True)
class DuplicateMatch:
    """One duplicate relationship between two event positions in a document."""

    first_index: int
    second_index: int
    basis: str
    score: float
    dedup_key: str
    detail: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "first_index": self.first_index,
            "second_index": self.second_index,
            "basis": self.basis,
            "score": self.score,
            "dedup_key": self.dedup_key,
            "detail": self.detail,
        }


def _pair_match(
    first: Mapping[str, Any],
    second: Mapping[str, Any],
    first_index: int,
    second_index: int,
    threshold: float,
) -> DuplicateMatch | None:
    key = dedup_key(first)
    if key != dedup_key(second):
        key = dedup_key(second)
    if (
        _key_is_complete(first)
        and _key_is_complete(second)
        and dedup_key(first) == dedup_key(second)
    ):
        return DuplicateMatch(
            first_index=first_index,
            second_index=second_index,
            basis="dedup_key",
            score=1.0,
            dedup_key=dedup_key(first),
            detail=f"same (canonical_id, event_category, normalised event_date) key {dedup_key(first)!r}",
        )
    score = jaccard(event_shingles(first), event_shingles(second))
    if score >= threshold:
        return DuplicateMatch(
            first_index=first_index,
            second_index=second_index,
            basis="quote_shingles",
            score=score,
            dedup_key=key,
            detail=(
                f"evidence-quote shingle Jaccard {score:.3f} >= threshold {threshold:.3f} "
                f"with event {first_index}"
            ),
        )
    return None


def find_duplicates(
    event_payloads: Sequence[Mapping[str, Any]],
    *,
    threshold: float = 0.85,
) -> tuple[DuplicateMatch, ...]:
    """Every duplicate pair among within-document event payloads.

    Quadratic in the number of events, which the schema caps at
    ``max_events_per_document`` (20 by default) -- a deliberate, bounded cost.
    """
    payloads = [_as_payload(payload) for payload in event_payloads]
    matches: list[DuplicateMatch] = []
    for second_index in range(len(payloads)):
        for first_index in range(second_index):
            match = _pair_match(
                payloads[first_index],
                payloads[second_index],
                first_index,
                second_index,
                threshold,
            )
            if match is not None:
                matches.append(match)
    return tuple(matches)


# ----------------------------------------------------------------- cross-document
@dataclass(frozen=True)
class DuplicateClusterMember:
    """One event inside a cross-document duplicate cluster."""

    doc_id: str
    index: int

    def to_dict(self) -> dict[str, Any]:
        return {"doc_id": self.doc_id, "index": self.index}


@dataclass(frozen=True)
class DuplicateCluster:
    """A set of events that duplicate each other across documents (leak check)."""

    members: tuple[DuplicateClusterMember, ...]
    basis: str
    score: float
    dedup_key: str

    @property
    def doc_ids(self) -> tuple[str, ...]:
        return tuple(sorted({member.doc_id for member in self.members}))

    def to_dict(self) -> dict[str, Any]:
        return {
            "members": [member.to_dict() for member in self.members],
            "basis": self.basis,
            "score": self.score,
            "dedup_key": self.dedup_key,
            "doc_ids": list(self.doc_ids),
        }


def _normalise_cluster_input(
    items: Mapping[str, Sequence[Any]]
    | Sequence[tuple[str, Any]],
) -> list[tuple[str, int, Mapping[str, Any]]]:
    normalised: list[tuple[str, int, Mapping[str, Any]]] = []
    if isinstance(items, Mapping):
        for doc_id, payloads in items.items():
            for index, payload in enumerate(payloads):
                normalised.append((str(doc_id), index, _as_payload(payload)))
        return normalised
    for entry in items:
        doc_id, payload = entry
        normalised.append((str(doc_id), len(normalised), _as_payload(payload)))
    return normalised


def find_duplicate_clusters(
    items: Mapping[str, Sequence[Any]]
    | Sequence[tuple[str, Any]],
    *,
    threshold: float = 0.85,
) -> tuple[DuplicateCluster, ...]:
    """Group events that duplicate each other, across documents.

    Accepts either ``{doc_id: [event_payload, ...]}`` or a flat sequence of
    ``(doc_id, event_payload)`` pairs; a "payload" may be a mapping or an object
    with ``to_dict()`` (e.g. an ``EventExtraction``).  Used by the benchmark's
    leakage check: every cluster spanning more than one document is evidence that
    a split would leak.  Quadratic in the number of events, which is fine for the
    sizes a leakage audit is run at; the helper is intentionally not wired into
    the per-document validator hot path.
    """
    entries = _normalise_cluster_input(items)
    parent = list(range(len(entries)))

    def find(position: int) -> int:
        while parent[position] != position:
            parent[position] = parent[parent[position]]
            position = parent[position]
        return position

    def union(left: int, right: int) -> None:
        root_left, root_right = find(left), find(right)
        if root_left != root_right:
            parent[root_right] = root_left

    for second in range(len(entries)):
        for first in range(second):
            match = _pair_match(
                entries[first][2],
                entries[second][2],
                first,
                second,
                threshold,
            )
            if match is not None:
                union(first, second)

    grouped: dict[int, list[int]] = {}
    for position in range(len(entries)):
        grouped.setdefault(find(position), []).append(position)

    clusters: list[DuplicateCluster] = []
    for root in sorted(grouped):
        positions = grouped[root]
        if len(positions) < 2:
            continue
        members = tuple(
            sorted(
                (DuplicateClusterMember(doc_id=entries[pos][0], index=entries[pos][1]) for pos in positions),
                key=lambda member: (member.doc_id, member.index),
            )
        )
        keys = {dedup_key(entries[pos][2]) for pos in positions}
        complete = all(_key_is_complete(entries[pos][2]) for pos in positions)
        if complete and len(keys) == 1:
            basis, score = "dedup_key", 1.0
        else:
            basis = "quote_shingles"
            scores = [
                jaccard(event_shingles(entries[a][2]), event_shingles(entries[b][2]))
                for a in positions
                for b in positions
                if a < b
            ]
            score = min(scores) if scores else 0.0
        clusters.append(
            DuplicateCluster(
                members=members,
                basis=basis,
                score=score,
                dedup_key=sorted(keys)[0] if len(keys) == 1 else "",
            )
        )
    clusters.sort(key=lambda cluster: (cluster.doc_ids, cluster.members))
    return tuple(clusters)
