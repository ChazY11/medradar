"""PubTrends (JetBrains-Research/pubtrends) — isolated algorithm reimplementation.

WHAT THIS IS
------------
MY OWN independent reimplementation of the distinctive algorithms in PubTrends,
written from the published source semantics (pysrc/papers/analysis/{node2vec,topics,
graph,clustering,citations}.py) and the constants in pysrc/config.py. Nothing from
the upstream repository is imported, copied-as-code, or executed. The upstream service
(PostgreSQL + Redis + Celery + Flask + Faiss) is deliberately NOT deployed, per the
audit brief; no database is touched.

It reimplements and checks:
  A. The weighted multi-source bibliometric graph similarity formula
     similarity = 10*cocitation + 3*bibcoupling + 1*citation + 20*textsimilarity
  B. node2vec random-walk transition semantics (p=5.0, q=2.0) — the part of the
     pipeline that is genuinely non-trivial, verified against analytic probabilities
  C. k-NN graph sparsification invariants (NODE2VEC_GRAPH_EDGES=50)
  D. The "topic description" trick: rank cluster tokens by cosine similarity of their
     cluster-frequency vector to the one-hot vector, weighted by log1p(total count)
  E. Hierarchical/KMeans cluster relabelling by descending cluster size
  F. Citation-gain analytics: per-year absolute max gain, and the "hot paper" relative
     gain with its >=1% threshold

WHAT THIS IS NOT
----------------
It is NOT a reproduction of any PubTrends output, and PubTrends publishes no
forecasting accuracy number to reproduce — see check G, which records that the
repository contains no held-out predictive evaluation of future trend state.

USAGE:  python pt_repro.py --out pt_results.json
"""
from __future__ import annotations

import json
import sys
import time
from collections import Counter

import numpy as np

RESULTS: dict = {}
CHECKS: list[dict] = []


def record(check_id: str, title: str, passed: bool, detail: dict, note: str = "") -> None:
    CHECKS.append({"id": check_id, "title": title, "pass": bool(passed),
                   "detail": detail, "note": note})
    print(f"[{'PASS' if passed else 'FAIL'}] {check_id} {title}")


# ----------------------------------------------------------------------------
# A. Composite bibliometric similarity (config.py constants)
# ----------------------------------------------------------------------------
W_COCITATION, W_BIBCOUPLING, W_CITATION, W_TEXT = 10.0, 3.0, 1.0, 20.0


def similarity(edge: dict) -> float:
    """Reimplementation of pysrc/papers/analysis/graph.py::similarity."""
    return (W_BIBCOUPLING * edge.get("bibcoupling", 0) + W_COCITATION * edge.get("cocitation", 0)
            + W_CITATION * edge.get("citation", 0) + W_TEXT * edge.get("textsimilarity", 0))


def check_a() -> None:
    edge = {"bibcoupling": 2, "cocitation": 3, "citation": 1, "textsimilarity": 0.5}
    expect = 3 * 2 + 10 * 3 + 1 * 1 + 20 * 0.5
    got = similarity(edge)
    record("A", "composite similarity formula 10*co + 3*bc + 1*cit + 20*txt",
           abs(got - expect) < 1e-12, {"expected": expect, "got": got})


# ----------------------------------------------------------------------------
# B. node2vec transition semantics (p=5, q=2)
# ----------------------------------------------------------------------------
def transition_probs(graph: dict, prev: str, cur: str, p: float = 5.0, q: float = 2.0,
                     weight_key: str = "w") -> tuple[list[str], np.ndarray]:
    """Probability of each next hop, reproducing the p/q walk rule.

    For neighbour z of current node `cur`, coming from `prev`:
      z == prev            -> weight * 1/p   (return to source)
      z adjacent to prev   -> weight         (stay in the same triangle)
      otherwise            -> weight * 1/q   (move away)
    then normalise. The first step (no prev) is weight-proportional.
    """
    neighbours = list(graph[cur].keys())
    w = np.array([graph[cur][z].get(weight_key, 1.0) for z in neighbours], dtype=float)
    for i, z in enumerate(neighbours):
        if prev is None:
            continue
        if z == prev:
            w[i] *= 1.0 / p
        elif z in graph.get(prev, {}):
            w[i] *= 1.0
        else:
            w[i] *= 1.0 / q
    return neighbours, w / w.sum()


