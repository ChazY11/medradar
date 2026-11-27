"""EXP-H1 — cross-database de-duplication, identifier linkage, metadata disagreement.

Reads only the saved datasets under ``DATASETS/scholarly/`` (no network) and
writes three artefacts into ``experiments/scholarly/``:

    EXP_H1_ANCHOR_MATRIX.jsonl   one row per (anchor, source) with what that
                                 source actually returned
    EXP_H1_DEDUP.json            the full measurement
    EXP_H1_DEDUP_SUMMARY.json    the same measurement stated in plain language

Nothing is repaired. A disagreement is written down as a disagreement.

    python experiments/scholarly/analyze_exp_h1.py
"""

from __future__ import annotations

import json
import os
import re
import sys
from collections import Counter, defaultdict
from itertools import combinations

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from CONNECTORS.scholarly import _util as U  # noqa: E402
from hz.timeq import parse_iso  # noqa: E402

EXP = os.path.dirname(os.path.abspath(__file__))

# The five sources EXP-H1 is defined over (the brief's core set), plus the two
# optional ones the brief allows.
CORE_SOURCES = ["openalex", "crossref", "europepmc", "pubmed_eutils"]
OPTIONAL_SOURCES = ["semantic_scholar", "openaire"]
ALL_SOURCES = CORE_SOURCES + OPTIONAL_SOURCES

SOURCE_LABEL = {
    "openalex": "OpenAlex",
    "crossref": "Crossref",
    "europepmc": "Europe PMC",
    "pubmed_eutils": "PubMed (E-utilities)",
    "semantic_scholar": "Semantic Scholar",
    "openaire": "OpenAIRE Graph",
}


# --------------------------------------------------------------------- loading
def load_records(source_id: str) -> list[dict]:
    path = os.path.join(U.DATASETS, source_id, "records.jsonl")
    if not os.path.isfile(path):
        return []
    out = []
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out


def rec_ids(rec: dict) -> dict[str, set[str]]:
    """scheme -> set of values, straight from the record's identifier list."""
    d: dict[str, set[str]] = defaultdict(set)
    for i in rec.get("identifiers") or []:
        s = (i.get("scheme") or "").lower()
        v = i.get("value")
        if s and v:
            d[s].add(str(v))
    return d


def rec_doi(rec: dict) -> str | None:
    for i in rec.get("identifiers") or []:
        if i.get("scheme") == "doi":
            return U.norm_doi(i.get("value"))
    return None


def rec_pmid(rec: dict) -> str | None:
    for i in rec.get("identifiers") or []:
        if i.get("scheme") == "pmid":
            v = str(i.get("value"))
            return re.sub(r"\D", "", v) or None
    return None


def rec_title(rec: dict) -> str:
    a = rec.get("attributes") or {}
    return U.norm_ws(a.get("title") or a.get("mainTitle") or a.get("brief_title")
                     or rec.get("original_name"))


def rec_date(rec: dict) -> str | None:
    """The source's single best 'when was this work published' date."""
    a = rec.get("attributes") or {}
    src = rec.get("source_id")
    if src == "openalex":
        return a.get("publication_date")
    if src == "crossref":
        d = a.get("dates") or {}
        return d.get("issued") or d.get("published") or d.get("published_online") \
            or d.get("published_print")
    if src == "europepmc":
        d = a.get("dates") or {}
        return d.get("firstPublicationDate") or d.get("electronicPublicationDate")
    if src == "pubmed_eutils":
        d = a.get("dates") or {}
        return d.get("article_date_electronic") or d.get("pub_date")
    if src == "semantic_scholar":
        return (a.get("dates") or {}).get("publicationDate")
    if src == "openaire":
        return a.get("publicationDate")
    return None


def rec_author_count(rec: dict) -> int | None:
    a = rec.get("attributes") or {}
    v = a.get("author_count")
    return v if isinstance(v, int) else None


def rec_author_edges(rec: dict) -> tuple[str | None, str | None]:
    a = rec.get("attributes") or {}
    return a.get("first_author_family"), a.get("last_author_family")


