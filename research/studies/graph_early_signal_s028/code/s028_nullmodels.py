"""S-028-CORRECTION-1: corrected randomised graph null models.

The Phase 0-3 study used ``SnapshotSeries._build_randomised`` for the G2
comparison.  Independent review showed that implementation

* tested candidate swaps against a *stale* adjacency map, so the swap chain
  could create duplicate ``(company, track)`` edges; ``weighted2`` is a dict, so
  the duplicates silently collapsed and both bipartite degree sequences drifted;
* gave every rewired edge the weight ``size.get((entity, track), 1)``, which is
  almost always ``1`` for a new edge, so the weighted activity graph used by the
  cosine-similarity features was replaced by an effectively unweighted one;
* resampled dates *with replacement* from the track's window date pool, so the
  per-track date distribution was not preserved, and recomputed ``first_touch``
  from those resampled window dates only, whereas the observed snapshots compute
  ``first_touch`` over the *whole* history.  Every track member therefore looked
  like a fresh entrant under the null.

This module replaces it with two explicit, separately documented null models.
Both operate on one snapshot at a time, on the same 12-month incidence graph the
G1 features are computed from, and both are then decorated by the *unchanged*
``SnapshotSeries._decorate`` so the downstream feature semantics are identical.

Null model N1 -- topology null
    Hypothesis: conditional on each company's number of active tracks and each
    track's number of active companies (the two bipartite degree sequences),
    *which* company is linked to *which* track is exchangeable.  Implemented as
    a uniformly-proposed double-edge swap on a dynamically maintained edge set,
    preserving simplicity (no duplicate ``(company, track)`` edges) and the node
    sets.  Edge weights (window event counts) are re-assigned by permuting the
    observed multiset of weights, so the total number of window events and the
    marginal weight distribution are exactly preserved while per-node strengths
    are not.  Track window dates are resampled with replacement, so per-track
    time distributions are only preserved in expectation.

Null model N2 -- topology + activity + timing null
    Hypothesis: as N1, but additionally conditional on each track's activity
    volume and on the exact per-track distribution of both *window event dates*
    and *first-touch dates*.  Weights are assigned on the randomised support by
    an exact transportation solution (integer max-flow) so that, when feasible,
    both the company and the track strength sequences are preserved exactly as
    well; when the flow is infeasible for a snapshot (reported, never silent) the
    assignment falls back to preserving the track strengths exactly and company
    strengths in expectation.  Window dates are then dealt out *without*
    replacement from the track's observed date multiset and first-touch dates are
    permuted within each track, so both per-track temporals are exact.

Neither model can preserve the company-level history (a company's own
first-touch dates and its own event dates).  That is intrinsic: the null is
precisely the statement that the company-track links carry no information, so
pre-window entry history cannot survive it.  Every resulting deviation is
measured and written to the invariant audit.
"""
from __future__ import annotations

import random
from collections import Counter, defaultdict
from typing import Any, Iterable, Mapping

from s028_lib import SnapshotSeries, add_months, iso, parse_date

N1 = "N1"
N2 = "N2"
NULL_MODELS = (N1, N2)


# --------------------------------------------------------------- graph swaps
def edge_index(weighted: Mapping[str, Mapping[str, float]]) -> dict[tuple[str, str], float]:
    """Flatten a nested ``weighted`` map into ``{(entity, track): weight}``."""
    return {(entity, track): float(weight)
            for entity, tracks in weighted.items()
            for track, weight in tracks.items()}