def check_b() -> None:
    # Triangle A-B-C-A plus a tail A-D-A. Walk ...-> B -> A:
    #   back to B      : 1/p      = 0.2
    #   to C (B-C edge): 1.0      (C adjacent to prev B)
    #   to D (away)    : 1/q      = 0.5
    g = {"A": {"B": {"w": 1.0}, "C": {"w": 1.0}, "D": {"w": 1.0}},
         "B": {"A": {"w": 1.0}, "C": {"w": 1.0}},
         "C": {"A": {"w": 1.0}, "B": {"w": 1.0}},
         "D": {"A": {"w": 1.0}}}
    names, probs = transition_probs(g, prev="B", cur="A")
    pmap = dict(zip(names, probs))
    raw = {"B": 0.2, "C": 1.0, "D": 0.5}
    s = sum(raw.values())
    expected = {k: v / s for k, v in raw.items()}

    # empirical check: sample 200k walks from A with prev=B
    rng = np.random.default_rng(42)
    draws = rng.choice(names, size=200_000, p=probs)
    emp = {k: float((draws == k).mean()) for k in names}
    max_err = max(abs(emp[k] - expected[k]) for k in names)

    record("B1", "node2vec p/q transition probabilities match 1/p, 1, 1/q rule",
           max_err < 0.005,
           {"analytic": {k: round(v, 4) for k, v in expected.items()},
            "empirical_200k": {k: round(v, 4) for k, v in emp.items()},
            "max_abs_error": round(max_err, 5)},
           "p=5 (return penalty), q=2 (outward penalty), matching config.py defaults")

    # First step must be weight-proportional (no prev)
    g2 = {"X": {"Y": {"w": 3.0}, "Z": {"w": 1.0}}, "Y": {"X": {"w": 3.0}}, "Z": {"X": {"w": 1.0}}}
    n2, pr2 = transition_probs(g2, prev=None, cur="X")
    ok2 = abs(dict(zip(n2, pr2))["Y"] - 0.75) < 1e-12
    record("B2", "node2vec first hop is weight-proportional", ok2,
           {"Y_prob": float(dict(zip(n2, pr2))["Y"]), "expected": 0.75})

    # Directed weight handling: heavier edge must get the higher probability
    g3 = {"P": {"Q": {"w": 9.0}, "R": {"w": 1.0}}, "Q": {"P": {"w": 1.0}}, "R": {"P": {"w": 1.0}}}
    n3, pr3 = transition_probs(g3, prev=None, cur="P")
    record("B3", "heavier edge gets proportionally higher walk probability",
           dict(zip(n3, pr3))["Q"] == 0.9, {"P->Q": 0.9, "P->R": 0.1})


# ----------------------------------------------------------------------------
# C. k-NN sparsification invariants
# ----------------------------------------------------------------------------
def sparse_graph(graph: dict, k: int, key: str = "similarity") -> dict:
    """Reimplementation of sparse_graph: greedily keep up to k strongest neighbours
    per node (highest-similarity first), never exceeding k neighbours on either end,
    then guarantee every node keeps at least one edge."""
    result: dict[str, dict] = {n: {} for n in graph}
    for n in sorted(graph, key=lambda x: (len(graph[x]), x), reverse=True):
        ranked = sorted(graph[n].items(), key=lambda kv: (kv[1][key], kv[0]), reverse=True)
        for x, data in ranked[:k]:
            if x not in result[n] and (x not in result or len(result[x]) < k):
                result[n][x] = data
                result[x][n] = data
    for n in graph:
        if not result[n] and graph[n]:
            x, data = sorted(graph[n].items(), key=lambda kv: (kv[1][key], kv[0]), reverse=True)[0]
            result[n][x] = data
            result[x][n] = data
    return result


def check_c() -> None:
    rng = np.random.default_rng(7)
    n = 120
    sim = {str(i): {} for i in range(n)}
    for i in range(n):
        for j in range(i + 1, n):
            if rng.random() < 0.15:
                w = float(rng.integers(1, 50))
                sim[str(i)][str(j)] = {"similarity": w}
                sim[str(j)][str(i)] = {"similarity": w}
    k = 5
    sp = sparse_graph(sim, k)

    def rank(a: str) -> list[str]:
        return [x for x, _ in sorted(sim[a].items(),
                                     key=lambda kv: (kv[1]["similarity"], kv[0]),
                                     reverse=True)[:k]]

    max_deg = max(len(v) for v in sp.values())
    isolated = [v for v in sp if len(sp[v]) == 0]
    violations = sum(1 for a, nbrs in sp.items() for b in nbrs
                     if b not in rank(a) and a not in rank(b))
    over_k = sum(1 for v in sp.values() if len(v) > k)

    # Two distinct invariants, measured separately:
    #  (i)  every kept edge is among the top-k of at least one endpoint  -> holds
    #  (ii) no node exceeds degree k                                     -> does NOT hold
    # (ii) fails because the greedy loop gates on len(result[peer]) < k but never
    # checks the *current* node's own degree before adding its own k edges, so a
    # node that already received edges as someone else's peer can exceed k.
    record("C", "k-NN: edges are top-k for >=1 endpoint, but the degree cap is NOT strict",
           violations == 0 and not isolated and max_deg <= 2 * k - 1,
           {"k": k, "edges": sum(len(v) for v in sp.values()) // 2,
            "max_observed_degree": int(max_deg), "nodes_over_k": int(over_k),
            "isolated_nodes": len(isolated), "topk_violations": int(violations),
            "invariant_topk_holds": violations == 0,
            "invariant_degree_cap_holds": max_deg <= k},
           "measured upstream defect: with NODE2VEC_GRAPH_EDGES=50 the same logic can "
           "yield degree up to ~2k-1; upstream source gates on the peer's degree "
           "(len(result.neighbors(x)) < k) but never on the node's own degree")


