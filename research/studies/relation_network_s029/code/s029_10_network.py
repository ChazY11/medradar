"""S-029 step 10 — network feasibility (RQ4 section E) with an explicit gate.

The brief allows structural network analysis only after the relation evidence passes a
basic quality gate. The gate is evaluated *before* any structural number is interpreted,
and its outcome is printed and stored.

Gate (must all hold; stated in advance in GO_NO_GO_CRITERIA.md):
  G1 claims with an externally stable identifier on at least one side, >= 60% of claims
  G2 share of claims resting on fuzzy/undated identity <= 15%
  G3 anachronism-flagged claims <= 5% of claims
  G4 at least 3 of the 5 companies have >= 20 authoritative claims

If the gate fails, the structural numbers are still computed as an inventory (so the
report is complete) but the artefact marks them NON_INTERPRETABLE, and no claim about
network structure is made.

What is *never* computed here: centrality/community claims from a graph whose edges are
one publication or one registry field. Those quantities would inherit the measurement
error measured in sections B-D and cannot be validated in this data.

Run:  python research/studies/relation_network_s029/code/s029_10_network.py
Writes: artifacts/network_feasibility.json, data/network_edges.jsonl
"""

from __future__ import annotations

import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from s029_common import (ARTIFACT_DIR, DATA_DIR, read_jsonl, utcnow_iso, write_json,
                         write_jsonl)


def components(adjacency: dict[str, set]) -> list[int]:
    seen: set[str] = set()
    sizes = []
    for node in adjacency:
        if node in seen:
            continue
        stack = [node]
        size = 0
        seen.add(node)
        while stack:
            cur = stack.pop()
            size += 1
            for nxt in adjacency.get(cur, ()):
                if nxt not in seen:
                    seen.add(nxt)
                    stack.append(nxt)
        sizes.append(size)
    return sorted(sizes, reverse=True)


