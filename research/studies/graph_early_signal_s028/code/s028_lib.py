"""S-028 core library: company–technology temporal bipartite graph for early signals.

Design constraints (see PRE_REGISTRATION.md and TEMPORAL_LEAKAGE_AUDIT.md):

* The frozen research inputs are read-only and SHA-256 verified before use.
* The entry-target construction mirrors the frozen ``build_entry_examples`` logic
  exactly (36-month dormancy, quarterly origins, left-censoring) so that the
  S-028 panel can be validated by reproducing the frozen benchmark counts.
* Every graph snapshot at origin ``t`` is built ONLY from events whose
  ``available_at`` <= t. No full-period graph statistic is ever computed and
  used to predict the past.
* Excluded from "qualifying" labels: Special 510(k) maintenance filings and PMA
  supplements. The label is a first observed *qualifying* public regulatory
  event, never a claim about innovation.
"""
from __future__ import annotations

import hashlib
import json
import math
import sqlite3
import sys
from collections import Counter, defaultdict
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping

REPO_ROOT = Path(__file__).resolve().parents[4]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from medradar.util import add_months, iso, parse_date, quarter_index, quarter_start, sha1  # noqa: E402
from medradar.intelligence.features.research_features import (  # noqa: E402
    ENTRY_INACTIVE_MONTHS_CAP,
    MONTH_LENGTH_DAYS,
    _pair_history_features,
)

# --------------------------------------------------------------------- constants
DORMANCY_MONTHS = 36
HORIZON_QUARTERS_PRIMARY = 4          # pre-registered primary: 4 quarters = 12 months
HORIZON_QUARTERS_SECONDARY = 2        # pre-registered secondary: 2 quarters = 6 months
QUARTER_MONTHS = 3
FROZEN_DB_SHA256 = "dd241bfec138d7977d7eb8f4c1db25119d59b6fe7ff573060b24d14eeeb71e0d"
FROZEN_DB_SIZE = 289443840
FROZEN_COVERAGE_END_REFERENCE = "2026-10-15"

BASE_FEATURES = (
    "rd_count_12m", "rd_count_previous_12m", "rd_momentum", "rd_count_36m",
    "rd_recency_years", "rd_company_count_12m", "rd_track_count_12m",
    "rd_company_track_share", "rd_pair_active_years", "rd_company_total_36m",
)
ENTRY_FEATURES = (
    "rd_pair_inactive_months",
    "rd_company_active_tracks_12m",
    "rd_company_active_tracks_delta",
    "rd_track_active_companies_12m",
    "rd_track_active_companies_delta",
    "rd_company_track_novelty_share",
)
B3_FEATURES = BASE_FEATURES + ENTRY_FEATURES

# G1 graph-feature groups. Names are stable identifiers used by the ablation.
PEER_ENTRY_FEATURES = (
    "g_coentry_count_12m",          # other companies' first observed entry into k, last 12m
    "g_coentry_decay",              # same, exponentially time-decayed (half-life 12m)
    "g_coentry_similarity_weighted",# peer entries weighted by portfolio similarity to c
    "g_max_entrant_similarity",     # similarity of the closest recent entrant to c
)
SIMILARITY_FEATURES = (
    "g_similarity_to_track_incumbents",  # mean similarity of c to companies active in k
    "g_similarity_to_track_max",         # max similarity
)
TWOHOP_FEATURES = (
    "g_twohop_reach",               # size of c's 2-hop neighbourhood through shared tracks
    "g_twohop_activity_decay",      # time-decayed 2-hop activity intensity
)
COOCCURRENCE_FEATURES = (
    "g_track_cooccurrence_pull",    # how strongly k co-occurs with c's current tracks
)
CENTRALITY_FEATURES = (
    "g_company_eigenvector",
    "g_company_clustering",
    "g_track_entrant_centrality",
)
G1_FEATURES = (PEER_ENTRY_FEATURES + SIMILARITY_FEATURES + TWOHOP_FEATURES
               + COOCCURRENCE_FEATURES + CENTRALITY_FEATURES)
G1_ALL = B3_FEATURES + G1_FEATURES


# ------------------------------------------------------------------ input layer
def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_frozen_db(path: Path, *, strict: bool = True) -> dict[str, Any]:
    """Verify the frozen research database by size and SHA-256 before use."""
    exists = path.exists()
    size = path.stat().st_size if exists else None
    digest = sha256_file(path) if exists else None
    ok = exists and size == FROZEN_DB_SIZE and digest == FROZEN_DB_SHA256
    record = {"path": str(path), "exists": exists, "size_bytes": size,
              "sha256": digest, "expected_sha256": FROZEN_DB_SHA256,
              "expected_size_bytes": FROZEN_DB_SIZE, "ok": ok}
    if strict and not ok:
        raise RuntimeError(f"frozen input mismatch: {record}")
    return record