# ------------------------------------------------------------------ main build
def main() -> int:
    anchors_doc = U.read_json(U.ANCHORS_PATH)
    anchors = anchors_doc["anchors"]
    by_doi = {a["doi"]: a for a in anchors}

    per_source: dict[str, list[dict]] = {s: load_records(s) for s in ALL_SOURCES}

    # ---------------- for each source, map anchor DOI -> records -------------
    rows: list[dict] = []
    matched: dict[tuple[str, str], list[dict]] = defaultdict(list)  # (source, doi) -> recs

    for s in ALL_SOURCES:
        for rec in per_source[s]:
            doi = rec_doi(rec)
            # PubMed/S2/OpenAIRE fallback: resolve DOI from the anchor whose PMID
            # matches, so an anchor is not lost purely because a source omitted
            # the DOI field.
            if not doi:
                pmid = rec_pmid(rec)
                if pmid:
                    for a in anchors:
                        if str((a.get("ids") or {}).get("pmid") or "").endswith(pmid):
                            doi = a["doi"]
                            break
            if doi and doi in by_doi:
                matched[(s, doi)].append(rec)
            elif doi:
                matched[(s, f"__offanchor__:{doi}")].append(rec)
            else:
                matched[(s, "__unresolved__")].append(rec)

    # ---------------- per (anchor, source) matrix ---------------------------
    for a in anchors:
        doi = a["doi"]
        for s in ALL_SOURCES:
            recs = matched.get((s, doi)) or []
            entry = {
                "anchor_no": a["anchor_no"],
                "firm": a["firm"],
                "tier": a["tier"],
                "anchor_doi": doi,
                "source_id": s,
                "source_label": SOURCE_LABEL[s],
                "found": bool(recs),
                "record_count": len(recs),
                "identifiers_exposed": sorted({
                    k for r in recs for k in rec_ids(r).keys()
                }),
                "pmid": sorted({rec_pmid(r) for r in recs if rec_pmid(r)}),
                "publication_date": rec_date(recs[0]) if recs else None,
                "title": rec_title(recs[0]) if recs else None,
                "author_count": rec_author_count(recs[0]) if recs else None,
                "first_author_family": rec_author_edges(recs[0])[0] if recs else None,
                "last_author_family": rec_author_edges(recs[0])[1] if recs else None,
                "raw_ref": recs[0].get("raw_ref") if recs else None,
            }
            rows.append(entry)

    U.write_jsonl(os.path.join(EXP, "EXP_H1_ANCHOR_MATRIX.jsonl"), rows)

    # ---------------- counts ------------------------------------------------
    source_rows_fetched = {s: sum(e["record_count"] for e in rows if e["source_id"] == s)
                           for s in ALL_SOURCES}
    anchor_hits = {s: sum(1 for e in rows if e["source_id"] == s and e["found"])
                   for s in ALL_SOURCES}
    total_rows_all = sum(source_rows_fetched.values())
    total_anchor_hits = sum(anchor_hits.values())

    # distinct works over the union, using the pre-registered precedence
    work_keys: set[str] = set()
    key_source: dict[str, set[str]] = defaultdict(set)
    key_to_doi: dict[str, str] = {}
    for s in ALL_SOURCES:
        for rec in per_source[s]:
            doi = rec_doi(rec)
            pmid = rec_pmid(rec)
            if doi:
                key = f"doi:{doi}"
            elif pmid:
                key = f"pmid:{pmid}"
            else:
                key = f"hash:{rec.get('content_hash')}"
            work_keys.add(key)
            key_source[key].add(s)
            if doi:
                key_to_doi[key] = doi

    distinct_works = len(work_keys)
    dedup_ratio = (distinct_works / total_rows_all) if total_rows_all else None
    dedup_ratio_anchor_hits = (distinct_works / total_anchor_hits) if total_anchor_hits else None

    # ---------------- identifier coverage ----------------------------------
    id_schemes = ["doi", "pmid", "pmcid", "openalex_id", "arxiv",
                  "nih_core_project_num", "cordis_rcn", "s2_corpus_id", "mag"]
    id_coverage = {}
    for s in ALL_SOURCES:
        recs = per_source[s]
        cov = {}
        for scheme in id_schemes:
            cov[scheme] = sum(1 for r in recs if scheme in rec_ids(r))
        id_coverage[s] = {"records": len(recs), "with_scheme": cov}

    # grant numbers in funding metadata, per source
    grant_field_coverage = {}
    for s in ALL_SOURCES:
        recs = per_source[s]
        n = 0
        for r in recs:
            a = r.get("attributes") or {}
            if s == "europepmc" and a.get("grants"):
                n += 1
            elif s == "pubmed_eutils" and a.get("grant_list"):
                n += 1
            elif s == "crossref" and a.get("funders") and any(
                    f.get("awards") for f in a["funders"]):
                n += 1
            elif s == "openalex" and a.get("awards"):
                n += 1
        grant_field_coverage[s] = n

    # ---------------- cross-identifier verification -----------------------
    # For each anchor, collect every source's PMID(s) and PMCID(s) and compare.
    xid = []
    pmid_agree = pmid_conflict = pmid_single = pmid_absent = 0
    pmcid_agree = pmcid_conflict = pmcid_single = 0
    for a in anchors:
        doi = a["doi"]
        pmids: dict[str, list[str]] = {}
        pmcids: dict[str, list[str]] = {}
        openalex_pmid = None
        oa_ids = a.get("ids") or {}
        if oa_ids.get("pmid"):
            openalex_pmid = re.sub(r"\D", "", str(oa_ids["pmid"]))
            pmids.setdefault(openalex_pmid, []).append("openalex")
        if oa_ids.get("pmcid"):
            pmcids.setdefault(str(oa_ids["pmcid"]), []).append("openalex")
        for s in ALL_SOURCES:
            for r in matched.get((s, doi)) or []:
                p = rec_pmid(r)
                if p:
                    pmids.setdefault(p, []).append(s)
                for i in r.get("identifiers") or []:
                    if i.get("scheme") == "pmcid":
                        pmcids.setdefault(str(i["value"]), []).append(s)
        distinct_pmids = sorted(pmids)
        distinct_pmcids = sorted(pmcids)
        if len(distinct_pmids) == 0:
            pmid_absent += 1
            pmid_status = "ABSENT_ALL_SOURCES"
        elif len(distinct_pmids) == 1:
            pmid_single += 1
            pmid_status = "SINGLE_VALUE_AGREED" if len(pmids[distinct_pmids[0]]) > 1 \
                else "SINGLE_SOURCE_ONLY"
        else:
            pmid_conflict += 1
            pmid_status = "CONFLICT"
        if len(distinct_pmcids) == 0:
            pmcid_status = "ABSENT_ALL_SOURCES"
        elif len(distinct_pmcids) == 1:
            pmcid_single += 1
            pmcid_status = ("SINGLE_VALUE_AGREED"
                            if len(pmcids[distinct_pmcids[0]]) > 1
                            else "SINGLE_SOURCE_ONLY")
        else:
            pmcid_conflict += 1
            pmcid_status = "CONFLICT"
        xid.append({
            "anchor_no": a["anchor_no"], "anchor_doi": doi,
            "pmid_values": {k: sorted(set(v)) for k, v in pmids.items()},
            "pmid_status": pmid_status,
            "pmcid_values": {k: sorted(set(v)) for k, v in pmcids.items()},
            "pmcid_status": pmcid_status,
            "openalex_exposes_pmid": bool(openalex_pmid),
        })

    # ---------------- metadata disagreement ------------------------------
    title_exact = title_prefix = title_diff = 0
    author_count_delta = Counter()
    date_deltas = Counter()
    date_conflicts: list[dict] = []
    author_conflicts: list[dict] = []
    title_conflicts: list[dict] = []

    for a in anchors:
        doi = a["doi"]
        present = {s: (matched.get((s, doi)) or [None])[0] for s in ALL_SOURCES}
        present = {s: r for s, r in present.items() if r}
        if len(present) < 2:
            continue
        # titles
        titles = {s: rec_title(r) for s, r in present.items() if rec_title(r)}
        norm = {s: t.lower() for s, t in titles.items()}
        vals = set(norm.values())
        if len(vals) == 1:
            title_exact += 1
        else:
            # prefix relationship is a truncation signature, not agreement
            vs = sorted(vals)
            if any(x.startswith(y) for x in vs for y in vs if x != y):
                title_prefix += 1
            else:
                title_diff += 1
            title_conflicts.append({"anchor_doi": doi, "titles": titles})
        # author counts
        counts = {s: rec_author_count(r) for s, r in present.items()}
        counts = {s: c for s, c in counts.items() if c is not None}
        if len(counts) >= 2:
            lo, hi = min(counts.values()), max(counts.values())
            author_count_delta[hi - lo] += 1
            if hi != lo:
                author_conflicts.append({"anchor_doi": doi, "author_counts": counts,
                                         "delta": hi - lo})
        # dates
        dates = {s: rec_date(r) for s, r in present.items()}
        dates = {s: d for s, d in dates.items() if d and parse_iso(d)}
        if len(dates) >= 2:
            base = dates.get("openalex")
            if base is None:
                continue
            b = parse_iso(base)
            ds = {}
            for s, d in dates.items():
                p = parse_iso(d)
                if p:
                    ds[s] = (p - b).days
            if ds:
                spread = max(ds.values()) - min(ds.values())
                bucket = _bucket(spread)
                date_deltas[bucket] += 1
                if spread > 0:
                    date_conflicts.append({
                        "anchor_doi": doi,
                        "openalex_date": base,
                        "per_source_date": dates,
                        "per_source_delta_days_vs_openalex": ds,
                        "max_spread_days": spread,
                        "bucket": bucket,
                    })

    # ---------------- per-source marginal contribution --------------------
    marginal = {}
    for s in ALL_SOURCES:
        only = sum(1 for k, ss in key_source.items() if ss == {s})
        marginal[s] = {
            "unique_works_only_this_source": only,
            "records": source_rows_fetched[s],
            "anchor_hits": anchor_hits[s],
            "anchors_where_this_is_the_only_source": sum(
                1 for a in anchors
                if (matched.get((s, a["doi"])) or [])
                and not any(matched.get((o, a["doi"])) for o in ALL_SOURCES if o != s)
            ),
        }

    # ---------------- anchors by how many sources hold them ---------------
    source_count_hist = Counter()
    for a in anchors:
        n = sum(1 for s in ALL_SOURCES if matched.get((s, a["doi"])))
        source_count_hist[n] += 1

    doc = {
        "experiment": "EXP-H1",
        "title": "Cross-database de-duplication of the same work, identifier linkage, "
                 "and metadata disagreement over a pre-registered fixed sample",
        "selection_rule": "experiments/scholarly/EXP_H1_SELECTION_RULE.md",
        "generated_at": U.utc_now(),
        "anchor_count": len(anchors),
        "sources_queried": ALL_SOURCES,
        "core_sources": CORE_SOURCES,
        "optional_sources": OPTIONAL_SOURCES,
        "counts": {
            "source_rows_fetched": total_rows_all,
            "per_source_rows_fetched": source_rows_fetched,
            "anchor_source_hits": total_anchor_hits,
            "per_source_anchor_hits": anchor_hits,
            "distinct_works_after_dedup": distinct_works,
            "dedup_ratio_rows": dedup_ratio,
            "dedup_ratio_anchor_hits": dedup_ratio_anchor_hits,
            "off_anchor_records": sum(
                1 for k, v in matched.items()
                if str(k[1]).startswith("__offanchor__") for _ in v),
            "unresolved_records": sum(
                1 for k, v in matched.items() if k[1] == "__unresolved__" for _ in v),
        },
        "anchors_by_number_of_sources_holding_them": dict(sorted(source_count_hist.items())),
        "identifier_coverage": id_coverage,
        "grant_metadata_coverage": grant_field_coverage,
        "cross_identifier_verification": {
            "pmid": {"absent_all_sources": pmid_absent,
                     "single_value": pmid_single,
                     "conflict": pmid_conflict},
            "pmcid": {"single_value": pmcid_single, "conflict": pmcid_conflict},
            "rows": xid,
        },
        "metadata_disagreement": {
            "title": {"all_sources_identical": title_exact,
                      "prefix_of_each_other": title_prefix,
                      "materially_different": title_diff,
                      "examples": title_conflicts[:15]},
            "author_count_delta_distribution": dict(sorted(author_count_delta.items())),
            "author_examples": author_conflicts[:15],
            "publication_date_spread_buckets": dict(date_deltas),
            "date_conflict_examples": date_conflicts[:25],
            "date_conflict_count": len(date_conflicts),
        },
        "per_source_marginal": marginal,
    }
    U.write_json(os.path.join(EXP, "EXP_H1_DEDUP.json"), doc)
    print(json.dumps({k: doc["counts"][k] for k in (
        "source_rows_fetched", "anchor_source_hits",
        "distinct_works_after_dedup", "dedup_ratio_rows")}, indent=2))
    print("per_source_anchor_hits:", json.dumps(anchor_hits))
    print("anchors by #sources:", dict(sorted(source_count_hist.items())))
    print("pmid:", pmid_absent, pmid_single, pmid_conflict)
    print("titles:", title_exact, title_prefix, title_diff)
    print("date buckets:", dict(date_deltas), "conflicts:", len(date_conflicts))
    return 0


def _bucket(days: int) -> str:
    if days == 0:
        return "same_day"
    if days <= 7:
        return "1-7_days"
    if days <= 30:
        return "8-30_days"
    if days <= 180:
        return "31-180_days"
    return "over_180_days"


if __name__ == "__main__":
    raise SystemExit(main())
