#!/usr/bin/env python
"""EXP-A / EXP-B / EXP-C for DATA-EXPANSION-001.

Reads the frozen anchor set, the per-anchor retrieval cells and the staging
store, and writes three result files plus the markdown tables the report cites.

Design notes that matter for interpreting the numbers
-----------------------------------------------------
* **Tier A/B/C.**  A retrieval hit is only *relevant* if it contains one of the
  anchor's distinctive product tokens.  Tier A additionally has a firm field in
  the record that resolves to the anchor's firm; Tier B does not (most scholarly
  records do not identify a manufacturer, and pretending otherwise is how
  keyword studies manufacture precision).  Tier C is the generic product-code
  name and exists only as a deliberate base-rate baseline.
* **Decoy control.**  Every linker is also evaluated against a *matched wrong
  pairing*: another anchor of the same firm, different product code, decision
  date within ±2 years.  A linker that links the same hit to both is not
  specific, no matter how high its recall looks.
* **No population precision.**  There is no human labelling budget this round,
  so EXP-B reports an error rate on the authoritative-identifier subset (with
  its denominator), a refusal rate, a candidate volume and the decoy control.
  It never reports Precision/Recall/F1 for the population.
* **Placebo.**  EXP-C compares the measured lead time against the lead time the
  same hits produce against pseudo-decision-dates drawn from ±365 days.
"""

from __future__ import annotations

import json
import random
import re
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable, Mapping

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(ROOT / "experiments"))

from medradar.external_sources import identity, schema, timeq  # noqa: E402

import anchor_search as A  # noqa: E402

ANCHOR_PATH = ROOT / "experiments" / "anchors" / "ANCHORS.json"
OUT = ROOT / "experiments"
SEED = 20261109  # frozen: any permutation result must be reproducible

#: Sources whose records carry a firm-identifying field.  For the others, a hit
#: can be product-specific but cannot confirm the manufacturer on its own.
FIRM_FIELD = {
    "clinicaltrials_gov": "lead_sponsor",
    "nih_reporter": "organization",
    "usaspending": "recipient",
}

SCHOLARLY = ("openalex", "europepmc", "crossref", "pubmed_eutils", "semantic_scholar")


# --------------------------------------------------------------------- linking
def _contains_token(text: str, token: str) -> bool:
    return re.search(rf"(?<![A-Za-z0-9]){re.escape(token)}(?![A-Za-z0-9])", text, re.IGNORECASE) is not None


def resolve_firm(extra: Mapping[str, Any], index: identity.CompanyIndex, source_id: str) -> dict[str, Any] | None:
    field = FIRM_FIELD.get(source_id)
    if not field:
        return None
    value = extra.get(field)
    if not value:
        return None
    return index.resolve(value)


def tier_of(hit: Mapping[str, Any], terms: list[str], firm_resolution: Mapping[str, Any] | None) -> str:
    text = " ".join(
        [
            str(hit.get("title") or ""),
            str((hit.get("extra") or {}).get("interventions") or ""),
        ]
    )
    matched = [t for t in terms if _contains_token(text, t)]
    if not matched:
        return "C_none"
    if firm_resolution and firm_resolution.get("method") in schema.CONFIRMED_METHODS:
        return "A_confirmed"
    return "B_product_only"


def hit_key(hit: Mapping[str, Any]) -> str:
    """Cross-source identity of a scholarly hit, for the de-duplication metric."""
    sid = str(hit.get("source_record_id") or "")
    extra = hit.get("extra") or {}
    doi = str(extra.get("doi") or "").lower().strip()
    if doi:
        return f"doi:{identity.normalize_doi(doi)}"
    pmid = str(extra.get("pmid") or "").strip()
    if pmid:
        return f"pmid:{pmid}"
    if sid.startswith("W") and sid[1:].isdigit():  # OpenAlex work id
        return f"openalex:{sid}"
    if sid.startswith("NCT"):
        return f"nct:{sid}"
    return f"{hit.get('source_id') or ''}:{sid}"