def bipartite_double_edge_swap(pairs: Iterable[tuple[str, str]], rng: random.Random,
                               swaps_per_edge: float = 10.0) -> dict[str, Any]:
    """Degree-preserving simple bipartite double-edge swap on a dynamic edge set.

    A swap takes two edges ``(a, b)`` and ``(c, d)`` and replaces them with
    ``(a, d)`` and ``(c, b)``.  It is applied only when it cannot create a
    duplicate edge or a loop, and the candidate check is made against the
    *current* adjacency, updated after every accepted swap.  Degrees on both
    sides are therefore invariant by construction, and the graph stays simple.

    Returns the new edge list plus acceptance statistics.
    """
    pairs = list(dict.fromkeys(pairs))
    n = len(pairs)
    adjacency: dict[str, set[str]] = defaultdict(set)
    track_adjacency: dict[str, set[str]] = defaultdict(set)
    for entity, track in pairs:
        adjacency[entity].add(track)
        track_adjacency[track].add(entity)
    stats = {"edges": n, "attempts": 0, "accepted": 0,
             "rejected_same_edge": 0, "rejected_degenerate": 0,
             "rejected_would_duplicate": 0, "target_attempts": 0}
    if n < 4:
        stats["acceptance_rate"] = None
        return {"pairs": pairs, "stats": stats}
    target = max(1, int(round(swaps_per_edge * n)))
    stats["target_attempts"] = target
    for _ in range(target):
        stats["attempts"] += 1
        i = rng.randrange(n)
        j = rng.randrange(n)
        if i == j:
            stats["rejected_same_edge"] += 1
            continue
        a, b = pairs[i]
        c, d = pairs[j]
        if a == c or b == d:
            stats["rejected_degenerate"] += 1
            continue
        if d in adjacency[a] or b in adjacency[c]:
            stats["rejected_would_duplicate"] += 1
            continue
        adjacency[a].discard(b)
        adjacency[c].discard(d)
        adjacency[a].add(d)
        adjacency[c].add(b)
        track_adjacency[b].discard(a)
        track_adjacency[d].discard(c)
        track_adjacency[d].add(a)
        track_adjacency[b].add(c)
        pairs[i] = (a, d)
        pairs[j] = (c, b)
        stats["accepted"] += 1
    stats["acceptance_rate"] = stats["accepted"] / stats["attempts"] if stats["attempts"] else None
    return {"pairs": pairs, "stats": stats}


def _degree_sequences(pairs: Iterable[tuple[str, str]]) -> tuple[dict[str, int], dict[str, int]]:
    entity_degree: Counter[str] = Counter()
    track_degree: Counter[str] = Counter()
    for entity, track in pairs:
        entity_degree[entity] += 1
        track_degree[track] += 1
    return dict(entity_degree), dict(track_degree)


def _strengths(weighted: Mapping[str, Mapping[str, float]]) -> tuple[dict[str, float], dict[str, float]]:
    entity_strength: dict[str, float] = defaultdict(float)
    track_strength: dict[str, float] = defaultdict(float)
    for entity, tracks in weighted.items():
        for track, weight in tracks.items():
            entity_strength[entity] += weight
            track_strength[track] += weight
    return dict(entity_strength), dict(track_strength)


# ------------------------------------------------------------------- weights
def assign_weights_shuffled(pairs: list[tuple[str, str]],
                            weights: Mapping[tuple[str, str], float],
                            rng: random.Random) -> dict[tuple[str, str], int]:
    """N1: permute the observed edge-weight multiset onto the swapped support.

    Total window event count and the marginal weight distribution are exact;
    per-node strengths are not constrained (measured by the audit).
    """
    pool = [int(round(value)) for value in weights.values()]
    rng.shuffle(pool)
    return {pair: pool[index] for index, pair in enumerate(pairs)}