def material_pma(payload: str) -> bool:
    """Frozen material-PMA rule: original PMA (or PANEL TRACK supplement)."""
    try:
        row = json.loads(payload or "{}")
    except (TypeError, ValueError):
        return False
    supplement = str(row.get("supplement_number") or "").strip().upper()
    kind = str(row.get("supplement_type") or "").strip().upper()
    return supplement in ("", "0", "S0") or "PANEL TRACK" in kind


def original_pma(payload: str) -> bool:
    """Strict original PMA: no supplement number at all (no PANEL TRACK exception)."""
    try:
        row = json.loads(payload or "{}")
    except (TypeError, ValueError):
        return False
    supplement = str(row.get("supplement_number") or "").strip().upper()
    return supplement in ("", "0", "S0")


def traditional_510k(payload: str) -> bool:
    """True for a Traditional 510(k); excludes Special and Abbreviated clearances."""
    try:
        row = json.loads(payload or "{}")
    except (TypeError, ValueError):
        return False
    return str(row.get("clearance_type") or "").strip().lower() == "traditional"


def is_qualifying(kind: str, payload: str) -> bool:
    """S-028 qualifying event: Traditional 510(k) or original (non-supplement) PMA.

    This excludes two classes of maintenance filing that the frozen benchmark
    counted as "material": Special 510(k)s (modifications of the filer's own
    device) and PMA supplements. See DATA_FEASIBILITY.md for the counts.
    """
    if kind == "510k":
        return traditional_510k(payload)
    if kind == "pma":
        return original_pma(payload)
    return False