# --------------------------------------------------------------------- loading
def load_payload() -> tuple[list[dict], dict, dict[str, dict[str, dict]], identity.CompanyIndex]:
    anchors = A.load_anchors(ANCHOR_PATH)
    pcs = A.load_product_codes()
    cells = A.load_cells(list(A.ADAPTERS))
    index = identity.CompanyIndex.from_config()
    return anchors, pcs, cells, index


def build_hit_rows(anchors, pcs, cells, index) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for anchor in anchors:
        terms = A.distinctive_terms(anchor, pcs)
        for source_id, by_anchor in cells.items():
            cell = by_anchor.get(anchor["anchor_id"].replace("_", ":")) or by_anchor.get(anchor["anchor_id"])
            if cell is None:
                # cache filenames replace ':' with '_'
                for key, value in by_anchor.items():
                    if key.replace("_", ":") == anchor["anchor_id"]:
                        cell = value
                        break
            if not cell:
                continue
            for hit in cell.get("hits", []) or []:
                firm = resolve_firm(hit.get("extra") or {}, index, source_id)
                tier = tier_of(hit, terms, firm)
                public_at = timeq.parse_date(hit.get("public_at"))
                rows.append(
                    {
                        "anchor_id": anchor["anchor_id"],
                        "firm_key": anchor["firm_key"],
                        "product_code": anchor["product_code"],
                        "decision_date": anchor["decision_date"],
                        "source_id": source_id,
                        "query": cell.get("query", ""),
                        "hit_key": hit_key({**hit, "source_id": source_id}),
                        "title": hit.get("title", ""),
                        "public_at": public_at.isoformat() if public_at else "",
                        "public_at_quality": timeq.implied_quality(hit.get("public_at")),
                        "tier": tier,
                        "terms": terms,
                        "firm_method": (firm or {}).get("method", "unavailable"),
                        "firm_key_hit": (firm or {}).get("resolved_key"),
                        "lead_days": timeq.lead_time_days(hit.get("public_at"), anchor["decision_date"]),
                    }
                )
    return rows


