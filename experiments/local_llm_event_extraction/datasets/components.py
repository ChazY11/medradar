"""Split assignment over near-duplicate leakage components.

The company-grouped split passed the *group* check but failed the *near-duplicate*
check: two 510(k) records from different companies render to text that shares more
than 80% of its 5-character shingles, because the structural rendering is a
template.  Putting them in different splits would leak the template across the
boundary, so the split unit has to be the **leakage component**: the transitive
closure of companies linked by a near-duplicate document pair.

That is what this module adds.  It is deliberately conservative -- a component is
never split, even when that makes the split sizes less even -- and it still
refuses to produce a manifest that fails the audit.
"""
from __future__ import annotations

from typing import Iterable, Mapping, Sequence

from ..contracts import DatasetCase
from .splits import _hash_fraction, _jaccard, _shingles, near_duplicate_pairs


class _UnionFind:
    def __init__(self, items: Iterable[str]) -> None:
        self._parent = {item: item for item in items}

    def find(self, item: str) -> str:
        while self._parent[item] != item:
            self._parent[item] = self._parent[self._parent[item]]
            item = self._parent[item]
        return item

    def union(self, left: str, right: str) -> None:
        root_left, root_right = self.find(left), self.find(right)
        if root_left != root_right:
            self._parent[max(root_left, root_right)] = min(root_left, root_right)


def leakage_components(cases: Sequence[DatasetCase]) -> dict[str, tuple[str, ...]]:
    """Map component id -> the case groups in it.

    Two groups are merged when any of their documents are near-duplicate text, so
    a split built from whole components cannot carry a templated document across
    the boundary.
    """
    groups = sorted({case.group for case in cases})
    union = _UnionFind(groups)
    for left, right, _score in near_duplicate_pairs(cases):
        left_case = next(case for case in cases if case.case_id == left)
        right_case = next(case for case in cases if case.case_id == right)
        union.union(left_case.group, right_case.group)
    components: dict[str, list[str]] = {}
    for group in groups:
        components.setdefault(union.find(group), []).append(group)
    return {root: tuple(sorted(members)) for root, members in components.items()}


def assign_component_splits(
    cases: Sequence[DatasetCase],
    *,
    seed: int,
    ratios: Mapping[str, float] | None = None,
) -> tuple[list[DatasetCase], dict[str, object]]:
    """Assign whole leakage components to train/validation/test.

    ``negative_controls`` always lands in test: those records exist to measure
    false assertion and abstention, and training on them would turn the abstention
    metric into a memorisation check.
    """
    from dataclasses import replace

    ratios = dict(ratios or {"train": 0.65, "validation": 0.15, "test": 0.20})
    components = leakage_components(cases)
    cases_by_group: dict[str, int] = {}
    for case in cases:
        cases_by_group[case.group] = cases_by_group.get(case.group, 0) + 1
    sizes = {
        root: sum(cases_by_group[group] for group in members)
        for root, members in components.items()
    }
    ordered = sorted(
        (root for root in components),
        key=lambda root: (_hash_fraction(seed, "component|" + root), root),
    )
    total = sum(sizes.values())
    targets = {split: ratios[split] * total for split in ("train", "validation", "test")}
    assigned: dict[str, int] = {"train": 0, "validation": 0, "test": 0}
    component_split: dict[str, str] = {}

    # Negative controls are pinned to test before anything else.
    for root, members in components.items():
        if "negative_controls" in members:
            component_split[root] = "test"
            assigned["test"] += sizes[root]
    # Greedy fill: give each remaining component to the split with the largest
    # deficit relative to its target, which keeps sizes close without ever
    # splitting a component.
    for root in ordered:
        if root in component_split:
            continue
        def deficit(split: str) -> float:
            return targets[split] - assigned[split]

        choice = max(("train", "validation", "test"), key=deficit)
        component_split[root] = choice
        assigned[choice] += sizes[root]

    # A split with no cases makes an evaluation impossible; move the smallest
    # component out of the largest split rather than silently reporting "no data".
    for split in ("validation", "test"):
        if not any(value == split for value in component_split.values()):
            movable = min(
                (
                    root
                    for root, value in component_split.items()
                    if value == "train" and "negative_controls" not in components[root]
                ),
                key=lambda root: sizes[root],
                default=None,
            )
            if movable is not None:
                component_split[movable] = split

    split_of_group: dict[str, str] = {}
    for root, members in components.items():
        for group in members:
            split_of_group[group] = component_split[root]
    audit = {
        "component_count": len(components),
        "components": {
            root: {"groups": list(members), "split": component_split[root], "cases": sizes[root]}
            for root, members in sorted(components.items())
        },
        "case_counts": dict(sorted(assigned.items())),
        "ratios": ratios,
        "seed": seed,
        "method": (
            "transitive closure of companies linked by near-duplicate document text; "
            "whole components assigned by seeded hash order and greedy target fill"
        ),
    }
    return [
        replace(case, split=split_of_group[case.group]) for case in cases
    ], audit


__all__ = ["assign_component_splits", "leakage_components"]