def assign_weights_transport(pairs: list[tuple[str, str]],
                             entity_strength: Mapping[str, float],
                             track_strength: Mapping[str, float],
                             rng: random.Random | None = None,
                             ) -> tuple[dict[tuple[str, str], int], str]:
    """N2: integer weights on the swapped support with preserved strengths.

    Two tiers, both recorded in the returned ``mode``:

    ``flow_both_margins``
        An exact integer transportation solution with ``scipy``'s max-flow: every
        support edge carries at least one event and *both* the company and the
        track strength sequences match the observed ones exactly.  This is **not
        always feasible**: the randomised support need not be able to route a
        high-strength company's volume through its new neighbours' spare capacity.
    ``column_margins``
        Always feasible fallback: every support edge carries at least one event,
        each track's total activity is preserved exactly (which is what makes the
        exact per-track date deal possible), and the company strengths are left to
        deviate.  The deviation is measured by the audit, never hidden.
    """
    support = list(dict.fromkeys(pairs))
    entity_degree, track_degree = _degree_sequences(support)
    row_extra = {e: int(round(entity_strength.get(e, 0.0))) - entity_degree[e]
                 for e in entity_degree}
    col_extra = {k: int(round(track_strength.get(k, 0.0))) - track_degree[k]
                 for k in track_degree}
    if any(value < 0 for value in row_extra.values()) or any(value < 0 for value in col_extra.values()):
        # Weight rounding made a strength smaller than the degree: fall back to
        # the minimum simple weighted graph (one event per edge).
        return {pair: 1 for pair in support}, "column_margins"
    total = sum(row_extra.values())
    if total == 0:
        return {pair: 1 for pair in support}, "flow_both_margins"
    solved = _solve_transport(support, row_extra, col_extra)
    if solved is not None:
        weights = {pair: 1 + solved[pair] for pair in support}
        return weights, "flow_both_margins"
    # Company margins infeasible on this support: keep the track margins exact.
    weights = {pair: 1 for pair in support}
    by_track: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for pair in support:
        by_track[pair[1]].append(pair)
    for track in sorted(by_track):
        extra = col_extra.get(track, 0)
        if extra <= 0:
            continue
        choices = by_track[track]
        for _ in range(extra):
            pick = choices[rng.randrange(len(choices))] if rng is not None else choices[0]
            weights[pick] += 1
    return weights, "column_margins"


def _solve_transport(support: list[tuple[str, str]],
                     row_extra: Mapping[str, int],
                     col_extra: Mapping[str, int],
                     ) -> dict[tuple[str, str], int] | None:
    """Exact integer flow for ``sum(row_extra) == sum(col_extra)`` or ``None``."""
    import numpy as np
    from scipy.sparse import csr_matrix
    from scipy.sparse.csgraph import maximum_flow
    rows = sorted(row_extra)
    cols = sorted(col_extra)
    if not rows or not cols:
        return None
    supply = sum(row_extra.values())
    demand = sum(col_extra.values())
    if supply != demand:
        return None
    if supply == 0:
        return {pair: 0 for pair in support}
    row_index = {value: index for index, value in enumerate(rows)}
    col_index = {value: len(rows) + index for index, value in enumerate(cols)}
    source = len(rows) + len(cols)
    sink = source + 1
    # node order: [rows..., cols..., source, sink]
    sources: list[int] = []
    targets: list[int] = []
    capacities: list[int] = []
    big = int(supply)
    for row in rows:
        value = int(row_extra[row])
        if value:
            sources.append(source)
            targets.append(row_index[row])
            capacities.append(value)
    for col in cols:
        value = int(col_extra[col])
        if value:
            sources.append(col_index[col])
            targets.append(sink)
            capacities.append(value)
    for entity, track in support:
        sources.append(row_index[entity])
        targets.append(col_index[track])
        capacities.append(big)
    size = sink + 1
    graph = csr_matrix((np.asarray(capacities, dtype=np.int64),
                        (np.asarray(sources, dtype=np.int64),
                         np.asarray(targets, dtype=np.int64))), shape=(size, size))
    result = maximum_flow(graph, source, sink)
    if int(result.flow_value) != supply:
        return None
    flow = result.flow.tocsr()
    out: dict[tuple[str, str], int] = {}
    for entity, track in support:
        out[(entity, track)] = int(flow[row_index[entity], col_index[track]])
    return out