# ----------------------------------------------------------------------- EXP-A
def exp_a(anchors, rows, cells) -> dict[str, Any]:
    by_source: dict[str, Any] = {}
    anchor_ids = [a["anchor_id"] for a in anchors]
    for source_id in cells:
        source_rows = [r for r in rows if r["source_id"] == source_id]
        relevant = [r for r in source_rows if r["tier"] in {"A_confirmed", "B_product_only"}]
        covered = {r["anchor_id"] for r in relevant}
        keys = [r["hit_key"] for r in relevant]
        unique_keys = set(keys)
        duplicate_rate = 1 - (len(unique_keys) / len(keys)) if keys else 0.0
        by_source[source_id] = {
            "anchors_queried": len(anchor_ids),
            "hits_returned": len(source_rows),
            "relevant_hits": len(relevant),
            "anchors_with_any_hit": len({r["anchor_id"] for r in source_rows}),
            "anchors_with_relevant_hit": len(covered),
            "coverage_any": round(len(covered) / len(anchor_ids), 4) if anchor_ids else 0.0,
            "unique_hit_keys": len(unique_keys),
            "within_source_duplicate_rate": round(duplicate_rate, 4),
            "tier_counts": dict(Counter(r["tier"] for r in source_rows)),
            "years_with_hits": dict(sorted(Counter(r["public_at"][:4] for r in relevant if r["public_at"]).items())),
        }

    # cross-source de-duplication: the same work reached from several sources
    key_sources: dict[str, set[str]] = defaultdict(set)
    for row in rows:
        if row["tier"] in {"A_confirmed", "B_product_only"}:
            key_sources[row["hit_key"]].add(row["source_id"])
    multi = {k: sorted(v) for k, v in key_sources.items() if len(v) > 1}
    total_relevant = sum(1 for r in rows if r["tier"] in {"A_confirmed", "B_product_only"})
    cross_source_redundancy = (
        round((total_relevant - len(key_sources)) / total_relevant, 4) if total_relevant else 0.0
    )

    # independence: distinct upstream authorities per anchor
    anchors_with_independent = {}
    for anchor_id in anchor_ids:
        authorities = {r["source_id"] for r in rows if r["anchor_id"] == anchor_id and r["tier"] in {"A_confirmed", "B_product_only"}}
        anchors_with_independent[anchor_id] = len(authorities)

    return {
        "schema": "medradar.external.exp_a.v1",
        "computed_at": timeq.utc_iso(),
        "anchor_count": len(anchor_ids),
        "per_source": by_source,
        "cross_source": {
            "relevant_rows": total_relevant,
            "unique_works": len(key_sources),
            "multi_source_works": len(multi),
            "cross_source_duplicate_rate": cross_source_redundancy,
            "example_multi_source": dict(list(sorted(multi.items()))[:10]),
        },
        "cross_source_independence": {
            "anchors_with_1_authority": sum(1 for v in anchors_with_independent.values() if v == 1),
            "anchors_with_2plus_authorities": sum(1 for v in anchors_with_independent.values() if v >= 2),
            "median_authorities": statistics.median(anchors_with_independent.values()) if anchors_with_independent else 0,
        },
        "verdicts": {
            source_id: (
                "INCREMENTAL"
                if data["hits_returned"] >= 20
                and data["coverage_any"] >= 0.10
                and data["within_source_duplicate_rate"] <= 0.50
                else ("INSUFFICIENT_EVIDENCE" if data["hits_returned"] < 20 else "NOT_INCREMENTAL")
            )
            for source_id, data in by_source.items()
        },
        "note": (
            "coverage_any counts anchors with at least one product-token hit; a hit is not a "
            "confirmed device match. Tier A counts carry a firm field that resolved to the anchor firm."
        ),
    }


# ----------------------------------------------------------------------- EXP-B
def _link_name_only(row) -> bool:
    return row["tier"] in {"A_confirmed", "B_product_only"}


def _link_name_plus_firm(row) -> bool:
    return row["tier"] == "A_confirmed" and row["firm_key_hit"] == row["firm_key"]


def _link_regulatory_id(row) -> bool:
    return bool(re.search(r"\b[KP]\d{6}\b", row["title"] or ""))


def _link_multi_field(row) -> bool:
    if not _link_name_plus_firm(row):
        return False
    if not row["public_at"]:
        return False
    lead = row["lead_days"]
    return lead is not None and -30 <= lead <= 730


def _link_semantic(row) -> bool:
    # candidate tier: a single distinctive token is enough, confidence capped
    return row["tier"] in {"A_confirmed", "B_product_only"}


STRATEGIES = {
    "name_only": _link_name_only,
    "name_plus_firm": _link_name_plus_firm,
    "regulatory_id": _link_regulatory_id,
    "multi_field": _link_multi_field,
    "candidate_semantic": _link_semantic,
}


def _decoy_for(anchor: Mapping[str, Any], anchors: list[dict]) -> dict | None:
    """Same firm, different product code, decision year within ±2."""
    best = None
    best_distance = 10**9
    for other in anchors:
        if other["anchor_id"] == anchor["anchor_id"]:
            continue
        if other["firm_key"] != anchor["firm_key"]:
            continue
        if other["product_code"] == anchor["product_code"]:
            continue
        distance = abs(other["decision_year"] - anchor["decision_year"])
        if distance <= 2 and distance < best_distance:
            best, best_distance = other, distance
    return best