def main() -> None:
    claims = list(read_jsonl(DATA_DIR / "claims.jsonl"))
    entities = {e["entity_id"]: e for e in read_jsonl(DATA_DIR / "entities.jsonl")}
    evidence = {e["evidence_id"]: e for e in read_jsonl(DATA_DIR / "evidence.jsonl")}
    quality_path = ARTIFACT_DIR / "quality_metrics.json"
    quality = {}
    if quality_path.exists():
        from s029_common import read_json
        quality = read_json(quality_path)

    authoritative = [c for c in claims if c["claim_status"] in ("VERIFIED_BY_SOURCE", "CANDIDATE")]

    def has_stable(eid):
        ent = entities.get(eid) or {}
        return any(v for v in (ent.get("stable_external_ids") or {}).values() if v)

    stable_share = 100.0 * sum(1 for c in authoritative if has_stable(c["subject_id"])
                               or has_stable(c.get("object_id") or "")) / max(len(authoritative), 1)
    fuzzy = [c for c in claims if c.get("mapping_status") in ("FUZZY", "ALIAS_UNDATED",
                                                             "group_member_undated")]
    fuzzy_share = 100.0 * len(fuzzy) / max(len(claims), 1)
    anach = [c for c in claims if c.get("anachronism")]
    anach_share = 100.0 * len(anach) / max(len(claims), 1)
    per_company = Counter(c["subject_id"].split(":")[-1] for c in authoritative
                          if c["subject_id"].startswith("ent:company:"))
    companies_ge_20 = sum(1 for v in per_company.values() if v >= 20)

    gate = {
        "G1_stable_identifier_share": {"value": round(stable_share, 2), "threshold": ">=60%",
                                       "pass": stable_share >= 60.0},
        "G2_fuzzy_or_undated_share": {"value": round(fuzzy_share, 2), "threshold": "<=15%",
                                      "pass": fuzzy_share <= 15.0},
        "G3_anachronism_share": {"value": round(anach_share, 2), "threshold": "<=5%",
                                 "pass": anach_share <= 5.0},
        "G4_companies_with_20_claims": {"value": companies_ge_20, "threshold": ">=3 of 5",
                                        "pass": companies_ge_20 >= 3},
    }
    gate_passed = all(v["pass"] for v in gate.values())

    # ---------------- edges (deduped claim triples) ----------------
    edges = {}
    for c in authoritative:
        if not c.get("object_id"):
            continue
        key = (c["subject_id"], c["predicate"], c["object_id"])
        edges.setdefault(key, {"subject": key[0], "predicate": key[1], "object": key[2],
                               "roles": set(), "claim_ids": [], "years": set(),
                               "confidences": []})
        e = edges[key]
        e["roles"].add(c.get("relation_role"))
        e["claim_ids"].append(c["relation_id"])
        if c.get("published_at"):
            e["years"].add(c["published_at"][:4])
        e["confidences"].append(c.get("confidence") or 0)

    edge_rows = []
    for e in edges.values():
        edge_rows.append({"subject": e["subject"], "predicate": e["predicate"],
                          "object": e["object"], "roles": sorted(x for x in e["roles"] if x),
                          "n_claims": len(e["claim_ids"]),
                          "years": sorted(e["years"]),
                          "max_confidence": max(e["confidences"]) if e["confidences"] else 0})
    edge_rows.sort(key=lambda r: (r["predicate"], r["subject"], r["object"]))
    write_jsonl(DATA_DIR / "network_edges.jsonl", edge_rows)

    node_types = Counter((entities.get(e["subject"]) or {}).get("entity_type", "MISSING")
                         for e in edge_rows)
    node_types_obj = Counter((entities.get(e["object"]) or {}).get("entity_type", "MISSING")
                             for e in edge_rows)
    years = Counter()
    for e in edge_rows:
        for y in e["years"]:
            years[y] += 1

    # ---------------- graph projections ----------------
    # (1) company <-> institution co-affiliation graph
    co = [e for e in edge_rows if e["predicate"] == "CO_AFFILIATED_ON"]
    adj_co: dict[str, set] = defaultdict(set)
    for e in co:
        adj_co[e["subject"]].add(e["object"])
        adj_co[e["object"]].add(e["subject"])
    # (2) company <-> trial graph
    ct = [e for e in edge_rows if e["predicate"] in ("SPONSORS_TRIAL", "RESPONSIBLE_FOR_TRIAL")
          and e["subject"].startswith("ent:company:")]
    adj_ct: dict[str, set] = defaultdict(set)
    for e in ct:
        adj_ct[e["subject"]].add(e["object"])
        adj_ct[e["object"]].add(e["subject"])
    # (3) institution <-> trial graph
    it = [e for e in edge_rows if e["predicate"] in ("SPONSORS_TRIAL", "HOSTS_TRIAL_SITE")
          and e["subject"].startswith("ent:institution:")]
    adj_it: dict[str, set] = defaultdict(set)
    for e in it:
        adj_it[e["subject"]].add(e["object"])
        adj_it[e["object"]].add(e["subject"])

    def degrees(adj, prefix):
        d = sorted((len(v) for k, v in adj.items() if k.startswith(prefix)), reverse=True)
        return {"n_nodes": len(d), "max": d[0] if d else 0,
                "median": d[len(d) // 2] if d else 0, "mean": round(sum(d) / len(d), 2) if d else 0,
                "distribution_top10": d[:10]}

    # ---------------- sensitivity ----------------
    # What would the graph look like if we had used only the canonical company string?
    mentions = list(read_jsonl(DATA_DIR / "company_mentions.jsonl"))
    canon_only_records = set()
    for m in mentions:
        if m.get("rule") in ("canonical_token_exact",) and m.get("company_key"):
            canon_only_records.add(m["record_id"])
    all_company_records = {m["record_id"] for m in mentions if m.get("company_key")}
    sensitivity = {
        "records_with_a_company_mention": len(all_company_records),
        "records_reachable_by_exact_parent_name_only": len(canon_only_records),
        "share_lost_if_only_exact_parent_name_used_pct": round(
            100.0 * (len(all_company_records) - len(canon_only_records))
            / max(len(all_company_records), 1), 2),
        "interpretation": "the network a canonical-name-only study would see is a subset whose "
                          "size is stated here; the missing part is not random (it is dominated "
                          "by operating units and former names)",
    }

    out = {
        "generated_at": utcnow_iso(),
        "gate": gate,
        "gate_passed": gate_passed,
        "interpretable": gate_passed,
        "inventory": {
            "claims_authoritative": len(authoritative),
            "unique_edges": len(edge_rows),
            "edges_by_predicate": dict(Counter(e["predicate"] for e in edge_rows)),
            "subject_node_types": dict(node_types),
            "object_node_types": dict(node_types_obj),
            "edges_by_publication_year": dict(sorted(years.items())),
            "entities_total": len(entities),
            "entities_with_stable_ids": sum(1 for e in entities.values()
                                            if any(v for v in (e.get("stable_external_ids")
                                                               or {}).values() if v)),
        },
        "structure": {
            "company_institution_coaffiliation": {
                "n_edges": len(co),
                "components_sizes": components(adj_co)[:10],
                "company_degree": degrees(adj_co, "ent:company:"),
                "institution_degree": degrees(adj_co, "ent:institution:"),
            },
            "company_trial": {"n_edges": len(ct),
                              "components_sizes": components(adj_ct)[:10],
                              "company_degree": degrees(adj_ct, "ent:company:")},
            "institution_trial": {"n_edges": len(it),
                                  "components_sizes": components(adj_it)[:10],
                                  "institution_degree": degrees(adj_it, "ent:institution:")},
        },
        "sensitivity": sensitivity,
        "not_computed_and_why": [
            "centrality / community detection: a node's rank would be driven by how many "
            "papers happen to list it, which section D shows is a text-parsing artefact",
            "temporal edge prediction: requires point-in-time observations, see T4",
            "knowledge-flow direction: no source in this round states a direction",
        ],
    }
    write_json(ARTIFACT_DIR / "network_feasibility.json", out)
    print({"gate_passed": gate_passed,
           "gate": {k: (v["value"], v["pass"]) for k, v in gate.items()},
           "unique_edges": len(edge_rows),
           "edges_by_predicate": out["inventory"]["edges_by_predicate"],
           "coaffilation_components": out["structure"]["company_institution_coaffiliation"]["components_sizes"][:5]})


if __name__ == "__main__":
    main()
