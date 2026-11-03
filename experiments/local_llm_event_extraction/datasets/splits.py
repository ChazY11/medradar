"""Grouped, deterministic train/validation/test assignment with leakage guards.

Why groups, not cases
---------------------
The same company's documents are near-duplicates of each other in tone, template
and entity surface.  A random case-level split would put one press release in
train and its follow-up in test, and the resulting score would measure memorised
phrasing rather than extraction.  So the split unit is the ``group`` (company /
document family), assigned by a hash of ``(seed, group)``, and a group may appear
in exactly one split.

Why a hard failure
------------------
If the assignment ever produces a group in two splits, or a near-duplicate text in
two splits, the run is not comparable to any other run.  The functions here raise
instead of returning a silently biased manifest.  ``assert_no_leakage`` is the
same check exposed for tests and for the benchmark's pre-flight.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import replace
from typing import Iterable, Sequence

from ..contracts import DatasetCase, DatasetManifest

SPLITS: tuple[str, ...] = ("train", "validation", "test")
DEFAULT_RATIOS: tuple[float, float, float] = (0.6, 0.2, 0.2)
DEFAULT_SEED = 20261104
_NEAR_DUPLICATE_THRESHOLD = 0.8
_SHINGLE_SIZE = 5
_WHITESPACE = re.compile(r"\s+")


def _hash_fraction(seed: int, group: str) -> float:
    digest = hashlib.sha256(f"{seed}|{group}".encode("utf-8")).hexdigest()
    return int(digest[:16], 16) / float(1 << 64)


def _split_counts(total: int, ratios: Sequence[float]) -> list[int]:
    if len(ratios) != len(SPLITS):
        raise ValueError(f"ratios must have {len(SPLITS)} entries, got {len(ratios)}")
    if any(ratio < 0 for ratio in ratios):
        raise ValueError("ratios must be non-negative")
    if abs(sum(ratios) - 1.0) > 1e-6:
        raise ValueError(f"ratios must sum to 1.0, got {sum(ratios)}")
    raw = [ratio * total for ratio in ratios]
    counts = [int(value) for value in raw]
    remainder = total - sum(counts)
    order = sorted(range(len(ratios)), key=lambda index: (-(raw[index] - counts[index]), index))
    for index in order[:remainder]:
        counts[index] += 1
    # Guarantee a usable split when there are enough groups for one, so a 7-group
    # dataset never silently reports "test metrics unavailable".
    if total >= len(SPLITS):
        for index in range(len(SPLITS)):
            if counts[index] == 0:
                donor = max(range(len(SPLITS)), key=lambda i: counts[i])
                if counts[donor] > 1:
                    counts[donor] -= 1
                    counts[index] = 1
    return counts


def _normalise_text(text: str) -> str:
    return _WHITESPACE.sub(" ", text.strip().lower())


def _shingles(text: str) -> frozenset[str]:
    normalised = _normalise_text(text)
    if len(normalised) <= _SHINGLE_SIZE:
        return frozenset({normalised})
    return frozenset(
        normalised[index : index + _SHINGLE_SIZE]
        for index in range(0, len(normalised) - _SHINGLE_SIZE + 1)
    )


def _jaccard(left: frozenset[str], right: frozenset[str]) -> float:
    if not left and not right:
        return 1.0
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


def near_duplicate_pairs(cases: Iterable[DatasetCase]) -> list[tuple[str, str, float]]:
    """Pairs of cases whose normalised 5-gram shingles are too similar.

    Deliberately simple (stdlib only) and deterministic.  It is a guard against
    accidentally shipping templated documents across splits, not a plagiarism
    detector.
    """
    materialised = list(cases)
    shingles = [_shingles(case.document.text) for case in materialised]
    pairs: list[tuple[str, str, float]] = []
    for left in range(len(materialised)):
        for right in range(left + 1, len(materialised)):
            score = _jaccard(shingles[left], shingles[right])
            if score >= _NEAR_DUPLICATE_THRESHOLD:
                pairs.append((materialised[left].case_id, materialised[right].case_id, score))
    return pairs


def assign_grouped_splits(
    cases: Sequence[DatasetCase],
    *,
    ratios: Sequence[float] = DEFAULT_RATIOS,
    seed: int = DEFAULT_SEED,
) -> DatasetManifest:
    """Assign every case to a split by group, deterministically.

    Groups are ordered by ``sha256(f"{seed}|{group}")`` and then allocated to
    train/validation/test by the requested ratios.  The same inputs always produce
    the same manifest; adding a group may reshuffle the others, which is why the
    seed and the group list are recorded in the manifest.
    """
    materialised = list(cases)
    if not materialised:
        raise ValueError("cannot assign splits to an empty case list")
    groups: list[str] = []
    seen: set[str] = set()
    for case in materialised:
        group = case.group or case.case_id
        if group not in seen:
            seen.add(group)
            groups.append(group)
    group_order = sorted(groups, key=lambda group: (_hash_fraction(seed, group), group))

    counts = _split_counts(len(group_order), ratios)
    assigned: dict[str, str] = {}
    cursor = 0
    for split, count in zip(SPLITS, counts):
        for group in group_order[cursor : cursor + count]:
            assigned[group] = split
        cursor += count
    if cursor != len(group_order):  # pragma: no cover - arithmetic guard
        raise ValueError("split allocation did not cover every group")

    assigned_cases = tuple(
        replace(case, split=assigned[case.group or case.case_id]) for case in materialised
    )
    manifest = DatasetManifest(
        name="grouped-split-v0",
        version="v0",
        cases=assigned_cases,
        notes=(
            f"grouped split seed={seed} ratios={tuple(ratios)}; "
            f"{len(group_order)} groups, {len(assigned_cases)} cases"
        ),
    )
    # Never return a leaking manifest: this is the point of the module.
    assert_no_leakage(manifest)
    return manifest


def assert_no_leakage(manifest: DatasetManifest) -> None:
    """Raise ``ValueError`` if a group or a near-duplicate text crosses splits."""
    group_to_splits: dict[str, set[str]] = {}
    unassigned: list[str] = []
    for case in manifest.cases:
        if case.split not in SPLITS:
            unassigned.append(case.case_id)
            continue
        group = case.group or case.case_id
        group_to_splits.setdefault(group, set()).add(case.split)
    if unassigned:
        raise ValueError(f"case(s) have no usable split: {unassigned}")
    leaked = {group: sorted(splits) for group, splits in group_to_splits.items() if len(splits) > 1}
    if leaked:
        raise ValueError(f"group leakage across splits: {leaked}")

    duplicate_pairs: list[tuple[str, str, float]] = []
    for left in range(len(manifest.cases)):
        for right in range(left + 1, len(manifest.cases)):
            first = manifest.cases[left]
            second = manifest.cases[right]
            if first.split == second.split:
                continue
            score = _jaccard(_shingles(first.document.text), _shingles(second.document.text))
            if score >= _NEAR_DUPLICATE_THRESHOLD:
                duplicate_pairs.append((first.case_id, second.case_id, score))
    if duplicate_pairs:
        raise ValueError(f"near-duplicate document text crosses splits: {duplicate_pairs}")


__all__ = [
    "DEFAULT_RATIOS",
    "DEFAULT_SEED",
    "SPLITS",
    "assign_grouped_splits",
    "assert_no_leakage",
    "near_duplicate_pairs",
]