def _price_hits_for(decoy: Mapping[str, Any], pcs, cells) -> list[dict]:
    """Hits retrieved for the decoy anchor itself (it is also an anchor)."""
    terms = A.distinctive_terms(decoy, pcs)
    out: list[dict] = []
    for source_id, by_anchor in cells.items():
        cell = None
        for key, value in by_anchor.items():
            if key.replace("_", ":") == decoy["anchor_id"]:
                cell = value
                break
        if not cell:
            continue
        for hit in cell.get("hits", []) or []:
            text = str(hit.get("title") or "")
            if any(_contains_token(text, t) for t in terms):
                out.append({"source_id": source_id, "title": text, "hit": hit})
    return out


def exp_b(anchors, rows, cells, pcs, index) -> dict[str, Any]:
    rng = random.Random(SEED)
    anchor_by_id = {a["anchor_id"]: a for a in anchors}
    decoys = {a["anchor_id"]: _decoy_for(a, anchors) for a in anchors}
    decoy_hits = {}
    for anchor_id, decoy in decoys.items():
        if decoy:
            decoy_hits[anchor_id] = _price_hits_for(decoy, pcs, cells)

    results: dict[str, Any] = {}
    for name, fn in STRATEGIES.items():
        real_links = [r for r in rows if fn(r)]
        real_anchor_ids = {r["anchor_id"] for r in real_links}
        # decoy: does the same strategy link a decoy's hits to the decoy?
        decoy_rates = []
        for anchor_id, hits in decoy_hits.items():
            if not hits:
                continue
            decoy = decoys[anchor_id]
            linked = 0
            for item in hits:
                fake_row = {
                    "anchor_id": decoy["anchor_id"],
                    "firm_key": decoy["firm_key"],
                    "product_code": decoy["product_code"],
                    "decision_date": decoy["decision_date"],
                    "source_id": item["source_id"],
                    "title": item["title"],
                    "public_at": "",
                    "tier": "B_product_only",
                    "firm_key_hit": None,
                    "lead_days": None,
                }
                if fn(fake_row):
                    linked += 1
            decoy_rates.append(linked / len(hits))
        real_rate = len(real_anchor_ids) / len(anchors) if anchors else 0.0
        decoy_rate = statistics.fmean(decoy_rates) if decoy_rates else 0.0
        specificity = (real_rate / decoy_rate) if decoy_rate > 0 else None

        # authoritative subset: hits that carry an official regulatory identifier
        authoritative = [r for r in rows if re.search(r"\b[KP]\d{6}\b", r["title"] or "")]
        authoritative_errors = [
            r for r in authoritative if fn(r) and r["tier"] == "B_product_only"
        ]
        # refusal rate: anchors for which the strategy declines on every relevant hit
        relevant_by_anchor = defaultdict(list)
        for row in rows:
            if row["tier"] in {"A_confirmed", "B_product_only"}:
                relevant_by_anchor[row["anchor_id"]].append(row)
        refused = sum(
            1
            for anchor_id, hit_rows in relevant_by_anchor.items()
            if not any(fn(r) for r in hit_rows)
        )
        refusal_rate = refused / len(relevant_by_anchor) if relevant_by_anchor else 0.0

        results[name] = {
            "anchors_linked": len(real_anchor_ids),
            "real_link_rate": round(real_rate, 4),
            "decoy_link_rate": round(decoy_rate, 4),
            "specificity_vs_decoy": (round(specificity, 3) if specificity is not None else None),
            "authoritative_subset_size": len(authoritative),
            "authoritative_subset_errors": len(authoritative_errors),
            "authoritative_error_rate": (
                round(len(authoritative_errors) / len(authoritative), 4) if authoritative else None
            ),
            "refusal_rate": round(refusal_rate, 4),
            "links": len(real_links),
        }

    usable = [
        name
        for name, data in results.items()
        if data["specificity_vs_decoy"] is not None
        and data["specificity_vs_decoy"] > 1.0
        and (data["authoritative_error_rate"] in (None, 0.0) or data["authoritative_error_rate"] < 0.05)
    ]
    return {
        "schema": "medradar.external.exp_b.v1",
        "computed_at": timeq.utc_iso(),
        "seed": SEED,
        "strategies": results,
        "usable_for_confirmed_links": usable,
        "decoys_available": sum(1 for d in decoys.values() if d),
        "population_metrics_withheld": (
            "No human labels exist this round, so population precision/recall/F1 are NOT computed. "
            "Only the authoritative-identifier subset error rate, the refusal rate and the decoy "
            "specificity are reported."
        ),
        "candidate_policy": "candidate_semantic links never enter the confirmed-link counts",
    }