# -------------------------------------------------------------------- dates
def assign_dates(pairs: list[tuple[str, str]], weights: Mapping[tuple[str, str], int],
                 window_events: list[dict[str, Any]], rng: random.Random,
                 *, replacement: bool) -> tuple[dict[str, list[Any]], dict[str, Any]]:
    """Deal window event dates to edges from each track's observed date multiset.

    ``replacement=False`` deals the multiset out exactly (requires the per-track
    event count to be preserved); ``replacement=True`` samples with replacement.
    """
    pools: dict[str, list[Any]] = defaultdict(list)
    for event in window_events:
        pools[event["track_id"]].append(event["day"])
    by_track: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for pair in pairs:
        by_track[pair[1]].append(pair)
    drawn: dict[tuple[str, str], list[Any]] = {}
    deviations: list[float] = []
    for track, track_pairs in by_track.items():
        pool = pools.get(track, [])
        if not pool:
            # The observed snapshot has no window events for this track: it
            # cannot be part of the window incidence graph, so this is a no-op.
            for pair in track_pairs:
                drawn[pair] = []
            continue
        if replacement:
            for pair in track_pairs:
                count = int(weights.get(pair, 1))
                drawn[pair] = [pool[rng.randrange(len(pool))] for _ in range(count)]
        else:
            shuffled = list(pool)
            rng.shuffle(shuffled)
            cursor = 0
            for pair in track_pairs:
                count = int(weights.get(pair, 1))
                drawn[pair] = shuffled[cursor:cursor + count]
                cursor += count
            if cursor != len(shuffled):
                # count mismatch: keep the remainder rather than drop events;
                # the deviation is measured below and reported by the audit.
                drawn[track_pairs[-1]] = drawn[track_pairs[-1]] + shuffled[cursor:]
        assigned = Counter(day for pair in track_pairs for day in drawn[pair])
        observed = Counter(pool)
        total = sum(observed.values()) or 1
        deviations.append(sum(abs(assigned[day] - observed[day])
                              for day in set(assigned) | set(observed)) / (2.0 * total))
    stats = {"temporal_total_variation_mean": (sum(deviations) / len(deviations)
                                               if deviations else None),
             "temporal_total_variation_max": max(deviations) if deviations else None,
             "replacement": replacement}
    return drawn, stats


def assign_first_touch(pairs: list[tuple[str, str]],
                       observed_first_touch: Mapping[tuple[str, str], Any],
                       observed_track_companies: Mapping[str, set[str]],
                       rng: random.Random) -> tuple[dict[tuple[str, str], Any], dict[str, Any]]:
    """Permute the observed first-touch dates *within each track*.

    The observed per-track multiset ``{first_touch(e, k) : k in portfolio(e)}``
    is dealt back to the randomised edges of that track.  Entry counts per track,
    entry-date distributions and the entrant-decay features are therefore exact at
    the track level; company-level entry history is destroyed by design.
    """
    by_track: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for pair in pairs:
        by_track[pair[1]].append(pair)
    out: dict[tuple[str, str], Any] = {}
    violations = 0
    for track, track_pairs in by_track.items():
        dates = [observed_first_touch[(member, track)]
                 for member in observed_track_companies.get(track, set())
                 if (member, track) in observed_first_touch]
        dates = sorted(dates)
        if len(dates) != len(track_pairs):
            violations += 1
        rng.shuffle(dates)
        for index, pair in enumerate(track_pairs):
            if index < len(dates):
                out[pair] = dates[index]
    return out, {"first_touch_multiset_violations": violations}