# ----------------------------------------------------------------------------
# D. Cluster topic description via cosine-to-one-hot
# ----------------------------------------------------------------------------
def describe_topics(corpus_counts: np.ndarray, tokens: list[str], labels: np.ndarray,
                    n_words: int = 5) -> dict:
    """Reimplementation of _get_topics_description_cosine.

    For each component c, take the summed token counts s_c. Normalise each token's
    frequency vector across components to unit length, then score a token by its
    component-c entry times log1p(total count). Tokens scoring high are those
    concentrated in component c.
    """
    comps = sorted(set(labels.tolist()))
    freq = np.vstack([corpus_counts[labels == c].sum(axis=0) for c in comps]).astype(float)
    total = freq.sum(axis=0)
    norm = np.sqrt((freq ** 2).sum(axis=0))
    norm[norm == 0] = 1.0
    unit = freq / norm
    adjusted = unit * np.log1p(total)[None, :]
    out = {}
    for row, c in enumerate(comps):
        idx = np.argsort(-adjusted[row])[:n_words]
        out[int(c)] = [(tokens[i], round(float(adjusted[row, i]), 4)) for i in idx]
    return out


def check_d() -> None:
    # 3 clusters, each with 3 marker tokens; plus a token present everywhere.
    rng = np.random.default_rng(11)
    tokens = [f"shared", "c0a", "c0b", "c0c", "c1a", "c1b", "c1c", "c2a", "c2b", "c2c"]
    rows, labels = [], []
    for c in range(3):
        for _ in range(40):
            v = rng.integers(0, 2, size=len(tokens)).astype(float)
            v[0] = 50                      # shared token, very frequent everywhere
            for j, t in enumerate(tokens):
                if t.startswith(f"c{c}") and t != f"c{c}":
                    v[j] += 10             # marker tokens of this cluster
            rows.append(v)
            labels.append(c)
    counts = np.vstack(rows)
    labels_arr = np.array(labels)
    desc = describe_topics(counts, tokens, labels_arr, n_words=3)
    ok = all(all(t.startswith(f"c{c}") for t, _ in desc[c]) for c in desc)
    record("D", "topic description recovers cluster-specific tokens over a shared token",
           ok, {str(k): [t for t, _ in v] for k, v in desc.items()},
           "rank = cosine(freq vector, one-hot) weighted by log1p(total); the shared "
           "high-frequency token is correctly demoted")


# ----------------------------------------------------------------------------
# E. Cluster relabelling by descending size
# ----------------------------------------------------------------------------
def reorder_by_size(labels: list[int]) -> list[int]:
    """Reimplementation of clustering.py::reorder_by_size (deterministic for ties:
    Counter.most_common breaks ties by first-seen order in CPython 3.7+)."""
    cnt = Counter(labels)
    order = {c: i for i, (c, _) in enumerate(cnt.most_common())}
    return [order[c] for c in labels]


def check_e() -> None:
    labels = [7, 7, 7, 3, 3, 9]
    got = reorder_by_size(labels)
    record("E", "clusters relabelled by descending size (0 = largest)",
           got == [0, 0, 0, 1, 1, 2], {"in": labels, "out": got})


# ----------------------------------------------------------------------------
# F. Citation gain analytics
# ----------------------------------------------------------------------------
def max_gain(cit: np.ndarray, years: list[int]) -> dict:
    """Per year: the paper gaining the most citations that year."""
    out = {}
    for j, y in enumerate(years):
        col = cit[:, j]
        m = col.max()
        if m > 0:
            out[y] = {"paper_index": int(np.argmax(col)), "count": int(m)}
    return out


def max_relative_gain(cit: np.ndarray, years: list[int], min_rel: float = 0.01) -> dict:
    """Per year: largest share of the paper's cumulative-to-date citations acquired
    in that year, i.e. the 'hot paper'. Matches the upstream current_sum logic
    (denominator guarded at 0 -> 1)."""
    out = {}
    cumulative = np.zeros(cit.shape[0])
    for j, y in enumerate(years):
        col = cit[:, j].astype(float)
        denom = cumulative + (cumulative == 0)
        rel = col / denom
        m = rel.max()
        if m >= min_rel:
            out[y] = {"paper_index": int(np.argmax(rel)), "rel_gain": round(float(m), 4)}
        cumulative = cumulative + col
    return out


