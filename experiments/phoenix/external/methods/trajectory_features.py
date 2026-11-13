"""Trajectory features shared by the M3 (NIH co-citation cluster trajectories) and
M5 (PTNS patent citation trajectories) method audits.

WHAT THIS IS
------------
An independent re-implementation of the *published method logic* for:

  M3  NIH / Davis et al. (2025) bioRxiv doi:10.64898/2025.12.16.694385
      - historical snapshot construction and cluster-to-cluster trajectory linking
        ("asking if they shared a simple majority of their papers")
      - the four diagnostic features named in the public text:
        %New, ancestral %New, topical cohesion (entropy), influence (whRCR)
      - contemporaneous-only influence accounting (the paper's "hRCR" idea:
        never use citations received after the snapshot year)

  M5  Ding et al. (2024) Sci Rep 14:24034, doi:10.1038/s41598-024-75913-0
      - network snapshots taken by publication year
      - new / grown / random patent subtasks (<2, >4 citations; random)
      - Richards (generalised logistic) growth-curve trajectory fitting
      - MALE and RMSLE evaluation metrics
      - multi-horizon evaluation (T+1 .. T+N)

WHAT THIS IS NOT
----------------
No original data and no original model. M5's learner is an R-GCN + BiLSTM stack
whose code and data are NOT public; the deep model is deliberately not
re-implemented here. Only the trajectory/feature/evaluation *protocol* is, with a
transparent statistical baseline standing in for the learner so the protocol can
be exercised end-to-end. This reproduces no number from either paper.

DEFINITIONAL AMBIGUITIES CARRIED FORWARD FROM THE SOURCES (documented, not hidden)
--------------------------------------------------------------------------------
1. M3's cohesion feature is only described as "entropy"; the distribution it is
   computed over lives in supplementary Methods, which were not retrieved. Here it
   is the Shannon entropy of a supplied external partition of a cluster's papers
   (e.g. journal or MeSH-term bins), normalised by log(k). Caller supplies the bins.
2. M3's trajectory link rule says "a simple majority of their papers" without
   stating whether the majority is of the earlier or the later cluster. Both are
   implemented; the default is a majority of the later (terminal) cluster, because
   the paper's chaining narration runs backwards from the present.
3. M5 measures are named MALE ("mean absolute logarithmic error") but described as
   a "mean squared difference between the logarithms". Both readings are provided.
4. M5's Richards curve parameters are named in the text but the equations are
   images in the published PDF/HTML; the form below is the standard generalised
   logistic curve they describe and is stated explicitly so a reader can check it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Iterable, Sequence

import numpy as np
from scipy import optimize


# --------------------------------------------------------------------------- #
# 1. Snapshot / cluster trajectory construction (M3)
# --------------------------------------------------------------------------- #
@dataclass
class ClusterSnapshot:
    """One topic cluster as observed in the network built from data up to `year`.

    papers: {paper_id: publication_year}
    influence: {paper_id: contemporaneous influence value}  (M3's hRCR)
    """

    year: int
    papers: dict[str, int] = field(default_factory=dict)
    influence: dict[str, float] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.papers:
            raise ValueError("cluster snapshot must contain at least one paper")

    @property
    def n_papers(self) -> int:
        return len(self.papers)


def pct_new(cluster: ClusterSnapshot) -> float:
    """M3 %New: fraction of the cluster's papers published in year x or x-1.

    Quoted definition (public text): "the number of papers published in calendar
    years 1995 and 1996 can easily be calculated as a percentage of all papers
    assigned to that 1996 cluster". So this is deliberately a two-year window, not
    a one-year window -- a detail that is easy to get wrong.
    """
    x = cluster.year
    recent = sum(1 for y in cluster.papers.values() if y in (x, x - 1))
    return recent / cluster.n_papers


def ancestral_pct_new(trajectory: Sequence[ClusterSnapshot]) -> float:
    """%New of the most recent ancestor of the last cluster in the sequence.

    "measures the growth of the literature contained in a cluster's most recent
    ancestor". Returns 0.0 for a trajectory with a single cluster (no ancestor is
    observable), which is the conservative reading.
    """
    if len(trajectory) < 2:
        return 0.0
    return pct_new(trajectory[-2])


def shannon_entropy(partition_counts: Iterable[float]) -> float:
    """Shannon entropy (nats) of a categorical distribution."""
    c = np.asarray(list(partition_counts), dtype=float)
    c = c[c > 0]
    if c.size == 0:
        raise ValueError("empty partition")
    p = c / c.sum()
    return float(-np.sum(p * np.log(p)))


def topical_cohesion(partition_counts: Iterable[float]) -> float:
    """M3 cohesion proxy: 1 - normalised entropy of an external partition.

    1.0 = all papers fall in one bin (maximally cohesive); 0.0 = papers spread
    uniformly over all supplied bins. M3 reports that signal clusters have *lower*
    cohesion than matched controls, i.e. higher entropy.
    """
    c = np.asarray([v for v in partition_counts], dtype=float)
    c = c[c > 0]
    if c.size <= 1:
        return 1.0
    return 1.0 - shannon_entropy(c) / np.log(c.size)


def whrcr(cluster: ClusterSnapshot) -> float:
    """M3 whRCR: the sum of contemporaneous influence values over the cluster."""
    return float(sum(cluster.influence.values()))


def contemporaneous_influence(
    citations: dict[str, Sequence[tuple[int, int]]],
    year: int,
) -> dict[str, float]:
    """Compute hRCR-style influence using only citations received up to `year`.

    citations maps paper_id -> [(citing_year, count), ...]. Anything dated after
    `year` is discarded, which is the leakage-avoidance rule the M3 paper calls out
    explicitly ("we needed to detect past examples of diagnostic signals without
    relying upon information leaked from the future").
    """
    out: dict[str, float] = {}
    for pid, series in citations.items():
        out[pid] = float(sum(cnt for y, cnt in series if y <= year))
    return out


def link_trajectories(
    snapshots: Sequence[ClusterSnapshot],
    rule: str = "of_terminal",
) -> list[list[int]]:
    """Chain clusters across yearly snapshots into trajectories by paper overlap.

    Returns a list of trajectories, each a list of indices into `snapshots`
    ordered by year. `rule`:
      "of_terminal" - majority of the later cluster's papers are shared
      "of_both"     - majority of both clusters are shared
      "of_earlier"  - majority of the earlier cluster's papers are shared
    A cluster may extend at most one predecessor here (the common, simple case);
    branching is reported rather than silently forced, via find_branches().
    """
    if rule not in {"of_terminal", "of_both", "of_earlier"}:
        raise ValueError(f"unknown rule: {rule}")
    order = sorted(range(len(snapshots)), key=lambda i: snapshots[i].year)
    # Only one snapshot per year is supported for chaining.
    years = [snapshots[i].year for i in order]
    if len(set(years)) != len(years):
        raise ValueError("link_trajectories expects at most one snapshot per year")

    pred: dict[int, int] = {}
    for pos in range(1, len(order)):
        cur_i = order[pos]
        prev_i = order[pos - 1]
        cur = set(snapshots[cur_i].papers)
        prev = set(snapshots[prev_i].papers)
        shared = len(cur & prev)
        if shared == 0:
            continue
        ok = {
            "of_terminal": shared > len(cur) / 2,
            "of_earlier": shared > len(prev) / 2,
            "of_both": shared > len(cur) / 2 and shared > len(prev) / 2,
        }[rule]
        if ok:
            pred[cur_i] = prev_i

    # Build forward links from the predecessor map, then read chains off the roots.
    children: dict[int, list[int]] = {}
    for child, parent in pred.items():
        children.setdefault(parent, []).append(child)
    for v in children.values():
        v.sort()

    chains: list[list[int]] = []
    covered: set[int] = set()

    def walk(start: int) -> None:
        chain = [start]
        covered.add(start)
        cur = start
        while cur in children:
            nxt = [c for c in children[cur] if c not in covered]
            if not nxt:
                break
            # A split (2+ children) is reported by find_branches(); here each
            # branch becomes its own trajectory rather than being forced into one.
            cur = nxt[0]
            chain.append(cur)
            covered.add(cur)
        chains.append(chain)

    for i in order:
        if i not in pred and i not in covered:
            walk(i)
    for i in order:  # any node not reachable from a root becomes its own chain
        if i not in covered:
            walk(i)
    return chains


def find_branches(snapshots: Sequence[ClusterSnapshot], rule: str = "of_terminal") -> list[dict]:
    """Report split events: one cluster with more than one majority-overlap successor.

    M3 calls these merge/split events (convergence/divergence) and reports that they
    are unusually common next to a breakthrough relative to base rates of 0.90%
    (convergence) and 1.47% (divergence). Convergence is the mirror case, detected
    here as a later cluster whose majority-overlap set contains more than one
    earlier cluster.
    """
    order = sorted(range(len(snapshots)), key=lambda i: snapshots[i].year)
    splits: list[dict] = []
    for pos in range(len(order) - 1):
        a, b = order[pos], order[pos + 1]
        pa, pb = set(snapshots[a].papers), set(snapshots[b].papers)
        shared = len(pa & pb)
        if shared == 0:
            continue
        ok = {
            "of_terminal": shared > len(pb) / 2,
            "of_earlier": shared > len(pa) / 2,
            "of_both": shared > len(pb) / 2 and shared > len(pa) / 2,
        }[rule]
        if ok:
            splits.append({"from": a, "to": b, "shared": shared})
    # a genuine split = one predecessor accepted by 2+ successors
    by_from: dict[int, list[int]] = {}
    for s in splits:
        by_from.setdefault(s["from"], []).append(s["to"])
    return [{"from": k, "to": v} for k, v in by_from.items() if len(v) > 1]


def trajectory_features(
    trajectory: Sequence[ClusterSnapshot],
    cohesion_bins: Sequence[float] | None = None,
) -> dict:
    """Bundle the four M3 diagnostic features for the final cluster of a trajectory.

    `cohesion_bins` are the counts of the terminal cluster's papers across an
    external topical partition (journal / MeSH / any independent binning). It is
    optional only because the binning must be supplied by the caller; when omitted
    the cohesion key is set to None rather than guessed.
    """
    if not trajectory:
        raise ValueError("empty trajectory")
    last = trajectory[-1]
    return {
        "year": last.year,
        "n_papers": last.n_papers,
        "pct_new": pct_new(last),
        "ancestral_pct_new": ancestral_pct_new(trajectory),
        "whrcr": whrcr(last),
        "cohesion": topical_cohesion(cohesion_bins) if cohesion_bins is not None else None,
        "trajectory_length": len(trajectory),
    }


# --------------------------------------------------------------------------- #
# 2. Richards growth curve (M5)
# --------------------------------------------------------------------------- #
def richards(
    t: np.ndarray | float,
    K: float,
    B: float,
    nu: float,
    t0: float,
    Q: float = 1.0,
) -> np.ndarray:
    """Generalised logistic (Richards) curve for cumulative citations.

        Y(t) = K / (1 + Q * exp(-B * (t - t0))) ** (1 / nu)

    K  asymptote (peak cumulative citations)
    B  growth rate
    nu shape / smoothness (nu = 1 reduces to the ordinary logistic)
    t0 inflection point
    Q  lag-phase offset (Q >> 1 pushes the take-off later)

    The M5 text names four curve parameters (peak, rate, lag, smoothness) that map
    onto K, B, t0 and nu; Q is the extra offset that makes the lag explicit.
    """
    t = np.asarray(t, dtype=float)
    return K / (1.0 + Q * np.exp(-B * (t - t0))) ** (1.0 / nu)


def fit_richards(
    years: Sequence[float],
    cumulative: Sequence[float],
) -> dict:
    """Least-squares fit of the Richards curve; returns params + fit quality."""
    y = np.asarray(years, dtype=float)
    c = np.asarray(cumulative, dtype=float)
    if y.shape != c.shape:
        raise ValueError("years and cumulative must have the same length")
    K0 = max(c.max(), 1.0) * 1.5
    p0 = [K0, 0.4, 1.0, float(np.mean(y)), 1.0]
    bounds = ([max(c.max(), 1e-9) * 1.0001, 1e-4, 1e-3, y.min() - 50, 1e-3],
              [max(c.max(), 1e-9) * 100 + 1e3, 5.0, 20.0, y.max() + 50, 1e3])
    try:
        popt, _ = optimize.curve_fit(richards, y, c, p0=p0, bounds=bounds, maxfev=20000)
        fitted = richards(y, *popt)
        sse = float(np.sum((c - fitted) ** 2))
        sst = float(np.sum((c - c.mean()) ** 2))
        return {
            "params": {"K": float(popt[0]), "B": float(popt[1]), "nu": float(popt[2]),
                       "t0": float(popt[3]), "Q": float(popt[4])},
            "sse": sse,
            "r2": 1.0 - sse / sst if sst > 0 else float("nan"),
            "ok": True,
        }
    except (RuntimeError, ValueError) as exc:
        return {"params": None, "sse": float("nan"), "r2": float("nan"), "ok": False,
                "error": str(exc)}


# --------------------------------------------------------------------------- #
# 3. Evaluation metrics (M5)
# --------------------------------------------------------------------------- #
def male(y_true: Sequence[float], y_pred: Sequence[float]) -> float:
    """Mean Absolute Logarithmic Error: mean |ln(1+y_hat) - ln(1+y)|.

    Name-faithful reading of "MALE". Targets are cumulative citation counts, which
    can be 0, so log1p is used (the paper does not state its offset - see audit).
    """
    a = np.log1p(np.clip(np.asarray(y_true, dtype=float), 0, None))
    b = np.log1p(np.clip(np.asarray(y_pred, dtype=float), 0, None))
    return float(np.mean(np.abs(b - a)))


def msle(y_true: Sequence[float], y_pred: Sequence[float]) -> float:
    """Mean Squared Logarithmic Error: the paper's alternative wording for MALE."""
    a = np.log1p(np.clip(np.asarray(y_true, dtype=float), 0, None))
    b = np.log1p(np.clip(np.asarray(y_pred, dtype=float), 0, None))
    return float(np.mean((b - a) ** 2))


def rmsle(y_true: Sequence[float], y_pred: Sequence[float]) -> float:
    """Root Mean Squared Logarithmic Error."""
    return float(np.sqrt(msle(y_true, y_pred)))


# --------------------------------------------------------------------------- #
# 4. Backtest protocol (M5)
# --------------------------------------------------------------------------- #
def cumulative_series(
    events: dict[str, Sequence[tuple[int, int]]],
    years: Sequence[int],
) -> dict[str, list[int]]:
    """Convert {id: [(citing_year, count)]} into cumulative counts at each year."""
    return {pid: cumulative_from_events(series, years) for pid, series in events.items()}


def cumulative_from_events(
    events: Sequence[tuple[int, int]],
    years: Sequence[int],
) -> list[int]:
    """Cumulative citation counts for one entity at each observation year.

    Only citations dated in the given year contribute to that year's increment,
    so the series is contemporaneous by construction: no future citation can enter
    an earlier snapshot.
    """
    years = list(years)
    by_year: dict[int, int] = {}
    for y, cnt in events:
        by_year[int(y)] = by_year.get(int(y), 0) + int(cnt)
    out, run = [], 0
    for y in years:
        run += by_year.get(int(y), 0)
        out.append(run)
    return out


def assign_subtask(final_cumulative: int, subtask: str) -> bool:
    """M5 subtask membership: new < 2 citations, grown > 4 citations, random = all.

    Quoted: "New Patents ... less than 2", "Grown Patents ... greater than 4",
    "Random Patents ... randomly sampled without restricting the citation
    frequency". Note the gap (exactly 2, 3 or 4 citations) belongs to no restricted
    subtask; that gap is reproduced faithfully rather than silently closed.
    """
    if subtask == "new":
        return final_cumulative < 2
    if subtask == "grown":
        return final_cumulative > 4
    if subtask == "random":
        return True
    raise ValueError(f"unknown subtask: {subtask}")


def rolling_origin_backtest(
    series: dict[str, list[int]],
    years: Sequence[int],
    history: int = 10,
    horizons: Sequence[int] = (1, 3, 5, 10),
    subtask: str = "random",
    model: Callable[[np.ndarray], float] | None = None,
    seed: int = 0,
) -> dict:
    """Evaluate a per-trajectory forecaster at several horizons.

    Protocol mirroring M5: fit on the first `history` snapshots, predict the
    cumulative count at T+N for each N, score with MALE/RMSLE, and report by
    subtask. `model` receives the history vector and returns a predicted future
    cumulative count; the default is a transparent log-linear extrapolation, which
    is a *baseline*, not the papers' learner.
    """
    years = list(years)
    if history >= len(years):
        raise ValueError("history window must be shorter than the series")
    if model is None:
        model = _loglinear_forecast
    rng = np.random.default_rng(seed)
    rows = []
    for pid, seq in series.items():
        hist = np.asarray(seq[:history], dtype=float)
        final = int(seq[-1])
        if not assign_subtask(final, subtask):
            continue
        for n in horizons:
            idx = min(history + n, len(seq)) - 1
            truth = float(seq[idx])
            pred = float(model(hist))
            rows.append({"id": pid, "horizon": int(n), "truth": truth, "pred": pred})
    if not rows:
        return {"n": 0, "subtask": subtask, "per_horizon": []}
    per_h = []
    for n in horizons:
        sub = [r for r in rows if r["horizon"] == n]
        if not sub:
            continue
        yt = [r["truth"] for r in sub]
        yp = [r["pred"] for r in sub]
        per_h.append({
            "horizon": int(n),
            "n": len(sub),
            "male": male(yt, yp),
            "rmsle": rmsle(yt, yp),
            "msle": msle(yt, yp),
        })
    return {"n": len(rows), "subtask": subtask, "history": history, "per_horizon": per_h}


def _loglinear_forecast(history: np.ndarray) -> float:
    """Baseline: extrapolate log1p(cumulative) with a least-squares line, then invert."""
    h = np.asarray(history, dtype=float)
    if h.size < 2 or np.all(h == h[0]):
        return float(h[-1])
    x = np.arange(h.size, dtype=float)
    coef = np.polyfit(x, np.log1p(h), 1)
    next_x = float(h.size)  # one step beyond the history window
    return float(np.expm1(np.polyval(coef, next_x)))


if __name__ == "__main__":
    c = ClusterSnapshot(year=1996, papers={"p1": 1974, "p2": 1995, "p3": 1996},
                        influence={"p1": 1.0, "p2": 2.0, "p3": 3.0})
    print(pct_new(c), whrcr(c))
    print(richards(np.array([0, 5, 10]), 100, 0.5, 1.0, 5.0, 1.0))