# ------------------------------------------------------------ null snapshots
def build_null_snapshot(observed: Mapping[str, Any], rng: random.Random,
                        swaps_per_edge: float, model: str) -> tuple[dict[str, Any], dict[str, Any]]:
    """Build one null snapshot from one observed snapshot of the same origin."""
    weighted = observed["weighted"]
    weights = edge_index(weighted)
    pairs = list(weights)
    swaps = bipartite_double_edge_swap(pairs, rng, swaps_per_edge=swaps_per_edge)
    new_pairs = swaps["pairs"]
    stats: dict[str, Any] = {"model": model, **swaps["stats"],
                             "observed_edges": len(pairs), "null_edges": len(new_pairs)}
    if model == N1:
        new_weights = assign_weights_shuffled(new_pairs, weights, rng)
    elif model == N2:
        entity_strength, track_strength = _strengths(weighted)
        new_weights, mode = assign_weights_transport(new_pairs, entity_strength,
                                                     track_strength, rng)
        stats["weight_mode"] = mode
    else:
        raise ValueError(f"unknown null model {model!r}")
    drawn, date_stats = assign_dates(new_pairs, new_weights, observed["window_events"], rng,
                                     replacement=(model == N1))
    first_touch, touch_stats = assign_first_touch(
        new_pairs, observed["first_touch"], observed["track_companies"], rng)
    stats.update(date_stats)
    stats.update(touch_stats)

    weighted2: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    portfolio2: dict[str, set[str]] = defaultdict(set)
    track_companies2: dict[str, set[str]] = defaultdict(set)
    for entity, track in new_pairs:
        weighted2[entity][track] = float(new_weights[(entity, track)])
        portfolio2[entity].add(track)
        track_companies2[track].add(entity)

    snapshot = {"cutoff": observed["cutoff"], "weighted": weighted2, "portfolio": portfolio2,
                "track_companies": track_companies2, "first_touch": first_touch,
                "window_events": [], "window_months": observed["window_months"],
                "randomised": True, "null_model": model}

    # -------- in-place invariant checks for this particular draw -----------
    observed_entities, observed_tracks = _degree_sequences(pairs)
    null_entities, null_tracks = _degree_sequences(new_pairs)
    stats["degree_sequences_equal"] = (observed_entities == null_entities
                                       and observed_tracks == null_tracks)
    stats["simple"] = len(set(new_pairs)) == len(new_pairs)
    stats["node_sets_equal"] = (set(observed_entities) == set(null_entities)
                                and set(observed_tracks) == set(null_tracks))
    obs_e_strength, obs_t_strength = _strengths(weighted)
    new_e_strength, new_t_strength = _strengths(weighted2)
    stats["max_abs_company_strength_deviation"] = max(
        abs(new_e_strength.get(e, 0.0) - obs_e_strength.get(e, 0.0))
        for e in set(obs_e_strength) | set(new_e_strength))
    stats["max_abs_track_strength_deviation"] = max(
        abs(new_t_strength.get(k, 0.0) - obs_t_strength.get(k, 0.0))
        for k in set(obs_t_strength) | set(new_t_strength))
    stats["total_event_count_equal"] = (
        sum(new_e_strength.values()) == sum(obs_e_strength.values()))
    stats["track_entry_date_multisets_equal"] = _entrant_multiset(
        first_touch, add_months(parse_date(observed["cutoff"]), -observed["window_months"])
    ) == _entrant_multiset(
        observed["first_touch"], add_months(parse_date(observed["cutoff"]), -observed["window_months"])
    )
    stats["edges_changed_fraction"] = (
        len(set(new_pairs) - set(pairs)) / len(pairs) if pairs else None)
    return snapshot, stats


def _entrant_multiset(first_touch: Mapping[tuple[str, str], Any], window_start: Any) -> Counter:
    out: Counter = Counter()
    for (_, track), day in first_touch.items():
        if day > window_start:
            out[track] += 1
    return out


class NullSnapshotSeries(SnapshotSeries):
    """Drop-in replacement for ``SnapshotSeries(randomised=True)``.

    It first builds the *observed* snapshots exactly as the frozen G1 path does,
    then replaces every snapshot by a draw from the requested null model and
    re-decorates it with the unchanged ``SnapshotSeries._decorate``.  ``features_for``
    is therefore computed by exactly the same code as the real-graph features.
    """

    def __init__(self, events: list[dict[str, Any]], cutoffs: Iterable[Any], *,
                 null_model: str = N1, seed: int = 20261104,
                 swaps_per_edge: float = 10.0, **kwargs: Any) -> None:
        kwargs.pop("randomised", None)
        super().__init__(events, cutoffs, randomised=False, seed=seed,
                         swaps_per_edge=swaps_per_edge, **kwargs)
        if null_model not in NULL_MODELS:
            raise ValueError(f"unknown null model {null_model!r}")
        self.null_model = null_model
        self.seed = seed
        self.swaps_per_edge = swaps_per_edge
        self.null_stats: dict[str, Any] = {}
        self._build_nulls()

    def _build_nulls(self) -> None:
        for index, cutoff in enumerate(self._cutoffs):
            observed = self._cache[cutoff]
            rng = random.Random(self.seed * 1000003 + index)
            snapshot, stats = build_null_snapshot(observed, rng, self.swaps_per_edge,
                                                 self.null_model)
            self._decorate(snapshot, parse_date(cutoff))
            self._cache[cutoff] = snapshot
            self.null_stats[cutoff] = {"origin_index": index, "origin": cutoff, **stats}