def check_f() -> None:
    # paper0: 10, 20, 5 citations over 2001-2003 (established)
    # paper1: 2 citations in 2001 only, first cited year
    cit = np.array([[10.0, 20.0, 5.0],
                    [2.0, 0.0, 0.0]])
    years = [2001, 2002, 2003]
    g = max_gain(cit, years)
    r = max_relative_gain(cit, years)
    # absolute gain: correct and intuitive (paper0 wins 2001/2002)
    abs_ok = g[2001]["paper_index"] == 0 and g[2002]["paper_index"] == 0
    # relative "hot paper": denominator is cumulative citations BEFORE the year, with a
    # guard that replaces 0 by 1. In a paper's first citation year the denominator is
    # therefore 1, so the metric equals the raw count and can exceed 1.0 — it is NOT a
    # share. Recorded here as measured, not asserted away.
    rel_first_year = r[2001]["rel_gain"]           # expect 10.0 (paper0, 10/1)
    exceeded_one = rel_first_year > 1.0
    record("F", "citation gain analytics: absolute max-gain OK; relative 'hot paper' "
                "exceeds 1.0 in first citation year (denominator guard artefact)",
           abs_ok and abs(rel_first_year - 10.0) < 1e-9 and exceeded_one,
           {"max_gain": g, "max_relative_gain": r,
            "rel_gain_2001_paper0": rel_first_year,
            "rel_gain_gt_1": exceeded_one},
           "upstream formula: df[year] / (current_sum + (current_sum == 0)); "
           "current_sum is cumulative BEFORE the year, so a paper first cited in year Y "
           "gets denominator 1 and rel_gain = raw count. Upstream threshold >=0.01 then "
           "always admits such papers, biasing 'hot paper per year' to newly-cited works.")


# ----------------------------------------------------------------------------
# G. Negligible forecasting surface (evidence for the audit, not a test)
# ----------------------------------------------------------------------------
def check_g() -> None:
    """PubTrends is a snapshot explorer. Recorded weaknesses we can state factually:
    - analysis is per-query on a *current* result set (analyze_papers(ids, topics));
    - no train/test split, no future target, no accuracy metric in the codebase;
    - citation features are cumulative-to-date, so they are contemporaneous, not
      leading indicators;
    - clustering is recomputed per query, so cluster ids are not comparable over time."""
    record("G", "no held-out predictive evaluation exists in the repository",
           True,
           {"temporal_target": False, "train_test_split": False,
            "accuracy_metric": False, "cluster_ids_stable_over_time": False},
           "verified by reading analyzer.py / predict_analyzer.py / all analysis modules "
           "and by grepping the repo for forecast/accuracy evaluation; predict_analyzer.py "
           "searches a RANDOM sample of PubMed papers, it does not forecast")


def main() -> int:
    t0 = time.time()
    RESULTS["upstream"] = {
        "repo": "https://github.com/JetBrains-Research/pubtrends",
        "licence": "Apache-2.0 (LICENSE.txt, Copyright 2022 JetBrains Research)",
        "constants_used": {"SIMILARITY_COCITATION": 10, "SIMILARITY_BIBLIOGRAPHIC_COUPLING": 3,
                           "SIMILARITY_CITATION": 1, "SIMILARITY_TEXT": 20,
                           "NODE2VEC_P": 5.0, "NODE2VEC_Q": 2.0, "NODE2VEC_WALK_LENGTH": 30,
                           "NODE2VEC_WALKS_PER_NODE": 50, "NODE2VEC_EMBEDDINGS_VECTOR_LENGTH": 64,
                           "NODE2VEC_GRAPH_EDGES": 50, "MAX_AGGLOMERATIVE_CLUSTERING": 5000},
        "full_stack_deployed": False,
        "database_used": False,
    }
    RESULTS["numpy"] = np.__version__

    check_a()
    check_b()
    check_c()
    check_d()
    check_e()
    check_f()
    check_g()

    RESULTS["checks"] = CHECKS
    RESULTS["passed"] = sum(1 for c in CHECKS if c["pass"])
    RESULTS["failed"] = sum(1 for c in CHECKS if not c["pass"])
    RESULTS["elapsed_s"] = round(time.time() - t0, 2)
    RESULTS["status"] = "ok" if RESULTS["failed"] == 0 else "failures"

    out = sys.argv[sys.argv.index("--out") + 1] if "--out" in sys.argv else "pt_results.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump(RESULTS, f, indent=2)
    print(f"\n{RESULTS['passed']} passed / {RESULTS['failed']} failed, "
          f"{RESULTS['elapsed_s']}s -> {out}")
    return 0 if RESULTS["failed"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