def load_events(db_path: Path) -> list[dict[str, Any]]:
    """Load the frozen 510(k)/PMA lane with material filtering, read-only.

    Returns one record per *material* event with a parsed ``day`` and
    ``available`` (knowledge clock). Additive flags describe the strict
    qualifying class so the label rule can be switched without reloading.
    """
    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    try:
        rows = con.execute(
            "SELECT event_id, kind, event_date, available_at, company_key, applicant_raw, "
            "track_id, source, payload FROM events WHERE kind IN ('510k','pma')"
        ).fetchall()
    finally:
        con.close()
    events: list[dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        if item["kind"] == "pma" and not material_pma(item.get("payload") or ""):
            continue
        day = parse_date(item.get("event_date"))
        available = parse_date(str(item.get("available_at") or "")[:10]) or day
        if not day or not available:
            continue
        payload = item.get("payload") or ""
        item["day"] = day
        item["available"] = available
        item["qualifying"] = is_qualifying(item["kind"], payload)
        item["clearance_type"] = ""
        item["supplement_number"] = ""
        try:
            raw = json.loads(payload)
            item["clearance_type"] = str(raw.get("clearance_type") or "")
            item["supplement_number"] = str(raw.get("supplement_number") or "")
            item["decision_date"] = str(raw.get("decision_date") or "")
        except (TypeError, ValueError):
            item["decision_date"] = ""
        events.append(item)
    events.sort(key=lambda event: (event["day"], event["event_id"]))
    return events


# --------------------------------------------------------------- panel builder
def panel_origins(panel_events: list[dict[str, Any]], horizon_months: int) -> tuple[list[date], date, date]:
    """Quarterly origins with the dormancy and label-maturity constraints.

    Mirrors the frozen ``entry_origins``: ``t - 36m >= coverage_start`` and
    ``t + H <= coverage_end``.
    """
    coverage_start = min(event["day"] for event in panel_events)
    coverage_end = max(event["day"] for event in panel_events)
    earliest = add_months(coverage_start, DORMANCY_MONTHS)
    index = quarter_index(earliest)
    if index is None:
        return [], coverage_start, coverage_end
    current = quarter_start(index)
    if current < earliest:
        current = quarter_start(index + 1)
    cutoffs: list[date] = []
    while add_months(current, horizon_months) <= coverage_end:
        cutoffs.append(current)
        current = add_months(current, 3)
    return cutoffs, coverage_start, coverage_end


def build_entry_panel(events: list[dict[str, Any]], *, entity_field: str = "company_key",
                      horizon_months: int = 12, label_kind: str = "qualifying",
                      snapshots: "SnapshotSeries | None" = None,
                      dataset_version: str = "s028_entry_v1") -> dict[str, Any]:
    """Dormant -> first qualifying activity entry examples (frozen protocol).

    ``label_kind``:
      * ``"material"``   - any material event (frozen benchmark label; for the
                           fidelity self-check and a sensitivity analysis only)
      * ``"qualifying"`` - Traditional 510(k) or original PMA (S-028 primary)
    """
    usable = [event for event in events
              if event.get(entity_field) and event.get("track_id")]
    if not usable:
        raise ValueError(f"no usable events for entity_field={entity_field}")
    if label_kind == "material":
        label_events = usable
    elif label_kind == "qualifying":
        label_events = [event for event in usable if event["qualifying"]]
    else:
        raise ValueError(label_kind)

    cutoffs, coverage_start, coverage_end = panel_origins(usable, horizon_months)
    examples: list[dict[str, Any]] = []
    positives_by_origin: dict[str, int] = {}
    candidates_by_origin: dict[str, int] = {}
    risk_by_origin: dict[str, int] = {}
    for cutoff in cutoffs:
        horizon_end = add_months(cutoff, horizon_months)
        history = [event for event in usable
                   if event["day"] <= cutoff and event["available"] <= cutoff]
        if not history:
            continue
        active_entities = sorted({event[entity_field] for event in history})
        tracks = sorted({event["track_id"] for event in history})
        day_12, day_24 = cutoff - timedelta(days=365), cutoff - timedelta(days=730)
        day_36 = cutoff - timedelta(days=1095)
        dormancy_cut = add_months(cutoff, -DORMANCY_MONTHS)
        by_pair: dict[tuple[str, str], list[date]] = defaultdict(list)
        by_company: Counter[str] = Counter()
        by_company_previous: Counter[str] = Counter()
        by_company36: Counter[str] = Counter()
        by_track: Counter[str] = Counter()
        by_track_previous: Counter[str] = Counter()
        company_tracks: dict[str, set[str]] = defaultdict(set)
        company_tracks_previous: dict[str, set[str]] = defaultdict(set)
        track_companies: dict[str, set[str]] = defaultdict(set)
        track_companies_previous: dict[str, set[str]] = defaultdict(set)
        company_events24: Counter[str] = Counter()
        for event in history:
            entity, track, day = event[entity_field], event["track_id"], event["day"]
            by_pair[(entity, track)].append(day)
            if day_12 < day <= cutoff:
                by_company[entity] += 1
                by_track[track] += 1
                company_tracks[entity].add(track)
                track_companies[track].add(entity)
            elif day_24 < day <= day_12:
                by_company_previous[entity] += 1
                by_track_previous[track] += 1
                company_tracks_previous[entity].add(track)
                track_companies_previous[track].add(entity)
            if day_36 < day <= cutoff:
                by_company36[entity] += 1
            if day_24 < day <= cutoff:
                company_events24[entity] += 1
        pair_first = {pair: min(days) for pair, days in by_pair.items()}
        novel_events24: Counter[str] = Counter()
        for event in history:
            if day_24 < event["day"] <= cutoff:
                pair = (event[entity_field], event["track_id"])
                if pair_first[pair] > day_24:
                    novel_events24[event[entity_field]] += 1
        future = [event for event in label_events
                  if cutoff < event["day"] <= horizon_end
                  and event.get(entity_field) and event.get("track_id")]
        future_by_pair: dict[tuple[str, str], list[date]] = defaultdict(list)
        for event in future:
            future_by_pair[(event[entity_field], event["track_id"])].append(event["day"])

        candidates = [
            (entity, track)
            for entity in active_entities
            for track in tracks
            if not by_pair.get((entity, track)) or max(by_pair[(entity, track)]) <= dormancy_cut
        ]
        candidates_by_origin[iso(cutoff)] = len(candidates)
        risk_by_origin[iso(cutoff)] = len(candidates)
        positives = 0
        for entity, track in candidates:
            pair_days = by_pair.get((entity, track), [])
            features: dict[str, float | None] = _pair_history_features(
                pair_days, cutoff, company=entity, track=track,
                by_company=by_company, by_track=by_track, by_company36=by_company36)
            last_day = max(pair_days) if pair_days else None
            features["rd_pair_inactive_months"] = (
                min(ENTRY_INACTIVE_MONTHS_CAP, (cutoff - last_day).days / MONTH_LENGTH_DAYS)
                if last_day else ENTRY_INACTIVE_MONTHS_CAP)
            features["rd_company_active_tracks_12m"] = float(len(company_tracks[entity]))
            features["rd_company_active_tracks_delta"] = float(
                len(company_tracks[entity]) - len(company_tracks_previous[entity]))
            features["rd_track_active_companies_12m"] = float(len(track_companies[track]))
            features["rd_track_active_companies_delta"] = float(
                len(track_companies[track]) - len(track_companies_previous[track]))
            total24 = company_events24[entity]
            features["rd_company_track_novelty_share"] = (
                novel_events24[entity] / total24 if total24 else 0.0)
            if snapshots is not None:
                features.update(snapshots.features_for(cutoff, entity, track))
            targets = future_by_pair.get((entity, track), [])
            if targets:
                positives += 1
            examples.append({
                "example_id": sha1(
                    f"{dataset_version}|{iso(cutoff)}|{horizon_months}|{entity}|{track}")[:32],
                "cutoff": iso(cutoff), "horizon_months": horizon_months,
                "company_key": entity, "track_id": track,
                "entity_field": entity_field,
                "features": features,
                "feature_available_at": iso(cutoff),
                "label": int(bool(targets)),
                "first_target_event_date": iso(min(targets)) if targets else None,
                "target_event_count": len(targets),
                "maturity": "mature",
            })
        positives_by_origin[iso(cutoff)] = positives
    return {
        "dataset_version": dataset_version, "entity_field": entity_field,
        "label_kind": label_kind, "horizon_months": horizon_months,
        "examples": examples, "cutoffs": [iso(c) for c in cutoffs],
        "coverage_start": iso(coverage_start), "coverage_end": iso(coverage_end),
        "dormancy_months": DORMANCY_MONTHS,
        "event_count": len(usable), "label_event_count": len(label_events),
        "entity_count": len({event[entity_field] for event in usable}),
        "track_count": len({event["track_id"] for event in usable}),
        "observed_pair_count": len({(event[entity_field], event["track_id"]) for event in usable}),
        "candidates_by_origin": candidates_by_origin,
        "positives_by_origin": positives_by_origin,
        "risk_by_origin": risk_by_origin,
        "n_examples": len(examples),
        "n_positives": sum(int(row["label"]) for row in examples),
    }


# ------------------------------------------------------------- graph snapshots
def _cosine(a: Mapping[str, float], b: Mapping[str, float]) -> float:
    keys = set(a) & set(b)
    if not keys:
        return 0.0
    dot = sum(a[k] * b[k] for k in keys)
    na = math.sqrt(sum(v * v for v in a.values()))
    nb = math.sqrt(sum(v * v for v in b.values()))
    return dot / (na * nb) if na and nb else 0.0


class SnapshotSeries:
    """Pre-computed company–technology graph snapshots at each origin.

    A snapshot at origin ``t`` uses only history events (``day <= t`` and
    ``available <= t``). It caches, per origin: the 12-month incidence matrix,
    per-company track portfolios, per-track company sets, first-touch times,
    company–company similarity, and centrality. ``randomised=True`` builds the
    same objects from a degree-preserving rewiring of the (company, track)
    activity blocks.
    """

    def __init__(self, events: list[dict[str, Any]], cutoffs: Iterable[str | date], *,
                 entity_field: str = "company_key", window_months: int = 12,
                 randomised: bool = False, seed: int = 20261104,
                 swaps_per_edge: int = 10) -> None:
        self.events = events
        self.entity_field = entity_field
        self.window_months = window_months
        self.randomised = randomised
        self.seed = seed
        self.swaps_per_edge = swaps_per_edge
        self._cache: dict[str, dict[str, Any]] = {}
        self._cutoffs = [iso(parse_date(c)) if not isinstance(c, str) else c for c in cutoffs]
        for cutoff in self._cutoffs:
            self._cache[cutoff] = self._build(parse_date(cutoff))
        if randomised:
            self._build_randomised()

    # -- observed snapshot -------------------------------------------------
    def _history(self, t: date) -> list[dict[str, Any]]:
        cutoff = add_months(t, -self.window_months)
        return [event for event in self.events
                if event["available"] <= t and event["day"] <= t
                and event["day"] > cutoff and event.get(self.entity_field) and event.get("track_id")]

    def _build(self, t: date) -> dict[str, Any]:
        window = self._history(t)
        weighted: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
        portfolio: dict[str, set[str]] = defaultdict(set)
        track_companies: dict[str, set[str]] = defaultdict(set)
        first_touch: dict[tuple[str, str], date] = {}
        all_history = [event for event in self.events
                       if event["available"] <= t and event["day"] <= t
                       and event.get(self.entity_field) and event.get("track_id")]
        for event in all_history:
            pair = (event[self.entity_field], event["track_id"])
            if pair not in first_touch or event["day"] < first_touch[pair]:
                first_touch[pair] = event["day"]
        for event in window:
            entity, track = event[self.entity_field], event["track_id"]
            weighted[entity][track] += 1.0
            portfolio[entity].add(track)
            track_companies[track].add(entity)
        snap = {"cutoff": iso(t), "weighted": weighted, "portfolio": portfolio,
                "track_companies": track_companies, "first_touch": first_touch,
                "window_events": window, "window_months": self.window_months}
        self._decorate(snap, t)
        return snap

    def _decorate(self, snap: dict[str, Any], t: date) -> None:
        """Cache everything row-independent: similarities, adjacency, centrality.

        Without this cache the per-row feature call is O(companies^2) and the
        panel build becomes quadratic in rows. The cache is built once per
        snapshot from that snapshot's own information only.
        """
        weighted = snap["weighted"]
        track_companies = snap["track_companies"]
        first_touch = snap["first_touch"]
        window_start = add_months(t, -self.window_months)
        nodes = sorted(set(weighted))
        # pairwise portfolio cosine similarity (0 when no shared active track)
        similarity: dict[tuple[str, str], float] = {}
        for i, a in enumerate(nodes):
            for b in nodes[i + 1:]:
                value = _cosine(weighted[a], weighted[b])
                similarity[(a, b)] = value
                similarity[(b, a)] = value
        snap["similarity"] = similarity
        # company-company co-activity projection and its centrality/clustering
        adjacency: dict[str, set[str]] = {node: set() for node in nodes}
        for members in track_companies.values():
            ordered = sorted(members)
            for i in range(len(ordered)):
                for j in range(i + 1, len(ordered)):
                    adjacency[ordered[i]].add(ordered[j])
                    adjacency[ordered[j]].add(ordered[i])
        snap["adjacency"] = adjacency
        snap["eigenvector"] = _eigenvector(adjacency)
        clustering: dict[str, float] = {}
        for node, neighbours in adjacency.items():
            if len(neighbours) > 1:
                links = sum(len(adjacency.get(a, set()) & neighbours) for a in neighbours) // 2
                possible = len(neighbours) * (len(neighbours) - 1) / 2
                clustering[node] = links / possible if possible else 0.0
            else:
                clustering[node] = 0.0
        snap["clustering"] = clustering
        # first observed entries inside the window, per track
        entrants_by_track: dict[str, list[tuple[str, date]]] = defaultdict(list)
        for (peer, track_id), day in first_touch.items():
            if day > window_start:
                entrants_by_track[track_id].append((peer, day))
        snap["entrants_by_track"] = entrants_by_track
        totals = Counter()
        for track_id, entries in entrants_by_track.items():
            totals[track_id] = len(entries)
        total_entries = sum(totals.values())
        snap["entrant_centrality"] = ({track_id: count / total_entries
                                       for track_id, count in totals.items()}
                                      if total_entries else {})

    # -- randomised snapshot ----------------------------------------------
    def _build_randomised(self) -> None:
        """Degree-preserving block rewiring of (company, track) activity blocks.

        Each company–track activity block is a stub. Randomly swapping the track
        endpoints of two blocks preserves, exactly, every company's number of
        active tracks and every track's number of active companies (the
        bipartite degree sequences); what it destroys is *which* company is
        active in *which* track. Each rewired edge then draws its event dates
        from that track's observed date pool, so the per-track time distribution
        is preserved while the identities are not.
        """
        import random
        rng = random.Random(self.seed)
        for cutoff, snap in list(self._cache.items()):
            weighted = snap["weighted"]
            blocks = [(entity, track) for entity, tracks in weighted.items() for track in tracks]
            if len(blocks) < 4:
                continue
            blocks = list(blocks)
            for _ in range(self.swaps_per_edge * len(blocks)):
                i, j = rng.randrange(len(blocks)), rng.randrange(len(blocks))
                if i == j:
                    continue
                e1, k1 = blocks[i]
                e2, k2 = blocks[j]
                if e1 == e2 or k1 == k2:
                    continue
                if k2 in weighted[e1] or k1 in weighted[e2]:
                    continue  # keep the randomised graph simple
                blocks[i], blocks[j] = (e1, k2), (e2, k1)
            # observed date pool + block sizes per track (time distribution source)
            date_pool: dict[str, list[date]] = defaultdict(list)
            for event in snap["window_events"]:
                date_pool[event["track_id"]].append(event["day"])
            size: dict[tuple[str, str], int] = {}
            for entity, tracks in weighted.items():
                for track in tracks:
                    size[(entity, track)] = max(1, int(round(weighted[entity][track])))
            weighted2: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
            portfolio2: dict[str, set[str]] = defaultdict(set)
            track_companies2: dict[str, set[str]] = defaultdict(set)
            first_touch2: dict[tuple[str, str], date] = {}
            for entity, track in blocks:
                pool = date_pool.get(track)
                if not pool:
                    continue
                count = size.get((entity, track), 1)
                drawn = [pool[rng.randrange(len(pool))] for _ in range(count)]
                weighted2[entity][track] = float(len(drawn))
                portfolio2[entity].add(track)
                track_companies2[track].add(entity)
                first_touch2[(entity, track)] = min(drawn)
            self._cache[cutoff] = {
                "cutoff": cutoff, "weighted": weighted2, "portfolio": portfolio2,
                "track_companies": track_companies2, "first_touch": first_touch2,
                "window_events": [], "window_months": self.window_months,
                "randomised": True,
            }
            self._decorate(self._cache[cutoff], parse_date(cutoff))

    # -- feature computation ----------------------------------------------
    def features_for(self, cutoff: str | date, entity: str, track: str) -> dict[str, float]:
        key = iso(parse_date(cutoff)) if not isinstance(cutoff, str) else cutoff
        snap = self._cache.get(key)
        if snap is None:
            return {name: 0.0 for name in G1_FEATURES}
        return self._compute(snap, entity, track)

    def _compute(self, snap: dict[str, Any], entity: str, track: str) -> dict[str, float]:
        weighted = snap["weighted"]
        portfolio = snap["portfolio"]
        track_companies = snap["track_companies"]
        similarity = snap["similarity"]
        adjacency = snap["adjacency"]
        cutoff = parse_date(snap["cutoff"])
        window_start = add_months(cutoff, -self.window_months)
        out: dict[str, float] = {}

        # --- other companies' first observed entry into this track ----
        entrants = [(peer, day) for peer, day in snap["entrants_by_track"].get(track, [])
                    if peer != entity]
        out["g_coentry_count_12m"] = float(len(entrants))
        decay = 0.0
        weighted_sim = 0.0
        max_sim = 0.0
        for peer, day in entrants:
            age_months = (cutoff - day).days / MONTH_LENGTH_DAYS
            decay += math.exp(-age_months / 12.0)
            value = similarity.get((entity, peer), 0.0)
            weighted_sim += value
            max_sim = max(max_sim, value)
        out["g_coentry_decay"] = decay
        out["g_coentry_similarity_weighted"] = weighted_sim
        out["g_max_entrant_similarity"] = max_sim

        # --- how similar is c to the incumbents of this track ----
        peers = sorted(set(track_companies.get(track, set())) - {entity})
        values = [similarity.get((entity, peer), 0.0) for peer in peers]
        out["g_similarity_to_track_incumbents"] = (
            sum(values) / len(values) if values else 0.0)
        out["g_similarity_to_track_max"] = max(values) if values else 0.0

        # --- 2-hop neighbourhood through shared tracks ----
        own_tracks = portfolio.get(entity, set())
        reach: set[str] = set()
        intensity = 0.0
        first_touch = snap["first_touch"]
        for other in own_tracks:
            for peer in track_companies.get(other, set()):
                if peer == entity:
                    continue
                reach.add(peer)
                last = first_touch.get((peer, other))
                if last is not None:
                    intensity += math.exp(-((cutoff - last).days / MONTH_LENGTH_DAYS) / 12.0)
        out["g_twohop_reach"] = float(len(reach))
        out["g_twohop_activity_decay"] = intensity / len(own_tracks) if own_tracks else 0.0

        # --- track co-occurrence pull ----
        pull = 0.0
        target_members = track_companies.get(track, set())
        for other in own_tracks:
            if other == track:
                continue
            members = track_companies.get(other, set())
            if not members or not target_members:
                continue
            pull += len(members & target_members) / math.sqrt(len(members) * len(target_members))
        out["g_track_cooccurrence_pull"] = pull / len(own_tracks) if own_tracks else 0.0

        # --- centrality on the bipartite projection ----
        out["g_company_eigenvector"] = snap["eigenvector"].get(entity, 0.0)
        out["g_company_clustering"] = snap["clustering"].get(entity, 0.0)
        out["g_track_entrant_centrality"] = snap["entrant_centrality"].get(track, 0.0)
        return out


def _eigenvector(adjacency: Mapping[str, set[str]], iterations: int = 60) -> dict[str, float]:
    """Deterministic power iteration on a company–company adjacency map."""
    if not adjacency:
        return {}
    values = {node: 1.0 for node in adjacency}
    for _ in range(iterations):
        updated = {node: 0.0 for node in adjacency}
        for node, neighbours in adjacency.items():
            for other in neighbours:
                updated[node] += values.get(other, 0.0)
        norm = math.sqrt(sum(value * value for value in updated.values()))
        if norm == 0:
            return {node: 0.0 for node in adjacency}
        values = {node: value / norm for node, value in updated.items()}
    return values


class FastLogisticRegression:
    """Vectorised, numerically identical form of ``LogisticBaseline``.

    Same algorithm as ``medradar.intelligence.models.baseline.LogisticBaseline``:
    train-only median imputation, train-only standardisation, missing-indicator
    columns, full-batch gradient descent on the log-loss with an L2 penalty,
    intercept initialised to the training log-odds, ``epochs=180, lr=0.15, l2=1.0``.
    Only the arithmetic is vectorised, so a 41k-row x 28-feature rolling-origin
    experiment becomes tractable without changing the learner. ``parity_check``
    proves agreement with the reference implementation.
    """

    def __init__(self, feature_names: Iterable[str], *, epochs: int = 180,
                 learning_rate: float = 0.15, l2: float = 1.0) -> None:
        import numpy as np
        self._np = np
        self.feature_names = list(feature_names)
        self.epochs = epochs
        self.learning_rate = learning_rate
        self.l2 = l2
        self.medians: dict[str, float] = {}
        self.means = None
        self.scales = None
        self.weights = None
        self.intercept = 0.0
        self.missing_features: list[str] = []

    def _raw(self, rows: list[dict[str, Any]]) -> Any:
        np = self._np
        matrix = np.empty((len(rows), len(self.feature_names)), dtype=float)
        for j, name in enumerate(self.feature_names):
            column = []
            for row in rows:
                value = row.get(name)
                try:
                    value = float(value) if value is not None else float("nan")
                except (TypeError, ValueError):
                    value = float("nan")
                column.append(value if math.isfinite(value) else float("nan"))
            matrix[:, j] = column
        return matrix

    def fit(self, rows: list[dict[str, Any]], labels: list[int]) -> "FastLogisticRegression":
        np = self._np
        if not rows:
            raise ValueError("no training rows")
        raw = self._raw(rows)
        for j, name in enumerate(self.feature_names):
            column = raw[:, j]
            observed = column[np.isfinite(column)]
            self.medians[name] = float(np.median(observed)) if observed.size else 0.0
            raw[~np.isfinite(raw[:, j]), j] = self.medians[name]
        self.missing_features = [name for name in self.feature_names
                                 if any(row.get(name) is None for row in rows)]
        design = raw
        self.means = design.mean(axis=0)
        scales = design.std(axis=0)
        self.scales = np.where(scales > 1e-6, scales, 1e-6)
        design = (design - self.means) / self.scales
        if self.missing_features:
            missing = np.array([[1.0 if row.get(name) is None else 0.0
                                 for name in self.missing_features] for row in rows])
            design = np.hstack([design, missing])
        y = np.asarray(labels, dtype=float)
        prevalence = min(max(y.mean(), 1e-5), 1 - 1e-5)
        self.weights = np.zeros(design.shape[1])
        self.intercept = math.log(prevalence / (1 - prevalence))
        n = len(rows)
        for _ in range(self.epochs):
            linear = design @ self.weights + self.intercept
            probability = 1.0 / (1.0 + np.exp(-np.clip(linear, -700, 700)))
            error = probability - y
            gradient = design.T @ error / n + self.l2 * self.weights / n
            self.weights -= self.learning_rate * gradient
            self.intercept -= self.learning_rate * error.mean()
        return self

    def predict_proba(self, rows: list[dict[str, Any]]) -> list[float]:
        np = self._np
        if self.weights is None:
            raise ValueError("model is not fitted")
        raw = self._raw(rows)
        for j, name in enumerate(self.feature_names):
            raw[~np.isfinite(raw[:, j]), j] = self.medians[name]
        design = (raw - self.means) / self.scales
        if self.missing_features:
            missing = np.array([[1.0 if row.get(name) is None else 0.0
                                 for name in self.missing_features] for row in rows])
            design = np.hstack([design, missing])
        linear = design @ self.weights + self.intercept
        return (1.0 / (1.0 + np.exp(-np.clip(linear, -700, 700)))).tolist()


def parity_check(rows: list[dict[str, Any]], labels: list[int],
                 feature_names: Iterable[str], sample: int = 400) -> dict[str, Any]:
    """Prove FastLogisticRegression reproduces LogisticBaseline predictions."""
    from medradar.intelligence.models.baseline import LogisticBaseline
    names = list(feature_names)
    train = rows[:sample]
    train_y = labels[:sample]
    test = rows[: min(200, len(rows))]
    reference = LogisticBaseline(names).fit(train, train_y)
    fast = FastLogisticRegression(names).fit(train, train_y)
    a = reference.predict_proba(test)
    b = fast.predict_proba(test)
    max_abs = max(abs(x - y) for x, y in zip(a, b)) if a else 0.0
    return {"n_train": len(train), "n_test": len(test), "max_abs_diff": max_abs,
            "ok": max_abs < 1e-9}


def fast_ap(labels: Any, probabilities: Any) -> float | None:
    """Average Precision with the repository's exact tie-group semantics.

    Vectorised copy of ``medradar.intelligence.evaluation.metrics.pr_auc``: scores
    are sorted descending, each block of equal scores is one threshold, and
    precision is integrated over recall. ``ap_parity_check`` proves equality.
    """
    import numpy as np
    y = np.asarray(labels, dtype=float)
    p = np.asarray(probabilities, dtype=float)
    if y.size == 0:
        return None
    positives = y.sum()
    if positives <= 0 or positives >= y.size:
        return None
    order = np.argsort(-p, kind="stable")
    y_sorted = y[order]
    p_sorted = p[order]
    tp = np.cumsum(y_sorted)
    fp = np.arange(1, y.size + 1) - tp
    # last index of every equal-score block
    boundaries = np.flatnonzero(np.r_[p_sorted[1:] != p_sorted[:-1], True])
    recall = tp[boundaries] / positives
    precision = tp[boundaries] / np.maximum(tp[boundaries] + fp[boundaries], 1.0)
    previous = np.r_[0.0, recall[:-1]]
    return float(np.sum((recall - previous) * precision))


def ap_parity_check(trials: int = 200, seed: int = 11) -> dict[str, Any]:
    """Prove ``fast_ap`` equals the repository's ``pr_auc`` on random data with ties."""
    import random
    from medradar.intelligence.evaluation.metrics import pr_auc
    rng = random.Random(seed)
    worst = 0.0
    for _ in range(trials):
        n = rng.randrange(5, 120)
        # coarse grid on purpose, to generate many ties
        probs = [rng.randrange(0, 12) / 11.0 for _ in range(n)]
        labels = [1 if rng.random() < 0.3 else 0 for _ in range(n)]
        if 0 < sum(labels) < n:
            worst = max(worst, abs(pr_auc(labels, probs) - fast_ap(labels, probs)))
    return {"trials": trials, "max_abs_diff": worst, "ok": worst < 1e-12}


def paired_cluster_bootstrap(pred_a: dict[str, Any], pred_b: dict[str, Any],
                             windows: list[str], unit: str = "company", *,
                             resamples: int = 2000, seed: int = 7,
                             mde_z: float = 1.959964 + 0.841621) -> dict[str, Any]:
    """Paired cluster bootstrap of AP(a) - AP(b), resampling whole clusters."""
    import numpy as np
    labels: list[int] = []
    probs_a: list[float] = []
    probs_b: list[float] = []
    clusters: list[str] = []
    for window in windows:
        a, b = pred_a.get(window), pred_b.get(window)
        if a is None or b is None or a["labels"] != b["labels"]:
            continue
        labels.extend(a["labels"])
        probs_a.extend(a["probs"])
        probs_b.extend(b["probs"])
        clusters.extend(a["companies"] if unit == "company" else a["pairs"])
    if not labels:
        return {"rows": 0, "delta": None, "ci_low": None, "ci_high": None,
                "se": None, "mde_80": None, "p_one_sided": None, "unit": unit}
    y = np.asarray(labels, dtype=float)
    pa = np.asarray(probs_a, dtype=float)
    pb = np.asarray(probs_b, dtype=float)
    point_a, point_b = fast_ap(y, pa), fast_ap(y, pb)
    point = (point_a - point_b) if point_a is not None and point_b is not None else None
    groups: dict[str, list[int]] = defaultdict(list)
    for index, key in enumerate(clusters):
        groups[key].append(index)
    order = sorted(groups)
    index_arrays = [np.asarray(groups[key], dtype=int) for key in order]
    rng = np.random.default_rng(seed)
    draws = []
    for _ in range(resamples):
        picks = rng.integers(0, len(index_arrays), size=len(index_arrays))
        sample = np.concatenate([index_arrays[i] for i in picks])
        sample_y = y[sample]
        if sample_y.sum() in (0, sample_y.size):
            continue
        value_a, value_b = fast_ap(sample_y, pa[sample]), fast_ap(sample_y, pb[sample])
        if value_a is None or value_b is None:
            continue
        draws.append(value_a - value_b)
    if not draws:
        return {"rows": len(labels), "delta": point, "ci_low": None, "ci_high": None,
                "se": None, "mde_80": None, "p_one_sided": None, "unit": unit,
                "ap_a": point_a, "ap_b": point_b}
    values = np.asarray(draws)
    se = float(values.std(ddof=1))
    low, high = float(np.quantile(values, 0.025)), float(np.quantile(values, 0.975))
    return {
        "rows": int(y.size), "positives": int(y.sum()), "clusters": len(order),
        "resampling_unit": unit, "seed": seed, "resamples_valid": int(values.size),
        "ap_a": point_a, "ap_b": point_b, "delta": point,
        "ci_low": low, "ci_high": high, "se": se, "mde_80": mde_z * se,
        "p_one_sided": float((values <= 0).mean()),
        "excludes_zero": bool(low > 0 or high < 0),
    }


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")