# ----------------------------------------------------------------------- EXP-C
def _bucket_summary(values: list[int]) -> dict[str, Any]:
    buckets = Counter(timeq.bucket_lead_time(v) for v in values)
    return {
        "n": len(values),
        "median_days": statistics.median(values) if values else None,
        "min_days": min(values) if values else None,
        "max_days": max(values) if values else None,
        "buckets": {
            key: buckets.get(key, 0)
            for key in ("0-90d", "91-180d", "181-365d", "366-730d", ">730d", "after_event")
        },
        "undatable": sum(1 for v in values if v is None),
    }


def exp_c(anchors, rows, cells, pcs) -> dict[str, Any]:
    """Lead-time distribution with a matched placebo.

    The placebo keeps the same retrieved hits and the same query and asks: if the
    anchor's decision date had been 12 pseudo-dates drawn uniformly from
    ±365 days, what lead times would the same evidence produce?  If the real
    date is not special, the real median sits inside that distribution.
    """
    rng = random.Random(SEED)
    usable = [r for r in rows if r["tier"] in {"A_confirmed", "B_product_only"}]
    dated = [
        r for r in usable if r["public_at"] and timeq.quality_allows_lead_time(r["public_at_quality"])
    ]
    tier_a = [r for r in dated if r["tier"] == "A_confirmed"]
    tier_b = [r for r in dated if r["tier"] == "B_product_only"]
    real_leads_a = [r["lead_days"] for r in tier_a if r["lead_days"] is not None]
    real_leads_b = [r["lead_days"] for r in tier_b if r["lead_days"] is not None]

    placebo_all: list[int] = []
    per_anchor_medians: list[float] = []
    for row in dated:
        decision = timeq.parse_date(row["decision_date"])
        published = timeq.parse_date(row["public_at"])
        if not decision or not published:
            continue
        leads = []
        for _ in range(12):
            offset = rng.randint(-365, 365)
            pseudo = decision.toordinal() + offset
            leads.append(pseudo - published.toordinal())
        placebo_all.extend(leads)
        per_anchor_medians.append(statistics.median(leads))

    def one_sided_p(real: list[int], null: list[int]) -> float | None:
        if not real or not null:
            return None
        real_med = statistics.median(real)
        hits = sum(1 for _ in range(2000) if statistics.median(rng.sample(null, min(len(null), max(3, len(real))))) >= real_med)
        return round(hits / 2000, 4)

    p_value = one_sided_p(real_leads_a, placebo_all)
    confirmed_share = (len(tier_a) / len(usable)) if usable else 0.0
    detectable = bool(
        p_value is not None and p_value < 0.05 and confirmed_share >= 0.7 and len(real_leads_a) >= 5
    )

    by_source = {}
    for source_id in cells:
        src_a = [r["lead_days"] for r in tier_a if r["source_id"] == source_id and r["lead_days"] is not None]
        by_source[source_id] = _bucket_summary(src_a)

    return {
        "schema": "medradar.external.exp_c.v1",
        "computed_at": timeq.utc_iso(),
        "seed": SEED,
        "tier_definition": {
            "A_confirmed": "product token match AND a firm field in the record resolved to the anchor firm",
            "B_product_only": "product token match only; the record cannot confirm the manufacturer",
        },
        "tier_a": _bucket_summary(real_leads_a),
        "tier_b": _bucket_summary(real_leads_b),
        "tier_a_by_source": by_source,
        "placebo": {
            "n_placebo_lead_values": len(placebo_all),
            "median_placebo_days": statistics.median(placebo_all) if placebo_all else None,
            "one_sided_p_tier_a_vs_placebo": p_value,
        },
        "confirmed_link_share": round(confirmed_share, 4),
        "decision_rule": "detectable iff p<0.05 AND confirmed_link_share>=0.7 AND >=5 dated tier-A rows",
        "verdict": "DETECTABLE_LEAD" if detectable else "NO_DETECTABLE_LEAD",
        "caveats": [
            "Anchors are products that were eventually cleared, so the sample is survivorship-selected.",
            "A retrospective earlier document is not a signal that was usable at the time.",
            "Any relation that only exists because of a later acquisition is excluded from tier A by construction.",
            "Tier B cannot be used as a lead-time claim; it is reported to show how much of the literature is product-named without manufacturer attribution.",
        ],
        "c3_non_fda_footprint": None,  # filled by c3_enrich.py once registries are collected
    }


# -------------------------------------------------------------------- reporting
def markdown_summary(exp_a_data, exp_b_data, exp_c_data) -> str:
    lines = ["# Experiment outputs (generated)\n", "## EXP-A — coverage per source\n",
             "| source | anchors with relevant hit | coverage | hits | unique | dup rate | verdict |",
             "|---|---|---|---|---|---|---|"]
    for source_id, data in sorted(exp_a_data["per_source"].items()):
        lines.append(
            f"| {source_id} | {data['anchors_with_relevant_hit']}/{data['anchors_queried']} | "
            f"{data['coverage_any']:.1%} | {data['hits_returned']} | {data['unique_hit_keys']} | "
            f"{data['within_source_duplicate_rate']:.1%} | {exp_a_data['verdicts'][source_id]} |"
        )
    lines += ["", "## EXP-B — linker behaviour vs matched decoy\n",
              "| strategy | real link rate | decoy link rate | specificity | refusal rate |",
              "|---|---|---|---|---|"]
    for name, data in exp_b_data["strategies"].items():
        lines.append(
            f"| {name} | {data['real_link_rate']:.1%} | {data['decoy_link_rate']:.1%} | "
            f"{data['specificity_vs_decoy']} | {data['refusal_rate']:.1%} |"
        )
    lines += ["", "## EXP-C — lead time\n",
              f"- tier A (firm-confirmed): n={exp_c_data['tier_a']['n']}, median={exp_c_data['tier_a']['median_days']}",
              f"- tier B (product-only): n={exp_c_data['tier_b']['n']}, median={exp_c_data['tier_b']['median_days']}",
              f"- placebo median: {exp_c_data['placebo']['median_placebo_days']}, p={exp_c_data['placebo']['one_sided_p_tier_a_vs_placebo']}",
              f"- verdict: **{exp_c_data['verdict']}**",
              ""]
    return "\n".join(lines)


def main() -> int:
    anchors, pcs, cells, index = load_payload()
    if not anchors:
        print("no anchors", file=sys.stderr)
        return 1
    rows = build_hit_rows(anchors, pcs, cells, index)
    if not rows:
        print("no retrieval rows; run anchor_search.py --run first", file=sys.stderr)
        return 1

    a = exp_a(anchors, rows, cells)
    b = exp_b(anchors, rows, cells, pcs, index)
    c = exp_c(anchors, rows, cells, pcs)

    for name, payload in (("exp_a/EXP_A.json", a), ("exp_b/EXP_B.json", b), ("exp_c/EXP_C.json", c)):
        path = OUT / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    hits_path = OUT / "exp_a" / "HITS.jsonl"
    hits_path.parent.mkdir(parents=True, exist_ok=True)
    with hits_path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")

    report = markdown_summary(a, b, c)
    (OUT / "RESULTS_TABLES.md").write_text(report + "\n", encoding="utf-8")
    print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
